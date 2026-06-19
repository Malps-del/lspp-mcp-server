"""MCP server entrypoint for LS-PrePost post-processing tools."""

from __future__ import annotations

from typing import Any

from .config import load_config
from .tools.ascii_curves import extract_ascii_curve as _extract_ascii_curve
from .tools.ale import (
    append_initial_volume_fraction_geometry as _append_initial_volume_fraction_geometry,
    create_initial_volume_fraction_geometry as _create_initial_volume_fraction_geometry,
    inspect_initial_volume_fraction_geometry as _inspect_initial_volume_fraction_geometry,
)
from .tools.assembly import (
    check_lsdyna_cylindrical_assembly as _check_lsdyna_cylindrical_assembly,
    create_lsdyna_cylindrical_assembly as _create_lsdyna_cylindrical_assembly,
)
from .tools.batch import batch_postprocess_cases as _batch_postprocess_cases
from .tools.binout import extract_binout_curve as _extract_binout_curve
from .tools.casegen import (
    generate_lsdyna_cases as _generate_lsdyna_cases,
    generate_lsdyna_keyword_field_sweep as _generate_lsdyna_keyword_field_sweep,
    generate_lsdyna_parameter_sweep as _generate_lsdyna_parameter_sweep,
    inspect_lsdyna_case_config as _inspect_lsdyna_case_config,
    validate_case_generator_integration as _validate_case_generator_integration,
)
from .tools.d3plot import (
    export_d3plot_contour as _export_d3plot_contour,
    export_d3plot_contour_frames as _export_d3plot_contour_frames,
    extract_d3plot_node_history as _extract_d3plot_node_history,
    infer_d3plot_state_times as _infer_d3plot_state_times,
    list_contour_color_styles as _list_contour_color_styles,
)
from .tools.keyword import (
    check_keyword_deck as _check_keyword_deck,
    inspect_keyword_deck as _inspect_keyword_deck,
    inspect_keyword_fields as _inspect_keyword_fields,
)
from .tools.preprocess import (
    create_lsdyna_block_mesh as _create_lsdyna_block_mesh,
    create_lsdyna_cylinder_shell_mesh as _create_lsdyna_cylinder_shell_mesh,
    create_lsdyna_plate_mesh as _create_lsdyna_plate_mesh,
    precheck_lsdyna_keyword_model as _precheck_lsdyna_keyword_model,
    preview_lsdyna_keyword_model as _preview_lsdyna_keyword_model,
)
from .tools.solver import (
    diagnose_lsdyna_logs as _diagnose_lsdyna_logs,
    run_lsdyna_solver as _run_lsdyna_solver,
    validate_lsdyna_solver as _validate_lsdyna_solver,
)
from .tools.results import (
    compare_lsdyna_cases as _compare_lsdyna_cases,
    extract_lsdyna_metrics as _extract_lsdyna_metrics,
    inspect_lsdyna_results as _inspect_lsdyna_results,
)
from .tools.sale import (
    check_lsdyna_sale_fluid_domain as _check_lsdyna_sale_fluid_domain,
    create_lsdyna_sale_fluid_domain as _create_lsdyna_sale_fluid_domain,
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
    color_style: str | None = None,
    color_palette_path: str | None = None,
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
        color_style=color_style,
        color_palette_path=color_palette_path,
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
    state_times: list[float] | None = None,
    time_tolerance: float | None = None,
    filename_template: str = "{variable}_state_{state:03d}.{format}",
    views: list[str] | None = None,
    part_ids: list[int] | str | int | None = None,
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
) -> dict[str, Any]:
    return _export_d3plot_contour_frames(
        d3plot_path=d3plot_path,
        output_dir=output_dir,
        variable=variable,
        view=view,
        state_start=state_start,
        state_end=state_end,
        state_indices=state_indices,
        state_times=state_times,
        time_tolerance=time_tolerance,
        filename_template=filename_template,
        views=views,
        part_ids=part_ids,
        show_legend=show_legend,
        show_triad=show_triad,
        background=background,
        window_size=window_size,
        use_nographics=use_nographics,
        range_level=range_level,
        color_style=color_style,
        color_palette_path=color_palette_path,
        image_format=image_format,
        overwrite=overwrite,
        config=load_config(),
    )


def list_contour_color_styles() -> dict[str, Any]:
    return _list_contour_color_styles(config=load_config())


