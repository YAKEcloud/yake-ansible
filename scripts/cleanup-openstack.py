#!/usr/bin/env python3
"""
Delete only the OpenStack resources belonging to a yake-ansible cluster/seed,
identified by the exact names/ownership the upstream components give them
(never "delete everything except X"), and only inside the current project.

Requirements:
  pip install -r requirements.txt

Usage:
  export OS_CLOUD=mycloud   # or use --cloud
  python3 scripts/cleanup-openstack.py --garden-url botany.yake.cloud
  python3 scripts/cleanup-openstack.py --seed-names managed-seed-a --dry-run

Exit code: 0 on success, 1 if any resource could not be deleted (all other
resources are still processed), 2 on usage/connection errors.
"""

import argparse
import re
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

import openstack

# Namespace of the CAPO Cluster object (roles/clusterapi_cluster/tasks/create.yml).
# CAPO names its resources "<prefix>-cluster-<namespace>-<cluster name>".
CAPO_NAMESPACE = "default"
# openstack-cloud-controller-manager and cinder-csi of the garden cluster run
# with the literal cluster name "kubernetes" (CLUSTER_NAME env in
# roles/clusterapi_cluster/files/{cloud-controller-manager,cinder-csi}), so its
# LBs are called kube_service_kubernetes_<ns>_<svc> and its PVC volumes carry
# the metadata cinder.csi.openstack.org/cluster=kubernetes. That name is shared
# with every other cluster using the defaults, so it is only ever combined with
# an ownership check (network, attachment).
CCM_CLUSTER_NAME = "kubernetes"
CSI_CLUSTER_KEY = "cinder.csi.openstack.org/cluster"
# Auto-managed by Neutron (deleted together with the subnet/network/router).
ROUTER_PORT_OWNERS = {
    "network:router_interface",
    "network:router_interface_distributed",
    "network:ha_router_replicated_interface",
}

SERVER_DELETE_TIMEOUT = 600
VOLUME_DETACH_TIMEOUT = 300
LOADBALANCER_DELETE_TIMEOUT = 600
POLL_INTERVAL = 5

OwnerKind = Literal["capo", "shoot"]


@dataclass(frozen=True)
class Owner:
    """A CAPO cluster ("capo") or a Gardener shoot technical ID ("shoot")."""

    name: str
    kind: OwnerKind

    @property
    def _capo_base(self) -> str:
        return f"{CAPO_NAMESPACE}-{self.name}"

    @property
    def network_name(self) -> str:
        """Name of the managed network, subnet and router."""
        if self.kind == "capo":
            return f"k8s-clusterapi-cluster-{self._capo_base}"
        return self.name

    @property
    def keypair_name(self) -> str:
        return self.name

    @property
    def server_group_names(self) -> set[str]:
        if self.kind == "capo":
            return {f"{self.name}-control-plane", f"{self.name}-worker"}
        return set()

    @property
    def capo_description(self) -> str | None:
        """Description CAPO sets on its floating IPs (pkg/utils/names)."""
        if self.kind == "capo":
            return (
                f"Created by cluster-api-provider-openstack cluster {self._capo_base}"
            )
        return None

    @property
    def apiserver_lb_name(self) -> str | None:
        if self.kind == "capo":
            return f"k8s-clusterapi-cluster-{self._capo_base}-kubeapi"
        return None

    def matches_security_group(self, name: str | None) -> bool:
        if self.kind == "capo":
            base = re.escape(self._capo_base)
            return bool(
                re.fullmatch(
                    rf"k8s-cluster-{base}-secgroup-(controlplane|worker|bastion)",
                    name or "",
                )
            )
        return name == self.name

    def matches_server(self, name: str | None) -> bool:
        """Machine names: CAPI/CAPO and Gardener machine-controller-manager."""
        n = re.escape(self.name)
        if self.kind == "capo":
            pattern = (
                rf"{n}-control-plane-[a-z0-9]{{5}}"
                rf"|{n}-[a-z0-9]+(-[a-z0-9]+)*-[a-z0-9]{{4,10}}-[a-z0-9]{{5}}"
            )
        else:
            pattern = rf"{n}-[a-z0-9]+(-[a-z0-9]+)*-z\d+-[a-z0-9]+-[a-z0-9]+"
        return bool(re.fullmatch(pattern, name or ""))

    def is_own_ccm_lb(
        self, lb: Any, network_ids: set[str], subnet_ids: set[str]
    ) -> bool:
        """LB created by the cloud-controller-manager for a Service."""
        name = lb.name or ""
        if self.kind == "shoot":
            # Gardener runs the CCM with --cluster-name=<technical id>.
            return name.startswith(f"kube_service_{self.name}_")
        return name.startswith(f"kube_service_{CCM_CLUSTER_NAME}_") and (
            lb.vip_network_id in network_ids or lb.vip_subnet_id in subnet_ids
        )


