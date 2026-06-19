# Getting Started

This guide walks through the prerequisites, installation, configuration, and first deployment of the yake-ansible platform.

## OpenStack Requirements

A productive Gardener installation with at least one managed seed and the ability to create shoot clusters requires the following minimum OpenStack quota:

| Resource | Minimum |
|----------|---------|
| Routers | 10 |
| Networks | 10 |
| Security groups | 15 |
| Floating IPs | 15 |
| Volumes | 40 |
| Volume storage | 1.5 TB |
| RAM | 150 GB |
| vCPUs | 50 |

At least two OpenStack projects are recommended:

- One project for the control plane
- One for the managed seed infrastructure.
- One or more projects for shoot cluster workloads.

The following OpenStack services must be available:

| Service | Purpose |
|---------|---------|
| Octavia (Load Balancer) | Required for Kubernetes API load balancers |
| Designate or another Service for DNS | Required for internal and external DNS records |
| Glance (Image) | Required for machine images (GardenLinux or Ubuntu) |
| Cinder (Block Storage) | Required for persistent volumes in clusters |
| Object Store (optional) | Required only if etcd or shoot backups are enabled |

### Cinder Volume Attachments

Each VM must support attaching a large number of Cinder volumes simultaneously. Gardener attaches multiple volumes per node — for root disks, etcd storage, and PersistentVolumes of shoot clusters running on the seed. Ensure your OpenStack environment does not impose a low limit on the number of volumes attachable per instance. If necessary, coordinate with your OpenStack administrator to raise the limit.

## Control Host Requirements

The control host is the machine from which you run the Ansible playbooks.

- Python 3.10 or later
- Docker (required for the default `docker` install method)
- Network access to the OpenStack APIs
- Network access to the internet (for pulling container images and Helm charts)

## Installation

Create a Python virtual environment and install the required dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
ansible-galaxy install -f -r requirements.yml
```

## Configuration

Copy the example configuration and open it for editing:

```bash
cp group_vars/all.yml.example group_vars/all.yml
$EDITOR group_vars/all.yml
```

The following sections are required for a minimal working deployment.

### OpenStack Credentials

These credentials are used for the garden cluster and the Gardener control plane. Application credentials are recommended over username and password.

```yaml
gardener_operator_openstack_auth_url: "https://keystone.example.com:5000"
gardener_operator_openstack_project_name: "my-project"
gardener_operator_openstack_domain_name: "my-domain"
gardener_operator_openstack_region_name: "RegionOne"
gardener_operator_openstack_application_credential_id: "..."
gardener_operator_openstack_application_credential_name: "yake"
gardener_operator_openstack_application_credential_secret: "..."
```

If your OpenStack uses a custom CA certificate, set it as a multiline string:

```yaml
gardener_operator_openstack_cacert: |
  -----BEGIN CERTIFICATE-----
  ...
  -----END CERTIFICATE-----
```

### Garden URL

The base domain for the Gardener installation. A wildcard DNS entry for this domain must point to the garden cluster's ingress load balancer IP.

```yaml
gardener_operator_garden_url: "gardener.example.com"
```

### DNS Provider

The DNS provider used by Gardener for shoot DNS records and internal domain management. OpenStack Designate is the default:

```yaml
gardener_operator_dns_provider_type: "openstack-designate"
gardener_operator_dns_credentials: {}  # reuses OpenStack credentials above
```

For other providers (AWS Route53, Azure DNS, Google Cloud DNS), set the type and provide the corresponding credentials. See [configuration.md](configuration.md#dns-provider) for examples.

### Cloud Profile

A cloud profile defines the available machine types, images, regions, and storage classes for a particular OpenStack environment. At least one cloud profile is required.

```yaml
gardener_operator_cloudprofiles:
  - name: openstack-a
    storageclasses:
      - name: ssd
        default: "true"
        type: ssd
        availability: nova
    floating_pools:
      - name: public
    loadbalancer_providers:
      - name: amphora
    keystone_urls:
      - region: region-a
        url: "https://keystone.example.com:5000"
    machine_images:
      - name: gardenlinux
        versions:
          - version: 2150.0.0
            image: "Garden Linux 2150.0"
            regions:
              - name: region-a
                id: "6ed7d8aa-e770-4061-a8d7-461a83e41c31"
    kubernetes_versions:
      - version: 1.35.3
        classification: supported
    machinetypes:
      - name: SCS-4V-8
        cpu: "4"
        gpu: "0"
        memory: 8Gi
    regions:
      - name: region-a
        zones:
          - nova
```

### Managed Seed

A managed seed is a Gardener shoot that is also registered as a Gardener seed. It provides capacity for hosting shoot cluster control planes.

```yaml
gardener_operator_managed_seeds:
  - name: seed-a
    cloudprofile_name: openstack-a
    networking_type: cilium
    kubernetes_version: 1.35.3
    floating_pool_name: "public"
    openstack:
      auth_url: "https://keystone.example.com:5000"
      project_name: "my-project"
      domain_name: "my-domain"
      region_name: "region-a"
      application_credential_id: "..."
      application_credential_name: "yake-seed"
      application_credential_secret: "..."
    workers:
      - name: worker-4v16
        machinetype: SCS-4V-16
        image_name: gardenlinux
        image_version: 2150.0.0
        minimum: 3
        maximum: 15
        volume_type: ssd
        volume_size: 50Gi
        zones:
          - nova
    settings:
      excess_capacity_reservation: true
```

### Garden Cluster

The garden cluster is created by Cluster API. Configure the OpenStack credentials and machine sizes for it:

```yaml
clusterapi_cluster_openstack_auth_url: "https://keystone.example.com:5000"
clusterapi_cluster_openstack_application_credential_id: "..."
clusterapi_cluster_openstack_application_credential_secret: "..."
clusterapi_cluster_openstack_domain_name: "my-domain"
clusterapi_cluster_openstack_region_name: "RegionOne"
clusterapi_cluster_openstack_image_id: "your-gardenlinux-image-uuid"
```

## Machine Images

Machine images must be uploaded to your OpenStack Glance before running the playbook. GardenLinux is the recommended OS. See [scripts/README.md](../scripts/README.md) for tools that automate this step.

## Running the Playbook

Once the configuration is complete, run the full setup:

```bash
ansible-playbook -i localhost, -c local site.yml
```

On hosts where `sudo` requires a password, add `--ask-become-pass`.

The playbook takes approximately 15 to 30 minutes to complete, depending on OpenStack provisioning speed.

## Validating the Deployment

After the playbook completes, verify each layer:

```bash
# Management cluster
export KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi
./.local/yake-kubectl get nodes

# Garden cluster
export KUBECONFIG=/var/lib/yake/kubeconfig.garden
./.local/yake-kubectl get nodes
./.local/yake-kubectl get pods -n garden

# Virtual Garden
export KUBECONFIG=/var/lib/yake/kubeconfig.garden
kubectl get secret gardener -n garden -o jsonpath='{.data.kubeconfig}' \
  | base64 -d > /var/lib/yake/gardener-operator/kubeconfig.vgarden
export KUBECONFIG=/var/lib/yake/gardener-operator/kubeconfig.vgarden
./.local/yake-kubectl get seeds
./.local/yake-kubectl get cloudprofiles
```

All seeds should show `Ready` status. Cloud profiles should list the machines, images, and regions you configured.
