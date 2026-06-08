"""Tools for extracting binout/binout0000 curves through LS-PrePost binaski."""

from __future__ import annotations

from typing import Any

from ..config import LsppConfig
from ..validators import (
    LsppValidationError,
    ensure_input_file,
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


VALID_BINOUT_BLOCKS = {"glstat", "matsum", "trhist", "dbfsi"}


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


def extract_binout_curve(
    binout_path: str,
    block: str,
    variable: str,
    output_csv: str,
    entity_index: int | None = None,
    mpp: bool = False,
    xyplot_window: int = 1,
    overwrite: bool = False,
    config: LsppConfig | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        if block not in VALID_BINOUT_BLOCKS:
            raise LsppValidationError(
                f"block must be one of: {', '.join(sorted(VALID_BINOUT_BLOCKS))}"
            )
        input_file = ensure_input_file(
            binout_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="binout file",
        )
        output = prepare_output(output_csv, cfg, overwrite)
        resolved = _resolve_binout_entry(cfg.variable_maps, block, variable, entity_index)
        context = {
            "binout_path": quote_path(input_file),
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
