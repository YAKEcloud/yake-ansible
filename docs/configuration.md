# Configuration Reference

All configuration lives in `group_vars/all.yml`. Role defaults provide sensible starting points; see each role's `defaults/main.yml` for the full list of available variables.

Versions listed on this page are the role defaults. They are bumped by Renovate, so check the `defaults/main.yml` of the role for the version that is actually deployed.

## Global

| Variable | Default | Description |
|----------|---------|-------------|
| `yake_install_method` | `docker` | How tools are installed: `docker` runs them as containers, `binary` downloads static binaries to `.local/`. |
| `proxy_env` | `{}` | Proxy environment variables passed to all components. Set `http_proxy`, `https_proxy`, and `no_proxy` as needed. |

### Tool Versions

The `kubectl_install`, `helm_install`, and `clusterctl_install` roles provide the CLI tools. With `yake_install_method: docker` they run as the container images `ghcr.io/yakecloud/<tool>`; with `binary` the matching static binaries are downloaded to `.local/`.

| Variable | Default | Description |
|----------|---------|-------------|
| `kubectl_install_version` | `v1.37.1` | kubectl version. |
| `helm_install_version` | `v4.3.0` | Helm version. |
| `clusterctl_install_version` | `v1.14.2` | clusterctl version. |

Each role also exposes `<role>_container_registry` (default `ghcr.io`) and `<role>_container_image` (`yakecloud/kubectl`, `yakecloud/helm`, `yakecloud/clusterctl`) to pull the images from a different registry.

## Management Cluster

Configured via the `management_cluster` role.

| Variable | Default | Description |
|----------|---------|-------------|
| `management_cluster_engine` | `kind` | Cluster engine: `kind` or `k3s`. |
| `management_cluster_name` | `clusterapi` | Name of the management cluster and prefix for its kubeconfig. |
| `management_cluster_kind_version` | `v0.33.0` | Version of the kind tool (`ghcr.io/yakecloud/kind`). |
| `management_cluster_kind_cluster_version` | `v1.37.0` | Kubernetes version for the kind node image (`kindest/node`). |
| `management_cluster_kind_cluster_api_server_address` | `127.0.0.1` | Address the kind API server listens on. |
| `management_cluster_k3s_version` | `1.37.0` | k3s version when using the k3s engine. |
| `management_cluster_kubeconfig` | `/var/lib/yake/kubeconfig.<name>` | Path of the kubeconfig file. |

The kubeconfig is written to `management_cluster_kubeconfig`, by default `/var/lib/yake/kubeconfig.<management_cluster_name>`.

## Garden Cluster

The garden cluster is provisioned by the `clusterapi_cluster` role on OpenStack.

### OpenStack Credentials

| Variable | Default | Description |
|----------|---------|-------------|
| `clusterapi_cluster_openstack_auth_url` | `""` | Keystone authentication URL. |
| `clusterapi_cluster_openstack_application_credential_id` | `""` | Application credential ID. |
| `clusterapi_cluster_openstack_application_credential_secret` | `""` | Application credential secret. |
| `clusterapi_cluster_openstack_domain_name` | `""` | OpenStack domain name. |
| `clusterapi_cluster_openstack_region_name` | `""` | OpenStack region. |
| `clusterapi_cluster_openstack_cacert` | `""` | PEM-encoded CA certificate for TLS verification. |
| `clusterapi_cluster_openstack_external_network` | `public` | Name of the external (floating IP) network. |
| `clusterapi_cluster_openstack_ssh_key_name` | `<cluster name>` | Name of the OpenStack key pair for the nodes. |
| `clusterapi_cluster_openstack_loadbalancer_provider` | `ovn` | Octavia provider for load balancers created by the cloud controller manager. |

### Machines

