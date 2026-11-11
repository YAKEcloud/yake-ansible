#!/usr/bin/env python3
"""
Sync CAPI and GardenLinux images to OpenStack Glance.

Requirements:
  pip install -r requirements.txt

Usage:
  export OS_CLOUD=mycloud   # or use --cloud
  python3 update-images.py --k8s-version 1.35.4
  python3 update-images.py --gardenlinux-version 2150.3.0 --skip-capi
  python3 update-images.py --k8s-version 1.35 --dry-run
"""

import argparse
import hashlib
import re
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

import openstack
import requests
import urllib3
from keystoneauth1.exceptions.connection import ConnectionError as OSConnectionError

CAPI_BASE_URL = "https://nbg1.your-objectstorage.com/osism/openstack-k8s-capi-images"
GARDENLINUX_REPO = "gardenlinux/gardenlinux"
# adjust if you need metal_prod or _usi variant
GARDENLINUX_FLAVOR = "openstack-gardener_prod"
IMAGE_VISIBILITY = "community"
VERSION_RE = re.compile(r"v?\d+\.\d+(\.\d+)?")
UBUNTU_VERSION_RE = re.compile(r"\d{4}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")


def _has_version(text: str, version: str) -> bool:
    """True if `version` appears in `text` as a whole version number, so that
    1.35.1 does not match 1.35.10 and 2150.3 does not match 2150.30."""
    return bool(re.search(rf"(?<![0-9.]){re.escape(version)}(?![0-9]|\.[0-9])", text))


def _short_gl_version(version: str) -> str:
    """'2150.3.0' → '2150.3',  '2150.3' → '2150.3'"""
    parts = version.split(".")
    if len(parts) == 3 and parts[2] == "0":
        return f"{parts[0]}.{parts[1]}"
    return version


def find_capi_image(
    conn: Any, patch_version: str
) -> tuple[Any, str] | tuple[None, None]:
    """
    Look for an existing, active CAPI image using three strategies, in order:
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
    # Only active images count: queued/killed leftovers of failed uploads must
    # not block a new upload.
    hits = list(conn.image.images(name=canonical_name, status="active"))
    if hits:
        return hits[0], f"exact name '{canonical_name}'"

    # 2. Property: kube_version (set by this script) — verify after fetch since
    #    Glance may ignore unknown property filters and return all images
    for img in conn.image.images(kube_version=kube_version, status="active"):
        if img.status == "active" and img.get("kube_version") == kube_version:
            return img, f"kube_version property '{kube_version}'"

    # 3. Fuzzy name scan
    for img in conn.image.images(status="active"):
        name_lower = (img.name or "").lower()
        if (
            img.status == "active"
            and "capi" in name_lower
            and _has_version(name_lower, f"v{patch}")
        ):
            return img, f"fuzzy name match ('capi' + 'v{patch}' in '{img.name}')"

    return None, None


def resolve_capi_series(minor: str) -> tuple[str, str]:
    """Resolve a Kubernetes minor version (e.g. '1.36') to the Ubuntu base
    and current patch it's currently built on, via the series' 'last-X'
    pointer file, which osism updates on every publish. The pointer file's
    path also carries the Ubuntu version (e.g. series v1.37+ moved from
    ubuntu-2404 to ubuntu-2604), so this is the only reliable way to learn
    it — it isn't a function of the Kubernetes version alone.
    Returns (ubuntu_version, patch), e.g. ('2604', '1.37.0').
    """
    url = f"{CAPI_BASE_URL}/last-{minor}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    # format: "YYYY-MM-DD ubuntu-2404-kube-vX.YY/ubuntu-2404-kube-vX.YY.Z.qcow2"
    line = resp.text.strip()
    try:
        path = line.split(maxsplit=1)[1]
        dirname = path.split("/", 1)[0]  # e.g. "ubuntu-2604-kube-v1.37"
        ubuntu_version = dirname.split("-")[1]
        patch = Path(path).stem.rsplit("-v", 1)[-1]
    except (IndexError, ValueError) as exc:
        raise RuntimeError(f"Could not parse pointer file '{url}': {line!r}") from exc
    if not UBUNTU_VERSION_RE.fullmatch(ubuntu_version) or not re.fullmatch(
        r"\d+\.\d+\.\d+", patch
    ):
        raise RuntimeError(f"Unexpected content in pointer file '{url}': {line!r}")
    return ubuntu_version, patch


def find_gardenlinux_image(
    conn: Any, version: str
) -> tuple[Any, str] | tuple[None, None]:
    """
    Look for an existing, active GardenLinux image using three strategies:
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
    hits = list(conn.image.images(name=canonical_name, status="active"))
    if hits:
        return hits[0], f"exact name '{canonical_name}'"

    # 2. Property: os_version (set by this script) — verify after fetch since
    #    Glance may ignore unknown property filters and return all images
    for v in (version, short):
        for img in conn.image.images(
            os_distro="gardenlinux", os_version=v, status="active"
        ):
            if (
                img.status == "active"
                and img.get("os_distro") == "gardenlinux"
                and img.get("os_version") in (version, short)
            ):
                return img, f"os_version property '{v}'"

    # 3. Fuzzy name scan
    gl_keywords = ("gardenlinux", "garden linux", "garden-linux")
    for img in conn.image.images(status="active"):
        name_lower = (img.name or "").lower()
        if (
            img.status == "active"
            and any(kw in name_lower for kw in gl_keywords)
            and (_has_version(name_lower, short) or _has_version(name_lower, version))
        ):
            return img, f"fuzzy name match (gardenlinux + version in '{img.name}')"

    return None, None


