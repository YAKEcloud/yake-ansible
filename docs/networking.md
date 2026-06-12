# Networking

This document describes the network topology, required ports, and DNS configuration of a yake-ansible deployment on OpenStack.

## Network Topology

```
  Internet / Corporate Network
          |  HTTPS :443
          v
  +----------------------------------------------------------------+
  |  OpenStack External Network ("public")                         |
  |                                                                |
  |  +---------------------------+  +---------------------------+  |
  |  |  Floating IP              |  |  Floating IP              |  |
  |  |  API Server LB  :443      |  |  Ingress LB  :443 / :80   |  |
  |  +-------------+-------------+  +-------------+-------------+  |
  +---------------|-------------------------------|----------------+
                  |                               |
  +---------------|-------------------------------|----------------+
  |  Neutron Network -- Garden Cluster            |                |
  |  Nodes: 192.168.0.0/24  (default)             |                |
  |                                               |                |
  |  +------------------------+  +----------------v-------------+  |
  |  |  Control Plane  x3     |  |  Nginx Ingress               |  |
  |  |  kube-apiserver  :6443 |  |  dashboard.<domain>  :443    |  |
  |  |  etcd            :2379 |  |  identity.<domain>   :443    |  |
  |  +------------------------+  |  garden.<domain>     :443    |  |
  |                              +------------------------------+  |
  |  Pod CIDR:     10.244.0.0/16                                   |
  |  Service CIDR: extracted from kube-apiserver at deploy time    |
  |                                                                |
  |  +-----------------------------------------------------------+ |
  |  |  Virtual Garden  (in-cluster, no separate OS network)     | |
  |  |  Services: 100.64.0.0/13                                  | |
  |  |  gardener-apiserver  etcd  dex (:5556)  dashboard         | |
  |  +-----------------------------------------------------------+ |
  +----------------------------------------------------------------+
       ^  gardenlet TLS outbound :443 --> virtual garden API
       |
  +----+-----------------------------------------------------------+
  |  Neutron Network -- Managed Seed  (one network per seed)       |
  |  Nodes:    10.120.0.0/16  (default)                            |
  |  Pods:     100.72.0.0/16                                       |
  |  Services: 100.80.0.0/13                                       |
  |                                                                |
  |  +-----------------------------------------------------------+ |
  |  |  Shoot-A control plane  (pods in namespace on the seed)   | |
  |  |  kube-apiserver  :443   <-- own Floating IP + LB          | |
  |  |  etcd, kcm, scheduler   in-cluster only                   | |
  |  |  vpn-seed-server  :8132 <-- reachable from shoot workers  | |
  |  +------------------------------+----------------------------+ |
  +---------------------------------+------------------------------+
                                    |  encrypted VPN tunnel (:8132)
  +---------------------------------|------------------------------+
  |  Neutron Network -- Shoot-A     v                              |
  |  Nodes:    10.121.0.0/16                                       |
  |  Pods:     100.73.0.0/16                                       |
  |  Services: 100.88.0.0/13                                       |
  |                                                                |
  |  Worker Nodes                                                  |
  |  +- vpn-shoot-client    outbound to vpn-seed-server :8132      |
  |  +- konnectivity-agent  API server <-> kubelet traffic         |
  +----------------------------------------------------------------+
```

## Layer Overview

All address ranges are configurable defaults. They must be non-overlapping across all layers. See [configuration.md](configuration.md) for the relevant variables.

| Layer | OpenStack Subnet | Pod CIDR | Service CIDR |
|-------|-----------------|----------|-------------|
| Garden cluster | `192.168.0.0/24` | `10.244.0.0/16` | from kube-apiserver |
| Virtual garden | - (in-cluster only) | - | `100.64.0.0/13` |
| Managed seed | `10.120.0.0/16` | `100.72.0.0/16` | `100.80.0.0/13` |
| Shoot (default) | `10.121.0.0/16` | `100.73.0.0/16` | `100.88.0.0/13` |

Each layer gets its own Neutron network and is isolated from the others by separate security groups. CAPO sets `allowAllInClusterTraffic: true`; node-to-node traffic within a cluster is unrestricted at the OpenStack level; isolation is handled by Kubernetes NetworkPolicies.

## Shoot Control Plane and Worker Connectivity

This is the central networking concept in Gardener.

**Shoot control planes run on the seed, not on the shoot workers.** When a shoot is created, Gardener deploys its entire control plane (kube-apiserver, etcd, controller-manager, scheduler) as pods in a dedicated namespace on the seed cluster. Shoot worker nodes are plain VMs with only kubelet.

