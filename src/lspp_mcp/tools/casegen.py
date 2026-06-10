"""Tools that reuse the external LS-DYNA Batch Case Generator project."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..config import LsppConfig
from ..templates import create_run_dir
from ..validators import (
    LsppValidationError,
    ensure_input_file,
    ensure_within_allowed_roots,
    positive_int,
)
from ._common import get_config, result_from_validation_error


def _casegen_paths(cfg: LsppConfig) -> tuple[Path, Path]:
    if not cfg.case_generator_python:
        raise LsppValidationError(
            "case_generator_python is not configured in config.yaml"
        )
    if cfg.case_generator_src is None:
        raise LsppValidationError("case_generator_src is not configured in config.yaml")
    python = Path(cfg.case_generator_python).expanduser().resolve(strict=False)
    src = cfg.case_generator_src.expanduser().resolve(strict=False)
    if not python.exists() or not python.is_file():
        raise LsppValidationError(f"case_generator_python not found: {python}")
    if not src.exists() or not src.is_dir():
        raise LsppValidationError(f"case_generator_src not found: {src}")
    return python, src


def _read_project_config(config_path: Path) -> dict[str, Any]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise LsppValidationError("Batch generator project config must be a JSON object")
    return data


def _resolve_optional_path(value: str | None, base_dir: Path) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve(strict=False)


def _validate_project_config_paths(
    data: dict[str, Any],
    project_config_path: Path,
    cfg: LsppConfig,
    output_dir_override: str | None = None,
    excel_path_override: str | None = None,
    copy_support_files_override: list[str] | None = None,
    preview_only: bool = False,
    overwrite: bool = False,
) -> Path | None:
    allowed_roots = cfg.resolved_allowed_roots()
    base_dir = project_config_path.parent

    k_path = _resolve_optional_path(data.get("k_file_path"), base_dir)
    if k_path is not None:
        ensure_input_file(k_path, cfg.workspace_root, allowed_roots, label="k_file_path")

    generator = data.get("generator", {}) if isinstance(data.get("generator"), dict) else {}
    excel_path = _resolve_optional_path(
        excel_path_override or generator.get("excel_path"), base_dir
    )
    method = str(generator.get("method", "")).lower()
    if excel_path is not None and (excel_path_override or method == "excel"):
        ensure_input_file(excel_path, cfg.workspace_root, allowed_roots, label="excel_path")

    output = data.get("output", {}) if isinstance(data.get("output"), dict) else {}
    raw_output_dir = output_dir_override or output.get("output_dir")
    output_dir = _resolve_optional_path(raw_output_dir, base_dir)
    if output_dir is not None:
        ensure_within_allowed_roots(output_dir, cfg.workspace_root, allowed_roots)
        if not preview_only:
            output_dir.mkdir(parents=True, exist_ok=True)
            if not overwrite and any(output_dir.iterdir()):
                raise LsppValidationError(
                    f"Output directory is not empty and overwrite=false: {output_dir}"
                )
    elif not preview_only:
        raise LsppValidationError("output_dir is required for case export")

    support_paths = (
        copy_support_files_override
        if copy_support_files_override is not None
        else output.get("copy_support_files", [])
    )
    if support_paths:
        if not isinstance(support_paths, list):
            raise LsppValidationError("copy_support_files must be a list")
        for item in support_paths:
            support_path = _resolve_optional_path(str(item), base_dir)
            if support_path is None:
                continue
            resolved = ensure_within_allowed_roots(
                support_path, cfg.workspace_root, allowed_roots
            )
            if not resolved.exists():
                raise LsppValidationError(f"copy support path does not exist: {resolved}")
    return output_dir


def _run_worker(
    cfg: LsppConfig,
    request: dict[str, Any],
    run_dir_base: Path,
    timeout: int | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    python, src = _casegen_paths(cfg)
    run_dir = create_run_dir(run_dir_base, f"casegen_{request['command']}")
    request_path = run_dir / "request.json"
    response_path = run_dir / "response.json"
    log_path = run_dir / "run.json"
    request_path.write_text(
        json.dumps(request, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(src) if not existing_pythonpath else f"{src}{os.pathsep}{existing_pythonpath}"
    worker = Path(__file__).resolve().parents[1] / "casegen_worker.py"
    command = [str(python), str(worker), "--request", str(request_path)]
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=timeout or cfg.timeout_seconds,
        env=env,
    )
    try:
        payload = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {
            "ok": False,
            "message": "Case generator worker did not return valid JSON.",
            "stdout": completed.stdout,
        }
    if completed.returncode != 0 and payload.get("ok", True):
        payload["ok"] = False
        payload["message"] = completed.stderr or f"Worker exited with {completed.returncode}"
    response_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log_path.write_text(
        json.dumps(
            {
                "command": command,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    payload["generated_request"] = str(request_path)
    payload["log_file"] = str(log_path)
    payload["generated_response"] = str(response_path)
    return payload, request_path, log_path


def validate_case_generator_integration(
    config: LsppConfig | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        python, src = _casegen_paths(cfg)
        run_base = ensure_within_allowed_roots(
            cfg.workspace_root / "case_generator_validation.json",
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
        )
        result, _request_path, _log_path = _run_worker(
            cfg,
            {"command": "validate"},
            run_base,
            timeout=timeout,
        )
        result["case_generator_python"] = str(python)
        result["case_generator_src"] = str(src)
        return result
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["case_generator_python"] = cfg.case_generator_python
        result["case_generator_src"] = str(cfg.case_generator_src or "")
        return result


def inspect_lsdyna_case_config(
    project_config_path: str,
    config: LsppConfig | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        config_path = ensure_input_file(
            project_config_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="project_config_path",
        )
        _validate_project_config_paths(
            _read_project_config(config_path),
            config_path,
            cfg,
            preview_only=True,
        )
        result, _request_path, _log_path = _run_worker(
            cfg,
            {
                "command": "inspect_config",
                "project_config_path": str(config_path),
            },
            config_path,
            timeout=timeout,
        )
        return result
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["project_config_path"] = str(project_config_path)
        return result


def generate_lsdyna_cases(
    project_config_path: str,
    output_dir: str | None = None,
    method: str | None = None,
    sample_count: int | None = None,
    random_seed: int | None = None,
    avoid_duplicates: bool | None = None,
    integer_rounding: str | None = None,
    excel_path: str | None = None,
    output_mode: str | None = None,
    folder_template: str | None = None,
    file_template: str | None = None,
    include_index_csv: bool | None = None,
    include_index_excel: bool | None = None,
    copy_support_files: list[str] | None = None,
    preview_only: bool = False,
    preview_limit: int = 5,
    overwrite: bool = False,
    config: LsppConfig | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        config_path = ensure_input_file(
            project_config_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="project_config_path",
        )
        if sample_count is not None:
            sample_count = positive_int(sample_count, "sample_count")
            if sample_count < 1:
                raise LsppValidationError("sample_count must be greater than 0")
        limit = positive_int(preview_limit, "preview_limit")
        data = _read_project_config(config_path)
        resolved_output_dir = _validate_project_config_paths(
            data,
            config_path,
            cfg,
            output_dir_override=output_dir,
            excel_path_override=excel_path,
            copy_support_files_override=copy_support_files,
            preview_only=preview_only,
            overwrite=overwrite,
        )
        overrides = {
            "output_dir": str(resolved_output_dir) if resolved_output_dir else None,
            "method": method,
            "sample_count": sample_count,
            "random_seed": random_seed,
            "avoid_duplicates": avoid_duplicates,
            "integer_rounding": integer_rounding,
            "excel_path": excel_path,
            "output_mode": output_mode,
            "folder_template": folder_template,
            "file_template": file_template,
            "include_index_csv": include_index_csv,
            "include_index_excel": include_index_excel,
            "copy_support_files": copy_support_files,
        }
        result, _request_path, _log_path = _run_worker(
            cfg,
            {
                "command": "generate_cases",
                "project_config_path": str(config_path),
                "overrides": overrides,
                "preview_only": preview_only,
                "preview_limit": limit,
            },
            (resolved_output_dir / "case_index.json")
            if resolved_output_dir
            else config_path,
            timeout=timeout,
        )
        return result
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["project_config_path"] = str(project_config_path)
        return result
