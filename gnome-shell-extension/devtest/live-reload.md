# Reloading the extension without logging out

GNOME Shell scans for extensions only at startup, and Wayland cannot restart the shell in
place, so an edited extension normally waits for your next login. It does not have to.

## The short version

```bash
./gnome-shell-extension/devtest/live-reload.sh
```

It prints a line. Press <kbd>Alt</kbd>+<kbd>F2</kbd>, type `lg`, press <kbd>Enter</kbd>,
paste the line into the prompt at the bottom, press <kbd>Enter</kbd>, then <kbd>Esc</kbd>.
The indicator is replaced in place, with no windows disturbed and nothing else in the
session touched.

When you are finished:

```bash
./gnome-shell-extension/devtest/live-reload-reset.sh
```

That points the shell back at the canonical extension and deletes the staged copies. The
switch takes effect at your next login.

## Why a copy is needed

The three obvious routes are all dead ends:

- `org.gnome.Shell.Extensions.ReloadExtension` over D-Bus refuses, reporting that it is
  deprecated and non-functional.
- Disabling and re-enabling only calls `disable()` and `enable()` on the object that is
  already loaded. It never re-reads the file.
- Running a second shell nested in a window is gone from this build, despite
  `--display-server` still describing itself as the opposite of nested. Mutter takes the
  native path and fails on `TakeControl`, because the real session already holds it.

The reason all three fail is the same. The shell loads an extension with
`import(extensionJs.get_uri())`, and JavaScript caches modules by URI. Re-importing the same
path returns the module that is already in memory, so the old code keeps running even though
the file on disk has changed. `ExtensionManager` half-admits this: `_canLoad` refuses to
reload an extension whose version changed while unloaded, with the message *"A different
version was loaded previously. You need to log out for changes to take effect."*

Give the import a path it has not seen and the problem disappears. Each revision is a copy
of the extension under a new uuid, `ai-usage-rN@fredrickmakoffu.github.io`, so its
`extension.js` sits at a URI nothing has imported yet. That is all `live-reload.sh` does:
refresh the canonical install so an ordinary logout is still correct, copy it to the next
free revision, rewrite `uuid` and `name` in the copy's `metadata.json`, then print the
command that swaps them.

## What the pasted command does

Looking Glass evaluates its input as the body of an async function with `Main`, `Gio` and
`GLib` in scope, so `await` works and several statements can share one line. In order it:

1. unloads the extension that is running, which destroys the indicator and disconnects the
   daemon proxy through the extension's own `disable()`;
2. rewrites `enabled-extensions`, swapping the old uuid for the new one, because an
   extension that is not in that list gets disabled again immediately;
3. builds an extension object pointing at the new directory and loads it, which imports the
   fresh `extension.js` and re-reads `stylesheet.css`;
4. returns the new panel indicator, so a result other than `null` means it worked.

## Things worth knowing

- **Every reload needs a new revision.** Once `r2` is loaded, its path is cached too, so the
  next reload has to be `r3`. The script tracks this by looking at what is already staged.
- **The running shell keeps the last revision** until you log out. The reset script cannot
  undo that from outside, and it does not pretend to.
- **The canonical install is always current.** `live-reload.sh` refreshes it on every run, so
  logging out at any point lands on the same code, under the real uuid.
- **A failed paste costs a logout, not a crash.** If the load throws, the indicator is gone
  until the next login; the error is visible in Looking Glass and in `journalctl /usr/bin/gnome-shell`.
- **Only the extension reloads.** The daemon is a separate systemd service and is unaffected,
  so usage data keeps flowing across reloads. Restart it with
  `systemctl --user restart cursor-spend-monitor.service` when the Python side changes.
