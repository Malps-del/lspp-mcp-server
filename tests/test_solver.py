from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lspp_mcp.config import LsppConfig  # noqa: E402
from lspp_mcp.tools.solver import (  # noqa: E402
    diagnose_lsdyna_logs,
    run_lsdyna_solver,
    validate_lsdyna_solver,
)
from lspp_mcp.variable_maps import default_variable_maps  # noqa: E402


def _same_path(left: str | Path, right: str | Path) -> bool:
    return Path(left).resolve(strict=False) == Path(right).resolve(strict=False)


class SolverToolTests(unittest.TestCase):
    def _config(self, root: Path, exe: Path | None = None) -> LsppConfig:
        return LsppConfig(
            lsprepost_exe="lsprepost.exe",
            lsdyna_exe=str(exe or Path(sys.executable)),
            workspace_root=root,
            allowed_roots=(root,),
            variable_maps=default_variable_maps(),
        )

    def test_validate_lsdyna_solver(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = validate_lsdyna_solver(config=self._config(root))
            self.assertTrue(result["ok"])
            self.assertTrue(_same_path(result["work_dir"], root))

    def test_run_lsdyna_solver_dry_run_builds_safe_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            k_file = root / "case.k"
            k_file.write_text("*KEYWORD\n*END\n", encoding="utf-8")
            result = run_lsdyna_solver(
                k_path="case.k",
                ncpu=4,
                memory="200m",
                additional_args=["jobid=test01"],
                dry_run=True,
                config=self._config(root),
            )
            self.assertTrue(result["ok"])
            k_arg = next(item for item in result["command"] if item.startswith("i="))
            self.assertTrue(_same_path(k_arg[2:], k_file))
            self.assertIn("ncpu=4", result["command"])
            self.assertIn("memory=200m", result["command"])
            self.assertIn("jobid=test01", result["command"])

    def test_run_lsdyna_solver_rejects_unsafe_args(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "case.k").write_text("*KEYWORD\n*END\n", encoding="utf-8")
            result = run_lsdyna_solver(
                k_path="case.k",
                additional_args=["shell"],
                dry_run=True,
                config=self._config(root),
            )
            self.assertFalse(result["ok"])
            self.assertIn("Unsupported solver argument", result["message"])

    def test_run_lsdyna_solver_captures_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            k_file = root / "case.k"
            k_file.write_text("*KEYWORD\n*END\n", encoding="utf-8")

            def fake_run(command, cwd, **kwargs):
                Path(cwd, "d3hsp").write_text(
                    "cycle = 20 time = 1.0e-3\nnormal termination\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout="solver ok",
                    stderr="",
                )

            with patch("subprocess.run", side_effect=fake_run):
                result = run_lsdyna_solver(
                    k_path=str(k_file),
                    ncpu=2,
                    config=self._config(root),
                )
            self.assertTrue(result["ok"])
            self.assertEqual(result["diagnostics"]["completion_state"], "normal_termination")
            self.assertEqual(result["diagnostics"]["latest_cycle"], 20)
            self.assertTrue(Path(result["log_file"]).exists())

    def test_run_lsdyna_solver_visible_console_uses_new_console(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            k_file = root / "case.k"
            k_file.write_text("*KEYWORD\n*END\n", encoding="utf-8")

            class FakeProcess:
                pid = 1234

                def __init__(self) -> None:
                    self.returncode = 0

                def wait(self, timeout=None):
                    (root / "d3hsp").write_text(
                        "cycle = 1 time = 1.0e-6\nnormal termination\n",
                        encoding="utf-8",
                    )
                    return self.returncode

            with patch("subprocess.Popen", return_value=FakeProcess()) as fake_popen:
                result = run_lsdyna_solver(
                    k_path=str(k_file),
                    show_console=True,
                    config=self._config(root),
                )

            self.assertTrue(result["ok"])
            self.assertTrue(result["show_console"])
            self.assertEqual(result["process_id"], 1234)
            self.assertFalse(result["still_running"])
            self.assertEqual(result["diagnostics"]["completion_state"], "normal_termination")
            kwargs = fake_popen.call_args.kwargs
            self.assertEqual(kwargs["cwd"], str(root))
            self.assertEqual(kwargs["creationflags"], subprocess.CREATE_NEW_CONSOLE)

    def test_run_lsdyna_solver_visible_console_timeout_leaves_process_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            k_file = root / "case.k"
            k_file.write_text("*KEYWORD\n*END\n", encoding="utf-8")

            class FakeProcess:
                pid = 5678

                def wait(self, timeout=None):
                    (root / "messag").write_text(
                        "cycle = 5 time = 2.0e-6\n",
                        encoding="utf-8",
                    )
                    raise subprocess.TimeoutExpired(["solver"], timeout)

            with patch("subprocess.Popen", return_value=FakeProcess()):
                result = run_lsdyna_solver(
                    k_path=str(k_file),
                    show_console=True,
                    timeout=1,
                    config=self._config(root),
                )

            self.assertFalse(result["ok"])
            self.assertTrue(result["timed_out"])
            self.assertTrue(result["still_running"])
            self.assertEqual(result["process_id"], 5678)
            self.assertIn("still running", result["message"])

    def test_diagnose_lsdyna_logs_finds_errors_and_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "d3hsp").write_text(
                "Warning 123 something\n"
                "cycle = 7 time = 2.5e-4\n"
                "Error 405 negative volume\n",
                encoding="utf-8",
            )
            result = diagnose_lsdyna_logs(case_dir=str(root), config=self._config(root))
            self.assertTrue(result["ok"])
            self.assertEqual(result["completion_state"], "error_detected")
            self.assertTrue(result["has_errors"])
            self.assertTrue(result["has_warnings"])
            self.assertEqual(result["latest_time"], 2.5e-4)


if __name__ == "__main__":
    unittest.main()
