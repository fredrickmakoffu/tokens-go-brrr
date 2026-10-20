# Security policy

tokens-go-brrr reads login tokens that other tools store on your machine (Claude Code,
Cursor, OpenCode, Codex), so credential handling is the part that matters most.

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Use GitHub's private reporting: on the repository page go to **Security** then
**Report a vulnerability**. Include what you found, how to reproduce it, and which
version you tested (the panel's About screen shows it).

I will acknowledge a report within a few days and tell you what I plan to do about it.
This is a one-person project, so please be patient, and I will credit you in the
release notes if you want that.

## Supported versions

Only the latest release gets fixes.

## What counts

Things I want to hear about:

- A credential or token written to disk, a log, the LLM call log, the state file or
  a notification, or sent to any host other than the provider it belongs to.
- The daemon refreshing, rotating or modifying another tool's login or files, other
  than the Cursor token refresh the README describes.
- A way for another local user or process to read data the daemon exposes (D-Bus
  interface, state file, ledger, history database) beyond what its file permissions
  intend.
- The update flow installing anything other than the package whose sha256 the
  manifest lists, or running with more privilege than the single `pkexec` install.
- Command or path injection through provider responses, project names or file names.

Not security issues: a provider changing or removing its usage endpoint, and wrong
numbers from a provider's own API. Those are ordinary bugs.

## Known limits

- Updates are checked against a sha256 from the same release as the package, so they
  protect against a corrupted download, not a compromised release. Packages are not
  GPG-signed yet.
- Anyone who can read your home directory can read the logins the other tools keep
  there. This project does not make that better or worse.

## What the daemon does with credentials

See the **Privacy** section of the [README](README.md) for what is read, where it is
sent, and how to turn the optional network features off.
