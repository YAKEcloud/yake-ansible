#!/usr/bin/env python3
"""
Sync CAPI and GardenLinux images to OpenStack Glance.

CAPI images:
  Pulled from https://nbg1.your-objectstorage.com/osism/openstack-k8s-capi-images/
  One image per Kubernetes patch version (e.g. v1.35.4), which is
  create-once and never overwritten upstream — unlike the unversioned
  series file (v1.35.qcow2), which is silently replaced on every publish.
  --k8s-version accepts either a full patch (1.35.4) or a bare minor
  (1.35); a bare minor is resolved to its current patch via the series'
  'last-X' pointer file before anything is named or uploaded, so the
  Glance image is always named after a concrete, stable patch version.
  Imported into Glance via the 'web-download' method by default, so
  OpenStack downloads the qcow2 directly — use --no-web-download to
  download it locally first instead.

GardenLinux images:
  Pulled from GitHub releases (gardenlinux/gardenlinux); the highest
  version among all non-draft, non-prerelease releases is used unless
  --gardenlinux-version pins one.
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
  python3 update-images.py --no-web-download --k8s-version 1.35.4
  python3 update-images.py --k8s-version 1.35   # resolves current patch, e.g. 1.35.8
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
    from keystoneauth1.exceptions.connection import ConnectionError as OSConnectionError
except ImportError:
    sys.exit("Missing dependency: pip install openstacksdk")

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: pip install requests")

try:
    import urllib3
    from urllib3.exceptions import InsecureRequestWarning
except ImportError:
    sys.exit("Missing dependency: pip install urllib3")

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
         as long as 'capi' and 'v<patch>' appear somewhere in the image name.
    Returns (image, strategy_description) or (None, None).
    """
    patch = patch_version.lstrip("v")
    canonical_name = f"ubuntu-capi-image-v{patch}"
    kube_version = f"v{patch}"

    # 1. Exact name
    hits = list(conn.image.images(name=canonical_name))
    if hits:
        return hits[0], f"exact name '{canonical_name}'"

    # 2. Property: kube_version (set by this script) — verify after fetch since
    #    Glance may ignore unknown property filters and return all images
    for img in conn.image.images(kube_version=kube_version):
        if img.get("kube_version") == kube_version:
            return img, f"kube_version property '{kube_version}'"

    # 3. Fuzzy name scan
    for img in conn.image.images():
        name_lower = (img.name or "").lower()
        if "capi" in name_lower and f"v{patch}" in name_lower:
            return img, f"fuzzy name match ('capi' + 'v{patch}' in '{img.name}')"

    return None, None


def resolve_capi_patch_version(minor):
    """Resolve a bare minor version (e.g. '1.36') to its current patch (e.g.
    '1.36.4') via the series' 'last-X' pointer file, which osism updates on
    every publish. Returns the patch version, e.g. '1.36.4'.
    """
    url = f"{CAPI_BASE_URL}/last-{minor}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    # format: "YYYY-MM-DD ubuntu-2404-kube-vX.YY/ubuntu-2404-kube-vX.YY.Z.qcow2"
    line = resp.text.strip()
    try:
        path = line.split(maxsplit=1)[1]
        patch = Path(path).stem.rsplit("-v", 1)[-1]
    except (IndexError, ValueError) as exc:
        raise RuntimeError(f"Could not parse pointer file '{url}': {line!r}") from exc
    return patch


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
        if any(kw in name_lower for kw in gl_keywords) and (
            short in name_lower or version in name_lower
        ):
            return img, (
                f"fuzzy name match " f"(gardenlinux + version in '{img.name}')"
            )

    return None, None