def infer_d3plot_state_times(d3plot_path: str) -> dict[str, Any]:
    return _infer_d3plot_state_times(
        d3plot_path=d3plot_path,
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
) -> dict[str, Any]:
    return _generate_lsdyna_parameter_sweep(
        k_path=k_path,
        parameter_name=parameter_name,
        output_dir=output_dir,
        values=values,
        start=start,
        end=end,
        step=step,
        data_type=data_type,
        output_mode=output_mode,
        folder_template=folder_template,
        file_template=file_template,
        include_index_csv=include_index_csv,
        include_index_excel=include_index_excel,
        copy_include_files=copy_include_files,
        copy_support_files=copy_support_files,
        preview_only=preview_only,
        preview_limit=preview_limit,
        overwrite=overwrite,
        config=load_config(),
    )


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
) -> dict[str, Any]:
    return _generate_lsdyna_keyword_field_sweep(
        k_path=k_path,
        output_dir=output_dir,
        values=values,
        start=start,
        end=end,
        step=step,
        alias=alias,
        keyword=keyword,
        keyword_instance=keyword_instance,
        line_number_in_block=line_number_in_block,
        file_line_number=file_line_number,
        field_number=field_number,
        field_name=field_name,
        current_value=current_value,
        data_type=data_type,
        output_mode=output_mode,
        folder_template=folder_template,
        file_template=file_template,
        include_index_csv=include_index_csv,
        include_index_excel=include_index_excel,
        copy_include_files=copy_include_files,
        copy_support_files=copy_support_files,
        preview_only=preview_only,
        preview_limit=preview_limit,
        overwrite=overwrite,
        config=load_config(),
    )


def validate_lsdyna_solver(
    solver_exe: str | None = None,
    work_dir: str | None = None,
) -> dict[str, Any]:
    return _validate_lsdyna_solver(
        solver_exe=solver_exe,
        work_dir=work_dir,
        config=load_config(),
    )


