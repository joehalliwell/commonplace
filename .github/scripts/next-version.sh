#!/usr/bin/env bash
# The version after `latest`, bumped by the one semver:major|minor|patch label among a PR's labels (a JSON array).
# Usage: next-version.sh <latest-tag> <labels-json>
set -euo pipefail

latest=$1
labels=$2

bumps=$(printf '%s' "$labels" | grep -oE '"semver:[^"]*"' | tr -d '"' || true)
if [ "$(printf '%s' "$bumps" | grep -c . || true)" -ne 1 ]; then
    echo "expected exactly one semver:major|minor|patch label, found: ${bumps:-none}" >&2
    exit 1
fi

if ! [[ $latest =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    echo "latest tag '$latest' is not a MAJOR.MINOR.PATCH version" >&2
    exit 1
fi
major=${BASH_REMATCH[1]} minor=${BASH_REMATCH[2]} patch=${BASH_REMATCH[3]}

case ${bumps#semver:} in
    major) echo "$((major + 1)).0.0" ;;
    minor) echo "$major.$((minor + 1)).0" ;;
    patch) echo "$major.$minor.$((patch + 1))" ;;
    *)
        echo "unknown semver label '$bumps'" >&2
        exit 1
        ;;
esac
