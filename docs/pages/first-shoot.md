# Your first shoot cluster

A shoot cluster is a Kubernetes cluster that Gardener creates and manages for you. After the installation, creating one takes a few minutes in the dashboard. This page shows how, and how to use the new cluster.

## Before you start

- The playbook finished and the layers are [validated](getting-started.md#validating-the-deployment): all seeds are `Ready` and the cloud profile lists your machines and images.
- You can sign in to the dashboard. Users and identity providers are configured in `gardener_operator_dex`, see [Security](security.md#access-to-gardener).
- You know the name of the cloud profile you want to use, for example `openstack-a`. The profile defines the regions, machine types, images and Kubernetes versions you can choose from.

## 1. Sign in

Open the dashboard at `https://dashboard.<garden-url>`, where `<garden-url>` is the value of `gardener_operator_garden_url`. You are redirected to Dex and sign in with a static user or your identity provider.

## 2. Use or create a project

Shoot clusters live in projects. The project `seeds` only hosts the managed seeds, so use another one for your workloads. Create it in the dashboard, or add it to your configuration and run the playbook again:

```yaml
gardener_operator_projects:
  - name: demo
    members:
      - email: "admin@example.com"
        role: admin
```

A project `demo` gets the namespace `garden-demo` in the virtual garden.

## 3. Add the OpenStack credentials

A shoot needs credentials for the OpenStack project in which its VMs, networks and load balancers are created. Add them in the project, in the section for secrets of the dashboard. Use an application credential, see [Security](security.md#openstack-credentials). The dashboard stores them in the project namespace of the virtual garden.

## 4. Create the cluster

In the project, create a new cluster and select:

| Setting | What to choose |
|---------|----------------|
| Infrastructure | `openstack` and the secret from step 3. |
| Cloud profile | The profile that fits your OpenStack environment. |
| Region | The OpenStack region. |
| Kubernetes version | One of the versions in the cloud profile. |
| Worker pool | A machine type, an image (GardenLinux is the recommended one), the minimum and maximum number of nodes and the availability zones. |
| Floating pool | The external network for the cluster. |

Everything else has a sensible default. Create the cluster and watch the status. It changes from creating to ready once the control plane runs on a seed and the worker nodes joined. Depending on your OpenStack this takes some minutes.

### The same with a manifest

You can create the same cluster with `kubectl` against the [virtual garden](operations.md#virtual-garden-gardener-api). Take the names from your cloud profile and your project.

```yaml
apiVersion: core.gardener.cloud/v1beta1
kind: Shoot
metadata:
  name: demo
  namespace: garden-demo
spec:
  cloudProfile:
    name: openstack-a
  region: RegionOne
  credentialsBindingName: openstack-credentials   # the binding that holds your credentials
  provider:
    type: openstack
    infrastructureConfig:
      apiVersion: openstack.provider.extensions.gardener.cloud/v1alpha1
      kind: InfrastructureConfig
      floatingPoolName: public
      networks:
        workers: 10.250.0.0/16
    controlPlaneConfig:
      apiVersion: openstack.provider.extensions.gardener.cloud/v1alpha1
      kind: ControlPlaneConfig
      loadBalancerProvider: ovn
    workers:
      - name: worker
        machine:
          type: SCS-4V-8
          image:
            name: gardenlinux
            version: "2150.15.0"
        minimum: 1
        maximum: 3
        zones:
          - nova
  networking:
    type: cilium
    nodes: 10.250.0.0/16
  kubernetes:
    version: "1.37.2"
```

```bash
export KUBECONFIG=/var/lib/yake/gardener-operator/kubeconfig.vgarden
./.local/yake-kubectl apply -f shoot.yaml
./.local/yake-kubectl -n garden-demo get shoot demo --watch
```

!!! note "Adapt the values"
    The machine type, image, version, floating pool, zone and network ranges in the example are placeholders. Use the values of your cloud profile. The managed seeds that yake-ansible creates use the same fields, you can compare with your `gardener_operator_managed_seeds` configuration.

## 5. Use the cluster

Download the kubeconfig in the dashboard, or target the shoot with `gardenctl` if you enabled it with `gardenctl_install_enabled`:

```bash
./.local/yake-gardenctl target --garden garden shoot demo --project demo
./.local/yake-gardenctl
kubectl get nodes
```

The first command points `gardenctl` at the shoot. The second opens a shell in which `kubectl` works for the targeted cluster. This works with the default Docker method of `gardenctl_install_method`. With the `binary` method, there is no wrapper shell, use the downloaded kubeconfig instead:

```bash
export KUBECONFIG=~/Downloads/kubeconfig-demo.yaml
kubectl get nodes
```

## 6. Delete the cluster

Delete the cluster in the dashboard. With `kubectl` against the virtual garden, Gardener requires a confirmation first:

```bash
export KUBECONFIG=/var/lib/yake/gardener-operator/kubeconfig.vgarden
./.local/yake-kubectl -n garden-demo annotate shoot demo confirmation.gardener.cloud/deletion=true --overwrite
./.local/yake-kubectl -n garden-demo delete shoot demo
```

Gardener removes the nodes, load balancers and networks it created in OpenStack. Wait until the shoot is gone before you remove the credentials or the project.

## Next steps

- Add more capacity or other regions with [managed seeds](operations.md#adding-a-managed-seed).
- Add more machine types and images with [cloud profiles](operations.md#adding-a-cloud-profile).
- Look into [Operations](operations.md#upgrading) for upgrades and troubleshooting.
