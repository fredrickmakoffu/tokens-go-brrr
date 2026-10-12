#!/usr/bin/env python3
"""Regenerate the light-theme block of the extension's stylesheet.css.

Delegates to gen_ui_artifacts.py so colour maps stay owned by ui/tokens.json.

    python3 scripts/gen_light_css.py
"""

from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent / "gen_ui_artifacts.py"), run_name="__main__")
