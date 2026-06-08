"""Subprocess runner for LS-PrePost."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from .validators import output_file_check, validate_window_size


@dataclass
class RunResult:
    ok: bool
    message: str
    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    log_file: str | None = None
    timed_out: bool = False


def _write_log(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def append_output_check(log_file: str | Path | None, check: dict[str, Any]) -> None:
    if log_file is None:
        return
    path = Path(log_file)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {}
    payload["output_check"] = check
    _write_log(path, payload)


def run_lsprepost(
    cfile_path: Path,
    mode: Literal["curve", "image"],
    window_size: str | None,
    use_nographics: bool,
    timeout: int,
    lsprepost_exe: str | Path | None = None,
    log_file: str | Path | None = None,
) -> RunResult:
    """Run LS-PrePost with a generated cfile and capture logs.

    The first five parameters match the requested public signature. The
    executable and log destination are optional integration parameters used by
    the MCP tool layer.
    """

    exe = str(lsprepost_exe or os.environ.get("LSPREPOST_EXE") or "lsprepost")
    command = [exe, f"c={cfile_path}"]
    if use_nographics or mode == "curve":
        command.append("-nographics")
    elif mode == "image":
        command.append(f"w={validate_window_size(window_size or '1600x1200')}")

    log_path = Path(log_file) if log_file is not None else None
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        result = RunResult(
            ok=False,
            message=f"LS-PrePost timed out after {timeout} seconds.",
            command=command,
            returncode=None,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            log_file=str(log_path) if log_path else None,
            timed_out=True,
        )
    except OSError as exc:
        result = RunResult(
            ok=False,
            message=f"Failed to start LS-PrePost: {exc}",
            command=command,
            returncode=None,
            stdout="",
            stderr=str(exc),
            log_file=str(log_path) if log_path else None,
        )
    else:
        result = RunResult(
            ok=completed.returncode == 0,
            message=(
                "LS-PrePost completed successfully."
                if completed.returncode == 0
                else f"LS-PrePost failed with return code {completed.returncode}."
            ),
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            log_file=str(log_path) if log_path else None,
        )

    if log_path is not None:
        _write_log(log_path, {"run": asdict(result)})
    return result


def check_required_output(path: Path, run_result: RunResult) -> dict[str, Any]:
    check = output_file_check(path)
    append_output_check(run_result.log_file, check)
    return check
