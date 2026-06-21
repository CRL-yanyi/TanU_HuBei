# -*- coding: utf-8 -*-
import math
from typing import Any, Hashable, Iterable, Mapping

import pyoptinterface as poi

from src.model.grid import Grid
from src.optim.variables import ThermalVariables


ConstraintKey = tuple[str, Hashable]


def add_thermal_uc_constraints(
    model: Any,
    grid: Grid,
    variables: ThermalVariables,
    periods: Iterable[Hashable],
    initial_on: Mapping[str, int] | None = None,
    initial_power_mw: Mapping[str, float] | None = None,
    initial_on_hours: Mapping[str, float] | None = None,
    initial_off_hours: Mapping[str, float] | None = None,
    step_hours: float = 1.0,
) -> dict[str, Any]:
    """添加火电机组组合（UC）约束，启停状态由模型优化决定。"""

    _require_positive_step(step_hours)
    periods = tuple(periods)
    constraints: dict[str, Any] = {}

    # 1. 遍历 Grid 中所有火电机组，逐机组、逐时段建立物理约束
    for unit in grid.getResListFromType("THERMAL"):
        unit_id = unit.id
        # 1.1 读取出力上下限参数：Pmin <= P_g,t <= Pmax
        p_min = _unit_number(unit, "Pmin")
        p_max = _unit_number(unit, "Pmax")
        if p_max < p_min:
            raise ValueError(f"Invalid output limits for unit {unit_id}")

        # 1.2 读取初始开停机状态和初始出力，用于第一个时段的状态转移与爬坡
        initial_state = _initial_status(unit, initial_on)
        previous_on: Any = initial_state
        previous_power: Any = _initial_power(unit, initial_power_mw, initial_state)
        if previous_on == 0 and previous_power != 0.0:
            raise ValueError(
                f"Initial power must be 0 when unit {unit_id} is offline"
            )

        # 1.3 读取常规、启动、停机爬坡能力
        ramp_up = _unit_number(unit, "rampUp")
        ramp_down = _unit_number(unit, "rampDown")
        startup_ramp = _ramp_capacity(unit, "startUpCapacity", p_max)
        shutdown_ramp = _ramp_capacity(unit, "shutDownCapacity", p_max)

        for period in periods:
            key = (unit_id, period)
            power = _var(variables.power, key, "thermal power")
            is_on = _var(variables.is_on, key, "thermal commitment")
            startup = _var(variables.startup, key, "thermal startup")
            shutdown = _var(variables.shutdown, key, "thermal shutdown")

            # 1.4 出力上下限约束：Pmin * u_g,t <= P_g,t <= Pmax * u_g,t
            constraints[f"thermal_pmin_{unit_id}_{period}"] = (
                model.add_linear_constraint(
                    power - p_min * is_on,
                    poi.Geq,
                    0.0,
                    name=f"thermal_pmin[{unit_id},{period}]",
                )
            )
            constraints[f"thermal_pmax_{unit_id}_{period}"] = (
                model.add_linear_constraint(
                    power - p_max * is_on,
                    poi.Leq,
                    0.0,
                    name=f"thermal_pmax[{unit_id},{period}]",
                )
            )

            # 1.5 启停状态转移约束：u_g,t - u_g,t-1 = v_g,t - w_g,t
            constraints[f"thermal_state_{unit_id}_{period}"] = (
                model.add_linear_constraint(
                    is_on - previous_on - startup + shutdown,
                    poi.Eq,
                    0.0,
                    name=f"thermal_state[{unit_id},{period}]",
                )
            )
            # 1.6 启动与停机互斥：v_g,t + w_g,t <= 1
            constraints[f"thermal_start_stop_excl_{unit_id}_{period}"] = (
                model.add_linear_constraint(
                    startup + shutdown,
                    poi.Leq,
                    1.0,
                    name=f"thermal_start_stop_excl[{unit_id},{period}]",
                )
            )

            # 1.7 上爬坡约束：P_g,t - P_g,t-1 <= RU * Δt * u_g,t-1 + SUCap * v_g,t
            constraints[f"thermal_ramp_up_{unit_id}_{period}"] = (
                model.add_linear_constraint(
                    power
                    - previous_power
                    - ramp_up * step_hours * previous_on
                    - startup_ramp * startup,
                    poi.Leq,
                    0.0,
                    name=f"thermal_ramp_up[{unit_id},{period}]",
                )
            )
            # 1.8 下爬坡约束：P_g,t-1 - P_g,t <= RD * Δt * u_g,t + SDCap * w_g,t
            constraints[f"thermal_ramp_down_{unit_id}_{period}"] = (
                model.add_linear_constraint(
                    previous_power
                    - power
                    - ramp_down * step_hours * is_on
                    - shutdown_ramp * shutdown,
                    poi.Leq,
                    0.0,
                    name=f"thermal_ramp_down[{unit_id},{period}]",
                )
            )

            previous_on = is_on
            previous_power = power

        # 1.9 最小开机、最小停机和滚动窗口初始剩余时间约束
        _add_minimum_time_constraints(
            model=model,
            variables=variables,
            constraints=constraints,
            unit=unit,
            periods=periods,
            initial_on=initial_on,
            initial_on_hours=initial_on_hours,
            initial_off_hours=initial_off_hours,
            step_hours=step_hours,
        )

    return constraints


