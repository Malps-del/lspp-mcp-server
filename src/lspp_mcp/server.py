"""MCP server entrypoint for LS-PrePost post-processing tools."""

from __future__ import annotations

from typing import Any

from .config import load_config
from .tools.ascii_curves import extract_ascii_curve as _extract_ascii_curve
from .tools.batch import batch_postprocess_cases as _batch_postprocess_cases
from .tools.binout import extract_binout_curve as _extract_binout_curve
from .tools.casegen import (
    generate_lsdyna_cases as _generate_lsdyna_cases,
    inspect_lsdyna_case_config as _inspect_lsdyna_case_config,
    validate_case_generator_integration as _validate_case_generator_integration,
)
from .tools.d3plot import (
    export_d3plot_contour as _export_d3plot_contour,
    export_d3plot_contour_frames as _export_d3plot_contour_frames,
    extract_d3plot_node_history as _extract_d3plot_node_history,
)
from .tools.keyword import (
    check_keyword_deck as _check_keyword_deck,
    inspect_keyword_deck as _inspect_keyword_deck,
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
    image_format: str | None = None,
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
        image_format=image_format,
        overwrite=overwrite,
        config=load_config(),
    )


def export_d3plot_contour_frames(
    d3plot_path: str,
    output_dir: str,
    variable: str,
    view: str,
    state_start: int | None = None,
    state_end: int | None = None,
    state_indices: list[int] | None = None,
    filename_template: str = "{variable}_state_{state:03d}.{format}",
    part_ids: list[int] | str | int | None = None,
    show_legend: bool = True,
    show_triad: bool = False,
    background: str = "white",
    window_size: str = "1600x1200",
    use_nographics: bool = False,
    range_level: int | None = None,
    image_format: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    return _export_d3plot_contour_frames(
        d3plot_path=d3plot_path,
        output_dir=output_dir,
        variable=variable,
        view=view,
        state_start=state_start,
        state_end=state_end,
        state_indices=state_indices,
        filename_template=filename_template,
        part_ids=part_ids,
        show_legend=show_legend,
        show_triad=show_triad,
        background=background,
        window_size=window_size,
        use_nographics=use_nographics,
        range_level=range_level,
        image_format=image_format,
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


def validate_case_generator_integration() -> dict[str, Any]:
    return _validate_case_generator_integration(config=load_config())


def inspect_lsdyna_case_config(project_config_path: str) -> dict[str, Any]:
    return _inspect_lsdyna_case_config(
        project_config_path=project_config_path,
        config=load_config(),
    )


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
) -> dict[str, Any]:
    return _generate_lsdyna_cases(
        project_config_path=project_config_path,
        output_dir=output_dir,
        method=method,
        sample_count=sample_count,
        random_seed=random_seed,
        avoid_duplicates=avoid_duplicates,
        integer_rounding=integer_rounding,
        excel_path=excel_path,
        output_mode=output_mode,
        folder_template=folder_template,
        file_template=file_template,
        include_index_csv=include_index_csv,
        include_index_excel=include_index_excel,
        copy_support_files=copy_support_files,
        preview_only=preview_only,
        preview_limit=preview_limit,
        overwrite=overwrite,
        config=load_config(),
    )


def inspect_keyword_deck(
    k_path: str,
    extra_k_paths: list[str] | None = None,
    include_includes: bool = True,
    max_depth: int = 4,
) -> dict[str, Any]:
    return _inspect_keyword_deck(
        k_path=k_path,
        extra_k_paths=extra_k_paths,
        include_includes=include_includes,
        max_depth=max_depth,
        config=load_config(),
    )


def check_keyword_deck(
    k_path: str,
    extra_k_paths: list[str] | None = None,
    include_includes: bool = True,
    max_depth: int = 4,
) -> dict[str, Any]:
    return _check_keyword_deck(
        k_path=k_path,
        extra_k_paths=extra_k_paths,
        include_includes=include_includes,
        max_depth=max_depth,
        config=load_config(),
    )


if FastMCP is not None:
    mcp = FastMCP("lspp-mcp-server")
    mcp.tool()(validate_lsprepost)
    mcp.tool()(list_supported_variables)
    mcp.tool()(export_d3plot_contour)
    mcp.tool()(export_d3plot_contour_frames)
    mcp.tool()(extract_ascii_curve)
    mcp.tool()(extract_d3plot_node_history)
    mcp.tool()(extract_binout_curve)
    mcp.tool()(batch_postprocess_cases)
    mcp.tool()(validate_case_generator_integration)
    mcp.tool()(inspect_lsdyna_case_config)
    mcp.tool()(generate_lsdyna_cases)
    mcp.tool()(inspect_keyword_deck)
    mcp.tool()(check_keyword_deck)
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
