"""Batch post-processing over case directories."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import LsppConfig, load_yaml_file
from ..validators import (
    LsppValidationError,
    ensure_input_directory,
    ensure_input_file,
    ensure_output_path,
)
from ._common import get_config
from .ascii_curves import extract_ascii_curve
from .binout import extract_binout_curve
from .d3plot import export_d3plot_contour, extract_d3plot_node_history


def _resolve_task_paths(case_dir: Path, task: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(task)
    for key in [
        "d3plot_path",
        "file_path",
        "binout_path",
        "output_png",
        "output_csv",
    ]:
        if key in resolved and isinstance(resolved[key], str):
            candidate = Path(resolved[key])
            if not candidate.is_absolute():
                resolved[key] = str(case_dir / candidate)
    return resolved


def _run_task(task: dict[str, Any], case_dir: Path, cfg: LsppConfig) -> dict[str, Any]:
    task_type = task.get("type")
    params = _resolve_task_paths(case_dir, {k: v for k, v in task.items() if k != "type"})
    if task_type == "export_d3plot_contour":
        return export_d3plot_contour(config=cfg, **params)
    if task_type == "extract_ascii_curve":
        return extract_ascii_curve(config=cfg, **params)
    if task_type == "extract_d3plot_node_history":
        return extract_d3plot_node_history(config=cfg, **params)
    if task_type == "extract_binout_curve":
        return extract_binout_curve(config=cfg, **params)
    raise LsppValidationError(f"Unsupported batch task type: {task_type}")


def _summary_paths(cases_root: Path, cfg: LsppConfig, overwrite: bool) -> tuple[Path, Path]:
    json_path = cases_root / "summary.json"
    csv_path = cases_root / "summary.csv"
    if overwrite or (not json_path.exists() and not csv_path.exists()):
        return (
            ensure_output_path(json_path, cfg.workspace_root, cfg.resolved_allowed_roots(), overwrite),
            ensure_output_path(csv_path, cfg.workspace_root, cfg.resolved_allowed_roots(), overwrite),
        )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return (
        ensure_output_path(cases_root / f"summary_{stamp}.json", cfg.workspace_root, cfg.resolved_allowed_roots(), False),
        ensure_output_path(cases_root / f"summary_{stamp}.csv", cfg.workspace_root, cfg.resolved_allowed_roots(), False),
    )


def batch_postprocess_cases(
    cases_root: str,
    task_config_path: str,
    overwrite: bool = False,
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        root = ensure_input_directory(
            cases_root,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="cases_root",
        )
        task_config = ensure_input_file(
            task_config_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="task_config_path",
        )
        task_data = load_yaml_file(task_config)
        tasks = task_data.get("tasks", [])
        if not isinstance(tasks, list) or not tasks:
            raise LsppValidationError("task_config_path must define a non-empty tasks list")
        case_names = task_data.get("cases")
        if case_names is None:
            case_dirs = [path for path in sorted(root.iterdir()) if path.is_dir()]
        else:
            if not isinstance(case_names, list):
                raise LsppValidationError("cases must be a list when provided")
            case_dirs = [root / str(case_name) for case_name in case_names]

        rows: list[dict[str, Any]] = []
        failed_cases: list[str] = []
        for case_dir in case_dirs:
            case_failed = False
            for index, task in enumerate(tasks):
                if not isinstance(task, dict):
                    raise LsppValidationError("Each task must be a mapping")
                result = _run_task(task, case_dir, cfg)
                rows.append(
                    {
                        "case": case_dir.name,
                        "task_index": index,
                        "task_type": task.get("type", ""),
                        "ok": bool(result.get("ok")),
                        "message": result.get("message", ""),
                        "output": result.get("output_image")
                        or result.get("output_png")
                        or result.get("output_csv")
                        or "",
                        "generated_cfile": result.get("generated_cfile", ""),
                        "log_file": result.get("log_file", ""),
                    }
                )
                if not result.get("ok"):
                    case_failed = True
            if case_failed:
                failed_cases.append(case_dir.name)

        summary_json, summary_csv = _summary_paths(root, cfg, overwrite)
        summary_payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cases_root": str(root),
            "task_config_path": str(task_config),
            "failed_cases": failed_cases,
            "rows": rows,
        }
        summary_json.write_text(
            json.dumps(summary_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        with summary_csv.open("w", newline="", encoding="utf-8") as handle:
            fieldnames = [
                "case",
                "task_index",
                "task_type",
                "ok",
                "message",
                "output",
                "generated_cfile",
                "log_file",
            ]
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        return {
            "summary_json": str(summary_json),
            "summary_csv": str(summary_csv),
            "failed_cases": failed_cases,
            "ok": not failed_cases,
            "message": "Batch post-processing completed."
            if not failed_cases
            else "Batch post-processing completed with failed cases.",
        }
    except Exception as exc:
        return {
            "summary_json": "",
            "summary_csv": "",
            "failed_cases": [],
            "ok": False,
            "message": str(exc),
        }
