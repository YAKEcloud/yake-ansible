#!/bin/bash
set -euo pipefail

README_URL="https://raw.githubusercontent.com/gardener/gardener-extension-provider-openstack/master/README.md"
RENOVATE_JSON="$(dirname "$0")/../../renovate.json"

readme=$(curl -fsSL --max-time 30 --retry 3 "${README_URL}")

# No match is handled below, so do not let grep's exit status abort here.
max_minor=$(grep -oE '\| *Kubernetes [0-9]+\.[0-9]+ *\|' <<< "${readme}" \
  | grep -oE '[0-9]+\.[0-9]+' \
  | sort -t. -k1,1n -k2,2n \
  | tail -1 || true)

if [ -z "${max_minor}" ]; then
  echo "Could not find any 'Kubernetes X.Y' entry in ${README_URL}" >&2
  exit 1
fi

major="${max_minor%%.*}"
minor="${max_minor##*.}"
next_minor="${major}.$((minor + 1)).0"
allowed="<${next_minor}"

current=$(jq -r '.packageRules[] | select(.matchDepNames == ["kubernetes/kubernetes"]) | .allowedVersions' "${RENOVATE_JSON}")

if [ -z "${current}" ]; then
  echo "No kubernetes/kubernetes allowedVersions rule found in ${RENOVATE_JSON}" >&2
  exit 1
fi

echo "allowed=${allowed}"

if [ "${current}" == "${allowed}" ]; then
  echo "changed=false"
  exit 0
fi

# Literal string replacement keeps the file's formatting (jq would reformat it).
content=$(<"${RENOVATE_JSON}")
printf '%s\n' "${content/"\"allowedVersions\": \"${current}\""/"\"allowedVersions\": \"${allowed}\""}" > "${RENOVATE_JSON}"

updated=$(jq -r '.packageRules[] | select(.matchDepNames == ["kubernetes/kubernetes"]) | .allowedVersions' "${RENOVATE_JSON}")
if [ "${updated}" != "${allowed}" ]; then
  echo "Failed to update allowedVersions in ${RENOVATE_JSON}" >&2
  exit 1
fi

echo "changed=true"