| Variable | Default | Description |
|----------|---------|-------------|
| `clusterapi_cluster_name` | `garden` | Name of the garden cluster. |
| `clusterapi_cluster_kubernetes_version` | `v1.36.5` | Kubernetes version for the garden cluster. |
| `clusterapi_cluster_openstack_image_id` | `""` | Glance image UUID for cluster nodes. |
| `clusterapi_cluster_openstack_image_name` | `""` | Expected name of the image. Strongly recommended: it is used to verify that the image ID is correct. |
| `clusterapi_cluster_control_plane_machine_count` | `3` | Number of control plane nodes. |
| `clusterapi_cluster_control_plane_machine_flavor` | `SCS-2V-4` | OpenStack flavor for control plane nodes. |
| `clusterapi_cluster_worker_machine_flavor` | `SCS-4V-8` | OpenStack flavor for worker nodes. |
| `clusterapi_cluster_root_volume_enabled` | `true` | Create a Cinder root volume. Set to `false` for flavors with local storage (for example local NVMe); the flavor's ephemeral disk is used then. |
| `clusterapi_cluster_control_plane_root_volume_size` | `20` | Root volume size of control plane nodes in GiB. |
| `clusterapi_cluster_worker_root_volume_size` | `20` | Root volume size of worker nodes in GiB. |
| `clusterapi_cluster_root_volume_type` | `__DEFAULT__` | Cinder volume type. |
| `clusterapi_cluster_root_volume_availability_zone` | first availability zone | Availability zone of the root volumes. |
| `clusterapi_cluster_openstack_availability_zones` | `[nova]` | List of availability zones for control plane nodes. |
| `clusterapi_cluster_csi_snapshotter_enabled` | `false` | Deploy the CSI snapshotter. Requires VolumeSnapshot CRDs and a SnapshotClass to be installed separately. |

Control plane and worker nodes are placed in OpenStack server groups with a `soft-anti-affinity` policy. This is controlled by `clusterapi_cluster_control_plane_server_group_enabled`, `clusterapi_cluster_worker_server_group_enabled` and the matching `..._server_group_policy` variables.

Control plane machine health checks are enabled by default (`clusterapi_cluster_control_plane_machine_health_check_enabled`). Unhealthy nodes are remediated after `300s`, with up to `3` retries (`clusterapi_cluster_control_plane_remediation_max_retry`).

Worker machine deployments support multiple pools and failure domains:

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
`clusterapi_cluster_openstack_ignore_volume_az: true` (default: `false`), so that the cinder-csi
does not expose it on the PV, causing an AZ mismatch.

### Networking

By default, CAPO creates a new network and subnet for the garden cluster. The subnet CIDR is set via `clusterapi_cluster_openstack_managed_subnets` (default: `172.28.0.0/24` with DNS nameserver `1.1.1.1`):

```yaml
clusterapi_cluster_openstack_managed_subnets:
  - cidr: "192.168.0.0/24"
    dns_nameservers:
      - "1.1.1.1"
```

The pod network is set via `clusterapi_cluster_pod_cidr_blocks` (default: `[10.244.0.0/16]`).

To use an existing subnet instead (for example, one allocated from an OpenStack subnet pool), set `clusterapi_cluster_openstack_subnets`. This is mutually exclusive with `managed_subnets`. DNS nameservers are configured on the subnet in OpenStack directly, not here.

```yaml
clusterapi_cluster_openstack_subnets:
  - id: "existing-subnet-uuid"
```

### CNI

| Variable | Default | Description |
|----------|---------|-------------|
| `clusterapi_cluster_network` | `cilium` | CNI plugin: `cilium` or `calico`. |
| `clusterapi_cluster_cilium_version` | `1.20.2` | Cilium chart version. |
| `clusterapi_cluster_cilium_helm_values` | see `defaults/main.yml` | Helm values for Cilium. |
| `clusterapi_cluster_calico_version` | `v3.33.0` | Calico chart version (tigera-operator). |
| `clusterapi_cluster_calico_helm_values` | `{}` | Helm values for Calico. |
| `clusterapi_cluster_metrics_server_version` | `3.14.0` | metrics-server chart version. |
| `clusterapi_cluster_metrics_server_helm_values` | see `defaults/main.yml` | Helm values for metrics-server (2 replicas, `--kubelet-insecure-tls`). |

### Registry Caches and Host Entries

The nodes pull images through the registry caches at `https://registry.osism.tech/v2/<name>`. The URLs are set per upstream registry through `clusterapi_cluster_container_registry_cache_dockerhub`, `..._pkg`, `..._gcr`, `..._ghcr`, `..._quay` and `..._k8s`.

To make additional hostnames resolvable on the nodes (for example for a private registry or Keystone), use `clusterapi_cluster_hosts_entries`:

```yaml
clusterapi_cluster_hosts_entries:
  - ip: "12.34.56.54"
    hostname: "harbor.example.com"
```

## Gardener Operator

