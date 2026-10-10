#!/usr/bin/env bash
# Headless Shell + mock daemon; drive each popover screen via Eval and screenshot it.
# SCHEME=prefer-light ./capture-screens.sh <out-dir> captures the light theme.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; REPO="$(cd "$HERE/../.." && pwd)"
UUID="ai-usage@fredrickmakoffu.github.io"
OUT="$(realpath -m "${1:-$REPO/design/screens/shots}")"; RUNTIME="$(mktemp -d)"
mkdir -p "$OUT" "$RUNTIME"/config/glib-2.0/settings "$RUNTIME"/data/gnome-shell/extensions "$RUNTIME"/cache
ln -sfn "$REPO/gnome-shell-extension/$UUID" "$RUNTIME/data/gnome-shell/extensions/$UUID"
# The shell resolves Barlow through fontconfig, which reads $XDG_DATA_HOME/fonts.
ln -sfn "$REPO/gnome-shell-extension/$UUID/fonts" "$RUNTIME/data/fonts"
cat >"$RUNTIME/config/glib-2.0/settings/keyfile" <<KF
[org/gnome/shell]
enabled-extensions=['$UUID']
disable-user-extensions=false
welcome-dialog-last-shown-version='99.0'

[org/gnome/desktop/interface]
color-scheme='${SCHEME:-prefer-dark}'
KF
export XDG_CONFIG_HOME="$RUNTIME/config" XDG_DATA_HOME="$RUNTIME/data" XDG_CACHE_HOME="$RUNTIME/cache" GSETTINGS_BACKEND=keyfile OUT
cat > "$RUNTIME/inner.sh" <<'INNER'
ev() { gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell --method org.gnome.Shell.Eval "$1" >/dev/null 2>&1; }
I="const i = Main.panel.statusArea['ai-usage@fredrickmakoffu.github.io'];"
shot() {
  sleep 0.8
  ev "$I const a = i.menu.actor; const [x,y] = a.get_transformed_position(); const [w,h] = a.get_transformed_size(); log('[cap] $1 ' + [x,y,w,h].map(Math.round).join(' '));"
  gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell/Screenshot --method org.gnome.Shell.Screenshot.Screenshot false false "$OUT/full-$1.png" >/dev/null 2>&1
}
ev "$I i.menu.open(); i._navigate('list');"; sleep 1
ev "$I log('[cap] tools ' + i.tools.map(t => t.id).join(','));"
:
for k in rolling weekly monthly; do ev "$I i._selectWindow('$k');"; shot "list-$k"; done
ev "$I i._selectWindow('rolling');"
for n in 0 1 2 3; do ev "$I if (i.tools[$n]) i._navigate('detail', i.tools[$n].id);"; shot "detail-$n"; done
ev "$I i._navigate('sessions', i.tools[0].id);"; shot sessions-active
ev "$I i._sessionsFilter = 'paused'; i._render(false);"; shot sessions-paused
ev "$I i._landingMode = 'fresh'; i._navigate('landing');"; shot landing
ev "$I i._landingMode = 'latest'; i._navigate('landing');"; shot landing-latest
ev "$I i._navigate('earlier');"; shot earlier
ev "$I i._navigate('guide');"; shot guide
ev "$I i._navigate('about');"; shot about
INNER
dbus-run-session -- bash -c "
  python3 '$HERE/mock_daemon.py' '$REPO' >'$RUNTIME/mock.log' 2>&1 &
  sleep 1
  gnome-shell --headless --virtual-monitor 1280x900 --no-x11 --unsafe-mode >'$RUNTIME/shell.log' 2>&1 &
  SP=\$!; sleep 12
  bash '$RUNTIME/inner.sh'
  kill \$SP; kill %1
" 2>/dev/null
grep '\[cap\]' "$RUNTIME/shell.log" | sed 's/.*\[cap\] //' > "$OUT/bounds.txt"
grep -iE 'error|exception' "$RUNTIME/shell.log" | grep -i ai-usage | head -5
cat "$OUT/bounds.txt"; ls "$OUT"
# Crop each full-screen shot down to the popover.
cd "$OUT" && python3 -I - <<'PY'
from PIL import Image
import os
for line in open('bounds.txt'):
    p = line.split()
    if p[0] == 'tools': continue
    x, y, w, h = map(int, p[1:])
    Image.open(f'full-{p[0]}.png').crop((x, y, x + w, y + h)).save(f'{p[0]}.png')
    os.remove(f'full-{p[0]}.png')
PY
