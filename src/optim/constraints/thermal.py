# -*- coding: utf-8 -*-
import math
from collections.abc import Mapping, Sequence

import pandas as pd
import pyoptinterface as poi


THERMAL_POWER = "thermal_power"
THERMAL_IS_ON = "thermal_is_on"
THERMAL_STARTUP = "thermal_startup"
THERMAL_SHUTDOWN = "thermal_shutdown"


def add_thermal_uc_constraints(opt_model, grid, periods):
    """添加火电机组组合常规约束。"""
    add_thermal_output_limit_constraints(opt_model, grid, periods)
    add_thermal_state_transition_constraints(opt_model, grid, periods)
    add_thermal_start_stop_exclusion_constraints(opt_model, grid, periods)
    add_thermal_minimum_time_constraints(opt_model, grid, periods)
    add_thermal_ramp_constraints(opt_model, grid, periods)


def add_thermal_ed_constraints(opt_model, grid, periods):
    """添加火电经济调度常规约束，固定状态来自 Thermal.ONOFF。"""
    add_thermal_fixed_status_constraints(opt_model, grid, periods)
    add_thermal_ed_output_limit_constraints(opt_model, grid, periods)
    add_thermal_ed_ramp_constraints(opt_model, grid, periods)


def add_thermal_output_limit_constraints(opt_model, grid, periods):
    """Pmin * u[t] <= P[t] <= Pmax * u[t]."""
    for unit in grid.getResListFromType("THERMAL"):
        p_min, p_max = _output_limits(unit)

        for t in periods:
            key = (unit.id, t)
            pg = opt_model.get_var(THERMAL_POWER, key)
            ug = opt_model.get_var(THERMAL_IS_ON, key)

            _add_constraint(
                opt_model,
                f"thermal_pmin_{unit.id}_{t}",
                pg - p_min * ug,
                poi.Geq,
                0.0,
                f"thermal_pmin[{unit.id},{t}]",
            )
            _add_constraint(
                opt_model,
                f"thermal_pmax_{unit.id}_{t}",
                pg - p_max * ug,
                poi.Leq,
                0.0,
                f"thermal_pmax[{unit.id},{t}]",
            )


def add_thermal_state_transition_constraints(opt_model, grid, periods):
    """u[t] - u[t-1] = startup[t] - shutdown[t]."""
    for unit in grid.getResListFromType("THERMAL"):
        ug_prev = _initial_status(unit)

        for t in periods:
            key = (unit.id, t)
            ug = opt_model.get_var(THERMAL_IS_ON, key)
            vg = opt_model.get_var(THERMAL_STARTUP, key)
            wg = opt_model.get_var(THERMAL_SHUTDOWN, key)

            _add_constraint(
                opt_model,
                f"thermal_state_{unit.id}_{t}",
                ug - ug_prev - vg + wg,
                poi.Eq,
                0.0,
                f"thermal_state[{unit.id},{t}]",
            )
            ug_prev = ug


def add_thermal_start_stop_exclusion_constraints(opt_model, grid, periods):
    """startup[t] + shutdown[t] <= 1."""
    for unit in grid.getResListFromType("THERMAL"):
        for t in periods:
            key = (unit.id, t)
            vg = opt_model.get_var(THERMAL_STARTUP, key)
            wg = opt_model.get_var(THERMAL_SHUTDOWN, key)

            _add_constraint(
                opt_model,
                f"thermal_start_stop_excl_{unit.id}_{t}",
                vg + wg,
                poi.Leq,
                1.0,
                f"thermal_start_stop_excl[{unit.id},{t}]",
            )


def add_thermal_minimum_time_constraints(opt_model, grid, periods):
    """最小开机、最小停机和窗口初始剩余时间约束。"""
    periods = tuple(periods)
    step_hours = _period_step_hours(periods)

    for unit in grid.getResListFromType("THERMAL"):
        _add_minimum_time_constraints_for_unit(opt_model, unit, periods, step_hours)