The `gardener_operator` role deploys the Gardener Operator and configures the entire Gardener control plane.

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `gardener_operator_version` | `1.152.0` | Gardener Operator Helm chart version. |
| `gardener_operator_kubernetes_version` | `1.36.5` | Kubernetes version for the internal seed shoot. |
| `gardener_operator_cluster_name` | `prod-garden` | Name of the garden cluster. |
| `gardener_operator_garden_url` | `example.com` | Base domain for the Gardener installation. |
| `gardener_operator_garden_cluster_admin_email` | `admin@example.com` | Email address for the Gardener dashboard admin. |
| `gardener_operator_networking_type` | `cilium` | Default CNI for shoots: `cilium` or `calico`. |
| `gardener_operator_image_registry` | `europe-docker.pkg.dev` | Registry the Gardener component images are pulled from. |
| `gardener_operator_gardenlet_image_vector_overwrite` | `""` | Image vector overwrite for all gardenlets, for example to pull images from a private registry. |
| `gardener_operator_gardenlet_feature_gates` | `{}` | Feature gates for all gardenlets (internal seed and managed seeds). |
| `gardener_operator_seed_block_cidrs` | `[169.254.169.254/32]` | CIDRs blocked in all shoot clusters via NetworkPolicy. |
| `gardener_operator_proxy_host` / `gardener_operator_proxy_port` | `""` / `3128` | HTTP proxy for the managed seeds; also allowed through a NetworkPolicy. |

### Dex, Kyverno and Reflector

Dex provides OIDC login for the dashboard. It is configured through `gardener_operator_dex`:

```yaml
gardener_operator_dex:
  dashboard_secret: "..."
  static_passwords:
    - email: "admin@example.com"
      username: "admin"
      hash: "$2a$10$..."   # bcrypt hash
  connectors: []           # see https://dexidp.io/docs/connectors/
```

| Variable | Default | Description |
|----------|---------|-------------|
| `gardener_operator_dex_version` | `0.25.2` | Dex Helm chart version. |
| `gardener_operator_kyverno_version` | `3.9.1` | Kyverno Helm chart version. |
| `gardener_operator_reflector_version` | `10.0.65` | Reflector Helm chart version. |
| `gardener_operator_helm_values` | `{}` | Additional Helm values for the Gardener Operator chart. |

### Projects

Additional Gardener projects are created from `gardener_operator_projects` (default: `[]`). The project `seeds` that hosts the managed seeds is configured with `gardener_operator_managed_seeds_project`; its members default to the admin email above.

### OpenStack Credentials

Used for the Gardener control plane, DNS, and backup integration.

| Variable | Default | Description |
|----------|---------|-------------|
| `gardener_operator_openstack_auth_url` | `https://keystone.example.com` | Keystone URL. |
| `gardener_operator_openstack_project_name` | `example` | OpenStack project. |
| `gardener_operator_openstack_domain_name` | `example` | OpenStack domain. |
| `gardener_operator_openstack_region_name` | `RegionOne` | OpenStack region. |
| `gardener_operator_openstack_application_credential_id` | `""` | Application credential ID. |
| `gardener_operator_openstack_application_credential_name` | `example-creds` | Application credential name. |
| `gardener_operator_openstack_application_credential_secret` | `""` | Application credential secret. |
| `gardener_operator_openstack_cacert` | `""` | PEM-encoded CA certificate. |
| `gardener_operator_openstack_zones` | `[zone1]` | Available availability zones. |

### DNS Provider

Gardener manages DNS records for shoots and internal domains. The provider is selected by `gardener_operator_dns_provider_type`.

