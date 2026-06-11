import math
from dataclasses import dataclass
from typing import Any, Hashable, Iterable, Mapping

import pyoptinterface as poi

from src.optim.variables import ThermalVariables


@dataclass
class ThermalCostObjective:
    """Expressions forming the thermal operating cost."""

    variable_cost: Any
    startup_cost: Any
    shutdown_cost: Any
    total_cost: Any


def set_thermal_cost_objective(
    model: Any,
    variables: ThermalVariables,
    unit_ids: Iterable[str],
    periods: Iterable[Hashable],
    variable_cost_yuan_per_mwh: Mapping[str, float],
    startup_cost_yuan: Mapping[str, float],
    shutdown_cost_yuan: Mapping[str, float],
    step_hours: float = 1.0,
) -> ThermalCostObjective:
    """Set generation, startup, and shutdown costs as the objective."""

    unit_ids = tuple(unit_ids)
    periods = tuple(periods)

    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError("Thermal unit IDs must be unique")

    if len(periods) != len(set(periods)):
        raise ValueError("Periods must be unique")

    if not math.isfinite(step_hours) or step_hours <= 0.0:
        raise ValueError("step_hours must be a positive finite number")

    cost_mappings = {
        "variable cost": variable_cost_yuan_per_mwh,
        "startup cost": startup_cost_yuan,
        "shutdown cost": shutdown_cost_yuan,
    }

    for cost_name, mapping in cost_mappings.items():
        for unit_id in unit_ids:
            if unit_id not in mapping:
                raise ValueError(f"Missing {cost_name} for unit {unit_id}")

            value = float(mapping[unit_id])
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(
                    f"{cost_name} must be finite and nonnegative: {unit_id}"
                )

    variable_cost = poi.ExprBuilder()
    startup_cost = poi.ExprBuilder()
    shutdown_cost = poi.ExprBuilder()

    for unit_id in unit_ids:
        for period in periods:
            key = (unit_id, period)

            if key not in variables.power:
                raise KeyError(f"Missing thermal power variable: {key}")
            if key not in variables.startup:
                raise KeyError(f"Missing thermal startup variable: {key}")
            if key not in variables.shutdown:
                raise KeyError(f"Missing thermal shutdown variable: {key}")

            variable_cost += (
                float(variable_cost_yuan_per_mwh[unit_id])
                * step_hours
                * variables.power[key]
            )
            startup_cost += (
                float(startup_cost_yuan[unit_id])
                * variables.startup[key]
            )
            shutdown_cost += (
                float(shutdown_cost_yuan[unit_id])
                * variables.shutdown[key]
            )

    total_cost = variable_cost + startup_cost + shutdown_cost

    model.set_objective(
        total_cost,
        poi.ObjectiveSense.Minimize,
    )

    return ThermalCostObjective(
        variable_cost=variable_cost,
        startup_cost=startup_cost,
        shutdown_cost=shutdown_cost,
        total_cost=total_cost,
    )