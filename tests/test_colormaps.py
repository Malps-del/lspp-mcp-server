from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lspp_mcp.colormaps import (  # noqa: E402
    builtin_color_styles,
    normalize_style_name,
    palette_lines,
)


class ColormapTests(unittest.TestCase):
    def test_reference_colormap_names_are_available(self) -> None:
        styles = builtin_color_styles()
        for name in [
            "viridis",
            "plasma",
            "inferno",
            "magma",
            "cividis",
            "ylorbr",
            "rdbu",
            "spectral",
            "coolwarm",
            "tab10",
            "turbo",
            "nipy_spectral",
        ]:
            self.assertIn(name, styles)

    def test_aliases_match_reference_names(self) -> None:
        self.assertEqual(normalize_style_name("YlOrBr"), "ylorbr")
        self.assertEqual(normalize_style_name("RdYlBu"), "rdylbu")
        self.assertEqual(normalize_style_name("tab-20"), "tab20")
        self.assertEqual(normalize_style_name("blue to red"), "blue_red")

    def test_continuous_palette_uses_zero_based_level_numbers(self) -> None:
        lines = palette_lines("plasma", 3)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], "0 0.05098 0.031373 0.529412")
        self.assertEqual(lines[-1], "3 0.941176 0.976471 0.129412")

    def test_discrete_palette_repeats_color_blocks(self) -> None:
        lines = palette_lines("tab10", 20)
        self.assertEqual(len(lines), 21)
        self.assertEqual(lines[0].split()[0], "0")
        self.assertEqual(lines[-1].split()[0], "20")
        self.assertEqual(lines[0].split()[1:], lines[1].split()[1:])
        self.assertNotEqual(lines[1].split()[1:], lines[2].split()[1:])


if __name__ == "__main__":
    unittest.main()
