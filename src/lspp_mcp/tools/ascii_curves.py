"""Tools for extracting LS-DYNA ASCII result curves."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import LsppConfig
from ..validators import (
    LsppValidationError,
    ensure_input_file,
    positive_int,
    require_variable_code,
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


VALID_ASCII_TYPES = {"nodout", "matsum", "glstat", "rcforc"}


def _plot_expression(
    ascii_type: str,
    variable_maps: dict[str, Any],
    variable: str | None,
    variable_code: int | None,
    entity_id: str | int | None,
) -> str:
    if ascii_type == "nodout":
        code = require_variable_code(variable_maps, "nodout", variable, variable_code)
        if entity_id is None:
            raise LsppValidationError("entity_id is required for nodout")
        return f"{code} {safe_token(entity_id, 'node_id')}"
    if ascii_type == "matsum":
        code = require_variable_code(variable_maps, "matsum", variable, variable_code)
        if entity_id is None:
            raise LsppValidationError("entity_id is required for matsum")
        return f"{code} {safe_token(entity_id, 'part_id')}"
    if ascii_type == "rcforc":
        if variable_code is None:
            if variable is None:
                raise LsppValidationError("variable_code is required for rcforc")
            if str(variable).isdigit():
                code = positive_int(variable, "variable")
            else:
                rcforc_map = variable_maps.get("rcforc", {})
                if variable not in rcforc_map:
                    raise LsppValidationError(
                        "rcforc requires variable_code or a configured variable"
                    )
                code = positive_int(rcforc_map[variable], f"rcforc.{variable}")
        else:
            code = positive_int(variable_code, "variable_code")
        if entity_id is None:
            raise LsppValidationError("entity_id is required for rcforc")
        return f"{code} {safe_token(entity_id, 'interface_or_name')}"
    if ascii_type == "glstat":
        if variable_code is not None:
            return str(positive_int(variable_code, "variable_code"))
        if not variable:
            raise LsppValidationError("variable or variable_code is required for glstat")
        return safe_token(variable, "glstat plot expression")
    raise LsppValidationError(f"Unsupported ascii_type: {ascii_type}")


def extract_ascii_curve(
    ascii_type: str,
    file_path: str,
    output_csv: str,
    variable: str | None = None,
    variable_code: int | None = None,
    entity_id: str | int | None = None,
    xyplot_window: int = 1,
    overwrite: bool = False,
    config: LsppConfig | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        if ascii_type not in VALID_ASCII_TYPES:
            raise LsppValidationError(
                f"ascii_type must be one of: {', '.join(sorted(VALID_ASCII_TYPES))}"
            )
        input_file = ensure_input_file(
            file_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label=f"{ascii_type} file",
        )
        output = prepare_output(output_csv, cfg, overwrite)
        context = {
            "ascii_type": ascii_type,
            "file_path": quote_path(input_file),
            "plot_expression": _plot_expression(
                ascii_type, cfg.variable_maps, variable, variable_code, entity_id
            ),
            "xyplot_window": positive_int(xyplot_window, "xyplot_window"),
            "output_csv": quote_path(output),
        }
        cfile_path, log_file, run_result, output_check = execute_generated_cfile(
            output_path=output,
            tool_name=f"extract_ascii_{ascii_type}",
            template_name="extract_ascii_curve.cfile.j2",
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
