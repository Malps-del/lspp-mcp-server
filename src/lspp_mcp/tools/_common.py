"""Shared helpers for tool modules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import LsppConfig, load_config
from ..runner import RunResult, check_required_output, run_lsprepost
from ..templates import create_run_dir, write_generated_cfile
from ..validators import (
    LsppValidationError,
    ensure_output_path,
    safe_cfile_string,
)


def get_config(config: LsppConfig | None) -> LsppConfig:
    return config if config is not None else load_config()


def result_from_validation_error(exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "message": str(exc),
        "generated_cfile": "",
        "log_file": "",
    }


def execute_generated_cfile(
    output_path: Path,
    tool_name: str,
    template_name: str,
    context: dict[str, Any],
    mode: str,
    window_size: str | None,
    use_nographics: bool,
    config: LsppConfig,
    timeout: int | None = None,
) -> tuple[Path, Path, RunResult, dict[str, Any]]:
    run_dir = create_run_dir(output_path, tool_name)
    cfile_path = write_generated_cfile(run_dir, template_name, context)
    log_file = run_dir / "run.json"
    run_result = run_lsprepost(
        cfile_path=cfile_path,
        mode=mode,  # type: ignore[arg-type]
        window_size=window_size,
        use_nographics=use_nographics,
        timeout=timeout or config.timeout_seconds,
        lsprepost_exe=config.lsprepost_exe,
        log_file=log_file,
    )
    output_check = check_required_output(output_path, run_result)
    return cfile_path, log_file, run_result, output_check


def finalize_output_result(
    output_key: str,
    output_path: Path,
    cfile_path: Path,
    log_file: Path,
    run_result: RunResult,
    output_check: dict[str, Any],
) -> dict[str, Any]:
    ok = bool(run_result.ok and output_check["nonempty"])
    if ok:
        message = "Output file generated successfully."
    elif not output_check["exists"]:
        message = "LS-PrePost ran but the expected output file was not generated."
    elif output_check["size_bytes"] == 0:
        message = "LS-PrePost generated an empty output file."
    else:
        message = run_result.message
    return {
        output_key: str(output_path),
        "generated_cfile": str(cfile_path),
        "log_file": str(log_file),
        "ok": ok,
        "message": message,
        "returncode": run_result.returncode,
    }


def prepare_output(
    output_path: str | Path,
    config: LsppConfig,
    overwrite: bool,
) -> Path:
    return ensure_output_path(
        output_path,
        config.workspace_root,
        config.resolved_allowed_roots(),
        overwrite=overwrite,
    )


def quote_path(path: Path) -> str:
    return safe_cfile_string(path)


def unsupported_error(message: str) -> LsppValidationError:
    return LsppValidationError(message)
