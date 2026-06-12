"""LS-DYNA result inspection, curve metrics, and case comparison tools."""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from typing import Any, Sequence

from ..config import LsppConfig
from ..validators import (
    LsppValidationError,
    ensure_input_directory,
    ensure_input_file,
    ensure_output_path,
)
from ._common import get_config, result_from_validation_error
from .solver import diagnose_lsdyna_logs


RESULT_PATTERNS: dict[str, list[str]] = {
    "d3plot": ["d3plot", "d3plot[0-9][0-9]", "d3plot[0-9][0-9][0-9]"],
    "d3part": ["d3part", "d3part[0-9][0-9]", "d3part[0-9][0-9][0-9]"],
    "binout": ["binout", "binout[0-9][0-9][0-9][0-9]"],
    "ascii": ["glstat", "matsum", "nodout", "rcforc", "trhist", "dbfsi"],
    "logs": ["d3hsp", "messag", "messag.*", "status.out", "status", "status.*"],
}
NUMERIC_SPLIT_RE = re.compile(r"[\s,]+")


def _file_info(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "name": path.name,
        "size_bytes": stat.st_size,
        "modified": stat.st_mtime,
    }


def _collect_result_files(case_dir: Path) -> dict[str, list[dict[str, Any]]]:
    collected: dict[str, list[dict[str, Any]]] = {}
    for category, patterns in RESULT_PATTERNS.items():
        files: list[Path] = []
        for pattern in patterns:
            files.extend(path for path in case_dir.glob(pattern) if path.is_file())
        collected[category] = [_file_info(path) for path in sorted(set(files))]
    return collected


def _available_actions(files: dict[str, list[dict[str, Any]]]) -> list[str]:
    actions: list[str] = []
    if files.get("d3plot") or files.get("d3part"):
        actions.extend(
            [
                "export_contour_images",
                "export_multi_state_images",
                "extract_node_history",
            ]
        )
    if files.get("binout"):
        actions.append("extract_binout_curves")
    if files.get("ascii"):
        actions.append("extract_ascii_curves")
    if files.get("logs"):
        actions.append("diagnose_logs")
    return actions


def inspect_lsdyna_results(
    case_dir: str,
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        directory = ensure_input_directory(
            case_dir,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="case_dir",
        )
        files = _collect_result_files(directory)
        diagnostics = diagnose_lsdyna_logs(case_dir=str(directory), config=cfg)
        return {
            "ok": True,
            "message": "LS-DYNA result directory inspected.",
            "case_dir": str(directory),
            "files": files,
            "file_counts": {key: len(value) for key, value in files.items()},
            "diagnostics": diagnostics,
            "available_actions": _available_actions(files),
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["case_dir"] = str(case_dir)
        return result


def _parse_curve_table(path: Path) -> tuple[list[str], list[list[float]]]:
    raw_lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "$"))
    ]
    if not raw_lines:
        raise LsppValidationError(f"curve file is empty: {path}")

    header: list[str] | None = None
    rows: list[list[float]] = []
    for line in raw_lines:
        parts = [part for part in NUMERIC_SPLIT_RE.split(line) if part]
        if not parts:
            continue
        try:
            row = [float(part) for part in parts]
        except ValueError:
            if header is None:
                header = parts
            continue
        rows.append(row)
    if not rows:
        raise LsppValidationError(f"curve file has no numeric rows: {path}")
    width = max(len(row) for row in rows)
    rows = [row for row in rows if len(row) == width]
    if not rows:
        raise LsppValidationError(f"curve file has inconsistent numeric rows: {path}")
    if header is None or len(header) != width:
        header = ["x"] + [f"y{index}" for index in range(1, width)]
    return header, rows


def _column_index(columns: list[str], selector: str | int | None, default: int) -> int:
    if selector is None:
        return default
    if isinstance(selector, int):
        index = selector
    elif str(selector).isdigit():
        index = int(str(selector))
    else:
        lowered = str(selector).strip().lower()
        for index, column in enumerate(columns):
            if column.strip().lower() == lowered:
                return index
        raise LsppValidationError(f"column not found: {selector}")
    if index < 0 or index >= len(columns):
        raise LsppValidationError(f"column index out of range: {selector}")
    return index


def _window_rows(
    rows: list[list[float]],
    x_index: int,
    time_window: Sequence[float] | None,
) -> list[list[float]]:
    if time_window is None:
        return rows
    if len(time_window) != 2:
        raise LsppValidationError("time_window must contain [start, end]")
    start, end = float(time_window[0]), float(time_window[1])
    if end < start:
        raise LsppValidationError("time_window end must be greater than or equal to start")
    filtered = [row for row in rows if start <= row[x_index] <= end]
    if not filtered:
        raise LsppValidationError("time_window selected no rows")
    return filtered