**How worker nodes reach their control plane:**

Shoot workers live in their own Neutron network and cannot directly route to the seed's pod network. Gardener bridges this with two components on every worker node:

- `vpn-shoot-client` establishes an encrypted tunnel to `vpn-seed-server` in the shoot's namespace on the seed. All traffic between workers and the control plane flows through this tunnel.
- `konnectivity-agent` handles the reverse channel from the API server to kubelet, used for `kubectl exec`, `kubectl logs`, and metrics scraping.

**How users reach the shoot API:**

The shoot's kube-apiserver is exposed via a dedicated LoadBalancer service on the seed, creating an Octavia LB with its own floating IP. This is the endpoint users receive in their kubeconfig.

**Quota implication:** every shoot adds at least one floating IP and one load balancer to the seed's OpenStack project.

## Ports

### External (reachable from outside OpenStack)

| Port | Protocol | Endpoint | Purpose |
|------|----------|---------|---------|
| 443 | TCP | Garden cluster API LB | Kubernetes API (used by CAPO and Gardener Operator) |
| 443 | TCP | Garden cluster Ingress LB | Gardener services via Nginx ingress |
| 80 | TCP | Garden cluster Ingress LB | HTTP redirect to HTTPS |
| 443 | TCP | Managed seed API LB | Seed Kubernetes API server |
| 443 | TCP | Per shoot own LB on seed | Shoot kube-apiserver (user kubeconfig endpoint) |
| 8132 | TCP | Per shoot own LB on seed | vpn-seed-server (shoot workers connect here) |

### Gardener Component Ports (in-cluster only)

| Port | Component | Cluster | Notes |
|------|-----------|---------|-------|
| 2722 | Gardener admission controller | Garden | Called by virtual garden kube-apiserver |
| 2750 | Gardenlet webhook server | Seed | Called by seed kube-apiserver |
| 2718 | Gardener controller manager | Garden | Metrics (Prometheus scrape) |
| 2718 | Gardener scheduler | Garden | Metrics (Prometheus scrape) |
| 5556 | Dex identity provider | Garden | Reachable only via Nginx ingress |

### Kubernetes Control Plane (in-cluster only)

| Port | Component |
|------|-----------|
| 6443 | kube-apiserver |
| 2379–2380 | etcd |
| 10250 | kubelet |
| 10257 | kube-controller-manager |
| 10259 | kube-scheduler |

## DNS

Default backend: OpenStack Designate (`openstack-designate`). Alternatives: `aws-route53`, `azure-dns`, `google-clouddns`; set via `gardener_operator_dns_provider_type`.

| Zone | Purpose |
|------|---------|
| `<garden-url>` | Root zone |
| `dashboard.<garden-url>` | Gardener Dashboard |
| `identity.<garden-url>` | Dex OIDC provider |
| `garden.<garden-url>` | Virtual garden API server |
| `internal.<garden-url>` | Internal seed ingress and terminals |
| `ingress.<seed>.<project>.<garden-url>` | Per-managed-seed ingress |

---

## OpenStack API Access

The control host and all cluster nodes require outbound access to the OpenStack API. Most deployments proxy all services behind a single HTTPS endpoint; the standard ports are listed for reference.

| Service | Standard port | Purpose |
|---------|--------------|---------|
| Keystone | 5000 / 443 | Authentication |
| Neutron | 9696 / 443 | Network provisioning |
| Nova | 8774 / 443 | VM lifecycle |
| Octavia | 9876 / 443 | Load balancers |
| Cinder | 8776 / 443 | Persistent volumes |
| Glance | 9292 / 443 | Machine images |
| Designate | 9001 / 443 | DNS records |

A custom CA certificate can be injected via `clusterapi_cluster_openstack_cacert`.

## CNI

Configurable per cluster: `cilium` (default) or `calico`. Set via `clusterapi_cluster_network` for the garden cluster and `gardener_operator_networking_type` for seeds and shoots.

## Container Registry

Nodes pull images through configurable mirrors. Defaults point to `registry.osism.tech`. Override via `clusterapi_cluster_container_registry_cache_*` variables.

## OpenStack Quota

| Resource | Garden cluster | Per managed seed | Per shoot |
|----------|---------------|-----------------|----------|
| Networks | 1 | 1 | 1 |
| Routers | 1 | 1 | 1 |
| Floating IPs | 2 | 2 | 1 |
| Load balancers | 2 | 2 | 1 |
| Security groups | 3–5 | 3–5 | 3–5 |

See [getting-started.md](getting-started.md#openstack-requirements) for full quota requirements.
