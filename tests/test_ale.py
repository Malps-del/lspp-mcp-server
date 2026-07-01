from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lspp_mcp.config import LsppConfig  # noqa: E402
from lspp_mcp.tools.ale import (  # noqa: E402
    append_initial_volume_fraction_geometry,
    create_initial_volume_fraction_geometry,
    inspect_initial_volume_fraction_geometry,
    render_initial_volume_fraction_geometry,
)
from lspp_mcp.variable_maps import default_variable_maps  # noqa: E402


class AleToolTests(unittest.TestCase):
    def _config(self, root: Path) -> LsppConfig:
        return LsppConfig(
            lsprepost_exe="lsprepost.exe",
            workspace_root=root,
            allowed_roots=(root,),
            variable_maps=default_variable_maps(),
        )

    def test_render_initial_volume_fraction_geometry_cylinder_and_box(self) -> None:
        rendered = render_initial_volume_fraction_geometry(
            fmsid=1,
            fmidtyp=1,
            bammg=1,
            fills=[
                {
                    "geometry": "cylinder",
                    "fammg": 3,
                    "point0": [25.0, 75.0, 0.0],
                    "point1": [25.0, 75.0, 1.0],
                    "radius": 8.0,
                },
                {
                    "geometry": "box",
                    "fammg": 4,
                    "min": [65.0, 35.0, 0.0],
                    "max": [85.0, 65.0, 1.0],
                },
            ],
        )

        self.assertIn("*INITIAL_VOLUME_FRACTION_GEOMETRY", rendered)
        self.assertIn("1, 1, 1, 3", rendered)
        self.assertIn("4, 0, 3, 0, 0, 0", rendered)
        self.assertIn("25, 75, 0, 25, 75, 1, 8, 8", rendered)
        self.assertIn("5, 0, 4, 0, 0, 0", rendered)
        self.assertIn("65, 35, 0, 85, 65, 1, 0", rendered)

    def test_render_initial_volume_fraction_geometry_uses_commas_for_long_values(self) -> None:
        rendered = render_initial_volume_fraction_geometry(
            fmsid=101,
            fmidtyp=1,
            bammg=1,
            fills=[
                {
                    "geometry": "cylinder",
                    "fammg": 3,
                    "point0": [1.649, 0.02292045, 0.3852976349],
                    "point1": [1.649, 0.02292045, 0.9852043651],
                    "radius": 0.125,
                },
            ],
        )

        self.assertIn("1.649, 0.02292045, 0.3852976349, 1.649, 0.02292045, 0.9852043651, 0.125, 0.125", rendered)

    def test_create_and_inspect_initial_volume_fraction_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            result = create_initial_volume_fraction_geometry(
                output_k="ale_fill.inc",
                fmsid=101,
                fmidtyp=1,
                bammg=2,
                ntrace=3,
                fills=[
                    {
                        "geometry": "cylinder",
                        "fammg": 1,
                        "point0": [0.0, 0.21, 0.0],
                        "point1": [0.0, 0.24, 0.0],
                        "radius": 0.0132,
                    }
                ],
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            inspection = result["inspection"]
            self.assertEqual(inspection["block_count"], 1)
            self.assertEqual(inspection["blocks"][0]["fmsid"], "101")
            self.assertEqual(inspection["blocks"][0]["bammg"], "2")
            self.assertEqual(inspection["blocks"][0]["fills"][0]["geometry"], "cylinder_or_cone")
            self.assertEqual(inspection["blocks"][0]["fills"][0]["detail"]["r1"], "0.0132")

    def test_append_initial_volume_fraction_geometry_before_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            (root / "main.k").write_text(
                "\n".join(
                    [
                        "*KEYWORD",
                        "*CONTROL_TERMINATION",
                        "1.0",
                        "*CONTROL_TIMESTEP",
                        "0",
                        "*DATABASE_BINARY_D3PLOT",
                        "0.1",
                        "*END",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = append_initial_volume_fraction_geometry(
                k_path="main.k",
                output_k="filled.k",
                fmsid=1,
                fmidtyp=1,
                bammg=1,
                fills=[
                    {
                        "geometry": "sphere",
                        "fammg": 2,
                        "center": [0.0, 0.0, 0.0],
                        "radius": 3.0,
                    }
                ],
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            text = (root / "filled.k").read_text(encoding="utf-8")
            self.assertLess(
                text.index("*INITIAL_VOLUME_FRACTION_GEOMETRY"),
                text.index("*END"),
            )
            self.assertEqual(result["inspection"]["block_count"], 1)
            self.assertTrue(result["keyword_check"]["ready_for_solver"])

    def test_inspect_reads_existing_main_style_example(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            (root / "main.k").write_text(
                "\n".join(
                    [
                        "*KEYWORD",
                        "*INITIAL_VOLUME_FRACTION_GEOMETRY",
                        "       101         1         2         3",
                        "         2         1         1       0.0       0.0       0.0",
                        "         1         0       0.0",
                        "         4         0         3       0.0       0.0       0.0",
                        "       0.0      0.21       0.0       0.0      0.24       0.0    0.0132    0.0132",
                        "*END",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = inspect_initial_volume_fraction_geometry(
                "main.k",
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["block_count"], 1)
            fills = result["blocks"][0]["fills"]
            self.assertEqual(len(fills), 2)
            self.assertEqual(fills[0]["geometry"], "segment")
            self.assertEqual(fills[0]["detail"]["sgsid"], "1")
            self.assertEqual(fills[1]["geometry"], "cylinder_or_cone")
            self.assertEqual(fills[1]["detail"]["r2"], "0.0132")


if __name__ == "__main__":
    unittest.main()