| Type | Description |
|------|-------------|
| `openstack-designate` | OpenStack Designate. Set `gardener_operator_dns_credentials: {}` to reuse the OpenStack credentials above. |
| `aws-route53` | AWS Route53. Provide `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `region` in `gardener_operator_dns_credentials`. |
| `azure-dns` | Azure DNS. Provide `subscriptionID`, `tenantID`, `clientID`, and `clientSecret`. |
| `google-clouddns` | Google Cloud DNS. Provide the service account JSON as `serviceaccount.json`. |

### Provider Extensions

Extension versions are managed by Renovate and follow their respective upstream releases.

| Variable | Default | Description |
|----------|---------|-------------|
| `gardener_operator_provider_openstack_version` | `1.58.0` | OpenStack provider extension version. |
| `gardener_operator_provider_aws_version` | `1.75.0` | AWS provider extension version (deployed only when DNS type is `aws-route53`). |
| `gardener_operator_provider_azure_version` | `1.65.1` | Azure provider extension version (deployed only when DNS type is `azure-dns`). |
| `gardener_operator_provider_gcp_version` | `1.56.0` | GCP provider extension version (deployed only when DNS type is `google-clouddns`). |
| `gardener_operator_networking_cilium_version` | `1.48.4` | Cilium networking extension version. |
| `gardener_operator_networking_calico_version` | `1.59.1` | Calico networking extension version. |
| `gardener_operator_os_gardenlinux_version` | `0.50.0` | GardenLinux OS extension version. |
| `gardener_operator_os_ubuntu_version` | `1.42.0` | Ubuntu OS extension version. |
| `gardener_operator_shoot_cert_service_version` | `1.66.0` | Shoot certificate service version. |
| `gardener_operator_shoot_dns_service_version` | `1.93.0` | Shoot DNS service version. |
| `gardener_operator_extension_registry_cache_version` | `0.25.0` | Registry cache extension version (deployed only when registry caches or mirrors are configured). |
| `gardener_operator_shoot_oidc_service_version` | `0.40.0` | Shoot OIDC service extension version (deployed only when `gardener_operator_shoot_oidc_service_enabled` is `true`, default `false`). |
| `gardener_operator_backup_s3_version` | `0.8.7` | S3 backup extension version (deployed only when a backup provider is set to `S3`). |

The storage class that the OpenStack provider extension creates for shoot control planes is set with `gardener_operator_provider_openstack_storageclass_name` (default: `default`), `..._storageclass_type` and `..._storageclass_zone` (default: `nova`). Raw Helm values for the extension can be passed with `gardener_operator_provider_openstack_helm_values`.

OS types to deploy are controlled by `gardener_operator_os_types` (default: `[gardenlinux]`). Add `ubuntu` to also support Ubuntu-based worker nodes.

### Certificate Issuance

The shoot certificate service supports ACME (Let's Encrypt) and a custom CA.

```yaml
# ACME (default)
gardener_operator_shoot_cert_service_issuer_type: acme
gardener_operator_shoot_cert_service_acme_email: "certs@example.com"
gardener_operator_shoot_cert_service_acme_server: "https://acme-v02.api.letsencrypt.org/directory"
# Staging: https://acme-staging-v02.api.letsencrypt.org/directory

# Custom CA
gardener_operator_shoot_cert_service_issuer_type: ca
gardener_operator_shoot_cert_service_ca_certificate: |
  -----BEGIN CERTIFICATE-----
  ...
gardener_operator_shoot_cert_service_ca_key: |
  -----BEGIN RSA PRIVATE KEY-----
  ...
```

The nameservers used for the DNS precheck of the ACME challenge are set with `gardener_operator_shoot_cert_service_precheck_nameservers` (default: `1.1.1.1,1.0.0.1`).

### Monitoring

Shoot Prometheus metrics of all seeds can be forwarded to a central endpoint via remote write. It is enabled when `remote_write.url` is non-empty:

```yaml
gardener_operator_monitoring:
  remote_write:
    url: "https://prometheus.example.com/api/v1/write"
    keep: []          # metric names to forward; empty forwards all
  basic_auth:
    username: ""
    password: ""
```

### Cloud Profiles

Cloud profiles define the infrastructure options available to shoot clusters. Multiple profiles can be configured for different OpenStack environments.

```yaml
gardener_operator_cloudprofiles:
  - name: openstack-a
    storageclasses:
      - name: ssd
        default: "true"
        type: ssd
        availability: nova
    floating_pools:
      - name: public
    loadbalancer_providers:
      - name: amphora
    keystone_urls:
      - region: region-a
        url: "https://keystone.example.com:5000"
    machine_images:
      - name: gardenlinux
        versions:
          - version: 2150.11.0
            image: "Garden Linux 2150.11"
            regions:
              - name: region-a
                id: "6ed7d8aa-e770-4061-a8d7-461a83e41c31"
    kubernetes_versions:
      - version: 1.36.5
        classification: supported
    machinetypes:
      - name: SCS-4V-8
        cpu: "4"
        gpu: "0"
        memory: 8Gi
    regions:
      - name: region-a
        zones:
          - nova
