#!/usr/bin/env python3
"""
Delete only the OpenStack resources belonging to a yake-ansible cluster/seed,
matched by name (never "delete everything except X").

Requirements:
  pip install openstacksdk

Usage:
  export OS_CLOUD=mycloud   # or use --cloud
  python3 scripts/cleanup-openstack.py --garden-url botany.yake.cloud
  python3 scripts/cleanup-openstack.py --seed-names managed-seed-a --dry-run
"""

import argparse
import re
import sys

try:
    import openstack
except ImportError:
    sys.exit("Missing dependency: pip install openstacksdk")


def own_name_regex(prefixes):
    """Strict regex: exact prefix, prefix-suffix, or CAPO's k8s-cluster(api)- forms."""
    parts = []
    for p in prefixes:
        escaped = re.escape(p)
        parts += [
            rf"^{escaped}$",
            rf"^{escaped}-.*$",
            rf"^k8s-cluster-default-{escaped}(-.*)?$",
            rf"^k8s-clusterapi-cluster-default-{escaped}(-.*)?$",
        ]
    return re.compile("|".join(parts))


def matches_any_substring(name, prefixes):
    return bool(name) and any(p in name for p in prefixes)


def report(dry_run, kind, items, label=lambda i: i.name or i.id):
    verb = "Would delete" if dry_run else "Deleting"
    for item in items:
        print(f"  [{kind}] {verb}: {label(item)} ({item.id})")


def gather(conn, prefixes, name_re):
    """Read-only: identify every resource this run owns. Never deletes anything."""
    print("Gathering resources ...")

    servers = [
        s for s in conn.compute.servers(details=True) if name_re.match(s.name or "")
    ]

    all_volumes = list(conn.block_storage.volumes())
    attached_to_own = {vol["id"] for s in servers for vol in (s.attached_volumes or [])}
    volumes = list(
        {
            v.id: v
            for v in all_volumes
            if matches_any_substring(v.name, prefixes) or v.id in attached_to_own
        }.values()
    )

    keypairs = [k for k in conn.compute.keypairs() if k.name in prefixes]

    server_groups = [
        g for g in conn.compute.server_groups() if name_re.match(g.name or "")
    ]

    security_groups = [
        g for g in conn.network.security_groups() if name_re.match(g.name or "")
    ]

    networks = [n for n in conn.network.networks() if name_re.match(n.name or "")]
    network_ids = {n.id for n in networks}
    subnets = [s for s in conn.network.subnets() if s.network_id in network_ids]

    routers = [r for r in conn.network.routers() if name_re.match(r.name or "")]
    router_ids = {r.id for r in routers}

    # openstack-cloud-controller-manager on our own garden host cluster names its
    # LoadBalancer-typed Service objects "kube_service_kubernetes_<namespace>_..."
    # (its default cluster-name is the literal string "kubernetes", not our
    # cluster name) - only Gardener's own shoot LBs embed our prefixes directly.
    loadbalancers = [
        lb
        for lb in conn.load_balancer.load_balancers()
        if matches_any_substring(lb.name, prefixes)
        or (lb.name or "").startswith("kube_service_kubernetes_")
    ]

    all_ports = list(conn.network.ports())
    own_ports = [p for p in all_ports if p.network_id in network_ids]
    router_interface_ports = [
        p
        for p in all_ports
        if p.device_owner == "network:router_interface" and p.device_id in router_ids
    ]
    own_port_ids = {p.id for p in own_ports} | {p.id for p in router_interface_ports}

    floating_ips = [f for f in conn.network.ips() if f.port_id in own_port_ids]

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


