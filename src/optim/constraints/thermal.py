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
@dataclass
class ThermalMinimumTimeConstraints:
    """最小开机、停机时间约束句柄。"""

    minimum_up: dict[ConstraintKey, Any]
    minimum_down: dict[ConstraintKey, Any]
    initial_residual: dict[ConstraintKey, Any]


def add_thermal_minimum_time_constraints(
    model: Any,
    variables: ThermalVariables,
    unit_ids: Iterable[str],
    periods: Iterable[Hashable],
    min_up_hours: Mapping[str, float],
    min_down_hours: Mapping[str, float],
    initial_on: Mapping[str, int],
    initial_on_hours: Mapping[str, float],
    initial_off_hours: Mapping[str, float],
    step_hours: float = 1.0,
) -> ThermalMinimumTimeConstraints:
    """添加最小连续开机、停机时间及初始剩余时间约束。"""

    if not math.isfinite(step_hours) or step_hours <= 0.0:
        raise ValueError("时间步长必须是正数")

    unit_ids = tuple(unit_ids)
    periods = tuple(periods)

    minimum_up_constraints = {}
    minimum_down_constraints = {}
    initial_residual_constraints = {}

    for unit_id in unit_ids:
        required_mappings = (
            min_up_hours,
            min_down_hours,
            initial_on,
            initial_on_hours,
            initial_off_hours,
        )
        if any(unit_id not in mapping for mapping in required_mappings):
            raise ValueError(f"机组 {unit_id} 缺少最小开停机参数")

        minimum_up_hours = float(min_up_hours[unit_id])
        minimum_down_hours = float(min_down_hours[unit_id])
        initial_state = int(initial_on[unit_id])
        elapsed_on_hours = float(initial_on_hours[unit_id])
        elapsed_off_hours = float(initial_off_hours[unit_id])

        numeric_values = (
            minimum_up_hours,
            minimum_down_hours,
            elapsed_on_hours,
            elapsed_off_hours,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in numeric_values):
            raise ValueError(f"机组 {unit_id} 的最小开停机参数不合法")

        if initial_state not in (0, 1):
            raise ValueError(f"机组 {unit_id} 的初始开机状态必须为 0 或 1")

        up_periods = math.ceil(minimum_up_hours / step_hours)
        down_periods = math.ceil(minimum_down_hours / step_hours)

        for period_index, period in enumerate(periods):
            key = (unit_id, period)

            if key not in variables.is_on:
                raise KeyError(f"缺少火电变量索引: {key}")

            if up_periods > 0:
                first_index = max(0, period_index - up_periods + 1)
                startup_sum = poi.quicksum(
                    variables.startup[unit_id, periods[index]]
                    for index in range(first_index, period_index + 1)
                )
                minimum_up_constraints[key] = model.add_linear_constraint(
                    startup_sum - variables.is_on[key],
                    poi.Leq,
                    0.0,
                    name=f"thermal_minimum_up[{unit_id},{period}]",
                )

            if down_periods > 0:
                first_index = max(0, period_index - down_periods + 1)
                shutdown_sum = poi.quicksum(
                    variables.shutdown[unit_id, periods[index]]
                    for index in range(first_index, period_index + 1)
                )
                minimum_down_constraints[key] = model.add_linear_constraint(
                    shutdown_sum + variables.is_on[key],
                    poi.Leq,
                    1.0,
                    name=f"thermal_minimum_down[{unit_id},{period}]",
                )

        if initial_state == 1:
            remaining_hours = max(0.0, minimum_up_hours - elapsed_on_hours)
            forced_periods = math.ceil(remaining_hours / step_hours)
            forced_value = 1.0
        else:
            remaining_hours = max(0.0, minimum_down_hours - elapsed_off_hours)
            forced_periods = math.ceil(remaining_hours / step_hours)
            forced_value = 0.0

        for period in periods[:forced_periods]:
            key = (unit_id, period)
            initial_residual_constraints[key] = model.add_linear_constraint(
                variables.is_on[key],
                poi.Eq,
                forced_value,
                name=f"thermal_initial_residual[{unit_id},{period}]",
            )

    return ThermalMinimumTimeConstraints(
        minimum_up=minimum_up_constraints,
        minimum_down=minimum_down_constraints,
        initial_residual=initial_residual_constraints,
    )