def _get_image_resilient(conn: Any, image_id: str, max_retries: int = 5) -> Any:
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


def _wait_for_active(
    conn: Any, image_id: str, timeout: int = 3600, poll_interval: int = 15
) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        img = _get_image_resilient(conn, image_id)
        if img.status == "active":
            return img
        if img.status in ("killed", "deleted"):
            raise RuntimeError(f"Image {image_id} ended up in status '{img.status}'")
        time.sleep(poll_interval)
    raise TimeoutError(f"Image {image_id} did not become active within {timeout}s")


def _human_size(num_bytes: int | None) -> str:
    if not num_bytes:
        return "unknown size"
    size = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def _get_content_length(url: str) -> int | None:
    """Best-effort HEAD request to learn the source file size upfront."""
    try:
        resp = requests.head(url, timeout=30, allow_redirects=True)
        resp.raise_for_status()
        length = resp.headers.get("content-length")
        return int(length) if length else None
    except requests.RequestException:
        return None


def _wait_for_import(
    conn: Any,
    image_id: str,
    total_size: int | None = None,
    timeout: int = 3600,
    poll_interval: int = 10,
    all_stores: bool = False,
) -> Any:
    expected_stores = {s.id for s in conn.image.stores()} if all_stores else set()
    start = time.monotonic()
    deadline = start + timeout
    last_status = None
    while time.monotonic() < deadline:
        img = _get_image_resilient(conn, image_id)
        elapsed = int(time.monotonic() - start)
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
            # NOTE: The importing property is not populated right away, so
            #       also wait until the image is present in all stores.
            image_stores = set(
                img.properties.get("stores", "").replace(",", " ").split()
            )
            importing_to_stores = (
                img.properties.get("os_glance_importing_to_stores", "")
                .replace(",", " ")
                .split()
            ) or sorted(expected_stores - image_stores)
            failed_import = (
                img.properties.get("os_glance_failed_import", "")
                .replace(",", " ")
                .split()
            )
            if len(failed_import) > 0:
                raise RuntimeError(
                    f"Failed to copy image {image_id} into all stores. Failed store(s):"
                    f" '{', '.join(failed_import)}'"
                )
            elif len(importing_to_stores) > 0:
                print(
                    f"      still copying image into store(s):"
                    f" {', '.join(importing_to_stores)}..."
                    f"  (elapsed: {elapsed}s){progress}"
                )
            else:
                return img
        elif img.status in ("killed", "deleted"):
            raise RuntimeError(
                f"Image {image_id} ended up in status '{img.status}' during import"
            )
        time.sleep(poll_interval)
    raise TimeoutError(f"Image {image_id} did not become active within {timeout}s")


def _delete_image_quietly(conn: Any, image: Any) -> None:
    """Remove the record of a failed upload so it cannot block the next run."""
    try:
        conn.image.delete_image(image, ignore_missing=True)
    except Exception as exc:
        print(f"      could not delete failed image {image.id}: {exc}", file=sys.stderr)


