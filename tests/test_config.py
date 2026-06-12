from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lspp_mcp.config import load_config  # noqa: E402


class ConfigTests(unittest.TestCase):
    def test_color_palettes_are_loaded_relative_to_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        'workspace_root: "."',
                        "allowed_roots:",
                        '  - "."',
                        "color_palettes:",
                        '  lab-style: "palettes/lab.txt"',
                    ]
                ),
                encoding="utf-8",
            )

            cfg = load_config(config_path)

            self.assertEqual(cfg.workspace_root, root)
            self.assertEqual(cfg.color_palettes["lab_style"], root / "palettes" / "lab.txt")


if __name__ == "__main__":
    unittest.main()