def run_lsdyna_solver(
    k_path: str,
    work_dir: str | None = None,
    ncpu: int | None = None,
    memory: str | None = None,
    additional_args: list[str] | None = None,
    dry_run: bool = False,
    show_console: bool = False,
    solver_exe: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    return _run_lsdyna_solver(
        k_path=k_path,
        work_dir=work_dir,
        ncpu=ncpu,
        memory=memory,
        additional_args=additional_args,
        dry_run=dry_run,
        show_console=show_console,
        solver_exe=solver_exe,
        timeout=timeout,
        config=load_config(),
    )


def diagnose_lsdyna_logs(
    case_dir: str | None = None,
    d3hsp_path: str | None = None,
    messag_path: str | None = None,
    status_path: str | None = None,
    max_findings: int = 50,
) -> dict[str, Any]:
    return _diagnose_lsdyna_logs(
        case_dir=case_dir,
        d3hsp_path=d3hsp_path,
        messag_path=messag_path,
        status_path=status_path,
        max_findings=max_findings,
        config=load_config(),
    )


def inspect_lsdyna_results(case_dir: str) -> dict[str, Any]:
    return _inspect_lsdyna_results(
        case_dir=case_dir,
        config=load_config(),
    )


def extract_lsdyna_metrics(
    curve_csv: str,
    output_json: str | None = None,
    x_column: str | int | None = None,
    y_columns: list[str | int] | None = None,
    time_window: list[float] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    return _extract_lsdyna_metrics(
        curve_csv=curve_csv,
        output_json=output_json,
        x_column=x_column,
        y_columns=y_columns,
        time_window=time_window,
        overwrite=overwrite,
        config=load_config(),
    )


def compare_lsdyna_cases(
    cases_root: str,
    output_csv: str,
    metric_specs: list[dict[str, Any]],
    case_glob: str = "*",
    overwrite: bool = False,
) -> dict[str, Any]:
    return _compare_lsdyna_cases(
        cases_root=cases_root,
        output_csv=output_csv,
        metric_specs=metric_specs,
        case_glob=case_glob,
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


def inspect_keyword_fields(
    k_path: str,
    extra_k_paths: list[str] | None = None,
    include_includes: bool = True,
    max_depth: int = 4,
    keyword_filter: list[str] | None = None,
    include_unknown: bool = False,
    max_blocks: int = 200,
) -> dict[str, Any]:
    return _inspect_keyword_fields(
        k_path=k_path,
        extra_k_paths=extra_k_paths,
        include_includes=include_includes,
        max_depth=max_depth,
        keyword_filter=keyword_filter,
        include_unknown=include_unknown,
        max_blocks=max_blocks,
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


def create_lsdyna_plate_mesh(
    output_k: str,
    length: float,
    width: float,
    thickness: float,
    elem_size: float | None = None,
    nx: int | None = None,
    ny: int | None = None,
    part_id: int = 1,
    section_id: int = 1,
    material_id: int = 1,
    density: float = 7.85e-9,
    young: float = 210000.0,
    poisson: float = 0.3,
    title: str = "generated_shell_plate",
    fixed_edges: bool = False,
    boundary_set_id: int = 1001,
    termination_time: float = 1.0,
    database_dt: float = 0.01,
    overwrite: bool = False,
    precheck_json: str | None = None,
) -> dict[str, Any]:
    return _create_lsdyna_plate_mesh(
        output_k=output_k,
        length=length,
        width=width,
        thickness=thickness,
        elem_size=elem_size,
        nx=nx,
        ny=ny,
        part_id=part_id,
        section_id=section_id,
        material_id=material_id,
        density=density,
        young=young,
        poisson=poisson,
        title=title,
        fixed_edges=fixed_edges,
        boundary_set_id=boundary_set_id,
        termination_time=termination_time,
        database_dt=database_dt,
        overwrite=overwrite,
        precheck_json=precheck_json,
        config=load_config(),
    )


def create_lsdyna_block_mesh(
    output_k: str,
    length: float,
    width: float,
    height: float,
    elem_size: float | None = None,
    nx: int | None = None,
    ny: int | None = None,
    nz: int | None = None,
    part_id: int = 1,
    section_id: int = 1,
    material_id: int = 1,
    density: float = 7.85e-9,
    young: float = 210000.0,
    poisson: float = 0.3,
    title: str = "generated_solid_block",
    termination_time: float = 1.0,
    database_dt: float = 0.01,
    overwrite: bool = False,
    precheck_json: str | None = None,
) -> dict[str, Any]:
    return _create_lsdyna_block_mesh(
        output_k=output_k,
        length=length,
        width=width,
        height=height,
        elem_size=elem_size,
        nx=nx,
        ny=ny,
        nz=nz,
        part_id=part_id,
        section_id=section_id,
        material_id=material_id,
        density=density,
        young=young,
        poisson=poisson,
        title=title,
        termination_time=termination_time,
        database_dt=database_dt,
        overwrite=overwrite,
        precheck_json=precheck_json,
        config=load_config(),
    )


def create_lsdyna_cylinder_shell_mesh(
    output_k: str,
    radius: float,
    height: float,
    thickness: float,
    elem_size: float | None = None,
    n_circumference: int | None = None,
    nz: int | None = None,
    part_id: int = 1,
    section_id: int = 1,
    material_id: int = 1,
    density: float = 7.85e-9,
    young: float = 210000.0,
    poisson: float = 0.3,
    title: str = "generated_cylinder_shell",
    cap_bottom: bool = False,
    cap_top: bool = False,
    cap_mesh: str = "quad",
    cap_radial_layers: int = 2,
    cap_core_fraction: float = 0.5,
    fixed_bottom: bool = False,
    fixed_top: bool = False,
    bottom_set_id: int = 1001,
    top_set_id: int = 1002,
    termination_time: float = 1.0,
    database_dt: float = 0.01,
    overwrite: bool = False,
    precheck_json: str | None = None,
) -> dict[str, Any]:
    return _create_lsdyna_cylinder_shell_mesh(
        output_k=output_k,
        radius=radius,
        height=height,
        thickness=thickness,
        elem_size=elem_size,
        n_circumference=n_circumference,
        nz=nz,
        part_id=part_id,
        section_id=section_id,
        material_id=material_id,
        density=density,
        young=young,
        poisson=poisson,
        title=title,
        cap_bottom=cap_bottom,
        cap_top=cap_top,
        cap_mesh=cap_mesh,
        cap_radial_layers=cap_radial_layers,
        cap_core_fraction=cap_core_fraction,
        fixed_bottom=fixed_bottom,
        fixed_top=fixed_top,
        bottom_set_id=bottom_set_id,
        top_set_id=top_set_id,
        termination_time=termination_time,
        database_dt=database_dt,
        overwrite=overwrite,
        precheck_json=precheck_json,
        config=load_config(),
    )


def precheck_lsdyna_keyword_model(
    k_path: str,
    output_json: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    return _precheck_lsdyna_keyword_model(
        k_path=k_path,
        output_json=output_json,
        overwrite=overwrite,
        config=load_config(),
    )


def preview_lsdyna_keyword_model(
    k_path: str,
    output_image: str,
    view: str = "isometric",
    show_mesh: bool = True,
    show_triad: bool = True,
    background: str = "white",
    window_size: str = "1600x1200",
    use_nographics: bool = False,
    image_format: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    return _preview_lsdyna_keyword_model(
        k_path=k_path,
        output_image=output_image,
        view=view,
        show_mesh=show_mesh,
        show_triad=show_triad,
        background=background,
        window_size=window_size,
        use_nographics=use_nographics,
        image_format=image_format,
        overwrite=overwrite,
        config=load_config(),
    )


def create_initial_volume_fraction_geometry(
    output_k: str,
    fmsid: int,
    bammg: int | str,
    fills: list[dict[str, Any]],
    fmidtyp: int = 1,
    ntrace: int = 3,
    comments: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    return _create_initial_volume_fraction_geometry(
        output_k=output_k,
        fmsid=fmsid,
        fmidtyp=fmidtyp,
        bammg=bammg,
        ntrace=ntrace,
        fills=fills,
        comments=comments,
        overwrite=overwrite,
        config=load_config(),
    )


def append_initial_volume_fraction_geometry(
    k_path: str,
    output_k: str,
    fmsid: int,
    bammg: int | str,
    fills: list[dict[str, Any]],
    fmidtyp: int = 1,
    ntrace: int = 3,
    comments: bool = True,
    insert_before_end: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    return _append_initial_volume_fraction_geometry(
        k_path=k_path,
        output_k=output_k,
        fmsid=fmsid,
        fmidtyp=fmidtyp,
        bammg=bammg,
        ntrace=ntrace,
        fills=fills,
        comments=comments,
        insert_before_end=insert_before_end,
        overwrite=overwrite,
        config=load_config(),
    )


def inspect_initial_volume_fraction_geometry(k_path: str) -> dict[str, Any]:
    return _inspect_initial_volume_fraction_geometry(
        k_path=k_path,
        config=load_config(),
    )


def create_lsdyna_cylindrical_assembly(
    output_k: str,
    radius: float,
    height: float,
    thickness: float,
    elem_size: float | None = None,
    n_circumference: int | None = None,
    nz: int | None = None,
    cap_bottom: bool = True,
    cap_top: bool = True,
    cap_mesh: str = "quad",
    cap_radial_layers: int = 2,
    cap_core_fraction: float = 0.5,
    shell_part_id: int = 1,
    shell_section_id: int = 1,
    shell_material_id: int = 1,
    shell_density: float = 7.85e-9,
    shell_young: float = 210000.0,
    shell_poisson: float = 0.3,
    attached_blocks: list[dict[str, Any]] | None = None,
    mass_points: list[dict[str, Any]] | None = None,
    internal_fill: dict[str, Any] | None = None,
    title: str = "generated_cylindrical_assembly",
    termination_time: float = 1.0,
    database_dt: float = 0.01,
    overwrite: bool = False,
    check_json: str | None = None,
) -> dict[str, Any]:
    return _create_lsdyna_cylindrical_assembly(
        output_k=output_k,
        radius=radius,
        height=height,
        thickness=thickness,
        elem_size=elem_size,
        n_circumference=n_circumference,
        nz=nz,
        cap_bottom=cap_bottom,
        cap_top=cap_top,
        cap_mesh=cap_mesh,
        cap_radial_layers=cap_radial_layers,
        cap_core_fraction=cap_core_fraction,
        shell_part_id=shell_part_id,
        shell_section_id=shell_section_id,
        shell_material_id=shell_material_id,
        shell_density=shell_density,
        shell_young=shell_young,
        shell_poisson=shell_poisson,
        attached_blocks=attached_blocks,
        mass_points=mass_points,
        internal_fill=internal_fill,
        title=title,
        termination_time=termination_time,
        database_dt=database_dt,
        overwrite=overwrite,
        check_json=check_json,
        config=load_config(),
    )


def check_lsdyna_cylindrical_assembly(
    k_path: str,
    shell_radius: float | None = None,
    shell_height: float | None = None,
    expect_closed_shell: bool = True,
    output_json: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    return _check_lsdyna_cylindrical_assembly(
        k_path=k_path,
        shell_radius=shell_radius,
        shell_height=shell_height,
        expect_closed_shell=expect_closed_shell,
        output_json=output_json,
        overwrite=overwrite,
        config=load_config(),
    )


def create_lsdyna_sale_fluid_domain(
    output_k: str,
    x_range: list[float],
    y_range: list[float],
    z_range: list[float] | None = None,
    nx: int = 10,
    ny: int = 10,
    nz: int | None = None,
    axisymmetric: bool = False,
    mesh_id: int = 1,
    domain_part_id: int = 101,
    section_id: int = 101,
    material_id: int = 1001,
    background_ammg: int = 1,
    materials: list[dict[str, Any]] | None = None,
    fills: list[dict[str, Any]] | None = None,
    boundary_type: str = "NONREFL",
    include_control_ale: bool = True,
    include_placeholder_materials: bool = True,
    termination_time: float = 1.0,
    database_dt: float = 0.01,
    title: str = "generated_sale_fluid_domain",
    overwrite: bool = False,
    check_json: str | None = None,
) -> dict[str, Any]:
    return _create_lsdyna_sale_fluid_domain(
        output_k=output_k,
        x_range=x_range,
        y_range=y_range,
        z_range=z_range,
        nx=nx,
        ny=ny,
        nz=nz,
        axisymmetric=axisymmetric,
        mesh_id=mesh_id,
        domain_part_id=domain_part_id,
        section_id=section_id,
        material_id=material_id,
        background_ammg=background_ammg,
        materials=materials,
        fills=fills,
        boundary_type=boundary_type,
        include_control_ale=include_control_ale,
        include_placeholder_materials=include_placeholder_materials,
        termination_time=termination_time,
        database_dt=database_dt,
        title=title,
        overwrite=overwrite,
        check_json=check_json,
        config=load_config(),
    )


def check_lsdyna_sale_fluid_domain(
    k_path: str,
    expect_axisymmetric: bool | None = None,
    output_json: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    return _check_lsdyna_sale_fluid_domain(
        k_path=k_path,
        expect_axisymmetric=expect_axisymmetric,
        output_json=output_json,
        overwrite=overwrite,
        config=load_config(),
    )


if FastMCP is not None:
    mcp = FastMCP("lspp-mcp-server")
    mcp.tool()(validate_lsprepost)
    mcp.tool()(list_supported_variables)
    mcp.tool()(export_d3plot_contour)
    mcp.tool()(export_d3plot_contour_frames)
    mcp.tool()(list_contour_color_styles)
    mcp.tool()(infer_d3plot_state_times)
    mcp.tool()(extract_ascii_curve)
    mcp.tool()(extract_d3plot_node_history)
    mcp.tool()(extract_binout_curve)
    mcp.tool()(batch_postprocess_cases)
    mcp.tool()(validate_case_generator_integration)
    mcp.tool()(inspect_lsdyna_case_config)
    mcp.tool()(generate_lsdyna_cases)
    mcp.tool()(generate_lsdyna_parameter_sweep)
    mcp.tool()(generate_lsdyna_keyword_field_sweep)
    mcp.tool()(validate_lsdyna_solver)
    mcp.tool()(run_lsdyna_solver)
    mcp.tool()(diagnose_lsdyna_logs)
    mcp.tool()(inspect_lsdyna_results)
    mcp.tool()(extract_lsdyna_metrics)
    mcp.tool()(compare_lsdyna_cases)
    mcp.tool()(inspect_keyword_deck)
    mcp.tool()(inspect_keyword_fields)
    mcp.tool()(check_keyword_deck)
    mcp.tool()(create_lsdyna_plate_mesh)
    mcp.tool()(create_lsdyna_block_mesh)
    mcp.tool()(create_lsdyna_cylinder_shell_mesh)
    mcp.tool()(precheck_lsdyna_keyword_model)
    mcp.tool()(preview_lsdyna_keyword_model)
    mcp.tool()(create_initial_volume_fraction_geometry)
    mcp.tool()(append_initial_volume_fraction_geometry)
    mcp.tool()(inspect_initial_volume_fraction_geometry)
    mcp.tool()(create_lsdyna_cylindrical_assembly)
    mcp.tool()(check_lsdyna_cylindrical_assembly)
    mcp.tool()(create_lsdyna_sale_fluid_domain)
    mcp.tool()(check_lsdyna_sale_fluid_domain)
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
