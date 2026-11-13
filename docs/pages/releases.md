# Releases

## Versioning

Releases follow Gardener. A tag like `v1.155.1-0` is the first release for Gardener `1.155.1`. The suffixes `-1`, `-2` and so on are fixes to this repository for the same Gardener version.

A new release is published automatically for every new Gardener version. The release notes list the Gardener changes first, then the changes in this repository.

## What is tested

Each release is tested with its Gardener version, and that means the Gardener installation only: management cluster, garden cluster, Gardener Operator, extensions and the managed seed. Shoots and everything else you run on top are outside the test scope.

## Using a release

Pin a release with `git checkout <tag>`. Then run the playbook as described in [Installation](getting-started.md).

To run another Gardener version, set `gardener_operator_version` in your `group_vars/all.yml`. This works, but it is not tested.

!!! note "Only the newest version is maintained"
    Fixes go into the newest Gardener version only. To get a fix, upgrade to the current release.

## Minimum Gardener version

The minimum Gardener version is `1.142.0`. Since that version, nginx-ingress is no longer deployed and all Gardener endpoints are served through the Istio ingress gateway. Older versions are not supported.

## Upgrading

How to upgrade Gardener, the provider extensions, the garden cluster and the management cluster step by step is described in [Operations](operations.md#upgrading).
