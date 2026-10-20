#!/usr/bin/env bash
# Lay installed files under DESTDIR using FHS paths.
#
#   packaging/stage.sh DESTDIR [daemon|gnome|plasma|all]
#
# Shared by RPM/DEB builds so packages cannot drift. Default is `all` (legacy
# single-tree staging). Split builds call each component separately.
set -euo pipefail

DEST="${1:?usage: stage.sh DESTDIR [daemon|gnome|plasma|all]}"
COMP="${2:-all}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UUID="tokens-go-brrr@fredrickmakoffu.github.io"
EXT_SRC="$ROOT/gnome-shell-extension/$UUID"
PLASMA_ID="org.tokensgobrrr.panel"
PLASMA_SRC="$ROOT/plasma/$PLASMA_ID"

stage_daemon() {
  # Daemon + CLI. --no-deps: the only runtime dependency is the distro's PyGObject.
  python3 -m pip install --root "$DEST" --prefix /usr --no-deps --no-build-isolation \
    --no-compile --disable-pip-version-check "$ROOT"

  install -d "$DEST/usr/share/licenses/tokens-go-brrr"
  install -m 0644 "$ROOT/LICENSE" "$DEST/usr/share/licenses/tokens-go-brrr/LICENSE"

  if compgen -G "$EXT_SRC/fonts/*.ttf" >/dev/null; then
    install -d "$DEST/usr/share/fonts/tokens-go-brrr"
    install -m 0644 "$EXT_SRC"/fonts/*.ttf "$DEST/usr/share/fonts/tokens-go-brrr/"
    [ -f "$EXT_SRC/fonts/OFL.txt" ] && \
      install -m 0644 "$EXT_SRC/fonts/OFL.txt" "$DEST/usr/share/licenses/tokens-go-brrr/OFL.txt"
  fi

  install -d "$DEST/usr/lib/systemd/user"
  sed 's|%h/.local/bin/tokens-go-brrr|/usr/bin/tokens-go-brrr|' \
    "$ROOT/systemd/tokens-go-brrr.service" \
    > "$DEST/usr/lib/systemd/user/tokens-go-brrr.service"

  # Shared visual tokens for panel clients (optional read; UIs also ship a copy).
  install -d "$DEST/usr/share/tokens-go-brrr/ui"
  install -m 0644 "$ROOT/ui/tokens.json" "$DEST/usr/share/tokens-go-brrr/ui/tokens.json"
}

stage_gnome() {
  install -d "$DEST/usr/share/gnome-shell/extensions/$UUID"
  cp -r "$EXT_SRC/." "$DEST/usr/share/gnome-shell/extensions/$UUID/"
  rm -rf "$DEST/usr/share/gnome-shell/extensions/$UUID/fonts"
}

stage_plasma() {
  [ -d "$PLASMA_SRC" ] || { echo "missing $PLASMA_SRC" >&2; exit 1; }
  install -d "$DEST/usr/share/plasma/plasmoids/$PLASMA_ID"
  cp -a "$PLASMA_SRC/." "$DEST/usr/share/plasma/plasmoids/$PLASMA_ID/"
  # Locales + tokens from ui/ so the plasmoid does not drift from the shared source.
  install -d "$DEST/usr/share/plasma/plasmoids/$PLASMA_ID/contents/ui/locales"
  install -m 0644 "$ROOT"/ui/locales/*.json \
    "$DEST/usr/share/plasma/plasmoids/$PLASMA_ID/contents/ui/locales/"
  install -m 0644 "$ROOT/ui/tokens.json" \
    "$DEST/usr/share/plasma/plasmoids/$PLASMA_ID/contents/ui/tokens.json"
  # Provider marks (same assets as the GNOME extension).
  if [ -d "$EXT_SRC/icons" ]; then
    install -d "$DEST/usr/share/plasma/plasmoids/$PLASMA_ID/contents/ui/icons"
    cp -a "$EXT_SRC/icons/." "$DEST/usr/share/plasma/plasmoids/$PLASMA_ID/contents/ui/icons/"
  fi
}

case "$COMP" in
  daemon) stage_daemon ;;
  gnome) stage_gnome ;;
  plasma) stage_plasma ;;
  all)
    stage_daemon
    stage_gnome
    stage_plasma
    ;;
  *)
    echo "usage: stage.sh DESTDIR [daemon|gnome|plasma|all]" >&2
    exit 2
    ;;
esac

find "$DEST" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
