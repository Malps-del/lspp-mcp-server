"""Controlled LS-DYNA preprocessing helpers."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from ..config import LsppConfig
from ..runner import check_required_output
from ..templates import create_run_dir, write_generated_cfile
from ..validators import (
    LsppValidationError,
    ensure_input_file,
    output_file_check,
    positive_int,
    safe_cfile_string,
    validate_window_size,
)
from ._common import (
    get_config,
    prepare_output,
    quote_path,
    result_from_validation_error,
)
from .keyword import check_keyword_deck, inspect_keyword_deck


SUPPORTED_PREVIEW_FORMATS = {
    "png": "png",
    "jpg": "jpg",
    "jpeg": "jpg",
    "bmp": "bmp",
    "gif": "gif",
    "wrl": "vrml",
}

VIEW_COMMANDS = {
    "isometric": "isometric x",
    "iso": "isometric x",
    "front": "front",
    "back": "back",
    "top": "top",
    "bottom": "bottom",
    "left": "left",
    "right": "right",
}


def _positive_float(value: float | int | str, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise LsppValidationError(f"{label} must be a positive number") from exc
    if not math.isfinite(number) or number <= 0:
        raise LsppValidationError(f"{label} must be a positive number")
    return number


def _positive_divisions(value: int | None, label: str) -> int:
    if value is None:
        raise LsppValidationError(f"{label} is required")
    number = positive_int(value, label)
    if number < 1:
        raise LsppValidationError(f"{label} must be at least 1")
    return number


def _division_count(length: float, elem_size: float | None, count: int | None, label: str) -> int:
    if count is not None:
        return _positive_divisions(count, label)
    if elem_size is None:
        raise LsppValidationError(f"Either elem_size or {label} is required")
    return max(1, int(math.ceil(length / elem_size)))


def _circumference_division_count(
    radius: float,
    elem_size: float | None,
    count: int | None,
) -> int:
    if count is not None:
        number = _positive_divisions(count, "n_circumference")
    elif elem_size is not None:
        number = int(math.ceil(2.0 * math.pi * radius / elem_size))
    else:
        raise LsppValidationError("Either elem_size or n_circumference is required")
    if number < 3:
        raise LsppValidationError("n_circumference must be at least 3")
    return number


def _fmt(value: float) -> str:
    return f"{value:.10g}"


def _keyword_header(title: str) -> list[str]:
    return [
        "*KEYWORD",
        f"$# created by lspp-mcp-server: {title}",
    ]


def _material_elastic(mid: int, density: float, young: float, poisson: float) -> list[str]:
    return [
        "*MAT_ELASTIC_TITLE",
        "generated_elastic",
        "$#     mid        ro         e        pr        da        db         k",
        f"{mid}, {_fmt(density)}, {_fmt(young)}, {_fmt(poisson)}, 0, 0, 0",
    ]


def _database_cards(termination_time: float, database_dt: float) -> list[str]:
    return [
        "*CONTROL_TERMINATION",
        "$#  endtim    endcyc     dtmin    endeng    endmas     nosol",
        f"{_fmt(termination_time)}, 0, 0, 0, 0, 0",
        "*CONTROL_TIMESTEP",
        "$#  dtinit    tssfac      isdo    tslimt     dt2ms     lctm     erode    ms1st",
        "0, 0.9, 0, 0, 0, 0, 0, 0",
        "*DATABASE_BINARY_D3PLOT",
        "$#      dt      lcdt      beam     npltc     psetid",
        f"{_fmt(database_dt)}, 0, 0, 0, 0",
        "*DATABASE_GLSTAT",
        f"{_fmt(database_dt)}",
        "*DATABASE_MATSUM",
        f"{_fmt(database_dt)}",
        "*DATABASE_EXTENT_BINARY",
        "$#   neiph     neips    maxint    strflg    sigflg    epsflg    rltflg    engflg",
        "0, 0, 3, 1, 1, 1, 1, 1",
    ]


def _write_keyword(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _edge_node_set(nx: int, ny: int) -> list[int]:
    ids: list[int] = []
    for j in range(ny + 1):
        for i in range(nx + 1):
            if i in {0, nx} or j in {0, ny}:
                ids.append(j * (nx + 1) + i + 1)
    return ids


def _node_set_lines(set_id: int, title: str, node_ids: list[int]) -> list[str]:
    lines = ["*SET_NODE_LIST_TITLE", title, f"{set_id}"]
    for index in range(0, len(node_ids), 8):
        lines.append(", ".join(str(node_id) for node_id in node_ids[index : index + 8]))
    return lines


def _cylinder_ring_node_set(n_circumference: int, axial_index: int) -> list[int]:
    return [
        axial_index * n_circumference + circumferential_index + 1
        for circumferential_index in range(n_circumference)
    ]


def _square_grid_boundary_order(divisions: int) -> list[tuple[int, int]]:
    points = [
        (ix, iy)
        for ix in range(divisions + 1)
        for iy in range(divisions + 1)
        if ix in {0, divisions} or iy in {0, divisions}
    ]
    center = divisions / 2.0

    def angle(point: tuple[int, int]) -> float:
        x = point[0] - center
        y = point[1] - center
        value = math.atan2(y, x)
        return value if value >= 0 else value + 2.0 * math.pi

    return sorted(points, key=angle)


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
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        output = prepare_output(output_k, cfg, overwrite)
        length_value = _positive_float(length, "length")
        width_value = _positive_float(width, "width")
        thickness_value = _positive_float(thickness, "thickness")
        elem_size_value = _positive_float(elem_size, "elem_size") if elem_size is not None else None
        nx_value = _division_count(length_value, elem_size_value, nx, "nx")
        ny_value = _division_count(width_value, elem_size_value, ny, "ny")
        pid = positive_int(part_id, "part_id")
        sid = positive_int(section_id, "section_id")
        mid = positive_int(material_id, "material_id")
        if min(pid, sid, mid) < 1:
            raise LsppValidationError("part_id, section_id, and material_id must be positive")
        termination = _positive_float(termination_time, "termination_time")
        dt = _positive_float(database_dt, "database_dt")
        dx = length_value / nx_value
        dy = width_value / ny_value

        lines = _keyword_header(title)
        lines.extend(_database_cards(termination, dt))
        lines.extend(
            [
                "*PART",
                title,
                "$#     pid     secid       mid     eosid      hgid      grav    adpopt      tmid",
                f"{pid}, {sid}, {mid}, 0, 0, 0, 0, 0",
                "*SECTION_SHELL",
                "$#   secid    elform      shrf       nip     propt   qr/irid     icomp     setyp",
                f"{sid}, 2, 0.833333, 5, 0, 0, 0, 0",
                "$#      t1        t2        t3        t4      nloc     marea      idof    edgset",
                f"{_fmt(thickness_value)}, {_fmt(thickness_value)}, {_fmt(thickness_value)}, {_fmt(thickness_value)}, 0, 0, 0, 0",
            ]
        )
        lines.extend(_material_elastic(mid, density, young, poisson))
        lines.extend(["*NODE", "$#   nid               x               y               z      tc      rc"])
        for j in range(ny_value + 1):
            y = j * dy
            for i in range(nx_value + 1):
                node_id = j * (nx_value + 1) + i + 1
                x = i * dx
                lines.append(f"{node_id}, {_fmt(x)}, {_fmt(y)}, 0, 0, 0")
        lines.extend(["*ELEMENT_SHELL", "$#   eid     pid      n1      n2      n3      n4"])
        elem_id = 1
        for j in range(ny_value):
            for i in range(nx_value):
                n1 = j * (nx_value + 1) + i + 1
                n2 = n1 + 1
                n3 = n2 + nx_value + 1
                n4 = n1 + nx_value + 1
                lines.append(f"{elem_id}, {pid}, {n1}, {n2}, {n3}, {n4}")
                elem_id += 1
        if fixed_edges:
            lines.extend(_node_set_lines(boundary_set_id, "fixed_plate_edges", _edge_node_set(nx_value, ny_value)))
            lines.extend(
                [
                    "*BOUNDARY_SPC_SET",
                    "$#     nsid       cid      dofx      dofy      dofz     dofrx     dofry     dofrz",
                    f"{boundary_set_id}, 0, 1, 1, 1, 1, 1, 1",
                ]
            )
        lines.append("*END")
        _write_keyword(output, lines)
        precheck = precheck_lsdyna_keyword_model(
            str(output),
            output_json=precheck_json,
            overwrite=overwrite,
            config=cfg,
        )
        return {
            "ok": True,
            "message": "Plate shell mesh keyword file generated.",
            "output_k": str(output),
            "mesh": {
                "type": "shell_plate",
                "length": length_value,
                "width": width_value,
                "thickness": thickness_value,
                "nx": nx_value,
                "ny": ny_value,
                "node_count": (nx_value + 1) * (ny_value + 1),
                "element_count": nx_value * ny_value,
                "fixed_edges": fixed_edges,
            },
            "precheck": precheck,
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["output_k"] = str(output_k)
        return result


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
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        output = prepare_output(output_k, cfg, overwrite)
        length_value = _positive_float(length, "length")
        width_value = _positive_float(width, "width")
        height_value = _positive_float(height, "height")
        elem_size_value = _positive_float(elem_size, "elem_size") if elem_size is not None else None
        nx_value = _division_count(length_value, elem_size_value, nx, "nx")
        ny_value = _division_count(width_value, elem_size_value, ny, "ny")
        nz_value = _division_count(height_value, elem_size_value, nz, "nz")
        pid = positive_int(part_id, "part_id")
        sid = positive_int(section_id, "section_id")
        mid = positive_int(material_id, "material_id")
        if min(pid, sid, mid) < 1:
            raise LsppValidationError("part_id, section_id, and material_id must be positive")
        termination = _positive_float(termination_time, "termination_time")
        dt = _positive_float(database_dt, "database_dt")
        dx = length_value / nx_value
        dy = width_value / ny_value
        dz = height_value / nz_value

        def node_id(i: int, j: int, k: int) -> int:
            return k * (ny_value + 1) * (nx_value + 1) + j * (nx_value + 1) + i + 1

        lines = _keyword_header(title)
        lines.extend(_database_cards(termination, dt))
        lines.extend(
            [
                "*PART",
                title,
                "$#     pid     secid       mid     eosid      hgid      grav    adpopt      tmid",
                f"{pid}, {sid}, {mid}, 0, 0, 0, 0, 0",
                "*SECTION_SOLID",
                "$#   secid    elform       aet",
                f"{sid}, 1, 0",
            ]
        )
        lines.extend(_material_elastic(mid, density, young, poisson))
        lines.extend(["*NODE", "$#   nid               x               y               z      tc      rc"])
        for k in range(nz_value + 1):
            for j in range(ny_value + 1):
                for i in range(nx_value + 1):
                    lines.append(
                        f"{node_id(i, j, k)}, {_fmt(i * dx)}, {_fmt(j * dy)}, {_fmt(k * dz)}, 0, 0"
                    )
        lines.extend(["*ELEMENT_SOLID", "$#   eid     pid      n1      n2      n3      n4      n5      n6      n7      n8"])
        elem_id = 1
        for k in range(nz_value):
            for j in range(ny_value):
                for i in range(nx_value):
                    n1 = node_id(i, j, k)
                    n2 = node_id(i + 1, j, k)
                    n3 = node_id(i + 1, j + 1, k)
                    n4 = node_id(i, j + 1, k)
                    n5 = node_id(i, j, k + 1)
                    n6 = node_id(i + 1, j, k + 1)
                    n7 = node_id(i + 1, j + 1, k + 1)
                    n8 = node_id(i, j + 1, k + 1)
                    lines.append(f"{elem_id}, {pid}, {n1}, {n2}, {n3}, {n4}, {n5}, {n6}, {n7}, {n8}")
                    elem_id += 1
        lines.append("*END")
        _write_keyword(output, lines)
        precheck = precheck_lsdyna_keyword_model(
            str(output),
            output_json=precheck_json,
            overwrite=overwrite,
            config=cfg,
        )
        return {
            "ok": True,
            "message": "Block solid mesh keyword file generated.",
            "output_k": str(output),
            "mesh": {
                "type": "solid_block",
                "length": length_value,
                "width": width_value,
                "height": height_value,
                "nx": nx_value,
                "ny": ny_value,
                "nz": nz_value,
                "node_count": (nx_value + 1) * (ny_value + 1) * (nz_value + 1),
                "element_count": nx_value * ny_value * nz_value,
            },
            "precheck": precheck,
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["output_k"] = str(output_k)
        return result


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
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        output = prepare_output(output_k, cfg, overwrite)
        radius_value = _positive_float(radius, "radius")
        height_value = _positive_float(height, "height")
        thickness_value = _positive_float(thickness, "thickness")
        elem_size_value = _positive_float(elem_size, "elem_size") if elem_size is not None else None
        ntheta_value = _circumference_division_count(
            radius_value,
            elem_size_value,
            n_circumference,
        )
        nz_value = _division_count(height_value, elem_size_value, nz, "nz")
        cap_mesh_value = cap_mesh.strip().lower()
        if cap_mesh_value not in {"quad", "tri"}:
            raise LsppValidationError("cap_mesh must be 'quad' or 'tri'")
        cap_layers_value = _positive_divisions(cap_radial_layers, "cap_radial_layers")
        cap_core_value = _positive_float(cap_core_fraction, "cap_core_fraction")
        if cap_core_value >= 1.0 / math.sqrt(2.0):
            raise LsppValidationError("cap_core_fraction must be less than 0.707")
        if cap_mesh_value == "quad" and (cap_bottom or cap_top):
            if ntheta_value % 8 != 0:
                raise LsppValidationError(
                    "quad capped cylinder shells require n_circumference to be divisible by 8"
                )
        pid = positive_int(part_id, "part_id")
        sid = positive_int(section_id, "section_id")
        mid = positive_int(material_id, "material_id")
        if min(pid, sid, mid) < 1:
            raise LsppValidationError("part_id, section_id, and material_id must be positive")
        termination = _positive_float(termination_time, "termination_time")
        dt = _positive_float(database_dt, "database_dt")
        dz = height_value / nz_value
        next_node_id = ntheta_value * (nz_value + 1) + 1

        lines = _keyword_header(title)
        lines.extend(_database_cards(termination, dt))
        lines.extend(
            [
                "*PART",
                title,
                "$#     pid     secid       mid     eosid      hgid      grav    adpopt      tmid",
                f"{pid}, {sid}, {mid}, 0, 0, 0, 0, 0",
                "*SECTION_SHELL",
                "$#   secid    elform      shrf       nip     propt   qr/irid     icomp     setyp",
                f"{sid}, 2, 0.833333, 5, 0, 0, 0, 0",
                "$#      t1        t2        t3        t4      nloc     marea      idof    edgset",
                f"{_fmt(thickness_value)}, {_fmt(thickness_value)}, {_fmt(thickness_value)}, {_fmt(thickness_value)}, 0, 0, 0, 0",
            ]
        )
        lines.extend(_material_elastic(mid, density, young, poisson))
        lines.extend(["*NODE", "$#   nid               x               y               z      tc      rc"])
        for k in range(nz_value + 1):
            z = k * dz
            for i in range(ntheta_value):
                theta = 2.0 * math.pi * i / ntheta_value
                node_id = k * ntheta_value + i + 1
                x = radius_value * math.cos(theta)
                y = radius_value * math.sin(theta)
                lines.append(f"{node_id}, {_fmt(x)}, {_fmt(y)}, {_fmt(z)}, 0, 0")

        def add_node(x: float, y: float, z: float) -> int:
            nonlocal next_node_id
            node_id = next_node_id
            next_node_id += 1
            lines.append(f"{node_id}, {_fmt(x)}, {_fmt(y)}, {_fmt(z)}, 0, 0")
            return node_id

        cap_elements: list[tuple[int, int, int, int]] = []

        def add_cap(z: float, outer_nodes: list[int], is_top: bool) -> None:
            if cap_mesh_value == "tri":
                center = add_node(0.0, 0.0, z)
                for i in range(ntheta_value):
                    if is_top:
                        cap_elements.append(
                            (
                                outer_nodes[i],
                                outer_nodes[(i + 1) % ntheta_value],
                                center,
                                0,
                            )
                        )
                    else:
                        cap_elements.append(
                            (
                                outer_nodes[(i + 1) % ntheta_value],
                                outer_nodes[i],
                                center,
                                0,
                            )
                        )
                return

            divisions = ntheta_value // 4
            half_side = radius_value * cap_core_value
            step = 2.0 * half_side / divisions
            boundary_order = _square_grid_boundary_order(divisions)
            if len(boundary_order) != ntheta_value:
                raise LsppValidationError("Could not construct quad cap boundary")
            grid_xy = {
                (ix, iy): (-half_side + ix * step, -half_side + iy * step)
                for ix in range(divisions + 1)
                for iy in range(divisions + 1)
            }
            grid_ids: dict[tuple[int, int], int] = {}
            square_ring: list[int] = []
            square_coords = [grid_xy[index] for index in boundary_order]

            transition_rings = [outer_nodes]
            for layer in range(1, cap_layers_value):
                alpha = layer / cap_layers_value
                ring: list[int] = []
                for i, (square_x, square_y) in enumerate(square_coords):
                    theta = 2.0 * math.pi * i / ntheta_value
                    circle_x = radius_value * math.cos(theta)
                    circle_y = radius_value * math.sin(theta)
                    ring.append(
                        add_node(
                            circle_x * (1.0 - alpha) + square_x * alpha,
                            circle_y * (1.0 - alpha) + square_y * alpha,
                            z,
                        )
                    )
                transition_rings.append(ring)

            for index in boundary_order:
                node_id = add_node(*grid_xy[index], z)
                grid_ids[index] = node_id
                square_ring.append(node_id)
            transition_rings.append(square_ring)

            for ix in range(1, divisions):
                for iy in range(1, divisions):
                    grid_ids[(ix, iy)] = add_node(*grid_xy[(ix, iy)], z)

            for outer_ring, inner_ring in zip(transition_rings, transition_rings[1:]):
                for i in range(ntheta_value):
                    if is_top:
                        cap_elements.append(
                            (
                                outer_ring[i],
                                outer_ring[(i + 1) % ntheta_value],
                                inner_ring[(i + 1) % ntheta_value],
                                inner_ring[i],
                            )
                        )
                    else:
                        cap_elements.append(
                            (
                                outer_ring[(i + 1) % ntheta_value],
                                outer_ring[i],
                                inner_ring[i],
                                inner_ring[(i + 1) % ntheta_value],
                            )
                        )

            for ix in range(divisions):
                for iy in range(divisions):
                    lower_left = grid_ids[(ix, iy)]
                    lower_right = grid_ids[(ix + 1, iy)]
                    upper_right = grid_ids[(ix + 1, iy + 1)]
                    upper_left = grid_ids[(ix, iy + 1)]
                    if is_top:
                        cap_elements.append((lower_left, lower_right, upper_right, upper_left))
                    else:
                        cap_elements.append((lower_right, lower_left, upper_left, upper_right))

        if cap_bottom:
            add_cap(
                z=0.0,
                outer_nodes=[index + 1 for index in range(ntheta_value)],
                is_top=False,
            )
        if cap_top:
            top_start = nz_value * ntheta_value
            add_cap(
                z=height_value,
                outer_nodes=[top_start + index + 1 for index in range(ntheta_value)],
                is_top=True,
            )
        lines.extend(["*ELEMENT_SHELL", "$#   eid     pid      n1      n2      n3      n4"])
        elem_id = 1
        for k in range(nz_value):
            for i in range(ntheta_value):
                n1 = k * ntheta_value + i + 1
                n2 = k * ntheta_value + ((i + 1) % ntheta_value) + 1
                n3 = (k + 1) * ntheta_value + ((i + 1) % ntheta_value) + 1
                n4 = (k + 1) * ntheta_value + i + 1
                lines.append(f"{elem_id}, {pid}, {n1}, {n2}, {n3}, {n4}")
                elem_id += 1
        for n1, n2, n3, n4 in cap_elements:
            lines.append(f"{elem_id}, {pid}, {n1}, {n2}, {n3}, {n4}")
            elem_id += 1
        if fixed_bottom:
            lines.extend(
                _node_set_lines(
                    bottom_set_id,
                    "fixed_cylinder_bottom",
                    _cylinder_ring_node_set(ntheta_value, 0),
                )
            )
            lines.extend(
                [
                    "*BOUNDARY_SPC_SET",
                    "$#     nsid       cid      dofx      dofy      dofz     dofrx     dofry     dofrz",
                    f"{bottom_set_id}, 0, 1, 1, 1, 1, 1, 1",
                ]
            )
        if fixed_top:
            lines.extend(
                _node_set_lines(
                    top_set_id,
                    "fixed_cylinder_top",
                    _cylinder_ring_node_set(ntheta_value, nz_value),
                )
            )
            lines.extend(
                [
                    "*BOUNDARY_SPC_SET",
                    "$#     nsid       cid      dofx      dofy      dofz     dofrx     dofry     dofrz",
                    f"{top_set_id}, 0, 1, 1, 1, 1, 1, 1",
                ]
            )
        lines.append("*END")
        _write_keyword(output, lines)
        precheck = precheck_lsdyna_keyword_model(
            str(output),
            output_json=precheck_json,
            overwrite=overwrite,
            config=cfg,
        )
        return {
            "ok": True,
            "message": "Cylinder shell mesh keyword file generated.",
            "output_k": str(output),
            "mesh": {
                "type": "cylinder_shell",
                "radius": radius_value,
                "height": height_value,
                "thickness": thickness_value,
                "n_circumference": ntheta_value,
                "nz": nz_value,
                "node_count": next_node_id - 1,
                "element_count": ntheta_value * nz_value + len(cap_elements),
                "cap_bottom": cap_bottom,
                "cap_top": cap_top,
                "cap_mesh": cap_mesh_value,
                "cap_radial_layers": cap_layers_value if cap_mesh_value == "quad" else None,
                "cap_core_fraction": cap_core_value if cap_mesh_value == "quad" else None,
                "fixed_bottom": fixed_bottom,
                "fixed_top": fixed_top,
            },
            "precheck": precheck,
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["output_k"] = str(output_k)
        return result


def _parse_numeric_fields(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("$"):
        return []
    if "," in stripped:
        return [part.strip() for part in stripped.split(",") if part.strip()]
    return [part for part in stripped.split() if part]


def _mesh_summary(path: Path) -> dict[str, Any]:
    nodes: dict[int, tuple[float, float, float]] = {}
    shell_elements: dict[int, tuple[int, list[int]]] = {}
    solid_elements: dict[int, tuple[int, list[int]]] = {}
    duplicate_nodes: list[int] = []
    duplicate_elements: list[int] = []
    current = ""
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("*"):
            current = stripped.split()[0].upper().rstrip(",")
            continue
        values = _parse_numeric_fields(raw_line)
        if not values:
            continue
        try:
            if current == "*NODE" and len(values) >= 4:
                nid = int(float(values[0]))
                xyz = (float(values[1]), float(values[2]), float(values[3]))
                if nid in nodes:
                    duplicate_nodes.append(nid)
                nodes[nid] = xyz
            elif current.startswith("*ELEMENT_SHELL") and len(values) >= 6:
                eid = int(float(values[0]))
                pid = int(float(values[1]))
                nids = [int(float(value)) for value in values[2:6]]
                if eid in shell_elements or eid in solid_elements:
                    duplicate_elements.append(eid)
                shell_elements[eid] = (pid, nids)
            elif current.startswith("*ELEMENT_SOLID") and len(values) >= 10:
                eid = int(float(values[0]))
                pid = int(float(values[1]))
                nids = [int(float(value)) for value in values[2:10]]
                if eid in shell_elements or eid in solid_elements:
                    duplicate_elements.append(eid)
                solid_elements[eid] = (pid, nids)
        except ValueError:
            continue

    referenced = [
        node_id
        for _pid, nids in list(shell_elements.values()) + list(solid_elements.values())
        for node_id in nids
        if node_id > 0
    ]
    referenced_set = set(referenced)
    missing_references = sorted(node_id for node_id in referenced_set if node_id not in nodes)
    unused_nodes = sorted(node_id for node_id in nodes if node_id not in referenced_set)
    degenerate_shells = []
    for eid, (_pid, nids) in shell_elements.items():
        positive_nids = [node_id for node_id in nids if node_id > 0]
        unique_nids = set(positive_nids)
        if len(unique_nids) < 3:
            degenerate_shells.append(eid)
        elif len(positive_nids) == 4 and len(unique_nids) < 4:
            degenerate_shells.append(eid)
    degenerate_shells = sorted(degenerate_shells)
    degenerate_solids = sorted(
        eid for eid, (_pid, nids) in solid_elements.items() if len(set(nids)) < 8
    )
    part_counts = Counter(
        [pid for pid, _nids in shell_elements.values()]
        + [pid for pid, _nids in solid_elements.values()]
    )
    if nodes:
        xs = [xyz[0] for xyz in nodes.values()]
        ys = [xyz[1] for xyz in nodes.values()]
        zs = [xyz[2] for xyz in nodes.values()]
        bounds = {
            "min": [min(xs), min(ys), min(zs)],
            "max": [max(xs), max(ys), max(zs)],
        }
    else:
        bounds = {"min": [], "max": []}
    issues: list[dict[str, Any]] = []
    for code, values, severity in [
        ("duplicate_nodes", duplicate_nodes, "error"),
        ("duplicate_elements", duplicate_elements, "error"),
        ("missing_node_references", missing_references, "error"),
        ("degenerate_shell_elements", degenerate_shells, "error"),
        ("degenerate_solid_elements", degenerate_solids, "error"),
        ("unused_nodes", unused_nodes, "info"),
    ]:
        if values:
            issues.append(
                {
                    "severity": severity,
                    "code": code,
                    "count": len(values),
                    "sample": values[:20],
                }
            )
    return {
        "node_count": len(nodes),
        "shell_element_count": len(shell_elements),
        "solid_element_count": len(solid_elements),
        "element_count": len(shell_elements) + len(solid_elements),
        "part_element_counts": dict(sorted(part_counts.items())),
        "bounds": bounds,
        "duplicate_node_count": len(duplicate_nodes),
        "duplicate_element_count": len(duplicate_elements),
        "missing_node_reference_count": len(missing_references),
        "unused_node_count": len(unused_nodes),
        "degenerate_shell_count": len(degenerate_shells),
        "degenerate_solid_count": len(degenerate_solids),
        "issues": issues,
    }


def precheck_lsdyna_keyword_model(
    k_path: str,
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
        keyword_summary = inspect_keyword_deck(str(path), config=cfg)
        keyword_check = check_keyword_deck(str(path), config=cfg)
        mesh_error_count = sum(1 for issue in mesh["issues"] if issue["severity"] == "error")
        ready = bool(
            keyword_check.get("ok")
            and keyword_check.get("ready_for_solver")
            and mesh_error_count == 0
        )
        result = {
            "ok": True,
            "message": "Keyword model precheck completed.",
            "k_path": str(path),
            "ready_for_solver": ready,
            "mesh": mesh,
            "keyword": {
                "keyword_count": keyword_summary.get("keyword_count"),
                "groups": keyword_summary.get("groups", {}),
                "database_outputs": keyword_summary.get("database_outputs", {}),
                "issue_counts": keyword_check.get("issue_counts", {}),
                "issues": keyword_check.get("issues", []),
            },
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


def _preview_format(output_path: Path, image_format: str | None) -> tuple[str, str]:
    requested = (image_format or output_path.suffix.lstrip(".") or "png").lower()
    if requested not in SUPPORTED_PREVIEW_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_PREVIEW_FORMATS))
        raise LsppValidationError(f"image_format must be one of: {supported}")
    extension = output_path.suffix.lstrip(".").lower()
    normalized = "jpg" if requested == "jpeg" else requested
    if extension and extension != normalized:
        raise LsppValidationError(
            f"Output extension .{extension} does not match image_format {normalized}"
        )
    return normalized, SUPPORTED_PREVIEW_FORMATS[requested]


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
    config: LsppConfig | None = None,
) -> dict[str, Any]:
    cfg = get_config(config)
    try:
        keyword = ensure_input_file(
            k_path,
            cfg.workspace_root,
            cfg.resolved_allowed_roots(),
            label="keyword file",
        )
        output = prepare_output(output_image, cfg, overwrite)
        validate_window_size(window_size)
        normalized_format, print_format = _preview_format(output, image_format)
        view_key = view.strip().lower()
        if view_key not in VIEW_COMMANDS:
            raise LsppValidationError(
                f"view must be one of: {', '.join(sorted(VIEW_COMMANDS))}"
            )
        background_rgb = {
            "white": "1 1 1",
            "black": "0 0 0",
            "gray": "0.5 0.5 0.5",
            "grey": "0.5 0.5 0.5",
        }.get(background.strip().lower())
        if background_rgb is None:
            raise LsppValidationError("background must be white, black, gray, or grey")
        run_dir = create_run_dir(output, "preview_lsdyna_keyword_model")
        cfile_path = write_generated_cfile(
            run_dir,
            "preview_keyword_model.cfile.j2",
            {
                "k_path": quote_path(keyword),
                "view_command": VIEW_COMMANDS[view_key],
                "mesh_command": "mesh on" if show_mesh else "mesh off",
                "show_triad": 1 if show_triad else 0,
                "background_rgb": background_rgb,
                "print_format": print_format,
                "output_image": quote_path(output),
            },
        )
        log_file = run_dir / "run.json"
        from . import _common

        run_result = _common.run_lsprepost(
            cfile_path=cfile_path,
            mode="image",
            window_size=window_size,
            use_nographics=use_nographics,
            timeout=cfg.timeout_seconds,
            lsprepost_exe=cfg.lsprepost_exe,
            log_file=log_file,
        )
        output_check = check_required_output(output, run_result)
        ok = bool(run_result.ok and output_check["nonempty"])
        return {
            "ok": ok,
            "message": (
                "Keyword model preview generated."
                if ok
                else "LS-PrePost preview did not generate the expected nonempty image."
            ),
            "k_path": str(keyword),
            "output_image": str(output),
            "image_format": normalized_format,
            "generated_cfile": str(cfile_path),
            "log_file": str(log_file),
            "returncode": run_result.returncode,
            "output_check": output_file_check(output),
        }
    except Exception as exc:
        result = result_from_validation_error(exc)
        result["k_path"] = str(k_path)
        result["output_image"] = str(output_image)
        return result