def build_owners(
    cluster_name: str, seeds_project: str, seed_names: list[str]
) -> list[Owner]:
    return [Owner(cluster_name, "capo")] + [
        Owner(f"shoot--{seeds_project}--{s}", "shoot") for s in seed_names
    ]


def server_on_own_network(server: Any, network_names: set[str]) -> bool:
    """Disambiguates machine names that differ only in the owner's prefix
    (e.g. cluster "garden" vs "garden-prod"): a server that has addresses must
    be attached to one of the owner's networks. Servers without addresses
    (e.g. in ERROR) can only be matched by name."""
    addresses = getattr(server, "addresses", None) or {}
    return not addresses or bool(set(addresses) & network_names)


def report(
    dry_run: bool,
    kind: str,
    items: Iterable[Any],
    label: Callable[[Any], Any] = lambda i: i.name or i.id,
) -> None:
    verb = "Would delete" if dry_run else "Deleting"
    for item in items:
        print(f"  [{kind}] {verb}: {label(item)} ({item.id})")


def gather(conn: Any, owners: list[Owner]) -> dict[str, list[Any]]:
    """Read-only: identify every resource this run owns. Never deletes anything.

    Neutron and Octavia return resources of all projects to admin credentials,
    so their listings are scoped to the current project. Nova and Cinder list
    the project of the token only.
    """
    print("Gathering resources ...")
    scope = {"project_id": conn.current_project_id}

    networks = [
        n
        for n in conn.network.networks(**scope)
        if any(n.name == o.network_name for o in owners)
    ]
    network_ids = {n.id for n in networks}
    network_names = {n.name for n in networks}
    subnets = [s for s in conn.network.subnets(**scope) if s.network_id in network_ids]
    subnet_ids = {s.id for s in subnets}

    servers = [
        s
        for s in conn.compute.servers(details=True)
        if any(o.matches_server(s.name) for o in owners)
        and server_on_own_network(s, network_names)
    ]
    server_ids = {s.id for s in servers}

    gardener_ids = {o.name for o in owners if o.kind == "shoot"}
    volumes = []
    skipped_volumes = []
    # Cinder rejects project_id as a filter (400). Without all_projects it lists
    # the project of the token only, which is the scope we want.
    for v in conn.block_storage.volumes():
        attached = {a.get("server_id") for a in (v.attachments or [])}
        cluster = (v.metadata or {}).get(CSI_CLUSTER_KEY)
        if attached & server_ids or cluster in gardener_ids:
            volumes.append(v)
        elif cluster == CCM_CLUSTER_NAME:
            skipped_volumes.append(v)
    for v in skipped_volumes:
        print(
            f"  [volume] Skipping (cluster '{CCM_CLUSTER_NAME}' is not unique, not"
            f" attached to an own server): {v.name or v.id} ({v.id})"
        )

    keypairs = [
        k
        for k in conn.compute.keypairs()
        if any(k.name == o.keypair_name for o in owners)
    ]
    server_groups = [
        g
        for g in conn.compute.server_groups()
        if any(g.name in o.server_group_names for o in owners)
    ]
    security_groups = [
        g
        for g in conn.network.security_groups(**scope)
        if any(o.matches_security_group(g.name) for o in owners)
    ]
    routers = [
        r
        for r in conn.network.routers(**scope)
        if any(r.name == o.network_name for o in owners)
    ]
    router_ids = {r.id for r in routers}

    apiserver_lbs = {o.apiserver_lb_name for o in owners if o.apiserver_lb_name}
    loadbalancers = [
        lb
        for lb in conn.load_balancer.load_balancers(**scope)
        if lb.name in apiserver_lbs
        or any(o.is_own_ccm_lb(lb, network_ids, subnet_ids) for o in owners)
    ]

    all_ports = list(conn.network.ports(**scope))
    # Router interfaces/DHCP/gateway ports are managed by Neutron itself.
    own_ports = [
        p
        for p in all_ports
        if p.network_id in network_ids
        and not (p.device_owner or "").startswith("network:")
    ]
    router_interface_ports = [
        p
        for p in all_ports
        if p.device_owner in ROUTER_PORT_OWNERS and p.device_id in router_ids
    ]
    own_port_ids = {p.id for p in all_ports if p.network_id in network_ids} | {
        p.id for p in router_interface_ports
    }
    # Attached to an own port, or created by CAPO for this cluster. The latter
    # also catches IPs that are no longer attached (e.g. after a LB was gone).
    capo_descriptions = {o.capo_description for o in owners} - {None}
    floating_ips = [
        f
        for f in conn.network.ips(**scope)
        if f.port_id in own_port_ids or f.description in capo_descriptions
    ]

    return {
        "servers": servers,
        "volumes": volumes,
        "keypairs": keypairs,
        "server_groups": server_groups,
        "security_groups": security_groups,
        "networks": networks,
        "subnets": subnets,
        "routers": routers,
        "router_interface_ports": router_interface_ports,
        "loadbalancers": loadbalancers,
        "ports": own_ports,
        "floating_ips": floating_ips,
    }


