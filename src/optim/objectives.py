# -*- coding: utf-8 -*-
import math
from typing import Any, Hashable, Iterable

import pyoptinterface as poi

from src.model.grid import Grid
from src.optim.variables import ThermalVariables


def set_thermal_cost_objective(
    model: Any,
    grid: Grid,
    variables: ThermalVariables,
    periods: Iterable[Hashable],
    step_hours: float = 1.0,
) -> dict[str, Any]:
    """设置火电发电成本、启动成本和停机成本目标函数。"""

    if not math.isfinite(step_hours) or step_hours <= 0.0:
        raise ValueError("step_hours must be a positive finite number")

    periods = tuple(periods)
    variable_cost = poi.ExprBuilder()
    startup_cost = poi.ExprBuilder()
    shutdown_cost = poi.ExprBuilder()

    # 1. 按火电机组和时段累加成本项
    for unit in grid.getResListFromType("THERMAL"):
        unit_id = unit.id
        # 1.1 读取线性发电成本、启动成本、停机成本
        linear_cost = _thermal_linear_cost(unit)
        startup_unit_cost = float(getattr(unit, "startUpCost", 0.0))
        shutdown_unit_cost = float(getattr(unit, "shutDownCost", 0.0))

        for period in periods:
            key = (unit_id, period)
            if key not in variables.power:
                raise KeyError(f"Missing thermal power variable: {key}")
            if key not in variables.startup:
                raise KeyError(f"Missing thermal startup variable: {key}")
            if key not in variables.shutdown:
                raise KeyError(f"Missing thermal shutdown variable: {key}")

            # 1.2 发电成本：linearCost * P_g,t * Δt
            variable_cost += linear_cost * step_hours * variables.power[key]
            # 1.3 启动成本：startUpCost * v_g,t
            startup_cost += startup_unit_cost * variables.startup[key]
            # 1.4 停机成本：shutDownCost * w_g,t
            shutdown_cost += shutdown_unit_cost * variables.shutdown[key]

    # 2. 总目标：min 发电成本 + 启动成本 + 停机成本
    total_cost = variable_cost + startup_cost + shutdown_cost
    model.set_objective(total_cost, poi.ObjectiveSense.Minimize)

    return {
        "variable_cost": variable_cost,
        "startup_cost": startup_cost,
        "shutdown_cost": shutdown_cost,
        "total_cost": total_cost,
    }


def _thermal_linear_cost(unit: Any) -> float:
    # 3. 优先使用成员3标准字段 linearCost，兼容旧字段 variableCost
    linear_cost = getattr(unit, "linearCost", None)
    if linear_cost is not None:
        return float(linear_cost)
    return float(getattr(unit, "variableCost", 0.0))
