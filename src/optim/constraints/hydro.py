# -*- coding: utf-8 -*-
"""水电与流域约束，对齐参考项目 hydromodel.py 的 2.3.1—2.3.3。

本模块保留单台水电机组的出力变量，但流域过程约束作用于流域内所有机组
出力之和：

- 2.3.1：流域总出力不超过“预想出力系数 × 流域装机容量”；
- 2.3.2：流域总出力不低于“强迫出力系数 × 流域装机容量”；
- 2.3.3：自然月内累计发电量等于“月平均系数 × 流域容量 × 月时长”。

功率单位为 MW，月度累计电量单位为 MWh。与参考模型一致，不额外添加
单机 ``Pmin`` 硬约束。
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from collections.abc import Collection, Hashable, Iterable, Mapping
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
from src.optim.variables import HydroVariables


def get_month_from_hour(hour: int) -> int:
    """兼容旧入口：把2030年内小时序号换算为自然月。"""
    timestamp = pd.Timestamp("2030-01-01") + pd.Timedelta(hours=int(hour))
    return int(timestamp.month)


def _add_constraint(
    target: Any,
    key: tuple[str, Hashable, str, str],
    expression: Any,
    sense: Any,
    rhs: float = 0.0,
) -> Any:
    """兼容项目 OptModel 和底层求解器模型的约束添加接口。

    正式流程传入 OptModel，约束会使用结构化 ``key`` 登记；旧测试可直接
    传入 pyoptinterface 模型，此时将同一个 key 转成约束名称。
    """
    if hasattr(target, "addCons"):
        return target.addCons(key, expression, sense, rhs)
    return target.add_linear_constraint(
        expression,
        sense,
        rhs,
        name=str(key),
    )


def _period_pairs(
    periods: Iterable[Hashable],
) -> tuple[list[tuple[Hashable, pd.Timestamp]], float]:
    """同时保留变量索引和用于自然月判断的真实时间戳。

    正式入口直接使用 DatetimeIndex，并按真实间隔返回小时步长。旧入口可能
    使用整数时段，因此按 2030-01-01 起的逐小时序列映射，仅用于兼容测试。
    """
    if isinstance(periods, pd.DatetimeIndex):
        time_idx = validate_time_index(periods)
        return list(zip(time_idx, time_idx)), step_hours(time_idx)

    original = list(periods)
    if not original:
        raise ValueError("periods must not be empty")
    timestamps = pd.date_range("2030-01-01", periods=len(original), freq="h")
    return list(zip(original, timestamps)), 1.0


def _hydro_constraints(
    target: Any,
    grid: Grid,
    variables: HydroVariables,
    periods: Iterable[Hashable],
    *,
    strict_monthly_data: bool,
    prior_month_energy_mwh: Mapping[tuple[str, int, int], float] | None = None,
    closed_months: Collection[tuple[int, int]] | None = None,
) -> dict[tuple[str, Hashable, str, str], Any]:
    """构造全部水电约束并返回“约束键—求解器约束”映射。

    ``strict_monthly_data=True`` 用于正式生产接口：预想、强迫、平均三个
    月度过程缺少任一项就立即报错。兼容入口设为 False，可运行不含流域过程
    数据的历史小算例，但不会伪造缺失值。
    """
    period_pairs, hours_per_step = _period_pairs(periods)
    constraints: dict[tuple[str, Hashable, str, str], Any] = {}

    # 单机出力：变量创建时已设置 P >= 0，此处补充 P <= Pmax。
    # 参考项目不设置单机 Pmin，流域强迫出力下限由 2.3.2 统一控制。
    for hydro in grid.getResListFromType("HYDRO"):
        p_max = finite_nonnegative(hydro.Pmax, owner=hydro.id, field="Pmax")
        for period, _ in period_pairs:
            key = (hydro.id, period, "P_MAX", "2.3.Pmax")
            constraints[key] = _add_constraint(
                target,
                key,
                variables.power[hydro.id, period],
                poi.Leq,
                p_max,
            )

    # 流域约束必须按分区逐个遍历 Basin，因为每个 Basin 保存自己的机组集合
    # 和三类月度过程系数。空流域不产生约束。
    for zone in grid.zones.values():
        for basin in zone.basinDict.values():
            if not basin.hydroDict:
                continue
            capacity = finite_nonnegative(
                basin.capacity, owner=basin.id, field="capacity"
            )
            if capacity <= 0.0:
                raise ValueError(f"{basin.id} field 'capacity' must be positive")
            basin_owner = f"{zone.id}:{basin.id}"

            # 按 (年, 月) 分组，避免跨年时把相同月份错误合并。
            month_groups: dict[tuple[int, int], list[tuple[Hashable, pd.Timestamp]]] = (
                defaultdict(list)
            )
            for period, timestamp in period_pairs:
                month_groups[(timestamp.year, timestamp.month)].append(
                    (period, timestamp)
                )
                # 流域总出力 P_basin,t = Σ P_hydro,t，不额外创建聚合变量。
                expression = poi.ExprBuilder()
                for hydro_id in basin.hydroDict:
                    expression += variables.power[hydro_id, period]

                if basin.predicted:
                    predicted = month_value(
                        basin.predicted,
                        timestamp,
                        owner=basin.id,
                        field="predicted",
                    )
                    if predicted > 1.0:
                        raise ValueError(
                            f"{basin_owner} predicted must be in [0, 1]"
                        )
                    # 2.3.1：ΣP_h,t <= predicted_month × basin_capacity。
                    key = (basin_owner, period, "P", "2.3.1")
                    constraints[key] = _add_constraint(
                        target,
                        key,
                        expression,
                        poi.Leq,
                        predicted * capacity,
                    )
                elif strict_monthly_data:
                    raise ValueError(
                        f"{basin.id} missing field 'predicted' for month "
                        f"{timestamp:%Y-%m}"
                    )

                if basin.forced:
                    forced = month_value(
                        basin.forced,
                        timestamp,
                        owner=basin.id,
                        field="forced",
                    )
                    if forced > 1.0:
                        raise ValueError(
                            f"{basin_owner} forced must be in [0, 1]"
                        )
                    if basin.predicted and forced > predicted:
                        raise ValueError(
                            f"{basin_owner} forced exceeds predicted for "
                            f"{timestamp:%Y-%m}"
                        )
                    # 2.3.2：ΣP_h,t >= forced_month × basin_capacity。
                    key = (basin_owner, period, "P", "2.3.2")
                    constraints[key] = _add_constraint(
                        target,
                        key,
                        expression,
                        poi.Geq,
                        forced * capacity,
                    )
                elif strict_monthly_data:
                    raise ValueError(
                        f"{basin.id} missing field 'forced' for month "
                        f"{timestamp:%Y-%m}"
                    )

            # 2.3.3 按自然月建立一条电量等式。若模拟窗口只覆盖部分月份，
            # 等式仅对窗口内实际时段求和，右端也使用相同的时段数量。
            for (_, _), month_periods in month_groups.items():
                first_timestamp = month_periods[0][1]
                if not basin.average:
                    if strict_monthly_data:
                        raise ValueError(
                            f"{basin.id} missing field 'average' for month "
                            f"{first_timestamp:%Y-%m}"
                        )
                    continue
                average = month_value(
                    basin.average,
                    first_timestamp,
                    owner=basin.id,
                    field="average",
                )
                if average > 1.0:
                    raise ValueError(
                        f"{basin_owner} average must be in [0, 1]"
                    )
                if basin.forced and basin.predicted:
                    forced = month_value(
                        basin.forced,
                        first_timestamp,
                        owner=basin.id,
                        field="forced",
                    )
                    predicted = month_value(
                        basin.predicted,
                        first_timestamp,
                        owner=basin.id,
                        field="predicted",
                    )
                    if not forced <= average <= predicted:
                        raise ValueError(
                            f"{basin_owner} requires 0 <= forced <= average <= "
                            f"predicted <= 1 for {first_timestamp:%Y-%m}"
                        )

                year_month = (first_timestamp.year, first_timestamp.month)
                rolling_mode = (
                    prior_month_energy_mwh is not None
                    or closed_months is not None
                )
                if rolling_mode and (
                    closed_months is None or year_month not in closed_months
                ):
                    continue
                # 左端 Σ(P_h,t × Δt) 将 MW 按时间步长换算为 MWh。
                expression = poi.ExprBuilder()
                for period, _ in month_periods:
                    for hydro_id in basin.hydroDict:
                        expression += (
                            variables.power[hydro_id, period] * hours_per_step
                        )
                month_key = pd.Timestamp(
                    first_timestamp.year, first_timestamp.month, 1
                )
                key = (basin_owner, month_key, "E", "2.3.3")
                if rolling_mode:
                    month_hours = calendar.monthrange(*year_month)[1] * 24.0
                    target_energy = average * capacity * month_hours
                    prior_energy = float(
                        (prior_month_energy_mwh or {}).get(
                            (basin_owner, *year_month),
                            0.0,
                        )
                    )
                    rhs = target_energy - prior_energy
                else:
                    # 右端 = 月平均出力系数 × 流域容量 × 窗口内月时长。
                    target_energy = (
                        average
                        * capacity
                        * len(month_periods)
                        * hours_per_step
                    )
                    rhs = target_energy
                constraints[key] = _add_constraint(
                    target,
                    key,
                    expression,
                    poi.Eq,
                    rhs,
                )

    return constraints


def setHydroConstraints(
    optmodel: Any,
    gridData: Grid,
    timeIdx: pd.DatetimeIndex,
    *,
    prior_month_energy_mwh: Mapping[tuple[str, int, int], float] | None = None,
    closed_months: Collection[tuple[int, int]] | None = None,
) -> dict[tuple[str, Hashable, str, str], Any]:
    """正式接口：读取 OptModel 中已登记的水电变量并建立全部参考约束。

    调用顺序应为 ``setHydroVarList`` 后再调用本函数。正式接口强制校验
    DatetimeIndex，并要求所有涉及月份均具备 predicted、forced、average。
    """
    validate_time_index(timeIdx)
    # HydroVariables 是约束层使用的类型化视图，不创建或复制求解变量。
    variables = HydroVariables(
        power={
            (hydro.id, period): optmodel.getVar(hydro.id, period, "P")
            for hydro in gridData.getResListFromType("HYDRO")
            for period in timeIdx
        }
    )
    return _hydro_constraints(
        optmodel,
        gridData,
        variables,
        timeIdx,
        strict_monthly_data=True,
        prior_month_energy_mwh=prior_month_energy_mwh,
        closed_months=closed_months,
    )


def add_hydro_constraints(
    model: Any,
    grid: Grid,
    variables: HydroVariables,
    periods: Iterable[Hashable],
) -> dict[tuple[str, Hashable, str, str], Any]:
    """兼容直接传入底层模型的历史入口。

    新代码应使用 ``setHydroConstraints``。该入口允许流域月度数据为空，
    仅为旧测试和旧调用链保留，不应作为生产模拟的数据完整性标准。
    """
    return _hydro_constraints(
        model,
        grid,
        variables,
        periods,
        strict_monthly_data=False,
    )
