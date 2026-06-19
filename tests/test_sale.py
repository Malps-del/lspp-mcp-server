from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lspp_mcp.config import LsppConfig  # noqa: E402
from lspp_mcp.tools.sale import (  # noqa: E402
    check_lsdyna_sale_fluid_domain,
    create_lsdyna_sale_fluid_domain,
)
from lspp_mcp.variable_maps import default_variable_maps  # noqa: E402


class SaleToolTests(unittest.TestCase):
    def _config(self, root: Path) -> LsppConfig:
        return LsppConfig(
            lsprepost_exe="lsprepost.exe",
            workspace_root=root,
            allowed_roots=(root,),
            variable_maps=default_variable_maps(),
        )

    def test_create_3d_sale_fluid_domain_with_fill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            result = create_lsdyna_sale_fluid_domain(
                output_k="sale.k",
                x_range=[-1.0, 1.0],
                y_range=[-2.0, 2.0],
                z_range=[0.0, 3.0],
                nx=4,
                ny=6,
                nz=8,
                background_ammg=1,
                materials=[
                    {"ammg": 1, "mid": 1001, "eosid": 1001, "name": "neutral_background"},
                    {"ammg": 2, "mid": 1002, "eosid": 1002, "name": "neutral_fill"},
                ],
                fills=[
                    {
                        "geometry": "box",
                        "fammg": 2,
                        "min": [-0.5, -0.5, 0.5],
                        "max": [0.5, 0.5, 1.5],
                    }
                ],
                check_json="sale_check.json",
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            self.assertFalse(result["domain"]["axisymmetric"])
            self.assertEqual(result["domain"]["fill_count"], 1)
            self.assertEqual(result["check"]["sale"]["control_point_count"], 3)
            self.assertTrue(result["check"]["sale"]["three_dimensional_multi_material_group"])
            self.assertTrue(result["check"]["ready_for_solver"])
            self.assertTrue((root / "sale_check.json").exists())
            text = (root / "sale.k").read_text(encoding="utf-8")
            self.assertIn("*ALE_STRUCTURED_MESH", text)
            self.assertIn("*ALE_STRUCTURED_MULTI-MATERIAL_GROUP", text)
            self.assertIn("*INITIAL_VOLUME_FRACTION_GEOMETRY", text)
            self.assertIn("*BOUNDARY_SALE_MESH_FACE", text)
            self.assertIn("*SET_PART_LIST_TITLE", text)

    def test_create_axisymmetric_sale_fluid_domain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            result = create_lsdyna_sale_fluid_domain(
                output_k="sale_axisym.k",
                x_range=[0.0, 5.0],
                y_range=[0.0, 5.0],
                nx=10,
                ny=10,
                axisymmetric=True,
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            self.assertTrue(result["domain"]["axisymmetric"])
            self.assertIsNone(result["domain"]["z_range"])
            self.assertEqual(result["check"]["sale"]["control_point_count"], 2)
            self.assertTrue(result["check"]["sale"]["axisymmetric_multi_material_group"])
            text = (root / "sale_axisym.k").read_text(encoding="utf-8")
            self.assertIn("*ALE_STRUCTURED_MULTI-MATERIAL_GROUP_AXISYM", text)
            self.assertIn("      1001      1002         0", text)
            self.assertIn("*SET_PART_LIST_TITLE", text)

    def test_3d_sale_domain_requires_z_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            result = create_lsdyna_sale_fluid_domain(
                output_k="bad.k",
                x_range=[0.0, 1.0],
                y_range=[0.0, 1.0],
                axisymmetric=False,
                config=self._config(root),
            )

            self.assertFalse(result["ok"])
            self.assertIn("z_range is required", result["message"])

    def test_check_reports_missing_sale_mesh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            (root / "empty.k").write_text(
                "\n".join(
                    [
                        "*KEYWORD",
                        "*CONTROL_TERMINATION",
                        "1.0",
                        "*CONTROL_TIMESTEP",
                        "0",
                        "*DATABASE_BINARY_D3PLOT",
                        "0.1",
                        "*MAT_NULL",
                        "1, 1.0",
                        "*PART",
                        "part",
                        "1, 1, 1",
                        "*END",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = check_lsdyna_sale_fluid_domain("empty.k", config=self._config(root))

            self.assertTrue(result["ok"])
            self.assertFalse(result["ready_for_solver"])
            self.assertIn("missing_sale_structured_mesh", {issue["code"] for issue in result["issues"]})


if __name__ == "__main__":
    unittest.main()
