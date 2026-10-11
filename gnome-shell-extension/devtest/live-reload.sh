#!/usr/bin/env bash
# Stage the working tree as a fresh revision and print the Looking Glass command
# that swaps the running extension for it, with no logout.
#
# Why a revision: GNOME imports an extension from a fixed file path, and
# JavaScript caches modules by path, so reloading the same directory silently
# re-runs the old code. Each revision is a copy under a new uuid, which gives the
# import a path it has not seen.
#
# The script stays running after it prints the command, and restores the
# canonical extension in enabled-extensions when it exits (Enter, Ctrl+C, or the
# terminal closing). Otherwise a throwaway revision uuid can be left in that
# list and the extension fails to load at the next login. Pass --no-wait to skip
# this and clean up yourself with live-reload-reset.sh.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
UUID="tokens-go-brrr@fredrickmakoffu.github.io"
EXT_HOME="$HOME/.local/share/gnome-shell/extensions"
PIDFILE="${XDG_RUNTIME_DIR:-/tmp}/tokens-go-brrr-live-reload.pid"

# A waiter from an earlier run would undo this run's revision when it exits, so
# hand its job over: SIGUSR1 makes it quit without restoring anything.
if [ -f "$PIDFILE" ]; then
  old="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$old" ] && [ "$old" != "$$" ] && kill -0 "$old" 2>/dev/null \
     && grep -q live-reload /proc/"$old"/cmdline 2>/dev/null; then
    kill -USR1 "$old" 2>/dev/null || true
  fi
  rm -f "$PIDFILE"
fi

# Keep the canonical install current too, so an ordinary logout is still correct
# and every staged revision can be thrown away.
mkdir -p "$EXT_HOME"
rm -rf "${EXT_HOME:?}/$UUID"
cp -r "$REPO/gnome-shell-extension/$UUID" "$EXT_HOME/"

NEXT="$(
  python3 - "$EXT_HOME" <<'PYEOF'
import os, re, sys

ext_home = sys.argv[1]
# A revision number must never be reused, even once its directory is gone: the
# shell caches an imported module for the life of the session, so reloading a
# path it has already seen silently runs the old code again. Directories alone
# cannot tell us that, because the reset script deletes them.
marker = os.path.join(ext_home, '.tokens-go-brrr-revision')
try:
    with open(marker) as handle:
        highest = int(handle.read().strip() or 1)
except (OSError, ValueError):
    highest = 1

for name in os.listdir(ext_home):
    found = re.fullmatch(r'tokens-go-brrr-r(\d+)@.*', name)
    if found:
        highest = max(highest, int(found.group(1)))

nxt = highest + 1
with open(marker, 'w') as handle:
    handle.write(str(nxt))
print(nxt)
PYEOF
)"

NEW="tokens-go-brrr-r${NEXT}@fredrickmakoffu.github.io"
rm -rf "${EXT_HOME:?}/$NEW"
cp -r "$REPO/gnome-shell-extension/$UUID" "$EXT_HOME/$NEW"
python3 - "$EXT_HOME/$NEW/metadata.json" "$NEW" "$NEXT" <<'PYEOF'
import json, pathlib, sys
path, uuid, rev = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
meta = json.loads(path.read_text())
meta['uuid'] = uuid
meta['name'] = f'tokens-go-brrr (live reload r{rev})'
path.write_text(json.dumps(meta, indent=2) + '\n')
PYEOF

# Older revisions have done their job. Leaving them behind piles up installs
# that the shell lists as separate extensions, so only the newest is kept. The
# *number* is what must never be reused while this login lasts — the shell has
# those modules cached — not the directory.
for dir in "$EXT_HOME"/tokens-go-brrr-r*@*; do
  [ "$(basename "$dir")" = "$NEW" ] && continue
  rm -rf "$dir"
done

cat <<EOF

Staged r${NEXT}. It replaces whichever copy the shell has loaded, if any.

Press Alt+F2, type lg, press Enter, then paste this and press Enter:

const M = Main.extensionManager; const NEW = '${NEW}'; const mine = M.getUuids().filter(u => /^tokens-go-brrr(-r[0-9]+)?@/.test(u) && M.lookup(u)); await Promise.all(mine.map(u => M.unloadExtension(M.lookup(u)))); const st = new Gio.Settings({schema_id: 'org.gnome.shell'}); st.set_strv('enabled-extensions', st.get_strv('enabled-extensions').filter(u => !/^tokens-go-brrr(-r[0-9]+)?@/.test(u)).concat([NEW])); await M.loadExtension(M.createExtensionObject(NEW, Gio.File.new_for_path(GLib.get_user_data_dir() + '/gnome-shell/extensions/' + NEW), 2)); Main.panel.statusArea[NEW]

Press Escape to close Looking Glass.

To go back to the canonical extension and delete every staged revision:

  ${HERE}/live-reload-reset.sh

EOF

if [ "${1:-}" = "--no-wait" ]; then
  exit 0
fi

echo $$ > "$PIDFILE"
RESTORE=1
cleanup() {
  rm -f "$PIDFILE"
  if [ "$RESTORE" = 1 ]; then
    echo
    "$HERE/live-reload-reset.sh"
  fi
}
trap cleanup EXIT
trap 'exit 0' INT TERM HUP
trap 'RESTORE=0; exit 0' USR1
echo "Leave this running while you test. Press Enter (or Ctrl+C) when done to restore"
echo "the canonical extension in enabled-extensions."
read -r _ || true
