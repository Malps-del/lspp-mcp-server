"""Tools for LS-DYNA solver execution and log diagnostics."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from ..config import LsppConfig
from ..templates import create_run_dir
from ..validators import (
    LsppValidationError,
    ensure_input_directory,
    ensure_input_file,
    ensure_within_allowed_roots,
    positive_int,
    safe_token,
)
from ._common import get_config, result_from_validation_error


ERROR_PATTERNS = (
    "error",
    "fatal",
    "negative volume",
    "segmentation",
    "forrtl",
    "nan",
    "termination due to",
)
WARNING_PATTERNS = ("warning", "warn ")
NORMAL_TERMINATION_RE = re.compile(r"normal\s+termination", re.IGNORECASE)
TIME_RE = re.compile(r"\btime\s*[=:]\s*([+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)", re.IGNORECASE)
CYCLE_RE = re.compile(r"\b(?:cycle|ncycle)\s*[=:]\s*([0-9]+)", re.IGNORECASE)
SOLVER_ARG_RE = re.compile(r"^[A-Za-z0-9_.:+\-/*(),=]+$")


@dataclass(slots=True)
class SolverRunResult:
    ok: bool
    message: str
    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False


def _solver_exe(cfg: LsppConfig, solver_exe: str | None = None) -> Path:
    raw = solver_exe or cfg.lsdyna_exe
    if not raw:
        raise LsppValidationError("lsdyna_exe is not configured in config.yaml")
    path = Path(raw).expanduser().resolve(strict=False)
    if not path.exists() or not path.is_file():
        raise LsppValidationError(f"LS-DYNA executable not found: {path}")
    return path


def _work_dir(
    work_dir: str | None,
    k_path: Path,
    cfg: LsppConfig,
) -> Path:
    if work_dir:
        resolved = ensure_within_allowed_roots(
            work_dir, cfg.workspace_root, cfg.resolved_allowed_roots()
        )
    else:
        resolved = ensure_within_allowed_roots(
            k_path.parent, cfg.workspace_root, cfg.resolved_allowed_roots()
        )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _solver_command(
    exe: Path,
    k_path: Path,
    ncpu: int | None,
    memory: str | None,
    additional_args: Sequence[str] | None,
) -> list[str]:
    command = [str(exe), f"i={k_path}"]
    if ncpu is not None:
        cpus = positive_int(ncpu, "ncpu")
        if cpus < 1:
            raise LsppValidationError("ncpu must be greater than 0")
        command.append(f"ncpu={cpus}")
    if memory:
        command.append(f"memory={safe_token(memory, 'memory')}")
    for index, arg in enumerate(additional_args or []):
        token = _safe_solver_arg(arg, f"additional_args[{index}]")
        if token.lower().startswith(("system", "shell", "cmd", "exec")):
            raise LsppValidationError(f"Unsupported solver argument: {token}")
        command.append(token)
    return command


def _safe_solver_arg(value: str, label: str) -> str:
    token = str(value).strip()
    if not token or any(char in token for char in ['"', "\r", "\n"]):
        raise LsppValidationError(f"{label} cannot be empty or contain quotes/newlines")
    if not SOLVER_ARG_RE.match(token):
        raise LsppValidationError(f"{label} contains unsupported characters: {token}")
    return token


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def validate_lsdyna_solver(
    solver_exe: str | None = None,
    work_dir: str | None = None,
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        exe = _solver_exe(cfg, solver_exe)
        workspace = ensure_input_directory(
            work_dir or cfg.workspace_root,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="work_dir",
        )
        test_file = workspace / ".lspp_mcp_solver_validate.tmp"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        return {
            "ok": True,
            "message": "LS-DYNA executable and work directory are valid.",
            "lsdyna_exe": str(exe),
            "work_dir": str(workspace),
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["lsdyna_exe"] = str(solver_exe or cfg.lsdyna_exe)
        result["work_dir"] = str(work_dir or cfg.workspace_root)
        return result


def run_lsdyna_solver(
    k_path: str,
    work_dir: str | None = None,
    ncpu: int | None = None,
    memory: str | None = None,
    additional_args: Sequence[str] | None = None,
    dry_run: bool = False,
    solver_exe: str | None = None,
    timeout: int | None = None,
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        exe = _solver_exe(cfg, solver_exe)
        keyword = ensure_input_file(
            k_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="k_path",
        )
        cwd = _work_dir(work_dir, keyword, cfg)
        command = _solver_command(exe, keyword, ncpu, memory, additional_args)
        if dry_run:
            return {
                "ok": True,
                "message": "Dry run only; LS-DYNA was not started.",
                "command": command,
                "work_dir": str(cwd),
                "k_path": str(keyword),
            }

        run_dir = create_run_dir(cwd / "lsdyna_run.json", "run_lsdyna_solver")
        log_file = run_dir / "run.json"
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                text=True,
                capture_output=True,
                timeout=timeout or cfg.timeout_seconds,
                check=False,
            )
            run_result = SolverRunResult(
                ok=completed.returncode == 0,
                message="LS-DYNA completed successfully."
                if completed.returncode == 0
                else f"LS-DYNA failed with return code {completed.returncode}.",
                command=command,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        except subprocess.TimeoutExpired as exc:
            run_result = SolverRunResult(
                ok=False,
                message=f"LS-DYNA timed out after {timeout or cfg.timeout_seconds} seconds.",
                command=command,
                returncode=None,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                timed_out=True,
            )
        except OSError as exc:
            run_result = SolverRunResult(
                ok=False,
                message=f"Failed to start LS-DYNA: {exc}",
                command=command,
                returncode=None,
                stdout="",
                stderr=str(exc),
            )
        diagnostics = diagnose_lsdyna_logs(case_dir=str(cwd), config=cfg)
        payload = {
            "run": asdict(run_result),
            "diagnostics": diagnostics,
        }
        _write_json(log_file, payload)
        return {
            "ok": bool(run_result.ok and not diagnostics.get("has_errors")),
            "message": run_result.message,
            "command": command,
            "work_dir": str(cwd),
            "k_path": str(keyword),
            "returncode": run_result.returncode,
            "timed_out": run_result.timed_out,
            "diagnostics": diagnostics,
            "log_file": str(log_file),
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["k_path"] = str(k_path)
        return result


def _candidate_files(case_dir: Path) -> dict[str, list[Path]]:
    patterns = {
        "d3hsp": ["d3hsp"],
        "messag": ["messag", "messag.*", "message", "message.*"],
        "status": ["status.out", "status", "status.*"],
    }
    found: dict[str, list[Path]] = {}
    for label, label_patterns in patterns.items():
        matches: list[Path] = []
        for pattern in label_patterns:
            matches.extend(path for path in case_dir.glob(pattern) if path.is_file())
        found[label] = sorted(set(matches))
    return found


def _read_log_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _line_is_error(lowered: str) -> bool:
    if "0 error" in lowered or "no error" in lowered:
        return False
    return any(pattern in lowered for pattern in ERROR_PATTERNS)


def _parse_logs(files: list[Path], max_findings: int) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    normal_termination = False
    latest_time: float | None = None
    latest_cycle: int | None = None
    tail: list[str] = []

    for path in files:
        try:
            lines = _read_log_lines(path)
        except OSError as exc:
            findings.append(
                {
                    "severity": "error",
                    "file": str(path),
                    "line": 0,
                    "message": f"Could not read log file: {exc}",
                }
            )
            continue
        tail.extend(f"{path.name}: {line}" for line in lines[-10:] if line.strip())
        for line_number, line in enumerate(lines, start=1):
            lowered = line.lower()
            if NORMAL_TERMINATION_RE.search(line):
                normal_termination = True
            time_match = TIME_RE.search(line)
            if time_match:
                try:
                    latest_time = float(time_match.group(1))
                except ValueError:
                    pass
            cycle_match = CYCLE_RE.search(line)
            if cycle_match:
                latest_cycle = int(cycle_match.group(1))
            severity = ""
            if _line_is_error(lowered):
                severity = "error"
            elif any(pattern in lowered for pattern in WARNING_PATTERNS):
                severity = "warning"
            if severity and len(findings) < max_findings:
                findings.append(
                    {
                        "severity": severity,
                        "file": str(path),
                        "line": line_number,
                        "message": line.strip(),
                    }
                )
    has_errors = any(item["severity"] == "error" for item in findings)
    has_warnings = any(item["severity"] == "warning" for item in findings)
    if normal_termination and not has_errors:
        state = "normal_termination"
    elif has_errors:
        state = "error_detected"
    elif files:
        state = "running_or_incomplete"
    else:
        state = "no_logs_found"
    return {
        "completion_state": state,
        "normal_termination": normal_termination,
        "has_errors": has_errors,
        "has_warnings": has_warnings,
        "latest_time": latest_time,
        "latest_cycle": latest_cycle,
        "findings": findings,
        "tail": tail[-40:],
    }


def diagnose_lsdyna_logs(
    case_dir: str | None = None,
    d3hsp_path: str | None = None,
    messag_path: str | None = None,
    status_path: str | None = None,
    max_findings: int = 50,
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        limit = positive_int(max_findings, "max_findings")
        files: list[Path] = []
        if case_dir:
            directory = ensure_input_directory(
                case_dir,
                cfg.workspace_root,
                cfg.resolved_allowed_roots(),
                label="case_dir",
            )
            candidates = _candidate_files(directory)
            for items in candidates.values():
                files.extend(items)
        else:
            directory = None
        for label, raw_path in [
            ("d3hsp_path", d3hsp_path),
            ("messag_path", messag_path),
            ("status_path", status_path),
        ]:
            if raw_path:
                files.append(
                    ensure_input_file(
                        raw_path,
                        cfg.workspace_root,
                        cfg.resolved_allowed_roots(),
                        label=label,
                    )
                )
        unique_files = sorted({path.resolve(strict=False) for path in files})
        parsed = _parse_logs(unique_files, limit)
        return {
            "ok": True,
            "message": "LS-DYNA logs diagnosed.",
            "case_dir": str(directory) if directory else "",
            "files": [str(path) for path in unique_files],
            **parsed,
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["case_dir"] = str(case_dir or "")
        return result
