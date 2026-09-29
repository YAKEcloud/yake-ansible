#!/bin/bash
set -euo pipefail

README_URL="https://raw.githubusercontent.com/gardener/gardener-extension-provider-openstack/master/README.md"
RENOVATE_JSON="$(dirname "$0")/../../renovate.json"

max_minor=$(curl -fsSL "${README_URL}" \
  | grep -oE '\| *Kubernetes [0-9]+\.[0-9]+ *\|' \
  | grep -oE '[0-9]+\.[0-9]+' \
  | sort -t. -k1,1n -k2,2n \
  | tail -1)

if [ -z "${max_minor}" ]; then
  echo "Could not find any 'Kubernetes X.Y' entry in ${README_URL}" >&2
  exit 1
fi

major="${max_minor%%.*}"
minor="${max_minor##*.}"
next_minor="${major}.$((minor + 1)).0"
allowed="<${next_minor}"

current=$(jq -r '.packageRules[] | select(.matchDepNames == ["kubernetes/kubernetes"]) | .allowedVersions' "${RENOVATE_JSON}")

if [ "${current}" == "${allowed}" ]; then
  echo "changed=false"
  exit 0
fi

tmp=$(mktemp)
jq --arg allowed "${allowed}" \
  '(.packageRules[] | select(.matchDepNames == ["kubernetes/kubernetes"]) | .allowedVersions) = $allowed' \
  "${RENOVATE_JSON}" > "${tmp}"
mv "${tmp}" "${RENOVATE_JSON}"

echo "changed=true"
echo "allowed=${allowed}"