class Cleaner:
    """Deletes resources one by one and collects failures instead of aborting."""

    def __init__(self, conn: Any, dry_run: bool) -> None:
        self.conn = conn
        self.dry_run = dry_run
        self.errors: list[str] = []

    def run(
        self,
        kind: str,
        items: list[Any],
        delete: Callable[[Any], Any],
        label: Callable[[Any], Any] = lambda i: i.name or i.id,
    ) -> None:
        report(self.dry_run, kind, items, label)
        if self.dry_run:
            return
        for item in items:
            try:
                delete(item)
            except Exception as exc:
                msg = f"[{kind}] {label(item)} ({item.id}): {exc}"
                print(f"  ERROR {msg}", file=sys.stderr)
                self.errors.append(msg)

    def delete_server(self, server: Any) -> None:
        self.conn.compute.delete_server(server, ignore_missing=True)

    def wait_server(self, server: Any) -> None:
        self.conn.compute.wait_for_delete(server, wait=SERVER_DELETE_TIMEOUT)

    def delete_volume(self, volume: Any) -> None:
        """Wait until the volume is detached (its server was just deleted).

        Root volumes with delete_on_termination are gone with their server.
        """
        deadline = time.monotonic() + VOLUME_DETACH_TIMEOUT
        while True:
            try:
                current = self.conn.block_storage.get_volume(volume.id)
            except openstack.exceptions.NotFoundException:
                return
            if current.status not in ("in-use", "attaching", "detaching"):
                break
            if time.monotonic() > deadline:
                raise TimeoutError(f"still '{current.status}' after detach timeout")
            time.sleep(POLL_INTERVAL)
        self.conn.block_storage.delete_volume(volume, ignore_missing=True)

    def delete_loadbalancer(self, lb: Any) -> None:
        self.conn.load_balancer.delete_load_balancer(
            lb, ignore_missing=True, cascade=True
        )
        self.conn.load_balancer.wait_for_delete(lb, wait=LOADBALANCER_DELETE_TIMEOUT)

    def remove_router_interface(self, port: Any) -> None:
        self.conn.network.remove_interface_from_router(
            port.device_id, subnet_id=port.fixed_ips[0]["subnet_id"]
        )


def cleanup(conn: Any, owned: dict[str, list[Any]], dry_run: bool) -> list[str]:
    c = Cleaner(conn, dry_run)

    c.run("server", owned["servers"], c.delete_server)
    if not dry_run:
        # Volumes, ports and networks can only go once the servers are gone.
        for s in owned["servers"]:
            try:
                c.wait_server(s)
            except Exception as exc:
                msg = f"[server] wait for {s.name} ({s.id}): {exc}"
                print(f"  ERROR {msg}", file=sys.stderr)
                c.errors.append(msg)

    c.run(
        "floating-ip",
        owned["floating_ips"],
        lambda f: conn.network.delete_ip(f, ignore_missing=True),
        label=lambda i: i.floating_ip_address,
    )
    c.run("loadbalancer", owned["loadbalancers"], c.delete_loadbalancer)
    c.run("volume", owned["volumes"], c.delete_volume)
    c.run(
        "router-interface",
        owned["router_interface_ports"],
        c.remove_router_interface,
        label=lambda i: i.device_id,
    )
    c.run(
        "router",
        owned["routers"],
        lambda r: conn.network.delete_router(r, ignore_missing=True),
    )
    c.run(
        "port",
        owned["ports"],
        lambda p: conn.network.delete_port(p, ignore_missing=True),
    )
    c.run(
        "subnet",
        owned["subnets"],
        lambda s: conn.network.delete_subnet(s, ignore_missing=True),
    )
    c.run(
        "network",
        owned["networks"],
        lambda n: conn.network.delete_network(n, ignore_missing=True),
    )
    c.run(
        "security-group",
        owned["security_groups"],
        lambda g: conn.network.delete_security_group(g, ignore_missing=True),
    )
    c.run(
        "keypair",
        owned["keypairs"],
        lambda k: conn.compute.delete_keypair(k, ignore_missing=True),
    )
    c.run(
        "server-group",
        owned["server_groups"],
        lambda g: conn.compute.delete_server_group(g, ignore_missing=True),
    )
    return c.errors


