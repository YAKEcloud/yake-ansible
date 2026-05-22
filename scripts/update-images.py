#!/usr/bin/env python3
"""
Sync CAPI and GardenLinux images to OpenStack Glance.

CAPI images (Gardener variant):
  Pulled from https://nbg1.your-objectstorage.com/osism/openstack-k8s-capi-images/
  One image per Kubernetes patch version (e.g. v1.35.4).
  Downloaded locally, then uploaded to Glance.

GardenLinux images:
  Pulled from GitHub releases (gardenlinux/gardenlinux).
  Assets are tar.xz archives containing a .raw or .qcow2 — always downloaded
  locally first.
  Glance name follows the cloudprofile convention: "Garden Linux 2150.3"

Requirements:
  pip install openstacksdk requests

Usage:
  export OS_CLOUD=mycloud   # or use --cloud
  python3 update-images.py --k8s-version 1.35.4
  python3 update-images.py --skip-capi
  python3 update-images.py --skip-gardenlinux --k8s-version 1.35.4
  python3 update-images.py --gardenlinux-version 2150.3.0
  python3 update-images.py --dry-run
"""

import argparse
import os
import sys
import tarfile
import tempfile
import time
from pathlib import Path

try:
    import openstack
except ImportError:
    sys.exit("Missing dependency: pip install openstacksdk")

try:
    import requests
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
except ImportError:
    sys.exit("Missing dependency: pip install requests")

try:
    from tqdm import tqdm
except ImportError:
    sys.exit("Missing dependency: pip install tqdm")


CAPI_BASE_URL = "https://nbg1.your-objectstorage.com/osism/openstack-k8s-capi-images"
GARDENLINUX_REPO = "gardenlinux/gardenlinux"
# adjust if you need metal_prod or _usi variant
GARDENLINUX_FLAVOR = "openstack-gardener_prod"


def _short_gl_version(version):
    """'2150.3.0' → '2150.3',  '2150.3' → '2150.3'"""
    parts = version.split(".")
    if len(parts) == 3 and parts[2] == "0":
        return f"{parts[0]}.{parts[1]}"
    return version


def find_capi_image(conn, patch_version):
    """
    Look for an existing CAPI image using three strategies, in order:
      1. Exact Glance name match  (ubuntu-capi-image-v1.35.4)
      2. Custom property 'kube_version' set by this script on previous uploads
      3. Fuzzy name scan — finds images uploaded manually under any name,
         as long as 'capi' and 'v<patch>' appear somewhere in the image name
    Returns (image, strategy_description) or (None, None).
    """
    patch = patch_version.lstrip("v")
    canonical_name = f"ubuntu-capi-image-v{patch}"

    # 1. Exact name
    hits = list(conn.image.images(name=canonical_name))
    if hits:
        return hits[0], f"exact name '{canonical_name}'"

    # 2. Property: kube_version (set by this script) — verify after fetch since
    #    Glance may ignore unknown property filters and return all images
    for img in conn.image.images(kube_version=f"v{patch}"):
        if img.get("kube_version") == f"v{patch}":
            return img, f"kube_version property 'v{patch}'"

    # 3. Fuzzy name scan
    for img in conn.image.images():
        name_lower = (img.name or "").lower()
        if "capi" in name_lower and f"v{patch}" in name_lower:
            return img, (f"fuzzy name match ('capi' + 'v{patch}' in '{img.name}')")

    return None, None


def find_gardenlinux_image(conn, version):
    """
    Look for an existing GardenLinux image using three strategies, in order:
      1. Exact Glance name match  (Garden Linux 2150.3)
      2. Property 'os_version' set by this script on previous uploads
      3. Fuzzy name scan — finds images uploaded manually under any name,
         as long as 'gardenlinux'/'garden linux'/'garden-linux' and the version
         number appear somewhere in the image name
    Returns (image, strategy_description) or (None, None).
    """
    short = _short_gl_version(version)
    canonical_name = f"Garden Linux {short}"

    # 1. Exact name
    hits = list(conn.image.images(name=canonical_name))
    if hits:
        return hits[0], f"exact name '{canonical_name}'"

    # 2. Property: os_version (set by this script) — verify after fetch since
    #    Glance may ignore unknown property filters and return all images
    for v in (version, short):
        for img in conn.image.images(os_distro="gardenlinux", os_version=v):
            if img.get("os_distro") == "gardenlinux" and img.get("os_version") in (
                version,
                short,
            ):
                return img, f"os_version property '{v}'"

    # 3. Fuzzy name scan
    gl_keywords = ("gardenlinux", "garden linux", "garden-linux")
    for img in conn.image.images():
        name_lower = (img.name or "").lower()
        if any(kw in name_lower for kw in gl_keywords):
            if short in name_lower or version in name_lower:
                return img, (
                    f"fuzzy name match " f"(gardenlinux + version in '{img.name}')"
                )

    return None, None


