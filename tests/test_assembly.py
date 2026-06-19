from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lspp_mcp.config import LsppConfig  # noqa: E402
from lspp_mcp.tools.assembly import (  # noqa: E402
    check_lsdyna_cylindrical_assembly,
    create_lsdyna_cylindrical_assembly,
)
from lspp_mcp.variable_maps import default_variable_maps  # noqa: E402


class AssemblyToolTests(unittest.TestCase):
    def _config(self, root: Path) -> LsppConfig:
        return LsppConfig(
            lsprepost_exe="lsprepost.exe",
            workspace_root=root,
            allowed_roots=(root,),
            variable_maps=default_variable_maps(),
        )

    def test_create_cylindrical_assembly_with_blocks_mass_and_fill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            result = create_lsdyna_cylindrical_assembly(
                output_k="assembly.k",
                radius=10.0,
                height=30.0,
                thickness=0.5,
                n_circumference=8,
                nz=2,
                attached_blocks=[
                    {
                        "count_circumference": 4,
                        "count_height": 1,
                        "radial_thickness": 1.0,
                        "circumferential_width": 2.0,
                        "height": 4.0,
                        "radial_gap": 0.0,
                        "part_id": 20,
                        "section_id": 20,
                        "material_id": 20,
                    }
                ],
                mass_points=[
                    {
                        "count_circumference": 4,
                        "count_height": 1,
                        "mass": 0.25,
                        "radial_offset": 1.5,
                    }
                ],
                internal_fill={
                    "fmsid": 101,
                    "bammg": 2,
                    "fammg": 3,
                    "radius": 9.0,
                },
                check_json="assembly_check.json",
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["assembly"]["solid_element_count"], 4)
            self.assertEqual(result["assembly"]["mass_element_count"], 4)
            self.assertTrue(result["assembly"]["internal_fill"])
            self.assertEqual(result["check"]["shell_edges"]["boundary_edge_count"], 0)
            self.assertEqual(result["check"]["masses"]["total_mass"], 1.0)
            self.assertTrue((root / "assembly_check.json").exists())
            text = (root / "assembly.k").read_text(encoding="utf-8")
            self.assertIn("*ELEMENT_SOLID", text)
            self.assertIn("*ELEMENT_MASS", text)
            self.assertIn("*INITIAL_VOLUME_FRACTION_GEOMETRY", text)

    def test_check_reports_open_shell_when_closed_expected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            create_lsdyna_cylindrical_assembly(
                output_k="open.k",
                radius=5.0,
                height=10.0,
                thickness=0.2,
                n_circumference=8,
                nz=1,
                cap_bottom=False,
                cap_top=False,
                config=self._config(root),
            )

            result = check_lsdyna_cylindrical_assembly(
                "open.k",
                expect_closed_shell=True,
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            self.assertFalse(result["ready_for_solver"])
            self.assertGreater(result["shell_edges"]["boundary_edge_count"], 0)
            self.assertIn("shell_boundary_edges", {issue["code"] for issue in result["issues"]})


if __name__ == "__main__":
    unittest.main()