def cleanup_dns(
    conn: Any, garden_url: str, preserve_types: list[str], dry_run: bool
) -> list[str]:
    """Delete all record sets of the garden URL zone except the preserved types.

    The zone is the deployment's own domain: Gardener creates records for the
    garden, the seeds and every shoot in it (plus ownership TXT records) under
    names that depend on project/shoot names, so they cannot be enumerated.
    Do not point --garden-url at a zone that holds unrelated records.
    """
    zone = f"{garden_url}."
    zones = [z for z in conn.dns.zones() if z.name == zone]
    if not zones:
        print(f"No DNS zone '{zone}' found, skipping.")
        return []
    recordsets = [
        r for z in zones for r in conn.dns.recordsets(z) if r.type not in preserve_types
    ]
    c = Cleaner(conn, dry_run)
    c.run(
        "dns-recordset",
        recordsets,
        lambda r: conn.dns.delete_recordset(r, ignore_missing=True),
        label=lambda i: f"{i.name} ({i.type})",
    )
    return c.errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--cloud",
        default=None,
        help="Cloud name from clouds.yaml (default: OS_CLOUD env var)",
    )
    parser.add_argument(
        "--cluster-name",
        default="garden",
        help="clusterapi_cluster_name (default: garden)",
    )
    parser.add_argument(
        "--seed-names",
        default="",
        metavar="NAME[,NAME...]",
        help="Comma-separated gardener_operator_managed_seeds[].name values",
    )
    parser.add_argument(
        "--seeds-project",
        default="seeds",
        help="gardener_operator_managed_seeds_project.name (default: seeds)",
    )
    parser.add_argument(
        "--garden-url",
        default=None,
        help="gardener_operator_garden_url, to clean up its DNS zone",
    )
    parser.add_argument(
        "--preserve-dns-type",
        action="append",
        default=None,
        metavar="TYPE",
        help="DNS record type to keep (default: SOA, NS); repeat for multiple",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be deleted without deleting anything",
    )
    parser.add_argument(
        "--insecure", action="store_true", help="Disable TLS certificate verification"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    print("Connecting to OpenStack ...")
    try:
        conn = openstack.connect(cloud=args.cloud, insecure=args.insecure)
        conn.authorize()
    except Exception as exc:
        print(
            f"Could not authenticate to OpenStack: {exc}\n"
            "Set OS_CLOUD or pass --cloud <name>.",
            file=sys.stderr,
        )
        return 2
    auth_url = conn.config.get_auth_args().get("auth_url", "unknown")
    project = conn.current_project
    print(f"Connected: {auth_url}")
    print(f"Project:   {project.name or 'unnamed'} ({conn.current_project_id})")

    if args.dry_run:
        print("Dry-run mode, nothing will be deleted.")

    seed_names = [s for s in args.seed_names.split(",") if s]
    owners = build_owners(args.cluster_name, args.seeds_project, seed_names)
    print(f"Matching resources owned by: {', '.join(o.name for o in owners)}")

    owned = gather(conn, owners)
    print("Found: " + ", ".join(f"{len(v)} {k}" for k, v in owned.items() if v))

    errors = cleanup(conn, owned, args.dry_run)
    if args.garden_url:
        errors += cleanup_dns(
            conn, args.garden_url, args.preserve_dns_type or ["SOA", "NS"], args.dry_run
        )

    if errors:
        print(f"\n{len(errors)} resource(s) could not be deleted:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit("\nAborted.")
