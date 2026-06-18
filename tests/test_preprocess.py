from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lspp_mcp.config import LsppConfig  # noqa: E402
from lspp_mcp.runner import RunResult  # noqa: E402
from lspp_mcp.tools.preprocess import (  # noqa: E402
    create_lsdyna_block_mesh,
    create_lsdyna_cylinder_shell_mesh,
    create_lsdyna_plate_mesh,
    precheck_lsdyna_keyword_model,
    preview_lsdyna_keyword_model,
)
from lspp_mcp.variable_maps import default_variable_maps  # noqa: E402


class PreprocessToolTests(unittest.TestCase):
    def _config(self, root: Path) -> LsppConfig:
        return LsppConfig(
            lsprepost_exe="lsprepost.exe",
            workspace_root=root,
            allowed_roots=(root,),
            variable_maps=default_variable_maps(),
        )

    def test_create_plate_mesh_generates_keyword_and_precheck(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            result = create_lsdyna_plate_mesh(
                output_k="plate.k",
                length=10.0,
                width=5.0,
                thickness=0.5,
                nx=2,
                ny=1,
                fixed_edges=True,
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["mesh"]["node_count"], 6)
            self.assertEqual(result["mesh"]["element_count"], 2)
            self.assertTrue(result["precheck"]["ready_for_solver"])
            text = (root / "plate.k").read_text(encoding="utf-8")
            self.assertIn("*ELEMENT_SHELL", text)
            self.assertIn("*BOUNDARY_SPC_SET", text)
            self.assertIn("*DATABASE_BINARY_D3PLOT", text)

    def test_create_block_mesh_generates_solid_elements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            result = create_lsdyna_block_mesh(
                output_k="block.k",
                length=2.0,
                width=2.0,
                height=1.0,
                nx=2,
                ny=2,
                nz=1,
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["mesh"]["node_count"], 18)
            self.assertEqual(result["mesh"]["element_count"], 4)
            self.assertEqual(result["precheck"]["mesh"]["solid_element_count"], 4)
            self.assertTrue((root / "block.k").exists())

    def test_create_cylinder_shell_mesh_generates_closed_shell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            result = create_lsdyna_cylinder_shell_mesh(
                output_k="cylinder.k",
                radius=2.0,
                height=5.0,
                thickness=0.1,
                n_circumference=8,
                nz=2,
                fixed_bottom=True,
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["mesh"]["node_count"], 24)
            self.assertEqual(result["mesh"]["element_count"], 16)
            self.assertEqual(result["precheck"]["mesh"]["shell_element_count"], 16)
            self.assertTrue(result["precheck"]["ready_for_solver"])
            text = (root / "cylinder.k").read_text(encoding="utf-8")
            self.assertIn("*ELEMENT_SHELL", text)
            self.assertIn("8, 1, 8, 1, 9, 16", text)
            self.assertIn("*BOUNDARY_SPC_SET", text)

    def test_cylinder_shell_can_infer_divisions_from_element_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            result = create_lsdyna_cylinder_shell_mesh(
                output_k="cylinder.k",
                radius=1.0,
                height=2.0,
                thickness=0.1,
                elem_size=1.0,
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["mesh"]["n_circumference"], 7)
            self.assertEqual(result["mesh"]["nz"], 2)
            self.assertEqual(result["mesh"]["element_count"], 14)

    def test_create_cylinder_shell_mesh_can_cap_both_ends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            result = create_lsdyna_cylinder_shell_mesh(
                output_k="closed_cylinder.k",
                radius=2.0,
                height=5.0,
                thickness=0.1,
                n_circumference=8,
                nz=2,
                cap_bottom=True,
                cap_top=True,
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["mesh"]["cap_mesh"], "quad")
            self.assertEqual(result["mesh"]["node_count"], 58)
            self.assertEqual(result["mesh"]["element_count"], 56)
            self.assertEqual(result["precheck"]["mesh"]["shell_element_count"], 56)
            self.assertEqual(result["precheck"]["mesh"]["missing_node_reference_count"], 0)
            self.assertEqual(result["precheck"]["mesh"]["degenerate_shell_count"], 0)
            self.assertTrue(result["precheck"]["ready_for_solver"])
            text = (root / "closed_cylinder.k").read_text(encoding="utf-8")
            self.assertIn("17, 1, 2, 1, 25, 26", text)
            self.assertIn("36, 1, 33, 41, 35, 34", text)

    def test_create_cylinder_shell_mesh_can_use_triangular_caps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            result = create_lsdyna_cylinder_shell_mesh(
                output_k="tri_capped_cylinder.k",
                radius=2.0,
                height=5.0,
                thickness=0.1,
                n_circumference=8,
                nz=2,
                cap_bottom=True,
                cap_top=True,
                cap_mesh="tri",
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["mesh"]["cap_mesh"], "tri")
            self.assertEqual(result["mesh"]["node_count"], 26)
            self.assertEqual(result["mesh"]["element_count"], 32)
            self.assertEqual(result["precheck"]["mesh"]["degenerate_shell_count"], 0)
            text = (root / "tri_capped_cylinder.k").read_text(encoding="utf-8")
            self.assertIn("17, 1, 2, 1, 25, 0", text)

    def test_precheck_reports_missing_node_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            (root / "bad.k").write_text(
                "\n".join(
                    [
                        "*KEYWORD",
                        "*CONTROL_TERMINATION",
                        "1.0",
                        "*CONTROL_TIMESTEP",
                        "0",
                        "*DATABASE_BINARY_D3PLOT",
                        "0.1",
                        "*PART",
                        "bad",
                        "1, 1, 1",
                        "*SECTION_SHELL",
                        "1",
                        "*MAT_ELASTIC",
                        "1, 1, 1, 0.3",
                        "*NODE",
                        "1, 0, 0, 0",
                        "2, 1, 0, 0",
                        "3, 1, 1, 0",
                        "*ELEMENT_SHELL",
                        "1, 1, 1, 2, 3, 4",
                        "*END",
                    ]
                ),
                encoding="utf-8",
            )

            result = precheck_lsdyna_keyword_model("bad.k", config=self._config(root))

            self.assertTrue(result["ok"])
            self.assertFalse(result["ready_for_solver"])
            self.assertEqual(result["mesh"]["missing_node_reference_count"], 1)
            self.assertEqual(result["mesh"]["issues"][0]["code"], "missing_node_references")

    def test_precheck_can_write_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            create_lsdyna_plate_mesh(
                output_k="plate.k",
                length=1.0,
                width=1.0,
                thickness=0.1,
                nx=1,
                ny=1,
                config=self._config(root),
            )

            result = precheck_lsdyna_keyword_model(
                "plate.k",
                output_json="precheck.json",
                overwrite=True,
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            self.assertTrue((root / "precheck.json").exists())
            self.assertEqual(result["output_json"], str(root / "precheck.json"))

    def test_preview_keyword_model_generates_cfile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            create_lsdyna_plate_mesh(
                output_k="plate.k",
                length=1.0,
                width=1.0,
                thickness=0.1,
                nx=1,
                ny=1,
                config=self._config(root),
            )
            output = root / "preview.png"

            def fake_run(*args, **kwargs):
                output.write_text("image", encoding="utf-8")
                return RunResult(
                    ok=True,
                    message="ok",
                    command=[],
                    returncode=0,
                    stdout="",
                    stderr="",
                    log_file=None,
                )

            with patch("lspp_mcp.tools._common.run_lsprepost", side_effect=fake_run):
                result = preview_lsdyna_keyword_model(
                    "plate.k",
                    "preview.png",
                    view="isometric",
                    config=self._config(root),
                )

            self.assertTrue(result["ok"])
            generated = Path(result["generated_cfile"]).read_text(encoding="utf-8")
            self.assertIn('open keyword "', generated)
            self.assertIn("isometric x", generated)
            self.assertIn('print png "', generated)


if __name__ == "__main__":
    unittest.main()
