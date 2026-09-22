# Operations

This document covers day-to-day operations of the platform: upgrading components, accessing clusters, extending the platform, and cleaning up resources.

## CI Variables (`group_vars/ci.yml`)

The variables used by the `Yake-Ansible install` GitHub Actions workflow live in `group_vars/ci.yml`, encrypted with [Ansible Vault](https://docs.ansible.com/ansible/latest/vault_guide/index.html). Since this repository is public, the file is safe to commit — it's useless without the vault password.

The vault password itself is never committed. It lives in:

- **Locally**: `.vault-pass.txt` in the repo root (gitignored).
- **In CI**: the `ANSIBLE_VAULT_PASSWORD` GitHub Actions secret. The workflow writes it to a temporary `.vault-pass.txt` at the start of the run and passes `--vault-password-file` to `ansible-playbook`.

It is deliberately **not** wired up via `ansible.cfg`'s `vault_password_file` setting, since that would apply to every `ansible-playbook`/`ansible-lint` invocation in the repo — including unrelated syntax checks in CI systems (e.g. Zuul/ansible-lint) that don't have the password file and don't need it, causing those to fail hard.

To view or edit the CI variables:

```bash
ansible-vault view --vault-password-file .vault-pass.txt group_vars/ci.yml
ansible-vault edit --vault-password-file .vault-pass.txt group_vars/ci.yml
```

Commit the resulting (still encrypted) diff normally. If you use `ansible-vault`/`ansible-playbook` against `group_vars/ci.yml` often, export `ANSIBLE_VAULT_PASSWORD_FILE=.vault-pass.txt` in your shell instead of passing the flag every time.

If the vault password ever needs to be rotated, generate a new one, run `ansible-vault rekey group_vars/ci.yml`, update `.vault-pass.txt` locally, and update the `ANSIBLE_VAULT_PASSWORD` secret in the repository settings.

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

### Garden and Managed Seed Teardown

Before tearing down the management cluster, the Garden and any ManagedSeed shoots must be deleted explicitly. Deleting the underlying cluster first leaves the Garden's cloud resources (DNS records, volumes, load balancers, backup buckets) orphaned in OpenStack, and the `Garden`/`Shoot` deletion webhooks require an explicit confirmation annotation anyway.

Order: managed-seed shoots first, then the `internal-seed` gardenlet, then the Garden, then the
underlying cluster. Each step targets a different API, so extract the virtual garden kubeconfig
first if you don't already have it (see [Accessing Clusters](#accessing-clusters)):

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.garden
kubectl get secret gardener -n garden -o jsonpath='{.data.kubeconfig}' \
  | base64 -d > /var/lib/yake/gardener-operator/kubeconfig.vgarden
```

**1. Delete each managed-seed shoot** — `managedseed`/`shoot` are Gardener API resources, so this
goes against the virtual garden:

```bash
export KUBECONFIG=/var/lib/yake/gardener-operator/kubeconfig.vgarden
./.local/yake-kubectl -n garden delete managedseed managed-seed-a
./.local/yake-kubectl -n garden annotate shoot managed-seed-a confirmation.gardener.cloud/deletion=true --overwrite
./.local/yake-kubectl -n garden delete shoot managed-seed-a
# wait until the shoot is fully gone before continuing
```

**2. Delete the `internal-seed` gardenlet** — also a virtual garden resource. Unlike
`managed-seed-a`, whose seed registration goes away with the `ManagedSeed` in step 1,
`internal-seed`'s `Gardenlet` is applied independently and isn't a child of the `Garden`
resource — deleting `Garden` alone won't remove it, so it needs this separate step. It also fails
as long as any shoot's `spec.seedName` still points at `internal-seed`, which is why it comes
after step 1 (this is standard Gardener seed-deletion behavior, not something enforced by this
repo):

```bash
export KUBECONFIG=/var/lib/yake/gardener-operator/kubeconfig.vgarden
./.local/yake-kubectl -n garden delete gardenlet internal-seed
# wait until the seed is fully gone before continuing
./.local/yake-kubectl get seed internal-seed
```

**3. Delete the Garden** — `Garden` is reconciled by gardener-operator running on the garden
cluster itself, so this uses that cluster's own kubeconfig, not the virtual garden:

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.garden
./.local/yake-kubectl annotate garden gardener confirmation.gardener.cloud/deletion=true --overwrite
./.local/yake-kubectl delete garden gardener
# wait until the Garden is fully gone before tearing down the cluster
```

Only once all three steps above have completed should the management cluster itself be torn down (see below).

### Full Teardown

**kind-based management cluster:**

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi
./.local/yake-kubectl delete cluster garden
./.local/yake-kubectl wait --for=delete cluster/garden --timeout=30m
./.local/yake-kind delete cluster --name clusterapi
docker rm -f $(docker ps -qa)
sudo rm -rf /var/lib/yake/
```

**k3s-based management cluster:**

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi
./.local/yake-kubectl delete cluster garden
./.local/yake-kubectl wait --for=delete cluster/garden --timeout=30m
sudo /usr/local/bin/k3s-uninstall.sh
sudo rm -rf /var/lib/yake/
```

The `wait` step matters: `capo-controller-manager`, which actually deprovisions the garden
cluster's OpenStack nodes and load balancer, runs *on the management cluster itself*. Tearing
down the management cluster (kind/k3s) before the `Cluster` object has finished deleting kills
the controller mid-reconciliation and leaves those OpenStack resources behind.

### OpenStack Resource Cleanup

The `cleanup.yml` playbook removes OpenStack resources that may remain after a teardown. It targets servers, volumes, floating IPs, load balancers, routers, networks, subnets, security groups, DNS record sets, and SSH key pairs.

Review the variables in the playbook before running it, as some resources may be shared with other projects:

```bash
ansible-playbook -i localhost, -c local cleanup.yml
```

This is a project-wide sweep, not scoped to a specific Shoot or Cluster — it removes matching
resources regardless of what created them (garden cluster, a managed seed's own worker nodes, or
anything else in the project). It's the practical fallback if the graceful teardown above was
skipped, interrupted, or left something behind (e.g. a stuck finalizer): rather than tracking down
every orphaned resource by hand, re-running `cleanup.yml` reclaims it. Only skip the graceful
`Garden`/`ManagedSeed` teardown steps entirely and rely on this instead when the OpenStack project
is dedicated to this environment (e.g. ephemeral CI runs) and nothing else in it needs to survive.

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