def _wait_for_active(conn, image_id, timeout=3600):
    deadline = time.time() + timeout
    while time.time() < deadline:
        img = conn.image.get_image(image_id)
        if img.status == "active":
            return img
        if img.status in ("killed", "deleted"):
            raise RuntimeError(f"Image {image_id} ended up in status '{img.status}'")
        time.sleep(15)
    raise TimeoutError(f"Image {image_id} did not become active within {timeout}s")


class _ProgressReader:
    """Wraps a file object and updates a tqdm bar as data is read."""

    def __init__(self, fh, pbar):
        self._fh = fh
        self._pbar = pbar

    def read(self, size=-1):
        data = self._fh.read(size)
        self._pbar.update(len(data))
        return data


def upload_from_file(conn, name, path, disk_format="qcow2", extra_props=None):
    file_size = path.stat().st_size
    with tqdm(
        total=file_size,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        desc=f"    ↑ {name}",
        leave=False,
    ) as pbar:
        with open(path, "rb") as fh:
            image = conn.image.create_image(
                name=name,
                disk_format=disk_format,
                container_format="bare",
                visibility="shared",
                min_disk=20,
                min_ram=512,
                **(extra_props or {}),
                data=_ProgressReader(fh, pbar),
            )
    return _wait_for_active(conn, image.id)


def download_file(url, dest, label=""):
    label = label or Path(url).name
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0)) or None
        with tqdm(
            total=total,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=f"    ↓ {label}",
            leave=False,
        ) as pbar:
            with open(dest, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=65536):
                    fh.write(chunk)
                    pbar.update(len(chunk))


def sync_capi_image(conn, k8s_version, ubuntu_version="2404", dry_run=False):
    print("\n=== CAPI Image (Gardener variant) ===")

    patch = k8s_version.lstrip("v")  # e.g. "1.35.4"
    minor = ".".join(patch.split(".")[:2])  # e.g. "1.35"
    canonical_name = f"ubuntu-capi-image-v{patch}"
    # Directory is keyed by minor version; filename contains the full patch.
    url = (
        f"{CAPI_BASE_URL}/ubuntu-{ubuntu_version}-kube-v{minor}-gardener"
        f"/ubuntu-{ubuntu_version}-kube-v{patch}.qcow2"
    )

    existing, strategy = find_capi_image(conn, patch)
    if existing:
        print(
            f"  [SKIP]   {canonical_name}" f"  — found via {strategy}  ({existing.id})"
        )
        return canonical_name, existing.id

    if dry_run:
        print(f"  [DRY-RUN] would download and upload {canonical_name}" f"  from {url}")
        return canonical_name, None

    print(f"  [UPLOAD] {canonical_name}")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / f"{canonical_name}.qcow2"
            download_file(url, local, canonical_name)
            image = upload_from_file(
                conn,
                canonical_name,
                local,
                extra_props={
                    "os_purpose": "k8snode",
                    "os_distro": "ubuntu",
                    "kube_version": f"v{patch}",
                    "image_description": ("https://github.com/osism/k8s-capi-images"),
                    "image_source": url,
                },
            )
        print(f"  [DONE]   {canonical_name}")
        return canonical_name, image.id
    except Exception as exc:
        print(f"  [ERROR]  {canonical_name}: {exc}", file=sys.stderr)
        return canonical_name, None


def fetch_gardenlinux_release(version=None):
    if version:
        url = (
            f"https://api.github.com/repos/{GARDENLINUX_REPO}"
            f"/releases/tags/{version}"
        )
    else:
        url = f"https://api.github.com/repos/{GARDENLINUX_REPO}" f"/releases/latest"

    resp = requests.get(
        url,
        headers={"Accept": "application/vnd.github.v3+json"},
        timeout=30,
    )
    resp.raise_for_status()
    release = resp.json()
    tag = release["tag_name"].lstrip("v")

    for asset in release["assets"]:
        n = asset["name"]
        if (
            GARDENLINUX_FLAVOR in n
            and "amd64" in n
            and n.endswith(".tar.xz")
            and "logs" not in n
            and "certs" not in n
        ):
            return tag, asset["browser_download_url"], asset["name"]

    raise RuntimeError(
        f"No matching GardenLinux asset for flavor '{GARDENLINUX_FLAVOR}'"
        f" (amd64) in release {tag}.\n"
        f"Set GARDENLINUX_FLAVOR at the top of the script to one of the"
        f" available variants."
    )


