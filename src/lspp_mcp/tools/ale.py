"""Controlled ALE keyword helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import LsppConfig
from ..validators import LsppValidationError, ensure_input_file, positive_int
from ._common import get_config, prepare_output, result_from_validation_error
from .keyword import check_keyword_deck


GEOMETRY_TO_CNTTYP = {
    "part": 1,
    "part_set": 1,
    "segment": 2,
    "segment_set": 2,
    "plane": 3,
    "cylinder": 4,
    "cone": 4,
    "box": 5,
    "sphere": 6,
    "function": 7,
}


def _fmt(value: int | float | str) -> str:
    if isinstance(value, float):
        return f"{value:.10g}"
    return str(value)


def _line(values: list[int | float | str]) -> str:
    return ", ".join(_fmt(value) for value in values)


def _number_triplet(values: Any, label: str) -> list[float]:
    if not isinstance(values, list | tuple) or len(values) != 3:
        raise LsppValidationError(f"{label} must be a list of three numbers")
    try:
        return [float(value) for value in values]
    except (TypeError, ValueError) as exc:
        raise LsppValidationError(f"{label} must be a list of three numbers") from exc


def _number_pair(values: Any, label: str) -> list[float]:
    if not isinstance(values, list | tuple) or len(values) != 2:
        raise LsppValidationError(f"{label} must be a list of two numbers")
    try:
        return [float(value) for value in values]
    except (TypeError, ValueError) as exc:
        raise LsppValidationError(f"{label} must be a list of two numbers") from exc


def _optional_velocity(fill: dict[str, Any]) -> list[float]:
    velocity = fill.get("velocity")
    if velocity is None:
        return [0.0, 0.0, 0.0]
    return _number_triplet(velocity, "velocity")


def _positive_float(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise LsppValidationError(f"{label} must be a positive number") from exc
    if number <= 0:
        raise LsppValidationError(f"{label} must be a positive number")
    return number


def _validate_fill(fill: dict[str, Any], index: int) -> tuple[int, list[int | float | str], list[int | float | str], str]:
    if not isinstance(fill, dict):
        raise LsppValidationError(f"fills[{index}] must be a mapping")
    geometry = str(fill.get("geometry", "")).strip().lower()
    if geometry not in GEOMETRY_TO_CNTTYP:
        supported = ", ".join(sorted(GEOMETRY_TO_CNTTYP))
        raise LsppValidationError(f"fills[{index}].geometry must be one of: {supported}")
    cnttyp = GEOMETRY_TO_CNTTYP[geometry]
    fillopt = int(fill.get("fillopt", 0))
    if fillopt not in {0, 1}:
        raise LsppValidationError(f"fills[{index}].fillopt must be 0 or 1")
    if "fammg" not in fill:
        raise LsppValidationError(f"fills[{index}].fammg is required")
    fammg = fill["fammg"]
    if isinstance(fammg, int) and fammg == 0:
        raise LsppValidationError(f"fills[{index}].fammg cannot be 0")
    velocity = _optional_velocity(fill)
    container = [cnttyp, fillopt, fammg, *velocity]
    label = geometry

    if geometry in {"part", "part_set"}:
        sid = positive_int(fill.get("sid"), f"fills[{index}].sid")
        stype = int(fill.get("stype", 1 if geometry == "part" else 0))
        normdir = int(fill.get("normdir", 0))
        xoffst = float(fill.get("xoffst", 0.0))
        detail = [sid, stype, normdir, xoffst]
    elif geometry in {"segment", "segment_set"}:
        sgsid = positive_int(fill.get("sgsid"), f"fills[{index}].sgsid")
        normdir = int(fill.get("normdir", 0))
        xoffst = float(fill.get("xoffst", 0.0))
        detail = [sgsid, normdir, xoffst]
    elif geometry == "plane":
        point = _number_triplet(fill.get("point"), f"fills[{index}].point")
        normal = _number_triplet(fill.get("normal"), f"fills[{index}].normal")
        detail = [*point, *normal]
    elif geometry in {"cylinder", "cone"}:
        point0 = _number_triplet(fill.get("point0"), f"fills[{index}].point0")
        point1 = _number_triplet(fill.get("point1"), f"fills[{index}].point1")
        if geometry == "cylinder":
            radius = _positive_float(fill.get("radius"), f"fills[{index}].radius")
            radii = [radius, radius]
        else:
            radii = _number_pair(fill.get("radii"), f"fills[{index}].radii")
            if radii[0] <= 0 or radii[1] <= 0:
                raise LsppValidationError(f"fills[{index}].radii values must be positive")
        detail = [*point0, *point1, *radii]
    elif geometry == "box":
        min_corner = _number_triplet(fill.get("min"), f"fills[{index}].min")
        max_corner = _number_triplet(fill.get("max"), f"fills[{index}].max")
        lcsid = int(fill.get("lcsid", 0))
        detail = [*min_corner, *max_corner, lcsid]
    elif geometry == "sphere":
        center = _number_triplet(fill.get("center"), f"fills[{index}].center")
        radius = _positive_float(fill.get("radius"), f"fills[{index}].radius")
        detail = [*center, radius]
    else:
        idfunc = positive_int(fill.get("idfunc"), f"fills[{index}].idfunc")
        detail = [idfunc]
    return cnttyp, container, detail, label


def render_initial_volume_fraction_geometry(
    fmsid: int,
    bammg: int | str,
    fills: list[dict[str, Any]],
    fmidtyp: int = 1,
    ntrace: int = 3,
    comments: bool = True,
) -> str:
    if not fills:
        raise LsppValidationError("fills must contain at least one filling action")
    fmsid_value = positive_int(fmsid, "fmsid")
    fmidtyp_value = int(fmidtyp)
    if fmidtyp_value not in {0, 1}:
        raise LsppValidationError("fmidtyp must be 0 for part set or 1 for part id")
    ntrace_value = positive_int(ntrace, "ntrace")
    if ntrace_value < 1:
        raise LsppValidationError("ntrace must be at least 1")
    lines = ["*INITIAL_VOLUME_FRACTION_GEOMETRY"]
    if comments:
        lines.append("$#   fmsid   fmidtyp     bammg    ntrace")
    lines.append(_line([fmsid_value, fmidtyp_value, bammg, ntrace_value]))
    for index, fill in enumerate(fills):
        _cnttyp, container, detail, label = _validate_fill(fill, index)
        if comments:
            lines.append(f"$# fill {index + 1}: {label}")
            lines.append("$#  cnttyp   fillopt     fammg        vx        vy        vz")
        lines.append(_line(container))
        lines.append(_line(detail))
    return "\n".join(lines) + "\n"


def create_initial_volume_fraction_geometry(
    output_k: str,
    fmsid: int,
    bammg: int | str,
    fills: list[dict[str, Any]],
    fmidtyp: int = 1,
    ntrace: int = 3,
    comments: bool = True,
    overwrite: bool = False,
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        output = prepare_output(output_k, cfg, overwrite)
        content = render_initial_volume_fraction_geometry(
            fmsid=fmsid,
            fmidtyp=fmidtyp,
            bammg=bammg,
            ntrace=ntrace,
            fills=fills,
            comments=comments,
        )
        output.write_text(content, encoding="utf-8", newline="\n")
        inspected = inspect_initial_volume_fraction_geometry(str(output), config=cfg)
        return {
            "ok": True,
            "message": "INITIAL_VOLUME_FRACTION_GEOMETRY block generated.",
            "output_k": str(output),
            "fill_count": len(fills),
            "inspection": inspected,
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["output_k"] = str(output_k)
        return result


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
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        source = ensure_input_file(
            k_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="keyword file",
        )
        output = prepare_output(output_k, cfg, overwrite)
        block = render_initial_volume_fraction_geometry(
            fmsid=fmsid,
            fmidtyp=fmidtyp,
            bammg=bammg,
            ntrace=ntrace,
            fills=fills,
            comments=comments,
        ).rstrip("\n")
        lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
        inserted = False
        if insert_before_end:
            for index in range(len(lines) - 1, -1, -1):
                if lines[index].strip().upper().startswith("*END"):
                    lines[index:index] = [block]
                    inserted = True
                    break
        if not inserted:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(block)
        output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        return {
            "ok": True,
            "message": "INITIAL_VOLUME_FRACTION_GEOMETRY block appended.",
            "source_k": str(source),
            "output_k": str(output),
            "inserted_before_end": inserted,
            "fill_count": len(fills),
            "inspection": inspect_initial_volume_fraction_geometry(str(output), config=cfg),
            "keyword_check": check_keyword_deck(str(output), config=cfg),
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["k_path"] = str(k_path)
        result["output_k"] = str(output_k)
        return result


def _split_values(line: str) -> list[str]:
    text = line.strip()
    if not text or text.startswith("$"):
        return []
    if "," in text:
        return [part.strip() for part in text.split(",") if part.strip()]
    return [part for part in text.split() if part]


def _parse_fill_detail(cnttyp: int, values: list[str]) -> dict[str, Any]:
    if cnttyp == 1:
        return {
            "sid": values[0] if len(values) > 0 else "",
            "stype": values[1] if len(values) > 1 else "",
            "normdir": values[2] if len(values) > 2 else "",
            "xoffst": values[3] if len(values) > 3 else "",
        }
    if cnttyp == 2:
        return {
            "sgsid": values[0] if len(values) > 0 else "",
            "normdir": values[1] if len(values) > 1 else "",
            "xoffst": values[2] if len(values) > 2 else "",
        }
    if cnttyp == 3:
        return {"point": values[:3], "normal": values[3:6]}
    if cnttyp == 4:
        return {"point0": values[:3], "point1": values[3:6], "r1": values[6] if len(values) > 6 else "", "r2": values[7] if len(values) > 7 else ""}
    if cnttyp == 5:
        return {"min": values[:3], "max": values[3:6], "lcsid": values[6] if len(values) > 6 else ""}
    if cnttyp == 6:
        return {"center": values[:3], "radius": values[3] if len(values) > 3 else ""}
    if cnttyp == 7:
        return {"idfunc": values[0] if values else ""}
    return {"raw": values}


def inspect_initial_volume_fraction_geometry(
    k_path: str,
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        path = ensure_input_file(
            k_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="keyword file",
        )
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        blocks: list[dict[str, Any]] = []
        index = 0
        while index < len(lines):
            if not lines[index].strip().upper().startswith("*INITIAL_VOLUME_FRACTION_GEOMETRY"):
                index += 1
                continue
            block_line = index + 1
            index += 1
            data: list[tuple[int, list[str], str]] = []
            while index < len(lines) and not lines[index].lstrip().startswith("*"):
                values = _split_values(lines[index])
                if values:
                    data.append((index + 1, values, lines[index]))
                index += 1
            if not data:
                blocks.append({"line": block_line, "error": "missing_card_1", "fills": []})
                continue
            card1_line, card1, _raw = data[0]
            fills: list[dict[str, Any]] = []
            cursor = 1
            while cursor + 1 < len(data):
                container_line, container, _container_raw = data[cursor]
                detail_line, detail, _detail_raw = data[cursor + 1]
                cnttyp = int(float(container[0])) if container else 0
                fills.append(
                    {
                        "line": container_line,
                        "detail_line": detail_line,
                        "cnttyp": cnttyp,
                        "fillopt": container[1] if len(container) > 1 else "",
                        "fammg": container[2] if len(container) > 2 else "",
                        "velocity": container[3:6],
                        "geometry": {
                            1: "part",
                            2: "segment",
                            3: "plane",
                            4: "cylinder_or_cone",
                            5: "box",
                            6: "sphere",
                            7: "function",
                        }.get(cnttyp, "unknown"),
                        "detail": _parse_fill_detail(cnttyp, detail),
                    }
                )
                cursor += 2
            blocks.append(
                {
                    "line": block_line,
                    "card1_line": card1_line,
                    "fmsid": card1[0] if len(card1) > 0 else "",
                    "fmidtyp": card1[1] if len(card1) > 1 else "",
                    "bammg": card1[2] if len(card1) > 2 else "",
                    "ntrace": card1[3] if len(card1) > 3 else "",
                    "fill_count": len(fills),
                    "fills": fills,
                }
            )
        return {
            "ok": True,
            "message": "INITIAL_VOLUME_FRACTION_GEOMETRY blocks inspected.",
            "k_path": str(path),
            "block_count": len(blocks),
            "blocks": blocks,
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["k_path"] = str(k_path)
        return result
