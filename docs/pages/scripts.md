# Scripts

The `scripts/` directory holds two standalone tools. They do not need the Ansible playbooks and use the standard OpenStack credential chain: a `clouds.yaml` entry (`OS_CLOUD` or `--cloud`) or the `OS_*` environment variables.

The full reference, with all options and the exact behavior, is in the [scripts README](https://github.com/YAKEcloud/yake-ansible/blob/main/scripts/README.md).

## update-images.py

Uploads the machine images the platform needs to OpenStack Glance: the Cluster API image for the garden cluster and the GardenLinux image for the worker nodes. Run it before you set up a new environment and after a new Kubernetes or GardenLinux release.

```bash
export OS_CLOUD=mycloud

# Check what would be uploaded
python3 scripts/update-images.py --dry-run --k8s-version 1.37

# Upload both images
python3 scripts/update-images.py --k8s-version 1.37
```

- Existing images are detected by name, by properties and by a scan for the version in the name, so a re-run does not upload duplicates. Only active images count.
- Local downloads are verified with SHA-256 where a checksum is published. The CAPI image is imported by Glance itself (`web-download`) and is not verified by the script. Use `--no-web-download` to download it locally and verify it.
- Images are uploaded with `visibility=community`, so other projects can use them by ID.
- With `--ids-file` the script writes the image IDs to a file, which you can use for your configuration.

The image names have to match the `image` field of your cloud profile. See [Installation](getting-started.md#machine-images).

## cleanup-openstack.py

Deletes the OpenStack resources that were created for a yake-ansible garden cluster or managed seed, and only those. It never deletes "everything except a list", because a shared OpenStack project may hold unrelated resources.

```bash
export OS_CLOUD=mycloud

# Check first
python3 scripts/cleanup-openstack.py \
  --garden-url gardener.example.com \
  --seed-names managed-seed-a,managed-seed-b \
  --dry-run

# Garden cluster and two managed seeds
python3 scripts/cleanup-openstack.py \
  --garden-url gardener.example.com \
  --seed-names managed-seed-a,managed-seed-b
```

!!! warning "Check the dry run first"
    - DNS record sets are deleted per Designate zone, not per project. A zone shared with other projects loses their records as well. Use `--preserve-dns-type` to keep further record types. `SOA` and `NS` are always kept.
    - Nova key pairs belong to a user, not to a project. The key pair named like the cluster is deleted for the user of the credentials.
    - A server without addresses, for example in `ERROR`, is matched by name only. A cluster `garden-prod` next to `garden` in the same project could be hit by this.

Use the script as the last step of a teardown, after the Gardener resources are gone. The order is described in [Operations](operations.md#cleanup).
