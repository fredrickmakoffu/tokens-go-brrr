#!/usr/bin/env bash
# Build a distro package in a throwaway container. Output lands in dist/.
#
#   packaging/build.sh rpm   # Fedora
#   packaging/build.sh deb   # Debian
#
# Builds whatever is in the working tree. Release builds run from a clean tag
# checkout in CI, so the tree is clean there.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="$(command -v podman || command -v docker || { echo "need podman or docker" >&2; exit 1; })"

case "${1:-}" in
  rpm) IMAGE="registry.fedoraproject.org/fedora:latest" ;;
  deb) IMAGE="docker.io/library/debian:stable" ;;
  *) echo "usage: $0 rpm|deb" >&2; exit 2 ;;
esac

mkdir -p "$ROOT/dist"
"$RUNTIME" run --rm \
  -v "$ROOT:/src:ro,Z" -v "$ROOT/dist:/out:Z" \
  "$IMAGE" bash "/src/packaging/$1/inner.sh"
ls -1 "$ROOT"/dist/*."$1"
