#!/usr/bin/env bash
# Install the Barlow fonts the popover is set in.
#
# The TTFs ship with the extension (SIL OFL, see fonts/OFL.txt), so this works
# offline. GNOME Shell reads fontconfig once at startup, so a Shell that was
# already running keeps its old fonts until you log out and back in.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$ROOT/gnome-shell-extension/ai-usage@fredrickmakoffu.github.io/fonts"
DST="$HOME/.local/share/fonts/ai-usage"

mkdir -p "$DST"
cp "$SRC"/*.ttf "$DST"/
fc-cache -f "$DST" >/dev/null 2>&1 || true

if [[ "$(fc-list)" == *"Barlow Condensed"* ]]; then
  echo "Barlow installed in $DST"
  echo "Log out and back in (or restart GNOME Shell) so the popover picks it up."
else
  echo "Fonts copied to $DST but fontconfig does not list them yet." >&2
  exit 1
fi
