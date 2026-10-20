# Contributing

Bug reports, provider fixes and small features are welcome. For anything large,
open an issue first so we can agree on the shape before you spend time on it.

By contributing you agree that your work is released under the [MIT License](LICENSE).

## Ground rules

- **Python stays standard-library only.** The one exception is PyGObject, which comes
  from the distribution. Do not add a PyPI dependency.
- **Fail soft.** A provider that is down, rate limited or logged out shows an error
  row. It never crashes the daemon or the panel.
- **Unknown is not zero.** If a limit cannot be read, show no bar. Never publish a
  healthy `0%` for "unknown". See `AGENTS.md` for the full policy.
- **Do not rename frozen install ids**: the extension UUID, D-Bus names, package
  names, config and data directories, the systemd unit. Display text is fine to change.
- **Treat other tools' logins as read-only.** The one existing exception is the Cursor
  token refresh in `local_auth.py`; do not add another without discussing it first.
  Do not log tokens, and do not send anything beyond the numbers a feature needs.

## Setup and checks

```bash
make test                              # unit tests
make lint                              # ruff check
make format-check                      # ruff format --check; `make format` fixes it
python3 scripts/bump_version.py --check
```

CI runs the same. The tests need PyGObject (`python3-gi`) from your distribution.

If you change anything under `site/`, run `python3 scripts/check_contrast.py` when
colours move. The GNOME extension has a dev loop in `gnome-shell-extension/devtest/`.

## Branches and pull requests

```
feature branch  ->  develop  ->  main  ->  tag vX.Y.Z  ->  draft release
```

- Branch from `develop` and open your pull request against `develop`.
- Keep a pull request to one change. Squash merge is used for features.
- Add or update tests. Parsers and meter logic in particular should have a case for
  malformed input.
- Do not bump the version in a feature pull request. Releases do that
  (`scripts/bump_version.py X.Y.Z`); see `design/RELEASE_AND_DISTRIBUTION.md`.

## Adding or fixing a provider

Providers live in `tokens_go_brrr/providers/` and implement the `Provider` protocol in
`providers/base.py`. Local usage harvesters, which feed the ledger, implement
`Harvester` in `harvesters/base.py`. Both must tolerate missing files, changed
response shapes and network failure. Include a test with a realistic response and one with a
broken one.

Most provider usage endpoints are not documented public APIs and change without
notice. If you find one that moved, say what you observed in the pull request.

## Reporting security problems

Do not open a public issue. See [SECURITY.md](SECURITY.md).
