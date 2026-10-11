#!/usr/bin/env bash
# Runs inside a clean distro container: install the built package the way a user
# would, check it landed correctly, then remove it and check it left cleanly.
# Cannot prove GNOME Shell loads the extension; that needs a real session.
set -euo pipefail
KIND="$1"
UUID="tokens-go-brrr@fredrickmakoffu.github.io"
VER="$(sed -n 's/^version = "\(.*\)"/\1/p' /src/pyproject.toml)"

case "$KIND" in
  rpm) dnf install -y -q /d/*.rpm >/dev/null ;;
  deb) export DEBIAN_FRONTEND=noninteractive
       apt-get update -qq >/dev/null
       apt-get install -y -qq --no-install-recommends /d/*.deb >/dev/null ;;
esac

fail() { echo "FAIL: $*" >&2; exit 1; }

[ "$(tokens-go-brrr --version | awk '{print $NF}')" = "$VER" ] || fail "version != $VER"
[ -x /usr/bin/tokens-go-brrr ] || fail "binary not in /usr/bin"
python3 -c "import json; m=json.load(open('/usr/share/gnome-shell/extensions/$UUID/metadata.json')); assert m['uuid']=='$UUID'; assert m['version-name']=='$VER'" \
  || fail "extension metadata"
[ -f /usr/share/gnome-shell/extensions/$UUID/extension.js ] || fail "extension.js missing"
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

case "$KIND" in
  rpm) dnf remove -y -q tokens-go-brrr >/dev/null ;;
  deb) apt-get remove -y -qq tokens-go-brrr >/dev/null ;;
esac
[ ! -e /usr/bin/tokens-go-brrr ] || fail "binary left behind after removal"
[ ! -e /usr/share/gnome-shell/extensions/$UUID ] || fail "extension left behind after removal"
echo "smoke ok: $KIND $VER"
