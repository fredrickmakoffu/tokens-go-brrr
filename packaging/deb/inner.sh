#!/usr/bin/env bash
# Runs inside the debian container. /src is the repo (read-only), /out receives the .deb files.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq --no-install-recommends python3 python3-pip python3-setuptools python3-wheel dpkg-dev >/dev/null

VER="$(python3 /src/scripts/bump_version.py --print)"
WORK="$(mktemp -d)"
cp -r /src "$WORK/src"
rm -rf "$WORK/src/.git" "$WORK/src/build" "$WORK/src/dist" "$WORK"/src/*.egg-info

fold_usr_local() {
  local PKG="$1"
  if [ -d "$PKG/usr/local" ]; then
    cp -a "$PKG/usr/local/." "$PKG/usr/"
    rm -rf "$PKG/usr/local"
  fi
}

build_one() {
  local COMP="$1" CONTROL_IN="$2" OUT_NAME="$3" POSTINST="${4:-}"
  local PKG="$WORK/pkg-$COMP"
  rm -rf "$PKG"
  mkdir -p "$PKG/DEBIAN"
  "$WORK/src/packaging/stage.sh" "$PKG" "$COMP"
  fold_usr_local "$PKG"
  sed "s/@VERSION@/$VER/g" "/src/packaging/deb/$CONTROL_IN" > "$PKG/DEBIAN/control"
  install -m 0644 /src/packaging/deb/copyright "$PKG/DEBIAN/copyright"
  if [ -n "$POSTINST" ]; then
    install -m 0755 "/src/packaging/deb/$POSTINST" "$PKG/DEBIAN/postinst"
  fi
  dpkg-deb --root-owner-group --build "$PKG" "/out/$OUT_NAME" >/dev/null
}

build_one daemon control.in "tokens-go-brrr_${VER}_all.deb" postinst
build_one gnome control-gnome.in "tokens-go-brrr-gnome_${VER}_all.deb"
build_one plasma control-plasma.in "tokens-go-brrr-plasma_${VER}_all.deb"