def upload_via_web_download(
    conn: Any,
    name: str,
    url: str,
    disk_format: str = "qcow2",
    extra_props: dict[str, str] | None = None,
    all_stores: bool = False,
) -> Any:
    """Create an image record and let OpenStack download the data itself.

    Requires the 'web-download' import method to be enabled on the cloud
    (most public/managed OpenStack clouds support it). Use --no-web-download
    to fall back to downloading locally and streaming the upload instead.
    The data is fetched by Glance, so it is not checksum-verified here.
    """
    image = conn.image.create_image(
        name=name,
        disk_format=disk_format,
        container_format="bare",
        visibility=IMAGE_VISIBILITY,
        min_disk=20,
        min_ram=512,
        **(extra_props or {}),
    )
    try:
        total_size = _get_content_length(url)
        print(f"    → requesting web-download import from {url}")
        print(f"    → source size: {_human_size(total_size)}")
        kwargs: dict[str, bool] = {}
        if all_stores:
            kwargs.update({"all_stores": True, "all_stores_must_succeed": True})
        conn.image.import_image(image, method="web-download", uri=url, **kwargs)
        return _wait_for_import(
            conn, image.id, total_size=total_size, all_stores=all_stores
        )
    except BaseException:
        _delete_image_quietly(conn, image)
        raise


class _Progress:
    """Prints a progress line at most every `interval` seconds."""

    def __init__(self, label: str, total: int | None, interval: int = 10) -> None:
        self._label = label
        self._total = total
        self._interval = interval
        self._done = 0
        self._next = time.monotonic() + interval

    def update(self, n: int) -> None:
        self._done += n
        if time.monotonic() >= self._next:
            self._next = time.monotonic() + self._interval
            pct = f" ({self._done * 100 // self._total}%)" if self._total else ""
            print(
                f"    {self._label}: {_human_size(self._done)}"
                f" / {_human_size(self._total)}{pct}",
                flush=True,
            )


class _ProgressReader:
    """Wraps a file object and reports progress as data is read."""

    def __init__(self, fh: Any, progress: _Progress) -> None:
        self._fh = fh
        self._progress = progress

    def read(self, size: int = -1) -> bytes:
        data = self._fh.read(size)
        self._progress.update(len(data))
        return data


def upload_from_file(
    conn: Any,
    name: str,
    path: Path,
    disk_format: str = "qcow2",
    extra_props: dict[str, str] | None = None,
    all_stores: bool = False,
) -> Any:
    progress = _Progress(f"↑ {name}", path.stat().st_size)
    image = None
    with open(path, "rb") as fh:
        try:
            image = conn.image.create_image(
                name=name,
                disk_format=disk_format,
                container_format="bare",
                visibility=IMAGE_VISIBILITY,
                min_disk=20,
                min_ram=512,
                **(extra_props or {}),
                data=_ProgressReader(fh, progress) if not all_stores else None,
            )
            if not all_stores:
                return _wait_for_active(conn, image.id)
            conn.image.stage_image(image, data=_ProgressReader(fh, progress))
            conn.image.import_image(
                image,
                method="glance-direct",
                all_stores=True,
                all_stores_must_succeed=True,
            ).raise_for_status()
            return _wait_for_import(conn, image.id, all_stores=True)
        except BaseException:
            print(f"      failure uploading image data for '{name}'", file=sys.stderr)
            if image is not None:
                _delete_image_quietly(conn, image)
            raise


def download_file(url: str, dest: Path, label: str = "") -> str:
    """Stream `url` to `dest` and return the SHA-256 hex digest of the data."""
    label = label or Path(url).name
    digest = hashlib.sha256()
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0)) or None
        progress = _Progress(f"↓ {label}", total)
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                fh.write(chunk)
                digest.update(chunk)
                progress.update(len(chunk))
    return digest.hexdigest()


def verify_checksum(label: str, actual: str, expected: str) -> None:
    if actual != expected:
        raise RuntimeError(
            f"SHA-256 mismatch for {label}: expected {expected}, got {actual}"
        )
    print(f"    → SHA-256 verified: {actual}")


def fetch_capi_checksum(url: str) -> str | None:
    """SHA-256 from the '<file>.CHECKSUM' file osism publishes next to each image
    (sha256sum format), or None if there is none."""
    resp = requests.get(f"{url}.CHECKSUM", timeout=30)
    if resp.status_code == requests.codes.not_found:
        return None
    resp.raise_for_status()
    token = resp.text.split(maxsplit=1)[0].lower() if resp.text.strip() else ""
    if not SHA256_RE.fullmatch(token):
        raise RuntimeError(f"Unexpected checksum file format at {url}.CHECKSUM")
    return token


