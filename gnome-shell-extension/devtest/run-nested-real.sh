#!/usr/bin/env bash
# Like run-nested.sh, but drives the real daemon against your real logins
# instead of the mock, so you see live numbers for every configured provider.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
UUID="ai-usage@fredrickmakoffu.github.io"
RUNTIME="${AI_USAGE_NESTED_DIR:-$(mktemp -d)}"
DURATION="${1:-60}"

mkdir -p "$RUNTIME"/{config/glib-2.0/settings,data/gnome-shell/extensions,cache,shots}
ln -sfn "$REPO/gnome-shell-extension/$UUID" "$RUNTIME/data/gnome-shell/extensions/$UUID"
mkdir -p "$RUNTIME/config/cursor-spend-monitor"
cp "$HOME/.config/cursor-spend-monitor/config.json" \
   "$RUNTIME/config/cursor-spend-monitor/" 2>/dev/null || true

cat > "$RUNTIME/config/glib-2.0/settings/keyfile" <<EOF
[org/gnome/shell]
enabled-extensions=['$UUID']
disable-user-extensions=false
welcome-dialog-last-shown-version='99.0'

[org/gnome/desktop/interface]
color-scheme='prefer-dark'
EOF

echo "runtime: $RUNTIME"
export XDG_CONFIG_HOME="$RUNTIME/config" XDG_DATA_HOME="$RUNTIME/data" \
       XDG_CACHE_HOME="$RUNTIME/cache" GSETTINGS_BACKEND=keyfile \
       AI_USAGE_SHOTS="$RUNTIME/shots"

# The shell needs the sandboxed data dir to find the extension, but the daemon
# must keep the real one so it still sees the OpenCode and Claude logins. The
# config is a copy, so chip swaps made in here do not touch your real settings.
dbus-run-session -- bash -c "
  cd '$REPO' && XDG_DATA_HOME='$HOME/.local/share' python3 -u -m cursor_spend_monitor run &
  sleep 2
  timeout $DURATION gnome-shell --headless --virtual-monitor 1280x720 --no-x11
  kill %1 2>/dev/null || true
"
