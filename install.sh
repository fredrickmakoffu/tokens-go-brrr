#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UUID="tokens-go-brrr@fredrickmakoffu.github.io"
EXT_SRC="$ROOT/gnome-shell-extension/$UUID"
EXT_HOME="$HOME/.local/share/gnome-shell/extensions"
EXT_DST="$EXT_HOME/$UUID"
SERVICE_SRC="$ROOT/systemd/tokens-go-brrr.service"
SERVICE_DST="$HOME/.config/systemd/user/tokens-go-brrr.service"

echo "==> Installing system packages (may prompt for sudo)..."
sudo dnf install -y python3-gobject libnotify

echo "==> Installing Python daemon (no-deps; uses system PyGObject)..."
pip3 install --user --force-reinstall --no-deps "$ROOT"

echo "==> Installing GNOME Shell extension..."
rm -rf "$EXT_DST"
mkdir -p "$(dirname "$EXT_DST")"
cp -r "$EXT_SRC" "$EXT_DST"

echo "==> Installing Barlow fonts (the design system's typeface)..."
"$ROOT/install-fonts.sh"

echo "==> Installing systemd user service..."
mkdir -p "$HOME/.config/systemd/user"
cp "$SERVICE_SRC" "$SERVICE_DST"
systemctl --user daemon-reload
# A running daemon keeps the old code in memory, so a reinstall alone is not
# enough: restart it if it is already up.
if systemctl --user is-active --quiet tokens-go-brrr.service; then
  systemctl --user restart tokens-go-brrr.service
fi

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
kept = [u for u in enabled if not re.match(r'tokens-go-brrr-r\d+@', u)]
if kept != enabled:
    subprocess.run(
        ['gsettings', 'set', 'org.gnome.shell', 'enabled-extensions', repr(kept)],
        check=True)
    print('  enabled-extensions ->', kept)
PY
for dir in "$EXT_HOME"/tokens-go-brrr-r*@*; do
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
echo "  1. tokens-go-brrr setup"
echo "  2. systemctl --user enable --now tokens-go-brrr.service"
echo "  3. Log out and back in so GNOME Shell loads the extension"
echo "     (X11 only: Alt+F2, type r, Enter)"
echo
echo "Then click the status dot in the top bar."
echo "Config: $HOME/.config/tokens-go-brrr/config.json"