def ensure_all_stores(conn: Any, image: Any, dry_run: bool = False) -> Any:
    # NOTE: Split on whitespace so we get an empty list from an empty string instead of
    #       a list with an empty string element. Store names do not contain whitespace.
    image_stores = set(image.properties.get("stores", "").replace(",", " ").split())
    stores = {store.id for store in conn.image.stores()}
    if not stores <= image_stores:
        if image.owner != conn.current_project_id:
            print(
                f"  [WARN]   existing image {image.id} is owned by another project"
                " and cannot be copied into all stores by us. Ask the owner to do"
                " so or re-upload the image into our project."
            )
            return image
        if not dry_run:
            print(f"  — copying existing image {image.id} into all stores")
            try:
                conn.image.import_image(
                    image,
                    method="copy-image",
                    all_stores=True,
                ).raise_for_status()
            except requests.exceptions.HTTPError as exc:
                print(f"  — failure copying image {image.id} into all stores.")
                if (
                    exc.response is not None
                    and exc.response.status_code == requests.codes.forbidden
                ):
                    print(
                        "  — import method 'copy-image' into all stores forbidden. Try"
                        " re-uploading into all stores directly or omit '--all-stores'"
                        " to skip this step entirely."
                    )
                raise

            return _wait_for_import(conn, image.id, all_stores=True)
        else:
            print(f"  [DRY-RUN] would copy existing image {image.id} into all stores")
    return image


def sync_capi_image(
    conn: Any,
    k8s_version: str,
    ubuntu_version: str | None = None,
    dry_run: bool = False,
    web_download: bool = True,
    all_stores: bool = False,
) -> tuple[str, str | None]:
    print("\n=== CAPI Image ===")

    version = k8s_version.lstrip("v")
    bare_minor = version.count(".") < 2
    minor = version if bare_minor else ".".join(version.split(".")[:2])

    resolved_patch = ""
    if ubuntu_version is None or bare_minor:
        # The Ubuntu base isn't a function of the Kubernetes version alone
        # (e.g. v1.37+ moved from ubuntu-2404 to ubuntu-2604) — the 'last-X'
        # pointer file is the only reliable source for it. Also needed here
        # to resolve a bare minor to its current patch, for naming/dedup.
        print(f"  Resolving current build for series v{minor} ...")
        resolved_ubuntu_version, resolved_patch = resolve_capi_series(minor)
        if ubuntu_version is None:
            ubuntu_version = resolved_ubuntu_version
        print(f"  Resolved: v{minor} → ubuntu-{ubuntu_version}, v{resolved_patch}")

    if bare_minor:
        # Still download the series file — it's rebuilt (and overwritten) on
        # every publish, including image-only fixes that don't bump the
        # patch, so it's the only URL that's guaranteed to be current. The
        # create-once per-patch file can lag behind it.
        patch = resolved_patch
        filename = f"ubuntu-{ubuntu_version}-kube-v{minor}.qcow2"
    else:
        # Exact patch requested: fetch that immutable, create-once file.
        patch = version
        filename = f"ubuntu-{ubuntu_version}-kube-v{patch}.qcow2"

    canonical_name = f"ubuntu-capi-image-v{patch}"
    url = f"{CAPI_BASE_URL}/ubuntu-{ubuntu_version}-kube-v{minor}/{filename}"

    existing, strategy = find_capi_image(conn, patch)
    if existing:
        print(f"  [SKIP]   {canonical_name}  — found via {strategy}  ({existing.id})")
        if all_stores:
            existing = ensure_all_stores(conn, existing, dry_run=dry_run)
        return canonical_name, existing.id

    if dry_run:
        if web_download:
            method = "web-download import"
        elif all_stores:
            method = "download, upload and import"
        else:
            method = "download and upload"

        stores = "all available image stores" if all_stores else "default image store"
        print(f"  [DRY-RUN] would {method} {canonical_name}  from {url} into {stores}")
        return canonical_name, None

    extra_props = {
        "os_purpose": "k8snode",
        "os_distro": "ubuntu",
        "kube_version": f"v{patch}",
        "image_description": "https://github.com/osism/k8s-capi-images",
        "image_source": url,
    }

    print(
        f"  [UPLOAD] {canonical_name}" + ("" if web_download else " (local download)")
    )
    try:
        if web_download:
            image = upload_via_web_download(
                conn,
                canonical_name,
                url,
                extra_props=extra_props,
                all_stores=all_stores,
            )
        else:
            with tempfile.TemporaryDirectory() as tmp:
                local = Path(tmp) / f"{canonical_name}.qcow2"
                expected = fetch_capi_checksum(url)
                actual = download_file(url, local, canonical_name)
                if expected:
                    verify_checksum(local.name, actual, expected)
                else:
                    print(f"    [WARN] no published checksum for {url}, not verified")
                image = upload_from_file(
                    conn,
                    canonical_name,
                    local,
                    extra_props=extra_props,
                    all_stores=all_stores,
                )
        print(f"  [DONE]   {canonical_name}")
        return canonical_name, image.id
    except Exception as exc:  # keep syncing the remaining images
        print(f"  [ERROR]  {canonical_name}: {exc}", file=sys.stderr)
        return canonical_name, None


