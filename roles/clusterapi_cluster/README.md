# clusterapi_cluster

This role creates or deletes a Kubernetes cluster on OpenStack using Cluster API (CAPO). It is used to provision the garden cluster that hosts the Gardener Operator.

## What this role does

**On create (`clusterapi_cluster_state: present`):**

1. Generates OpenStack credentials (`clouds.yaml`) and creates the corresponding Kubernetes secret.
2. Looks up the external network ID from OpenStack.
3. Creates an OpenStack SSH key pair and saves the private key to `/var/lib/yake/`.
4. Generates the cluster manifest using `clusterctl generate cluster` and applies it to the management cluster.
5. Waits for the Kubernetes API to become available and saves the kubeconfig.
6. Installs the selected CNI (Cilium or Calico).
7. Deploys the OpenStack Cloud Controller Manager (CCM) and Cinder CSI driver.

**On delete (`clusterapi_cluster_state: absent`):**

Deletes the Cluster API `Cluster` resource, which triggers CAPO to remove all associated OpenStack resources.

## Requirements

- A management cluster with Cluster API and the CAPO provider initialized.
- The kubeconfig for the management cluster at `/var/lib/yake/kubeconfig.clusterapi`.
- A GardenLinux or Ubuntu Glance image uploaded to OpenStack.

## Variables

### OpenStack Credentials

| Variable | Default | Description |
|----------|---------|-------------|
| `clusterapi_cluster_openstack_auth_url` | `""` | Keystone URL. |
| `clusterapi_cluster_openstack_application_credential_id` | `""` | Application credential ID. |
| `clusterapi_cluster_openstack_application_credential_secret` | `""` | Application credential secret. |
| `clusterapi_cluster_openstack_domain_name` | `""` | OpenStack domain name. |
| `clusterapi_cluster_openstack_region_name` | `""` | OpenStack region. |
| `clusterapi_cluster_openstack_cacert` | `""` | PEM-encoded CA certificate (optional). |
| `clusterapi_cluster_openstack_external_network` | `public` | Name of the external network for floating IPs. |
| `clusterapi_cluster_openstack_loadbalancer_provider` | `ovn` | Load balancer provider for the API server load balancer. |
| `clusterapi_cluster_openstack_loadbalancer_monitor_delay` | `5` | Seconds between health probes against each API server LB member. |
| `clusterapi_cluster_openstack_loadbalancer_monitor_timeout` | `5` | Seconds a health probe waits before timing out. |
| `clusterapi_cluster_openstack_loadbalancer_monitor_max_retries` | `1` | Successful probes required before a member flips to `ONLINE`. Kept low to shrink the race window where a joining control-plane node hits an LB with zero healthy members ("connection refused" during `kubeadm join --control-plane`). |

### Cluster

| Variable | Default | Description |
|----------|---------|-------------|
| `clusterapi_cluster_name` | `garden` | Cluster name and prefix for all created resources. |
| `clusterapi_cluster_kubernetes_version` | `v1.36.1` | Kubernetes version. |
| `clusterapi_cluster_state` | `present` | `present` creates the cluster, `absent` deletes it. |

### Machines