def add_thermal_ramp_constraints(opt_model, grid, periods):
    """常规爬坡约束，包含启动和停机容量。"""
    periods = tuple(periods)
    step_hours = _period_step_hours(periods)

    for unit in grid.getResListFromType("THERMAL"):
        _, p_max = _output_limits(unit)
        ramp_up = _unit_number(unit, "rampUp")
        ramp_down = _unit_number(unit, "rampDown")
        startup_ramp = _ramp_capacity(unit, "startUpCapacity", p_max)
        shutdown_ramp = _ramp_capacity(unit, "shutDownCapacity", p_max)

        ug_prev = _initial_status(unit)
        pg_prev = _initial_power(unit, ug_prev)
        if ug_prev == 0 and pg_prev != 0.0:
            raise ValueError(f"Initial power must be 0 when unit {unit.id} is offline")

        for t in periods:
            key = (unit.id, t)
            pg = opt_model.get_var(THERMAL_POWER, key)
            ug = opt_model.get_var(THERMAL_IS_ON, key)
            vg = opt_model.get_var(THERMAL_STARTUP, key)
            wg = opt_model.get_var(THERMAL_SHUTDOWN, key)

            _add_constraint(
                opt_model,
                f"thermal_ramp_up_{unit.id}_{t}",
                pg - pg_prev - ramp_up * step_hours * ug_prev - startup_ramp * vg,
                poi.Leq,
                0.0,
                f"thermal_ramp_up[{unit.id},{t}]",
            )
            _add_constraint(
                opt_model,
                f"thermal_ramp_down_{unit.id}_{t}",
                pg_prev - pg - ramp_down * step_hours * ug - shutdown_ramp * wg,
                poi.Leq,
                0.0,
                f"thermal_ramp_down[{unit.id},{t}]",
            )

            ug_prev = ug
            pg_prev = pg


def add_thermal_must_run_constraints(opt_model, grid, periods):
    """可选约束：mustRun 机组强制开机。"""
    for unit in grid.getResListFromType("THERMAL"):
        if not bool(getattr(unit, "mustRun", False)):
            continue

        for t in periods:
            key = (unit.id, t)
            ug = opt_model.get_var(THERMAL_IS_ON, key)

            _add_constraint(
                opt_model,
                f"thermal_must_run_{unit.id}_{t}",
                ug,
                poi.Eq,
                1.0,
                f"thermal_must_run[{unit.id},{t}]",
            )


def add_thermal_fixed_status_constraints(opt_model, grid, periods):
    """ED 固定开停机状态：u/v/w 由 Thermal.ONOFF 决定。"""
    periods = tuple(periods)

    for unit in grid.getResListFromType("THERMAL"):
        status_prev = _initial_status(unit)

        for t_idx, t in enumerate(periods):
            key = (unit.id, t)
            status = _fixed_status(unit, t, t_idx)
            startup_status = max(status - status_prev, 0)
            shutdown_status = max(status_prev - status, 0)

            _add_constraint(
                opt_model,
                f"thermal_fixed_on_{unit.id}_{t}",
                opt_model.get_var(THERMAL_IS_ON, key),
                poi.Eq,
                status,
                f"thermal_fixed_on[{unit.id},{t}]",
            )
            _add_constraint(
                opt_model,
                f"thermal_fixed_startup_{unit.id}_{t}",
                opt_model.get_var(THERMAL_STARTUP, key),
                poi.Eq,
                startup_status,
                f"thermal_fixed_startup[{unit.id},{t}]",
            )
            _add_constraint(
                opt_model,
                f"thermal_fixed_shutdown_{unit.id}_{t}",
                opt_model.get_var(THERMAL_SHUTDOWN, key),
                poi.Eq,
                shutdown_status,
                f"thermal_fixed_shutdown[{unit.id},{t}]",
            )

            status_prev = status