def extract_image(archive_path, dest_dir):
    """Return path to the first .raw or .qcow2 inside a tar.xz."""
    with tarfile.open(archive_path, "r:xz") as tar:
        for member in tar.getmembers():
            if member.name.endswith((".raw", ".qcow2")):
                member.name = os.path.basename(member.name)
                tar.extract(member, path=dest_dir)
                return Path(dest_dir) / member.name
    raise RuntimeError(f"No .raw or .qcow2 image found inside {archive_path.name}")


def sync_gardenlinux_image(conn, version=None, dry_run=False):
    print("\n=== GardenLinux Images ===")

    tag, asset_url, asset_name = fetch_gardenlinux_release(version)
    short = _short_gl_version(tag)
    canonical_name = f"Garden Linux {short}"
    print(f"  Release: {tag}  →  Glance name: '{canonical_name}'")

    existing, strategy = find_gardenlinux_image(conn, tag)
    if existing:
        print(
            f"  [SKIP]   '{canonical_name}'"
            f"  — found via {strategy}  ({existing.id})"
        )
        return canonical_name, existing.id

    if dry_run:
        print(
            f"  [DRY-RUN] would download and upload '{canonical_name}'"
            f"  from {asset_url}"
        )
        return canonical_name, None

    print(f"  [UPLOAD] {canonical_name}")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / asset_name
            download_file(asset_url, archive, asset_name)

            print("    → extracting archive ...")
            image_path = extract_image(archive, tmp)
            disk_format = "raw" if image_path.suffix == ".raw" else "qcow2"
            print(f"    → format: {disk_format}  file: {image_path.name}")

            image = upload_from_file(
                conn,
                canonical_name,
                image_path,
                disk_format=disk_format,
                extra_props={
                    "os_distro": "gardenlinux",
                    "os_version": tag,
                    "architecture": "amd64",
                },
            )
        print(f"  [DONE]   {canonical_name}")
        return canonical_name, image.id
    except Exception as exc:
        print(f"  [ERROR]  {canonical_name}: {exc}", file=sys.stderr)
        return canonical_name, None


def main():
    parser = argparse.ArgumentParser(
        description="Sync CAPI and GardenLinux images to OpenStack Glance.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--cloud",
        default=None,
        help="Cloud name from clouds.yaml (default: OS_CLOUD env var)",
    )
    parser.add_argument(
        "--k8s-version",
        metavar="X.Y.Z",
        default=None,
        help=(
            "Kubernetes patch version for the CAPI image, e.g. 1.35.4"
            " (required unless --skip-capi)"
        ),
    )
    parser.add_argument(
        "--ubuntu-version",
        default="2404",
        metavar="YYYYMM",
        help="Ubuntu version for CAPI images (default: 2404)",
    )
    parser.add_argument(
        "--gardenlinux-version",
        default=None,
        metavar="VERSION",
        help=("Pin a specific GardenLinux version" " (default: latest release)"),
    )
    parser.add_argument("--skip-capi", action="store_true", help="Skip CAPI images")
    parser.add_argument(
        "--skip-gardenlinux",
        action="store_true",
        help="Skip GardenLinux image",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=("Check what would be uploaded without actually uploading anything"),
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification (for self-signed certs)",
    )
    args = parser.parse_args()

    if args.insecure:
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    print("Connecting to OpenStack ...")
    try:
        conn = openstack.connect(cloud=args.cloud, insecure=args.insecure)
        _ = conn.auth["auth_url"]
    except Exception:
        sys.exit(
            "No OpenStack credentials found." " Set OS_CLOUD or pass --cloud <name>."
        )
    print(f"Connected: {conn.auth['auth_url']}")

    if not args.skip_capi and not args.k8s_version:
        parser.error("--k8s-version is required unless --skip-capi is set")

    if args.dry_run:
        print("Dry-run mode — no images will be uploaded.")

    results = []

    if not args.skip_capi:
        results.append(
            sync_capi_image(conn, args.k8s_version, args.ubuntu_version, args.dry_run)
        )

    if not args.skip_gardenlinux:
        results.append(
            sync_gardenlinux_image(conn, args.gardenlinux_version, args.dry_run)
        )

    print("\n=== Summary ===")
    for name, image_id in results:
        if image_id:
            print(f"  {name}")
            print(f"    ID: {image_id}")
        else:
            print(f"  {name}  — not uploaded (error or dry-run)")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nAborted.")
    except Exception as exc:
        sys.exit(f"Error: {exc}")
