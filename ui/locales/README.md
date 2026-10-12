# Shared locale catalogs

JSON catalogs here are the shared source for panel chrome strings. The GNOME
extension still ships `locales.js` (GJS cannot import JSON the same way); keep
keys and English wording in sync when you add a string.

Plasma loads `en.json` / `fr.json` / `pt-BR.json` from the plasmoid package
(copied at stage time from this directory).

Not translated on purpose: product name, provider names, commands, paths.
