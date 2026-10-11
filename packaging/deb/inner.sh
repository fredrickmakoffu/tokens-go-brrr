#!/usr/bin/env bash
# Runs inside the debian container. /src is the repo (read-only), /out receives the .deb.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq --no-install-recommends python3 python3-pip python3-setuptools python3-wheel dpkg-dev >/dev/null

VER="$(python3 /src/scripts/bump_version.py --print)"
WORK="$(mktemp -d)"
cp -r /src "$WORK/src"
rm -rf "$WORK/src/.git" "$WORK/src/build" "$WORK/src/dist" "$WORK"/src/*.egg-info
PKG="$WORK/pkg"; mkdir -p "$PKG/DEBIAN"

"$WORK/src/packaging/stage.sh" "$PKG"

# Debian's pip redirects root installs to /usr/local (dist-packages). Packages
# must own /usr, so fold it back; dist-packages is already the right dir name.
if [ -d "$PKG/usr/local" ]; then
  cp -a "$PKG/usr/local/." "$PKG/usr/"
  rm -rf "$PKG/usr/local"
fi

sed "s/@VERSION@/$VER/" /src/packaging/deb/control.in > "$PKG/DEBIAN/control"
install -m 0755 /src/packaging/deb/postinst "$PKG/DEBIAN/postinst"
dpkg-deb --root-owner-group --build "$PKG" "/out/tokens-go-brrr_${VER}_all.deb" >/dev/null
