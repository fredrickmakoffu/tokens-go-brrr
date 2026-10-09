#!/usr/bin/env bash
# Install-test the packages in dist/ inside clean containers.
#   packaging/smoke.sh rpm|deb
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="$(command -v podman || command -v docker || { echo "need podman or docker" >&2; exit 1; })"
case "${1:-}" in
  rpm) IMAGE="registry.fedoraproject.org/fedora:latest" ;;
  deb) IMAGE="docker.io/library/debian:stable" ;;
  *) echo "usage: $0 rpm|deb" >&2; exit 2 ;;
esac
ls "$ROOT"/dist/*."$1" >/dev/null 2>&1 || { echo "no .$1 in dist/; build it first" >&2; exit 1; }
"$RUNTIME" run --rm -v "$ROOT:/src:ro,Z" -v "$ROOT/dist:/d:ro,Z" \
  "$IMAGE" bash /src/packaging/smoke-inner.sh "$1"
