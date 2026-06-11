# yake-ansible

yake-ansible automates the deployment of a Gardener-based Kubernetes platform on OpenStack. It provisions a local management cluster, initializes Cluster API with the OpenStack provider, creates a dedicated garden cluster, and installs the Gardener Operator with cloud profiles, managed seeds, and all required extensions.

The result is a fully operational Gardener installation that can manage Kubernetes shoot clusters across one or more OpenStack tenants.

## Architecture

```
  +-------------------------------------------+
  |  Control Host                             |
  |  +--------------------------------------+ |
  |  |  Management Cluster (kind/k3s)       | |
  |  |  Cluster API + CAPO                  | |
  |  +-------------------+------------------+ |
  +--------------------+----------------------+
                       |  provisions via OpenStack API
                       v
  +-------------------------------------------+
  |  Garden Cluster (OpenStack)               |
  |  Gardener Operator                        |
  |  +- Virtual Garden                        |
  |      +- gardener-apiserver, etcd          |
  |      +- dashboard, dex (OIDC)             |
  |      +- Internal Seed (this cluster)      |
  |      +- Managed Seeds (registered shoots) |
  +--------------------+----------------------+
       ^               |
       |  gardenlet connects back (TLS :443)
  +----+--------------------------------------+
  |  Managed Seed (OpenStack)                 |
  |  +- Gardenlet                             |
  |  +- Shoot control planes (per shoot)      |
  |      kube-apiserver exposed via own LB    |
  |      VPN tunnel to shoot workers          |
  |                                           |
  |  +- Shoot Clusters  (OpenStack)           |
  |      worker nodes, own Neutron network    |
  +-------------------------------------------+
```

See [docs/architecture.md](docs/architecture.md) for a detailed description of each layer and [docs/networking.md](docs/networking.md) for ports, IP ranges, and traffic flows.

## Requirements

- OpenStack tenant with sufficient quota (see [docs/getting-started.md](docs/getting-started.md#openstack-requirements))
- Python 3.10 or later on the control host
- Docker for the default install method

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
ansible-galaxy install -f -r requirements.yml
```

## Configuration

Copy `group_vars/all.yml.example` to `group_vars/all.yml` and fill in your values. At minimum, configure the OpenStack credentials, the garden URL, a cloud profile, and at least one managed seed.

See [docs/configuration.md](docs/configuration.md) for a complete variable reference.

## Usage

Run the full setup in one step:

```bash
ansible-playbook -i localhost, -c local site.yml
```

Or run individual steps using tags:

```bash
ansible-playbook -i localhost, -c local site.yml --tags kubectl
ansible-playbook -i localhost, -c local site.yml --tags helm
ansible-playbook -i localhost, -c local site.yml --tags clusterctl
ansible-playbook -i localhost, -c local site.yml --tags management-cluster
ansible-playbook -i localhost, -c local site.yml --tags clusterapi
ansible-playbook -i localhost, -c local site.yml --tags garden-cluster
ansible-playbook -i localhost, -c local site.yml --tags gardener
```

All plays are idempotent and can be re-run to apply configuration changes or upgrade components.

## Accessing Clusters

Kubeconfigs for all clusters are written to `/var/lib/yake/`. Tools installed by this project are available as wrapper scripts under `.local/`.

**Management cluster (CAPI host):**
```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi
./.local/yake-kubectl get nodes
```

**Garden cluster:**
```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.garden
./.local/yake-kubectl get nodes
```

**Virtual Garden (Gardener API):**
```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.garden
kubectl get secret gardener -n garden -o jsonpath='{.data.kubeconfig}' \
  | base64 -d > /var/lib/yake/gardener-operator/kubeconfig.vgarden
export KUBECONFIG=/var/lib/yake/gardener-operator/kubeconfig.vgarden
./.local/yake-kubectl get seeds
```

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | Layer model, component roles, and data flow |
| [Networking](docs/networking.md) | Network topology, ports, IP ranges, DNS, VPN |
| [Getting Started](docs/getting-started.md) | OpenStack requirements, installation, first run |
| [Configuration](docs/configuration.md) | Complete variable reference for all roles |
| [Operations](docs/operations.md) | Upgrades, cleanup, troubleshooting |

## Scripts

See [scripts/README.md](scripts/README.md) for auxiliary tools such as syncing CAPI and GardenLinux images to OpenStack Glance.
