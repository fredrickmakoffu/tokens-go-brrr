#!/usr/bin/env bash
# Runs inside the fedora container. /src is the repo (read-only), /out receives the RPM.
set -euo pipefail
dnf install -y -q rpm-build python3 python3-devel python3-pip python3-setuptools python3-wheel >/dev/null
VER="$(python3 /src/scripts/bump_version.py --print)"

TOP="$HOME/rpmbuild"; mkdir -p "$TOP"/{SOURCES,SPECS}
STAGE="$(mktemp -d)/cursor-spend-monitor-$VER"; mkdir -p "$STAGE"
tar -C /src --exclude=.git --exclude=build --exclude=dist --exclude='*.egg-info' \
    --exclude=__pycache__ --exclude=.ruff_cache --exclude=design --exclude=site -cf - . | tar -C "$STAGE" -xf -
tar -C "$(dirname "$STAGE")" -czf "$TOP/SOURCES/cursor-spend-monitor-$VER.tar.gz" "cursor-spend-monitor-$VER"

rpmbuild -bb --define "ver $VER" /src/packaging/rpm/cursor-spend-monitor.spec >/dev/null
cp "$TOP"/RPMS/noarch/*.rpm /out/
