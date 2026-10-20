#!/usr/bin/env bash
# Install the daemon and the panel UI that matches this session.
#
#   ./install.sh              # --ui=auto (detect GNOME / Plasma / none)
#   ./install.sh --ui=gnome
#   ./install.sh --ui=plasma
#   ./install.sh --ui=none    # daemon + CLI only
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UUID="tokens-go-brrr@fredrickmakoffu.github.io"
EXT_SRC="$ROOT/gnome-shell-extension/$UUID"
EXT_HOME="$HOME/.local/share/gnome-shell/extensions"
EXT_DST="$EXT_HOME/$UUID"
PLASMA_ID="org.tokensgobrrr.panel"
PLASMA_SRC="$ROOT/plasma/$PLASMA_ID"
PLASMA_DST="$HOME/.local/share/plasma/plasmoids/$PLASMA_ID"
SERVICE_SRC="$ROOT/systemd/tokens-go-brrr.service"
SERVICE_DST="$HOME/.config/systemd/user/tokens-go-brrr.service"

UI="auto"
while [ $# -gt 0 ]; do
  case "$1" in
    --ui=*) UI="${1#--ui=}" ;;
    --ui) shift; UI="${1:-}" ;;
    -h|--help)
      sed -n '2,8p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

UI="$(PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -c \
  "from tokens_go_brrr.desktop import detect_ui; print(detect_ui('$UI'))")"

echo "==> UI target: $UI"

echo "==> Installing system packages (may prompt for sudo)..."
if command -v dnf >/dev/null; then
  sudo dnf install -y python3-gobject libnotify
elif command -v apt-get >/dev/null; then
  sudo apt-get install -y python3-gi libnotify-bin gir1.2-notify-0.7
else
  echo "install python3-gobject / python3-gi and libnotify yourself" >&2
fi

echo "==> Installing Python daemon (no-deps; uses system PyGObject)..."
pip3 install --user --force-reinstall --no-deps "$ROOT"

echo "==> Installing Barlow fonts (the design system's typeface)..."
"$ROOT/install-fonts.sh"

echo "==> Installing systemd user service..."
mkdir -p "$HOME/.config/systemd/user"
cp "$SERVICE_SRC" "$SERVICE_DST"
systemctl --user daemon-reload
if systemctl --user is-active --quiet tokens-go-brrr.service; then
  systemctl --user restart tokens-go-brrr.service
fi

install_gnome() {
  echo "==> Installing GNOME Shell extension..."
  rm -rf "$EXT_DST"
  mkdir -p "$(dirname "$EXT_DST")"
  cp -r "$EXT_SRC" "$EXT_DST"

  echo "==> Removing leftover live-reload revisions..."
  python3 - <<'PY' || true
import ast, re, subprocess
try:
    enabled = ast.literal_eval(subprocess.run(
        ['gsettings', 'get', 'org.gnome.shell', 'enabled-extensions'],
        capture_output=True, text=True, check=True).stdout.strip())
except Exception:
    raise SystemExit(0)
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
  gsettings set org.gnome.shell disable-user-extensions false 2>/dev/null || true
  gnome-extensions enable "$UUID" 2>/dev/null || true
}

install_plasma() {
  echo "==> Installing Plasma plasmoid..."
  rm -rf "$PLASMA_DST"
  mkdir -p "$(dirname "$PLASMA_DST")"
  cp -a "$PLASMA_SRC" "$PLASMA_DST"
  mkdir -p "$PLASMA_DST/contents/ui/locales"
  cp -a "$ROOT"/ui/locales/*.json "$PLASMA_DST/contents/ui/locales/"
  cp -a "$ROOT/ui/tokens.json" "$PLASMA_DST/contents/ui/tokens.json"
  if [ -d "$EXT_SRC/icons" ]; then
    mkdir -p "$PLASMA_DST/contents/ui/icons"
    cp -a "$EXT_SRC/icons/." "$PLASMA_DST/contents/ui/icons/"
  fi
  echo "  Add «tokens-go-brrr» to a panel (Edit panel → Add widgets) if it is not already there."
}

case "$UI" in
  gnome) install_gnome ;;
  plasma) install_plasma ;;
  none)
    echo "==> Skipping panel UI (daemon + CLI only)."
    ;;
esac

echo
echo "Done."
echo
echo "Next steps:"
echo "  1. tokens-go-brrr setup"
echo "  2. systemctl --user enable --now tokens-go-brrr.service"
case "$UI" in
  gnome)
    echo "  3. Log out and back in so GNOME Shell loads the extension"
    echo "     (X11 only: Alt+F2, type r, Enter)"
    echo
    echo "Then click the status dot in the top bar."
    ;;
  plasma)
    echo "  3. Add the tokens-go-brrr widget to your panel if needed"
    echo
    echo "Then click the status dot in the panel."
    ;;
  *)
    echo "  3. Use the CLI (tokens-go-brrr status) or install a UI:"
    echo "       ./install.sh --ui=gnome   or   ./install.sh --ui=plasma"
    ;;
esac
echo "Config: $HOME/.config/tokens-go-brrr/config.json"
