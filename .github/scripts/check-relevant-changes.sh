#!/bin/bash
# Decide what a PR needs from the yake-ansible-install CI pipeline.
#
# relevant: does the PR touch anything the pipeline exercises at all?
#   group_vars/ci.yml only uses kind (not k3s), cilium networking (not calico),
#   the OpenStack provider (not AWS/Azure/GCP), the GardenLinux OS extension (not
#   Ubuntu), no proxy, no registry cache/mirror, no shoot-oidc-service, no S3
#   backups, and always pins its own Kubernetes version (so the role defaults for
#   it are never actually used). Bumping only these has zero test value in CI.
# seed: does the managed seed (cloud profile, project, seed, Kyverno) need to be
#   built? On by default. Off only if every change is documentation, an image
#   build, or a kubectl/helm bump (nothing the seed path touches).
#   Gardener, extension, Kyverno, Dex updates always run the seed.
#
# Usage: check-relevant-changes.sh <base-sha> <head-sha>
# Writes "relevant=true|false" and "seed=true|false" to stdout (for GITHUB_OUTPUT).
# The pattern arrays are read through a nameref in only_ignored.
# shellcheck disable=SC2034
set -euo pipefail

BASE_SHA="${1:?base sha required}"
HEAD_SHA="${2:?head sha required}"

# One regex per file, matched against the *changed* (added/removed) lines
# in that file only. Any file not listed here is always treated as
# relevant if it changed. Keep these anchored (^var_name:) so they only
# ever match a single, specific var's own definition line - never a
# comment, a nested value, or an unrelated var that happens to share a
# substring.
declare -A IGNORE_PATTERNS=(
  ["roles/management_cluster/defaults/main.yml"]='^management_cluster_k3s_version:'
  ["roles/clusterapi_cluster/defaults/main.yml"]='^clusterapi_cluster_(calico_version|kubernetes_version):'
  ["roles/gardener_operator/defaults/main.yml"]='^gardener_operator_(kubernetes_version|provider_aws_version|provider_azure_version|provider_gcp_version|networking_calico_version|os_ubuntu_version|extension_registry_cache_version|shoot_oidc_service_version|backup_s3_version):'
)

# Additionally ignored for the seed (the garden cluster is still tested).
declare -A SEED_IGNORE_PATTERNS=(
  ["roles/kubectl_install/defaults/main.yml"]='^kubectl_install_version:'
  ["roles/helm_install/defaults/main.yml"]='^helm_install_version:'
)
for f in "${!IGNORE_PATTERNS[@]}"; do
  SEED_IGNORE_PATTERNS["${f}"]="${IGNORE_PATTERNS[${f}]}"
done

# Three-dot diff: only what the PR changed since its merge base, not what
# landed on the base branch in the meantime.
changed_files=$(git diff --name-only "${BASE_SHA}...${HEAD_SHA}")

is_doc() {
  case "$1" in
    *.md | docs/* | images/*) return 0 ;;
    *) return 1 ;;
  esac
}

# only_ignored <array name> <docs ok>: true if every changed file has only changed
# lines matching its pattern in the given array (or, with docs ok = true, is documentation).
only_ignored() {
  local -n patterns="$1"
  local docs_ok="$2"
  local f pattern line changed_lines
  for f in ${changed_files}; do
    [ "${docs_ok}" = true ] && is_doc "${f}" && continue
    [ -n "${patterns[${f}]+set}" ] || return 1
  done

  for f in ${changed_files}; do
    [ "${docs_ok}" = true ] && is_doc "${f}" && continue
    # Skip the ---/+++ file headers (everything before the first hunk), keep
    # every added/removed line, including ones whose content starts with - or +.
    changed_lines=$(git diff --unified=0 "${BASE_SHA}...${HEAD_SHA}" -- "${f}" \
      | awk '/^@@/ { hunk = 1; next } hunk && /^[+-]/' \
      | sed -E 's/^[+-]//' \
      | sed -E 's/^[[:space:]]+//;s/[[:space:]]+$//' \
      | grep -v '^$' \
      | grep -v '^#' || true)

    [ -n "${changed_lines}" ] || continue

    pattern="${patterns[${f}]}"
    while IFS= read -r line; do
      echo "${line}" | grep -qE "${pattern}" || return 1
    done <<< "${changed_lines}"
  done
  return 0
}

if [ -z "${changed_files}" ] || only_ignored IGNORE_PATTERNS false; then
  echo "relevant=false"
  echo "seed=false"
  exit 0
fi

echo "relevant=true"
if only_ignored SEED_IGNORE_PATTERNS true; then
  echo "seed=false"
else
  echo "seed=true"
fi
