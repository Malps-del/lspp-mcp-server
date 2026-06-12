"""Tools for d3plot image export and node-history extraction."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Sequence

from ..colormaps import (
    COLOR_STYLE_GROUPS,
    builtin_color_styles,
    normalize_style_name,
    palette_lines,
)
from ..config import LsppConfig
from ..validators import (
    LsppValidationError,
    ensure_input_file,
    ensure_within_allowed_roots,
    format_part_ids,
    output_file_check,
    positive_int,
    require_variable_code,
    safe_cfile_string,
    validate_window_size,
)
from ._common import (
    execute_generated_cfile,
    finalize_output_result,
    get_config,
    prepare_output,
    quote_path,
    result_from_validation_error,
)


VALID_VIEWS = {"front", "back", "top", "bottom", "left", "right", "isometric"}
VALID_BACKGROUNDS = {"white": "1 1 1", "black": "0 0 0"}
VALID_IMAGE_FORMATS = {
    "png",
    "jpg",
    "bmp",
    "gif",
    "wrl",
}
IMAGE_FORMAT_ALIASES = {
    "jpeg": "jpg",
    "vrml": "wrl",
    "vrml2": "wrl",
}
PRINT_FORMATS = {
    "png": "png",
    "jpg": "jpg",
    "bmp": "bmp",
    "gif": "gif",
    "wrl": "vrml",
}
STATE_TIME_RE = re.compile(
    r"^\s*(?P<cycle>\d+)\s+t\s+(?P<time>[+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)"
    r".*write\s+d3plot\s+file",
    re.IGNORECASE,
)


def _view_command(view: str) -> str:
    if view not in VALID_VIEWS:
        raise LsppValidationError(
            f"view must be one of: {', '.join(sorted(VALID_VIEWS))}"
        )
    return "isometric x" if view == "isometric" else view


def _part_command(part_ids: Sequence[int] | str | int | None) -> str:
    formatted = format_part_ids(part_ids)
    if not formatted:
        return "pall"
    return f"m {formatted}"


def _range_level_commands(range_level: int | None) -> str:
    if range_level is None:
        return ""
    level = positive_int(range_level, "range_level")
    if level < 1:
        raise LsppValidationError("range_level must be greater than 0")
    return f"range level {level}\nrange pal update"


def _available_color_styles(config: LsppConfig) -> set[str]:
    return {"default", *builtin_color_styles(), *config.color_palettes}


def _normalized_color_style(color_style: str | None, config: LsppConfig) -> str:
    style = normalize_style_name(color_style)
    if style not in _available_color_styles(config):
        raise LsppValidationError(
            "color_style must be one of: "
            + ", ".join(sorted(_available_color_styles(config)))
            + ", or provide color_palette_path"
        )
    return style


def _write_builtin_palette_file(
    style: str,
    output_parent: Path,
    range_level: int | None,
) -> Path:
    palette_dir = output_parent / ".lspp_mcp" / "palettes"
    palette_dir.mkdir(parents=True, exist_ok=True)
    palette_path = palette_dir / f"{style}.txt"
    levels = positive_int(range_level, "range_level") if range_level is not None else 50
    if levels < 2:
        raise LsppValidationError("range_level must be at least 2 when color_style is used")
    palette_path.write_text(
        "\n".join(palette_lines(style, levels)) + "\n",
        encoding="ascii",
        newline="\n",
    )
    return palette_path


def _resolve_color_palette(
    style: str,
    color_palette_path: str | None,
    config: LsppConfig,
    output_parent: Path,
    range_level: int | None,
) -> Path | None:
    if color_palette_path:
        return ensure_input_file(
            color_palette_path,
            config.workspace_root,
            config.resolved_allowed_roots(),
            label="color palette file",
        )
    if style == "default":
        return None
    if style in config.color_palettes:
        return ensure_input_file(
            config.color_palettes[style],
            config.workspace_root,
            config.resolved_allowed_roots(),
            label=f"color palette file for {style}",
        )
    return _write_builtin_palette_file(style, output_parent, range_level)


def _color_style_commands(palette_path: Path | None) -> str:
    if palette_path is None:
        return ""
    return f'range pal load "{quote_path(palette_path)}"\nrange pal update'


def _normalize_image_format(image_format: str) -> str:
    normalized = image_format.lower().strip().lstrip(".")
    normalized = IMAGE_FORMAT_ALIASES.get(normalized, normalized)
    if normalized not in VALID_IMAGE_FORMATS:
        raise LsppValidationError(
            "image_format must be one of: "
            + ", ".join(sorted(VALID_IMAGE_FORMATS))
        )
    return normalized


def _image_format_for_output(output: Path, image_format: str | None) -> str:
    suffix = output.suffix.lower().lstrip(".")
    if image_format:
        normalized = _normalize_image_format(image_format)
        if suffix:
            suffix_format = _normalize_image_format(suffix)
            if suffix_format != normalized:
                raise LsppValidationError(
                    "image_format does not match output file extension: "
                    f"{normalized} vs .{suffix}"
                )
        return normalized
    if suffix:
        return _normalize_image_format(suffix)
    return "png"


def _state_indices(
    state_start: int | None,
    state_end: int | None,
    state_indices: Sequence[int] | None,
) -> list[int]:
    if state_indices is not None:
        indices = [positive_int(value, "state_index") for value in state_indices]
        if not indices:
            raise LsppValidationError("state_indices cannot be empty")
        return indices
    if state_start is None or state_end is None:
        raise LsppValidationError(
            "Either state_indices or both state_start and state_end are required"
        )
    start = positive_int(state_start, "state_start")
    end = positive_int(state_end, "state_end")
    if end < start:
        raise LsppValidationError("state_end must be greater than or equal to state_start")
    return list(range(start, end + 1))


def _state_time_rows_from_logs(case_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in ("d3hsp", "messag"):
        log_path = case_dir / name
        if not log_path.exists() or not log_path.is_file():
            continue
        for line_number, line in enumerate(
            log_path.read_text(encoding="utf-8", errors="replace").splitlines(),
            start=1,
        ):
            match = STATE_TIME_RE.search(line)
            if not match:
                continue
            rows.append(
                {
                    "state_index": len(rows) + 1,
                    "time": float(match.group("time")),
                    "cycle": int(match.group("cycle")),
                    "source_file": str(log_path),
                    "line": line_number,
                }
            )
        if rows:
            break
    return rows


def _state_indices_from_times(
    d3plot: Path,
    state_times: Sequence[float] | None,
    time_tolerance: float | None,
) -> tuple[list[int] | None, list[dict[str, Any]]]:
    if state_times is None:
        return None, []
    rows = _state_time_rows_from_logs(d3plot.parent)
    if not rows:
        raise LsppValidationError(
            "Could not infer d3plot state times from d3hsp or messag logs"
        )
    tolerance = None if time_tolerance is None else float(time_tolerance)
    selected: list[int] = []
    mapping: list[dict[str, Any]] = []
    for requested in state_times:
        requested_time = float(requested)
        nearest = min(rows, key=lambda row: abs(float(row["time"]) - requested_time))
        delta = abs(float(nearest["time"]) - requested_time)
        if tolerance is not None and delta > tolerance:
            raise LsppValidationError(
                f"No d3plot state within tolerance for time {requested_time}; "
                f"nearest state {nearest['state_index']} at time {nearest['time']}"
            )
        selected.append(int(nearest["state_index"]))
        mapping.append(
            {
                "requested_time": requested_time,
                "state_index": int(nearest["state_index"]),
                "state_time": float(nearest["time"]),
                "delta": delta,
                "cycle": nearest["cycle"],
            }
        )
    return selected, mapping


def _format_frame_filename(
    filename_template: str,
    variable: str,
    state: int,
    index: int,
    image_format: str,
    view: str,
) -> str:
    try:
        filename = filename_template.format(
            variable=variable,
            state=state,
            index=index,
            format=image_format,
            ext=image_format,
            view=view,
        )
    except (KeyError, ValueError) as exc:
        raise LsppValidationError(
            "filename_template may only use {variable}, {state}, {index}, "
            "{format}, {ext}, and {view}"
        ) from exc
    if not filename or filename in {".", ".."}:
        raise LsppValidationError("filename_template produced an empty filename")
    if any(separator in filename for separator in ("/", "\\")):
        raise LsppValidationError(
            "filename_template must produce filenames only; use output_dir for folders"
        )
    return filename


def _frame_output_paths(
    output_dir: Path,
    filename_template: str,
    variable: str,
    states: Sequence[int],
    views: Sequence[str],
    image_format: str | None,
) -> tuple[list[Path], str, list[dict[str, Any]]]:
    if image_format:
        resolved_format = _normalize_image_format(image_format)
    elif "{format" in filename_template or "{ext" in filename_template:
        resolved_format = "png"
    else:
        first_name = _format_frame_filename(
            filename_template, variable, states[0], 1, "png", views[0]
        )
        resolved_format = _image_format_for_output(output_dir / first_name, None)

    paths: list[Path] = []
    specs: list[dict[str, Any]] = []
    seen: set[str] = set()
    frame_index = 1
    for state in states:
        for view_name in views:
            filename = _format_frame_filename(
                filename_template, variable, state, frame_index, resolved_format, view_name
            )
            output = output_dir / filename
            _image_format_for_output(output, resolved_format)
            key = str(output).lower()
            if key in seen:
                raise LsppValidationError(
                    f"filename_template produced duplicate output: {output}"
                )
            seen.add(key)
            paths.append(output)
            specs.append({"state": state, "view": view_name, "output": output})
            frame_index += 1
    return paths, resolved_format, specs


def _frame_print_commands(
    frame_specs: Sequence[dict[str, Any]],
    print_format: str,
) -> str:
    lines: list[str] = []
    for spec in frame_specs:
        lines.append(f"state {spec['state']}")
        lines.append(_view_command(str(spec["view"])))
        lines.append("ac")
        lines.append(
            f'print {print_format} "{quote_path(spec["output"])}" opaque enlisted "OGL1x1"'
        )
    return "\n".join(lines)


def list_contour_color_styles(config: LsppConfig | None = None) -> dict[str, Any]:
    cfg = get_config(config)
    return {
        "ok": True,
        "styles": sorted(_available_color_styles(cfg)),
        "built_in_styles": sorted({"default", *builtin_color_styles()}),
        "style_groups": {key: list(value) for key, value in COLOR_STYLE_GROUPS.items()},
        "configured_styles": sorted(cfg.color_palettes),
        "custom_palette_path_supported": True,
        "message": "Supported contour color styles returned.",
    }


def infer_d3plot_state_times(
    d3plot_path: str,
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        d3plot = ensure_input_file(
            d3plot_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="d3plot file",
        )
        rows = _state_time_rows_from_logs(d3plot.parent)
        return {
            "ok": bool(rows),
            "message": "D3plot state times inferred."
            if rows
            else "No d3plot state write times found in d3hsp or messag.",
            "d3plot_path": str(d3plot),
            "states": rows,
            "state_count": len(rows),
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["d3plot_path"] = str(d3plot_path)
        return result


def export_d3plot_contour(
    d3plot_path: str,
    output_png: str,
    variable: str,
    state_index: int,
    view: str,
    part_ids: Sequence[int] | str | int | None = None,
    show_legend: bool = True,
    show_triad: bool = False,
    background: str = "white",
    window_size: str = "1600x1200",
    use_nographics: bool = False,
    range_level: int | None = None,
    color_style: str | None = None,
    color_palette_path: str | None = None,
    image_format: str | None = None,
    overwrite: bool = False,
    config: LsppConfig | None = None,
    timeout: int | None = None,
    title: str = "",
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        d3plot = ensure_input_file(
            d3plot_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="d3plot file",
        )
        output = prepare_output(output_png, cfg, overwrite)
        resolved_image_format = _image_format_for_output(output, image_format)
        style = (
            "custom"
            if color_palette_path and not color_style
            else _normalized_color_style(color_style, cfg)
        )
        palette_path = _resolve_color_palette(
            style, color_palette_path, cfg, output.parent, range_level
        )
        fringe_code = require_variable_code(cfg.variable_maps, "d3plot_fringe", variable)
        if background not in VALID_BACKGROUNDS:
            raise LsppValidationError("background must be white or black")
        context = {
            "open_command": "openc"
            if cfg.open_d3plot_command == "openc"
            else "open",
            "d3plot_path": quote_path(d3plot),
            "fringe_code": fringe_code,
            "state_index": positive_int(state_index, "state_index"),
            "view_command": _view_command(view),
            "part_command": _part_command(part_ids),
            "show_legend": 1 if show_legend else 0,
            "show_triad": 1 if show_triad else 0,
            "background_rgb": VALID_BACKGROUNDS[background],
            "title_command": f'title "{safe_cfile_string(title)}"' if title else "title 0",
            "range_level_commands": _range_level_commands(range_level),
            "color_style_commands": _color_style_commands(palette_path),
            "image_format": resolved_image_format,
            "print_format": PRINT_FORMATS[resolved_image_format],
            "output_image": quote_path(output),
        }
        cfile_path, log_file, run_result, output_check = execute_generated_cfile(
            output_path=output,
            tool_name="export_d3plot_contour",
            template_name="export_d3plot_contour.cfile.j2",
            context=context,
            mode="image",
            window_size=validate_window_size(window_size),
            use_nographics=use_nographics,
            config=cfg,
            timeout=timeout,
        )
        result = finalize_output_result(
            "output_png", output, cfile_path, log_file, run_result, output_check
        )
        result["output_image"] = result["output_png"]
        result["image_format"] = resolved_image_format
        result["color_style"] = style
        result["palette_file"] = str(palette_path) if palette_path else ""
        return result
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["output_png"] = str(output_png)
        result["output_image"] = str(output_png)
        if image_format:
            result["image_format"] = image_format
        return result


def export_d3plot_contour_frames(
    d3plot_path: str,
    output_dir: str,
    variable: str,
    view: str,
    state_start: int | None = None,
    state_end: int | None = None,
    state_indices: Sequence[int] | None = None,
    state_times: Sequence[float] | None = None,
    time_tolerance: float | None = None,
    filename_template: str = "{variable}_state_{state:03d}.{format}",
    views: Sequence[str] | None = None,
    part_ids: Sequence[int] | str | int | None = None,
    show_legend: bool = True,
    show_triad: bool = False,
    background: str = "white",
    window_size: str = "1600x1200",
    use_nographics: bool = False,
    range_level: int | None = None,
    color_style: str | None = None,
    color_palette_path: str | None = None,
    image_format: str | None = None,
    overwrite: bool = False,
    config: LsppConfig | None = None,
    timeout: int | None = None,
    title: str = "",
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        d3plot = ensure_input_file(
            d3plot_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="d3plot file",
        )
        mapped_states, state_time_map = _state_indices_from_times(
            d3plot, state_times, time_tolerance
        )
        states = mapped_states or _state_indices(state_start, state_end, state_indices)
        view_names = list(views) if views is not None else [view]
        if not view_names:
            raise LsppValidationError("views cannot be empty")
        for item in view_names:
            _view_command(item)
        resolved_template = filename_template
        if views is not None and len(view_names) > 1 and filename_template == "{variable}_state_{state:03d}.{format}":
            resolved_template = "{variable}_{view}_state_{state:03d}.{format}"
        output_root = ensure_within_allowed_roots(
            output_dir, cfg.workspace_root, cfg.resolved_allowed_roots()
        )
        outputs, resolved_image_format, frame_specs = _frame_output_paths(
            output_root, resolved_template, variable, states, view_names, image_format
        )
        for output in outputs:
            prepare_output(output, cfg, overwrite)
        style = (
            "custom"
            if color_palette_path and not color_style
            else _normalized_color_style(color_style, cfg)
        )
        palette_path = _resolve_color_palette(
            style, color_palette_path, cfg, output_root, range_level
        )
        fringe_code = require_variable_code(cfg.variable_maps, "d3plot_fringe", variable)
        if background not in VALID_BACKGROUNDS:
            raise LsppValidationError("background must be white or black")
        context = {
            "open_command": "openc"
            if cfg.open_d3plot_command == "openc"
            else "open",
            "d3plot_path": quote_path(d3plot),
            "fringe_code": fringe_code,
            "view_command": _view_command(view),
            "part_command": _part_command(part_ids),
            "show_legend": 1 if show_legend else 0,
            "show_triad": 1 if show_triad else 0,
            "background_rgb": VALID_BACKGROUNDS[background],
            "title_command": f'title "{safe_cfile_string(title)}"' if title else "title 0",
            "range_level_commands": _range_level_commands(range_level),
            "color_style_commands": _color_style_commands(palette_path),
            "image_format": resolved_image_format,
            "print_format": PRINT_FORMATS[resolved_image_format],
            "frame_print_commands": _frame_print_commands(
                frame_specs, PRINT_FORMATS[resolved_image_format]
            ),
        }
        cfile_path, log_file, run_result, _output_check = execute_generated_cfile(
            output_path=outputs[0],
            tool_name="export_d3plot_contour_frames",
            template_name="export_d3plot_contour_frames.cfile.j2",
            context=context,
            mode="image",
            window_size=validate_window_size(window_size),
            use_nographics=use_nographics,
            config=cfg,
            timeout=timeout,
        )
        output_checks = [output_file_check(output) for output in outputs]
        generated_count = sum(1 for item in output_checks if item["nonempty"])
        ok = bool(run_result.ok and generated_count == len(outputs))
        if ok:
            message = "All frame images generated successfully."
        else:
            message = (
                f"Generated {generated_count} of {len(outputs)} requested frame images."
            )
            if run_result.message and not run_result.ok:
                message = f"{message} {run_result.message}"
        return {
            "ok": ok,
            "message": message,
            "output_dir": str(output_root),
            "output_images": [str(output) for output in outputs],
            "image_format": resolved_image_format,
            "color_style": style,
            "palette_file": str(palette_path) if palette_path else "",
            "state_indices": states,
            "state_time_map": state_time_map,
            "views": view_names,
            "generated_count": generated_count,
            "requested_count": len(outputs),
            "checks": output_checks,
            "generated_cfile": str(cfile_path),
            "log_file": str(log_file),
            "returncode": run_result.returncode,
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["output_dir"] = str(output_dir)
        result["output_images"] = []
        if image_format:
            result["image_format"] = image_format
        return result


def extract_d3plot_node_history(
    d3plot_path: str,
    node_id: int,
    output_csv: str,
    variable: str | None = None,
    variable_code: int | None = None,
    xyplot_window: int = 1,
    overwrite: bool = False,
    config: LsppConfig | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        d3plot = ensure_input_file(
            d3plot_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="d3plot file",
        )
        output = prepare_output(output_csv, cfg, overwrite)
        code = require_variable_code(
            cfg.variable_maps, "node_history", variable, variable_code
        )
        context = {
            "open_command": "openc"
            if cfg.open_d3plot_command == "openc"
            else "open",
            "d3plot_path": quote_path(d3plot),
            "node_id": positive_int(node_id, "node_id"),
            "variable_code": code,
            "xyplot_window": positive_int(xyplot_window, "xyplot_window"),
            "output_csv": quote_path(output),
        }
        cfile_path, log_file, run_result, output_check = execute_generated_cfile(
            output_path=output,
            tool_name="extract_d3plot_node_history",
            template_name="extract_d3plot_node_history.cfile.j2",
            context=context,
            mode="curve",
            window_size=None,
            use_nographics=True,
            config=cfg,
            timeout=timeout,
        )
        return finalize_output_result(
            "output_csv", output, cfile_path, log_file, run_result, output_check
        )
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["output_csv"] = str(output_csv)
        return result
