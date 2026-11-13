# How it works

yake-ansible is a single playbook, `site.yml`, that you run on the [control host](architecture.md#control-host). Every play builds one layer of the platform, and each layer creates the next. The table lists the plays in the order in which they run. You can run all plays in one go or pick single steps with tags.

## The playbook

<div class="yake-nowrap" markdown>

| Tag | Role | What it does |
|-----|------|--------------|
| `kubectl` | `kubectl_install` | Installs `kubectl` and a wrapper script `.local/yake-kubectl`. |
| `helm` | `helm_install` | Installs Helm and a wrapper script `.local/yake-helm`. |
| `clusterctl` | `clusterctl_install` | Installs `clusterctl` and a wrapper script `.local/yake-clusterctl`. |
| `management-cluster` | `management_cluster` | Creates the management cluster with kind (default) or k3s. |
| `clusterapi` | `clusterapi_install` | Initializes Cluster API with the OpenStack provider on the management cluster. |
| `management-cluster-upgrade` | `management_cluster` | Upgrades a kind management cluster. Runs only with the kind engine and `management_cluster_kind_upgrade: true`. |
| `garden-cluster` | `clusterapi_cluster` | Creates the garden cluster on OpenStack through Cluster API. |
| `gardener` | `gardener_operator` | Installs the Gardener Operator and creates the Garden with cloud profiles, managed seeds and extensions. |
| `gardenctl` | `gardenctl_install` | Installs `gardenctl` and a wrapper script `.local/yake-gardenctl`. |

</div>

The roles are documented in the [configuration reference](configuration.md), one section per role.

## Run everything or single steps

```bash
# Everything
ansible-playbook -i localhost, -c local site.yml

# One layer
ansible-playbook -i localhost, -c local site.yml --tags garden-cluster

# Several layers
ansible-playbook -i localhost, -c local site.yml --tags garden-cluster,gardener
```

All plays are idempotent. Run the playbook again after you changed a variable or want to upgrade a component, and only what differs is changed. How to upgrade is described in [Operations](operations.md#upgrading).

!!! note "Run the layers in order"
    A layer needs the layers before it. Running `--tags gardener` on a fresh machine fails, because the garden cluster does not exist yet. For a first installation, run the full playbook.

## Where the state lives

The control host keeps everything the playbook generates in `/var/lib/yake/`:

| Path | Content |
|------|---------|
| `kubeconfig.clusterapi` | Kubeconfig of the management cluster. |
| `kubeconfig.garden` | Kubeconfig of the garden cluster. |
| `gardener-operator/kubeconfig.vgarden` | Kubeconfig of the virtual garden (the Gardener API), once you extracted it. See [Accessing Clusters](operations.md#accessing-clusters). |
| `clouds.<name>.yaml`, `cloud-secret.yaml` | OpenStack credentials for Cluster API, written with mode `0600`. |
| `ca/` | The generated root CA, if you use the generated CA for certificates. |

Back up `/var/lib/yake/` together with your `group_vars/all.yml`. Both contain credentials and keys, for example the encryption key of the garden cluster. See also [Security](security.md).

## What you configure

You configure the platform in `group_vars/all.yml`, which you copy from `group_vars/all.yml.example`. Every role has defaults, so the file only needs the values that differ in your environment. The minimal set is described in the [installation guide](getting-started.md#configuration). Everything else is in the [configuration reference](configuration.md).
