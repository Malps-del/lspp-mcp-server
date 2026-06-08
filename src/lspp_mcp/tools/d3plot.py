"""Tools for d3plot image export and node-history extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from ..config import LsppConfig
from ..validators import (
    LsppValidationError,
    ensure_input_file,
    format_part_ids,
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
            "output_png": quote_path(output),
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
        return finalize_output_result(
            "output_png", output, cfile_path, log_file, run_result, output_check
        )
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["output_png"] = str(output_png)
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