def add_thermal_ed_constraints(
    model: Any,
    grid: Grid,
    variables: ThermalVariables,
    periods: Iterable[Hashable],
    fixed_on: Mapping[ConstraintKey, int],
    initial_on: Mapping[str, int] | None = None,
    initial_power_mw: Mapping[str, float] | None = None,
    step_hours: float = 1.0,
) -> dict[str, Any]:
    """添加火电经济调度（ED）约束，启停状态由 fixed_on 固定。"""

    _require_positive_step(step_hours)
    periods = tuple(periods)
    constraints: dict[str, Any] = {}

    # 2. ED 中启停状态不再优化，按 fixed_on 固定后只调度出力
    for unit in grid.getResListFromType("THERMAL"):
        unit_id = unit.id
        # 2.1 读取火电机组物理参数
        p_min = _unit_number(unit, "Pmin")
        p_max = _unit_number(unit, "Pmax")
        ramp_up = _unit_number(unit, "rampUp")
        ramp_down = _unit_number(unit, "rampDown")
        startup_ramp = _ramp_capacity(unit, "startUpCapacity", p_max)
        shutdown_ramp = _ramp_capacity(unit, "shutDownCapacity", p_max)

        previous_status = _initial_status(unit, initial_on)
        previous_power: Any = _initial_power(unit, initial_power_mw, previous_status)
        if previous_status == 0 and previous_power != 0.0:
            raise ValueError(
                f"Initial power must be 0 when unit {unit_id} is offline"
            )

        for period in periods:
            key = (unit_id, period)
            # 2.2 根据固定开机状态推导启动、停机状态
            status = _binary(fixed_on, key, "fixed commitment")
            startup_status = max(status - previous_status, 0)
            shutdown_status = max(previous_status - status, 0)
            power = _var(variables.power, key, "thermal power")

            # 2.3 固定开机状态：u_g,t = fixed_on_g,t
            constraints[f"thermal_fixed_on_{unit_id}_{period}"] = (
                model.add_linear_constraint(
                    _var(variables.is_on, key, "thermal commitment"),
                    poi.Eq,
                    status,
                    name=f"thermal_fixed_on[{unit_id},{period}]",
                )
            )
            # 2.4 固定启动状态：v_g,t = max(u_g,t - u_g,t-1, 0)
            constraints[f"thermal_fixed_startup_{unit_id}_{period}"] = (
                model.add_linear_constraint(
                    _var(variables.startup, key, "thermal startup"),
                    poi.Eq,
                    startup_status,
                    name=f"thermal_fixed_startup[{unit_id},{period}]",
                )
            )
            # 2.5 固定停机状态：w_g,t = max(u_g,t-1 - u_g,t, 0)
            constraints[f"thermal_fixed_shutdown_{unit_id}_{period}"] = (
                model.add_linear_constraint(
                    _var(variables.shutdown, key, "thermal shutdown"),
                    poi.Eq,
                    shutdown_status,
                    name=f"thermal_fixed_shutdown[{unit_id},{period}]",
                )
            )
            # 2.6 固定状态下的出力上下限：Pmin * status <= P_g,t <= Pmax * status
            constraints[f"thermal_pmin_{unit_id}_{period}"] = (
                model.add_linear_constraint(
                    power - p_min * status,
                    poi.Geq,
                    0.0,
                    name=f"thermal_pmin[{unit_id},{period}]",
                )
            )
            constraints[f"thermal_pmax_{unit_id}_{period}"] = (
                model.add_linear_constraint(
                    power - p_max * status,
                    poi.Leq,
                    0.0,
                    name=f"thermal_pmax[{unit_id},{period}]",
                )
            )
            # 2.7 固定状态下的上爬坡约束
            constraints[f"thermal_ramp_up_{unit_id}_{period}"] = (
                model.add_linear_constraint(
                    power
                    - previous_power
                    - ramp_up * step_hours * previous_status
                    - startup_ramp * startup_status,
                    poi.Leq,
                    0.0,
                    name=f"thermal_ramp_up[{unit_id},{period}]",
                )
            )
            # 2.8 固定状态下的下爬坡约束
            constraints[f"thermal_ramp_down_{unit_id}_{period}"] = (
                model.add_linear_constraint(
                    previous_power
                    - power
                    - ramp_down * step_hours * status
                    - shutdown_ramp * shutdown_status,
                    poi.Leq,
                    0.0,
                    name=f"thermal_ramp_down[{unit_id},{period}]",
                )
            )

            previous_status = status
            previous_power = power

    return constraints


