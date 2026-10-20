# Third-party notices

tokens-go-brrr is released under the [MIT License](LICENSE). This file lists what
else is in the repository or on the download site, and under what terms.

## Fonts

**Barlow** and **Barlow Condensed**, copyright 2017 The Barlow Project Authors
(<https://github.com/jpt/barlow>), SIL Open Font License 1.1. The font files and
the full license text are in
`gnome-shell-extension/tokens-go-brrr@fredrickmakoffu.github.io/fonts/` (`OFL.txt`).
Packages install the license text to `/usr/share/licenses/tokens-go-brrr/OFL.txt`.

The download site (`site/`) loads the same families from Google Fonts at view time.

## Trademarks and logos

The provider logos in `gnome-shell-extension/tokens-go-brrr@fredrickmakoffu.github.io/icons/`
and in the site are used only to identify the service a meter belongs to:

| Name | Owner |
| --- | --- |
| Claude, Claude Code | Anthropic, PBC |
| Codex | OpenAI |
| Cursor | Anysphere Inc. |
| OpenCode | its respective owners |
| Pi | its respective owners |

They are not covered by this project's MIT license. They remain the property of their
owners, and their use here does not imply affiliation with or endorsement by them.
If you are a rights holder and want a logo removed or replaced, open an issue.

## Download site dependencies

`site/index.html` loads these from a CDN at view time. They are not bundled in the
repository or in any package.

| Library | Version | License |
| --- | --- | --- |
| React and React DOM | 18.3.1 | MIT |
| @babel/standalone | 7.29.0 | MIT |

## Python and system dependencies

The daemon uses only the Python standard library, plus PyGObject (LGPL-2.1-or-later)
from the distribution for D-Bus and notifications. PyGObject is installed by your
package manager, not shipped here.
