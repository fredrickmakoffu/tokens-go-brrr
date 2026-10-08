#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UUID="ai-usage@fredrickmakoffu.github.io"
EXT_SRC="$ROOT/gnome-shell-extension/$UUID"
EXT_HOME="$HOME/.local/share/gnome-shell/extensions"
EXT_DST="$EXT_HOME/$UUID"
SERVICE_SRC="$ROOT/systemd/cursor-spend-monitor.service"
SERVICE_DST="$HOME/.config/systemd/user/cursor-spend-monitor.service"

echo "==> Installing system packages (may prompt for sudo)..."
sudo dnf install -y python3-gobject libnotify

echo "==> Installing Python daemon (no-deps; uses system PyGObject)..."
pip3 install --user --force-reinstall --no-deps "$ROOT"

echo "==> Installing GNOME Shell extension..."
rm -rf "$EXT_DST"
mkdir -p "$(dirname "$EXT_DST")"
cp -r "$EXT_SRC" "$EXT_DST"

echo "==> Installing systemd user service..."
mkdir -p "$HOME/.config/systemd/user"
cp "$SERVICE_SRC" "$SERVICE_DST"
systemctl --user daemon-reload

echo "==> Removing leftover live-reload revisions..."
# `live-reload.sh` stages each revision under a new uuid, which is how it makes
# the shell re-import a changed file. Those copies are throwaway, and an install
# that skips this leaves a stale revision enabled beside the real one — two "AI
# Usage" extensions in the list, which is exactly what happened once.
python3 - <<'PY'
import ast, re, subprocess

enabled = ast.literal_eval(subprocess.run(
    ['gsettings', 'get', 'org.gnome.shell', 'enabled-extensions'],
    capture_output=True, text=True, check=True).stdout.strip())
kept = [u for u in enabled if not re.match(r'ai-usage-r\d+@', u)]
if kept != enabled:
    subprocess.run(
        ['gsettings', 'set', 'org.gnome.shell', 'enabled-extensions', repr(kept)],
        check=True)
    print('  enabled-extensions ->', kept)
PY
for dir in "$EXT_HOME"/ai-usage-r*@*; do
  [ -e "$dir" ] || continue
  rm -rf "$dir"
  echo "  removed $(basename "$dir")"
done

echo "==> Enabling the extension..."
gsettings set org.gnome.shell disable-user-extensions false
gnome-extensions enable "$UUID" 2>/dev/null || true

echo
echo "Done."
echo
echo "Next steps:"
echo "  1. cursor-spend-monitor setup"
echo "  2. systemctl --user enable --now cursor-spend-monitor.service"
echo "  3. Log out and back in so GNOME Shell loads the extension"
echo "     (X11 only: Alt+F2, type r, Enter)"
echo
echo "Then click the status dot in the top bar."
echo "Config: $HOME/.config/cursor-spend-monitor/config.json"
