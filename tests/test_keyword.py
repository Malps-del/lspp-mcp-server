from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lspp_mcp.config import LsppConfig  # noqa: E402
from lspp_mcp.tools.keyword import (  # noqa: E402
    check_keyword_deck,
    inspect_keyword_deck,
    inspect_keyword_fields,
)
from lspp_mcp.variable_maps import default_variable_maps  # noqa: E402


class KeywordToolTests(unittest.TestCase):
    def _config(self, root: Path) -> LsppConfig:
        return LsppConfig(
            lsprepost_exe="lsprepost.exe",
            workspace_root=root,
            allowed_roots=(root,),
            variable_maps=default_variable_maps(),
        )

    def test_inspect_keyword_deck_follows_includes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "materials.k").write_text(
                "\n".join(
                    [
                        "*KEYWORD",
                        "*MAT_HIGH_EXPLOSIVE_BURN_TITLE",
                        "tnt",
                        "1, 1.63e-9",
                        "*EOS_JWL_TITLE",
                        "jwl",
                        "1, 3.7e5",
                        "*END",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "main.k").write_text(
                "\n".join(
                    [
                        "*KEYWORD",
                        "*CONTROL_TERMINATION",
                        "1.0",
                        "*CONTROL_TIMESTEP",
                        "0",
                        "*DATABASE_BINARY_D3PLOT",
                        "1.0e-4",
                        "*DATABASE_GLSTAT",
                        "1.0e-5",
                        "*PART",
                        "shell",
                        "10, 1, 1",
                        "*SECTION_SHELL",
                        "1",
                        "*INCLUDE",
                        "materials.k",
                        "*END",
                    ]
                ),
                encoding="utf-8",
            )

            result = inspect_keyword_deck("main.k", config=self._config(root))

            self.assertTrue(result["ok"])
            self.assertEqual(len(result["files"]), 2)
            self.assertEqual(result["keyword_counts"]["*DATABASE_BINARY_D3PLOT"], 1)
            self.assertEqual(
                result["blast_impact"]["keywords"]["*MAT_HIGH_EXPLOSIVE_BURN_TITLE"],
                1,
            )
            self.assertTrue(result["database_outputs"]["d3plot"]["present"])

    def test_check_keyword_deck_reports_missing_include_as_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.k").write_text(
                "\n".join(["*KEYWORD", "*INCLUDE", "missing.k", "*END"]),
                encoding="utf-8",
            )

            result = check_keyword_deck("main.k", config=self._config(root))

            self.assertTrue(result["ok"])
            self.assertFalse(result["ready_for_solver"])
            self.assertEqual(result["issue_counts"]["error"], 1)
            self.assertEqual(result["issues"][0]["code"], "missing_include")

    def test_extra_keyword_files_are_checked_together(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.k").write_text(
                "\n".join(
                    [
                        "*KEYWORD",
                        "*CONTROL_TERMINATION",
                        "1.0",
                        "*CONTROL_TIMESTEP",
                        "0",
                        "*DATABASE_BINARY_D3PLOT",
                        "1.0e-4",
                        "*INITIAL_DETONATION",
                        "1, 0, 0, 0",
                        "*END",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "materials.k").write_text(
                "\n".join(
                    [
                        "*KEYWORD",
                        "*MAT_HIGH_EXPLOSIVE_BURN_TITLE",
                        "he",
                        "1",
                        "*EOS_JWL_TITLE",
                        "jwl",
                        "1",
                        "*END",
                    ]
                ),
                encoding="utf-8",
            )

            result = check_keyword_deck(
                "main.k",
                extra_k_paths=["materials.k"],
                include_includes=False,
                config=self._config(root),
            )

            self.assertTrue(result["ok"])
            self.assertEqual(len(result["extra_k_paths"]), 1)
            self.assertNotIn(
                "he_without_jwl",
                {issue["code"] for issue in result["issues"]},
            )
            self.assertEqual(
                result["blast_impact"]["keywords"]["*MAT_HIGH_EXPLOSIVE_BURN_TITLE"],
                1,
            )

    def test_inspect_keyword_fields_parses_parameters_and_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.k").write_text(
                "\n".join(
                    [
                        "*KEYWORD",
                        "*PARAMETER",
                        "$#   prmr1      val1     prmr2      val2     prmr3      val3",
                        "R expDp   2.5       R soil    2         R air     3",
                        "*PARAMETER_EXPRESSION_LOCAL",
                        "$#    prmr                                                            expression",
                        "Rpexp1    soil-0.1",
                        "*CONTROL_TERMINATION",
                        "$#  endtim    endcyc     dtmin    endeng    endmas     nosol",
                        "      0.05         0       0.0       0.01.000000E8         0",
                        "*DATABASE_TRACER",
                        "$#    time     track         x         y         z    ammgid       nid    radius",
                        "       0.0         1       0.5&expdp           0.0         0         0       0.0",
                        "*INITIAL_DETONATION",
                        "$#     pid         x         y         z        lt         -    mmgset",
                        "       101       0.0       2.0       0.0&expdp           0.0",
                        "*END",
                    ]
                ),
                encoding="utf-8",
            )

            result = inspect_keyword_fields("main.k", config=self._config(root))

            self.assertTrue(result["ok"])
            summary = result["parameter_summary"]
            self.assertEqual(summary["definitions"]["expdp"]["value"], "2.5")
            self.assertEqual(summary["definitions"]["soil"]["value"], "2")
            self.assertEqual(summary["expressions"]["pexp1"]["expression"], "soil-0.1")
            self.assertEqual(summary["expressions"]["pexp1"]["dependencies"], ["soil"])
            self.assertEqual(
                summary["references"]["expdp"][0]["keyword"],
                "*DATABASE_TRACER",
            )
            self.assertEqual(summary["references"]["expdp"][0]["field"], "x")

            termination = next(
                block
                for block in result["field_blocks"]
                if block["keyword"] == "*CONTROL_TERMINATION"
            )
            fields = {
                field["name"]: field["value"]
                for row in termination["rows"]
                for field in row["fields"]
            }
            self.assertEqual(fields["endtim"], "0.05")
            self.assertEqual(fields["endmas"], "1.000000E8")


if __name__ == "__main__":
    unittest.main()