def _add_minimum_time_constraints(
    model: Any,
    variables: ThermalVariables,
    constraints: dict[str, Any],
    unit: Any,
    periods: tuple[Hashable, ...],
    initial_on: Mapping[str, int] | None,
    initial_on_hours: Mapping[str, float] | None,
    initial_off_hours: Mapping[str, float] | None,
    step_hours: float,
) -> None:
    unit_id = unit.id
    # 3. 将最小开停机小时数换算成优化时段数
    min_up = _unit_number(unit, "minON")
    min_down = _unit_number(unit, "minOFF")
    up_periods = math.ceil(min_up / step_hours)
    down_periods = math.ceil(min_down / step_hours)

    if up_periods > 1:
        for period_index in range(up_periods - 1, len(periods)):
            period = periods[period_index]
            # 3.1 最小开机时间：最近 up_periods 内启动过，则当前必须开机
            startup_sum = poi.quicksum(
                _var(
                    variables.startup,
                    (unit_id, periods[index]),
                    "thermal startup",
                )
                for index in range(period_index - up_periods + 1, period_index + 1)
            )
            constraints[f"thermal_min_up_{unit_id}_{period}"] = (
                model.add_linear_constraint(
                    startup_sum
                    - _var(variables.is_on, (unit_id, period), "thermal commitment"),
                    poi.Leq,
                    0.0,
                    name=f"thermal_min_up[{unit_id},{period}]",
                )
            )

    if down_periods > 1:
        for period_index in range(down_periods - 1, len(periods)):
            period = periods[period_index]
            # 3.2 最小停机时间：最近 down_periods 内停机过，则当前必须停机
            shutdown_sum = poi.quicksum(
                _var(
                    variables.shutdown,
                    (unit_id, periods[index]),
                    "thermal shutdown",
                )
                for index in range(period_index - down_periods + 1, period_index + 1)
            )
            constraints[f"thermal_min_down_{unit_id}_{period}"] = (
                model.add_linear_constraint(
                    shutdown_sum
                    + _var(variables.is_on, (unit_id, period), "thermal commitment"),
                    poi.Leq,
                    1.0,
                    name=f"thermal_min_down[{unit_id},{period}]",
                )
            )

    initial_state = _initial_status(unit, initial_on)
    elapsed_on = _initial_hours(unit, initial_on_hours, online=True)
    elapsed_off = _initial_hours(unit, initial_off_hours, online=False)

    # 3.3 处理滚动优化窗口开始前已经持续的开机/停机时间
    if initial_state == 1:
        forced_value = 1.0
        forced_periods = math.ceil(max(0.0, min_up - elapsed_on) / step_hours)
    else:
        forced_value = 0.0
        forced_periods = math.ceil(max(0.0, min_down - elapsed_off) / step_hours)

    for period in periods[:forced_periods]:
        constraints[f"thermal_initial_residual_{unit_id}_{period}"] = (
            model.add_linear_constraint(
                _var(variables.is_on, (unit_id, period), "thermal commitment"),
                poi.Eq,
                forced_value,
                name=f"thermal_initial_residual[{unit_id},{period}]",
            )
        )


def _var(variables: Mapping[Any, Any], key: Any, label: str) -> Any:
    try:
        return variables[key]
    except KeyError as exc:
        raise KeyError(f"Missing {label} variable: {key}") from exc


def _binary(mapping: Mapping[Any, int], key: Any, label: str) -> int:
    if key not in mapping:
        raise ValueError(f"Missing {label}: {key}")

    value = int(mapping[key])
    if value not in (0, 1):
        raise ValueError(f"{label} must be 0 or 1: {key}")
    return value


def _require_positive_step(step_hours: float) -> None:
    if not math.isfinite(step_hours) or step_hours <= 0.0:
        raise ValueError("step_hours must be positive")


def _unit_number(unit: Any, field: str, default: float | None = None) -> float:
    # 4. 统一读取并校验火电数值字段，避免主约束逻辑重复写参数检查
    value = getattr(unit, field, default)
    if value is None:
        raise ValueError(f"Thermal unit {unit.id} is missing field {field}")

    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{field} must be finite and nonnegative: {unit.id}")
    return value


def _ramp_capacity(unit: Any, field: str, fallback: float) -> float:
    # 5. 启动/停机爬坡容量缺省或为 0 时，按 Pmax 放宽处理
    value = _unit_number(unit, field, fallback)
    if value == 0.0:
        return fallback
    return value


def _initial_status(unit: Any, override: Mapping[str, int] | None) -> int:
    if override is not None and unit.id in override:
        return _binary(override, unit.id, "initial commitment")

    init_t = float(getattr(unit, "initT", 0.0))
    return 1 if init_t > 0.0 else 0


def _initial_hours(
    unit: Any,
    override: Mapping[str, float] | None,
    online: bool,
) -> float:
    if override is not None and unit.id in override:
        value = float(override[unit.id])
    else:
        init_t = float(getattr(unit, "initT", 0.0))
        value = max(init_t, 0.0) if online else max(-init_t, 0.0)

    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"Initial hours must be finite and nonnegative: {unit.id}")
    return value


def _initial_power(
    unit: Any,
    override: Mapping[str, float] | None,
    initial_status: int,
) -> float:
    if override is not None and unit.id in override:
        value = float(override[unit.id])
    else:
        value = getattr(unit, "initialPower", None)
        if value is None:
            value = _unit_number(unit, "Pmin") if initial_status == 1 else 0.0
        value = float(value)

    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"Initial power must be finite and nonnegative: {unit.id}")
    return value
