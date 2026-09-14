#!/usr/bin/env bash
# Stage the working tree as a fresh revision and print the Looking Glass command
# that swaps the running extension for it, with no logout.
#
# Why a revision: GNOME imports an extension from a fixed file path, and
# JavaScript caches modules by path, so reloading the same directory silently
# re-runs the old code. Each revision is a copy under a new uuid, which gives the
# import a path it has not seen.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
UUID="ai-usage@fredrickmakoffu.github.io"
EXT_HOME="$HOME/.local/share/gnome-shell/extensions"

# Keep the canonical install current too, so an ordinary logout lands on this code
# and every staged revision can be thrown away.
mkdir -p "$EXT_HOME"
rm -rf "${EXT_HOME:?}/$UUID"
cp -r "$REPO/gnome-shell-extension/$UUID" "$EXT_HOME/"

read -r CURRENT NEXT <<<"$(python3 - "$EXT_HOME" "$UUID" <<'PY'
import ast, os, re, subprocess, sys

ext_home, uuid = sys.argv[1], sys.argv[2]
enabled = ast.literal_eval(subprocess.run(
    ['gsettings', 'get', 'org.gnome.shell', 'enabled-extensions'],
    capture_output=True, text=True, check=True).stdout.strip())

# whichever of ours the shell is running right now: the canonical one on a fresh
# login, or the last revision that was loaded into this session
current = next((u for u in enabled if u.startswith('ai-usage')), uuid)

revisions = [int(m.group(1)) for name in os.listdir(ext_home)
             if (m := re.fullmatch(r'ai-usage-r(\d+)@.*', name))]
print(current, max(revisions, default=1) + 1)
PY
)"

NEW="ai-usage-r${NEXT}@fredrickmakoffu.github.io"
rm -rf "${EXT_HOME:?}/$NEW"
cp -r "$REPO/gnome-shell-extension/$UUID" "$EXT_HOME/$NEW"
python3 - "$EXT_HOME/$NEW/metadata.json" "$NEW" "$NEXT" <<'PY'
import json, pathlib, sys
path, uuid, rev = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
meta = json.loads(path.read_text())
meta['uuid'] = uuid
meta['name'] = f'AI Usage (live reload r{rev})'
path.write_text(json.dumps(meta, indent=2) + '\n')
PY

cat <<EOF

Staged r${NEXT}.  Replacing: ${CURRENT}

Press Alt+F2, type lg, press Enter, then paste this and press Enter:

const M = Main.extensionManager; const OLD = '${CURRENT}'; const NEW = '${NEW}'; await M.unloadExtension(M.lookup(OLD)); const st = new Gio.Settings({schema_id: 'org.gnome.shell'}); st.set_strv('enabled-extensions', st.get_strv('enabled-extensions').filter(u => u !== OLD).concat([NEW])); await M.loadExtension(M.createExtensionObject(NEW, Gio.File.new_for_path(GLib.get_user_data_dir() + '/gnome-shell/extensions/' + NEW), 2)); Main.panel.statusArea[NEW]

Press Escape to close Looking Glass.

To go back to the canonical extension and delete every staged revision:

  ${HERE}/live-reload-reset.sh

EOF
