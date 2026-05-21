# Operations

This document covers day-to-day operations of the platform: upgrading components, accessing clusters, extending the platform, and cleaning up resources.

## Upgrading

All playbooks are idempotent. Re-running a playbook with an updated version variable upgrades the corresponding component.

### Upgrading Gardener

Update `gardener_operator_version` in `group_vars/all.yml` and re-run:

```bash
ansible-playbook -i localhost, -c local gardener-operator.yml
```

The Gardener Operator performs a rolling upgrade of all Gardener components. After the playbook completes, verify that all pods are running:

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.garden
./.local/yake-kubectl get pods -n garden
```

### Upgrading Provider Extensions

Provider extension versions are separate variables (e.g., `gardener_operator_provider_openstack_version`). Update the relevant version and re-run the gardener-operator playbook. Renovate automatically opens pull requests for version updates.

Note that the OpenStack provider v1.55.0 dropped support for Kubernetes versions 1.31 and earlier. All clusters must be on Kubernetes 1.32 or later before upgrading to this version.

### Upgrading the Garden Cluster

Update `clusterapi_cluster_kubernetes_version` and re-run:

```bash
ansible-playbook -i localhost, -c local clusterapi-cluster.yml
```

Cluster API performs a rolling upgrade of the control plane nodes followed by worker nodes.

### Upgrading Tool Versions

kubectl, Helm, clusterctl, and kind versions are set by `kubectl_install_version`, `helm_install_version`, `clusterctl_install_version`, and `management_cluster_kind_version` respectively. After updating these variables, re-run the corresponding install playbooks.

## Accessing Clusters

Kubeconfigs for all clusters are written to `/var/lib/yake/`.

### Management Cluster

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi
./.local/yake-kubectl get nodes
```

### Garden Cluster

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.garden
./.local/yake-kubectl get nodes
```

### Virtual Garden (Gardener API)

The virtual garden kubeconfig is stored as a secret inside the garden cluster. Extract it before use, as the token it contains may rotate:

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.garden
kubectl get secret gardener -n garden -o jsonpath='{.data.kubeconfig}' \
  | base64 -d > /var/lib/yake/gardener-operator/kubeconfig.vgarden
export KUBECONFIG=/var/lib/yake/gardener-operator/kubeconfig.vgarden
./.local/yake-kubectl get seeds
./.local/yake-kubectl get cloudprofiles
./.local/yake-kubectl get shoots -A
```

## Adding a Cloud Profile

Add a new entry to `gardener_operator_cloudprofiles` in `group_vars/all.yml` and re-run the gardener-operator playbook. Cloud profiles are reconciled without downtime.

## Adding a Managed Seed

Add a new entry to `gardener_operator_managed_seeds` and re-run:

```bash
ansible-playbook -i localhost, -c local gardener-operator.yml
```

The new seed shoot is created on the internal seed and then registered as a Gardener seed. This process takes several minutes. Monitor progress:

```bash
export KUBECONFIG=/var/lib/yake/gardener-operator/kubeconfig.vgarden
./.local/yake-kubectl get shoots -n garden -w
./.local/yake-kubectl get managedseeds -n garden -w
```

## Cleanup

### Full Teardown

**kind-based management cluster:**

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi
./.local/yake-kubectl delete cluster garden
./.local/yake-kind delete cluster --name clusterapi
docker rm -f $(docker ps -qa)
sudo rm -rf /var/lib/yake/
```

**k3s-based management cluster:**

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi
./.local/yake-kubectl delete cluster garden
sudo /usr/local/bin/k3s-uninstall.sh
sudo rm -rf /var/lib/yake/
```

### OpenStack Resource Cleanup

The `cleanup.yml` playbook removes OpenStack resources that may remain after a teardown. It targets servers, volumes, floating IPs, load balancers, routers, networks, subnets, security groups, DNS record sets, and SSH key pairs.

Review the variables in the playbook before running it, as some resources may be shared with other projects:

```bash
ansible-playbook -i localhost, -c local cleanup.yml
```

## Troubleshooting

### General Debugging

Add `-vvv` to any Ansible command for detailed output:

```bash
ansible-playbook -i localhost, -c local gardener-operator.yml -vvv
```

Dry-run mode shows what would change without applying it:

```bash
ansible-playbook -i localhost, -c local gardener-operator.yml --check
```

### Garden Cluster Not Coming Up

Check the CAPI controller logs on the management cluster:

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi
./.local/yake-kubectl get openstackcluster garden -o yaml
./.local/yake-kubectl get machines -A
./.local/yake-kubectl logs -n capo-system deploy/capo-controller-manager
```

Verify that the OpenStack application credentials have sufficient permissions and that the external network name in `clusterapi_cluster_openstack_external_network` matches an existing network in your project.

### Gardener Operator Not Ready

Check the operator pod and its logs:

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.garden
./.local/yake-kubectl get pods -n garden
./.local/yake-kubectl logs -n garden deploy/gardener-operator
```

The Garden resource describes the overall reconciliation status:

```bash
./.local/yake-kubectl get garden -o yaml
```

### Managed Seed Shoot Stuck

Check the shoot status and Gardenlet logs:

```bash
export KUBECONFIG=/var/lib/yake/gardener-operator/kubeconfig.vgarden
./.local/yake-kubectl describe shoot <seed-name> -n garden
./.local/yake-kubectl get managedseed <seed-name> -n garden -o yaml
```

### DNS Records Not Created

Verify that the DNS provider credentials are correct and that the Designate zone exists. The shoot DNS service extension logs can be checked in the garden cluster:

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.garden
./.local/yake-kubectl logs -n extension-shoot-dns-service \
  deploy/gardener-extension-shoot-dns-service
```

### Variable Precedence

Ansible applies variables in this order (later takes precedence):

1. Role defaults (`roles/*/defaults/main.yml`)
2. `group_vars/all.yml`
3. Extra vars passed with `-e`

If a variable does not take effect, check that it is spelled correctly and set at the right level.