def _integral(xs: list[float], ys: list[float]) -> float:
    total = 0.0
    for index in range(1, len(xs)):
        total += 0.5 * (ys[index - 1] + ys[index]) * (xs[index] - xs[index - 1])
    return total


def _series_metrics(xs: list[float], ys: list[float]) -> dict[str, float]:
    max_index = max(range(len(ys)), key=lambda index: ys[index])
    min_index = min(range(len(ys)), key=lambda index: ys[index])
    abs_index = max(range(len(ys)), key=lambda index: abs(ys[index]))
    mean = sum(ys) / len(ys)
    rms = math.sqrt(sum(value * value for value in ys) / len(ys))
    return {
        "max": ys[max_index],
        "time_at_max": xs[max_index],
        "min": ys[min_index],
        "time_at_min": xs[min_index],
        "abs_max": ys[abs_index],
        "time_at_abs_max": xs[abs_index],
        "final": ys[-1],
        "mean": mean,
        "rms": rms,
        "integral": _integral(xs, ys),
    }


def extract_lsdyna_metrics(
    curve_csv: str,
    output_json: str | None = None,
    x_column: str | int | None = None,
    y_columns: Sequence[str | int] | None = None,
    time_window: Sequence[float] | None = None,
    overwrite: bool = False,
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        curve = ensure_input_file(
            curve_csv,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="curve_csv",
        )
        columns, rows = _parse_curve_table(curve)
        x_index = _column_index(columns, x_column, 0)
        selected_rows = _window_rows(rows, x_index, time_window)
        if y_columns is None:
            y_indices = [index for index in range(len(columns)) if index != x_index]
        else:
            y_indices = [_column_index(columns, item, 1) for item in y_columns]
        xs = [row[x_index] for row in selected_rows]
        metrics = {
            columns[index]: _series_metrics(xs, [row[index] for row in selected_rows])
            for index in y_indices
        }
        result = {
            "ok": True,
            "message": "Curve metrics extracted.",
            "curve_csv": str(curve),
            "row_count": len(selected_rows),
            "columns": columns,
            "x_column": columns[x_index],
            "metrics": metrics,
        }
        if output_json:
            output = ensure_output_path(
                output_json,
                cfg.workspace_root,
                cfg.resolved_allowed_roots(),
                overwrite=overwrite,
            )
            import json

            output.write_text(
                json.dumps(result, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            result["output_json"] = str(output)
        return result
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["curve_csv"] = str(curve_csv)
        return result


def compare_lsdyna_cases(
    cases_root: str,
    output_csv: str,
    metric_specs: Sequence[dict[str, Any]],
    case_glob: str = "*",
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
        if not metric_specs:
            raise LsppValidationError("metric_specs cannot be empty")
        case_dirs = sorted(path for path in root.glob(case_glob) if path.is_dir())
        if not case_dirs:
            raise LsppValidationError(f"No case directories matched: {case_glob}")
        records: list[dict[str, Any]] = []
        for case_dir in case_dirs:
            record: dict[str, Any] = {"case": case_dir.name, "case_dir": str(case_dir)}
            for spec in metric_specs:
                name = str(spec.get("name") or spec.get("curve_csv") or "metric")
                curve_path = case_dir / str(spec["curve_csv"])
                metric_result = extract_lsdyna_metrics(
                    curve_csv=str(curve_path),
                    x_column=spec.get("x_column"),
                    y_columns=[spec["y_column"]] if spec.get("y_column") is not None else None,
                    time_window=spec.get("time_window"),
                    config=cfg,
                )
                if not metric_result.get("ok"):
                    record[f"{name}.ok"] = False
                    record[f"{name}.message"] = metric_result.get("message", "")
                    continue
                metric_name = str(spec.get("metric", "max"))
                series_metrics = next(iter(metric_result["metrics"].values()))
                record[f"{name}.{metric_name}"] = series_metrics.get(metric_name)
                if f"time_at_{metric_name}" in series_metrics:
                    record[f"{name}.time_at_{metric_name}"] = series_metrics[
                        f"time_at_{metric_name}"
                    ]
                record[f"{name}.ok"] = True
            records.append(record)

        output = ensure_output_path(
            output_csv,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            overwrite=overwrite,
        )
        columns = sorted({key for record in records for key in record})
        preferred = ["case", "case_dir"]
        columns = preferred + [column for column in columns if column not in preferred]
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(records)
        return {
            "ok": True,
            "message": "Case comparison completed.",
            "cases_root": str(root),
            "output_csv": str(output),
            "case_count": len(records),
            "records_preview": records[:5],
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["cases_root"] = str(cases_root)
        result["output_csv"] = str(output_csv)
        return result
