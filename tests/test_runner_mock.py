from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lspp_mcp.config import LsppConfig  # noqa: E402
from lspp_mcp.runner import RunResult, run_lsprepost  # noqa: E402
from lspp_mcp.tools.ascii_curves import extract_ascii_curve  # noqa: E402
from lspp_mcp.tools.binout import extract_binout_curve  # noqa: E402
from lspp_mcp.tools.d3plot import (  # noqa: E402
    export_d3plot_contour,
    extract_d3plot_node_history,
)
from lspp_mcp.variable_maps import default_variable_maps  # noqa: E402


class RunnerMockTests(unittest.TestCase):
    def _config(self, root: Path) -> LsppConfig:
        return LsppConfig(
            lsprepost_exe="lsprepost.exe",
            workspace_root=root,
            allowed_roots=(root,),
            variable_maps=default_variable_maps(),
        )

    def test_runner_uses_nographics_for_curve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch("subprocess.run") as mocked:
            cfile = Path(tmp) / "generated.cfile"
            cfile.write_text("new\nexit\n", encoding="utf-8")
            mocked.return_value = subprocess.CompletedProcess(
                ["lsprepost.exe"], 0, stdout="ok", stderr=""
            )
            result = run_lsprepost(
                cfile,
                mode="curve",
                window_size=None,
                use_nographics=False,
                timeout=5,
                lsprepost_exe="lsprepost.exe",
            )
            self.assertTrue(result.ok)
            command = mocked.call_args.args[0]
            self.assertIn("-nographics", command)
            self.assertIn(f"c={cfile}", command)

    def test_missing_output_returns_not_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "d3plot").write_text("fake", encoding="utf-8")
            cfg = self._config(root)
            with patch(
                "lspp_mcp.tools._common.run_lsprepost",
                return_value=RunResult(
                    ok=True,
                    message="ok",
                    command=[],
                    returncode=0,
                    stdout="",
                    stderr="",
                    log_file=None,
                ),
            ):
                result = export_d3plot_contour(
                    d3plot_path="d3plot",
                    output_png="post/out.jpg",
                    variable="von_mises",
                    state_index=1,
                    view="front",
                    range_level=50,
                    config=cfg,
                )
            self.assertFalse(result["ok"])
            self.assertIn("not generated", result["message"])
            self.assertEqual(result["image_format"], "jpg")
            generated = Path(result["generated_cfile"]).read_text(encoding="utf-8")
            self.assertIn('print jpg "', generated)
            self.assertIn("range level 50", generated)
            self.assertIn("range pal update", generated)

    def test_mismatched_image_format_returns_not_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "d3plot").write_text("fake", encoding="utf-8")
            cfg = self._config(root)
            result = export_d3plot_contour(
                d3plot_path="d3plot",
                output_png="post/out.wrl",
                variable="von_mises",
                state_index=1,
                view="front",
                image_format="png",
                config=cfg,
            )
            self.assertFalse(result["ok"])
            self.assertIn("does not match", result["message"])

    def test_unsupported_image_format_returns_not_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "d3plot").write_text("fake", encoding="utf-8")
            cfg = self._config(root)
            result = export_d3plot_contour(
                d3plot_path="d3plot",
                output_png="post/out.svg",
                variable="von_mises",
                state_index=1,
                view="front",
                config=cfg,
            )
            self.assertFalse(result["ok"])
            self.assertIn("image_format must be one of", result["message"])

    def test_empty_output_returns_not_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "nodout").write_text("fake", encoding="utf-8")
            output = root / "post" / "node.csv"

            def fake_run(*args, **kwargs):
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("", encoding="utf-8")
                return RunResult(
                    ok=True,
                    message="ok",
                    command=[],
                    returncode=0,
                    stdout="",
                    stderr="",
                    log_file=None,
                )

            cfg = self._config(root)
            with patch("lspp_mcp.tools._common.run_lsprepost", side_effect=fake_run):
                result = extract_ascii_curve(
                    ascii_type="nodout",
                    file_path="nodout",
                    variable="x_displacement",
                    entity_id=1001,
                    output_csv="post/node.csv",
                    config=cfg,
                )
            self.assertFalse(result["ok"])
            self.assertIn("empty", result["message"])

    def test_tools_generate_expected_cfiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ["nodout", "matsum", "d3plot", "binout"]:
                (root / name).write_text("fake", encoding="utf-8")
            cfg = self._config(root)
            fake_run = Mock(
                return_value=RunResult(
                    ok=True,
                    message="ok",
                    command=[],
                    returncode=0,
                    stdout="",
                    stderr="",
                    log_file=None,
                )
            )
            with patch("lspp_mcp.tools._common.run_lsprepost", fake_run):
                nodout = extract_ascii_curve(
                    "nodout",
                    "nodout",
                    "post/nodout.csv",
                    variable="x_displacement",
                    entity_id=1001,
                    config=cfg,
                )
                matsum = extract_ascii_curve(
                    "matsum",
                    "matsum",
                    "post/matsum.csv",
                    variable="internal_energy",
                    entity_id=1,
                    config=cfg,
                )
                node_history = extract_d3plot_node_history(
                    "d3plot",
                    node_id=1001,
                    variable="resultant_displacement",
                    output_csv="post/node_history.csv",
                    config=cfg,
                )
                binout = extract_binout_curve(
                    "binout",
                    block="glstat",
                    variable="kinetic_energy",
                    output_csv="post/binout.csv",
                    config=cfg,
                )
            self.assertIn("ascii nodout plot 1 1001", Path(nodout["generated_cfile"]).read_text(encoding="utf-8"))
            self.assertIn("ascii matsum plot 1 1", Path(matsum["generated_cfile"]).read_text(encoding="utf-8"))
            self.assertIn("ntime 8", Path(node_history["generated_cfile"]).read_text(encoding="utf-8"))
            self.assertIn("binaski plot", Path(binout["generated_cfile"]).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
