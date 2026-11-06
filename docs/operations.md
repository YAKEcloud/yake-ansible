# Operations

This document covers day-to-day operations of the platform: upgrading components, accessing clusters, extending the platform, and cleaning up resources.

## CI Variables (`group_vars/ci.yml`)

The variables used by the `Yake-Ansible install` GitHub Actions workflow live in `group_vars/ci.yml`, encrypted with [Ansible Vault](https://docs.ansible.com/ansible/latest/vault_guide/index.html). Since this repository is public, the file is safe to commit: it's useless without the vault password.

The vault password itself is never committed. It lives in:

- **Locally**: `.vault-pass.txt` in the repo root (gitignored).
- **In CI**: the `ANSIBLE_VAULT_PASSWORD` GitHub Actions secret. The workflow writes it to a temporary `.vault-pass.txt` at the start of the run and passes `--vault-password-file` to `ansible-playbook`.

It is deliberately **not** wired up via `ansible.cfg`'s `vault_password_file` setting, since that would apply to every `ansible-playbook`/`ansible-lint` invocation in the repo, including unrelated syntax checks in CI systems (e.g. ansible-lint) that don't have the password file and don't need it, causing those to fail hard.

To view or edit the CI variables:

```bash
ansible-vault view --vault-password-file .vault-pass.txt group_vars/ci.yml
ansible-vault edit --vault-password-file .vault-pass.txt group_vars/ci.yml
```

Commit the resulting (still encrypted) diff normally. If you use `ansible-vault`/`ansible-playbook` against `group_vars/ci.yml` often, export `ANSIBLE_VAULT_PASSWORD_FILE=.vault-pass.txt` in your shell instead of passing the flag every time.

If the vault password ever needs to be rotated, generate a new one, run `ansible-vault rekey group_vars/ci.yml`, update `.vault-pass.txt` locally, and update the `ANSIBLE_VAULT_PASSWORD` secret in the repository settings.

## Releases

Releases follow Gardener: `v1.152.0-0` is the first release for Gardener `1.152.0`; `-1`, `-2`, ... are fixes to this repository. A new release is published automatically for every new Gardener version. The release notes list the Gardener changes first, then the changes in this repository.

Each release is tested with its Gardener version, and that means the Gardener installation only. Seeds, shoots and everything else you run on top are outside the test scope.

Pin a release with `git checkout <tag>`. To run another Gardener version, set `gardener_operator_version` in your `all.yml`. This works, but is not tested. Only the newest Gardener version is maintained.

## Upgrading

All playbooks are idempotent. Re-running a playbook with an updated version variable upgrades the corresponding component.

### Upgrading Gardener

Update `gardener_operator_version` in `group_vars/all.yml` and re-run:

```bash
ansible-playbook -i localhost, -c local site.yml --tags gardener
```

The minimum supported Gardener version is `1.142.0`. Older versions are not supported, because nginx-ingress is no longer deployed since then and all Gardener endpoints are served via the Istio ingress gateway.

The Gardener Operator performs a rolling upgrade of all Gardener components. After the playbook completes, verify that all pods are running:

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.garden
./.local/yake-kubectl get pods -n garden
```

### Upgrading Provider Extensions

Provider extension versions are separate variables (e.g., `gardener_operator_provider_openstack_version`). Update the relevant version and re-run the playbook with `--tags gardener`. Renovate automatically opens pull requests for version updates.

### Switching the Virtual Garden to High Availability

`gardener_operator_virtual_garden_high_availability` (default `true`) runs etcd main and events of the virtual garden with 3 members each (instead of 1) and the virtual kube-apiserver and the gardener-apiserver with 3 replicas (instead of 2). On an existing installation with a single member, the next playbook run switches it over:

1. etcd-druid restarts the existing member and adds two new members one after another.
2. While the membership changes, the virtual garden kube-apiserver restarts several times. The Gardener API and the dashboard are unavailable for a few minutes, and `gardener-apiserver`, `gardener-controller-manager`, `gardener-scheduler`, `gardenlet` and `virtual-garden-kube-controller-manager` go into `CrashLoopBackOff`.
3. Once all members are ready, the Garden returns to `Succeeded` (about 6 minutes in our tests). The crashing pods recover on their own, the `CrashLoopBackOff` can delay this by up to 5 more minutes. The `gardenlet` may log `panic: ... no matches for seedmanagement.gardener.cloud/v1alpha1` until the `gardener-apiserver` is back, this is expected.

Existing shoot clusters keep running, only changes through the Gardener API are delayed. Plan the switch in a maintenance window. It cannot be reverted. To stay on a single member, set `gardener_operator_virtual_garden_high_availability: false` before the run.

Watch the progress with:

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.garden
./.local/yake-kubectl -n garden get etcd
./.local/yake-kubectl -n garden get pods -l app.kubernetes.io/part-of=virtual-garden-etcd-main
./.local/yake-kubectl get garden
```

### Upgrading the Garden Cluster

Update `clusterapi_cluster_kubernetes_version` and re-run:

```bash
ansible-playbook -i localhost, -c local site.yml --tags garden-cluster
```

Cluster API performs a rolling upgrade of the control plane nodes followed by worker nodes.

The default of `clusterapi_cluster_kubernetes_version` (and `gardener_operator_kubernetes_version`) moves with this repository, currently to `1.37.2`. If you did not set the variable, the next run upgrades the garden cluster. Pin the variable in `group_vars/all.yml` to stay on your version. The unused variable `clusterapi_cluster_kubeconfig` has been removed.

### Upgrading Tool Versions

kubectl, Helm, clusterctl, and kind versions are set by `kubectl_install_version`, `helm_install_version`, `clusterctl_install_version`, and `management_cluster_kind_version` respectively. After updating these variables, re-run the playbook with the matching tags (`kubectl`, `helm`, `clusterctl`, `management-cluster`).

On the first run the `clusterapi` step initializes Cluster API with `clusterctl init`. On an existing management cluster it runs `clusterctl upgrade apply` instead with the same versions. The provider versions are pinned by `clusterapi_install_capi_version` (core, kubeadm bootstrap, kubeadm control plane) and `clusterapi_install_capo_version` (OpenStack). They have to match the vendored ORC manifest (`files/orc.yaml`). If one of them is empty, `clusterctl upgrade apply --contract <contract>` is used instead and the providers float to the latest versions for that contract, set by `clusterapi_install_contract` (default `v1beta2`). A clusterctl release that supports a newer contract makes the step fail until the variable is raised.

### Upgrading the kind Management Cluster

kind clusters cannot be upgraded in place and an existing cluster is never touched by a changed `management_cluster_kind_cluster_version` (also not when Renovate bumps it). To replace it, set `management_cluster_kind_upgrade: true` and run the playbook, or only the step with `--tags management-cluster-upgrade`. The step does nothing if the running Kubernetes version is not older than the configured one.

It runs after the `clusterapi` step so that the Cluster API providers are current, then:

1. Checks that all clusters in `management_cluster_kind_upgrade_namespace` are provisioned and not paused.
2. Writes the Cluster API objects with `clusterctl move --to-directory` to `/var/lib/yake/backup/<timestamp>`. The source is not modified. If this fails, the clusters are resumed and the kind cluster is left alone.
3. Deletes the kind cluster and creates it again with the same name, so kubeconfig paths stay valid. Cluster API and ORC are installed on it.
4. Restores the objects with `clusterctl move --from-directory` and waits until all clusters are provisioned and not paused.

The OpenStack resources keep running throughout, only reconciliation pauses for a few minutes. Back up and restore are limited to `management_cluster_kind_upgrade_namespace` (all objects of this repo live in `default`). The cloud secret is carried over because it has the `clusterctl.cluster.x-k8s.io/move` label.

The backup contains CA keys and credentials and is deleted after the clusters are restored. If the step fails after the old cluster was deleted, it is kept and the playbook does not restore on a re-run, because the new cluster already has the desired version. Restore manually once Cluster API is installed on the new cluster:

```bash
./.local/yake-clusterctl move --from-directory /var/lib/yake/backup/<timestamp> \
  --to-kubeconfig /var/lib/yake/kubeconfig.clusterapi
```

`clusterctl move` was designed for the bootstrap case and is not a verified backup and restore tool. Run the upgrade on a test setup first.

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

### gardenctl

If `gardenctl_install_enabled` is set, `.local/yake-gardenctl` passes its arguments to gardenctl. Without arguments it opens a shell in the container, where `kubectl` works for the targeted cluster (`KUBECONFIG` is set automatically via `gardenctl rc`):

```bash
./.local/yake-gardenctl target --garden garden shoot <shoot> --project <project>
./.local/yake-gardenctl
kubectl get nodes
```

The configuration and target sessions are kept in `/var/lib/yake/gardenctl/.garden`.

## Adding a Cloud Profile

Add a new entry to `gardener_operator_cloudprofiles` in `group_vars/all.yml` and re-run the playbook with `--tags gardener`. Cloud profiles are reconciled without downtime.

## Adding a Managed Seed

Add a new entry to `gardener_operator_managed_seeds` and re-run:

```bash
ansible-playbook -i localhost, -c local site.yml --tags gardener
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

**1. Delete each managed-seed shoot.** `managedseed`/`shoot` are Gardener API resources, so this
goes against the virtual garden:

```bash
export KUBECONFIG=/var/lib/yake/gardener-operator/kubeconfig.vgarden
./.local/yake-kubectl -n garden delete managedseed managed-seed-a
./.local/yake-kubectl -n garden annotate shoot managed-seed-a confirmation.gardener.cloud/deletion=true --overwrite
./.local/yake-kubectl -n garden delete shoot managed-seed-a
# wait until the shoot is fully gone before continuing
```

**2. Delete the `internal-seed` gardenlet.** Also a virtual garden resource. Unlike
`managed-seed-a`, whose seed registration goes away with the `ManagedSeed` in step 1,
`internal-seed`'s `Gardenlet` is applied independently and isn't a child of the `Garden`
resource. Deleting `Garden` alone won't remove it, so it needs this separate step. It also fails
as long as any shoot's `spec.seedName` still points at `internal-seed`, which is why it comes
after step 1 (this is standard Gardener seed-deletion behavior, not something enforced by this
repo):

```bash
export KUBECONFIG=/var/lib/yake/gardener-operator/kubeconfig.vgarden
./.local/yake-kubectl -n garden delete gardenlet internal-seed
# wait until the seed is fully gone before continuing
./.local/yake-kubectl get seed internal-seed
```

**3. Delete the Garden.** `Garden` is reconciled by gardener-operator running on the garden
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
docker rm -f kind helm kubectl clusterctl gardenctl
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

The `cleanup.yml` playbook removes OpenStack resources left behind after a teardown: servers,
volumes (including PVC volumes), floating IPs, load balancers (API server and Service LBs),
routers, ports, networks, subnets, security groups, server groups, SSH key pairs and the DNS
record sets of the garden URL zone (except SOA/NS). It only touches resources it can positively
identify as belonging to this run's `clusterapi_cluster_name` and `gardener_operator_managed_seeds`
(exact CAPO/Gardener names, ownership and attachment, inside the current project; see
`scripts/README.md` for the rules). The DNS zone is the exception: all its record sets are
removed, so it must be dedicated to this deployment.

The playbook requires two variables: `cleanup_openstack_cloud` (cloud name in the clouds file)
and `cleanup_clouds_file` (path to that clouds.yaml, e.g. `/var/lib/yake/clouds.garden.yaml`).

```bash
ansible-playbook -i localhost, -c local cleanup.yml -e "@group_vars/all.yml"
```

It's the practical fallback if the graceful teardown above was skipped, interrupted, or left
something behind (e.g. a stuck finalizer): rather than tracking down every orphaned resource by
hand, re-running `cleanup.yml` reclaims it.

The OpenStack part can also be run standalone, outside Ansible: `scripts/cleanup-openstack.py`
(pass `--dry-run` to preview first). It exits non-zero if any resource could not be deleted.

**Full local reset.** For a manual test run where you also want the local docker containers,
images, and `/var/lib/yake/` gone afterwards (not something CI needs, since its runner is
thrown away anyway):

```bash
ansible-playbook -i localhost, -c local cleanup.yml -e "@group_vars/all.yml" -e cleanup_full_local_reset=true --ask-become-pass
```

## Troubleshooting

### General Debugging

Add `-vvv` to any Ansible command for detailed output:

```bash
ansible-playbook -i localhost, -c local site.yml --tags gardener -vvv
```

Dry-run mode shows what would change without applying it:

```bash
ansible-playbook -i localhost, -c local site.yml --tags gardener --check
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

### Gardenlet in CrashLoopBackOff After Upgrading to 1.153

Since Gardener 1.153 the gardenlet no longer derives `spec.dns.defaults` of its Seed from the `default-domain` secret. It overwrites the Seed with the `seedConfig` it is given, and removing already set defaults is rejected. The gardenlet then exits at startup:

```
panic: could not register seed "internal-seed": Seed.core.gardener.cloud "internal-seed" is invalid: spec.dns.defaults: Forbidden: removing defaults DNS configuration is not allowed
```

The templates for the internal seed and for managed seeds now set `dns.defaults` explicitly. Running the playbook with a release that contains this change at the same time as the Gardener upgrade is enough.

If the gardenlet is already crash-looping, it cannot apply the new configuration itself, and the Gardener Operator does not redeploy a Gardenlet whose Seed already exists. Re-run the playbook with `--tags gardener` first, then force the redeploy:

```bash
export KUBECONFIG=/var/lib/yake/gardener-operator/kubeconfig.vgarden
./.local/yake-kubectl -n garden annotate gardenlets.seedmanagement.gardener.cloud internal-seed \
  gardener.cloud/operation=force-redeploy

export KUBECONFIG=/var/lib/yake/kubeconfig.garden
./.local/yake-kubectl -n garden rollout restart deploy/gardener-operator
```

The annotation is only evaluated when the operator starts, hence the restart. The operator removes it after the redeploy.

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
