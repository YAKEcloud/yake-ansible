# Glossary

The terms you meet in this documentation, in the order of the layers.

| Term | Meaning |
|------|---------|
| **Control host** | The machine on which you run the playbook. It also runs the management cluster. For production, we recommend a dedicated VM on OpenStack. |
| **Management cluster** | A small Kubernetes cluster (kind or k3s) on the control host. It runs Cluster API and creates the garden cluster. |
| **Cluster API (CAPI)** | A Kubernetes project to create and manage Kubernetes clusters declaratively. |
| **CAPO** | The Cluster API provider for OpenStack. It turns cluster definitions into OpenStack resources. |
| **Garden cluster** | The Kubernetes cluster on OpenStack that hosts the Gardener control plane. |
| **Gardener Operator** | The operator that installs and manages Gardener on the garden cluster. You describe Gardener in a `Garden` resource. |
| **Virtual garden** | The Gardener API with its own etcd, running inside the garden cluster. You talk to Gardener through it, not through the garden cluster API. |
| **Seed** | A Kubernetes cluster that hosts the control planes of shoot clusters. |
| **Internal seed** | The garden cluster itself, registered as a seed. It is protected and meant for the managed seeds. |
| **Managed seed** | A seed that is itself a shoot cluster and is registered as a seed automatically. It provides capacity for the control planes of your shoots. |
| **Gardenlet** | The Gardener agent on a seed. It connects to the virtual garden and runs the shoot control planes on its seed. |
| **Shoot cluster** | A workload Kubernetes cluster that Gardener creates and manages. Its control plane runs on a seed, its worker nodes are OpenStack VMs. |
| **Project** | A Gardener project groups shoot clusters and their members. It maps to a namespace `garden-<name>` in the virtual garden. |
| **Cloud profile** | Defines what shoots can use: regions, machine types, images, Kubernetes versions, floating pools. |
| **Extension** | A component that adds support for a cloud, an operating system or a feature to Gardener, for example the OpenStack provider extension. |
| **Dex** | The OIDC identity provider that signs you in to the Gardener dashboard. |
| **Istio ingress gateway** | The entry point for all Gardener endpoints, such as the dashboard and Dex. |
| **Shoot control plane** | The Kubernetes API server, etcd and controllers of a shoot cluster. They run as pods on the seed, not on the shoot's own nodes. |

For the layers and their relations, see [Architecture](architecture.md). For the Gardener concepts in depth, see the [Gardener documentation](https://gardener.cloud/docs/gardener/).