def cleanup(conn, owned, dry_run):
    report(dry_run, "server", owned["servers"])
    if not dry_run:
        for s in owned["servers"]:
            conn.compute.delete_server(s, ignore_missing=True)
        for s in owned["servers"]:
            conn.compute.wait_for_delete(s)

    report(
        dry_run,
        "floating-ip",
        owned["floating_ips"],
        label=lambda i: i.floating_ip_address,
    )
    if not dry_run:
        for f in owned["floating_ips"]:
            conn.network.delete_ip(f, ignore_missing=True)

    report(dry_run, "loadbalancer", owned["loadbalancers"])
    if not dry_run:
        for lb in owned["loadbalancers"]:
            conn.load_balancer.delete_load_balancer(
                lb, ignore_missing=True, cascade=True
            )
        for lb in owned["loadbalancers"]:
            conn.load_balancer.wait_for_delete(lb)

    report(dry_run, "volume", owned["volumes"], label=lambda i: i.name or i.id)
    if not dry_run:
        for v in owned["volumes"]:
            conn.block_storage.delete_volume(v, ignore_missing=True)

    report(
        dry_run,
        "router-interface",
        owned["router_interface_ports"],
        label=lambda i: i.device_id,
    )
    if not dry_run:
        for p in owned["router_interface_ports"]:
            try:
                conn.network.remove_interface_from_router(
                    p.device_id, subnet_id=p.fixed_ips[0]["subnet_id"]
                )
            except (
                Exception
            ) as exc:  # noqa: BLE001 — best-effort, router delete below still runs
                print(f"  [router-interface] Warning: {exc}")

    report(dry_run, "router", owned["routers"])
    if not dry_run:
        for r in owned["routers"]:
            conn.network.delete_router(r, ignore_missing=True)

    report(dry_run, "port", owned["ports"], label=lambda i: i.name or i.id)
    if not dry_run:
        for p in owned["ports"]:
            conn.network.delete_port(p, ignore_missing=True)

    report(dry_run, "subnet", owned["subnets"], label=lambda i: i.name or i.id)
    if not dry_run:
        for s in owned["subnets"]:
            conn.network.delete_subnet(s, ignore_missing=True)

    report(dry_run, "network", owned["networks"])
    if not dry_run:
        for n in owned["networks"]:
            conn.network.delete_network(n, ignore_missing=True)

    report(dry_run, "security-group", owned["security_groups"])
    if not dry_run:
        for g in owned["security_groups"]:
            conn.network.delete_security_group(g, ignore_missing=True)

    report(dry_run, "keypair", owned["keypairs"], label=lambda i: i.name)
    if not dry_run:
        for k in owned["keypairs"]:
            conn.compute.delete_keypair(k, ignore_missing=True)

    report(dry_run, "server-group", owned["server_groups"])
    if not dry_run:
        for g in owned["server_groups"]:
            conn.compute.delete_server_group(g, ignore_missing=True)


def cleanup_dns(conn, garden_url, preserve_types, dry_run):
    zone = f"{garden_url}."
    zones = [z for z in conn.dns.zones() if z.name == zone]
    if not zones:
        print(f"No DNS zone '{zone}' found, skipping.")
        return
    recordsets = [
        r for z in zones for r in conn.dns.recordsets(z) if r.type not in preserve_types
    ]
    report(dry_run, "dns-recordset", recordsets, label=lambda i: f"{i.name} ({i.type})")
    if not dry_run:
        for r in recordsets:
            conn.dns.delete_recordset(r, ignore_missing=True)


def main():
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
    args = parser.parse_args()

    print("Connecting to OpenStack ...")
    try:
        conn = openstack.connect(cloud=args.cloud, insecure=args.insecure)
        _ = conn.auth["auth_url"]
    except Exception:  # noqa: BLE001 — turn any connect failure into a CLI error
        sys.exit("No OpenStack credentials found. Set OS_CLOUD or pass --cloud <name>.")
    print(f"Connected: {conn.auth['auth_url']}")

    if args.dry_run:
        print("Dry-run mode — nothing will be deleted.")

    seed_names = [s for s in args.seed_names.split(",") if s]
    prefixes = [args.cluster_name] + [
        f"shoot--{args.seeds_project}--{s}" for s in seed_names
    ]
    name_re = own_name_regex(prefixes)
    print(f"Matching resources owned by: {', '.join(prefixes)}")

    owned = gather(conn, prefixes, name_re)
    cleanup(conn, owned, args.dry_run)

    if args.garden_url:
        cleanup_dns(
            conn, args.garden_url, args.preserve_dns_type or ["SOA", "NS"], args.dry_run
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nAborted.")
    except Exception as exc:  # noqa: BLE001 — top-level guard, report and exit cleanly
        sys.exit(f"Error: {exc}")
