#!/usr/bin/env bash
# Walk every popover screen in a throwaway headless Shell and fail if any of
# them lays out to an impossible size.
#
# Why this exists: a Clutter allocation warning ("tried to allocate a size of
# 360.00 x -2147483648.00") is a *layout* bug, not noise, and it is invisible to
# every other kind of test — no exception is thrown, the JS all runs, and the
# popover is simply drawn as nothing. That is exactly how a negative
# `margin-bottom` on one label made clicking Latest appear to close the menu.
#
# Nothing here needs a display, a mouse, or the real daemon:
#   * the mock daemon supplies state (including a billboard and a latest message)
#   * `--unsafe-mode` re-enables org.gnome.Shell.Eval, which drives the screens
#   * the Shell's own log is the assertion
#
# One trap worth knowing, because it cost an afternoon: the *D-Bus* Eval method
# evaluates a plain script. Unlike the Alt+F2 Looking Glass console, neither
# `await` nor `return` is available to it ("SyntaxError: await is only valid in
# async functions", "return not in function"). Sequencing is therefore done with
# a GLib timeout chain, and the driver reports itself through the log rather than
# through a return value.
#
# Usage: ./layout-smoke.sh [seconds-to-wait-for-startup]
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
UUID="ai-usage@fredrickmakoffu.github.io"
BOOT="${1:-12}"
RUNTIME="$(mktemp -d)"
LOG="$RUNTIME/shell.log"

mkdir -p "$RUNTIME"/config/glib-2.0/settings "$RUNTIME"/data/gnome-shell/extensions "$RUNTIME"/cache
ln -sfn "$REPO/gnome-shell-extension/$UUID" "$RUNTIME/data/gnome-shell/extensions/$UUID"
# The shell resolves Barlow through fontconfig, which reads $XDG_DATA_HOME/fonts.
ln -sfn "$REPO/gnome-shell-extension/$UUID/fonts" "$RUNTIME/data/fonts"

# A keyfile settings backend, so the test never touches the real session's
# enabled-extensions.
cat >"$RUNTIME/config/glib-2.0/settings/keyfile" <<EOF
[org/gnome/shell]
enabled-extensions=['$UUID']
disable-user-extensions=false
welcome-dialog-last-shown-version='99.0'

[org/gnome/desktop/interface]
color-scheme='${SCHEME:-default}'
EOF

read -r -d '' DRIVER <<'JS'
const i = Main.panel.statusArea['ai-usage@fredrickmakoffu.github.io'];
if (!i) {
    log('[layout-smoke] extension not loaded');
} else {
    const screens = ['list', 'guide', 'about', 'landing', 'earlier', 'detail', 'sessions'];
    let n = 0;

    // Structure, not pixels. Each of these was a bug once, and each is a
    // property of the actor tree the screen builds, so it can be asserted here
    // instead of being looked at in a live session.
    const collect = (root, styleClass) => {
        const found = [];
        const walk = (actor) => {
            if (actor.style_class === styleClass) found.push(actor);
            for (const child of actor.get_children ? actor.get_children() : [])
                walk(child);
        };
        walk(root);
        return found;
    };
    const texts = (root) => {
        const found = [];
        const walk = (actor) => {
            if (typeof actor.text === 'string') found.push(actor.text);
            for (const child of actor.get_children ? actor.get_children() : [])
                walk(child);
        };
        walk(root);
        return found;
    };
    const checkLanding = () => {
        try {
            const root = i.menu.box;
            // The insight is a headline and an optional body, not a quote
            // between marks, and Latest is not offered from the page it opens.
            if (collect(root, 'ai-usage-title').length !== 1)
                log('[layout-smoke] the landing page needs exactly one headline');
            if (texts(root).includes('Latest'))
                log('[layout-smoke] the landing page offers Latest, which is itself');
            const cont = collect(root, 'ai-usage-primary-btn')[0];
            if (!cont) log('[layout-smoke] no Continue button on the landing page');
            else if (!cont.x_expand) log('[layout-smoke] Continue should fill the row');
        } catch (e) {
            // A broken assertion must not take the walk down with it: reported
            // here, it still fails the run rather than passing quietly.
            log('[layout-smoke] landing check threw: ' + e.message);
        }
    };
    const checkList = () => {
        try {
            if (i._state && i._state.latestMessage
                && !texts(i.menu.box).includes('Latest'))
                log('[layout-smoke] Latest is missing from the list screen');
        } catch (e) {
            log('[layout-smoke] list check threw: ' + e.message);
        }
    };

    i.menu.open();
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
        if (n < screens.length) {
            const name = screens[n++];
            const toolId = i.tools && i.tools.length ? i.tools[0].id : null;
            try {
                i._navigate(name, toolId);
            } catch (e) {
                log('[layout-smoke] ' + name + ' threw: ' + e.message);
            }
            if (name === 'landing') checkLanding();
            if (name === 'list') checkList();
            return GLib.SOURCE_CONTINUE;
        }
        // Behaviour, not layout: Continue has to get the user out of this
        // screen. It once did not, because the proxy's interface XML declared
        // no Acknowledge method and the missing call threw before the
        // navigation ran — stranding anyone who opened the page.
        i._landingMode = 'latest';
        i._navigate('landing');
        const before = i._screen;
        try {
            i._leaveLanding();
        } catch (e) {
            log('[layout-smoke] leaveLanding threw: ' + e.message);
        }
        if (before !== 'landing' || i._screen !== 'list') {
            log('[layout-smoke] continue FAILED: was ' + before + ', now ' + i._screen);
        }
        log('[layout-smoke] walked ' + n + ' screens');
        return GLib.SOURCE_REMOVE;
    });
}
'started'
JS