def add_thermal_ed_output_limit_constraints(opt_model, grid, periods):
    """ED 出力上下限，开停机状态读取 Thermal.ONOFF。"""
    periods = tuple(periods)

    for unit in grid.getResListFromType("THERMAL"):
        p_min, p_max = _output_limits(unit)

        for t_idx, t in enumerate(periods):
            key = (unit.id, t)
            status = _fixed_status(unit, t, t_idx)
            pg = opt_model.get_var(THERMAL_POWER, key)

            _add_constraint(
                opt_model,
                f"thermal_pmin_{unit.id}_{t}",
                pg - p_min * status,
                poi.Geq,
                0.0,
                f"thermal_pmin[{unit.id},{t}]",
            )
            _add_constraint(
                opt_model,
                f"thermal_pmax_{unit.id}_{t}",
                pg - p_max * status,
                poi.Leq,
                0.0,
                f"thermal_pmax[{unit.id},{t}]",
            )


def add_thermal_ed_ramp_constraints(opt_model, grid, periods):
    """ED 爬坡约束，开停机状态读取 Thermal.ONOFF。"""
    periods = tuple(periods)
    step_hours = _period_step_hours(periods)

    for unit in grid.getResListFromType("THERMAL"):
        _, p_max = _output_limits(unit)
        ramp_up = _unit_number(unit, "rampUp")
        ramp_down = _unit_number(unit, "rampDown")
        startup_ramp = _ramp_capacity(unit, "startUpCapacity", p_max)
        shutdown_ramp = _ramp_capacity(unit, "shutDownCapacity", p_max)

        status_prev = _initial_status(unit)
        pg_prev = _initial_power(unit, status_prev)
        if status_prev == 0 and pg_prev != 0.0:
            raise ValueError(f"Initial power must be 0 when unit {unit.id} is offline")

        for t_idx, t in enumerate(periods):
            key = (unit.id, t)
            status = _fixed_status(unit, t, t_idx)
            startup_status = max(status - status_prev, 0)
            shutdown_status = max(status_prev - status, 0)
            pg = opt_model.get_var(THERMAL_POWER, key)

            _add_constraint(
                opt_model,
                f"thermal_ramp_up_{unit.id}_{t}",
                pg
                - pg_prev
                - ramp_up * step_hours * status_prev
                - startup_ramp * startup_status,
                poi.Leq,
                0.0,
                f"thermal_ramp_up[{unit.id},{t}]",
            )
            _add_constraint(
                opt_model,
                f"thermal_ramp_down_{unit.id}_{t}",
                pg_prev
                - pg
                - ramp_down * step_hours * status
                - shutdown_ramp * shutdown_status,
                poi.Leq,
                0.0,
                f"thermal_ramp_down[{unit.id},{t}]",
            )

            status_prev = status
            pg_prev = pg


def _add_minimum_time_constraints_for_unit(opt_model, unit, periods, step_hours):
    min_up = _unit_number(unit, "minON")
    min_down = _unit_number(unit, "minOFF")
    up_periods = math.ceil(min_up / step_hours)
    down_periods = math.ceil(min_down / step_hours)

    if up_periods > 1:
        for t_idx in range(up_periods - 1, len(periods)):
            t = periods[t_idx]
            startup_sum = poi.quicksum(
                opt_model.get_var(THERMAL_STARTUP, (unit.id, periods[i]))
                for i in range(t_idx - up_periods + 1, t_idx + 1)
            )
            _add_constraint(
                opt_model,
                f"thermal_min_up_{unit.id}_{t}",
                startup_sum - opt_model.get_var(THERMAL_IS_ON, (unit.id, t)),
                poi.Leq,
                0.0,
                f"thermal_min_up[{unit.id},{t}]",
            )

    if down_periods > 1:
        for t_idx in range(down_periods - 1, len(periods)):
            t = periods[t_idx]
            shutdown_sum = poi.quicksum(
                opt_model.get_var(THERMAL_SHUTDOWN, (unit.id, periods[i]))
                for i in range(t_idx - down_periods + 1, t_idx + 1)
            )
            _add_constraint(
                opt_model,
                f"thermal_min_down_{unit.id}_{t}",
                shutdown_sum + opt_model.get_var(THERMAL_IS_ON, (unit.id, t)),
                poi.Leq,
                1.0,
                f"thermal_min_down[{unit.id},{t}]",
            )

    initial_state = _initial_status(unit)
    elapsed_on = _initial_hours(unit, online=True)
    elapsed_off = _initial_hours(unit, online=False)

    if initial_state == 1:
        forced_value = 1.0
        forced_periods = math.ceil(max(0.0, min_up - elapsed_on) / step_hours)
    else:
        forced_value = 0.0
        forced_periods = math.ceil(max(0.0, min_down - elapsed_off) / step_hours)

    for t in periods[:forced_periods]:
        _add_constraint(
            opt_model,
            f"thermal_initial_residual_{unit.id}_{t}",
            opt_model.get_var(THERMAL_IS_ON, (unit.id, t)),
            poi.Eq,
            forced_value,
            f"thermal_initial_residual[{unit.id},{t}]",
        )


