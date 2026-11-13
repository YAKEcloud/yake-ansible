# yake-ansible

yake-ansible automates the deployment of a Gardener-based Kubernetes platform on OpenStack. It provisions a local management cluster, initializes Cluster API with the OpenStack provider, creates a dedicated garden cluster, and installs the Gardener Operator with cloud profiles, managed seeds, and all required extensions.

The result is a fully operational Gardener installation that can manage Kubernetes shoot clusters across one or more OpenStack tenants.

| Page | Description |
|------|-------------|
| [Getting Started](getting-started.md) | OpenStack requirements, installation, first run |
| [Architecture](architecture.md) | Layer model, component roles, and data flow |
| [Networking](networking.md) | Network topology, ports, IP ranges, DNS, VPN |
| [Configuration](configuration.md) | Complete variable reference for all roles |
| [Operations](operations.md) | Upgrades, cleanup, troubleshooting |
