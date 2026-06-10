"""Tools that reuse the external LS-DYNA Batch Case Generator project."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from decimal import Decimal, InvalidOperation
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


def _format_value_for_name(value: Any) -> str:
    text = str(value).strip()
    return (
        text.replace("-", "m")
        .replace("+", "p")
        .replace(".", "p")
        .replace(" ", "_")
    )


def _validate_case_alias(alias: str) -> str:
    text = alias.strip()
    if not text:
        raise LsppValidationError("alias cannot be empty")
    if any(char in text for char in ['"', "'", "\r", "\n", " ", ",", "{", "}"]):
        raise LsppValidationError(
            "alias must be a single template-safe name without spaces or braces"
        )
    return text


def _coerce_sweep_value(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _build_sweep_values(
    values: list[int | float | str] | None,
    start: int | float | str | None,
    end: int | float | str | None,
    step: int | float | str | None,
) -> list[int | float | str]:
    if values is not None:
        if not values:
            raise LsppValidationError("values cannot be empty")
        return list(values)
    if start is None or end is None or step is None:
        raise LsppValidationError("Either values or start/end/step is required")
    try:
        current = Decimal(str(start))
        stop = Decimal(str(end))
        increment = Decimal(str(step))
    except InvalidOperation as exc:
        raise LsppValidationError("start/end/step must be numeric") from exc
    if increment == 0:
        raise LsppValidationError("step cannot be zero")
    if (stop - current) * increment < 0:
        raise LsppValidationError("step sign does not move from start toward end")

    sweep_values: list[int | float] = []
    guard = 0
    while (increment > 0 and current <= stop) or (increment < 0 and current >= stop):
        sweep_values.append(_coerce_sweep_value(current))
        current += increment
        guard += 1
        if guard > 10000:
            raise LsppValidationError("Too many sweep values; limit is 10000")
    if not sweep_values:
        raise LsppValidationError("No sweep values were generated")
    return sweep_values


def _resolve_optional_path(value: str | None, base_dir: Path) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve(strict=False)


def _auto_include_files(k_path: Path, cfg: LsppConfig) -> list[str]:
    allowed_roots = cfg.resolved_allowed_roots()
    lines = k_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    include_paths: list[str] = []
    for index, raw_line in enumerate(lines):
        keyword = raw_line.strip().upper()
        if keyword != "*INCLUDE":
            continue
        for candidate_line in lines[index + 1 :]:
            stripped = candidate_line.strip()
            if not stripped or stripped.startswith("$"):
                continue
            if stripped.startswith("*"):
                break
            raw_path = stripped.split(",", 1)[0].strip().strip('"').strip("'")
            if not raw_path:
                break
            include_path = _resolve_optional_path(raw_path, k_path.parent)
            if include_path is None:
                break
            resolved = ensure_within_allowed_roots(
                include_path,
                cfg.workspace_root,
                allowed_roots,
            )
            if not resolved.exists():
                raise LsppValidationError(f"Included file does not exist: {resolved}")
            include_paths.append(str(resolved))
            break
    return include_paths


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


def generate_lsdyna_parameter_sweep(
    k_path: str,
    parameter_name: str,
    output_dir: str,
    values: list[int | float | str] | None = None,
    start: int | float | str | None = None,
    end: int | float | str | None = None,
    step: int | float | str | None = None,
    data_type: str | None = None,
    output_mode: str = "separate_folders",
    folder_template: str | None = None,
    file_template: str = "{case_name}.k",
    include_index_csv: bool = True,
    include_index_excel: bool = False,
    copy_include_files: bool = True,
    copy_support_files: list[str] | None = None,
    preview_only: bool = False,
    preview_limit: int = 5,
    overwrite: bool = False,
    config: LsppConfig | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        source = ensure_input_file(
            k_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="k_path",
        )
        parameter_name = parameter_name.strip().lstrip("&")
        if not parameter_name or any(
            char in parameter_name for char in ['"', "'", "\r", "\n", " ", ","]
        ):
            raise LsppValidationError("parameter_name must be a single LS-DYNA parameter name")
        if output_mode not in {"flat", "separate_folders"}:
            raise LsppValidationError("output_mode must be flat or separate_folders")
        if data_type is not None and data_type not in {"int", "integer", "i", "float", "r"}:
            raise LsppValidationError("data_type must be int/integer/i or float/r")

        sweep_values = _build_sweep_values(values, start, end, step)
        limit = positive_int(preview_limit, "preview_limit")
        if limit < 1:
            raise LsppValidationError("preview_limit must be greater than 0")
        destination = ensure_within_allowed_roots(
            output_dir,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
        )
        if not preview_only:
            destination.mkdir(parents=True, exist_ok=True)
            if not overwrite and any(destination.iterdir()):
                raise LsppValidationError(
                    f"Output directory is not empty and overwrite=false: {destination}"
                )

        support_paths: list[str] = []
        if copy_include_files:
            support_paths.extend(_auto_include_files(source, cfg))
        if copy_support_files:
            for item in copy_support_files:
                support_path = _resolve_optional_path(str(item), source.parent)
                if support_path is None:
                    continue
                resolved = ensure_within_allowed_roots(
                    support_path,
                    cfg.workspace_root,
                    cfg.resolved_allowed_roots(),
                )
                if not resolved.exists():
                    raise LsppValidationError(f"copy support path does not exist: {resolved}")
                support_paths.append(str(resolved))

        deduped_support_paths = list(dict.fromkeys(support_paths))
        template = folder_template
        if template is None:
            template = (
                f"case_{{case_id:03d}}_{parameter_name}_"
                + "{"
                + parameter_name
                + "}"
            )

        result, _request_path, _log_path = _run_worker(
            cfg,
            {
                "command": "generate_parameter_sweep",
                "k_file_path": str(source),
                "parameter_name": parameter_name,
                "values": sweep_values,
                "data_type": data_type,
                "output": {
                    "output_dir": str(destination),
                    "output_mode": output_mode,
                    "folder_template": template,
                    "file_template": file_template,
                    "include_index_csv": include_index_csv,
                    "include_index_excel": include_index_excel,
                    "copy_support_files": deduped_support_paths,
                },
                "preview_only": preview_only,
                "preview_limit": limit,
            },
            (destination / "case_index.json") if destination else source,
            timeout=timeout,
        )
        result["copied_support_files"] = deduped_support_paths
        result["value_count"] = len(sweep_values)
        result["value_name_preview"] = [
            _format_value_for_name(value) for value in sweep_values[:limit]
        ]
        return result
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["k_path"] = str(k_path)
        result["parameter_name"] = str(parameter_name)
        return result


def generate_lsdyna_keyword_field_sweep(
    k_path: str,
    output_dir: str,
    values: list[int | float | str] | None = None,
    start: int | float | str | None = None,
    end: int | float | str | None = None,
    step: int | float | str | None = None,
    alias: str | None = None,
    keyword: str | None = None,
    keyword_instance: int = 1,
    line_number_in_block: int | None = None,
    file_line_number: int | None = None,
    field_number: int | None = None,
    field_name: str | None = None,
    current_value: str | None = None,
    data_type: str | None = None,
    output_mode: str = "separate_folders",
    folder_template: str | None = None,
    file_template: str = "{case_name}.k",
    include_index_csv: bool = True,
    include_index_excel: bool = False,
    copy_include_files: bool = True,
    copy_support_files: list[str] | None = None,
    preview_only: bool = False,
    preview_limit: int = 5,
    overwrite: bool = False,
    config: LsppConfig | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    target_label = (
        alias
        or field_name
        or (f"{str(keyword).strip().lstrip('*').lower()}_field" if keyword else "field_value")
    )
    try:
        source = ensure_input_file(
            k_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="k_path",
        )
        target_alias = _validate_case_alias(str(target_label))
        if file_line_number is None and not keyword:
            raise LsppValidationError("keyword is required when file_line_number is not provided")
        if output_mode not in {"flat", "separate_folders"}:
            raise LsppValidationError("output_mode must be flat or separate_folders")
        if data_type is not None and data_type not in {"int", "integer", "i", "float", "r"}:
            raise LsppValidationError("data_type must be int/integer/i or float/r")
        if field_number is not None:
            field_number = positive_int(field_number, "field_number")
            if field_number < 1:
                raise LsppValidationError("field_number must be 1-based and greater than 0")
        if keyword_instance is not None:
            keyword_instance = positive_int(keyword_instance, "keyword_instance")
            if keyword_instance < 1:
                raise LsppValidationError("keyword_instance must be 1-based and greater than 0")
        if line_number_in_block is not None:
            line_number_in_block = positive_int(line_number_in_block, "line_number_in_block")
            if line_number_in_block < 1:
                raise LsppValidationError(
                    "line_number_in_block must be 1-based and greater than 0"
                )
        if file_line_number is not None:
            file_line_number = positive_int(file_line_number, "file_line_number")
            if file_line_number < 1:
                raise LsppValidationError("file_line_number must be 1-based and greater than 0")

        sweep_values = _build_sweep_values(values, start, end, step)
        limit = positive_int(preview_limit, "preview_limit")
        if limit < 1:
            raise LsppValidationError("preview_limit must be greater than 0")
        destination = ensure_within_allowed_roots(
            output_dir,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
        )
        if not preview_only:
            destination.mkdir(parents=True, exist_ok=True)
            if not overwrite and any(destination.iterdir()):
                raise LsppValidationError(
                    f"Output directory is not empty and overwrite=false: {destination}"
                )

        support_paths: list[str] = []
        if copy_include_files:
            support_paths.extend(_auto_include_files(source, cfg))
        if copy_support_files:
            for item in copy_support_files:
                support_path = _resolve_optional_path(str(item), source.parent)
                if support_path is None:
                    continue
                resolved = ensure_within_allowed_roots(
                    support_path,
                    cfg.workspace_root,
                    cfg.resolved_allowed_roots(),
                )
                if not resolved.exists():
                    raise LsppValidationError(f"copy support path does not exist: {resolved}")
                support_paths.append(str(resolved))

        deduped_support_paths = list(dict.fromkeys(support_paths))
        template = folder_template
        if template is None:
            template = f"case_{{case_id:03d}}_{target_alias}_{{{target_alias}}}"

        target: dict[str, Any] = {
            "alias": target_alias,
            "keyword": keyword,
            "keyword_instance": keyword_instance,
            "line_number_in_block": line_number_in_block,
            "file_line_number": file_line_number,
            "field_number": field_number,
            "field_name": field_name,
            "current_value": current_value,
        }
        result, _request_path, _log_path = _run_worker(
            cfg,
            {
                "command": "generate_keyword_field_sweep",
                "k_file_path": str(source),
                "target": target,
                "values": sweep_values,
                "data_type": data_type,
                "output": {
                    "output_dir": str(destination),
                    "output_mode": output_mode,
                    "folder_template": template,
                    "file_template": file_template,
                    "include_index_csv": include_index_csv,
                    "include_index_excel": include_index_excel,
                    "copy_support_files": deduped_support_paths,
                },
                "preview_only": preview_only,
                "preview_limit": limit,
            },
            (destination / "case_index.json") if destination else source,
            timeout=timeout,
        )
        result["copied_support_files"] = deduped_support_paths
        result["value_count"] = len(sweep_values)
        result["value_name_preview"] = [
            _format_value_for_name(value) for value in sweep_values[:limit]
        ]
        return result
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["k_path"] = str(k_path)
        result["target_alias"] = str(target_label)
        return result
