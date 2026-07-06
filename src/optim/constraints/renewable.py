# -*- coding: utf-8 -*-
"""风电、光伏约束，对齐参考项目 renewablemodel.py 的 2.5.1—2.5.3。

风电和光伏使用相同的数学形式：

- 2.5.1：实际出力 + 弃电 = 场景标幺系数 × 当月装机容量；
- 2.5.2：相邻时段实际出力的上升量不超过上爬坡限值；
- 2.5.3：相邻时段实际出力的下降量不超过下爬坡限值。

出力、弃电和装机容量单位均为 MW；场景系数为非负标幺值；爬坡参数单位
为 MW/h，因此约束右端需要乘以实际时间步长。
"""

from __future__ import annotations

import math
from collections.abc import Callable, Hashable, Iterable
from typing import Any

import pandas as pd
import pyoptinterface as poi

from src.model.grid import Grid
from src.optim.constraints._constraint_utils import (
    finite_nonnegative,
    month_value,
    step_hours,
    validate_time_index,
)
from src.optim.variables import RenewableVariables
from src.scenario import ScenarioSet


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


def _renewable_constraints(
    target: Any,
    grid: Grid,
    variables: RenewableVariables,
    periods: list[Hashable],
    *,
    hours_per_step: float,
    available_power: Callable[[Any, Hashable], float],
) -> dict[tuple[str, Hashable, str, str], Any]:
    """按给定可用功率函数构造风电、光伏的守恒和爬坡约束。

    ``available_power`` 隔离了正式场景接口与历史资源时序接口的取数差异，
    两条调用路径因此共用完全相同的数学公式。
    """
    constraints: dict[tuple[str, Hashable, str, str], Any] = {}
    renewable_units = (
        grid.getResListFromType("WIND") + grid.getResListFromType("PV")
    )

    for resource in renewable_units:
        # inf 表示不启用对应方向的爬坡限制；有限值必须为非负 MW/h。
        ramp_up = float(getattr(resource, "rampUp", float("inf")))
        ramp_down = float(getattr(resource, "rampDown", float("inf")))
        for field, value in (("rampUp", ramp_up), ("rampDown", ramp_down)):
            if value != float("inf") and (
                not math.isfinite(value) or value < 0.0
            ):
                raise ValueError(
                    f"{resource.id} field '{field}' must be nonnegative"
                )

        for index, period in enumerate(periods):
            # 可用功率必须是有限非负值，防止缺失或异常场景值进入模型。
            available = finite_nonnegative(
                available_power(resource, period),
                owner=resource.id,
                field="available_power",
            )
            # 2.5.1：P_actual,t + P_curt,t = P_available,t。
            # 两个变量均非负，因此等式同时保证实际出力不会超过可用出力。
            key = (resource.id, period, "P", "2.5.1")
            constraints[key] = _add_constraint(
                target,
                key,
                variables.power[resource.id, period]
                + variables.curtailment[resource.id, period],
                poi.Eq,
                available,
            )

            if index == 0:
                # 第一个时段没有模型内前序出力，不建立跨窗口爬坡约束。
                continue
            previous = periods[index - 1]
            if ramp_up != float("inf"):
                # 2.5.2：(P_t - P_(t-1)) <= rampUp × Δt。
                key = (resource.id, period, "RAMP_UP", "2.5.2")
                constraints[key] = _add_constraint(
                    target,
                    key,
                    variables.power[resource.id, period]
                    - variables.power[resource.id, previous],
                    poi.Leq,
                    ramp_up * hours_per_step,
                )
            if ramp_down != float("inf"):
                # 2.5.3：(P_(t-1) - P_t) <= rampDown × Δt。
                key = (resource.id, period, "RAMP_DOWN", "2.5.3")
                constraints[key] = _add_constraint(
                    target,
                    key,
                    variables.power[resource.id, previous]
                    - variables.power[resource.id, period],
                    poi.Leq,
                    ramp_down * hours_per_step,
                )
    return constraints


