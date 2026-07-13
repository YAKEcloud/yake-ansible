# gardener_operator

This role deploys the Gardener Operator on an existing Kubernetes cluster and configures the full Gardener control plane, including cloud profiles, managed seeds, Dex, and all required extensions.

## What this role does

1. Creates the `garden` namespace and installs the Gardener Operator via Helm from the OCI registry.
2. Renders and applies the `Garden` resource, which triggers the Operator to bootstrap the virtual garden (etcd, API server, controller manager, scheduler, dashboard).
3. Deploys all configured extensions as `Extension` resources: the OpenStack provider, networking plugins, OS extensions, DNS and certificate services, and optionally registry cache and OIDC service.
4. Creates cloud profiles and configures DNS and backup credentials.
5. Waits for the virtual garden to become ready and saves the kubeconfig to `/var/lib/yake/gardener-operator/kubeconfig.vgarden`.
6. Creates a Garden project and configures the internal seed.
7. Creates managed seed shoots and registers them as Gardener seeds.

## Requirements

- A running Kubernetes cluster with a kubeconfig at `/var/lib/yake/kubeconfig.garden`.
- OpenStack Designate (or another supported DNS provider) with a zone that matches `gardener_operator_garden_url`.
- Machine images uploaded to Glance for all configured cloud profiles.

## Variables

### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `gardener_operator_version` | `1.142.1` | Gardener Operator Helm chart version. |
| `gardener_operator_garden_url` | `example.com` | Base domain. Wildcard DNS for this domain must point to the garden ingress. |
| `gardener_operator_kubernetes_version` | `1.36.1` | Kubernetes version for the internal seed shoot. |
| `gardener_operator_networking_type` | `cilium` | Default CNI for shoots: `cilium` or `calico`. |
| `gardener_operator_garden_cluster_admin_email` | `admin@example.com` | Admin email for the Gardener dashboard. |

### OpenStack Credentials

| Variable | Description |
|----------|-------------|
| `gardener_operator_openstack_auth_url` | Keystone URL. |
| `gardener_operator_openstack_project_name` | OpenStack project name. |
| `gardener_operator_openstack_domain_name` | OpenStack domain name. |
| `gardener_operator_openstack_region_name` | OpenStack region. |
| `gardener_operator_openstack_application_credential_id` | Application credential ID. |
| `gardener_operator_openstack_application_credential_name` | Application credential name. |
| `gardener_operator_openstack_application_credential_secret` | Application credential secret. |
| `gardener_operator_openstack_cacert` | PEM-encoded CA certificate (optional). |
| `gardener_operator_openstack_zones` | List of availability zones. |

