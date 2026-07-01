from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lspp_mcp.config import LsppConfig  # noqa: E402
from lspp_mcp.tools.binout import (  # noqa: E402
    INSTALL_LASSO_MESSAGE,
    extract_binout_curve,
    extract_binout_metrics,
    inspect_binout_contents,
)
from lspp_mcp.validators import LsppValidationError  # noqa: E402
from lspp_mcp.variable_maps import default_variable_maps  # noqa: E402


class FakeBinout:
    sources: list[str] = []

    data = {
        "glstat": {
            "time": [0.0, 1.0, 2.0],
            "kinetic_energy": [0.0, 10.0, 5.0],
        },
        "nodout": {
            "time": [0.0, 1.0, 2.0],
            "ids": [101, 102],
            "y_displacement": [
                [0.0, 0.1],
                [0.2, 0.3],
                [0.4, 0.5],
            ],
        },
        "dbfsi": {
            "time": [0.0, 1.0, 2.0],
            "legend_ids": ["fsi_a", "fsi_b"],
            "pres": [
                [0.0, 1.0],
                [4.0, 2.0],
                [1.0, 0.0],
            ],
        },
        "trhist": {
            "time": [0.0, 1.0, 2.0],
            "ids": [7],
            "sx": [[-3.0], [-9.0], [-6.0]],
            "sy": [[-3.0], [-6.0], [-3.0]],
            "sz": [[-3.0], [-3.0], [0.0]],
        },
    }

    def __init__(self, source: str) -> None:
        self.source = source
        self.sources.append(source)

    def read(self, *path: str):
        if not path:
            return list(self.data.keys())
        if len(path) == 1:
            return list(self.data[path[0]].keys())
        value = self.data[path[0]]
        for item in path[1:]:
            value = value[item]
        return value


class BinoutLassoTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeBinout.sources = []

    def _config(self, root: Path) -> LsppConfig:
        return LsppConfig(
            lsprepost_exe="lsprepost.exe",
            workspace_root=root,
            allowed_roots=(root,),
            variable_maps=default_variable_maps(),
        )

    def _write_shards(self, root: Path) -> None:
        (root / "binout0000").write_text("fake", encoding="utf-8")
        (root / "binout0001").write_text("fake", encoding="utf-8")

    def test_inspect_binout_contents_uses_lasso_and_mpp_glob(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "lspp_mcp.tools.binout._load_lasso_binout_class",
            return_value=FakeBinout,
        ):
            root = Path(tmp)
            self._write_shards(root)

            result = inspect_binout_contents("binout0000", config=self._config(root))

            self.assertTrue(result["ok"])
            self.assertTrue(FakeBinout.sources[-1].endswith("binout*"))
            self.assertEqual(result["mpp_shards"], 2)
            self.assertIn("glstat", result["top_blocks"])
            self.assertEqual(result["blocks"]["glstat"]["variables"]["time"]["steps"], 3)
            self.assertEqual(
                result["blocks"]["nodout"]["variables"]["y_displacement"]["shape"],
                [3, 2],
            )

    def test_lasso_exports_one_dimensional_variable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "lspp_mcp.tools.binout._load_lasso_binout_class",
            return_value=FakeBinout,
        ):
            root = Path(tmp)
            (root / "binout").write_text("fake", encoding="utf-8")

            result = extract_binout_curve(
                "binout",
                block="glstat",
                variable="kinetic_energy",
                output_csv="post/glstat_ke.csv",
                backend="lasso",
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            with (root / "post" / "glstat_ke.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["time", "value"])
            self.assertEqual(rows[2], ["1.0", "10.0"])
            self.assertEqual(result["metrics"]["columns"]["value"]["peak"], 10.0)

    def test_lasso_exports_two_dimensional_variable_by_entity_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "lspp_mcp.tools.binout._load_lasso_binout_class",
            return_value=FakeBinout,
        ):
            root = Path(tmp)
            (root / "binout").write_text("fake", encoding="utf-8")

            result = extract_binout_curve(
                "binout",
                block="nodout",
                variable="y_displacement",
                entity_index=1,
                output_csv="post/nodout_y_102.csv",
                backend="lasso",
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            with (root / "post" / "nodout_y_102.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["time", "value"])
            self.assertEqual(rows[2], ["1.0", "0.3"])

    def test_lasso_exports_all_entities_with_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "lspp_mcp.tools.binout._load_lasso_binout_class",
            return_value=FakeBinout,
        ):
            root = Path(tmp)
            (root / "binout").write_text("fake", encoding="utf-8")

            result = extract_binout_curve(
                "binout",
                block="dbfsi",
                variable="pres",
                output_csv="post/dbfsi_pres.csv",
                backend="lasso",
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            with (root / "post" / "dbfsi_pres.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["time", "fsi_a", "fsi_b"])
            self.assertEqual(rows[2], ["1.0", "4.0", "2.0"])

    def test_lasso_missing_dependency_reports_install_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "lspp_mcp.tools.binout._load_lasso_binout_class",
            side_effect=LsppValidationError(INSTALL_LASSO_MESSAGE),
        ):
            root = Path(tmp)
            (root / "binout").write_text("fake", encoding="utf-8")

            result = extract_binout_curve(
                "binout",
                block="glstat",
                variable="kinetic_energy",
                output_csv="post/out.csv",
                backend="lasso",
                config=self._config(root),
            )

            self.assertFalse(result["ok"])
            self.assertIn("pip install lasso-python h5py pandas rich", result["message"])

    def test_pressure_proxy_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "lspp_mcp.tools.binout._load_lasso_binout_class",
            return_value=FakeBinout,
        ):
            root = Path(tmp)
            (root / "binout").write_text("fake", encoding="utf-8")

            result = extract_binout_metrics(
                "binout",
                block="trhist",
                variable="p_proxy",
                pressure_proxy=True,
                backend="lasso",
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            metrics = result["pressure_metrics"]["columns"]["7"]
            self.assertEqual(metrics["peak_pressure"], 6.0)
            self.assertEqual(metrics["arrival_time"], 0.0)
            self.assertEqual(metrics["shock_impulse"], 9.0)


if __name__ == "__main__":
    unittest.main()
