# Requirements

Check these requirements before you start the [installation](getting-started.md).

## OpenStack Requirements

A productive Gardener installation with at least one managed seed and the ability to create shoot clusters requires the following minimum OpenStack quota:

| Resource | Minimum |
|----------|---------|
| Routers | 10 |
| Networks | 10 |
| Security groups | 15 |
| Floating IPs | 15 |
| Volumes | 50 |
| Volume storage | 2 TB |
| RAM | 150 GB |
| vCPUs | 50 |

Separate OpenStack projects are recommended:

- One project for the control plane (garden cluster).
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

Each VM must support attaching a large number of Cinder volumes simultaneously. Gardener attaches multiple volumes per node: for root disks, etcd storage, and PersistentVolumes of shoot clusters running on the seed. Ensure your OpenStack environment does not impose a low limit on the number of volumes attachable per instance. If necessary, coordinate with your OpenStack administrator to raise the limit.

## Control Host Requirements

The control host is the machine from which you run the Ansible playbooks.

For production, we recommend a dedicated VM on OpenStack as control host, which is also where the management cluster runs. This is how YAKE is operated. It is not a requirement: any other machine works as well, for example a workstation for tests.

- Python 3.13 or later (required by the pinned `ansible-core`)
- Docker (required for the default `docker` install method)
- Network access to the OpenStack APIs
- Network access to the internet (for pulling container images and Helm charts)
