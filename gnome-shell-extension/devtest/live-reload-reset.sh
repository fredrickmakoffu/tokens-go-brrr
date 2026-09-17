#!/usr/bin/env bash
# Point the shell back at the canonical extension and delete staged revisions.
# The switch itself takes effect at the next login; the deletions are immediate.
set -euo pipefail

UUID="ai-usage@fredrickmakoffu.github.io"
EXT_HOME="$HOME/.local/share/gnome-shell/extensions"

python3 - "$UUID" <<'PY'
import ast, re, subprocess, sys
uuid = sys.argv[1]
enabled = ast.literal_eval(subprocess.run(
    ['gsettings', 'get', 'org.gnome.shell', 'enabled-extensions'],
    capture_output=True, text=True, check=True).stdout.strip())
kept = [u for u in enabled if not re.match(r'ai-usage(-r\d+)?@', u)]
kept.append(uuid)
subprocess.run(['gsettings', 'set', 'org.gnome.shell', 'enabled-extensions', repr(kept)], check=True)
print('enabled-extensions ->', kept)
PY

removed=0
for dir in "$EXT_HOME"/ai-usage-r*@*; do
  [ -e "$dir" ] || continue
  rm -rf "$dir"
  echo "removed $(basename "$dir")"
  removed=$((removed + 1))
done
[ "$removed" -eq 0 ] && echo "no staged revisions to remove"

# The marker is deliberately kept: revision numbers must never be reused while
# this login lasts, because the shell still has their modules cached.

echo
echo "The running shell still has the last revision loaded; the canonical one takes"
echo "over at your next login."
