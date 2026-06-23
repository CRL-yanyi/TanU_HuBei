# -*- coding: utf-8 -*-
import math
from typing import Any, Hashable, Iterable

import pyoptinterface as poi

from src.model.grid import Grid
from src.optim.variables import ThermalVariables, RenewableVariables, LoadShedVariables


def set_grid_objective(
    model: Any,
    grid: Grid,
    periods: Iterable[Hashable],
    thermal_vars: ThermalVariables | None = None,
    renewable_vars: RenewableVariables | None = None,
    load_shed_vars: LoadShedVariables | None = None,
    step_hours: float = 1.0,
    curtailment_penalty_wind: float = 0.0,
    curtailment_penalty_pv: float = 0.0,
    load_shed_penalty: float = 0.0,
) -> dict[str, Any]:
    """通用目标函数设置函数：整合火电成本、新能源弃能惩罚与负荷损失惩罚，仅执行一次求解器目标设置。"""
    if not math.isfinite(step_hours) or step_hours <= 0.0:
        raise ValueError("step_hours must be a positive finite number")

    periods = tuple(periods)
    total_expr = poi.ExprBuilder()
    results = {}

    # 1. 累加火电机组的运行与启停成本
    if thermal_vars is not None:
        variable_cost = poi.ExprBuilder()
        startup_cost = poi.ExprBuilder()
        shutdown_cost = poi.ExprBuilder()

        for unit in grid.getResListFromType("THERMAL"):
            unit_id = unit.id
            linear_cost = _thermal_linear_cost(unit)
            startup_unit_cost = float(getattr(unit, "startUpCost", 0.0))
            shutdown_unit_cost = float(getattr(unit, "shutDownCost", 0.0))

            for period in periods:
                key = (unit_id, period)
                if key not in thermal_vars.power:
                    raise KeyError(f"Missing thermal power variable: {key}")
                if key not in thermal_vars.startup:
                    raise KeyError(f"Missing thermal startup variable: {key}")
                if key not in thermal_vars.shutdown:
                    raise KeyError(f"Missing thermal shutdown variable: {key}")

                # 发电成本：linearCost * P_g,t * Δt
                if abs(linear_cost) > 1e-9:
                    variable_cost.add_affine_term(thermal_vars.power[key], linear_cost * step_hours)
                # 启动成本：startUpCost * v_g,t
                if abs(startup_unit_cost) > 1e-9:
                    startup_cost.add_affine_term(thermal_vars.startup[key], startup_unit_cost)
                # 停机成本：shutDownCost * w_g,t
                if abs(shutdown_unit_cost) > 1e-9:
                    shutdown_cost.add_affine_term(thermal_vars.shutdown[key], shutdown_unit_cost)

        thermal_total = variable_cost + startup_cost + shutdown_cost
        total_expr += thermal_total

        results.update({
            "variable_cost": variable_cost,
            "startup_cost": startup_cost,
            "shutdown_cost": shutdown_cost,
            "thermal_cost": thermal_total,      # 系统目标兼容字段
            "total_cost": thermal_total,        # 火电目标兼容字段
        })

    # 2. 累加新能源弃风弃光惩罚成本
    renewable_cost = poi.ExprBuilder()
    if renewable_vars is not None:
        if abs(curtailment_penalty_wind) > 1e-9:
            for k in grid.getResListFromType("WIND"):
                for t in periods:
                    renewable_cost.add_affine_term(renewable_vars.curtailment[k.id, t], curtailment_penalty_wind * step_hours)

        if abs(curtailment_penalty_pv) > 1e-9:
            for k in grid.getResListFromType("PV"):
                for t in periods:
                    renewable_cost.add_affine_term(renewable_vars.curtailment[k.id, t], curtailment_penalty_pv * step_hours)

        total_expr += renewable_cost
    results["renewable_cost"] = renewable_cost

    # 3. 累加系统失负荷惩罚成本
    load_shed_cost = poi.ExprBuilder()
    if load_shed_vars is not None and abs(load_shed_penalty) > 1e-9:
        for zone_id in grid.zones:
            for t in periods:
                load_shed_cost.add_affine_term(load_shed_vars.load_shed[zone_id, t], load_shed_penalty * step_hours)
        
        total_expr += load_shed_cost
    results["load_shed_cost"] = load_shed_cost

    # 4. 统一在模型上设置最小化目标函数
    model.set_objective(total_expr, poi.ObjectiveSense.Minimize)
    results["total_objective"] = total_expr

    return results


def _thermal_linear_cost(unit: Any) -> float:
    # 优先使用成员3标准字段 linearCost，兼容旧字段 variableCost
    linear_cost = getattr(unit, "linearCost", None)
    if linear_cost is not None:
        return float(linear_cost)
    return float(getattr(unit, "variableCost", 0.0))
