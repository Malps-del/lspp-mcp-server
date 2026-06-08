"""Default configurable LS-PrePost variable maps.

These defaults are copied into ``config.example.yaml`` and can be overridden by
``config.yaml``. Tool code reads maps through ``LsppConfig`` instead of relying
on magic numbers at call sites.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_D3PLOT_FRINGE: dict[str, int] = {
    "pressure": 8,
    "von_mises": 9,
    "effective_plastic_strain": 7,
    "x_displacement": 17,
    "y_displacement": 18,
    "z_displacement": 19,
    "resultant_displacement": 20,
    "x_velocity": 21,
    "y_velocity": 22,
    "z_velocity": 23,
    "resultant_velocity": 24,
    "x_acceleration": 231,
    "y_acceleration": 232,
    "z_acceleration": 233,
    "resultant_acceleration": 234,
    "x_coordinate": 246,
    "y_coordinate": 247,
    "z_coordinate": 248,
}


DEFAULT_NODOUT: dict[str, int] = {
    "x_displacement": 1,
    "y_displacement": 2,
    "z_displacement": 3,
    "resultant_displacement": 4,
    "x_velocity": 5,
    "y_velocity": 6,
    "z_velocity": 7,
    "resultant_velocity": 8,
    "x_acceleration": 9,
    "y_acceleration": 10,
    "z_acceleration": 11,
    "resultant_acceleration": 12,
    "hic15": 13,
    "hic36": 14,
    "csi": 15,
    "x_coordinate": 28,
    "y_coordinate": 29,
    "z_coordinate": 30,
    "hic_unlimited": 31,
}


DEFAULT_MATSUM: dict[str, int] = {
    "internal_energy": 1,
    "kinetic_energy": 2,
    "hourglass_energy": 3,
    "x_rbdisplacement": 4,
    "y_rbdisplacement": 5,
    "z_rbdisplacement": 6,
    "resultant_rbdisplacement": 7,
    "x_rbvelocity": 8,
    "y_rbvelocity": 9,
    "z_rbvelocity": 10,
    "resultant_rbvelocity": 11,
    "x_rbacceleration": 12,
    "y_rbacceleration": 13,
    "z_rbacceleration": 14,
    "resultant_rbacceleration": 15,
    "x_momentum": 16,
    "y_momentum": 17,
    "z_momentum": 18,
    "resultant_momentum": 19,
    "added_mass": 20,
    "kinetic_internal_energy_ratio": 21,
    "hic15": 22,
    "hic36": 23,
    "csi": 24,
    "eroded_internal_energy": 25,
    "eroded_kinetic_energy": 26,
    "total_internal_energy": 27,
    "total_kinetic_energy": 28,
    "eroded_hourglass_energy": 29,
}


DEFAULT_NODE_HISTORY: dict[str, int] = {
    "x_coordinate": 1,
    "y_coordinate": 2,
    "z_coordinate": 3,
    "total_coordinate": 4,
    "x_displacement": 5,
    "y_displacement": 6,
    "z_displacement": 7,
    "resultant_displacement": 8,
    "x_velocity": 9,
    "y_velocity": 10,
    "z_velocity": 11,
    "resultant_velocity": 12,
    "x_acceleration": 13,
    "y_acceleration": 14,
    "z_acceleration": 15,
    "resultant_acceleration": 16,
    "temperature": 17,
    "temperature_rate": 18,
    "d_temperature_dt": 18,
    "x_heat_flux": 19,
    "y_heat_flux": 20,
    "z_heat_flux": 21,
    "resultant_heat_flux": 22,
    "mass_scaling": 23,
    "xy_displacement": 24,
    "yz_displacement": 25,
    "xz_displacement": 26,
    "relative_x_displacement": 27,
    "relative_y_displacement": 28,
    "relative_z_displacement": 29,
    "relative_resultant_displacement": 30,
    "hic15": 31,
    "hic36": 32,
    "csi": 33,
}


DEFAULT_BINOUT: dict[str, dict[str, dict[str, Any]]] = {
    "glstat": {
        "kinetic_energy": {
            "variable": "kinetic_energy",
            "index1": 0,
            "index2": 1,
            "entity_index": 0,
        },
        "internal_energy": {
            "variable": "internal_energy",
            "index1": 0,
            "index2": 1,
            "entity_index": 0,
        },
        "hourglass_energy": {
            "variable": "hourglass_energy",
            "index1": 0,
            "index2": 1,
            "entity_index": 0,
        },
        "total_energy": {
            "variable": "total_energy",
            "index1": 0,
            "index2": 1,
            "entity_index": 0,
        },
    },
    "matsum": {
        "internal_energy": {
            "variable": "internal_energy",
            "index1": 0,
            "index2": 1,
            "entity_index": 0,
        },
        "kinetic_energy": {
            "variable": "kinetic_energy",
            "index1": 0,
            "index2": 1,
            "entity_index": 0,
        },
    },
    "trhist": {
        "x_displacement": {
            "variable": "x_displacement",
            "index1": 0,
            "index2": 1,
            "entity_index": 0,
        },
        "y_displacement": {
            "variable": "y_displacement",
            "index1": 0,
            "index2": 1,
            "entity_index": 0,
        },
        "z_displacement": {
            "variable": "z_displacement",
            "index1": 0,
            "index2": 1,
            "entity_index": 0,
        },
    },
    "dbfsi": {
        "pressure": {
            "variable": "pressure",
            "index1": 0,
            "index2": 1,
            "entity_index": 0,
        },
        "resultant_force": {
            "variable": "resultant_force",
            "index1": 0,
            "index2": 1,
            "entity_index": 0,
        },
    },
}


DEFAULT_VARIABLE_MAPS: dict[str, Any] = {
    "d3plot_fringe": DEFAULT_D3PLOT_FRINGE,
    "nodout": DEFAULT_NODOUT,
    "matsum": DEFAULT_MATSUM,
    "node_history": DEFAULT_NODE_HISTORY,
    "binout": DEFAULT_BINOUT,
}


def default_variable_maps() -> dict[str, Any]:
    """Return a deep copy so callers can safely merge user configuration."""

    return deepcopy(DEFAULT_VARIABLE_MAPS)


def deep_update(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into ``base`` and return ``base``."""

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_update(base[key], value)
        else:
            base[key] = value
    return base
