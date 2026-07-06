# -*- coding: utf-8 -*-
"""分区功率平衡约束。"""

import math
from collections.abc import Mapping

import pandas as pd
import pyoptinterface as poi

from src.model.grid import Grid
from src.model.zone import Zone
from src.optim.opt_model import OptModel


def setPowerBalanceCons(
    optmodel: OptModel,
    gridData: Grid,
    timeIdx: pd.DatetimeIndex,
    *,
    include_load_shedding: bool = False,
    fixed_external_injection_mw: Mapping[tuple[str, pd.Timestamp], float]
    | None = None,
) -> None:
    """为每个分区添加逐时功率平衡。

    ``fixed_external_injection_mw`` 使用正值表示外部电网向省内分区注入。
    失负荷变量只有在调用方显式创建并启用后才进入平衡，保持旧调用兼容。
    """

    # 每个 Zone 独立建立平衡等式，联络线变量负责分区之间的耦合。
    for zone in gridData.zones.values():
        setZonePowerBalanceCons(
            optmodel,
            zone,
            gridData,
            timeIdx,
            include_load_shedding=include_load_shedding,
            fixed_external_injection_mw=fixed_external_injection_mw,
        )


def setZonePowerBalanceCons(
    optmodel: OptModel,
    zone: Zone,
    gridData: Grid,
    timeIdx: pd.DatetimeIndex,
    constype: str = "P",
    *,
    include_load_shedding: bool = False,
    fixed_external_injection_mw: Mapping[tuple[str, pd.Timestamp], float]
    | None = None,
) -> None:
    """汇总分区内资源与联络线，使净注入等于零。"""

    # 每个调度时段建立一条“供给-需求+净流入=0”的等式。
    for t in timeIdx:
        # 空表达式从 0 开始，随后按资源类型逐项累加。
        expr = poi.ExprBuilder()

        # 火电、水电、风电、光伏都作为正向电源出力加入平衡式。
        for resource_type in ("THERMAL", "HYDRO", "WIND", "PV"):
            for res in gridData.getResListFromZoneAndType(zone.id, resource_type):
                expr += optmodel.getVar(res.id, t, "P")

        # 储能放电 PD 是供给，充电 PC 是额外用电需求。
        for storage in gridData.getResListFromZoneAndType(zone.id, "STORAGE"):
            expr += optmodel.getVar(storage.id, t, "P", "PD")
            expr -= optmodel.getVar(storage.id, t, "P", "PC")

        # 负荷是固定需求，因此从表达式中扣除其逐时 MW 值。
        for load in gridData.getResListFromZoneAndType(zone.id, "LOAD"):
            demand = _series_value(load, t)
            expr -= demand
            if include_load_shedding:
                shed = optmodel.getVar(load.id, t, "P", "shed")
                expr += shed
                # 失负荷不能超过该负荷资源当前时段的实际需求。
                optmodel.addCons(
                    (load.id, t, "P_SHED", "2.9.3"),
                    shed,
                    poi.Leq,
                    demand,
                )

        if fixed_external_injection_mw is not None:
            injection = float(
                fixed_external_injection_mw.get((zone.id, t), 0.0)
            )
            if not math.isfinite(injection):
                raise ValueError(
                    f"External injection must be finite: {(zone.id, t)}"
                )
            expr += injection

        # 正潮流定义为 fromZone -> toZone：终点加流入，起点减流出。
        for line in gridData.intertrans.values():
            flow = optmodel.getVar(line.id, t, "P")
            if line.toZone == zone.id:
                expr += flow
            if line.fromZone == zone.id:
                expr -= flow

        # 净注入等于零即得到该分区、该时段的功率平衡等式。
        optmodel.addCons((zone.id, t, constype, "2.9.1"), expr, poi.Eq)


def _series_value(resource, period) -> float:
    """读取负荷时序值，并在需要时从标幺值换算为 MW。"""

    # 缺失任一调度时段会导致平衡式不完整，因此直接报错。
    if period not in resource.TSCapacity:
        raise ValueError(f"Missing time-series value: {(resource.id, period)}")
    # 数据层已完成中文字段和单位清洗，这里只转换为浮点数。
    value = float(resource.TSCapacity[period])
    # 标幺时序需要乘资源容量才能得到实际 MW。
    if resource.isPU:
        value *= float(resource.capacity)
    # 负荷必须是有限非负数，避免 NaN 或负需求进入模型。
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"Time-series value must be finite and nonnegative: {resource.id}")
    return value
