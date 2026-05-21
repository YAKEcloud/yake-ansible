# Configuration Reference

All configuration lives in `group_vars/all.yml`. Role defaults provide sensible starting points; see each role's `defaults/main.yml` for the full list of available variables.

## Global

| Variable | Default | Description |
|----------|---------|-------------|
| `yake_install_method` | `docker` | How tools are installed: `docker` runs them as containers, `binary` downloads static binaries to `.local/`. |
| `proxy_env` | `{}` | Proxy environment variables passed to all components. Set `http_proxy`, `https_proxy`, and `no_proxy` as needed. |

## Management Cluster

Configured via the `management_cluster` role.

| Variable | Default | Description |
|----------|---------|-------------|
| `management_cluster_engine` | `kind` | Cluster engine: `kind` or `k3s`. |
| `management_cluster_name` | `clusterapi` | Name of the management cluster and prefix for its kubeconfig. |
| `management_cluster_kind_cluster_version` | `v1.35.1` | Kubernetes version for the kind node image. |
| `management_cluster_k3s_version` | `1.35.1` | k3s version when using the k3s engine. |

The kubeconfig is written to `/var/lib/yake/kubeconfig.<management_cluster_name>`.

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

### Machines

| Variable | Default | Description |
|----------|---------|-------------|
| `clusterapi_cluster_kubernetes_version` | `v1.36.1` | Kubernetes version for the garden cluster. |
| `clusterapi_cluster_openstack_image_id` | `""` | Glance image UUID for cluster nodes. |
| `clusterapi_cluster_control_plane_machine_count` | `3` | Number of control plane nodes. |
| `clusterapi_cluster_control_plane_machine_flavor` | `SCS-2V-4` | OpenStack flavor for control plane nodes. |
| `clusterapi_cluster_worker_machine_flavor` | `SCS-4V-8` | OpenStack flavor for worker nodes. |
| `clusterapi_cluster_root_volume_size` | `20` | Root volume size in GiB. |
| `clusterapi_cluster_root_volume_type` | `__DEFAULT__` | Cinder volume type. |
| `clusterapi_cluster_openstack_availability_zones` | `[nova]` | List of availability zones for control plane nodes. |

Worker machine deployments support multiple pools and failure domains:

```yaml
clusterapi_cluster_worker_machine_deployments:
  - name: md-0
    replicas: 3
    failure_domain: nova
    image_id: "{{ clusterapi_cluster_openstack_image_id }}"
```

### Networking

By default, CAPO creates a new network and subnet for the garden cluster. The subnet CIDR is set via `clusterapi_cluster_openstack_managed_subnets`:

```yaml
clusterapi_cluster_openstack_managed_subnets:
  - cidr: "192.168.0.0/24"
    dns_nameservers:
      - "1.1.1.1"
```

To use an existing subnet instead (for example, one allocated from an OpenStack subnet pool), set `clusterapi_cluster_openstack_subnets`. This is mutually exclusive with `managed_subnets`. DNS nameservers are configured on the subnet in OpenStack directly, not here.

```yaml
clusterapi_cluster_openstack_subnets:
  - id: "existing-subnet-uuid"
```

### CNI

| Variable | Default | Description |
|----------|---------|-------------|
| `clusterapi_cluster_network` | `cilium` | CNI plugin: `cilium` or `calico`. |
| `clusterapi_cluster_cilium_version` | `1.19.3` | Cilium chart version. |
| `clusterapi_cluster_calico_version` | `v3.32.0` | Calico chart version (tigera-operator). |

## Gardener Operator

The `gardener_operator` role deploys the Gardener Operator and configures the entire Gardener control plane.

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `gardener_operator_version` | `1.142.1` | Gardener Operator Helm chart version. |
| `gardener_operator_kubernetes_version` | `1.36.1` | Kubernetes version for the internal seed shoot. |
| `gardener_operator_garden_url` | `example.com` | Base domain for the Gardener installation. |
| `gardener_operator_garden_cluster_admin_email` | `admin@example.com` | Email address for the Gardener dashboard admin. |
| `gardener_operator_networking_type` | `cilium` | Default CNI for shoots: `cilium` or `calico`. |

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

| Variable | Description |
|----------|-------------|
| `gardener_operator_provider_openstack_version` | OpenStack provider extension version. |
| `gardener_operator_provider_aws_version` | AWS provider extension version (deployed only when DNS type is `aws-route53`). |
| `gardener_operator_provider_azure_version` | Azure provider extension version (deployed only when DNS type is `azure-dns`). |
| `gardener_operator_provider_gcp_version` | GCP provider extension version (deployed only when DNS type is `google-clouddns`). |
| `gardener_operator_networking_cilium_version` | Cilium networking extension version. |
| `gardener_operator_networking_calico_version` | Calico networking extension version. |
| `gardener_operator_os_gardenlinux_version` | GardenLinux OS extension version. |
| `gardener_operator_os_ubuntu_version` | Ubuntu OS extension version. |
| `gardener_operator_shoot_cert_service_version` | Shoot certificate service version. |
| `gardener_operator_shoot_dns_service_version` | Shoot DNS service version. |

OS types to deploy are controlled by `gardener_operator_os_types` (default: `[gardenlinux]`). Add `ubuntu` to also support Ubuntu-based worker nodes.

### Certificate Issuance

The shoot certificate service supports ACME (Let's Encrypt) and a custom CA.

```yaml
# ACME (default)
gardener_operator_shoot_cert_service_issuer_type: acme
gardener_operator_shoot_cert_service_acme_email: "certs@example.com"
gardener_operator_shoot_cert_service_acme_server: "https://acme-v02.api.letsencrypt.org/directory"

# Custom CA
gardener_operator_shoot_cert_service_issuer_type: ca
gardener_operator_shoot_cert_service_ca_certificate: |
  -----BEGIN CERTIFICATE-----
  ...
gardener_operator_shoot_cert_service_ca_key: |
  -----BEGIN RSA PRIVATE KEY-----
  ...
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
          - version: 2150.0.0
            image: "Garden Linux 2150.0"
            regions:
              - name: region-a
                id: "6ed7d8aa-e770-4061-a8d7-461a83e41c31"
    kubernetes_versions:
      - version: 1.35.3
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
| `workers_cidr` | No | Worker subnet CIDR (default: `10.120.0.0/16`). Mutually exclusive with `subnet_pool`. |
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
    image_version: 2150.0.0
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

S3-compatible storage is also supported by setting the provider to `S3` and configuring the corresponding credentials.

### Registry Mirrors

To proxy container image pulls through a private registry, configure `gardener_operator_managed_seeds_registry_mirrors`. The registry cache extension is deployed automatically when this list is non-empty.

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
