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

Worker node deployments support multiple pools across failure domains:

```yaml
clusterapi_cluster_worker_machine_deployments:
  - name: md-0
    replicas: 3
    failure_domain: nova
    image_id: "{{ clusterapi_cluster_openstack_image_id }}"
```

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
