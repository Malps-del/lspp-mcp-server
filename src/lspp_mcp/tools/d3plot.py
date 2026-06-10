"""Tools for d3plot image export and node-history extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

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


def _format_frame_filename(
    filename_template: str,
    variable: str,
    state: int,
    index: int,
    image_format: str,
) -> str:
    try:
        filename = filename_template.format(
            variable=variable,
            state=state,
            index=index,
            format=image_format,
            ext=image_format,
        )
    except (KeyError, ValueError) as exc:
        raise LsppValidationError(
            "filename_template may only use {variable}, {state}, {index}, "
            "{format}, and {ext}"
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
    image_format: str | None,
) -> tuple[list[Path], str]:
    if image_format:
        resolved_format = _normalize_image_format(image_format)
    elif "{format" in filename_template or "{ext" in filename_template:
        resolved_format = "png"
    else:
        first_name = _format_frame_filename(
            filename_template, variable, states[0], 1, "png"
        )
        resolved_format = _image_format_for_output(output_dir / first_name, None)

    paths: list[Path] = []
    seen: set[str] = set()
    for index, state in enumerate(states, start=1):
        filename = _format_frame_filename(
            filename_template, variable, state, index, resolved_format
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
    return paths, resolved_format


def _frame_print_commands(
    states: Sequence[int],
    outputs: Sequence[Path],
    print_format: str,
) -> str:
    lines: list[str] = []
    for state, output in zip(states, outputs):
        lines.append(f"state {state}")
        lines.append("ac")
        lines.append(
            f'print {print_format} "{quote_path(output)}" opaque enlisted "OGL1x1"'
        )
    return "\n".join(lines)


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
    filename_template: str = "{variable}_state_{state:03d}.{format}",
    part_ids: Sequence[int] | str | int | None = None,
    show_legend: bool = True,
    show_triad: bool = False,
    background: str = "white",
    window_size: str = "1600x1200",
    use_nographics: bool = False,
    range_level: int | None = None,
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
        states = _state_indices(state_start, state_end, state_indices)
        output_root = ensure_within_allowed_roots(
            output_dir, cfg.workspace_root, cfg.resolved_allowed_roots()
        )
        outputs, resolved_image_format = _frame_output_paths(
            output_root, filename_template, variable, states, image_format
        )
        for output in outputs:
            prepare_output(output, cfg, overwrite)
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
            "image_format": resolved_image_format,
            "print_format": PRINT_FORMATS[resolved_image_format],
            "frame_print_commands": _frame_print_commands(
                states, outputs, PRINT_FORMATS[resolved_image_format]
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
            "state_indices": states,
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
