# -*- coding: utf-8 -*-
import math
from typing import Any, Hashable, Iterable, Mapping

import pyoptinterface as poi

from src.model.grid import Grid
from src.optim.variables import ThermalVariables


def add_system_reserve_constraints(
    model: Any,
    grid: Grid,
    variables: ThermalVariables,
    periods: Iterable[Hashable],
    reserve_requirement_mw: Mapping[Hashable, float],
) -> dict[str, Any]:
    """添加系统旋转备用约束，备用来自在线火电剩余容量。"""

    constraints: dict[str, Any] = {}
    # 1. 当前备用只统计火电：Pmax * u_g,t - P_g,t
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

        # 1.1 汇总所有在线火电机组的可上调容量
        for unit in thermal_units:
            key = (unit.id, period)
            if key not in variables.power or key not in variables.is_on:
                raise KeyError(f"Missing thermal variable: {key}")

            reserve_expr += unit.Pmax * variables.is_on[key] - variables.power[key]

        # 1.2 系统备用约束：sum(Pmax * u - P) >= R_t
        constraints[f"system_reserve_{period}"] = model.add_linear_constraint(
            reserve_expr,
            poi.Geq,
            requirement,
            name=f"system_reserve[{period}]",
        )

    return constraints
