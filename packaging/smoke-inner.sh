#!/usr/bin/env bash
# Runs inside a clean distro container: install the built package the way a user
# would, check it landed correctly, then remove it and check it left cleanly.
# Cannot prove GNOME Shell loads the extension; that needs a real session.
set -euo pipefail
KIND="$1"
UUID="ai-usage@fredrickmakoffu.github.io"
VER="$(sed -n 's/^version = "\(.*\)"/\1/p' /src/pyproject.toml)"

case "$KIND" in
  rpm) dnf install -y -q /d/*.rpm >/dev/null ;;
  deb) export DEBIAN_FRONTEND=noninteractive
       apt-get update -qq >/dev/null
       apt-get install -y -qq --no-install-recommends /d/*.deb >/dev/null ;;
esac

fail() { echo "FAIL: $*" >&2; exit 1; }

[ "$(cursor-spend-monitor --version | awk '{print $NF}')" = "$VER" ] || fail "version != $VER"
[ -x /usr/bin/cursor-spend-monitor ] || fail "binary not in /usr/bin"
python3 -c "import json; m=json.load(open('/usr/share/gnome-shell/extensions/$UUID/metadata.json')); assert m['uuid']=='$UUID'; assert m['version-name']=='$VER'" \
  || fail "extension metadata"
[ -f /usr/share/gnome-shell/extensions/$UUID/extension.js ] || fail "extension.js missing"
grep -q '^ExecStart=/usr/bin/cursor-spend-monitor run' /usr/lib/systemd/user/cursor-spend-monitor.service \
  || fail "unit ExecStart"
if compgen -G "/src/gnome-shell-extension/$UUID/fonts/*.ttf" >/dev/null; then
  ls /usr/share/fonts/ai-usage/*.ttf >/dev/null || fail "fonts missing"
else
  echo "warning: no fonts in the source tree, so none were packaged" >&2
fi
if [ "$KIND" = deb ]; then
  dpkg -L cursor-spend-monitor | grep -q '^/usr/local' && fail "files under /usr/local"
fi

case "$KIND" in
  rpm) dnf remove -y -q cursor-spend-monitor >/dev/null ;;
  deb) apt-get remove -y -qq cursor-spend-monitor >/dev/null ;;
esac
[ ! -e /usr/bin/cursor-spend-monitor ] || fail "binary left behind after removal"
[ ! -e /usr/share/gnome-shell/extensions/$UUID ] || fail "extension left behind after removal"
echo "smoke ok: $KIND $VER"
