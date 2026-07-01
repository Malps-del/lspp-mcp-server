"""Tools for extracting LS-DYNA binout curves.

The legacy backend drives LS-PrePost/binaski. The lasso backend reads binout
files directly through optional ``lasso-python`` and is better suited to large
MPP binout shards.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from ..config import LsppConfig
from ..validators import (
    LsppValidationError,
    ensure_input_file,
    ensure_output_path,
    ensure_within_allowed_roots,
    positive_int,
    safe_token,
)
from ._common import (
    execute_generated_cfile,
    finalize_output_result,
    get_config,
    prepare_output,
    quote_path,
    result_from_validation_error,
)


VALID_BINOUT_BLOCKS = {"glstat", "matsum", "nodout", "trhist", "dbfsi"}
VALID_BINOUT_BACKENDS = {"auto", "lasso", "lsprepost"}
DEFAULT_METRICS = ("peak", "time_at_peak", "min", "final", "positive_impulse")
INSTALL_LASSO_MESSAGE = (
    "lasso-python is required for backend='lasso'. Install it with: "
    "pip install lasso-python h5py pandas rich"
)


def _validate_backend(backend: str) -> str:
    normalized = backend.strip().lower()
    if normalized not in VALID_BINOUT_BACKENDS:
        raise LsppValidationError(
            f"backend must be one of: {', '.join(sorted(VALID_BINOUT_BACKENDS))}"
        )
    return normalized


def _split_variable_path(block: str | None, variable: str) -> tuple[str, str]:
    text = variable.strip().strip("/")
    if "/" in text:
        parts = [part for part in text.split("/") if part]
        if len(parts) < 2:
            raise LsppValidationError(f"Invalid binout variable path: {variable}")
        path_block = parts[0].lower()
        path_variable = "/".join(parts[1:])
        if block and block.lower() not in {"", path_block}:
            raise LsppValidationError(
                f"Variable path block '{path_block}' does not match block '{block}'."
            )
        return path_block, path_variable
    if not block:
        raise LsppValidationError("block is required when variable is not a path.")
    return block.lower(), text


def _resolve_binout_entry(
    variable_maps: dict[str, Any],
    block: str,
    variable: str,
    entity_index: int | None,
) -> dict[str, Any]:
    block_map = variable_maps.get("binout", {}).get(block, {})
    configured = block_map.get(variable, {})
    if configured and not isinstance(configured, dict):
        raise LsppValidationError(f"binout map entry must be a mapping: {block}.{variable}")
    if configured:
        plot_variable = safe_token(configured.get("variable", variable), "binout variable")
        index1 = positive_int(configured.get("index1", 0), "index1")
        index2 = positive_int(configured.get("index2", 1), "index2")
        configured_entity = configured.get("entity_index", 0)
    else:
        plot_variable = safe_token(variable, "binout variable")
        index1 = 0
        index2 = 1
        configured_entity = 0
    return {
        "binout_variable": plot_variable,
        "index1": index1,
        "index2": index2,
        "entity_index": positive_int(
            configured_entity if entity_index is None else entity_index,
            "entity_index",
        ),
    }


def _path_has_glob(path: str) -> bool:
    return any(char in path for char in "*?[")


def _resolve_binout_source(binout_path: str, cfg: LsppConfig) -> dict[str, Any]:
    allowed_roots = cfg.resolved_allowed_roots()
    if _path_has_glob(binout_path):
        pattern = ensure_within_allowed_roots(binout_path, cfg.workspace_root, allowed_roots)
        parent = pattern.parent
        ensure_within_allowed_roots(parent, cfg.workspace_root, allowed_roots)
        matches = sorted(path for path in parent.glob(pattern.name) if path.is_file())
        if not matches:
            raise LsppValidationError(f"binout glob did not match any files: {pattern}")
        for match in matches:
            ensure_within_allowed_roots(match, cfg.workspace_root, allowed_roots)
        lsprepost_input = matches[0]
        lasso_input = str(pattern)
    else:
        input_file = ensure_input_file(
            binout_path,
            cfg.workspace_root,
            allowed_roots,
            label="binout file",
        )
        siblings = sorted(path for path in input_file.parent.glob("binout*") if path.is_file())
        if input_file.name.lower().startswith("binout") and len(siblings) > 1:
            for sibling in siblings:
                ensure_within_allowed_roots(sibling, cfg.workspace_root, allowed_roots)
            lasso_input = str(input_file.parent / "binout*")
        else:
            lasso_input = str(input_file)
        lsprepost_input = input_file
        matches = siblings if "*" in lasso_input else [input_file]
    return {
        "lsprepost_input": lsprepost_input,
        "lasso_input": lasso_input,
        "matched_files": [str(path) for path in matches],
        "mpp_shards": len(matches),
    }


def _load_lasso_binout_class() -> Any:
    try:
        from lasso.dyna import Binout  # type: ignore
    except ModuleNotFoundError as exc:
        raise LsppValidationError(INSTALL_LASSO_MESSAGE) from exc
    return Binout


def _open_lasso_binout(source: str) -> Any:
    Binout = _load_lasso_binout_class()
    binout = Binout(source)
    try:
        binout.read()
    except TypeError:
        pass
    return binout


def _read_lasso_path(binout: Any, path: list[str]) -> Any:
    try:
        return binout.read(*path)
    except TypeError:
        return binout.read("/".join(path))


def _read_lasso_optional(binout: Any, path: list[str]) -> Any | None:
    try:
        return _read_lasso_path(binout, path)
    except Exception:
        return None


def _is_child_listing(value: Any) -> bool:
    if isinstance(value, dict):
        return True
    if isinstance(value, (str, bytes)) or value is None:
        return False
    if isinstance(value, (list, tuple, set)):
        return all(isinstance(item, str) for item in value)
    return False


def _children_from_listing(value: Any) -> list[str]:
    if isinstance(value, dict):
        return sorted(str(key) for key in value.keys())
    if isinstance(value, (list, tuple, set)):
        return sorted(str(item) for item in value)
    return []


def _shape_dtype(value: Any) -> dict[str, Any]:
    shape = getattr(value, "shape", None)
    dtype = getattr(value, "dtype", None)
    if shape is None:
        rows = _to_list(value)
        shape = _infer_shape(rows)
    return {
        "shape": [int(item) for item in shape] if shape is not None else [],
        "dtype": str(dtype) if dtype is not None else type(value).__name__,
    }


def _to_list(value: Any) -> list[Any]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, tuple):
        value = list(value)
    if isinstance(value, list):
        return value
    return [value]


def _infer_shape(value: Any) -> list[int]:
    if hasattr(value, "shape"):
        return [int(item) for item in value.shape]
    if not isinstance(value, list):
        return []
    if not value:
        return [0]
    first = value[0]
    if isinstance(first, list):
        return [len(value), len(first)]
    return [len(value)]


def _as_float_list(value: Any, label: str) -> list[float]:
    values = _to_list(value)
    try:
        return [float(item) for item in values]
    except (TypeError, ValueError) as exc:
        raise LsppValidationError(f"{label} must be numeric.") from exc


def _as_2d_rows(value: Any, time_len: int, label: str) -> tuple[list[list[float]], bool]:
    raw = _to_list(value)
    if not raw:
        raise LsppValidationError(f"{label} is empty.")
    if not isinstance(raw[0], list):
        if len(raw) != time_len:
            raise LsppValidationError(
                f"{label} length {len(raw)} does not match time length {time_len}."
            )
        return [[float(item)] for item in raw], False
    rows = [[float(item) for item in row] for row in raw]
    if len(rows) == time_len:
        return rows, True
    if rows and len(rows[0]) == time_len:
        return [list(column) for column in zip(*rows)], True
    raise LsppValidationError(
        f"{label} shape {_infer_shape(raw)} is incompatible with time length {time_len}."
    )


def _read_time(binout: Any, block: str) -> list[float]:
    time_data = _read_lasso_optional(binout, [block, "time"])
    if time_data is None:
        time_data = _read_lasso_optional(binout, ["time"])
    if time_data is None:
        raise LsppValidationError(f"No time variable found for binout block '{block}'.")
    return _as_float_list(time_data, f"{block}/time")


def _read_entity_labels(binout: Any, block: str, count: int) -> list[str]:
    for name in ("ids", "legend_ids", "legend", "labels"):
        labels = _read_lasso_optional(binout, [block, name])
        if labels is None:
            continue
        values = [str(item).strip() for item in _to_list(labels)]
        if len(values) == count and len(set(values)) == count:
            return values
    return [f"entity_{index}" for index in range(count)]


def _sanitize_variable_name(variable: str) -> str:
    return variable.strip("/").split("/")[-1].replace(" ", "_")


def _write_lasso_csv(
    output: Path,
    times: list[float],
    rows: list[list[float]],
    headers: list[str],
) -> None:
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time", *headers])
        for time_value, values in zip(times, rows):
            writer.writerow([time_value, *values])


def _curve_from_lasso(
    binout: Any,
    block: str,
    variable: str,
    entity_index: int | None,
) -> dict[str, Any]:
    times = _read_time(binout, block)
    data = _read_lasso_optional(binout, [block, *variable.split("/")])
    if data is None:
        raise LsppValidationError(f"Variable not found in binout: {block}/{variable}")
    rows, multi_entity = _as_2d_rows(data, len(times), f"{block}/{variable}")
    variable_name = _sanitize_variable_name(variable)
    if multi_entity and entity_index is not None:
        index = positive_int(entity_index, "entity_index")
        if index >= len(rows[0]):
            raise LsppValidationError(
                f"entity_index {index} is out of range for {block}/{variable} "
                f"with {len(rows[0])} entities."
            )
        rows = [[row[index]] for row in rows]
        headers = ["value"]
        selected_entity = index
    elif multi_entity:
        headers = _read_entity_labels(binout, block, len(rows[0]))
        selected_entity = None
    else:
        headers = ["value"]
        selected_entity = None
    return {
        "time": times,
        "rows": rows,
        "headers": headers,
        "block": block,
        "variable": variable,
        "variable_name": variable_name,
        "is_multi_entity": multi_entity,
        "selected_entity_index": selected_entity,
    }


def _integrate_positive(times: list[float], values: list[float]) -> float:
    total = 0.0
    for left in range(len(times) - 1):
        dt = times[left + 1] - times[left]
        y0 = max(values[left], 0.0)
        y1 = max(values[left + 1], 0.0)
        total += 0.5 * (y0 + y1) * dt
    return total


def _window_curve(
    times: list[float],
    values: list[float],
    window: list[float] | tuple[float, float] | None,
) -> tuple[list[float], list[float]]:
    if window is None:
        return times, values
    start, end = float(window[0]), float(window[1])
    filtered = [(time, value) for time, value in zip(times, values) if start <= time <= end]
    if not filtered:
        return [], []
    return [item[0] for item in filtered], [item[1] for item in filtered]


def _metrics_for_series(
    times: list[float],
    values: list[float],
    metrics: list[str],
    time_window: list[float] | tuple[float, float] | None = None,
) -> dict[str, float | None]:
    window_times, window_values = _window_curve(times, values, time_window)
    if not window_values:
        return {name: None for name in metrics}
    peak = max(window_values)
    peak_index = window_values.index(peak)
    result: dict[str, float | None] = {}
    for name in metrics:
        if name == "peak":
            result[name] = peak
        elif name == "time_at_peak":
            result[name] = window_times[peak_index]
        elif name == "min":
            result[name] = min(window_values)
        elif name == "final":
            result[name] = window_values[-1]
        elif name == "positive_impulse":
            result[name] = _integrate_positive(window_times, window_values)
        else:
            raise LsppValidationError(f"Unsupported binout metric: {name}")
    return result


def _arrival_time(times: list[float], values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    peak = max(values)
    if peak <= 0.0:
        return None
    threshold = peak * fraction
    for time_value, value in zip(times, values):
        if value >= threshold:
            return time_value
    return None


def _curve_metrics(
    curve: dict[str, Any],
    metrics: list[str] | None,
    time_window: list[float] | None = None,
) -> dict[str, Any]:
    metric_names = metrics or list(DEFAULT_METRICS)
    columns: dict[str, Any] = {}
    for column, header in enumerate(curve["headers"]):
        values = [row[column] for row in curve["rows"]]
        columns[header] = _metrics_for_series(curve["time"], values, metric_names, time_window)
    return {"columns": columns, "metrics": metric_names}


def _pressure_proxy_curve(
    binout: Any,
    entity_index: int | None,
) -> dict[str, Any]:
    sx = _curve_from_lasso(binout, "trhist", "sx", entity_index)
    sy = _curve_from_lasso(binout, "trhist", "sy", entity_index)
    sz = _curve_from_lasso(binout, "trhist", "sz", entity_index)
    if sx["time"] != sy["time"] or sx["time"] != sz["time"]:
        raise LsppValidationError("trhist sx/sy/sz time arrays do not match.")
    if sx["headers"] != sy["headers"] or sx["headers"] != sz["headers"]:
        raise LsppValidationError("trhist sx/sy/sz entity labels do not match.")
    rows: list[list[float]] = []
    for row_sx, row_sy, row_sz in zip(sx["rows"], sy["rows"], sz["rows"]):
        rows.append(
            [
                -1.0 * (vx + vy + vz) / 3.0
                for vx, vy, vz in zip(row_sx, row_sy, row_sz)
            ]
        )
    return {
        "time": sx["time"],
        "rows": rows,
        "headers": sx["headers"],
        "block": "trhist",
        "variable": "p_proxy",
        "variable_name": "p_proxy",
        "is_multi_entity": sx["is_multi_entity"],
        "selected_entity_index": sx["selected_entity_index"],
    }


def _underwater_pressure_metrics(
    curve: dict[str, Any],
    shock_window: list[float] | None,
    bubble_window: list[float] | None,
    arrival_threshold_fraction: float,
) -> dict[str, Any]:
    columns: dict[str, Any] = {}
    for column, header in enumerate(curve["headers"]):
        values = [row[column] for row in curve["rows"]]
        peak = max(values) if values else math.nan
        peak_index = values.index(peak) if values else -1
        after_peak = [curve["time"][peak_index], curve["time"][-1]] if peak_index >= 0 else None
        columns[header] = {
            "peak_pressure": peak if values else None,
            "arrival_time": _arrival_time(curve["time"], values, arrival_threshold_fraction),
            "time_at_peak_pressure": curve["time"][peak_index] if peak_index >= 0 else None,
            "shock_impulse": _metrics_for_series(
                curve["time"], values, ["positive_impulse"], shock_window
            )["positive_impulse"],
            "post_shock_bubble_impulse": _metrics_for_series(
                curve["time"],
                values,
                ["positive_impulse"],
                bubble_window if bubble_window is not None else after_peak,
            )["positive_impulse"],
        }
    return {"columns": columns}


def _extract_binout_curve_lasso(
    binout_path: str,
    block: str,
    variable: str,
    output_csv: str,
    entity_index: int | None,
    overwrite: bool,
    config: LsppConfig,
) -> dict[str, Any]:
    source = _resolve_binout_source(binout_path, config)
    output = ensure_output_path(
        output_csv,
        config.workspace_root,
        config.resolved_allowed_roots(),
        overwrite=overwrite,
    )
    block_name, variable_name = _split_variable_path(block, variable)
    if block_name not in VALID_BINOUT_BLOCKS:
        raise LsppValidationError(
            f"block must be one of: {', '.join(sorted(VALID_BINOUT_BLOCKS))}"
        )
    binout = _open_lasso_binout(source["lasso_input"])
    curve = _curve_from_lasso(binout, block_name, variable_name, entity_index)
    _write_lasso_csv(output, curve["time"], curve["rows"], curve["headers"])
    return {
        "ok": True,
        "message": "binout CSV generated with lasso-python backend.",
        "backend": "lasso",
        "output_csv": str(output),
        "binout_source": source["lasso_input"],
        "matched_files": source["matched_files"],
        "mpp_shards": source["mpp_shards"],
        "block": block_name,
        "variable": variable_name,
        "columns": ["time", *curve["headers"]],
        "row_count": len(curve["time"]),
        "metrics": _curve_metrics(curve, None),
        "generated_cfile": "",
        "log_file": "",
    }


def _extract_binout_curve_lsprepost(
    binout_path: str,
    block: str,
    variable: str,
    output_csv: str,
    entity_index: int | None,
    mpp: bool,
    xyplot_window: int,
    overwrite: bool,
    config: LsppConfig,
    timeout: int | None,
) -> dict[str, Any]:
    if block not in VALID_BINOUT_BLOCKS:
        raise LsppValidationError(
            f"block must be one of: {', '.join(sorted(VALID_BINOUT_BLOCKS))}"
        )
    source = _resolve_binout_source(binout_path, config)
    output = prepare_output(output_csv, config, overwrite)
    resolved = _resolve_binout_entry(config.variable_maps, block, variable, entity_index)
    context = {
        "binout_path": quote_path(source["lsprepost_input"]),
        "block": block,
        "index1": resolved["index1"],
        "index2": resolved["index2"],
        "entity_index": resolved["entity_index"],
        "binout_variable": resolved["binout_variable"],
        "xyplot_window": positive_int(xyplot_window, "xyplot_window"),
        "output_csv": quote_path(output),
        "mpp_note": "c MPP binout0000 input" if mpp else "c SMP binout input",
    }
    cfile_path, log_file, run_result, output_check = execute_generated_cfile(
        output_path=output,
        tool_name=f"extract_binout_{block}",
        template_name="extract_binout_curve.cfile.j2",
        context=context,
        mode="curve",
        window_size=None,
        use_nographics=True,
        config=config,
        timeout=timeout,
    )
    result = finalize_output_result(
        "output_csv", output, cfile_path, log_file, run_result, output_check
    )
    result["backend"] = "lsprepost"
    result["binout_source"] = str(source["lsprepost_input"])
    result["matched_files"] = source["matched_files"]
    result["mpp_shards"] = source["mpp_shards"]
    return result


def extract_binout_curve(
    binout_path: str,
    block: str,
    variable: str,
    output_csv: str,
    entity_index: int | None = None,
    mpp: bool = False,
    xyplot_window: int = 1,
    overwrite: bool = False,
    backend: str = "auto",
    config: LsppConfig | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        selected_backend = _validate_backend(backend)
        block_name, variable_name = _split_variable_path(block, variable)
        if selected_backend == "lsprepost":
            return _extract_binout_curve_lsprepost(
                binout_path,
                block_name,
                variable_name,
                output_csv,
                entity_index,
                mpp,
                xyplot_window,
                overwrite,
                cfg,
                timeout,
            )
        try:
            return _extract_binout_curve_lasso(
                binout_path,
                block_name,
                variable_name,
                output_csv,
                entity_index,
                overwrite,
                cfg,
            )
        except Exception as lasso_exc:
            if selected_backend == "lasso":
                raise
            fallback = _extract_binout_curve_lsprepost(
                binout_path,
                block_name,
                variable_name,
                output_csv,
                entity_index,
                mpp,
                xyplot_window,
                overwrite,
                cfg,
                timeout,
            )
            fallback["backend"] = "lsprepost"
            fallback["backend_attempts"] = [
                {"backend": "lasso", "ok": False, "message": str(lasso_exc)},
                {"backend": "lsprepost", "ok": fallback.get("ok", False)},
            ]
            return fallback
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["output_csv"] = str(output_csv)
        result["backend"] = backend
        return result


def inspect_binout_contents(
    binout_path: str,
    backend: str = "auto",
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        selected_backend = _validate_backend(backend)
        if selected_backend == "lsprepost":
            raise LsppValidationError(
                "inspect_binout_contents requires the lasso backend; "
                "LS-PrePost/binaski does not expose a stable no-GUI contents API."
            )
        source = _resolve_binout_source(binout_path, cfg)
        binout = _open_lasso_binout(source["lasso_input"])
        top_listing = _read_lasso_path(binout, [])
        blocks = _children_from_listing(top_listing)
        block_details: dict[str, Any] = {}
        for block in blocks:
            listing = _read_lasso_optional(binout, [block])
            variables = _children_from_listing(listing) if _is_child_listing(listing) else []
            variable_details: dict[str, Any] = {}
            for variable in variables:
                data = _read_lasso_optional(binout, [block, variable])
                if data is None or _is_child_listing(data):
                    continue
                meta = _shape_dtype(data)
                if variable == "time":
                    values = _as_float_list(data, f"{block}/time")
                    meta["time_start"] = values[0] if values else None
                    meta["time_end"] = values[-1] if values else None
                    meta["steps"] = len(values)
                variable_details[variable] = meta
            block_details[block] = {
                "variables": variable_details,
                "variable_names": sorted(variable_details.keys()),
            }
        return {
            "ok": True,
            "message": "binout contents inspected with lasso-python backend.",
            "backend": "lasso",
            "binout_source": source["lasso_input"],
            "matched_files": source["matched_files"],
            "mpp_shards": source["mpp_shards"],
            "top_blocks": blocks,
            "blocks": block_details,
            "generated_cfile": "",
            "log_file": "",
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["backend"] = backend
        return result


def extract_binout_metrics(
    binout_path: str,
    block: str,
    variable: str,
    entity_index: int | None = None,
    backend: str = "auto",
    metrics: list[str] | None = None,
    time_window: list[float] | None = None,
    pressure_proxy: bool = False,
    shock_window: list[float] | None = None,
    bubble_window: list[float] | None = None,
    arrival_threshold_fraction: float = 0.05,
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        selected_backend = _validate_backend(backend)
        if selected_backend == "lsprepost":
            raise LsppValidationError(
                "extract_binout_metrics requires the lasso backend; use "
                "extract_binout_curve with backend='lsprepost' for legacy CSV export."
            )
        source = _resolve_binout_source(binout_path, cfg)
        block_name, variable_name = _split_variable_path(block, variable)
        binout = _open_lasso_binout(source["lasso_input"])
        if pressure_proxy or (block_name == "trhist" and variable_name == "p_proxy"):
            curve = _pressure_proxy_curve(binout, entity_index)
            pressure_metrics = _underwater_pressure_metrics(
                curve,
                shock_window,
                bubble_window,
                arrival_threshold_fraction,
            )
        else:
            curve = _curve_from_lasso(binout, block_name, variable_name, entity_index)
            pressure_metrics = {}
        return {
            "ok": True,
            "message": "binout metrics extracted with lasso-python backend.",
            "backend": "lasso",
            "binout_source": source["lasso_input"],
            "matched_files": source["matched_files"],
            "mpp_shards": source["mpp_shards"],
            "block": curve["block"],
            "variable": curve["variable"],
            "columns": curve["headers"],
            "metrics": _curve_metrics(curve, metrics, time_window),
            "pressure_metrics": pressure_metrics,
            "generated_cfile": "",
            "log_file": "",
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["backend"] = backend
        return result