| Variable | Default | Description |
|----------|---------|-------------|
| `clusterapi_cluster_openstack_image_id` | `""` | Glance image UUID for all nodes. |
| `clusterapi_cluster_openstack_ssh_key_name` | `{{ clusterapi_cluster_name }}` | OpenStack SSH key pair name. |
| `clusterapi_cluster_control_plane_machine_count` | `3` | Number of control plane nodes. |
| `clusterapi_cluster_control_plane_machine_flavor` | `SCS-2V-4` | OpenStack flavor for control plane nodes. |
| `clusterapi_cluster_worker_machine_flavor` | `SCS-4V-8` | OpenStack flavor for worker nodes. |
| `clusterapi_cluster_root_volume_size` | `20` | Root volume size in GiB. |
| `clusterapi_cluster_root_volume_type` | `__DEFAULT__` | Cinder volume type. |
| `clusterapi_cluster_openstack_availability_zones` | `[nova]` | Availability zones for control plane nodes. |
| `clusterapi_cluster_control_plane_machine_health_check_enabled` | `true` | Deploy a MachineHealthCheck for control-plane nodes so a Machine that never registers a Node (e.g. a permanently failed `kubeadm join`) is automatically replaced instead of hanging forever. |
| `clusterapi_cluster_control_plane_machine_health_check_unhealthy_timeout` | `300s` | How long a control-plane Machine may report `Ready=Unknown/False` before the MachineHealthCheck marks it unhealthy. |
| `clusterapi_cluster_control_plane_remediation_max_retry` | `3` | Max number of remediation retries KubeadmControlPlane performs for a control-plane Machine before giving up. |
| `clusterapi_cluster_control_plane_remediation_retry_period_seconds` | `120` | Minimum time between two remediation retries. |
| `clusterapi_cluster_control_plane_remediation_min_healthy_period_seconds` | `3600` | Time after which a new failure is treated as unrelated to a previous remediation (retry counter resets). |
| `clusterapi_cluster_control_plane_server_group_enabled` | `true` | Place control-plane machines in an OpenStack server group so they're spread across hypervisors. |
| `clusterapi_cluster_control_plane_server_group_policy` | `soft-anti-affinity` | Server group policy for control-plane machines. `soft-anti-affinity` prefers separate hosts without hard-failing scheduling on clouds with few hypervisors (unlike `anti-affinity`). |
| `clusterapi_cluster_worker_server_group_enabled` | `true` | Place worker machines in an OpenStack server group so they're spread across hypervisors. |
| `clusterapi_cluster_worker_server_group_policy` | `soft-anti-affinity` | Server group policy for worker machines. |

Worker node deployments support multiple pools across failure domains:

```yaml
clusterapi_cluster_worker_machine_deployments:
  - name: md-0
    replicas: 3
    failure_domain: nova
    image_id: "{{ clusterapi_cluster_openstack_image_id }}"
```

To specify different failure domains for machines and their volumes use:

```yaml
clusterapi_cluster_worker_machine_deployments:
  - name: md-0
    replicas: 3
    failure_domain: nova
    root_volume_failure_domain: cinder
    image_id: "{{ clusterapi_cluster_openstack_image_id }}"
```

Make sure to also specify
`clusterapi_cluster_openstack_ignore_volume_az: "true"`, so that the cinder-csi
does not expose it on the PV, causing an AZ mismatch.

### Networking

Two networking approaches are available and are mutually exclusive.

**Managed subnets** — CAPO creates a new network and subnet:

```yaml
clusterapi_cluster_openstack_managed_subnets:
  - cidr: "192.168.0.0/24"
    dns_nameservers:
      - "1.1.1.1"
```

**Existing subnets** — reference a pre-existing subnet by its OpenStack UUID. This is the preferred approach when subnets are allocated from an OpenStack subnet pool, since the pool allocation must happen before cluster creation. DNS nameservers are configured on the subnet in OpenStack and do not need to be set here.

```yaml
clusterapi_cluster_openstack_subnets:
  - id: "existing-subnet-uuid"
```

Up to two subnets can be listed (one IPv4 and one IPv6 for dual-stack clusters).

### CNI

| Variable | Default | Description |
|----------|---------|-------------|
| `clusterapi_cluster_network` | `cilium` | CNI plugin: `cilium` or `calico`. |
| `clusterapi_cluster_cilium_version` | `1.19.3` | Cilium Helm chart version. |
| `clusterapi_cluster_calico_version` | `v3.32.0` | Calico (tigera-operator) Helm chart version. |

### Container Registry Mirrors

All nodes are configured to pull images through the OSISM registry cache by default. Override these variables to point to your own mirrors:

| Variable | Default |
|----------|---------|
| `clusterapi_cluster_container_registry_cache_dockerhub` | `https://registry.osism.tech/v2/dockerhub` |
| `clusterapi_cluster_container_registry_cache_k8s` | `https://registry.osism.tech/v2/k8s` |
| `clusterapi_cluster_container_registry_cache_ghcr` | `https://registry.osism.tech/v2/ghcr` |
| `clusterapi_cluster_container_registry_cache_gcr` | `https://registry.osism.tech/v2/gcr` |
| `clusterapi_cluster_container_registry_cache_quay` | `https://registry.osism.tech/v2/quay` |
| `clusterapi_cluster_container_registry_cache_pkg` | `https://registry.osism.tech/v2/pkg` |

## Files written

| Path | Description |
|------|-------------|
| `/var/lib/yake/kubeconfig.garden` | Kubeconfig for the created cluster. |
| `/var/lib/yake/<cluster-name>` | Private SSH key for node access. |
| `/var/lib/yake/<cluster-name>.pub` | Public SSH key. |
