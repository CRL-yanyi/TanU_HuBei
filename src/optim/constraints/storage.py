# -*- coding: utf-8 -*-
"""储能与抽蓄约束，对齐参考项目 storagemodel.py 的 2.4.1—2.4.6。

普通电化学储能和抽水蓄能使用同一组数学约束：

- 2.4.1、2.4.2：充、放电功率受状态变量和额定功率限制；
- 2.4.3：按时间步长和充放电效率递推时段末能量；
- 2.4.4：每个时段的能量均位于 ``[Emin, Emax]``；
- 2.4.5：充电状态与放电状态不能同时为 1；
- 2.4.6：每天最后一个时段的能量固定为 ``EnT``。

功率单位为 MW，能量单位为 MWh，效率是 (0, 1] 内的无量纲值。
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Iterable, Mapping
from typing import Any

import pandas as pd
import pyoptinterface as poi

from src.model.grid import Grid
from src.optim.constraints._constraint_utils import (
    finite_nonnegative,
    is_last_period_of_day,
    step_hours,
    validate_time_index,
)
from src.optim.variables import StorageVariables


def _add_constraint(
    target: Any,
    key: tuple[str, Hashable, str, str],
    expression: Any,
    sense: Any,
    rhs: float = 0.0,
) -> Any:
    """兼容 OptModel 与底层 pyoptinterface 模型的约束添加方式。"""
    if hasattr(target, "addCons"):
        return target.addCons(key, expression, sense, rhs)
    return target.add_linear_constraint(
        expression,
        sense,
        rhs,
        name=str(key),
    )


def _normalise_periods(
    periods: Iterable[Hashable],
) -> tuple[list[Hashable], pd.DatetimeIndex | None, float]:
    """规范化时段，并返回时段列表、日期索引和小时步长。

    正式 DatetimeIndex 可识别真实日末并支持 15 分钟等非整小时步长；历史
    整数索引没有日期信息，只能按 1 小时处理并把窗口最后一段视为日末。
    """
    if isinstance(periods, pd.DatetimeIndex):
        time_idx = validate_time_index(periods)
        return list(time_idx), time_idx, step_hours(time_idx)
    period_list = list(periods)
    if not period_list:
        raise ValueError("periods must not be empty")
    return period_list, None, 1.0


def _storage_constraints(
    target: Any,
    grid: Grid,
    variables: StorageVariables,
    periods: Iterable[Hashable],
    *,
    initial_energy: Mapping[str, float] | None = None,
) -> dict[tuple[str, Hashable, str, str], Any]:
    """构造储能/抽蓄全部运行约束。"""
    period_list, time_idx, hours_per_step = _normalise_periods(periods)
    constraints: dict[tuple[str, Hashable, str, str], Any] = {}

    for storage in grid.getResListFromType("STORAGE"):
        # 先集中校验静态参数，避免求解后才暴露容量或初末状态不合法。
        p_max = finite_nonnegative(
            storage.Pmax, owner=storage.id, field="Pmax"
        )
        e_min = finite_nonnegative(
            storage.Emin, owner=storage.id, field="Emin"
        )
        e_max = finite_nonnegative(
            storage.Emax, owner=storage.id, field="Emax"
        )
        initial_value = (
            initial_energy.get(storage.id, storage.E0)
            if initial_energy is not None
            else storage.E0
        )
        e_initial = finite_nonnegative(
            initial_value, owner=storage.id, field="E0"
        )
        e_terminal = finite_nonnegative(
            storage.EnT, owner=storage.id, field="EnT"
        )
        if e_min > e_max:
            raise ValueError(f"{storage.id} Emin must not exceed Emax")
        if not e_min <= e_initial <= e_max:
            raise ValueError(f"{storage.id} E0 must be within [Emin, Emax]")
        if not e_min <= e_terminal <= e_max:
            raise ValueError(f"{storage.id} EnT must be within [Emin, Emax]")

        # 效率不得为 0，否则放电项 PD/effD 无定义；大于 1 也不符合物理含义。
        efficiency_charge = float(storage.effC)
        efficiency_discharge = float(storage.effD)
        for field, value in (
            ("effC", efficiency_charge),
            ("effD", efficiency_discharge),
        ):
            if not math.isfinite(value) or value <= 0.0 or value > 1.0:
                raise ValueError(f"{storage.id} field '{field}' must be in (0, 1]")

        for index, period in enumerate(period_list):
            # PC、PD、E、CS、DS 均来自同一资源和同一时段的变量键。
            charge = variables.charge_power[storage.id, period]
            discharge = variables.discharge_power[storage.id, period]
            energy = variables.energy[storage.id, period]
            charging_state = variables.is_charging[storage.id, period]
            discharging_state = variables.is_discharging[storage.id, period]

            # 2.4.1：PC_t <= CS_t × Pmax。
            # CS_t=0 时充电功率必须为 0；CS_t=1 时可在 [0, Pmax] 内取值。
            key = (storage.id, period, "PC", "2.4.1")
            constraints[key] = _add_constraint(
                target,
                key,
                charge - charging_state * p_max,
                poi.Leq,
                0.0,
            )
            # 2.4.2：PD_t <= DS_t × Pmax，含义与充电侧对应。
            key = (storage.id, period, "PD", "2.4.2")
            constraints[key] = _add_constraint(
                target,
                key,
                discharge - discharging_state * p_max,
                poi.Leq,
                0.0,
            )
            # 2.4.5：CS_t + DS_t <= 1，禁止同一时段同时充电和放电。
            key = (storage.id, period, "CDS", "2.4.5")
            constraints[key] = _add_constraint(
                target,
                key,
                charging_state + discharging_state,
                poi.Leq,
                1.0,
            )
            # 2.4.4：显式设置能量上下界，便于约束追踪和误差检查。
            key = (storage.id, period, "E_MIN", "2.4.4")
            constraints[key] = _add_constraint(
                target,
                key,
                energy,
                poi.Geq,
                e_min,
            )
            key = (storage.id, period, "E_MAX", "2.4.4")
            constraints[key] = _add_constraint(
                target,
                key,
                energy,
                poi.Leq,
                e_max,
            )

            # 2.4.3：
            # E_t = E_(t-1) + (PC_t×effC - PD_t/effD)×Δt。
            # 充电只有 effC 比例进入储能；为向系统输出 PD，储能侧需消耗
            # PD/effD。乘 Δt 后将功率变化量转换为能量变化量。
            energy_change = (
                charge * efficiency_charge
                - discharge / efficiency_discharge
            ) * hours_per_step
            if index == 0:
                # 首时段没有模型内前序变量，使用资源参数 E0 作为窗口初值。
                transition = energy - energy_change
                rhs = e_initial
            else:
                previous = variables.energy[storage.id, period_list[index - 1]]
                transition = energy - previous - energy_change
                rhs = 0.0
            key = (storage.id, period, "E", "2.4.3")
            constraints[key] = _add_constraint(
                target,
                key,
                transition,
                poi.Eq,
                rhs,
            )

            # 2.4.6：正式日期索引在每个自然日末固定 E=EnT；兼容整数索引
            # 无法识别跨日，只在整个窗口最后一个时段添加该约束。
            end_of_day = (
                is_last_period_of_day(time_idx, index)
                if time_idx is not None
                else index == len(period_list) - 1
            )
            if end_of_day:
                key = (storage.id, period, "E_END", "2.4.6")
                constraints[key] = _add_constraint(
                    target,
                    key,
                    energy,
                    poi.Eq,
                    e_terminal,
                )

    return constraints


def setStorageConstraints(
    optmodel: Any,
    gridData: Grid,
    timeIdx: pd.DatetimeIndex,
    *,
    initial_energy: Mapping[str, float] | None = None,
) -> dict[tuple[str, Hashable, str, str], Any]:
    """正式接口：读取统一变量键并建立储能和抽蓄约束。

    调用前应先执行 ``setStorageVarList``。本函数不创建变量，只从 OptModel
    读取 PC、PD、E、CS、DS，并把它们组织成约束层需要的类型化视图。
    """
    validate_time_index(timeIdx)
    variables = StorageVariables(
        charge_power={
            (storage.id, period): optmodel.getVar(
                storage.id, period, "P", "PC"
            )
            for storage in gridData.getResListFromType("STORAGE")
            for period in timeIdx
        },
        discharge_power={
            (storage.id, period): optmodel.getVar(
                storage.id, period, "P", "PD"
            )
            for storage in gridData.getResListFromType("STORAGE")
            for period in timeIdx
        },
        energy={
            (storage.id, period): optmodel.getVar(storage.id, period, "E")
            for storage in gridData.getResListFromType("STORAGE")
            for period in timeIdx
        },
        is_charging={
            (storage.id, period): optmodel.getVar(storage.id, period, "CS")
            for storage in gridData.getResListFromType("STORAGE")
            for period in timeIdx
        },
        is_discharging={
            (storage.id, period): optmodel.getVar(storage.id, period, "DS")
            for storage in gridData.getResListFromType("STORAGE")
            for period in timeIdx
        },
    )
    return _storage_constraints(
        optmodel,
        gridData,
        variables,
        timeIdx,
        initial_energy=initial_energy,
    )


def add_storage_constraints(
    model: Any,
    grid: Grid,
    variables: StorageVariables,
    periods: Iterable[Hashable],
    initial_energy: dict[str, float] | None = None,
) -> dict[tuple[str, Hashable, str, str], Any]:
    """兼容直接传入底层模型的历史入口。

    ``initial_energy`` 可覆盖本次约束右端使用的 ``E0``，用于把上一个窗口
    的末端能量传给下一个窗口。该映射不会修改 Grid 中的资源参数。
    """
    return _storage_constraints(
        model,
        grid,
        variables,
        periods,
        initial_energy=initial_energy,
    )