def _add_constraint(opt_model, constraint_key, expr, sense, rhs, name):
    opt_model.add_linear_constraint(constraint_key, expr, sense, rhs, name)


def _output_limits(unit):
    p_min = _unit_number(unit, "Pmin")
    p_max = _unit_number(unit, "Pmax")
    if p_max < p_min:
        raise ValueError(f"Invalid output limits for unit {unit.id}")
    return p_min, p_max


def _period_step_hours(periods):
    periods = tuple(periods)
    if len(periods) >= 2:
        delta = periods[1] - periods[0]
        if isinstance(delta, pd.Timedelta):
            hours = delta / pd.Timedelta(hours=1)
            _require_positive_step(hours)
            return float(hours)
    return 1.0


def _require_positive_step(step_hours):
    if not math.isfinite(step_hours) or step_hours <= 0.0:
        raise ValueError("step_hours must be positive")


def _unit_number(unit, field, default=None):
    value = getattr(unit, field, default)
    if value is None:
        raise ValueError(f"Thermal unit {unit.id} is missing field {field}")

    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{field} must be finite and nonnegative: {unit.id}")
    return value


def _ramp_capacity(unit, field, fallback):
    value = _unit_number(unit, field, fallback)
    if value == 0.0:
        return fallback
    return value


def _initial_status(unit):
    init_t = float(getattr(unit, "initT", 0.0))
    return 1 if init_t > 0.0 else 0


def _initial_hours(unit, online):
    init_t = float(getattr(unit, "initT", 0.0))
    value = max(init_t, 0.0) if online else max(-init_t, 0.0)

    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"Initial hours must be finite and nonnegative: {unit.id}")
    return value


def _initial_power(unit, initial_status):
    value = getattr(unit, "initialPower", None)
    if value is None:
        value = _unit_number(unit, "Pmin") if initial_status == 1 else 0.0

    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"Initial power must be finite and nonnegative: {unit.id}")
    return value


def _fixed_status(unit, period, period_index):
    onoff = getattr(unit, "ONOFF", None)
    if onoff is None or onoff == {}:
        raise ValueError(f"Missing fixed commitment: {(unit.id, period)}")

    try:
        if isinstance(onoff, Mapping):
            if period in onoff:
                return _as_binary(onoff[period], unit, period)
            if period_index in onoff:
                return _as_binary(onoff[period_index], unit, period)
            if "S0" in onoff:
                return _fixed_status_from_container(
                    onoff["S0"], unit, period, period_index
                )
        return _fixed_status_from_container(onoff, unit, period, period_index)
    except (IndexError, KeyError, TypeError) as exc:
        raise ValueError(f"Missing fixed commitment: {(unit.id, period)}") from exc

    raise ValueError(f"Missing fixed commitment: {(unit.id, period)}")


def _fixed_status_from_container(values, unit, period, period_index):
    if isinstance(values, Mapping):
        if period in values:
            return _as_binary(values[period], unit, period)
        if period_index in values:
            return _as_binary(values[period_index], unit, period)
        raise KeyError(period)

    if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
        return _as_binary(values[period_index], unit, period)

    raise TypeError("Unsupported ONOFF format")


def _as_binary(value, unit, period):
    value = int(value)
    if value not in (0, 1):
        raise ValueError(f"fixed commitment must be 0 or 1: {(unit.id, period)}")
    return value
