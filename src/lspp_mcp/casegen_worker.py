"""Subprocess worker for the optional LS-DYNA Batch Case Generator integration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def _load_services() -> dict[str, Any]:
    from lsdyna_batch_generator.core.models import (
        CaseDefinition,
        GenerationMethod,
        GeneratorConfig,
        IntegerRounding,
        OutputMode,
        OutputNamingConfig,
    )
    from lsdyna_batch_generator.core.parser import KFileParser
    from lsdyna_batch_generator.services.case_generator import CaseGeneratorService
    from lsdyna_batch_generator.services.config_service import ConfigService
    from lsdyna_batch_generator.services.constraint_service import ConstraintService
    from lsdyna_batch_generator.services.export_service import ExportService

    return {
        "CaseDefinition": CaseDefinition,
        "GenerationMethod": GenerationMethod,
        "GeneratorConfig": GeneratorConfig,
        "IntegerRounding": IntegerRounding,
        "OutputMode": OutputMode,
        "OutputNamingConfig": OutputNamingConfig,
        "KFileParser": KFileParser,
        "CaseGeneratorService": CaseGeneratorService,
        "ConfigService": ConfigService,
        "ConstraintService": ConstraintService,
        "ExportService": ExportService,
    }


def _apply_overrides(app_config: Any, overrides: dict[str, Any], services: dict[str, Any]) -> None:
    GenerationMethod = services["GenerationMethod"]
    IntegerRounding = services["IntegerRounding"]
    OutputMode = services["OutputMode"]

    generator = app_config.generator
    if overrides.get("method"):
        generator.method = GenerationMethod(overrides["method"])
    if overrides.get("sample_count") is not None:
        generator.sample_count = int(overrides["sample_count"])
    if "random_seed" in overrides:
        generator.random_seed = overrides["random_seed"]
    if overrides.get("avoid_duplicates") is not None:
        generator.avoid_duplicates = bool(overrides["avoid_duplicates"])
    if overrides.get("integer_rounding"):
        generator.integer_rounding = IntegerRounding(overrides["integer_rounding"])
    if overrides.get("excel_path"):
        generator.excel_path = overrides["excel_path"]

    output = app_config.output
    if overrides.get("output_dir"):
        output.output_dir = overrides["output_dir"]
    if overrides.get("output_mode"):
        output.output_mode = OutputMode(overrides["output_mode"])
    if overrides.get("folder_template"):
        output.folder_template = overrides["folder_template"]
    if overrides.get("file_template"):
        output.file_template = overrides["file_template"]
    if overrides.get("include_index_csv") is not None:
        output.include_index_csv = bool(overrides["include_index_csv"])
    if overrides.get("include_index_excel") is not None:
        output.include_index_excel = bool(overrides["include_index_excel"])
    if overrides.get("copy_support_files") is not None:
        output.copy_support_files = list(overrides["copy_support_files"])


def _generate_cases(app_config: Any, services: dict[str, Any]) -> tuple[Any, list[str]]:
    GenerationMethod = services["GenerationMethod"]
    CaseDefinition = services["CaseDefinition"]
    generator_service = services["CaseGeneratorService"]()
    constraint_service = services["ConstraintService"]()

    if not app_config.parameters:
        raise ValueError("配置中没有待修改参数。")

    generator_config = app_config.generator
    if generator_config.method == GenerationMethod.EXCEL:
        if not generator_config.excel_path:
            raise ValueError("Excel 生成方式需要 excel_path。")
        result = generator_service.load_from_excel(
            app_config.parameters, generator_config.excel_path
        )
    elif generator_config.method == GenerationMethod.LHS:
        result = generator_service.generate_lhs(app_config.parameters, generator_config)
    else:
        result = generator_service.generate_random(app_config.parameters, generator_config)

    constraint_result = constraint_service.apply_constraints(
        result.dataframe, app_config.constraints
    )
    result.dataframe = constraint_result.dataframe
    result.cases = [
        CaseDefinition(case_id=index + 1, values=row)
        for index, row in enumerate(result.dataframe.to_dict(orient="records"))
    ]
    warnings = list(result.warnings)
    warnings.extend(constraint_result.messages)
    return result, warnings


def _stats(dataframe: Any) -> dict[str, Any]:
    stats: dict[str, Any] = {"rows": int(len(dataframe.index)), "columns": list(dataframe.columns)}
    numeric: dict[str, Any] = {}
    try:
        import pandas as pd

        for column in dataframe.columns:
            series = dataframe[column]
            if pd.api.types.is_numeric_dtype(series):
                numeric[column] = {
                    "min": float(series.min()),
                    "max": float(series.max()),
                    "mean": float(series.mean()),
                }
    except Exception:
        pass
    stats["numeric"] = numeric
    return stats


def _command_validate() -> dict[str, Any]:
    services = _load_services()
    return {
        "ok": True,
        "message": "LS-DYNA Batch Case Generator modules imported successfully.",
        "available_services": sorted(services),
    }


def _command_inspect_config(request: dict[str, Any]) -> dict[str, Any]:
    services = _load_services()
    config_path = Path(request["project_config_path"])
    app_config = services["ConfigService"]().load(str(config_path))
    document = None
    keyword_summary: dict[str, int] = {}
    if app_config.k_file_path:
        document = services["KFileParser"]().parse(app_config.k_file_path)
        keyword_summary = document.keyword_summary()
    output_config = app_config.output
    return {
        "ok": True,
        "message": "Batch case generator config inspected.",
        "project_config_path": str(config_path),
        "k_file_path": app_config.k_file_path,
        "parameter_count": len(app_config.parameters),
        "parameters": [parameter.to_dict() for parameter in app_config.parameters],
        "constraint_count": len(app_config.constraints),
        "constraints": [constraint.to_dict() for constraint in app_config.constraints],
        "generator": app_config.generator.to_dict(),
        "output": output_config.to_dict(),
        "keyword_summary": keyword_summary,
        "line_count": len(document.lines) if document else 0,
    }


def _command_generate_cases(request: dict[str, Any]) -> dict[str, Any]:
    services = _load_services()
    config_path = Path(request["project_config_path"])
    app_config = services["ConfigService"]().load(str(config_path))
    _apply_overrides(app_config, request.get("overrides", {}), services)

    if not app_config.k_file_path:
        raise ValueError("配置中没有 k_file_path。")
    if not app_config.output.output_dir and not request.get("preview_only"):
        raise ValueError("配置中没有 output_dir。")

    document = services["KFileParser"]().parse(app_config.k_file_path)
    generation_result, warnings = _generate_cases(app_config, services)
    exporter = services["ExportService"]()
    preview_lines = exporter.preview_case_names(
        generation_result.cases, app_config.output, limit=int(request.get("preview_limit", 5))
    )

    records: list[dict[str, Any]] = []
    if not request.get("preview_only"):
        index_df = exporter.export_cases(
            document,
            app_config.parameters,
            generation_result.cases,
            app_config.output,
        )
        records = index_df.to_dict(orient="records")

    output_dir = Path(app_config.output.output_dir) if app_config.output.output_dir else None
    return {
        "ok": True,
        "message": "Case generation completed."
        if not request.get("preview_only")
        else "Case generation preview completed.",
        "preview_only": bool(request.get("preview_only")),
        "project_config_path": str(config_path),
        "k_file_path": app_config.k_file_path,
        "output_dir": str(output_dir) if output_dir else "",
        "generated_count": len(generation_result.cases),
        "warnings": warnings,
        "stats": _stats(generation_result.dataframe),
        "naming_preview": preview_lines,
        "records_preview": records[: int(request.get("preview_limit", 5))],
        "index_csv": str(output_dir / "case_index.csv")
        if output_dir and app_config.output.include_index_csv
        else "",
        "index_excel": str(output_dir / "case_index.xlsx")
        if output_dir and app_config.output.include_index_excel
        else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    args = parser.parse_args()

    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    command = request.get("command")
    try:
        if command == "validate":
            result = _command_validate()
        elif command == "inspect_config":
            result = _command_inspect_config(request)
        elif command == "generate_cases":
            result = _command_generate_cases(request)
        else:
            raise ValueError(f"Unsupported command: {command}")
    except Exception as exc:
        result = {"ok": False, "message": str(exc), "error_type": exc.__class__.__name__}

    sys.stdout.write(json.dumps(result, ensure_ascii=False, default=_json_default))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