def _get_image_resilient(conn, image_id, max_retries=5):
    """conn.image.get_image(), retrying transient connection drops.

    Long-running web-download imports get polled for up to an hour; the
    Glance API connection occasionally resets mid-poll, which shouldn't
    abort an otherwise-healthy import.
    """
    for attempt in range(1, max_retries + 1):
        try:
            return conn.image.get_image(image_id)
        except (
            OSConnectionError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as exc:
            if attempt == max_retries:
                raise
            wait = min(30, 2**attempt)
            print(
                f"      connection hiccup polling image status"
                f" (attempt {attempt}/{max_retries}): {exc} — retrying in {wait}s"
            )
            time.sleep(wait)
    raise RuntimeError(f"Unable to fetch image {image_id} after {max_retries} attempts")


def _wait_for_active(conn, image_id, timeout=3600):
    deadline = time.time() + timeout
    while time.time() < deadline:
        img = _get_image_resilient(conn, image_id)
        if img.status == "active":
            return img
        if img.status in ("killed", "deleted"):
            raise RuntimeError(f"Image {image_id} ended up in status '{img.status}'")
        time.sleep(15)
    raise TimeoutError(f"Image {image_id} did not become active within {timeout}s")


def _human_size(num_bytes):
    if not num_bytes:
        return "unknown size"
    size = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def _get_content_length(url):
    """Best-effort HEAD request to learn the source file size upfront."""
    try:
        resp = requests.head(url, timeout=30, allow_redirects=True)
        resp.raise_for_status()
        length = resp.headers.get("content-length")
        return int(length) if length else None
    except requests.RequestException:
        return None


def _wait_for_import(conn, image_id, total_size=None, timeout=3600, poll_interval=10):
    start = time.time()
    deadline = start + timeout
    last_status = None
    while time.time() < deadline:
        img = _get_image_resilient(conn, image_id)
        elapsed = int(time.time() - start)
        progress = ""
        if total_size and img.size:
            pct = min(100, img.size * 100 // total_size)
            progress = (
                f"  ~{pct}% ({_human_size(img.size)} / {_human_size(total_size)})"
            )
        if img.status != last_status:
            print(f"      status: {img.status}  (elapsed: {elapsed}s){progress}")
            last_status = img.status
        elif img.status == "importing":
            print(f"      still importing ...  (elapsed: {elapsed}s){progress}")
        if img.status == "active":
            return img
        if img.status in ("killed", "deleted"):
            raise RuntimeError(
                f"Image {image_id} ended up in status '{img.status}' during import"
            )
        time.sleep(poll_interval)
    raise TimeoutError(f"Image {image_id} did not become active within {timeout}s")


def upload_via_web_download(conn, name, url, disk_format="qcow2", extra_props=None):
    """Create an image record and let OpenStack download the data itself.

    Requires the 'web-download' import method to be enabled on the cloud
    (most public/managed OpenStack clouds support it). Use --no-web-download
    to fall back to downloading locally and streaming the upload instead.
    """
    image = conn.image.create_image(
        name=name,
        disk_format=disk_format,
        container_format="bare",
        visibility="shared",
        min_disk=20,
        min_ram=512,
        **(extra_props or {}),
    )
    total_size = _get_content_length(url)
    print(f"    → requesting web-download import from {url}")
    print(f"    → source size: {_human_size(total_size)}")
    conn.image.import_image(image, method="web-download", uri=url)
    return _wait_for_import(conn, image.id, total_size=total_size)


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
    with (
        tqdm(
            total=file_size,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=f"    ↑ {name}",
            leave=False,
        ) as pbar,
        open(path, "rb") as fh,
    ):
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
        with (
            tqdm(
                total=total,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc=f"    ↓ {label}",
                leave=False,
            ) as pbar,
            open(dest, "wb") as fh,
        ):
            for chunk in resp.iter_content(chunk_size=65536):
                fh.write(chunk)
                pbar.update(len(chunk))


def sync_capi_image(
    conn,
    k8s_version,
    ubuntu_version="2404",
    dry_run=False,
    web_download=True,
):
    print("\n=== CAPI Image ===")

    version = k8s_version.lstrip("v")
    if version.count(".") < 2:
        # Bare minor: resolve the current patch for naming/dedup, but still
        # download the series file — it's rebuilt (and overwritten) on every
        # publish, including image-only fixes that don't bump the patch, so
        # it's the only URL that's guaranteed to be current. The create-once
        # per-patch file can lag behind it.
        minor = version
        print(f"  Resolving current patch for series v{minor} ...")
        patch = resolve_capi_patch_version(minor)
        print(f"  Resolved: v{minor} → v{patch}")
        filename = f"ubuntu-{ubuntu_version}-kube-v{minor}.qcow2"
    else:
        # Exact patch requested: fetch that immutable, create-once file.
        patch = version
        minor = ".".join(patch.split(".")[:2])
        filename = f"ubuntu-{ubuntu_version}-kube-v{patch}.qcow2"

    canonical_name = f"ubuntu-capi-image-v{patch}"
    url = f"{CAPI_BASE_URL}/ubuntu-{ubuntu_version}-kube-v{minor}/{filename}"

    existing, strategy = find_capi_image(conn, patch)
    if existing:
        print(
            f"  [SKIP]   {canonical_name}" f"  — found via {strategy}  ({existing.id})"
        )
        return canonical_name, existing.id

    if dry_run:
        method = "web-download import" if web_download else "download and upload"
        print(f"  [DRY-RUN] would {method} {canonical_name}" f"  from {url}")
        return canonical_name, None

    extra_props = {
        "os_purpose": "k8snode",
        "os_distro": "ubuntu",
        "kube_version": f"v{patch}",
        "image_description": ("https://github.com/osism/k8s-capi-images"),
        "image_source": url,
    }

    print(
        f"  [UPLOAD] {canonical_name}" + ("" if web_download else " (local download)")
    )
    try:
        if web_download:
            image = upload_via_web_download(
                conn, canonical_name, url, extra_props=extra_props
            )
        else:
            with tempfile.TemporaryDirectory() as tmp:
                local = Path(tmp) / f"{canonical_name}.qcow2"
                download_file(url, local, canonical_name)
                image = upload_from_file(
                    conn, canonical_name, local, extra_props=extra_props
                )
        print(f"  [DONE]   {canonical_name}")
        return canonical_name, image.id
    except Exception as exc:  # noqa: BLE001 — keep syncing the remaining images
        print(f"  [ERROR]  {canonical_name}: {exc}", file=sys.stderr)
        return canonical_name, None


def _find_flavor_asset(release):
    """Return (asset_url, asset_name) for GARDENLINUX_FLAVOR in a release, or None."""
    for asset in release["assets"]:
        n = asset["name"]
        if (
            GARDENLINUX_FLAVOR in n
            and "amd64" in n
            and n.endswith(".tar.xz")
            and "logs" not in n
            and "certs" not in n
        ):
            return asset["browser_download_url"], asset["name"]
    return None


def _iter_gardenlinux_releases(max_pages=5, per_page=100):
    for page in range(1, max_pages + 1):
        resp = requests.get(
            f"https://api.github.com/repos/{GARDENLINUX_REPO}/releases",
            headers={"Accept": "application/vnd.github.v3+json"},
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            return
        yield from batch
        if len(batch) < per_page:
            return


def fetch_gardenlinux_release(version=None):
    if version:
        url = (
            f"https://api.github.com/repos/{GARDENLINUX_REPO}"
            f"/releases/tags/{version}"
        )
        resp = requests.get(
            url,
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=30,
        )
        resp.raise_for_status()
        release = resp.json()
        tag = release["tag_name"].lstrip("v")
        asset = _find_flavor_asset(release)
        if not asset:
            raise RuntimeError(
                f"No matching GardenLinux asset for flavor '{GARDENLINUX_FLAVOR}'"
                f" (amd64) in release {tag}.\n"
                f"Set GARDENLINUX_FLAVOR at the top of the script to one of the"
                f" available variants."
            )
        return tag, asset[0], asset[1]

    # GitHub's "latest" release is the most recently *published* one, not the
    # one with the highest version — GardenLinux keeps patching older major
    # versions (e.g. 1877.x) after newer ones (e.g. 2150.x) already exist, so
    # /releases/latest can point at a stale major. Scan all releases instead
    # and pick the highest (major, minor) that has a matching asset.
    best = None
    for release in _iter_gardenlinux_releases():
        if release.get("draft") or release.get("prerelease"):
            continue
        tag = release["tag_name"].lstrip("v")
        parts = tag.split(".")
        if len(parts) < 2 or not all(p.isdigit() for p in parts[:2]):
            continue
        version_key = (int(parts[0]), int(parts[1]))
        if best is not None and version_key <= best[0]:
            continue
        asset = _find_flavor_asset(release)
        if asset:
            best = (version_key, tag, asset)

    if best is None:
        raise RuntimeError(
            f"No GardenLinux release found with a matching asset for flavor"
            f" '{GARDENLINUX_FLAVOR}' (amd64).\n"
            f"Set GARDENLINUX_FLAVOR at the top of the script to one of the"
            f" available variants."
        )
    _, tag, asset = best
    return tag, asset[0], asset[1]


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
    except Exception as exc:  # noqa: BLE001 — keep syncing the remaining images
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
        metavar="X.Y[.Z]",
        default=None,
        help=(
            "Kubernetes version for the CAPI image: a full patch (1.35.4)"
            " or a bare minor (1.35), which is resolved to its current"
            " patch automatically (required unless --skip-capi)"
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
    parser.add_argument(
        "--no-web-download",
        action="store_true",
        help=(
            "Disable the OpenStack 'web-download' image import method and fall"
            " back to downloading the image locally before uploading it."
            " Use this if web-download is disabled on your cloud. Only"
            " affects the CAPI image; GardenLinux images are always"
            " downloaded locally since they ship as tar.xz archives."
        ),
    )
    args = parser.parse_args()

    if args.insecure:
        urllib3.disable_warnings(InsecureRequestWarning)

    print("Connecting to OpenStack ...")
    try:
        conn = openstack.connect(cloud=args.cloud, insecure=args.insecure)
        _ = conn.auth["auth_url"]
    except Exception:  # noqa: BLE001 — turn any connect failure into a CLI error
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
            sync_capi_image(
                conn,
                args.k8s_version,
                args.ubuntu_version,
                args.dry_run,
                web_download=not args.no_web_download,
            )
        )

    if not args.skip_gardenlinux:
        results.append(
            sync_gardenlinux_image(conn, args.gardenlinux_version, args.dry_run)
        )

    print("\n=== Summary ===")
    name_width = max((len(name) for name, _ in results), default=0)
    for name, image_id in results:
        label = image_id if image_id else "— not uploaded (error or dry-run)"
        print(f"  {name:<{name_width}}  {label}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nAborted.")
    except Exception as exc:  # noqa: BLE001 — top-level guard, report and exit cleanly
        sys.exit(f"Error: {exc}")
