"""Neutral cylindrical assembly keyword helpers."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from ..config import LsppConfig
from ..validators import LsppValidationError, ensure_input_file, positive_int
from ._common import get_config, prepare_output, result_from_validation_error
from .ale import render_initial_volume_fraction_geometry
from .preprocess import (
    _circumference_division_count,
    _database_cards,
    _division_count,
    _fmt,
    _material_elastic,
    _mesh_summary,
    _positive_divisions,
    _positive_float,
    _square_grid_boundary_order,
    _write_keyword,
    precheck_lsdyna_keyword_model,
)


def _require_positive_id(value: int | str, label: str) -> int:
    number = positive_int(value, label)
    if number < 1:
        raise LsppValidationError(f"{label} must be positive")
    return number


def _vec_add(*vectors: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        sum(vector[0] for vector in vectors),
        sum(vector[1] for vector in vectors),
        sum(vector[2] for vector in vectors),
    )


def _vec_scale(vector: tuple[float, float, float], scale: float) -> tuple[float, float, float]:
    return (vector[0] * scale, vector[1] * scale, vector[2] * scale)


def _node_line(node_id: int, xyz: tuple[float, float, float]) -> str:
    return f"{node_id}, {_fmt(xyz[0])}, {_fmt(xyz[1])}, {_fmt(xyz[2])}, 0, 0"


def _z_centers(height: float, count: int, item_height: float, margin: float) -> list[float]:
    if count == 1:
        return [height / 2.0]
    usable = height - 2.0 * margin - item_height
    if usable < 0:
        raise LsppValidationError("z_margin and item height leave no room along shell height")
    step = usable / (count - 1)
    return [margin + item_height / 2.0 + index * step for index in range(count)]


def _shell_edge_summary(path: Path) -> dict[str, Any]:
    shell_edges: Counter[tuple[int, int]] = Counter()
    current = ""
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("*"):
            current = stripped.split()[0].upper().rstrip(",")
            continue
        if not current.startswith("*ELEMENT_SHELL"):
            continue
        values = _split_values(raw_line)
        if len(values) < 6:
            continue
        try:
            nids = [int(float(value)) for value in values[2:6] if int(float(value)) > 0]
        except ValueError:
            continue
        for first, second in zip(nids, nids[1:] + nids[:1]):
            shell_edges[tuple(sorted((first, second)))] += 1
    boundary = [edge for edge, count in shell_edges.items() if count == 1]
    nonmanifold = [edge for edge, count in shell_edges.items() if count > 2]
    return {
        "shell_edge_count": len(shell_edges),
        "boundary_edge_count": len(boundary),
        "nonmanifold_edge_count": len(nonmanifold),
        "boundary_edge_sample": boundary[:20],
        "nonmanifold_edge_sample": nonmanifold[:20],
    }


def _split_values(line: str) -> list[str]:
    text = line.strip()
    if not text or text.startswith("$"):
        return []
    if "," in text:
        return [part.strip() for part in text.split(",") if part.strip()]
    return [part for part in text.split() if part]


def _mass_summary(path: Path) -> dict[str, Any]:
    current = ""
    masses: list[float] = []
    node_ids: list[int] = []
    duplicate_ids: list[int] = []
    element_ids: set[int] = set()
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("*"):
            current = stripped.split()[0].upper().rstrip(",")
            continue
        if not current.startswith("*ELEMENT_MASS"):
            continue
        values = _split_values(raw_line)
        if len(values) < 3:
            continue
        try:
            eid = int(float(values[0]))
            node_id = int(float(values[1]))
            mass = float(values[2])
        except ValueError:
            continue
        if eid in element_ids:
            duplicate_ids.append(eid)
        element_ids.add(eid)
        node_ids.append(node_id)
        masses.append(mass)
    return {
        "mass_element_count": len(masses),
        "total_mass": sum(masses),
        "min_mass": min(masses) if masses else None,
        "max_mass": max(masses) if masses else None,
        "node_ids_sample": node_ids[:20],
        "duplicate_mass_element_count": len(duplicate_ids),
        "duplicate_mass_element_sample": duplicate_ids[:20],
    }


def _part_lines(title: str, part_id: int, section_id: int, material_id: int) -> list[str]:
    return [
        "*PART",
        title,
        "$#     pid     secid       mid     eosid      hgid      grav    adpopt      tmid",
        f"{part_id}, {section_id}, {material_id}, 0, 0, 0, 0, 0",
    ]


def _section_shell_lines(section_id: int, thickness: float) -> list[str]:
    return [
        "*SECTION_SHELL",
        "$#   secid    elform      shrf       nip     propt   qr/irid     icomp     setyp",
        f"{section_id}, 2, 0.833333, 5, 0, 0, 0, 0",
        "$#      t1        t2        t3        t4      nloc     marea      idof    edgset",
        f"{_fmt(thickness)}, {_fmt(thickness)}, {_fmt(thickness)}, {_fmt(thickness)}, 0, 0, 0, 0",
    ]


def _section_solid_lines(section_id: int) -> list[str]:
    return [
        "*SECTION_SOLID",
        "$#   secid    elform       aet",
        f"{section_id}, 1, 0",
    ]


def _make_quad_cap(
    add_node: Any,
    radius: float,
    ntheta: int,
    outer_nodes: list[int],
    z: float,
    is_top: bool,
    radial_layers: int,
    core_fraction: float,
) -> list[tuple[int, int, int, int]]:
    divisions = ntheta // 4
    half_side = radius * core_fraction
    step = 2.0 * half_side / divisions
    boundary_order = _square_grid_boundary_order(divisions)
    if len(boundary_order) != ntheta:
        raise LsppValidationError("Could not construct quad cap boundary")

    grid_xy = {
        (ix, iy): (-half_side + ix * step, -half_side + iy * step)
        for ix in range(divisions + 1)
        for iy in range(divisions + 1)
    }
    square_coords = [grid_xy[index] for index in boundary_order]
    transition_rings = [outer_nodes]
    for layer in range(1, radial_layers):
        alpha = layer / radial_layers
        ring: list[int] = []
        for i, (square_x, square_y) in enumerate(square_coords):
            theta = 2.0 * math.pi * i / ntheta
            circle_x = radius * math.cos(theta)
            circle_y = radius * math.sin(theta)
            ring.append(
                add_node(
                    (
                        circle_x * (1.0 - alpha) + square_x * alpha,
                        circle_y * (1.0 - alpha) + square_y * alpha,
                        z,
                    )
                )
            )
        transition_rings.append(ring)

    grid_ids: dict[tuple[int, int], int] = {}
    square_ring: list[int] = []
    for index in boundary_order:
        grid_ids[index] = add_node((*grid_xy[index], z))
        square_ring.append(grid_ids[index])
    transition_rings.append(square_ring)
    for ix in range(1, divisions):
        for iy in range(1, divisions):
            grid_ids[(ix, iy)] = add_node((*grid_xy[(ix, iy)], z))

    elements: list[tuple[int, int, int, int]] = []
    for outer_ring, inner_ring in zip(transition_rings, transition_rings[1:]):
        for i in range(ntheta):
            if is_top:
                elements.append((outer_ring[i], outer_ring[(i + 1) % ntheta], inner_ring[(i + 1) % ntheta], inner_ring[i]))
            else:
                elements.append((outer_ring[(i + 1) % ntheta], outer_ring[i], inner_ring[i], inner_ring[(i + 1) % ntheta]))
    for ix in range(divisions):
        for iy in range(divisions):
            lower_left = grid_ids[(ix, iy)]
            lower_right = grid_ids[(ix + 1, iy)]
            upper_right = grid_ids[(ix + 1, iy + 1)]
            upper_left = grid_ids[(ix, iy + 1)]
            if is_top:
                elements.append((lower_left, lower_right, upper_right, upper_left))
            else:
                elements.append((lower_right, lower_left, upper_left, upper_right))
    return elements


def _make_tri_cap(
    add_node: Any,
    ntheta: int,
    outer_nodes: list[int],
    z: float,
    is_top: bool,
) -> list[tuple[int, int, int, int]]:
    center = add_node((0.0, 0.0, z))
    elements: list[tuple[int, int, int, int]] = []
    for i in range(ntheta):
        if is_top:
            elements.append((outer_nodes[i], outer_nodes[(i + 1) % ntheta], center, 0))
        else:
            elements.append((outer_nodes[(i + 1) % ntheta], outer_nodes[i], center, 0))
    return elements


def check_lsdyna_cylindrical_assembly(
    k_path: str,
    shell_radius: float | None = None,
    shell_height: float | None = None,
    expect_closed_shell: bool = True,
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
        mesh = _mesh_summary(path)
        edges = _shell_edge_summary(path)
        masses = _mass_summary(path)
        precheck = precheck_lsdyna_keyword_model(str(path), config=cfg)
        issues: list[dict[str, Any]] = []
        for issue in mesh.get("issues", []):
            issues.append(issue)
        if expect_closed_shell and edges["boundary_edge_count"]:
            issues.append(
                {
                    "severity": "error",
                    "code": "shell_boundary_edges",
                    "count": edges["boundary_edge_count"],
                    "sample": edges["boundary_edge_sample"],
                }
            )
        if edges["nonmanifold_edge_count"]:
            issues.append(
                {
                    "severity": "error",
                    "code": "nonmanifold_shell_edges",
                    "count": edges["nonmanifold_edge_count"],
                    "sample": edges["nonmanifold_edge_sample"],
                }
            )
        if masses["duplicate_mass_element_count"]:
            issues.append(
                {
                    "severity": "error",
                    "code": "duplicate_mass_elements",
                    "count": masses["duplicate_mass_element_count"],
                    "sample": masses["duplicate_mass_element_sample"],
                }
            )
        bounds = mesh.get("bounds", {})
        if shell_radius is not None and bounds.get("max"):
            radius_value = _positive_float(shell_radius, "shell_radius")
            max_radial = max(
                abs(float(bounds["min"][0])),
                abs(float(bounds["min"][1])),
                abs(float(bounds["max"][0])),
                abs(float(bounds["max"][1])),
            )
            if max_radial < radius_value:
                issues.append(
                    {
                        "severity": "warning",
                        "code": "bounds_inside_expected_shell_radius",
                        "message": "Model radial bounds are smaller than the expected shell radius.",
                    }
                )
        if shell_height is not None and bounds.get("max"):
            height_value = _positive_float(shell_height, "shell_height")
            if float(bounds["max"][2]) < height_value:
                issues.append(
                    {
                        "severity": "warning",
                        "code": "bounds_below_expected_shell_height",
                        "message": "Model z bounds are smaller than the expected shell height.",
                    }
                )
        error_count = sum(1 for issue in issues if issue.get("severity") == "error")
        result = {
            "ok": True,
            "message": "Cylindrical assembly check completed.",
            "k_path": str(path),
            "ready_for_solver": bool(precheck.get("ready_for_solver") and error_count == 0),
            "issue_counts": {
                "error": error_count,
                "warning": sum(1 for issue in issues if issue.get("severity") == "warning"),
                "info": sum(1 for issue in issues if issue.get("severity") == "info"),
            },
            "mesh": mesh,
            "shell_edges": edges,
            "masses": masses,
            "issues": issues,
            "keyword": precheck.get("keyword", {}),
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
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        output = prepare_output(output_k, cfg, overwrite)
        radius_value = _positive_float(radius, "radius")
        height_value = _positive_float(height, "height")
        thickness_value = _positive_float(thickness, "thickness")
        elem_size_value = _positive_float(elem_size, "elem_size") if elem_size is not None else None
        ntheta = _circumference_division_count(radius_value, elem_size_value, n_circumference)
        nz_value = _division_count(height_value, elem_size_value, nz, "nz")
        cap_mesh_value = cap_mesh.strip().lower()
        if cap_mesh_value not in {"quad", "tri"}:
            raise LsppValidationError("cap_mesh must be 'quad' or 'tri'")
        cap_layers = _positive_divisions(cap_radial_layers, "cap_radial_layers")
        cap_core = _positive_float(cap_core_fraction, "cap_core_fraction")
        if cap_core >= 1.0 / math.sqrt(2.0):
            raise LsppValidationError("cap_core_fraction must be less than 0.707")
        if cap_mesh_value == "quad" and (cap_bottom or cap_top) and ntheta % 8 != 0:
            raise LsppValidationError("quad capped cylindrical assemblies require n_circumference divisible by 8")

        shell_pid = _require_positive_id(shell_part_id, "shell_part_id")
        shell_sid = _require_positive_id(shell_section_id, "shell_section_id")
        shell_mid = _require_positive_id(shell_material_id, "shell_material_id")
        termination = _positive_float(termination_time, "termination_time")
        dt = _positive_float(database_dt, "database_dt")
        attached_specs = attached_blocks or []
        mass_specs = mass_points or []

        lines = [
            "*KEYWORD",
            f"$# created by lspp-mcp-server: {title}",
        ]
        lines.extend(_database_cards(termination, dt))
        lines.extend(_part_lines("cylindrical_shell", shell_pid, shell_sid, shell_mid))
        lines.extend(_section_shell_lines(shell_sid, thickness_value))
        lines.extend(_material_elastic(shell_mid, shell_density, shell_young, shell_poisson))

        solid_sections: set[int] = set()
        solid_materials: set[int] = set()
        solid_parts: set[int] = set()
        for spec_index, spec in enumerate(attached_specs):
            sid = _require_positive_id(spec.get("section_id", 20 + spec_index), f"attached_blocks[{spec_index}].section_id")
            mid = _require_positive_id(spec.get("material_id", 20 + spec_index), f"attached_blocks[{spec_index}].material_id")
            pid = _require_positive_id(spec.get("part_id", 20 + spec_index), f"attached_blocks[{spec_index}].part_id")
            if sid not in solid_sections:
                lines.extend(_section_solid_lines(sid))
                solid_sections.add(sid)
            if mid not in solid_materials:
                lines.extend(
                    _material_elastic(
                        mid,
                        float(spec.get("density", 7.85e-9)),
                        float(spec.get("young", 210000.0)),
                        float(spec.get("poisson", 0.3)),
                    )
                )
                solid_materials.add(mid)
            if pid not in solid_parts:
                lines.extend(_part_lines(str(spec.get("title", f"attached_blocks_{spec_index + 1}")), pid, sid, mid))
                solid_parts.add(pid)

        nodes: list[tuple[int, tuple[float, float, float]]] = []
        shell_elements: list[tuple[int, int, int, int, int, int]] = []
        solid_elements: list[tuple[int, int, list[int]]] = []
        mass_nodes: list[tuple[int, tuple[float, float, float]]] = []
        mass_elements: list[tuple[int, int, float]] = []
        next_node_id = 1
        next_shell_eid = 1
        next_solid_eid = 100000
        next_mass_eid = 200000

        def add_node(xyz: tuple[float, float, float]) -> int:
            nonlocal next_node_id
            node_id = next_node_id
            next_node_id += 1
            nodes.append((node_id, xyz))
            return node_id

        dz = height_value / nz_value
        for k in range(nz_value + 1):
            z = k * dz
            for i in range(ntheta):
                theta = 2.0 * math.pi * i / ntheta
                add_node((radius_value * math.cos(theta), radius_value * math.sin(theta), z))
        cap_elements: list[tuple[int, int, int, int]] = []
        if cap_bottom:
            outer = [index + 1 for index in range(ntheta)]
            if cap_mesh_value == "quad":
                cap_elements.extend(_make_quad_cap(add_node, radius_value, ntheta, outer, 0.0, False, cap_layers, cap_core))
            else:
                cap_elements.extend(_make_tri_cap(add_node, ntheta, outer, 0.0, False))
        if cap_top:
            outer = [nz_value * ntheta + index + 1 for index in range(ntheta)]
            if cap_mesh_value == "quad":
                cap_elements.extend(_make_quad_cap(add_node, radius_value, ntheta, outer, height_value, True, cap_layers, cap_core))
            else:
                cap_elements.extend(_make_tri_cap(add_node, ntheta, outer, height_value, True))

        for k in range(nz_value):
            for i in range(ntheta):
                n1 = k * ntheta + i + 1
                n2 = k * ntheta + ((i + 1) % ntheta) + 1
                n3 = (k + 1) * ntheta + ((i + 1) % ntheta) + 1
                n4 = (k + 1) * ntheta + i + 1
                shell_elements.append((next_shell_eid, shell_pid, n1, n2, n3, n4))
                next_shell_eid += 1
        for n1, n2, n3, n4 in cap_elements:
            shell_elements.append((next_shell_eid, shell_pid, n1, n2, n3, n4))
            next_shell_eid += 1

        for spec_index, spec in enumerate(attached_specs):
            pid = _require_positive_id(spec.get("part_id", 20 + spec_index), f"attached_blocks[{spec_index}].part_id")
            count_theta = _positive_divisions(spec.get("count_circumference", 1), f"attached_blocks[{spec_index}].count_circumference")
            count_z = _positive_divisions(spec.get("count_height", 1), f"attached_blocks[{spec_index}].count_height")
            radial_thickness = _positive_float(spec.get("radial_thickness"), f"attached_blocks[{spec_index}].radial_thickness")
            circum_width = _positive_float(spec.get("circumferential_width"), f"attached_blocks[{spec_index}].circumferential_width")
            block_height = _positive_float(spec.get("height"), f"attached_blocks[{spec_index}].height")
            radial_gap = float(spec.get("radial_gap", 0.0))
            start_angle = math.radians(float(spec.get("start_angle_deg", 0.0)))
            z_margin = float(spec.get("z_margin", 0.0))
            centers_z = _z_centers(height_value, count_z, block_height, z_margin)
            for iz, z_center in enumerate(centers_z):
                for itheta in range(count_theta):
                    theta = start_angle + 2.0 * math.pi * itheta / count_theta
                    radial = (math.cos(theta), math.sin(theta), 0.0)
                    tangent = (-math.sin(theta), math.cos(theta), 0.0)
                    r_inner = radius_value + radial_gap
                    r_outer = r_inner + radial_thickness
                    z_low = z_center - block_height / 2.0
                    z_high = z_center + block_height / 2.0
                    corner_ids: list[int] = []
                    for z_value in [z_low, z_high]:
                        for r_value, s_value in [
                            (r_inner, -circum_width / 2.0),
                            (r_outer, -circum_width / 2.0),
                            (r_outer, circum_width / 2.0),
                            (r_inner, circum_width / 2.0),
                        ]:
                            xyz = _vec_add(_vec_scale(radial, r_value), _vec_scale(tangent, s_value), (0.0, 0.0, z_value))
                            corner_ids.append(add_node(xyz))
                    solid_elements.append((next_solid_eid, pid, corner_ids))
                    next_solid_eid += 1

        for spec_index, spec in enumerate(mass_specs):
            count_theta = _positive_divisions(spec.get("count_circumference", 1), f"mass_points[{spec_index}].count_circumference")
            count_z = _positive_divisions(spec.get("count_height", 1), f"mass_points[{spec_index}].count_height")
            mass = _positive_float(spec.get("mass"), f"mass_points[{spec_index}].mass")
            radial_offset = float(spec.get("radial_offset", 0.0))
            start_angle = math.radians(float(spec.get("start_angle_deg", 0.0)))
            z_margin = float(spec.get("z_margin", 0.0))
            centers_z = _z_centers(height_value, count_z, 0.0, z_margin)
            for z_center in centers_z:
                for itheta in range(count_theta):
                    theta = start_angle + 2.0 * math.pi * itheta / count_theta
                    xyz = ((radius_value + radial_offset) * math.cos(theta), (radius_value + radial_offset) * math.sin(theta), z_center)
                    node_id = add_node(xyz)
                    mass_nodes.append((node_id, xyz))
                    mass_elements.append((next_mass_eid, node_id, mass))
                    next_mass_eid += 1

        lines.extend(["*NODE", "$#   nid               x               y               z      tc      rc"])
        for node_id, xyz in nodes:
            lines.append(_node_line(node_id, xyz))
        lines.extend(["*ELEMENT_SHELL", "$#   eid     pid      n1      n2      n3      n4"])
        for element in shell_elements:
            lines.append(", ".join(str(value) for value in element))
        if solid_elements:
            lines.extend(["*ELEMENT_SOLID", "$#   eid     pid      n1      n2      n3      n4      n5      n6      n7      n8"])
            for eid, pid, node_ids in solid_elements:
                lines.append(", ".join(str(value) for value in [eid, pid, *node_ids]))
        if mass_elements:
            lines.extend(["*ELEMENT_MASS", "$#   eid     nid      mass"])
            for eid, node_id, mass in mass_elements:
                lines.append(f"{eid}, {node_id}, {_fmt(mass)}")

        fill_block = ""
        if internal_fill:
            fill_config = dict(internal_fill)
            fills = fill_config.get("fills")
            if fills is None:
                fill_radius = float(fill_config.get("radius", max(radius_value - thickness_value, radius_value * 0.95)))
                z0 = float(fill_config.get("z0", 0.0))
                z1 = float(fill_config.get("z1", height_value))
                fills = [
                    {
                        "geometry": "cylinder",
                        "fillopt": int(fill_config.get("fillopt", 0)),
                        "fammg": fill_config.get("fammg", 1),
                        "point0": [0.0, 0.0, z0],
                        "point1": [0.0, 0.0, z1],
                        "radius": fill_radius,
                    }
                ]
            fill_block = render_initial_volume_fraction_geometry(
                fmsid=int(fill_config.get("fmsid", 1)),
                fmidtyp=int(fill_config.get("fmidtyp", 1)),
                bammg=fill_config.get("bammg", 0),
                ntrace=int(fill_config.get("ntrace", 3)),
                fills=fills,
                comments=bool(fill_config.get("comments", True)),
            ).rstrip("\n")
            lines.append(fill_block)
        lines.append("*END")
        _write_keyword(output, lines)

        assembly_check = check_lsdyna_cylindrical_assembly(
            str(output),
            shell_radius=radius_value,
            shell_height=height_value,
            expect_closed_shell=bool(cap_bottom and cap_top),
            output_json=check_json,
            overwrite=overwrite,
            config=cfg,
        )
        return {
            "ok": True,
            "message": "Cylindrical assembly keyword file generated.",
            "output_k": str(output),
            "assembly": {
                "radius": radius_value,
                "height": height_value,
                "thickness": thickness_value,
                "n_circumference": ntheta,
                "nz": nz_value,
                "cap_bottom": cap_bottom,
                "cap_top": cap_top,
                "cap_mesh": cap_mesh_value,
                "shell_element_count": len(shell_elements),
                "solid_element_count": len(solid_elements),
                "mass_element_count": len(mass_elements),
                "node_count": len(nodes),
                "internal_fill": bool(internal_fill),
            },
            "check": assembly_check,
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["output_k"] = str(output_k)
        return result
