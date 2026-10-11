"""The translation catalogs stay in step with English.

A missing key falls back to English at runtime, so a gap is silent: nothing
fails, one language just quietly stops being translated. These tests make the
gap loud. They read the catalogs with node, since both are JavaScript, and skip
where node is not installed.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "gnome-shell-extension" / "tokens-go-brrr@fredrickmakoffu.github.io"
SITE = ROOT / "site"

# Strings that are the same in every language on purpose (brand and brand-like).
SAME_EVERYWHERE = {"brand", "dl.kind.rpm", "dl.kind.deb"}

EXT_SCRIPT = """
import { CATALOGS } from "%s";
console.log(JSON.stringify(CATALOGS));
""" % (EXT / "locales.js").as_uri()

# The site's i18n.js is a browser IIFE; run it against a stub window and read the
# catalogs back through t() by asking for every key in each locale.
SITE_SCRIPT = r"""
const fs = require("fs");
const vm = require("vm");
const src = fs.readFileSync(process.argv[1], "utf8");
const cats = {};
const ctx = {
  window: {}, navigator: { languages: ["en"], language: "en" }, location: { search: "" },
  localStorage: { getItem() { return null; }, setItem() {} },
  document: { documentElement: { setAttribute() {}, removeAttribute() {} }, querySelector() { return null; }, title: "" },
  Intl, URLSearchParams,
};
// Expose the catalogs: the script keeps them in closure variables, so hand them
// out by patching the one line that builds CATALOGS.
const patched = src.replace("var CATALOGS = { en: en, fr: fr, \"pt-BR\": pt };", "var CATALOGS = { en: en, fr: fr, \"pt-BR\": pt }; window.__CATALOGS = CATALOGS;");
vm.runInNewContext(patched, ctx);
console.log(JSON.stringify(ctx.window.__CATALOGS));
"""


def _normal(key: str) -> str:
    return re.sub(r"_(zero|one|two|few|many|other)$", "", key)


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class LocaleParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ext = subprocess.run(
            ["node", "--input-type=module", "-e", EXT_SCRIPT],
            capture_output=True, text=True, check=True,
        )
        site = subprocess.run(
            ["node", "-e", SITE_SCRIPT, str(SITE / "i18n.js")],
            capture_output=True, text=True, check=True,
        )
        cls.catalogs = {"extension": json.loads(ext.stdout), "site": json.loads(site.stdout)}

    def _each(self):
        for name, cats in self.catalogs.items():
            for code in ("fr", "pt-BR"):
                yield name, code, cats["en"], cats[code]

    def test_every_english_key_is_translated(self):
        for name, code, en, other in self._each():
            want = {_normal(k) for k in en} - SAME_EVERYWHERE
            have = {_normal(k) for k in other}
            self.assertEqual(want - have, set(), f"{name} {code} is missing keys")

    def test_no_translation_without_an_english_source(self):
        for name, code, en, other in self._each():
            extra = {_normal(k) for k in other} - {_normal(k) for k in en}
            self.assertEqual(extra, set(), f"{name} {code} has keys English lacks")

    def test_placeholders_match_english(self):
        for name, code, en, other in self._each():
            by_key = {_normal(k): v for k, v in en.items()}
            for key, text in other.items():
                if _normal(key) not in by_key:
                    continue
                # Plural forms may drop {n} ("un jour"), but never invent one.
                want = _placeholders(by_key[_normal(key)])
                self.assertLessEqual(
                    _placeholders(text), want | {"n"},
                    f"{name} {code} {key}: unknown placeholder",
                )
                if _normal(key) == key:  # a single form must keep all of them
                    self.assertEqual(
                        _placeholders(text), want, f"{name} {code} {key}: placeholders differ"
                    )

    def test_no_translation_is_left_in_english(self):
        # Only checks long strings: short ones ("Guide", "Sessions") are the same word.
        for name, code, en, other in self._each():
            for key, text in other.items():
                if key in SAME_EVERYWHERE or len(text) < 28:
                    continue
                self.assertNotEqual(text, en.get(key), f"{name} {code} {key} is still English")


if __name__ == "__main__":
    unittest.main()
