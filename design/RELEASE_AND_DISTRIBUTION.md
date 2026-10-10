# Release and distribution

How a change travels from a feature branch to an installable on a download page.

## Platform reality

Only the Linux/GNOME build exists. The UI is a GNOME Shell extension talking to the
daemon over D-Bus, supervised by a systemd user unit. Windows and macOS are not a
repackaging job: they need a tray/menu-bar client and a non-D-Bus transport
(localhost HTTP/JSON on the daemon). Plan for that as its own piece of work.

| Layer | Linux | Windows | macOS |
|---|---|---|---|
| Core daemon (pure Python) | shared | shared | shared |
| Transport to UI | D-Bus | localhost HTTP | localhost HTTP |
| UI | GNOME extension | tray app | menu-bar app |
| Autostart | systemd user unit | Task Scheduler / Startup | launchd agent |

## Branches

```
feature/*  --PR (squash)-->  develop  --release PR (merge commit)-->  main  --tag vX.Y.Z-->  draft release
hotfix/*   --PR----------------------------------------------------> main  --tag--------->  draft release
                                                   main --auto PR--> develop   (sync-develop.yml)
```

- `develop` is the integration branch. Feature work targets it.
- A release is a PR `develop -> main` that does one thing: bump the version
  (`scripts/bump_version.py X.Y.Z`). Use a merge commit so history stays traceable.
- A hotfix branches from `main`, PRs straight to `main`, and is tagged immediately.
  `sync-develop.yml` then opens a PR carrying it back to `develop`.
- You release by pushing the tag, not by merging. Merging to `main` alone ships nothing.

```
git switch main && git pull
git tag v0.6.0 && git push origin v0.6.0
```

## Version

`pyproject.toml` is the source of truth. `scripts/bump_version.py` also updates
`cursor_spend_monitor/__init__.py` and the extension's `metadata.json`
(`version-name`). CI fails if they disagree, and the release job fails if the tag
differs from the code.

## Build

Each distro package is built in a throwaway container, so Fedora and Debian builds
work the same on your laptop and in CI.

```
make rpm        # Fedora   -> dist/*.rpm
make deb        # Debian   -> dist/*.deb
make packages   # both, plus SHA256SUMS and manifest.json
```

`packaging/stage.sh` lays the files out once (FHS paths); the RPM spec and the DEB
builder both call it so the packages cannot drift.

| Installed to | What |
|---|---|
| `/usr/bin/cursor-spend-monitor`, Python site/dist-packages | daemon + CLI |
| `/usr/share/gnome-shell/extensions/<uuid>/` | GNOME extension |
| `/usr/lib/systemd/user/cursor-spend-monitor.service` | user unit |
| `/usr/share/fonts/ai-usage/` | Barlow (SIL OFL) |

Targets: the RPM is built on the current `fedora:latest` and pins that release's
Python ABI, so build one per Fedora release you support. The DEB is built on Debian
stable. The code needs Python >= 3.11, so Ubuntu 22.04 (3.10) is not supported.

## Release pipeline

`release.yml`, on a `v*` tag, or run by hand from the Actions tab (**Release >
Run workflow**, on `main`) when there is no terminal to push a tag from:

1. Check the tag equals the code version and the commit is on `main`.
2. Run the tests, build rpm + deb, write `SHA256SUMS` and `manifest.json`.
3. Create a **draft** GitHub release with those files.

A manual run takes the version from the code, refuses any branch but `main`, and
creates the `v<version>` tag itself only after the build and tests have passed,
so a broken build leaves no tag. Re-running is safe: a tag already on that commit
is reused, and one on another commit stops the release.

Audit step: download the draft's artifacts, install in a VM, run
`design/QA_CHECKLIST.md`, then press **Publish**. Windows and macOS jobs slot into
the same workflow later.

## Download site

A static `site/` (plain HTML/CSS/JS, Barlow, the same palette) that reads
`manifest.json` of the latest published release and renders one card per platform:
version, size, sha256, install command, with the visitor's OS highlighted. Platforms
not built yet show "coming soon". Not built yet.

## GitHub Free plan constraints

Verify against GitHub's current plan page; these were true when this was written.

| Constraint | Effect |
|---|---|
| Repo is currently **private** | Release assets need a signed-in viewer, so a public download page cannot link to them. |
| Pages on Free requires a **public** repo | Same decision as above. |
| Branch protection / rulesets need a public repo on Free | Private: the "PRs only, CI must pass" rules are convention, not enforced. |
| Actions: 2,000 min/month on private repos (unlimited on public) | Linux builds are ~1-3 min each; fine. Windows runs count 2x, macOS 10x: build them only on tags. |

**Decision needed: make the repo public.** It unlocks Pages, unlimited Actions
minutes, and enforceable branch protection, and it makes release downloads linkable.
Before flipping it: grep history for secrets, and add a LICENSE (there is none today;
the RPM spec carries a placeholder). The alternative is keeping the code private and
publishing releases to a separate public repo, or hosting the site and files on
Cloudflare Pages/R2, at the cost of extra moving parts.

## Later

- GPG-sign the RPM/DEB and publish a dnf/apt repo so updates are automatic.
- Windows: PyInstaller + Inno Setup. macOS: py2app + `create-dmg`. Unsigned builds
  trigger SmartScreen / Gatekeeper warnings.
