"""Structured ALE fluid-domain keyword helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import LsppConfig
from ..validators import LsppValidationError, ensure_input_file, positive_int
from ._common import get_config, prepare_output, result_from_validation_error
from .ale import inspect_initial_volume_fraction_geometry, render_initial_volume_fraction_geometry
from .keyword import check_keyword_deck, inspect_keyword_deck
from .preprocess import (
    _database_cards,
    _fmt,
    _positive_float,
    _write_keyword,
)


def _require_positive_int(value: int | str, label: str) -> int:
    number = positive_int(value, label)
    if number < 1:
        raise LsppValidationError(f"{label} must be positive")
    return number


def _line(values: list[int | float | str]) -> str:
    return " ".join(f"{_fmt(value) if isinstance(value, float) else str(value):>10}" for value in values).rstrip()


def _axis_extent(values: Any, label: str) -> tuple[float, float]:
    if not isinstance(values, list | tuple) or len(values) != 2:
        raise LsppValidationError(f"{label} must be [min, max]")
    start = float(values[0])
    end = float(values[1])
    if end <= start:
        raise LsppValidationError(f"{label}[1] must be greater than {label}[0]")
    return start, end


def _axis_divisions(value: int | str, label: str) -> int:
    number = _require_positive_int(value, label)
    if number < 1:
        raise LsppValidationError(f"{label} must be at least 1")
    return number


def _control_points(cpid: int, start: float, end: float, divisions: int) -> list[str]:
    return [
        "*ALE_STRUCTURED_MESH_CONTROL_POINTS",
        "$#    cpid    unused     icase       sfo    unused      offo",
        f"{cpid:>10}                   0       1.0                 0.0",
        "$#                 n                   x            ratio/xl",
        f"{1:>20}{_fmt(start):>20}                 0.0",
        f"{divisions + 1:>20}{_fmt(end):>20}                 0.0",
    ]


def _boundary_sale_lines(mshid: int, boundary_type: str) -> list[str]:
    bctype = boundary_type.strip().upper()
    if bctype not in {"NONREFL", "NOFLOW"}:
        raise LsppValidationError("boundary_type must be NONREFL or NOFLOW")
    return [
        "*BOUNDARY_SALE_MESH_FACE",
        "$#  bctype     mshid      negx      posx      negy      posy      negz      posz",
        f"{bctype:<10}{mshid:>10}         1         1         1         1         1         1",
    ]


def _placeholder_material_lines(materials: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for material in materials:
        mid = _require_positive_int(material.get("mid"), "materials[].mid")
        eosid = positive_int(material.get("eosid", 0), "materials[].eosid")
        density = float(material.get("density", 1.0))
        if density <= 0:
            raise LsppValidationError("materials[].density must be positive")
        title = str(material.get("name", f"neutral_material_{mid}"))
        lines.extend(
            [
                "*MAT_NULL_TITLE",
                title,
                "$#     mid        ro        pc        mu     terod     cerod        ym        pr",
                f"{mid}, {_fmt(density)}, 0, 0, 0, 0, 0, 0",
            ]
        )
        if eosid:
            lines.extend(
                [
                    "*EOS_LINEAR_POLYNOMIAL_TITLE",
                    f"placeholder_eos_{eosid}",
                    "$#   eosid        c0        c1        c2        c3        c4        c5        c6",
                    f"{eosid}, 0, 0, 0, 0, 0, 0, 0",
                    "$#      e0        v0",
                    "0, 1",
                ]
            )
    return lines


def _multi_material_group_lines(
    materials: list[dict[str, Any]],
    axisymmetric: bool,
) -> list[str]:
    keyword = (
        "*ALE_STRUCTURED_MULTI-MATERIAL_GROUP_AXISYM"
        if axisymmetric
        else "*ALE_STRUCTURED_MULTI-MATERIAL_GROUP"
    )
    lines = [keyword]
    for material in materials:
        ammg = _require_positive_int(material.get("ammg"), "materials[].ammg")
        mid = _require_positive_int(material.get("mid"), "materials[].mid")
        eosid = positive_int(material.get("eosid", 0), "materials[].eosid")
        pref = float(material.get("pref", 0.0))
        lines.extend(
            [
                "$#  ammgnm       mid     eosid    unused    unused    unused    unused      pref",
                f"{ammg:<10}{mid:>10}{eosid:>10}                                               {_fmt(pref)}",
            ]
        )
    return lines


def _set_part_lines(set_id: int, part_id: int) -> list[str]:
    return [
        "*SET_PART_LIST_TITLE",
        "sale_domain_part_set",
        "$#     sid       da1       da2       da3       da4    solver",
        f"{set_id:>10}       0.0       0.0       0.0       0.0MECH",
        "$#    pid1      pid2      pid3      pid4      pid5      pid6      pid7      pid8",
        f"{part_id:>10}",
    ]


def _default_materials(background_ammg: int) -> list[dict[str, Any]]:
    return [
        {
            "ammg": background_ammg,
            "mid": 1001,
            "eosid": 1001,
            "name": "neutral_background",
            "density": 1.0,
            "pref": 0.0,
        }
    ]


def _count_keyword(keyword_counts: dict[str, int], keyword: str) -> int:
    return keyword_counts.get(keyword, 0)


def check_lsdyna_sale_fluid_domain(
    k_path: str,
    expect_axisymmetric: bool | None = None,
    output_json: str | None = None,
    overwrite: bool = False,
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
        keyword_summary = inspect_keyword_deck(str(path), config=cfg)
        keyword_check = check_keyword_deck(str(path), config=cfg)
        counts = keyword_summary.get("keyword_counts", {})
        issues: list[dict[str, Any]] = []
        for issue in keyword_check.get("issues", []):
            if issue.get("severity") == "error":
                issues.append(issue)
        if _count_keyword(counts, "*ALE_STRUCTURED_MESH") == 0:
            issues.append(
                {
                    "severity": "error",
                    "code": "missing_sale_structured_mesh",
                    "message": "*ALE_STRUCTURED_MESH was not found.",
                }
            )
        control_point_count = _count_keyword(counts, "*ALE_STRUCTURED_MESH_CONTROL_POINTS")
        if control_point_count < 2:
            issues.append(
                {
                    "severity": "error",
                    "code": "insufficient_sale_control_points",
                    "message": "At least two *ALE_STRUCTURED_MESH_CONTROL_POINTS blocks are required.",
                }
            )
        has_axisym = _count_keyword(counts, "*ALE_STRUCTURED_MULTI-MATERIAL_GROUP_AXISYM") > 0
        has_3d = _count_keyword(counts, "*ALE_STRUCTURED_MULTI-MATERIAL_GROUP") > 0
        if not (has_axisym or has_3d):
            issues.append(
                {
                    "severity": "error",
                    "code": "missing_sale_multi_material_group",
                    "message": "No structured multi-material group keyword was found.",
                }
            )
        if expect_axisymmetric is True and not has_axisym:
            issues.append(
                {
                    "severity": "error",
                    "code": "axisymmetric_group_not_found",
                    "message": "Expected *_AXISYM multi-material group, but it was not found.",
                }
            )
        if expect_axisymmetric is False and not has_3d:
            issues.append(
                {
                    "severity": "error",
                    "code": "three_dimensional_group_not_found",
                    "message": "Expected 3D multi-material group, but it was not found.",
                }
            )
        fill = inspect_initial_volume_fraction_geometry(str(path), config=cfg)
        if _count_keyword(counts, "*BOUNDARY_SALE_MESH_FACE") == 0:
            issues.append(
                {
                    "severity": "warning",
                    "code": "missing_sale_boundary",
                    "message": "*BOUNDARY_SALE_MESH_FACE was not found.",
                }
            )
        error_count = sum(1 for issue in issues if issue.get("severity") == "error")
        result = {
            "ok": True,
            "message": "S-ALE fluid-domain check completed.",
            "k_path": str(path),
            "ready_for_solver": bool(keyword_check.get("ready_for_solver") and error_count == 0),
            "issue_counts": {
                "error": error_count,
                "warning": sum(1 for issue in issues if issue.get("severity") == "warning"),
                "info": sum(1 for issue in issues if issue.get("severity") == "info"),
            },
            "sale": {
                "structured_mesh_count": _count_keyword(counts, "*ALE_STRUCTURED_MESH"),
                "control_point_count": control_point_count,
                "axisymmetric_multi_material_group": has_axisym,
                "three_dimensional_multi_material_group": has_3d,
                "boundary_sale_mesh_face_count": _count_keyword(counts, "*BOUNDARY_SALE_MESH_FACE"),
                "initial_volume_fraction_block_count": fill.get("block_count", 0),
            },
            "issues": issues,
            "keyword": {
                "keyword_counts": counts,
                "groups": keyword_summary.get("groups", {}),
                "database_outputs": keyword_summary.get("database_outputs", {}),
            },
            "initial_volume_fraction": fill,
        }
        if output_json:
            output = prepare_output(output_json, cfg, overwrite)
            output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            result["output_json"] = str(output)
        return result
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["k_path"] = str(k_path)
        return result


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
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        output = prepare_output(output_k, cfg, overwrite)
        x0, x1 = _axis_extent(x_range, "x_range")
        y0, y1 = _axis_extent(y_range, "y_range")
        if axisymmetric:
            z_extent = None
            nz_value = None
        else:
            if z_range is None:
                raise LsppValidationError("z_range is required when axisymmetric=false")
            z_extent = _axis_extent(z_range, "z_range")
            nz_value = _axis_divisions(nz if nz is not None else nx, "nz")
        nx_value = _axis_divisions(nx, "nx")
        ny_value = _axis_divisions(ny, "ny")
        mesh_id_value = _require_positive_int(mesh_id, "mesh_id")
        part_id_value = _require_positive_int(domain_part_id, "domain_part_id")
        section_id_value = _require_positive_int(section_id, "section_id")
        material_id_value = _require_positive_int(material_id, "material_id")
        background_ammg_value = _require_positive_int(background_ammg, "background_ammg")
        termination = _positive_float(termination_time, "termination_time")
        dt = _positive_float(database_dt, "database_dt")
        material_specs = materials or _default_materials(background_ammg_value)
        if not any(int(item.get("ammg", 0)) == background_ammg_value for item in material_specs):
            raise LsppValidationError("materials must include the background_ammg")

        cpid_x = mesh_id_value * 1000 + 1
        cpid_y = mesh_id_value * 1000 + 2
        cpid_z = 0 if axisymmetric else mesh_id_value * 1000 + 3
        lines = [
            "*KEYWORD",
            f"$# created by lspp-mcp-server: {title}",
        ]
        if include_control_ale:
            lines.extend(
                [
                    "*CONTROL_ALE",
                    "$#     dct      nadv      meth      afac      bfac      cfac      dfac      efac",
                    "        -1         1        -2      -1.0       0.0       0.0       0.0       0.0",
                    "$#   start       end     aafac     vfact      prit       ebc      pref   nsidebc",
                    "       0.0 1.0000E20       1.0 1.0000E-6         0         0       0.0         0",
                    "$#    ncpl      nbkt    imascl    checkr    beamin   mmgpref    pdifmx   dtmufac",
                    "         1        50         0       0.0       0.0         0       0.0       0.0",
                    "$# optimpp    ialedr    bndflx    minmas",
                    "         0         0         0 1.0000E-5",
                    "*CONTROL_MPP_DECOMPOSITION_DISTRIBUTE_ALE_ELEMENTS",
                ]
            )
        lines.extend(_database_cards(termination, dt))
        lines.extend(
            [
                "*PART",
                "sale_fluid_domain",
                "$#     pid     secid       mid     eosid      hgid      grav    adpopt      tmid",
                f"{part_id_value}, {section_id_value}, {material_id_value}, 0, 0, 0, 0, 0",
                "*SECTION_SOLID",
                "$#   secid    elform       aet",
                f"{section_id_value}, 1, 0",
            ]
        )
        lines.extend(_set_part_lines(part_id_value, part_id_value))
        if include_placeholder_materials:
            lines.extend(_placeholder_material_lines(material_specs))
        lines.extend(_boundary_sale_lines(mesh_id_value, boundary_type))
        if fills:
            lines.append(
                render_initial_volume_fraction_geometry(
                    fmsid=part_id_value,
                    fmidtyp=1,
                    bammg=background_ammg_value,
                    ntrace=3,
                    fills=fills,
                    comments=True,
                ).rstrip("\n")
            )
        lines.extend(
            [
                "*ALE_STRUCTURED_MESH",
                "$#   mshid      dpid      nbid      ebid    unused    unused    unused    tdeath",
                f"{mesh_id_value:>10}{part_id_value:>10}         0         0                              1.00000E16",
                "$#   cpidx     cpidy     cpidz      nid0     lcsid",
                f"{cpid_x:>10}{cpid_y:>10}{cpid_z:>10}         0         0",
            ]
        )
        lines.extend(_control_points(cpid_x, x0, x1, nx_value))
        lines.extend(_control_points(cpid_y, y0, y1, ny_value))
        if not axisymmetric and z_extent is not None and nz_value is not None:
            lines.extend(_control_points(cpid_z, z_extent[0], z_extent[1], nz_value))
        lines.extend(_multi_material_group_lines(material_specs, axisymmetric))
        lines.append("*END")
        _write_keyword(output, lines)

        check = check_lsdyna_sale_fluid_domain(
            str(output),
            expect_axisymmetric=axisymmetric,
            output_json=check_json,
            overwrite=overwrite,
            config=cfg,
        )
        return {
            "ok": True,
            "message": "S-ALE fluid-domain keyword file generated.",
            "output_k": str(output),
            "domain": {
                "axisymmetric": axisymmetric,
                "mesh_id": mesh_id_value,
                "domain_part_id": part_id_value,
                "background_ammg": background_ammg_value,
                "x_range": [x0, x1],
                "y_range": [y0, y1],
                "z_range": list(z_extent) if z_extent is not None else None,
                "nx": nx_value,
                "ny": ny_value,
                "nz": nz_value,
                "material_group_count": len(material_specs),
                "fill_count": len(fills or []),
            },
            "check": check,
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["output_k"] = str(output_k)
        return result
