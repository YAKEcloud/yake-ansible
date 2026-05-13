# Scripts

Auxiliary scripts for operating a YAKE environment. These are standalone tools
and do not require the Ansible playbooks to run.

---

## update-images.py

Syncs CAPI and GardenLinux images to OpenStack Glance.
Run this before setting up a new environment or after a Kubernetes/GardenLinux release.

### Requirements

```bash
pip install openstacksdk requests
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

# Only GardenLinux (latest release)
python3 scripts/update-images.py --skip-capi

# Pin a specific GardenLinux version instead of using the latest
python3 scripts/update-images.py --skip-capi --gardenlinux-version 2150.3.0

# Check what would be uploaded without actually uploading anything
python3 scripts/update-images.py --dry-run
```

### What the script uploads

**CAPI images** — Ubuntu-based Kubernetes node images, Gardener variant:

| Glance name | Source |
|---|---|
| `ubuntu-capi-image-v1.35.4` | `nbg1.your-objectstorage.com/osism/openstack-k8s-capi-images/ubuntu-2404-kube-v1.35-gardener/ubuntu-2404-kube-v1.35.4.qcow2` |

The name follows the [SCS standard scs-0104-v2](https://docs.scs.community/standards/scs-0104-v2-standard-images).
The directory in the object store is keyed by minor version (`v1.35-gardener`);
the filename contains the full patch version (`v1.35.4.qcow2`).

The following properties are set automatically as required by the SCS standard:
`os_purpose=k8snode`, `image_description`, `image_source`.

These images are used by Cluster API for management and seed cluster nodes.
Reference them in `group_vars/all.yml` via `clusterapi_cluster_openstack_image_id`
(look up the ID after upload with `openstack image show ubuntu-2404-kube-v1.35.4 -f value -c id`).

**GardenLinux images** — OS images for Gardener shoot worker nodes:

| Glance name | Source |
|---|---|
| `Garden Linux 2150.3` | GitHub release `gardenlinux/gardenlinux` → `openstack-gardener_prod-amd64-*.tar.xz` |

The name follows the Gardener cloudprofile convention (`Garden Linux <major>.<minor>`) and
must match the `image` field in `gardener_operator_cloudprofiles[].machine_images[].versions[].image`.

### How duplicate detection works

Before uploading, the script runs three checks in order and stops as soon as one matches:

| Strategy | What it checks |
|---|---|
| 1. Exact name | Glance name equals the canonical name (e.g. `Garden Linux 2150.3`) |
| 2. Property match | Custom properties set by this script on previous uploads (`kube_version` for CAPI, `os_version` + `os_distro` for GardenLinux) |
| 3. Fuzzy name scan | Scans all images in Glance and checks whether the version string appears anywhere in the name |

The output tells you which strategy matched, for example:

```
[SKIP]   Garden Linux 2150.3  — found via fuzzy name match (gardenlinux + version in 'gardenlinux-2150-openstack')  (abc123...)
```

The fuzzy scan catches manually uploaded images regardless of how they were named,
as long as the version number is part of the name.
If the image exists with no version in its name at all (e.g. just `gardenlinux-latest`),
the script cannot detect it and will upload a new one — use `--dry-run` first to review.

### Upload method

| Image type | Method |
|---|---|
| CAPI | Local download (qcow2) → upload |
| GardenLinux | Local download (tar.xz) → extract → upload |

All images are uploaded with `visibility=shared`. Temporary local files (downloads, extracted
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
