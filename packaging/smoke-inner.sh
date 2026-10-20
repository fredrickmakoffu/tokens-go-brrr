#!/usr/bin/env bash
# Runs inside a clean distro container: install the built packages the way a user
# would, check they landed correctly, then remove them and check they left cleanly.
# Cannot prove GNOME Shell / Plasma loads the UI; that needs a real session.
set -euo pipefail
KIND="$1"
UUID="tokens-go-brrr@fredrickmakoffu.github.io"
PLASMA_ID="org.tokensgobrrr.panel"
VER="$(sed -n 's/^version = "\(.*\)"/\1/p' /src/pyproject.toml)"

case "$KIND" in
  rpm) dnf install -y -q /d/*.rpm >/dev/null ;;
  deb) export DEBIAN_FRONTEND=noninteractive
       apt-get update -qq >/dev/null
       # Core first so UI packages can satisfy Depends.
       apt-get install -y -qq --no-install-recommends \
         /d/tokens-go-brrr_${VER}_all.deb \
         /d/tokens-go-brrr-gnome_${VER}_all.deb \
         /d/tokens-go-brrr-plasma_${VER}_all.deb >/dev/null ;;
esac

fail() { echo "FAIL: $*" >&2; exit 1; }

[ "$(tokens-go-brrr --version | awk '{print $NF}')" = "$VER" ] || fail "version != $VER"
[ -x /usr/bin/tokens-go-brrr ] || fail "binary not in /usr/bin"
[ -f /usr/share/tokens-go-brrr/ui/tokens.json ] || fail "shared tokens.json missing"
python3 -c "import json; m=json.load(open('/usr/share/gnome-shell/extensions/$UUID/metadata.json')); assert m['uuid']=='$UUID'; assert m['version-name']=='$VER'" \
  || fail "extension metadata"
[ -f /usr/share/gnome-shell/extensions/$UUID/extension.js ] || fail "extension.js missing"
[ -f /usr/share/plasma/plasmoids/$PLASMA_ID/metadata.json ] || fail "plasmoid metadata missing"
[ -f /usr/share/plasma/plasmoids/$PLASMA_ID/contents/ui/main.qml ] || fail "plasmoid main.qml missing"
grep -q '^ExecStart=/usr/bin/tokens-go-brrr run' /usr/lib/systemd/user/tokens-go-brrr.service \
  || fail "unit ExecStart"
if compgen -G "/src/gnome-shell-extension/$UUID/fonts/*.ttf" >/dev/null; then
  ls /usr/share/fonts/tokens-go-brrr/*.ttf >/dev/null || fail "fonts missing"
else
  echo "warning: no fonts in the source tree, so none were packaged" >&2
fi
if [ "$KIND" = deb ]; then
  dpkg -L tokens-go-brrr | grep -q '^/usr/local' && fail "files under /usr/local"
fi

# Core must not hard-require a desktop shell (KDE / GNOME isolation).
case "$KIND" in
  rpm)
    rpm -qR tokens-go-brrr | grep -E 'gnome-shell|plasma-workspace' && \
      fail "core RPM must not Require gnome-shell or plasma-workspace" || true
    rpm -qR tokens-go-brrr-gnome | grep -q gnome-shell || fail "gnome RPM missing gnome-shell Requires"
    rpm -qR tokens-go-brrr-plasma | grep -q plasma-workspace || fail "plasma RPM missing plasma-workspace Requires"
    ;;
  deb)
    dpkg-deb -f /d/tokens-go-brrr_${VER}_all.deb Depends | grep -E 'gnome-shell|plasma-workspace' && \
      fail "core DEB must not Depend on gnome-shell or plasma-workspace" || true
    ;;
esac

case "$KIND" in
  rpm) dnf remove -y -q tokens-go-brrr tokens-go-brrr-gnome tokens-go-brrr-plasma >/dev/null ;;
  deb) apt-get remove -y -qq tokens-go-brrr-gnome tokens-go-brrr-plasma tokens-go-brrr >/dev/null ;;
esac
[ ! -e /usr/bin/tokens-go-brrr ] || fail "binary left behind after removal"
[ ! -e /usr/share/gnome-shell/extensions/$UUID ] || fail "extension left behind after removal"
[ ! -e /usr/share/plasma/plasmoids/$PLASMA_ID ] || fail "plasmoid left behind after removal"
echo "smoke ok: $KIND $VER"