def setRenewableConstraints(
    optmodel: Any,
    gridData: Grid,
    timeIdx: pd.DatetimeIndex,
    scenarioSet: ScenarioSet,
    scenarioId: str,
) -> dict[tuple[str, Hashable, str, str], Any]:
    """正式接口：按指定单场景和月装机容量建立新能源约束。

    调用前应先执行 ``setRenewableVarList``。场景时间索引必须与模型时间索引
    完全相同，避免场景值错位。当前生产模型只允许一个概率为 1 的场景。
    """
    validate_time_index(timeIdx)
    scenario = scenarioSet.require_single_scenario(scenarioId)
    # equals 同时比较长度、顺序和每个时间戳，不允许仅长度相同但时刻错位。
    if not scenario.time_index.equals(timeIdx):
        raise ValueError(
            f"scenario '{scenarioId}' time index does not match timeIdx"
        )

    # 风电和光伏都使用 P 与 P/curt 两类已登记变量。
    renewable_units = (
        gridData.getResListFromType("WIND")
        + gridData.getResListFromType("PV")
    )
    variables = RenewableVariables(
        power={
            (resource.id, period): optmodel.getVar(resource.id, period, "P")
            for resource in renewable_units
            for period in timeIdx
        },
        curtailment={
            (resource.id, period): optmodel.getVar(
                resource.id, period, "P", "curt"
            )
            for resource in renewable_units
            for period in timeIdx
        },
    )

    def available_power(resource: Any, period: pd.Timestamp) -> float:
        """计算资源在当前时段的可用出力，单位 MW。"""
        if not resource.monthly_capacity_mw:
            raise ValueError(
                f"{resource.id} missing field 'monthly_capacity_mw' "
                f"for month {period:%Y-%m}"
            )
        # 装机容量按自然月切换，跨月窗口会自动读取新月份的容量。
        installed_capacity = month_value(
            resource.monthly_capacity_mw,
            period,
            owner=resource.id,
            field="monthly_capacity_mw",
        )
        # 场景表按“时间戳 × 资源 ID”提供标幺系数。
        factor = scenarioSet.get_value(scenarioId, resource.id, period)
        return installed_capacity * factor

    return _renewable_constraints(
        optmodel,
        gridData,
        variables,
        list(timeIdx),
        hours_per_step=step_hours(timeIdx),
        available_power=available_power,
    )


def add_renewable_constraints(
    model: Any,
    grid: Grid,
    variables: RenewableVariables,
    periods: Iterable[Hashable],
) -> dict[tuple[str, Hashable, str, str], Any]:
    """兼容旧入口：使用资源自身的逐时系数和固定装机容量。

    正式生产代码应使用 ``setRenewableConstraints``。该入口保留既有测试中的
    ``resource.TSCapacity`` 数据结构，其中值为标幺系数，``capacity`` 为
    固定装机容量；它最终仍调用同一个 ``_renewable_constraints``。
    """
    if isinstance(periods, pd.DatetimeIndex):
        period_list = list(validate_time_index(periods))
        hours_per_step = step_hours(periods)
    else:
        period_list = list(periods)
        if not period_list:
            raise ValueError("periods must not be empty")
        hours_per_step = 1.0

    def available_power(resource: Any, period: Hashable) -> float:
        """按旧数据结构计算 ``capacity × TSCapacity[period]``。"""
        if period not in resource.TSCapacity:
            raise ValueError(
                f"{resource.id} missing time-series value for period {period}"
            )
        factor = finite_nonnegative(
            resource.TSCapacity[period],
            owner=resource.id,
            field="TSCapacity",
        )
        return finite_nonnegative(
            resource.capacity,
            owner=resource.id,
            field="capacity",
        ) * factor

    return _renewable_constraints(
        model,
        grid,
        variables,
        period_list,
        hours_per_step=hours_per_step,
        available_power=available_power,
    )