export XDG_CONFIG_HOME="$RUNTIME/config" XDG_DATA_HOME="$RUNTIME/data" \
      XDG_CACHE_HOME="$RUNTIME/cache" GSETTINGS_BACKEND=keyfile
# Exported because the driver is evaluated by the *inner* shell: DRIVER is
# referenced inside the escaped string below, so without this it expands to
# nothing and the test walks no screens at all.
export DRIVER

dbus-run-session -- bash -c "
  python3 '$HERE/mock_daemon.py' '$REPO' >'$RUNTIME/mock.log' 2>&1 &
  sleep 1
  gnome-shell --headless --virtual-monitor 1280x720 --no-x11 --unsafe-mode >'$LOG' 2>&1 &
  SHELL_PID=\$!
  sleep $BOOT
  gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell \
    --method org.gnome.Shell.Eval \"\$DRIVER\" >'$RUNTIME/eval.log' 2>&1
  sleep 6
  kill \$SHELL_PID 2>/dev/null
  kill %1 2>/dev/null
" 2>/dev/null

echo
if [ ! -s "$LOG" ]; then
      echo "FAIL: the shell produced no log at all; it never started."
      echo "      (check that gnome-shell can run with --headless here)"
      exit 2
fi

if grep -q "\[layout-smoke\] extension not loaded" "$LOG" 2>/dev/null; then
      echo "FAIL: the extension was not loaded in the nested shell."
      exit 2
fi

# Eval's return value does not survive gdbus here, so the driver announces
# itself in the log instead. Without this, a driver that never ran would look
# exactly like a clean pass — which is worse than having no test.
if ! grep -q "\[layout-smoke\] walked" "$LOG" 2>/dev/null; then
      echo "FAIL: the screen driver never ran, so nothing was actually tested."
      echo "      Eval said: $(head -c 200 "$RUNTIME/eval.log" 2>/dev/null)"
      exit 2
fi

ALLOCATIONS="$(grep -c "tried to allocate a size" "$LOG" 2>/dev/null)"
THROWN="$(grep -c "\[layout-smoke\].*threw" "$LOG" 2>/dev/null)"
CONTINUE_BROKE="$(grep -c "\[layout-smoke\] continue FAILED" "$LOG" 2>/dev/null)"

if [ "${CONTINUE_BROKE:-0}" != "0" ]; then
  echo "FAIL: Continue did not return to the provider list."
  grep "\[layout-smoke\] continue FAILED" "$LOG" | head -3
  echo
  echo "The landing page must always be escapable — check that nothing in"
  echo "_leaveLanding() can throw before it navigates."
  exit 1
fi

# Anything else the driver reports is a failed expectation: the success path logs
# only the screen walk. A new assertion in the driver is therefore enforced here
# without needing a matching branch, which is how it should be.
UNEXPECTED="$(grep '\[layout-smoke\]' "$LOG" 2>/dev/null | grep -vc 'walked .* screens')"
if [ "${UNEXPECTED:-0}" != "0" ]; then
  echo "FAIL: $UNEXPECTED unexpected condition(s) from the driver:"
  grep '\[layout-smoke\]' "$LOG" | grep -v 'walked .* screens' | head -5
  exit 1
fi

if [ "${ALLOCATIONS:-0}" != "0" ] || [ "${THROWN:-0}" != "0" ]; then
      echo "FAIL: $ALLOCATIONS allocation warning(s), $THROWN screen(s) threw."
      echo
      grep "tried to allocate a size" "$LOG" | sort -u | head -10
      grep "\[layout-smoke\].*threw" "$LOG" | head -10
      echo
      echo "A negative height means a box is subtracting more than it has —"
      echo "look for a negative margin or an unset dimension in that screen's CSS."
      exit 1
fi

echo "PASS: $(grep -o 'walked [0-9]* screens' "$LOG" | head -1) and every one laid"
echo "      out cleanly (0 allocation warnings)."
