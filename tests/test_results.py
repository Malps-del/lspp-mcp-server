from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lspp_mcp.config import LsppConfig  # noqa: E402
from lspp_mcp.tools.results import (  # noqa: E402
    compare_lsdyna_cases,
    extract_lsdyna_metrics,
    inspect_lsdyna_results,
)
from lspp_mcp.variable_maps import default_variable_maps  # noqa: E402


class ResultsToolTests(unittest.TestCase):
    def _config(self, root: Path) -> LsppConfig:
        return LsppConfig(
            lsprepost_exe="lsprepost.exe",
            workspace_root=root,
            allowed_roots=(root,),
            variable_maps=default_variable_maps(),
        )

    def test_inspect_lsdyna_results_detects_files_and_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ["d3plot", "d3plot01", "binout", "glstat"]:
                (root / name).write_text("x", encoding="utf-8")
            (root / "d3hsp").write_text(
                "cycle = 10 time = 1.0e-3\nnormal termination\n",
                encoding="utf-8",
            )

            result = inspect_lsdyna_results(str(root), config=self._config(root))

            self.assertTrue(result["ok"])
            self.assertEqual(result["file_counts"]["d3plot"], 2)
            self.assertEqual(result["file_counts"]["binout"], 1)
            self.assertIn("export_contour_images", result["available_actions"])
            self.assertEqual(
                result["diagnostics"]["completion_state"], "normal_termination"
            )

    def test_extract_lsdyna_metrics_computes_curve_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            curve = root / "curve.csv"
            curve.write_text(
                "time,pressure\n0,0\n1,2\n2,4\n3,3\n",
                encoding="utf-8",
            )

            result = extract_lsdyna_metrics(
                str(curve),
                x_column="time",
                y_columns=["pressure"],
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            metrics = result["metrics"]["pressure"]
            self.assertEqual(metrics["max"], 4.0)
            self.assertEqual(metrics["time_at_max"], 2.0)
            self.assertEqual(metrics["final"], 3.0)
            self.assertAlmostEqual(metrics["integral"], 7.5)

    def test_compare_lsdyna_cases_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = root / "cases"
            for case_name, scale in [("case_a", 1.0), ("case_b", 2.0)]:
                case_dir = cases / case_name
                case_dir.mkdir(parents=True)
                (case_dir / "pressure.csv").write_text(
                    f"time,pressure\n0,0\n1,{scale}\n2,{2 * scale}\n",
                    encoding="utf-8",
                )
            output = root / "summary.csv"

            result = compare_lsdyna_cases(
                cases_root=str(cases),
                output_csv=str(output),
                metric_specs=[
                    {
                        "name": "peak_pressure",
                        "curve_csv": "pressure.csv",
                        "x_column": "time",
                        "y_column": "pressure",
                        "metric": "max",
                    }
                ],
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            self.assertTrue(output.exists())
            with output.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["peak_pressure.max"], "4.0")


if __name__ == "__main__":
    unittest.main()