def _find_flavor_asset(release: dict[str, Any]) -> tuple[str, str, str | None] | None:
    """Return (asset_url, asset_name, sha256) for GARDENLINUX_FLAVOR in a release,
    or None. sha256 is the digest GitHub records for the asset, if any."""
    for asset in release["assets"]:
        n = asset["name"]
        if (
            GARDENLINUX_FLAVOR in n
            and "amd64" in n
            and n.endswith(".tar.xz")
            and "logs" not in n
            and "certs" not in n
        ):
            digest = (asset.get("digest") or "").removeprefix("sha256:").lower()
            return (
                asset["browser_download_url"],
                asset["name"],
                digest if SHA256_RE.fullmatch(digest) else None,
            )
    return None


def _iter_gardenlinux_releases(max_pages: int = 5, per_page: int = 100):
    for page in range(1, max_pages + 1):
        resp = requests.get(
            f"https://api.github.com/repos/{GARDENLINUX_REPO}/releases",
            headers={"Accept": "application/vnd.github+json"},
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


def fetch_gardenlinux_release(
    version: str | None = None,
) -> tuple[str, str, str, str | None]:
    if version:
        url = (
            f"https://api.github.com/repos/{GARDENLINUX_REPO}"
            f"/releases/tags/{version}"
        )
        resp = requests.get(
            url,
            headers={"Accept": "application/vnd.github+json"},
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
        return tag, *asset

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
    return tag, *asset


def extract_image(archive_path: Path, dest_dir: str | Path) -> Path:
    """Return path to the first .raw or .qcow2 inside a tar.xz."""
    with tarfile.open(archive_path, "r:xz") as tar:
        for member in tar:  # streaming: the archive is decompressed only once
            if member.isfile() and member.name.endswith((".raw", ".qcow2")):
                member.name = Path(member.name).name
                tar.extract(member, path=dest_dir, filter="data")
                return Path(dest_dir) / member.name
    raise RuntimeError(f"No .raw or .qcow2 image found inside {archive_path.name}")


def sync_gardenlinux_image(
    conn: Any,
    version: str | None = None,
    dry_run: bool = False,
    all_stores: bool = False,
) -> tuple[str, str | None]:
    print("\n=== GardenLinux Images ===")

    tag, asset_url, asset_name, asset_sha256 = fetch_gardenlinux_release(version)
    short = _short_gl_version(tag)
    canonical_name = f"Garden Linux {short}"
    print(f"  Release: {tag}  →  Glance name: '{canonical_name}'")

    existing, strategy = find_gardenlinux_image(conn, tag)
    if existing:
        print(
            f"  [SKIP]   '{canonical_name}'"
            f"  — found via {strategy}  ({existing.id})"
        )
        if all_stores:
            existing = ensure_all_stores(conn, existing, dry_run=dry_run)
        return canonical_name, existing.id

    if dry_run:
        if all_stores:
            method = "download, upload and import"
        else:
            method = "download and upload"
        print(f"  [DRY-RUN] would {method} '{canonical_name}' from {asset_url}")
        return canonical_name, None

    print(f"  [UPLOAD] {canonical_name}")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / asset_name
            actual = download_file(asset_url, archive, asset_name)
            if asset_sha256:
                verify_checksum(asset_name, actual, asset_sha256)
            else:
                print(
                    f"    [WARN] no published checksum for {asset_name}, not verified"
                )

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
                all_stores=all_stores,
            )
        print(f"  [DONE]   {canonical_name}")
        return canonical_name, image.id
    except Exception as exc:  # keep syncing the remaining images
        print(f"  [ERROR]  {canonical_name}: {exc}", file=sys.stderr)
        return canonical_name, None


def main() -> None:
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
        default=None,
        metavar="YYYYMM",
        help=(
            "Override the Ubuntu base for the CAPI image (e.g. 2604)."
            " Default: auto-detected per series from the 'last-X' pointer"
            " file, since it changes between series (e.g. v1.37+ moved"
            " from 2404 to 2604)."
        ),
    )
    parser.add_argument(
        "--gardenlinux-version",
        default=None,
        metavar="VERSION",
        help="Pin a specific GardenLinux version (default: latest release)",
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
        help="Check what would be uploaded without actually uploading anything",
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
    parser.add_argument(
        "--ids-file",
        metavar="FILE",
        default=None,
        help=(
            "Write the IDs of the selected images to FILE as 'capi=<id>' and"
            " 'gardenlinux=<id>' lines. This is the image the script found (it"
            " may have a different name) or uploaded."
        ),
    )
    parser.add_argument(
        "--all-stores",
        action="store_true",
        help=(
            "Import image into all available glance stores."
            " This requires interoperable image import using either `glance-direct` or"
            " `web-download` method, depending on the '--no-web-download' parameter."
            " Existing images are copied using the `copy-image` method, which is"
            " only permitted for images owned by our project."
            " This requires the import into all stores to succeed."
        ),
    )
    args = parser.parse_args()

    # Validate before connecting: the values end up in URLs and image names.
    if not args.skip_capi and not args.k8s_version:
        parser.error("--k8s-version is required unless --skip-capi is set")
    if args.k8s_version and not VERSION_RE.fullmatch(args.k8s_version):
        parser.error("--k8s-version must look like 1.35, 1.35.4 or v1.35.4")
    if args.ubuntu_version and not UBUNTU_VERSION_RE.fullmatch(args.ubuntu_version):
        parser.error("--ubuntu-version must look like 2404")
    if args.gardenlinux_version and not VERSION_RE.fullmatch(args.gardenlinux_version):
        parser.error("--gardenlinux-version must look like 2150.3 or 2150.3.0")
    if args.gardenlinux_version:
        args.gardenlinux_version = args.gardenlinux_version.lstrip("v")

    if args.insecure:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    print("Connecting to OpenStack ...")
    try:
        conn = openstack.connect(cloud=args.cloud, insecure=args.insecure)
        conn.authorize()
    except Exception as exc:
        sys.exit(
            f"Could not connect to OpenStack ({exc})."
            " Set OS_CLOUD or pass --cloud <name>."
        )
    print(f"Connected: {conn.config.get_auth_args().get('auth_url', 'unknown')}")

    if args.dry_run:
        print("Dry-run mode — no images will be uploaded.")

    try:
        import_info = conn.image.get_import_info()
        import_methods = import_info.import_methods.get("value", [])
    except Exception as exc:  # pre-flight check is best effort
        import_methods = None
        print(f"Could not query supported import methods ({exc}), skipping check.")

    if import_methods is not None:
        required_methods = set()
        if not args.skip_capi and not args.no_web_download:
            required_methods.add("web-download")
        if args.all_stores:
            required_methods.add("copy-image")
            if (not args.skip_capi and args.no_web_download) or (
                not args.skip_gardenlinux
            ):
                required_methods.add("glance-direct")
        missing_methods = required_methods - set(import_methods)
        if missing_methods:
            raise RuntimeError(
                "Required import method(s) not supported by the cloud:"
                f" {', '.join(sorted(missing_methods))}"
            )

    results = []
    ids = {}

    if not args.skip_capi:
        results.append(
            sync_capi_image(
                conn,
                args.k8s_version,
                args.ubuntu_version,
                args.dry_run,
                web_download=not args.no_web_download,
                all_stores=args.all_stores,
            )
        )
        ids["capi"] = results[-1][1]

    if not args.skip_gardenlinux:
        results.append(
            sync_gardenlinux_image(
                conn,
                args.gardenlinux_version,
                args.dry_run,
                all_stores=args.all_stores,
            )
        )
        ids["gardenlinux"] = results[-1][1]

    if args.ids_file:
        with open(args.ids_file, "w", encoding="utf-8") as fh:
            for key, image_id in ids.items():
                if image_id:
                    fh.write(f"{key}={image_id}\n")

    print("\n=== Summary ===")
    name_width = max((len(name) for name, _ in results), default=0)
    for name, image_id in results:
        label = image_id if image_id else "— not uploaded (error or dry-run)"
        print(f"  {name:<{name_width}}  {label}")

    if not args.dry_run and any(image_id is None for _, image_id in results):
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nAborted.")
    except Exception as exc:  # top-level guard, report and exit cleanly
        sys.exit(f"Error: {exc}")
