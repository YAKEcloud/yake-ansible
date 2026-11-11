# Scripts

Auxiliary scripts for operating a YAKE environment. These are standalone tools
and do not require the Ansible playbooks to run.

---

## update-images.py

Syncs CAPI and GardenLinux images to OpenStack Glance.
Run this before setting up a new environment or after a Kubernetes/GardenLinux release.

### Requirements

```bash
pip install -r requirements.txt
```

### Authentication

The script uses the standard OpenStack credential chain:

```bash
# Option 1: clouds.yaml (recommended)
export OS_CLOUD=mycloud
python3 scripts/update-images.py

# Option 2: explicit --cloud flag
python3 scripts/update-images.py --cloud mycloud

# Option 3: environment variables (OS_AUTH_URL, OS_APPLICATION_CREDENTIAL_ID, ...)
python3 scripts/update-images.py
```

### Usage

```bash
# Sync both image types (--k8s-version is required)
python3 scripts/update-images.py --k8s-version 1.35.4

# Only CAPI image
python3 scripts/update-images.py --skip-gardenlinux --k8s-version 1.35.4

# Bare minor: resolved to the current patch release of that series
python3 scripts/update-images.py --k8s-version 1.35

# Override the Ubuntu base (default: auto-detected from the series' 'last-X' file)
python3 scripts/update-images.py --k8s-version 1.37 --ubuntu-version 2604

# Only GardenLinux (latest release)
python3 scripts/update-images.py --skip-capi

# Pin a specific GardenLinux version instead of using the latest
python3 scripts/update-images.py --skip-capi --gardenlinux-version 2150.3.0

# Check what would be uploaded without actually uploading anything
python3 scripts/update-images.py --dry-run --k8s-version 1.35.4

# Write the IDs of the selected images to a file ('capi=<id>', 'gardenlinux=<id>')
python3 scripts/update-images.py --ids-file image-ids.txt --k8s-version 1.35.4

# Skip TLS certificate verification for the OpenStack API (for self-signed certificates)
python3 scripts/update-images.py --insecure --k8s-version 1.35.4

# Disable OpenStack web-download import and download the CAPI image locally first
# (use this if web-download is disabled on your cloud)
python3 scripts/update-images.py --no-web-download --k8s-version 1.35.4

# Import into all Glance stores (existing images are copied, own project only)
python3 scripts/update-images.py --all-stores --k8s-version 1.35.4
```

### What the script uploads

**CAPI images** (Ubuntu-based Kubernetes node images):

| Glance name | Source |
|---|---|
| `ubuntu-capi-image-v1.35.6` | `nbg1.your-objectstorage.com/osism/openstack-k8s-capi-images/ubuntu-2404-kube-v1.35/ubuntu-2404-kube-v1.35.6.qcow2` |

