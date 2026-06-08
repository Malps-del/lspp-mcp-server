"""MCP server entrypoint for LS-PrePost post-processing tools."""

from __future__ import annotations

from typing import Any

from .config import load_config
from .tools.ascii_curves import extract_ascii_curve as _extract_ascii_curve
from .tools.batch import batch_postprocess_cases as _batch_postprocess_cases
from .tools.binout import extract_binout_curve as _extract_binout_curve
from .tools.d3plot import (
    export_d3plot_contour as _export_d3plot_contour,
    extract_d3plot_node_history as _extract_d3plot_node_history,
)
from .validators import LsppValidationError, validate_lsprepost_installation

try:
    from mcp.server.fastmcp import FastMCP  # type: ignore
except ModuleNotFoundError:
    FastMCP = None  # type: ignore[assignment]


def validate_lsprepost(lsprepost_exe: str, workspace_root: str) -> dict[str, Any]:
    return validate_lsprepost_installation(lsprepost_exe, workspace_root)


def list_supported_variables(category: str) -> dict[str, Any]:
    cfg = load_config()
    if category not in {"d3plot_fringe", "nodout", "matsum", "node_history", "binout"}:
        raise LsppValidationError(
            "category must be one of: d3plot_fringe, nodout, matsum, node_history, binout"
        )
    return {"variables": cfg.variable_maps.get(category, {})}


def export_d3plot_contour(
    d3plot_path: str,
    output_png: str,
    variable: str,
    state_index: int,
    view: str,
    part_ids: list[int] | str | int | None = None,
    show_legend: bool = True,
    show_triad: bool = False,
    background: str = "white",
    window_size: str = "1600x1200",
    use_nographics: bool = False,
    range_level: int | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    return _export_d3plot_contour(
        d3plot_path=d3plot_path,
        output_png=output_png,
        variable=variable,
        state_index=state_index,
        view=view,
        part_ids=part_ids,
        show_legend=show_legend,
        show_triad=show_triad,
        background=background,
        window_size=window_size,
        use_nographics=use_nographics,
        range_level=range_level,
        overwrite=overwrite,
        config=load_config(),
    )


def extract_ascii_curve(
    ascii_type: str,
    file_path: str,
    output_csv: str,
    variable: str | None = None,
    variable_code: int | None = None,
    entity_id: str | int | None = None,
    xyplot_window: int = 1,
    overwrite: bool = False,
) -> dict[str, Any]:
    return _extract_ascii_curve(
        ascii_type=ascii_type,
        file_path=file_path,
        output_csv=output_csv,
        variable=variable,
        variable_code=variable_code,
        entity_id=entity_id,
        xyplot_window=xyplot_window,
        overwrite=overwrite,
        config=load_config(),
    )


def extract_d3plot_node_history(
    d3plot_path: str,
    node_id: int,
    output_csv: str,
    variable: str | None = None,
    variable_code: int | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    return _extract_d3plot_node_history(
        d3plot_path=d3plot_path,
        node_id=node_id,
        output_csv=output_csv,
        variable=variable,
        variable_code=variable_code,
        overwrite=overwrite,
        config=load_config(),
    )


def extract_binout_curve(
    binout_path: str,
    block: str,
    variable: str,
    output_csv: str,
    entity_index: int | None = None,
    mpp: bool = False,
    xyplot_window: int = 1,
    overwrite: bool = False,
) -> dict[str, Any]:
    return _extract_binout_curve(
        binout_path=binout_path,
        block=block,
        variable=variable,
        output_csv=output_csv,
        entity_index=entity_index,
        mpp=mpp,
        xyplot_window=xyplot_window,
        overwrite=overwrite,
        config=load_config(),
    )


def batch_postprocess_cases(
    cases_root: str,
    task_config_path: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    return _batch_postprocess_cases(
        cases_root=cases_root,
        task_config_path=task_config_path,
        overwrite=overwrite,
        config=load_config(),
    )


if FastMCP is not None:
    mcp = FastMCP("lspp-mcp-server")
    mcp.tool()(validate_lsprepost)
    mcp.tool()(list_supported_variables)
    mcp.tool()(export_d3plot_contour)
    mcp.tool()(extract_ascii_curve)
    mcp.tool()(extract_d3plot_node_history)
    mcp.tool()(extract_binout_curve)
    mcp.tool()(batch_postprocess_cases)
else:
    mcp = None


def main() -> None:
    if mcp is None:
        raise SystemExit(
            "The MCP Python SDK is not installed. Install this project with its "
            "dependencies, then run: lspp-mcp-server"
        )
    mcp.run()


if __name__ == "__main__":
    main()
