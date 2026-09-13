#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_SRC="$ROOT/systemd/cursor-spend-monitor.service"
SERVICE_DST="$HOME/.config/systemd/user/cursor-spend-monitor.service"

echo "==> Installing system packages (may prompt for sudo)..."
sudo dnf install -y \
  python3-gobject \
  libayatana-appindicator-gtk3 \
  gnome-shell-extension-appindicator \
  libnotify

echo "==> Enabling AppIndicator GNOME extension..."
gsettings set org.gnome.shell disable-user-extensions false
gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com 2>/dev/null || true
# Keep it in the enabled list even if gnome-extensions CLI races
current="$(gsettings get org.gnome.shell enabled-extensions)"
if ! echo "$current" | grep -q "appindicatorsupport@rgcjonas.gmail.com"; then
  gsettings set org.gnome.shell enabled-extensions \
    "$(python3 -c "import ast,sys; e=ast.literal_eval(sys.argv[1]); e.append('appindicatorsupport@rgcjonas.gmail.com'); print(repr(e))" "$current")"
fi

echo "==> Installing Python package (no-deps; uses system PyGObject)..."
pip3 install --user --no-deps "$ROOT"

echo "==> Installing systemd user service..."
mkdir -p "$HOME/.config/systemd/user"
cp "$SERVICE_SRC" "$SERVICE_DST"
systemctl --user daemon-reload

echo
echo "Done."
echo
echo "Next steps:"
echo "  1. cursor-spend-monitor setup     # paste WorkosCursorSessionToken cookie"
echo "  2. cursor-spend-monitor status      # verify API access"
echo "  3. systemctl --user enable --now cursor-spend-monitor.service"
echo
echo "Config & alerts: $HOME/.config/cursor-spend-monitor/config.json"