The name follows the [SCS standard scs-0104-v2](https://docs.scs.community/standards/scs-0104-v2-standard-images).
Versions are validated (`X.Y[.Z]`) before anything is requested.

The following properties are set automatically as required by the SCS standard:
`os_purpose=k8snode`, `image_description`, `image_source`.

These images are used by Cluster API for management and seed cluster nodes.
Reference them in `group_vars/all.yml` via `clusterapi_cluster_openstack_image_id`
(look up the ID in the script's summary or in Glance).

**GardenLinux images:** OS images for Gardener shoot worker nodes:

| Glance name | Source |
|---|---|
| `Garden Linux 2150.3` | GitHub release `gardenlinux/gardenlinux` → `openstack-gardener_prod-amd64-*.tar.xz` |

The name follows the Gardener cloudprofile convention (`Garden Linux <major>.<minor>`) and
must match the `image` field in `gardener_operator_cloudprofiles[].machine_images[].versions[].image`.

### How duplicate detection works

Before uploading, the script runs three checks in order and stops as soon as one matches.
Only images in status `active` count, so leftovers of failed uploads never block a re-run
(and a failed upload deletes its own image record):

| Strategy | What it checks |
|---|---|
| 1. Exact name | Glance name equals the canonical name (e.g. `Garden Linux 2150.3`) |
| 2. Property match | Custom properties set by this script on previous uploads (`kube_version` for CAPI, `os_version` + `os_distro` for GardenLinux) |
| 3. Fuzzy name scan | Scans all images in Glance and checks whether the version appears in the name as a whole number (`1.35.1` does not match `1.35.10`) |

The output tells you which strategy matched, for example:

```
[SKIP]   Garden Linux 2150.3  — found via fuzzy name match (gardenlinux + version in 'gardenlinux-2150-openstack')  (abc123...)
```

The fuzzy scan catches manually uploaded images regardless of how they were named,
as long as the version number is part of the name.
If the image exists with no version in its name at all (e.g. just `gardenlinux-latest`),
the script cannot detect it and will upload a new one. Use `--dry-run` first to review.

### Integrity

Local downloads are verified with SHA-256: CAPI images against the `<file>.CHECKSUM`
file osism publishes next to each image, GardenLinux archives against the digest GitHub
records for the release asset. A mismatch aborts the upload; a missing checksum prints a
warning. With `web-download` Glance fetches the data itself, so it is not verified by the script.

### Upload method

| Image type | Method |
|---|---|
| CAPI | OpenStack `web-download` import (default). Glance downloads the qcow2 directly from the URL, nothing is transferred through the machine running the script |
| GardenLinux | Local download (tar.xz) → extract → upload (always, since the image is packed inside an archive) |

For the CAPI image, the script creates the Glance image record and then triggers an
[interoperable image import](https://docs.openstack.org/glance/latest/admin/interoperable-image-import.html)
with `method=web-download`, pointing Glance at the source URL. Not every cloud has this
import method enabled; if it's disabled, uploads fail with an error mentioning the
`web-download` method. In that case, pass `--no-web-download` to fall back to downloading
the qcow2 to the local machine first and streaming the upload from there.

All images are uploaded with `visibility=community`, so they can be used from other projects by ID (they do not show up in image lists there unless `--community` is passed). Existing images keep their visibility; change one with `openstack image set --community <id>`. Temporary local files (downloads, extracted
archives) are cleaned up automatically after each upload, even if an error occurs.

### Changing the GardenLinux flavor

By default the script uses the `openstack-gardener_prod` flavor (amd64).
If you need a different variant (e.g. `openstack-gardener-metal_prod` for bare-metal nodes),
change the `GARDENLINUX_FLAVOR` constant at the top of the script:

```python
GARDENLINUX_FLAVOR = "openstack-gardener-metal_prod"
```

Available flavors follow the pattern `openstack-<flavor>-<arch>-<version>-<commit>.tar.xz`
and can be browsed on the [GardenLinux releases page](https://github.com/gardenlinux/gardenlinux/releases).

---

## cleanup-openstack.py

Deletes the OpenStack resources built by a yake-ansible cluster/seed, and only those.
Never deletes "everything except a preserved list": a shared OpenStack project can hold
unrelated infrastructure that must never be touched. All listings are scoped to the
current project, with two exceptions. DNS record sets are deleted per zone, not per project: a Designate zone shared with other projects loses their records too (see the DNS row below). Nova key pairs belong to a user, not to a project. The key pair named like the cluster is deleted for the user of the credentials, so make sure that no other project of that user uses a key pair with this name. Used by `cleanup.yml`.

### Requirements

```bash
pip install -r requirements.txt
```

### Usage

```bash
export OS_CLOUD=mycloud   # or use --cloud

# Clean up the clusterapi_cluster (default name: garden) and its DNS zone
python3 scripts/cleanup-openstack.py --garden-url botany.example.com

# Also clean up one or more managed seeds
python3 scripts/cleanup-openstack.py --seed-names managed-seed-a,managed-seed-b --garden-url botany.example.com

# Check what would be deleted without deleting anything
python3 scripts/cleanup-openstack.py --seed-names managed-seed-a --dry-run
```

`--cluster-name` (default `garden`) and `--seeds-project` (default `seeds`) only need to be
passed if `clusterapi_cluster_name` / `gardener_operator_managed_seeds_project.name` were
changed from their defaults. `--insecure` disables TLS verification, `--preserve-dns-type`
(repeatable) keeps further record types in the zone. `SOA` and `NS` are always kept.

The script prints the auth URL, project name/id and the number of resources found before
deleting. Individual failures are collected, the remaining resources are still processed,
and the exit code is 1 if anything could not be deleted (2 for credential errors).

### What is matched

| Resource | Match |
|---|---|
| Networks, subnets, routers | exact CAPO name `k8s-clusterapi-cluster-default-<cluster>` or shoot ID `shoot--<project>--<seed>` |
| Security groups | `k8s-cluster-default-<cluster>-secgroup-{controlplane,worker,bastion}` or exact shoot ID |
| Servers | CAPI machine names `<cluster>-control-plane-xxxxx` / `<cluster>-<md>-<hash>-xxxxx` or Gardener machine names `<shoot ID>-<pool>-z<n>-...`, and on one of the owner's networks. A server without addresses (e.g. in `ERROR`) cannot be checked against the network and is matched by name only, so a cluster `garden-prod` next to `garden` in the same project could be hit by this |
| Limitation | Clusters on existing subnets (`clusterapi_cluster_openstack_subnets`) have no managed network, so their servers cannot be matched safely and are not deleted. The same holds for everything that is matched through the network. Delete these by hand. |
| Server groups, key pair | `<cluster>-control-plane`, `<cluster>-worker`; key pair `<cluster>` (or shoot ID) |
| Load balancers | API server LB `k8s-clusterapi-cluster-default-<cluster>-kubeapi`; CCM LBs `kube_service_kubernetes_*` only if on the cluster's own network; shoot LBs `kube_service_<shoot ID>_*` |
| Volumes | attached to an own server, or Cinder CSI metadata `cinder.csi.openstack.org/cluster` equal to a shoot ID. PVC volumes of the garden cluster (CSI cluster name `kubernetes`) are only deleted while attached to an own server |
| Ports | on own networks (Neutron-managed `network:*` ports are left to Neutron) |
| Floating IPs | attached to an own port, or with the CAPO description `Created by cluster-api-provider-openstack cluster default-<cluster-name>` (also when no longer attached) |
| DNS | all record sets of the zone `--garden-url` except `SOA`, `NS` and `--preserve-dns-type`. Gardener names records after projects and shoots, so they cannot be enumerated: use a zone dedicated to this deployment |
