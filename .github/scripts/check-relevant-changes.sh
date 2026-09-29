#!/bin/bash
# Decide whether a PR touches anything the yake-ansible-install CI pipeline
# actually exercises. group_vars/ci.yml only uses kind (not k3s), cilium
# networking (not calico), the OpenStack provider (not AWS/Azure/GCP), the
# GardenLinux OS extension (not Ubuntu), no proxy (Kyverno never runs), no
# registry cache/mirror, no shoot-oidc-service, no S3 backups, and always
# pins its own Kubernetes version (so the role defaults for it are never
# actually used). Bumping only these has zero test value in CI - skip the
# expensive OpenStack-backed run for changes confined to those lines.
#
# Usage: check-relevant-changes.sh <base-sha> <head-sha>
# Writes "relevant=true" or "relevant=false" to stdout (for GITHUB_OUTPUT).
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
  ["roles/gardener_operator/defaults/main.yml"]='^gardener_operator_(kubernetes_version|kyverno_version|provider_aws_version|provider_azure_version|provider_gcp_version|networking_calico_version|os_ubuntu_version|extension_registry_cache_version|shoot_oidc_service_version|backup_s3_version):'
)

changed_files=$(git diff --name-only "${BASE_SHA}" "${HEAD_SHA}")

if [ -z "${changed_files}" ]; then
  echo "relevant=false"
  exit 0
fi

for f in ${changed_files}; do
  if [ -z "${IGNORE_PATTERNS[${f}]+set}" ]; then
    echo "relevant=true"
    exit 0
  fi
done

# Every changed file has an ignore pattern - relevant unless every changed
# line in every one of those files matches its own pattern.
for f in ${changed_files}; do
  changed_lines=$(git diff --unified=0 "${BASE_SHA}" "${HEAD_SHA}" -- "${f}" \
    | grep -E '^[+-][^+-]' \
    | sed -E 's/^[+-]//' \
    | sed -E 's/^[[:space:]]+//;s/[[:space:]]+$//' \
    | grep -v '^$' \
    | grep -v '^#' || true)

  if [ -z "${changed_lines}" ]; then
    continue
  fi

  pattern="${IGNORE_PATTERNS[${f}]}"
  while IFS= read -r line; do
    if ! echo "${line}" | grep -qE "${pattern}"; then
      echo "relevant=true"
      exit 0
    fi
  done <<< "${changed_lines}"
done

echo "relevant=false"
