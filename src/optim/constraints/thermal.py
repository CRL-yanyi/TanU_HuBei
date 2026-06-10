import math
from dataclasses import dataclass
from typing import Any, Hashable, Iterable, Mapping

import pyoptinterface as poi

from src.optim.variables import ThermalVariables


ConstraintKey = tuple[str, Hashable]


@dataclass
class ThermalCapacityConstraints:
    """火电出力上下限约束句柄。"""

    lower: dict[ConstraintKey, Any]
    upper: dict[ConstraintKey, Any]


def add_thermal_capacity_constraints(
    model: Any,
    variables: ThermalVariables,
    unit_ids: Iterable[str],
    periods: Iterable[Hashable],
    p_min_mw: Mapping[str, float],
    p_max_mw: Mapping[str, float],
) -> ThermalCapacityConstraints:
    """添加火电机组出力上下限约束。"""

    unit_ids = tuple(unit_ids)
    periods = tuple(periods)

    lower_constraints = {}
    upper_constraints = {}

    for unit_id in unit_ids:
        if unit_id not in p_min_mw or unit_id not in p_max_mw:
            raise ValueError(f"机组 {unit_id} 缺少出力上下限参数")

        minimum = float(p_min_mw[unit_id])
        maximum = float(p_max_mw[unit_id])

        if not math.isfinite(minimum) or not math.isfinite(maximum):
            raise ValueError(f"机组 {unit_id} 的出力上下限必须是有限数值")

        if minimum < 0.0 or maximum < minimum:
            raise ValueError(f"机组 {unit_id} 的出力上下限不合法")

        for period in periods:
            key = (unit_id, period)

            if key not in variables.power or key not in variables.is_on:
                raise KeyError(f"缺少火电变量索引: {key}")

            power = variables.power[key]
            is_on = variables.is_on[key]

            lower_constraints[key] = model.add_linear_constraint(
                power - minimum * is_on,
                poi.Geq,
                0.0,
                name=f"thermal_capacity_lower[{unit_id},{period}]",
            )
            upper_constraints[key] = model.add_linear_constraint(
                power - maximum * is_on,
                poi.Leq,
                0.0,
                name=f"thermal_capacity_upper[{unit_id},{period}]",
            )

    return ThermalCapacityConstraints(
        lower=lower_constraints,
        upper=upper_constraints,
    )
@dataclass
class ThermalCommitmentConstraints:
    """火电启停状态转换约束句柄。"""

    transition: dict[ConstraintKey, Any]
    no_simultaneous_start_stop: dict[ConstraintKey, Any]


def add_thermal_commitment_constraints(
    model: Any,
    variables: ThermalVariables,
    unit_ids: Iterable[str],
    periods: Iterable[Hashable],
    initial_on: Mapping[str, int],
) -> ThermalCommitmentConstraints:
    """添加启停状态转换及禁止同时启停约束。"""

    unit_ids = tuple(unit_ids)
    periods = tuple(periods)

    transition_constraints = {}
    no_simultaneous_constraints = {}

    for unit_id in unit_ids:
        if unit_id not in initial_on:
            raise ValueError(f"机组 {unit_id} 缺少初始开机状态")

        initial_state = int(initial_on[unit_id])
        if initial_state not in (0, 1):
            raise ValueError(f"机组 {unit_id} 的初始开机状态必须为 0 或 1")

        for period_index, period in enumerate(periods):
            key = (unit_id, period)

            required_variables = (
                variables.is_on,
                variables.startup,
                variables.shutdown,
            )
            if any(key not in variable_group for variable_group in required_variables):
                raise KeyError(f"缺少火电变量索引: {key}")

            current_on = variables.is_on[key]
            startup = variables.startup[key]
            shutdown = variables.shutdown[key]

            if period_index == 0:
                previous_on = initial_state
            else:
                previous_period = periods[period_index - 1]
                previous_on = variables.is_on[unit_id, previous_period]

            transition_constraints[key] = model.add_linear_constraint(
                current_on - previous_on - startup + shutdown,
                poi.Eq,
                0.0,
                name=f"thermal_state_transition[{unit_id},{period}]",
            )

            no_simultaneous_constraints[key] = model.add_linear_constraint(
                startup + shutdown,
                poi.Leq,
                1.0,
                name=f"thermal_no_simultaneous_start_stop[{unit_id},{period}]",
            )

    return ThermalCommitmentConstraints(
        transition=transition_constraints,
        no_simultaneous_start_stop=no_simultaneous_constraints,
    )