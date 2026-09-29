#!/usr/bin/env bash
# Build the release notes: Gardener changelogs on top, this repository's
# changes below.
#
# Usage: build-release-notes.sh <tag> <previous-tag|""> <target-sha>
# Requires GH_TOKEN and GITHUB_REPOSITORY.
set -euo pipefail

tag=$1
previous=$2
target=$3

gardener_of() { sed -E 's/^v(.*)-[0-9]+$/\1/' <<<"$1"; }

current=$(gardener_of "$tag")
previous_gardener=""
[ -n "$previous" ] && previous_gardener=$(gardener_of "$previous")

# Gardener releases in (previous_gardener, current]; only the current one
# if there is no previous release.
if [ -z "$previous_gardener" ]; then
  versions=$current
else
  versions=$( {
      gh api --paginate repos/gardener/gardener/releases \
        --jq '.[] | select(.draft == false and .prerelease == false) | .tag_name' |
        sed 's/^v//'
      echo "$previous_gardener"
      echo "$current"
    } | sort -uV | awk -v lo="$previous_gardener" -v hi="$current" '$0 == hi { if (on) print; exit } on { print } $0 == lo { on = 1 }' | sort -rV)
fi

if [ -n "$versions" ]; then
  echo "## Gardener"
  echo
  for v in $versions; do
    echo "### [Gardener v${v}](https://github.com/gardener/gardener/releases/tag/v${v})"
    echo
    # Drop the title and everything from "Helm Charts" on (chart and image
    # references), demote the remaining headings below our own and remove
    # @mentions: GitHub would list the Gardener authors as contributors
    # of this repository. Entries for developers and dependency bumps are
    # of no use to someone installing Gardener, so they are dropped too,
    # together with headings that end up empty. Noteworthy and breaking
    # sections are kept as they are, their entries are rare and matter.
    gh api "repos/gardener/gardener/releases/tags/v${v}" --jq .body |
      sed -E '/^## Helm Charts/,$d; /^# /d; s/^## /#### /' |
      sed -E 's/ by @[A-Za-z0-9_-]+(\[bot\])?//g; s/(^|[^A-Za-z0-9`])@([A-Za-z0-9_-]+)/\1\2/g' |
      awk '
        /^#### / { heading = $0; important = ($0 ~ /Noteworthy|Breaking|Action/); next }
        /^- / { skip = (!important && $0 ~ /^- `\[(DEVELOPER|DEPENDENCY)\]`/) }
        /^[^- ]/ || /^$/ { skip = 0 }
        skip { next }
        /^$/ { blank = 1; next }
        {
          if (heading != "") { if (started) print ""; print heading; heading = ""; blank = 0 }
          else if (blank) print ""
          blank = 0; started = 1
          print
        }'
    echo
  done
fi

echo "## Changes in this repository"
echo
if [ -z "$previous" ]; then
  echo "Initial release."
else
  gh api "repos/${GITHUB_REPOSITORY}/releases/generate-notes" \
    -f tag_name="$tag" -f target_commitish="$target" \
    -f previous_tag_name="$previous" --jq .body
fi
