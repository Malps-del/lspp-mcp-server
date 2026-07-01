"""Read-only LS-DYNA keyword deck inspection tools."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import LsppConfig
from ..validators import LsppValidationError, ensure_input_file, positive_int
from ._common import get_config, result_from_validation_error


KEYWORD_GROUPS: dict[str, tuple[str, ...]] = {
    "control": ("*CONTROL_",),
    "database": ("*DATABASE_",),
    "part": ("*PART",),
    "section": ("*SECTION_",),
    "material": ("*MAT_",),
    "eos": ("*EOS_",),
    "hourglass": ("*HOURGLASS",),
    "node": ("*NODE",),
    "element": ("*ELEMENT_",),
    "set": ("*SET_",),
    "define": ("*DEFINE_",),
    "boundary": ("*BOUNDARY_",),
    "initial": ("*INITIAL_",),
    "ale": ("*ALE_", "*CONTROL_ALE", "*BOUNDARY_SALE", "*INITIAL_VOLUME_FRACTION"),
    "fsi": ("*ALE_STRUCTURED_FSI", "*CONSTRAINED_LAGRANGE_IN_SOLID", "*DATABASE_FSI"),
    "contact": ("*CONTACT_",),
    "load": ("*LOAD_",),
    "include": ("*INCLUDE",),
}

BLAST_IMPACT_KEYWORDS = {
    "*MAT_HIGH_EXPLOSIVE_BURN",
    "*MAT_HIGH_EXPLOSIVE_BURN_TITLE",
    "*MAT_JOHNSON_COOK",
    "*MAT_JOHNSON_COOK_TITLE",
    "*MAT_SIMPLIFIED_JOHNSON_COOK",
    "*MAT_PLASTIC_KINEMATIC",
    "*MAT_PLASTIC_KINEMATIC_TITLE",
    "*MAT_RIGID",
    "*MAT_RIGID_TITLE",
    "*MAT_RIGID_DISCRETE",
    "*MAT_RIGID_DISCRETE_TITLE",
    "*MAT_NULL",
    "*MAT_NULL_TITLE",
    "*MAT_VACUUM",
    "*MAT_WOOD",
    "*MAT_WOOD_TITLE",
    "*EOS_JWL",
    "*EOS_JWL_TITLE",
    "*EOS_GRUNEISEN",
    "*EOS_GRUNEISEN_TITLE",
    "*EOS_LINEAR_POLYNOMIAL",
    "*EOS_LINEAR_POLYNOMIAL_TITLE",
    "*INITIAL_DETONATION",
    "*INITIAL_VOLUME_FRACTION_GEOMETRY",
    "*INITIAL_HYDROSTATIC_ALE",
    "*ALE_STRUCTURED_MESH",
    "*ALE_STRUCTURED_MESH_CONTROL_POINTS",
    "*ALE_STRUCTURED_MULTI-MATERIAL_GROUP",
    "*ALE_STRUCTURED_FSI",
    "*SET_MULTI-MATERIAL_GROUP_LIST",
    "*CONSTRAINED_LAGRANGE_IN_SOLID",
    "*BOUNDARY_SALE_MESH_FACE",
    "*DATABASE_FSI",
    "*DATABASE_TRACER",
    "*DATABASE_BINARY_D3PART",
    "*DATABASE_BINARY_D3PLOT",
    "*DATABASE_BINARY_D3THDT",
}

DATABASE_KEYWORDS = {
    "d3plot": "*DATABASE_BINARY_D3PLOT",
    "d3part": "*DATABASE_BINARY_D3PART",
    "d3thdt": "*DATABASE_BINARY_D3THDT",
    "glstat": "*DATABASE_GLSTAT",
    "matsum": "*DATABASE_MATSUM",
    "nodout": "*DATABASE_NODOUT",
    "rcforc": "*DATABASE_RCFORC",
    "spcforc": "*DATABASE_SPCFORC",
    "secforc": "*DATABASE_SECFORC",
    "elout": "*DATABASE_ELOUT",
    "fsi": "*DATABASE_FSI",
    "tracer": "*DATABASE_TRACER",
    "extent_binary": "*DATABASE_EXTENT_BINARY",
    "history_node": "*DATABASE_HISTORY_NODE",
    "history_node_set": "*DATABASE_HISTORY_NODE_SET",
}

_INT_RE = re.compile(r"^[+-]?\d+$")
_NUMBER_SPLIT_RE = re.compile(r"[\s,]+")
_LABEL_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_/-]*|-")
_PARAM_REF_RE = re.compile(r"&([A-Za-z][A-Za-z0-9_]*)")

FIELD_SCHEMAS: dict[str, list[list[str]]] = {
    "*CONTROL_ALE": [
        ["dct", "nadv", "meth", "afac", "bfac", "cfac", "dfac", "efac"],
        ["start", "end", "aafac", "vfact", "prit", "ebc", "pref", "nsidebc"],
        ["ncpl", "nbkt", "imascl", "checkr", "beamin", "mmgpref", "pdifmx", "dtmufac"],
        ["optimpp", "ialedr", "bndflx", "minmas"],
    ],
    "*CONTROL_ENERGY": [
        ["hgen", "rwen", "slnten", "rylen", "irgen", "maten", "drlen", "disen"],
    ],
    "*CONTROL_TERMINATION": [
        ["endtim", "endcyc", "dtmin", "endeng", "endmas", "nosol"],
    ],
    "*CONTROL_TIMESTEP": [
        ["dtinit", "tssfac", "isdo", "tslimt", "dt2ms", "lctm", "erode", "ms1st"],
    ],
    "*DATABASE_BINARY_D3PLOT": [["dt", "lcdt", "beam", "npltc", "psetid"]],
    "*DATABASE_GLSTAT": [["dt", "binary", "lcur", "ioopt"]],
    "*DATABASE_MATSUM": [["dt", "binary", "lcur", "ioopt"]],
    "*DATABASE_TRACER": [["time", "track", "x", "y", "z", "ammgid", "nid", "radius"]],
    "*DATABASE_TRHIST": [["dt", "binary", "lcur", "ioopt"]],
    "*BOUNDARY_SALE_MESH_FACE": [
        ["bctype", "mshid", "negx", "posx", "negy", "posy", "negz", "posz"],
    ],
    "*INITIAL_DETONATION": [["pid", "x", "y", "z", "lt", "-", "mmgset"]],
    "*ALE_STRUCTURED_MESH": [["mshid", "pid", "nbid", "ebid"]],
    "*ALE_STRUCTURED_MESH_CONTROL_POINTS": [
        ["mshid", "dir", "start", "end", "ratio", "bias"],
    ],
    "*ALE_STRUCTURED_MULTI-MATERIAL_GROUP": [["ammgnm", "mid", "eosid", "-", "-", "-", "-", "pref"]],
    "*ALE_STRUCTURED_MULTI-MATERIAL_GROUP_AXISYM": [
        ["ammgnm", "mid", "eosid", "-", "-", "-", "-", "pref"]
    ],
    "*ALE_STRUCTURED_FSI": [
        ["lstrsid", "alesid", "lstrstyp", "alestyp", "-", "-", "-", "mcoup"],
        ["start", "end", "pfac", "fric", "-", "flip"],
    ],
}


@dataclass(slots=True)
class KeywordBlock:
    file_path: Path
    keyword: str
    line_number: int
    lines: list[str]

    @property
    def data_lines(self) -> list[str]:
        return [
            line.rstrip("\n")
            for line in self.lines[1:]
            if line.strip() and not line.lstrip().startswith("$")
        ]


def _normalize_keyword(line: str) -> str:
    token = line.strip().split()[0].upper()
    return token.rstrip(",")


def _base_keyword(keyword: str) -> str:
    return keyword[:-6] if keyword.endswith("_TITLE") else keyword


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _parse_blocks(path: Path) -> tuple[list[KeywordBlock], int]:
    lines = _read_lines(path)
    blocks: list[KeywordBlock] = []
    current_start: int | None = None
    current_keyword = ""
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("*") and not stripped.startswith("**"):
            if current_start is not None:
                blocks.append(
                    KeywordBlock(
                        file_path=path,
                        keyword=current_keyword,
                        line_number=current_start + 1,
                        lines=lines[current_start:index],
                    )
                )
            current_start = index
            current_keyword = _normalize_keyword(stripped)
    if current_start is not None:
        blocks.append(
            KeywordBlock(
                file_path=path,
                keyword=current_keyword,
                line_number=current_start + 1,
                lines=lines[current_start:],
            )
        )
    return blocks, len(lines)


def _first_int(lines: list[str], skip_title: bool = False) -> int | None:
    scan = lines[1:] if skip_title and len(lines) > 1 else lines
    for line in scan:
        for token in _NUMBER_SPLIT_RE.split(line.strip()):
            if _INT_RE.match(token):
                return int(token)
    return None


def _first_number_text(lines: list[str]) -> str | None:
    for line in lines:
        for token in _NUMBER_SPLIT_RE.split(line.strip()):
            if token:
                return token
    return None


def _extract_include_path(block: KeywordBlock) -> str | None:
    for line in block.data_lines:
        candidate = line.strip().strip('"').strip("'")
        if candidate:
            return candidate.split(",", 1)[0].strip().strip('"').strip("'")
    return None


def _resolve_include(base_file: Path, include_text: str) -> Path:
    include_path = Path(include_text)
    if not include_path.is_absolute():
        include_path = base_file.parent / include_path
    return include_path.resolve(strict=False)


def _belongs_to_group(keyword: str, prefixes: tuple[str, ...]) -> bool:
    base = _base_keyword(keyword)
    return any(base.startswith(prefix) for prefix in prefixes)


def _references(value: str) -> list[str]:
    return sorted({match.group(1) for match in _PARAM_REF_RE.finditer(value)})


def _value_kind(value: str) -> str:
    text = value.strip()
    if not text:
        return "empty"
    if _references(text):
        return "parameter_reference"
    try:
        float(text)
    except ValueError:
        return "text"
    return "number"


def _field(name: str, value: str, field_index: int) -> dict[str, Any]:
    refs = _references(value)
    return {
        "name": name,
        "value": value.strip(),
        "field_index": field_index,
        "kind": _value_kind(value),
        "references": refs,
        "normalized_references": [ref.lower() for ref in refs],
    }


def _comment_labels(line: str) -> list[str]:
    text = line.lstrip()
    if text.startswith("$#"):
        text = text[2:]
    elif text.startswith("$"):
        text = text[1:]
    return [match.group(0).lower() for match in _LABEL_RE.finditer(text)]


def _split_data_values(line: str, expected_count: int | None = None) -> list[str]:
    stripped = line.strip()
    if not stripped:
        return []
    if "," in stripped:
        return [part.strip() for part in stripped.split(",")]
    if expected_count and len(line) > 10:
        chunks = [line[index : index + 10].strip() for index in range(0, len(line), 10)]
        combined: list[str] = []
        for chunk in chunks:
            if chunk.startswith("&") and combined:
                combined[-1] = f"{combined[-1]}{chunk}"
            else:
                combined.append(chunk)
        chunks = combined
        if len(chunks) >= min(expected_count, 2):
            return chunks[:expected_count]
    return [part for part in _NUMBER_SPLIT_RE.split(stripped) if part]


def _schema_for(keyword: str) -> list[list[str]] | None:
    base = _base_keyword(keyword)
    if keyword in FIELD_SCHEMAS:
        return FIELD_SCHEMAS[keyword]
    return FIELD_SCHEMAS.get(base)


def _parse_parameter_block(block: KeywordBlock) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for local_index, line in enumerate(block.lines[1:], start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("$"):
            continue
        tokens = _split_data_values(line)
        fields: list[dict[str, Any]] = []
        for group_index in range(0, len(tokens), 3):
            group = tokens[group_index : group_index + 3]
            if len(group) < 3:
                continue
            parameter_index = group_index // 3 + 1
            fields.extend(
                [
                    _field(f"type_{parameter_index}", group[0], group_index),
                    _field(f"name_{parameter_index}", group[1], group_index + 1),
                    _field(f"value_{parameter_index}", group[2], group_index + 2),
                ]
            )
        rows.append(
            {
                "line": block.line_number + local_index,
                "line_index_in_block": local_index,
                "raw": line,
                "fields": fields,
            }
        )
    return rows


def _parse_parameter_expression_block(block: KeywordBlock) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for local_index, line in enumerate(block.lines[1:], start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("$"):
            continue
        parts = stripped.split(maxsplit=1)
        first = parts[0]
        expression = parts[1] if len(parts) > 1 else ""
        if len(first) >= 2 and first[0].isalpha():
            parameter_type = first[0]
            name = first[1:]
        else:
            parameter_type = ""
            name = first
        fields = [
            _field("type", parameter_type, 0),
            _field("name", name, 1),
            _field("expression", expression, 2),
        ]
        rows.append(
            {
                "line": block.line_number + local_index,
                "line_index_in_block": local_index,
                "raw": line,
                "fields": fields,
            }
        )
    return rows


def _parse_generic_block(block: KeywordBlock) -> tuple[list[dict[str, Any]], str]:
    schema = _schema_for(block.keyword)
    rows: list[dict[str, Any]] = []
    active_labels: list[str] = []
    data_row_index = 0
    for local_index, line in enumerate(block.lines[1:], start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("$"):
            labels = _comment_labels(line)
            if labels:
                active_labels = labels
            continue
        names = schema[data_row_index] if schema and data_row_index < len(schema) else active_labels
        values = _split_data_values(line, len(names) if names else None)
        if not values:
            continue
        fields = [
            _field(names[index] if index < len(names) else f"field_{index + 1}", value, index)
            for index, value in enumerate(values)
        ]
        rows.append(
            {
                "line": block.line_number + local_index,
                "line_index_in_block": local_index,
                "raw": line,
                "fields": fields,
            }
        )
        data_row_index += 1
    source = "schema" if schema else "comment_labels" if any(row["fields"] for row in rows) else "raw"
    return rows, source


def _parse_field_block(block: KeywordBlock) -> dict[str, Any]:
    if block.keyword == "*PARAMETER":
        rows = _parse_parameter_block(block)
        source = "schema"
    elif block.keyword.startswith("*PARAMETER_EXPRESSION"):
        rows = _parse_parameter_expression_block(block)
        source = "schema"
    else:
        rows, source = _parse_generic_block(block)
    return {
        "keyword": block.keyword,
        "base_keyword": _base_keyword(block.keyword),
        "file": str(block.file_path),
        "line": block.line_number,
        "schema_source": source,
        "rows": rows,
    }


def _parameter_summary(field_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    definitions: dict[str, Any] = {}
    expressions: dict[str, Any] = {}
    references: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for field_block in field_blocks:
        keyword = field_block["keyword"]
        if keyword == "*PARAMETER":
            for row in field_block["rows"]:
                fields = row["fields"]
                by_name = {field["name"]: field["value"] for field in fields}
                parameter_count = len(fields) // 3
                for index in range(1, parameter_count + 1):
                    name = by_name.get(f"name_{index}", "")
                    if not name:
                        continue
                    definitions[name.lower()] = {
                        "name": name,
                        "type": by_name.get(f"type_{index}", ""),
                        "value": by_name.get(f"value_{index}", ""),
                        "file": field_block["file"],
                        "line": row["line"],
                    }
        elif keyword.startswith("*PARAMETER_EXPRESSION"):
            for row in field_block["rows"]:
                by_name = {field["name"]: field for field in row["fields"]}
                name = by_name.get("name", {}).get("value", "")
                if not name:
                    continue
                expression = by_name.get("expression", {}).get("value", "")
                refs = [
                    token
                    for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_]*\b", expression)
                    if token.lower() not in {"r", "i", "c"}
                ]
                expressions[name.lower()] = {
                    "name": name,
                    "type": by_name.get("type", {}).get("value", ""),
                    "expression": expression,
                    "dependencies": sorted({ref for ref in refs if ref.lower() != name.lower()}),
                    "normalized_dependencies": sorted(
                        {ref.lower() for ref in refs if ref.lower() != name.lower()}
                    ),
                    "file": field_block["file"],
                    "line": row["line"],
                }
        for row in field_block["rows"]:
            for field in row["fields"]:
                for ref in field.get("references", []):
                    references[ref.lower()].append(
                        {
                            "name": ref,
                            "file": field_block["file"],
                            "keyword": keyword,
                            "block_line": field_block["line"],
                            "line": row["line"],
                            "field": field["name"],
                            "value": field["value"],
                        }
                    )
    return {
        "definitions": dict(sorted(definitions.items())),
        "expressions": dict(sorted(expressions.items())),
        "references": {key: value for key, value in sorted(references.items())},
    }


def _collect_deck(
    path: Path,
    allowed_roots: tuple[Path, ...],
    include_includes: bool,
    max_depth: int,
) -> tuple[list[KeywordBlock], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    all_blocks: list[KeywordBlock] = []
    includes: list[dict[str, Any]] = []
    file_line_counts: dict[str, int] = {}
    visited: set[Path] = set()

    def visit(file_path: Path, depth: int, parent: Path | None = None) -> None:
        resolved = file_path.resolve(strict=False)
        if resolved in visited:
            return
        visited.add(resolved)
        blocks, line_count = _parse_blocks(resolved)
        file_line_counts[str(resolved)] = line_count
        all_blocks.extend(blocks)
        if not include_includes or depth >= max_depth:
            return
        for block in blocks:
            if not block.keyword.startswith("*INCLUDE"):
                continue
            include_text = _extract_include_path(block)
            if not include_text:
                includes.append(
                    {
                        "source": str(block.file_path),
                        "line": block.line_number,
                        "path": "",
                        "resolved_path": "",
                        "exists": False,
                        "message": "Include card has no path.",
                    }
                )
                continue
            include_path = _resolve_include(block.file_path, include_text)
            exists = include_path.exists() and include_path.is_file()
            within_allowed = any(
                include_path.resolve(strict=False).is_relative_to(root)
                for root in allowed_roots
            )
            includes.append(
                {
                    "source": str(block.file_path),
                    "line": block.line_number,
                    "path": include_text,
                    "resolved_path": str(include_path),
                    "exists": exists,
                    "within_allowed_roots": within_allowed,
                }
            )
            if exists and within_allowed:
                visit(include_path, depth + 1, parent=resolved)

    visit(path, 0)
    return all_blocks, includes, [], file_line_counts


def _keyword_counts(blocks: list[KeywordBlock]) -> dict[str, int]:
    counts = Counter(block.keyword for block in blocks)
    return dict(sorted(counts.items()))


def _group_summary(blocks: list[KeywordBlock]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for group, prefixes in KEYWORD_GROUPS.items():
        group_blocks = [
            block for block in blocks if _belongs_to_group(block.keyword, prefixes)
        ]
        summary[group] = {
            "count": len(group_blocks),
            "keywords": dict(sorted(Counter(block.keyword for block in group_blocks).items())),
        }
    return summary


def _database_summary(blocks: list[KeywordBlock]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for name, keyword in DATABASE_KEYWORDS.items():
        matches = [block for block in blocks if _base_keyword(block.keyword) == keyword]
        found[name] = {
            "present": bool(matches),
            "keyword": keyword,
            "count": len(matches),
            "dt": _first_number_text(matches[0].data_lines) if matches else None,
            "locations": [
                {"file": str(block.file_path), "line": block.line_number}
                for block in matches[:10]
            ],
        }
    return found


def _entity_summary(blocks: list[KeywordBlock]) -> dict[str, Any]:
    entities: dict[str, list[dict[str, Any]]] = {
        "parts": [],
        "sections": [],
        "materials": [],
        "sets": [],
    }
    for block in blocks:
        base = _base_keyword(block.keyword)
        skip_title = block.keyword.endswith("_TITLE")
        if base == "*PART":
            entity_id = _first_int(block.data_lines, skip_title=True)
            entities["parts"].append(
                {
                    "id": entity_id,
                    "keyword": block.keyword,
                    "file": str(block.file_path),
                    "line": block.line_number,
                }
            )
        elif base.startswith("*SECTION_"):
            entity_id = _first_int(block.data_lines, skip_title=skip_title)
            entities["sections"].append(
                {
                    "id": entity_id,
                    "keyword": block.keyword,
                    "file": str(block.file_path),
                    "line": block.line_number,
                }
            )
        elif base.startswith("*MAT_"):
            entity_id = _first_int(block.data_lines, skip_title=skip_title)
            entities["materials"].append(
                {
                    "id": entity_id,
                    "keyword": block.keyword,
                    "file": str(block.file_path),
                    "line": block.line_number,
                }
            )
        elif base.startswith("*SET_"):
            entity_id = _first_int(block.data_lines, skip_title=skip_title)
            entities["sets"].append(
                {
                    "id": entity_id,
                    "keyword": block.keyword,
                    "file": str(block.file_path),
                    "line": block.line_number,
                }
            )
    return {
        name: {"count": len(items), "items": items[:50]}
        for name, items in entities.items()
    }


def _blast_impact_summary(blocks: list[KeywordBlock]) -> dict[str, Any]:
    counts = Counter(
        block.keyword for block in blocks if block.keyword in BLAST_IMPACT_KEYWORDS
    )
    return {
        "count": sum(counts.values()),
        "keywords": dict(sorted(counts.items())),
    }


def _issues(blocks: list[KeywordBlock], includes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(_base_keyword(block.keyword) for block in blocks)
    database = _database_summary(blocks)
    issues: list[dict[str, Any]] = []

    for include in includes:
        if not include.get("exists"):
            issues.append(
                {
                    "severity": "error",
                    "code": "missing_include",
                    "message": f"Include file is missing: {include.get('resolved_path')}",
                    "source": include.get("source"),
                    "line": include.get("line"),
                }
            )
        elif not include.get("within_allowed_roots", True):
            issues.append(
                {
                    "severity": "error",
                    "code": "include_outside_allowed_roots",
                    "message": (
                        "Include file exists but is outside allowed_roots: "
                        f"{include.get('resolved_path')}"
                    ),
                    "source": include.get("source"),
                    "line": include.get("line"),
                }
            )

    if counts["*END"] == 0:
        issues.append(
            {
                "severity": "warning",
                "code": "missing_end",
                "message": "No *END card was found in the parsed deck.",
            }
        )
    for required in ("*CONTROL_TERMINATION", "*CONTROL_TIMESTEP"):
        if counts[required] == 0:
            issues.append(
                {
                    "severity": "warning",
                    "code": "missing_control_card",
                    "message": f"{required} was not found.",
                }
            )

    if not (database["d3plot"]["present"] or database["d3part"]["present"]):
        issues.append(
            {
                "severity": "warning",
                "code": "missing_contour_database",
                "message": "No d3plot or d3part binary database card was found.",
            }
        )
    for name in ("glstat", "matsum", "extent_binary"):
        if not database[name]["present"]:
            issues.append(
                {
                    "severity": "info",
                    "code": "recommended_database_missing",
                    "message": f"{DATABASE_KEYWORDS[name]} was not found.",
                }
            )

    has_clis_fsi = counts["*CONSTRAINED_LAGRANGE_IN_SOLID"] > 0
    if has_clis_fsi and not database["fsi"]["present"]:
        issues.append(
            {
                "severity": "info",
                "code": "fsi_database_missing",
                "message": "CLIS FSI coupling is present, but *DATABASE_FSI was not found.",
            }
        )

    has_he = any(
        keyword.startswith("*MAT_HIGH_EXPLOSIVE_BURN") for keyword in counts
    )
    if has_he and counts["*EOS_JWL"] == 0:
        issues.append(
            {
                "severity": "warning",
                "code": "he_without_jwl",
                "message": "High explosive material is present, but *EOS_JWL was not found.",
            }
        )
    if counts["*INITIAL_DETONATION"] > 0 and not has_he:
        issues.append(
            {
                "severity": "info",
                "code": "detonation_without_he_material",
                "message": "*INITIAL_DETONATION is present; verify the explosive material IDs.",
            }
        )

    has_ale = any(keyword.startswith("*ALE_") for keyword in counts) or counts["*CONTROL_ALE"] > 0
    if has_ale and counts["*BOUNDARY_SALE_MESH_FACE"] == 0:
        issues.append(
            {
                "severity": "info",
                "code": "ale_boundary_not_found",
                "message": "ALE cards are present, but *BOUNDARY_SALE_MESH_FACE was not found.",
            }
        )

    if not any(keyword.startswith("*MAT_") for keyword in counts):
        issues.append(
            {"severity": "warning", "code": "no_materials", "message": "No *MAT cards found."}
        )
    if counts["*PART"] == 0:
        issues.append(
            {"severity": "warning", "code": "no_parts", "message": "No *PART cards found."}
        )
    return issues


def inspect_keyword_deck(
    k_path: str,
    extra_k_paths: list[str] | None = None,
    include_includes: bool = True,
    max_depth: int = 4,
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        depth = positive_int(max_depth, "max_depth")
        path = ensure_input_file(
            k_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="keyword file",
        )
        paths = [path]
        for extra_path in extra_k_paths or []:
            paths.append(
                ensure_input_file(
                    extra_path,
                    cfg.workspace_root,
                    cfg.resolved_allowed_roots(),
                    label="extra keyword file",
                )
            )
        blocks: list[KeywordBlock] = []
        includes: list[dict[str, Any]] = []
        file_line_counts: dict[str, int] = {}
        for deck_path in paths:
            deck_blocks, deck_includes, _warnings, deck_line_counts = _collect_deck(
                deck_path, cfg.resolved_allowed_roots(), include_includes, depth
            )
            blocks.extend(deck_blocks)
            includes.extend(deck_includes)
            file_line_counts.update(deck_line_counts)
        return {
            "ok": True,
            "message": "Keyword deck parsed successfully.",
            "k_path": str(path),
            "extra_k_paths": [str(item) for item in paths[1:]],
            "include_includes": include_includes,
            "files": [
                {"path": file_path, "line_count": line_count}
                for file_path, line_count in sorted(file_line_counts.items())
            ],
            "keyword_count": len(blocks),
            "keyword_counts": _keyword_counts(blocks),
            "groups": _group_summary(blocks),
            "database_outputs": _database_summary(blocks),
            "blast_impact": _blast_impact_summary(blocks),
            "entities": _entity_summary(blocks),
            "includes": includes,
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["k_path"] = str(k_path)
        return result


def inspect_keyword_fields(
    k_path: str,
    extra_k_paths: list[str] | None = None,
    include_includes: bool = True,
    max_depth: int = 4,
    keyword_filter: list[str] | None = None,
    include_unknown: bool = False,
    max_blocks: int = 200,
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        depth = positive_int(max_depth, "max_depth")
        limit = positive_int(max_blocks, "max_blocks")
        path = ensure_input_file(
            k_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="keyword file",
        )
        paths = [path]
        for extra_path in extra_k_paths or []:
            paths.append(
                ensure_input_file(
                    extra_path,
                    cfg.workspace_root,
                    cfg.resolved_allowed_roots(),
                    label="extra keyword file",
                )
            )
        blocks: list[KeywordBlock] = []
        includes: list[dict[str, Any]] = []
        file_line_counts: dict[str, int] = {}
        for deck_path in paths:
            deck_blocks, deck_includes, _warnings, deck_line_counts = _collect_deck(
                deck_path, cfg.resolved_allowed_roots(), include_includes, depth
            )
            blocks.extend(deck_blocks)
            includes.extend(deck_includes)
            file_line_counts.update(deck_line_counts)

        filters = {item.upper() for item in keyword_filter or []}
        field_blocks: list[dict[str, Any]] = []
        for block in blocks:
            if filters and block.keyword not in filters and _base_keyword(block.keyword) not in filters:
                continue
            parsed = _parse_field_block(block)
            has_schema = parsed["schema_source"] == "schema"
            has_fields = any(row["fields"] for row in parsed["rows"])
            if has_schema or include_unknown or filters or has_fields:
                field_blocks.append(parsed)
            if len(field_blocks) >= limit:
                break

        return {
            "ok": True,
            "message": "Keyword fields parsed successfully.",
            "k_path": str(path),
            "extra_k_paths": [str(item) for item in paths[1:]],
            "include_includes": include_includes,
            "files": [
                {"path": file_path, "line_count": line_count}
                for file_path, line_count in sorted(file_line_counts.items())
            ],
            "keyword_filter": sorted(filters),
            "truncated": len(field_blocks) >= limit,
            "field_block_count": len(field_blocks),
            "field_blocks": field_blocks,
            "parameter_summary": _parameter_summary(field_blocks),
            "includes": includes,
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["k_path"] = str(k_path)
        return result


def check_keyword_deck(
    k_path: str,
    extra_k_paths: list[str] | None = None,
    include_includes: bool = True,
    max_depth: int = 4,
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        depth = positive_int(max_depth, "max_depth")
        path = ensure_input_file(
            k_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="keyword file",
        )
        paths = [path]
        for extra_path in extra_k_paths or []:
            paths.append(
                ensure_input_file(
                    extra_path,
                    cfg.workspace_root,
                    cfg.resolved_allowed_roots(),
                    label="extra keyword file",
                )
            )
        blocks: list[KeywordBlock] = []
        includes: list[dict[str, Any]] = []
        file_line_counts: dict[str, int] = {}
        for deck_path in paths:
            deck_blocks, deck_includes, _warnings, deck_line_counts = _collect_deck(
                deck_path, cfg.resolved_allowed_roots(), include_includes, depth
            )
            blocks.extend(deck_blocks)
            includes.extend(deck_includes)
            file_line_counts.update(deck_line_counts)
        issues = _issues(blocks, includes)
        issue_counts = dict(Counter(issue["severity"] for issue in issues))
        ready_for_solver = issue_counts.get("error", 0) == 0
        return {
            "ok": True,
            "message": "Keyword deck checks completed.",
            "k_path": str(path),
            "extra_k_paths": [str(item) for item in paths[1:]],
            "ready_for_solver": ready_for_solver,
            "issue_counts": issue_counts,
            "issues": issues,
            "files": [
                {"path": file_path, "line_count": line_count}
                for file_path, line_count in sorted(file_line_counts.items())
            ],
            "database_outputs": _database_summary(blocks),
            "groups": _group_summary(blocks),
            "blast_impact": _blast_impact_summary(blocks),
            "includes": includes,
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["k_path"] = str(k_path)
        return result
