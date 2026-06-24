# -*- coding: utf-8 -*-
import math
from typing import Any, Hashable, Iterable

import pandas as pd
import pyoptinterface as poi

from src.model.grid import Grid
from src.optim.opt_model import OptModel


def set_thermal_cost_objective(
    opt_model: OptModel,
    grid: Grid,
    periods: Iterable[Hashable],
    step_hours: float | None = None,
) -> dict[str, Any]:
    """Set thermal generation, startup, and shutdown costs."""

    periods = tuple(periods)
    if step_hours is None:
        step_hours = _period_step_hours(periods)
    if not math.isfinite(step_hours) or step_hours <= 0.0:
        raise ValueError("step_hours must be a positive finite number")

    variable_cost = poi.ExprBuilder()
    startup_cost = poi.ExprBuilder()
    shutdown_cost = poi.ExprBuilder()

    for unit in grid.getResListFromType("THERMAL"):
        linear_cost = _thermal_linear_cost(unit)
        startup_unit_cost = float(getattr(unit, "startUpCost", 0.0))
        shutdown_unit_cost = float(getattr(unit, "shutDownCost", 0.0))

        for period in periods:
            key = (unit.id, period)
            variable_cost += (
                linear_cost * step_hours * opt_model.get_var("thermal_power", key)
            )
            startup_cost += (
                startup_unit_cost * opt_model.get_var("thermal_startup", key)
            )
            shutdown_cost += (
                shutdown_unit_cost * opt_model.get_var("thermal_shutdown", key)
            )

    total_cost = variable_cost + startup_cost + shutdown_cost
    opt_model.set_objective(total_cost, poi.ObjectiveSense.Minimize)

    return {
        "variable_cost": variable_cost,
        "startup_cost": startup_cost,
        "shutdown_cost": shutdown_cost,
        "total_cost": total_cost,
    }


def _thermal_linear_cost(unit: Any) -> float:
    linear_cost = getattr(unit, "linearCost", None)
    if linear_cost is not None:
        return float(linear_cost)
    return float(getattr(unit, "variableCost", 0.0))


def _period_step_hours(periods: Iterable[Hashable]) -> float:
    periods_tuple = tuple(periods)
    if len(periods_tuple) >= 2:
        delta = periods_tuple[1] - periods_tuple[0]
        if isinstance(delta, pd.Timedelta):
            hours = delta / pd.Timedelta(hours=1)
            if math.isfinite(hours) and hours > 0.0:
                return float(hours)
    return 1.0
