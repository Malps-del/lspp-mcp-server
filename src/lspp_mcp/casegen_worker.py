"""Subprocess worker for the optional LS-DYNA Batch Case Generator integration."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


TOKEN_PATTERN = re.compile(r"[^,\s]+")


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def _load_services() -> dict[str, Any]:
    from lsdyna_batch_generator.core.models import (
        CaseDefinition,
        DataType,
        GenerationMethod,
        GeneratorConfig,
        IntegerRounding,
        OutputMode,
        OutputNamingConfig,
        ParameterTarget,
    )
    from lsdyna_batch_generator.core.parser import KFileParser
    from lsdyna_batch_generator.services.case_generator import CaseGeneratorService
    from lsdyna_batch_generator.services.config_service import ConfigService
    from lsdyna_batch_generator.services.constraint_service import ConstraintService
    from lsdyna_batch_generator.services.export_service import ExportService

    return {
        "CaseDefinition": CaseDefinition,
        "DataType": DataType,
        "GenerationMethod": GenerationMethod,
        "GeneratorConfig": GeneratorConfig,
        "IntegerRounding": IntegerRounding,
        "OutputMode": OutputMode,
        "OutputNamingConfig": OutputNamingConfig,
        "ParameterTarget": ParameterTarget,
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


def _token_values(tokens: list[Any]) -> list[str]:
    return [str(getattr(token, "value", token)) for token in tokens]


def _looks_like_parameter_name(value: str, parameter_name: str) -> bool:
    return value.strip().lstrip("&").lower() == parameter_name.strip().lstrip("&").lower()


def _normalize_keyword(value: str) -> str:
    text = value.strip().upper()
    return text if text.startswith("*") else f"*{text}"


def _data_type_for(parameter_type: str, override: str | None, services: dict[str, Any]) -> Any:
    DataType = services["DataType"]
    raw = (override or parameter_type or "").strip().lower()
    if raw in {"i", "int", "integer"}:
        return DataType.INTEGER
    return DataType.FLOAT


def _parameter_target_from_match(
    parameter_name: str,
    parameter_type: str,
    current_value: str,
    line_number: int,
    field_index: int,
    block_start_line: int,
    relative_line_index: int,
    instance_index: int,
    services: dict[str, Any],
    data_type: str | None = None,
) -> Any:
    ParameterTarget = services["ParameterTarget"]
    return ParameterTarget(
        parameter_id=f"parameter_{parameter_name}",
        alias=parameter_name,
        keyword="*PARAMETER",
        instance_index=instance_index,
        block_start_line=block_start_line,
        relative_line_index=relative_line_index,
        file_line_number=line_number,
        field_index=field_index,
        current_value=current_value,
        source_name=f"*PARAMETER {parameter_name}",
        data_type=_data_type_for(parameter_type, data_type, services),
        group_name="mcp_parameter_sweep",
    )


def _field_target_from_match(
    alias: str,
    keyword: str,
    current_value: str,
    line_number: int,
    field_index: int,
    block_start_line: int,
    relative_line_index: int,
    instance_index: int,
    services: dict[str, Any],
    source_name: str = "",
    data_type: str | None = None,
) -> Any:
    ParameterTarget = services["ParameterTarget"]
    safe_alias = alias.strip() or "field_value"
    return ParameterTarget(
        parameter_id=f"keyword_field_{safe_alias}",
        alias=safe_alias,
        keyword=keyword,
        instance_index=instance_index,
        block_start_line=block_start_line,
        relative_line_index=relative_line_index,
        file_line_number=line_number,
        field_index=field_index,
        current_value=current_value,
        source_name=source_name or f"{keyword} field {field_index + 1}",
        data_type=_data_type_for("", data_type, services),
        group_name="mcp_keyword_field_sweep",
    )


def _line_tokens(raw_line: str) -> list[str]:
    return [match.group(0) for match in TOKEN_PATTERN.finditer(raw_line)]


def _token_values_from_line(parsed_line: Any) -> list[str]:
    return _token_values(list(getattr(parsed_line, "tokens", [])))


def _field_index_from_target(
    tokens: list[str],
    target: dict[str, Any],
    field_names: list[str] | None = None,
) -> int:
    if target.get("field_number") is not None:
        field_index = int(target["field_number"]) - 1
        if field_index < 0:
            raise ValueError("field_number must be 1-based and greater than 0")
        if field_index >= len(tokens):
            raise ValueError(f"field_number {field_index + 1} exceeds token count {len(tokens)}")
        return field_index

    field_name = str(target.get("field_name", "")).strip().lower()
    if field_name and field_names:
        for index, name in enumerate(field_names):
            if str(name).strip().lower() == field_name:
                return index
        raise ValueError(f"field_name not found on selected line: {target.get('field_name')}")

    current_value = target.get("current_value")
    if current_value is not None:
        matches = [
            index
            for index, token in enumerate(tokens)
            if str(token).strip() == str(current_value).strip()
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ValueError(f"current_value not found on selected line: {current_value}")
        raise ValueError(
            f"current_value appears {len(matches)} times; provide field_number to disambiguate"
        )

    raise ValueError("target must include field_number, field_name, or current_value")


def _locate_block_for_file_line(document: Any, file_line_number: int) -> Any | None:
    for block in getattr(document, "blocks", []):
        start_line = int(getattr(block, "start_line", 0))
        end_line = int(getattr(block, "end_line", 0))
        if start_line <= file_line_number <= end_line:
            return block
    return None


def _locate_keyword_field_target(
    document: Any,
    target: dict[str, Any],
    services: dict[str, Any],
    data_type: str | None = None,
) -> Any:
    alias = str(target.get("alias") or "field_value").strip()

    if target.get("file_line_number") is not None:
        line_number = int(target["file_line_number"])
        lines = list(getattr(document, "lines", []))
        if line_number < 1 or line_number > len(lines):
            raise ValueError(f"file_line_number is outside the file: {line_number}")
        raw_line = str(lines[line_number - 1])
        tokens = _line_tokens(raw_line)
        field_index = _field_index_from_target(tokens, target)
        block = _locate_block_for_file_line(document, line_number)
        keyword = (
            str(getattr(block, "keyword", "")).upper()
            if block is not None
            else _normalize_keyword(str(target.get("keyword") or "*UNKNOWN"))
        )
        block_start_line = int(getattr(block, "start_line", line_number)) if block is not None else line_number
        instance_index = int(getattr(block, "instance_index", 0)) if block is not None else 0
        return _field_target_from_match(
            alias=alias,
            keyword=keyword,
            current_value=tokens[field_index],
            line_number=line_number,
            field_index=field_index,
            block_start_line=block_start_line,
            relative_line_index=line_number - block_start_line,
            instance_index=instance_index,
            services=services,
            source_name=str(target.get("field_name") or ""),
            data_type=data_type,
        )

    keyword = _normalize_keyword(str(target.get("keyword") or ""))
    if keyword == "*":
        raise ValueError("target.keyword is required when file_line_number is not provided")
    keyword_instance = int(target.get("keyword_instance", 1))
    if keyword_instance < 1:
        raise ValueError("keyword_instance must be 1-based and greater than 0")

    matching_blocks = [
        block
        for block in getattr(document, "blocks", [])
        if str(getattr(block, "keyword", "")).upper() == keyword
    ]
    if len(matching_blocks) < keyword_instance:
        raise ValueError(f"keyword instance not found: {keyword} #{keyword_instance}")
    block = matching_blocks[keyword_instance - 1]

    selected_line = None
    if target.get("line_number_in_block") is not None:
        line_number_in_block = int(target["line_number_in_block"])
        for parsed_line in getattr(block, "parsed_lines", []):
            if int(getattr(parsed_line, "line_index_in_block", -1)) == line_number_in_block:
                selected_line = parsed_line
                break
        if selected_line is None:
            raise ValueError(
                f"line_number_in_block not found in {keyword} #{keyword_instance}: "
                f"{line_number_in_block}"
            )
    else:
        field_name = str(target.get("field_name", "")).strip().lower()
        current_value = target.get("current_value")
        for parsed_line in getattr(block, "parsed_lines", []):
            tokens = _token_values_from_line(parsed_line)
            if not tokens:
                continue
            names = list(getattr(parsed_line, "field_names", []))
            if field_name and any(str(name).strip().lower() == field_name for name in names):
                selected_line = parsed_line
                break
            if current_value is not None and any(
                str(token).strip() == str(current_value).strip() for token in tokens
            ):
                selected_line = parsed_line
                break
        if selected_line is None:
            raise ValueError(
                "Could not infer target line; provide line_number_in_block or file_line_number"
            )

    tokens = _token_values_from_line(selected_line)
    field_names = list(getattr(selected_line, "field_names", []))
    field_index = _field_index_from_target(tokens, target, field_names=field_names)
    source_name = (
        str(target.get("field_name") or "").strip()
        or (field_names[field_index] if field_index < len(field_names) else "")
    )
    return _field_target_from_match(
        alias=alias,
        keyword=keyword,
        current_value=tokens[field_index],
        line_number=int(getattr(selected_line, "line_number_in_file")),
        field_index=field_index,
        block_start_line=int(getattr(block, "start_line")),
        relative_line_index=int(getattr(selected_line, "line_index_in_block")),
        instance_index=int(getattr(block, "instance_index", keyword_instance - 1)),
        services=services,
        source_name=source_name,
        data_type=data_type,
    )


def _locate_parameter_target(
    document: Any,
    parameter_name: str,
    services: dict[str, Any],
    data_type: str | None = None,
) -> Any:
    for block in getattr(document, "blocks", []):
        if str(getattr(block, "keyword", "")).upper() != "*PARAMETER":
            continue
        for parsed_line in getattr(block, "parsed_lines", []):
            tokens = _token_values(list(getattr(parsed_line, "tokens", [])))
            for index in range(0, max(len(tokens) - 2, 0), 3):
                if _looks_like_parameter_name(tokens[index + 1], parameter_name):
                    return _parameter_target_from_match(
                        parameter_name=parameter_name,
                        parameter_type=tokens[index],
                        current_value=tokens[index + 2],
                        line_number=int(getattr(parsed_line, "line_number_in_file")),
                        field_index=index + 2,
                        block_start_line=int(getattr(block, "start_line")),
                        relative_line_index=int(getattr(parsed_line, "line_index_in_block")),
                        instance_index=int(getattr(block, "instance_index", 0)),
                        services=services,
                        data_type=data_type,
                    )

    lines = list(getattr(document, "lines", []))
    in_parameter_block = False
    block_start_line = 0
    instance_index = -1
    for zero_index, raw_line in enumerate(lines):
        stripped = str(raw_line).strip()
        if stripped.upper().startswith("*PARAMETER"):
            in_parameter_block = True
            block_start_line = zero_index + 1
            instance_index += 1
            continue
        if stripped.startswith("*"):
            in_parameter_block = False
            continue
        if not in_parameter_block or not stripped or stripped.startswith("$"):
            continue
        tokens = str(raw_line).replace(",", " ").split()
        for index in range(0, max(len(tokens) - 2, 0), 3):
            if _looks_like_parameter_name(tokens[index + 1], parameter_name):
                return _parameter_target_from_match(
                    parameter_name=parameter_name,
                    parameter_type=tokens[index],
                    current_value=tokens[index + 2],
                    line_number=zero_index + 1,
                    field_index=index + 2,
                    block_start_line=block_start_line,
                    relative_line_index=(zero_index + 1) - block_start_line,
                    instance_index=max(instance_index, 0),
                    services=services,
                    data_type=data_type,
                )

    raise ValueError(f"Parameter not found in *PARAMETER block: {parameter_name}")


def _command_generate_parameter_sweep(request: dict[str, Any]) -> dict[str, Any]:
    services = _load_services()
    CaseDefinition = services["CaseDefinition"]
    OutputMode = services["OutputMode"]
    OutputNamingConfig = services["OutputNamingConfig"]

    k_file_path = str(request["k_file_path"])
    output = dict(request.get("output", {}))
    output_config = OutputNamingConfig(
        output_dir=str(output.get("output_dir", "")),
        output_mode=OutputMode(output.get("output_mode", "separate_folders")),
        folder_template=str(output.get("folder_template", "case_{case_id:03d}")),
        file_template=str(output.get("file_template", "{case_name}.k")),
        include_index_csv=bool(output.get("include_index_csv", True)),
        include_index_excel=bool(output.get("include_index_excel", False)),
        copy_support_files=list(output.get("copy_support_files", [])),
    )
    if not output_config.output_dir and not request.get("preview_only"):
        raise ValueError("output_dir is required for case export")

    document = services["KFileParser"]().parse(k_file_path)
    parameter_name = str(request["parameter_name"])
    target = _locate_parameter_target(
        document,
        parameter_name,
        services,
        data_type=request.get("data_type"),
    )
    values = list(request.get("values", []))
    cases = [
        CaseDefinition(case_id=index + 1, values={parameter_name: value})
        for index, value in enumerate(values)
    ]

    exporter = services["ExportService"]()
    preview_limit = int(request.get("preview_limit", 5))
    preview_lines = exporter.preview_case_names(cases, output_config, limit=preview_limit)
    records: list[dict[str, Any]] = []
    if not request.get("preview_only"):
        index_df = exporter.export_cases(document, [target], cases, output_config)
        records = index_df.to_dict(orient="records")

    output_dir = Path(output_config.output_dir) if output_config.output_dir else None
    return {
        "ok": True,
        "message": "Parameter sweep generation completed."
        if not request.get("preview_only")
        else "Parameter sweep generation preview completed.",
        "preview_only": bool(request.get("preview_only")),
        "k_file_path": k_file_path,
        "parameter": target.to_dict(),
        "output": output_config.to_dict(),
        "output_dir": str(output_dir) if output_dir else "",
        "generated_count": len(cases),
        "values": values,
        "naming_preview": preview_lines,
        "records_preview": records[:preview_limit],
        "index_csv": str(output_dir / "case_index.csv")
        if output_dir and output_config.include_index_csv
        else "",
        "index_excel": str(output_dir / "case_index.xlsx")
        if output_dir and output_config.include_index_excel
        else "",
    }


def _command_generate_keyword_field_sweep(request: dict[str, Any]) -> dict[str, Any]:
    services = _load_services()
    CaseDefinition = services["CaseDefinition"]
    OutputMode = services["OutputMode"]
    OutputNamingConfig = services["OutputNamingConfig"]

    k_file_path = str(request["k_file_path"])
    output = dict(request.get("output", {}))
    output_config = OutputNamingConfig(
        output_dir=str(output.get("output_dir", "")),
        output_mode=OutputMode(output.get("output_mode", "separate_folders")),
        folder_template=str(output.get("folder_template", "case_{case_id:03d}")),
        file_template=str(output.get("file_template", "{case_name}.k")),
        include_index_csv=bool(output.get("include_index_csv", True)),
        include_index_excel=bool(output.get("include_index_excel", False)),
        copy_support_files=list(output.get("copy_support_files", [])),
    )
    if not output_config.output_dir and not request.get("preview_only"):
        raise ValueError("output_dir is required for case export")

    document = services["KFileParser"]().parse(k_file_path)
    target = _locate_keyword_field_target(
        document,
        dict(request.get("target", {})),
        services,
        data_type=request.get("data_type"),
    )
    alias = target.alias
    values = list(request.get("values", []))
    cases = [
        CaseDefinition(case_id=index + 1, values={alias: value})
        for index, value in enumerate(values)
    ]

    exporter = services["ExportService"]()
    preview_limit = int(request.get("preview_limit", 5))
    preview_lines = exporter.preview_case_names(cases, output_config, limit=preview_limit)
    records: list[dict[str, Any]] = []
    if not request.get("preview_only"):
        index_df = exporter.export_cases(document, [target], cases, output_config)
        records = index_df.to_dict(orient="records")

    output_dir = Path(output_config.output_dir) if output_config.output_dir else None
    return {
        "ok": True,
        "message": "Keyword field sweep generation completed."
        if not request.get("preview_only")
        else "Keyword field sweep generation preview completed.",
        "preview_only": bool(request.get("preview_only")),
        "k_file_path": k_file_path,
        "target": target.to_dict(),
        "output": output_config.to_dict(),
        "output_dir": str(output_dir) if output_dir else "",
        "generated_count": len(cases),
        "values": values,
        "naming_preview": preview_lines,
        "records_preview": records[:preview_limit],
        "index_csv": str(output_dir / "case_index.csv")
        if output_dir and output_config.include_index_csv
        else "",
        "index_excel": str(output_dir / "case_index.xlsx")
        if output_dir and output_config.include_index_excel
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
        elif command == "generate_parameter_sweep":
            result = _command_generate_parameter_sweep(request)
        elif command == "generate_keyword_field_sweep":
            result = _command_generate_keyword_field_sweep(request)
        else:
            raise ValueError(f"Unsupported command: {command}")
    except Exception as exc:
        result = {"ok": False, "message": str(exc), "error_type": exc.__class__.__name__}

    sys.stdout.write(json.dumps(result, ensure_ascii=False, default=_json_default))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
