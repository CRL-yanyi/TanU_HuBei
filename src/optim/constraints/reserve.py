# -*- coding: utf-8 -*-
import math
from typing import Any, Hashable, Iterable, Mapping

import pyoptinterface as poi

from src.model.grid import Grid
from src.optim.opt_model import OptModel


def add_system_reserve_constraints(
    opt_model: OptModel,
    grid: Grid,
    periods: Iterable[Hashable],
    reserve_requirement_mw: Mapping[Hashable, float],
) -> dict[str, Any]:
    """Add spinning reserve constraints from online thermal spare capacity."""

    constraints: dict[str, Any] = {}
    thermal_units = tuple(grid.getResListFromType("THERMAL"))

    for period in periods:
        if period not in reserve_requirement_mw:
            raise ValueError(f"Missing reserve requirement for period {period}")

        requirement = float(reserve_requirement_mw[period])
        if not math.isfinite(requirement) or requirement < 0.0:
            raise ValueError(
                f"Reserve requirement must be finite and nonnegative: {period}"
            )

        reserve_expr = poi.ExprBuilder()

        for unit in thermal_units:
            key = (unit.id, period)
            reserve_expr += (
                unit.Pmax * opt_model.get_var("thermal_is_on", key)
                - opt_model.get_var("thermal_power", key)
            )

        constraint_key = f"system_reserve_{period}"
        constraints[constraint_key] = opt_model.add_linear_constraint(
            constraint_key,
            reserve_expr,
            poi.Geq,
            requirement,
            name=f"system_reserve[{period}]",
        )

    return constraints
