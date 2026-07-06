# -*- coding: utf-8 -*-
"""成员3目标函数。"""

import math

import pandas as pd
import pyoptinterface as poi

from src.model.grid import Grid
from src.model.resource import Thermal
from src.optim.opt_model import OptModel


def setThermalObjective(
    optmodel: OptModel,
    gridData: Grid,
    timeIdx: pd.DatetimeIndex,
) -> None:
    """薄入口：累计全部火电成本并设置最小化目标。"""

    # 每次构建总目标前先清空旧表达式，避免重复调用导致成本重复累计。
    optmodel.obj = poi.ExprBuilder()
    # 各机组成本相互独立，逐台累加到统一目标表达式。
    for thermal in gridData.getResListFromType("THERMAL"):
        setThermalCostObj(optmodel, thermal, timeIdx)
    # 全部成本项加入后，统一设置为最小化目标。
    optmodel.setObjective(poi.ObjectiveSense.Minimize)


def setProductionObjective(
    optmodel: OptModel,
    gridData: Grid,
    timeIdx: pd.DatetimeIndex,
    *,
    include_load_shedding: bool = False,
) -> None:
    """设置首期生产模拟完整目标函数。

    目标包含火电发电与启停成本、弃风弃光惩罚；启用失负荷时再加入
    ``Load.curtailmentPenalty × P/shed``。所有功率成本均乘时间步长，
    将元/MWh与MW正确换算为元。
    """
    optmodel.obj = poi.ExprBuilder()
    for thermal in gridData.getResListFromType("THERMAL"):
        setThermalCostObj(optmodel, thermal, timeIdx)

    step_hours = _step_hours(timeIdx)
    for renewable_type in ("WIND", "PV"):
        for resource in gridData.getResListFromType(renewable_type):
            penalty = float(resource.curtailmentPenalty)
            for period in timeIdx:
                optmodel.obj += (
                    penalty
                    * step_hours
                    * optmodel.getVar(resource.id, period, "P", "curt")
                )

    if include_load_shedding:
        for load in gridData.getResListFromType("LOAD"):
            penalty = float(load.curtailmentPenalty)
            for period in timeIdx:
                optmodel.obj += (
                    penalty
                    * step_hours
                    * optmodel.getVar(load.id, period, "P", "shed")
                )

    optmodel.setObjective(poi.ObjectiveSense.Minimize)


def setThermalCostObj(
    optmodel: OptModel,
    res: Thermal,
    timeIdx: pd.DatetimeIndex,
) -> None:
    """累计单台火电的发电、启动和停机成本。"""

    # MW 乘时段小时数得到 MWh，用于计算电量成本。
    step_hours = _step_hours(timeIdx)
    # 优先使用 TanU 命名 linearCost；缺省时兼容成员1的 variableCost。
    linear_cost = res.linearCost
    if linear_cost is None:
        linear_cost = res.variableCost
    # 确保成本参数参与表达式前是标准浮点数。
    linear_cost = float(linear_cost)
    # 每个时段分别累计发电成本、启动成本和停机成本。
    for t in timeIdx:
        optmodel.obj += (
            linear_cost * step_hours * optmodel.getVar(res.id, t, "P")
            + res.startUpCost * optmodel.getVar(res.id, t, "CV")
            + res.shutDownCost * optmodel.getVar(res.id, t, "CW")
        )


def _step_hours(timeIdx: pd.DatetimeIndex) -> float:
    """从 DatetimeIndex 推导目标函数使用的小时步长。"""

    # 多时段使用前两个相邻时间戳的实际差值。
    if len(timeIdx) >= 2:
        hours = (timeIdx[1] - timeIdx[0]) / pd.Timedelta(hours=1)
    # 单时段优先读取 DatetimeIndex 自带频率。
    elif timeIdx.freq is not None:
        hours = timeIdx.freq.nanos / (3600 * 1e9)
    # 无频率的单时段算例按项目默认的一小时处理。
    else:
        hours = 1.0
    # 非正步长无法将功率换算为电量，应立即阻止建模。
    if not math.isfinite(hours) or hours <= 0.0:
        raise ValueError("timeIdx frequency must be positive")
    return float(hours)
