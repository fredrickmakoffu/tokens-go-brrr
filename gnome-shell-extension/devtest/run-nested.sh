#!/usr/bin/env bash
# Launch a throwaway headless GNOME Shell with the extension + a mock daemon.
# Usage: ./run-nested.sh [seconds]   (screenshots land in ./shots when a driver is present)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
UUID="tokens-go-brrr@fredrickmakoffu.github.io"
RUNTIME="${AI_USAGE_NESTED_DIR:-$(mktemp -d)}"
DURATION="${1:-60}"

mkdir -p "$RUNTIME"/{config/glib-2.0/settings,data/gnome-shell/extensions,cache,shots}
ln -sfn "$REPO/gnome-shell-extension/$UUID" "$RUNTIME/data/gnome-shell/extensions/$UUID"
# The shell resolves Barlow through fontconfig, which reads $XDG_DATA_HOME/fonts.
ln -sfn "$REPO/gnome-shell-extension/$UUID/fonts" "$RUNTIME/data/fonts"

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

dbus-run-session -- bash -c "
  python3 '$HERE/mock_daemon.py' '$REPO' &
  sleep 1
  timeout $DURATION gnome-shell --headless --virtual-monitor 1280x720 --no-x11
  kill %1 2>/dev/null || true
"
