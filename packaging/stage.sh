#!/usr/bin/env bash
# Lay the installed files out under DESTDIR using FHS paths. Shared by the RPM
# and DEB builds so the two packages cannot drift apart.
#
#   packaging/stage.sh DESTDIR
set -euo pipefail

DEST="${1:?usage: stage.sh DESTDIR}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UUID="ai-usage@fredrickmakoffu.github.io"
EXT_SRC="$ROOT/gnome-shell-extension/$UUID"

# Daemon + CLI. --no-deps: the only runtime dependency is the distro's PyGObject.
python3 -m pip install --root "$DEST" --prefix /usr --no-deps --no-build-isolation \
  --no-compile --disable-pip-version-check "$ROOT"

# GNOME Shell extension.
install -d "$DEST/usr/share/gnome-shell/extensions/$UUID"
cp -r "$EXT_SRC/." "$DEST/usr/share/gnome-shell/extensions/$UUID/"
# Fonts are installed system-wide instead (below); don't ship them twice.
rm -rf "$DEST/usr/share/gnome-shell/extensions/$UUID/fonts"

# Always present (possibly empty) so the RPM file list is never empty.
install -d "$DEST/usr/share/licenses/cursor-spend-monitor"

# Barlow, the design system's typeface (SIL OFL).
if compgen -G "$EXT_SRC/fonts/*.ttf" >/dev/null; then
  install -d "$DEST/usr/share/fonts/ai-usage"
  install -m 0644 "$EXT_SRC"/fonts/*.ttf "$DEST/usr/share/fonts/ai-usage/"
  [ -f "$EXT_SRC/fonts/OFL.txt" ] && install -m 0644 "$EXT_SRC/fonts/OFL.txt" "$DEST/usr/share/licenses/cursor-spend-monitor/OFL.txt"
fi

# systemd user unit: same as the dev one, but the binary lives in /usr/bin.
install -d "$DEST/usr/lib/systemd/user"
sed 's|%h/.local/bin/cursor-spend-monitor|/usr/bin/cursor-spend-monitor|' \
  "$ROOT/systemd/cursor-spend-monitor.service" \
  > "$DEST/usr/lib/systemd/user/cursor-spend-monitor.service"

# Strip bytecode and build leftovers that must not land in the package.
find "$DEST" -name '__pycache__' -type d -prune -exec rm -rf {} +