`gardener_operator_provider_openstack_helm_values` is merged as-is into the `provider-openstack` extension's Helm chart values (empty by default, no override). Use it for anything the chart supports but this role doesn't expose directly, e.g. the etcd storage class provisioned for shoot control planes ([`config.etcd.storage`](https://github.com/gardener/gardener-extension-provider-openstack/blob/master/charts/gardener-extension-provider-openstack/values.yaml)):

```yaml
gardener_operator_provider_openstack_helm_values:
  config:
    etcd:
      storage:
        className: my-fast-storage-class
        capacity: 25Gi
```

### DNS Provider

`gardener_operator_dns_provider_type` selects the DNS provider. Supported values: `openstack-designate`, `aws-route53`, `azure-dns`, `google-clouddns`.

For `openstack-designate`, set `gardener_operator_dns_credentials: {}` to reuse the OpenStack credentials above. For other providers, set the corresponding key/value credentials in `gardener_operator_dns_credentials`.

### Cloud Profiles

`gardener_operator_cloudprofiles` is a list of cloud profile definitions. Each entry creates a `CloudProfile` resource in the virtual garden.

Key fields per profile:

| Field | Description |
|-------|-------------|
| `name` | Cloud profile name. |
| `storageclasses` | Cinder storage classes with type, availability zone, and optional default flag. |
| `floating_pools` | List of floating pool names available for shoot load balancers. |
| `loadbalancer_providers` | List of available load balancer providers (e.g., `amphora`, `ovn`). |
| `keystone_urls` | Keystone URL per region. |
| `machine_images` | Machine images with versions and per-region Glance IDs. |
| `kubernetes_versions` | Available Kubernetes versions with classification (`preview`, `supported`, `deprecated`). |
| `machinetypes` | Machine type definitions with CPU, GPU, and memory. |
| `regions` | Regions with availability zones. |

### Managed Seeds

`gardener_operator_managed_seeds` is a list of seeds to create. Each entry creates a shoot on the internal seed and registers it as a Gardener seed.

#### InfrastructureConfig: networks

The worker subnet for each managed seed is configured under the seed entry. Two approaches are supported and are mutually exclusive.

**Explicit CIDR:**

```yaml
workers_cidr: "10.120.0.0/16"
```

If `workers_cidr` is not set, it defaults to `10.120.0.0/16`.

**Subnet pool allocation** (requires gardener-extension-provider-openstack v1.55.0 or later):

```yaml
subnet_pool:
  id: "subnet-pool-uuid"
  prefix_length: 24  # optional, controls allocated subnet size
```

The load balancer provider defaults to `amphora` and can be overridden per seed:

```yaml
loadbalancer_provider: ovn
```

#### Full seed example

```yaml
gardener_operator_managed_seeds:
  - name: seed-a
    cloudprofile_name: openstack-a
    networking_type: cilium
    kubernetes_version: 1.35.3
    floating_pool_name: "public"
    loadbalancer_provider: amphora  # optional, default: amphora
    workers_cidr: "10.120.0.0/16"  # optional, default: 10.120.0.0/16
    openstack:
      auth_url: "https://keystone.example.com:5000"
      project_name: "seed-project"
      domain_name: "my-domain"
      region_name: "region-a"
      application_credential_id: "..."
      application_credential_name: "yake-seed"
      application_credential_secret: "..."
    workers:
      - name: worker-4v16
        machinetype: SCS-4V-16
        image_name: gardenlinux
        image_version: 2150.0.0
        minimum: 3
        maximum: 15
        volume_type: ssd
        volume_size: 50Gi
        zones:
          - nova
    settings:
      excess_capacity_reservation: true
```

### Backups

Etcd backups for the virtual garden and the internal seed are enabled when the corresponding credentials are set.

| Variable | Description |
|----------|-------------|
| `gardener_operator_garden_backup_provider` | Backup provider: `openstack` or `S3`. |
| `gardener_operator_garden_backup_bucket_name` | Bucket or container name. |
| `gardener_operator_garden_backup_credentials` | Provider credentials as a YAML string. |
| `gardener_operator_internal_seed_backup_provider` | Same for the internal seed. |
| `gardener_operator_internal_seed_backup_bucket_name` | Bucket or container name. |
| `gardener_operator_internal_seed_backup_credentials` | Provider credentials as a YAML string. |

## Monitoring

`gardener_operator_monitoring` configures remote write of shoot Prometheus metrics to a central Prometheus/Cortex instance, as described in the [Gardener monitoring docs](https://gardener.cloud/docs/gardener/monitoring/#collect-all-shoot-prometheus-with-remote-write). It applies to every shoot on the internal seed and on all managed seeds; there is nothing to configure per shoot.

| Variable | Default | Description |
|----------|---------|-------------|
| `gardener_operator_monitoring.remote_write.url` | `""` | Remote write endpoint. Feature is disabled while empty. |
| `gardener_operator_monitoring.remote_write.keep` | `[]` | Metric names to forward. Empty forwards all metrics. |
| `gardener_operator_monitoring.basic_auth.username` | `""` | Basic auth username for the remote write endpoint. |
| `gardener_operator_monitoring.basic_auth.password` | `""` | Basic auth password. Secret is only created when both username and password are set. |

This only covers shoot metrics. Gardener's own seed/garden monitoring (cache, aggregate and seed Prometheus) has no remote write option — it is pull-based: the [aggregate Prometheus](https://gardener.cloud/docs/gardener/monitoring/#aggregate-prometheus) exposes an ingress in each seed's `garden` namespace so an external Prometheus/Cortex can scrape (federate) it instead. There is no role variable for this; set up such scraping directly on the central Prometheus/Cortex side.

## Files written

| Path | Description |
|------|-------------|
| `/var/lib/yake/gardener-operator/kubeconfig.vgarden` | Virtual garden kubeconfig. |