```

### Managed Seeds

Each entry in `gardener_operator_managed_seeds` creates a shoot cluster and registers it as a Gardener seed.

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Shoot and seed name. |
| `cloudprofile_name` | Yes | Name of the cloud profile to use. |
| `networking_type` | Yes | CNI: `cilium` or `calico`. |
| `kubernetes_version` | Yes | Kubernetes version for the seed shoot. |
| `floating_pool_name` | Yes | OpenStack floating pool for the seed's load balancer. |
| `loadbalancer_provider` | No | Load balancer provider (default: `amphora`). Alternatives: `haproxy`, `ovn`. |
| `internal_domain` | No | Internal domain of the seed (default: `internal.<gardener_operator_garden_url>`). |
| `workers_cidr` | No | Worker subnet CIDR (default: `100.96.0.0/16`). Mutually exclusive with `subnet_pool`. |
| `subnet_pool` | No | Allocate the worker subnet from an OpenStack subnet pool instead of using an explicit CIDR. |
| `openstack` | Yes | OpenStack credentials for this seed (see below). |
| `workers` | Yes | List of worker pool configurations (see below). |
| `settings` | Yes | Seed settings (see below). |

**Subnet pool allocation:**

When a subnet pool is configured, the OpenStack provider allocates the CIDR automatically. This is mutually exclusive with `workers_cidr`.

```yaml
subnet_pool:
  id: "subnet-pool-uuid"
  prefix_length: 24  # optional, controls the allocated subnet size
```

**OpenStack credentials per seed:**

```yaml
openstack:
  auth_url: "https://keystone.example.com:5000"
  project_name: "seed-project"
  domain_name: "my-domain"
  region_name: "region-a"
  application_credential_id: "..."
  application_credential_name: "yake-seed-a"
  application_credential_secret: "..."
  # cacert: |  # optional, for custom CA
  #   -----BEGIN CERTIFICATE-----
```

**Worker pool configuration:**

```yaml
workers:
  - name: worker-4v16
    machinetype: SCS-4V-16
    image_name: gardenlinux
    image_version: 2150.11.0
    minimum: 3
    maximum: 15
    volume_type: ssd       # optional
    volume_size: 50Gi
    zones:
      - nova
```

**Seed settings:**

```yaml
settings:
  excess_capacity_reservation: true  # reserve capacity for shoot control planes
  backup:                             # optional, enables etcd backups for shoots on this seed
    provider: openstack
    region: region-a
    bucket_name: my-backup-bucket
    credentials:
      authURL: "..."
      tenantName: "..."
      domainName: "..."
      regionName: "..."
      applicationCredentialID: "..."
      applicationCredentialName: "..."
      applicationCredentialSecret: "..."
```

### Backups

**Garden etcd backup** (enabled when `gardener_operator_garden_backup_credentials` is non-empty):

```yaml
gardener_operator_garden_backup_provider: openstack
gardener_operator_garden_backup_region: "region-a"
gardener_operator_garden_backup_bucket_name: gardener-etcd
gardener_operator_garden_backup_credentials: |
  authURL: "..."
  tenantName: "..."
  ...
```

**Internal seed etcd backup** (enabled when `gardener_operator_internal_seed_backup_credentials` is non-empty):

```yaml
gardener_operator_internal_seed_backup_provider: openstack
gardener_operator_internal_seed_backup_region: "region-a"
gardener_operator_internal_seed_backup_bucket_name: gardener-internal-seed
gardener_operator_internal_seed_backup_credentials: |
  authURL: "..."
  ...
```

The internal seed's `excess_capacity_reservation` is controlled by `gardener_operator_internal_seed_excess_capacity_reservation` (default: `"false"`). Only enable it on hosts with more than 16Gi of RAM.

S3-compatible storage is also supported by setting the provider to `S3` and configuring the corresponding credentials.

### Registry Mirrors

Registry caches (`gardener_operator_managed_seeds_registry_caches`, default `[]`) run a pull-through cache inside the seed for each listed upstream, with an optional `volume_size`. To proxy container image pulls through a private registry instead, configure `gardener_operator_managed_seeds_registry_mirrors`. The registry cache extension is deployed automatically when this list is non-empty.

```yaml
gardener_operator_managed_seeds_registry_mirrors:
  - upstream: docker.io
    host: "https://harbor.example.com/docker.io"
  - upstream: registry.k8s.io
    host: "https://harbor.example.com/registry.k8s.io"
  - upstream: europe-docker.pkg.dev
    host: "https://harbor.example.com/europe-docker.pkg.dev"
    ca: true  # set to true if the mirror uses a custom CA certificate
```

When `ca: true` is set for any mirror, provide the CA bundle:

```yaml
gardener_operator_managed_seeds_registry_mirrors_ca: |
  -----BEGIN CERTIFICATE-----
  ...
  -----END CERTIFICATE-----
```
