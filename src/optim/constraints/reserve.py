import math
from dataclasses import dataclass
from typing import Any, Hashable, Iterable, Mapping

import pyoptinterface as poi

from src.optim.variables import ThermalVariables


@dataclass
class SystemReserveConstraints:
    """System spinning-reserve constraint handles."""

    requirement: dict[Hashable, Any]


def add_system_reserve_constraints(
    model: Any,
    variables: ThermalVariables,
    unit_ids: Iterable[str],
    periods: Iterable[Hashable],
    p_max_mw: Mapping[str, float],
    reserve_requirement_mw: Mapping[Hashable, float],
) -> SystemReserveConstraints:
    """Require sufficient unused capacity from online thermal units."""

    unit_ids = tuple(unit_ids)
    periods = tuple(periods)

    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError("Thermal unit IDs must be unique")

    if len(periods) != len(set(periods)):
        raise ValueError("Periods must be unique")

    maximum_capacity = {}

    for unit_id in unit_ids:
        if unit_id not in p_max_mw:
            raise ValueError(f"Missing maximum capacity for unit {unit_id}")

        maximum = float(p_max_mw[unit_id])

        if not math.isfinite(maximum) or maximum < 0.0:
            raise ValueError(
                f"Maximum capacity must be finite and nonnegative: {unit_id}"
            )

        maximum_capacity[unit_id] = maximum

    constraints = {}

    for period in periods:
        if period not in reserve_requirement_mw:
            raise ValueError(
                f"Missing reserve requirement for period {period}"
            )

        requirement = float(reserve_requirement_mw[period])

        if not math.isfinite(requirement) or requirement < 0.0:
            raise ValueError(
                f"Reserve requirement must be finite and nonnegative: {period}"
            )

        available_reserve = poi.ExprBuilder()

        for unit_id in unit_ids:
            key = (unit_id, period)

            if key not in variables.power or key not in variables.is_on:
                raise KeyError(f"Missing thermal variable: {key}")

            available_reserve += (
                maximum_capacity[unit_id] * variables.is_on[key]
                - variables.power[key]
            )

        constraints[period] = model.add_linear_constraint(
            available_reserve,
            poi.Geq,
            requirement,
            name=f"system_reserve[{period}]",
        )

    return SystemReserveConstraints(requirement=constraints)