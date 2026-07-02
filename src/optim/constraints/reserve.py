# -*- coding: utf-8 -*-
"""系统旋转备用约束。"""

import math

import pandas as pd
import pyoptinterface as poi

from src.model.grid import Grid
from src.optim.opt_model import OptModel


def setSystemReserveCons(
    optmodel: OptModel,
    gridData: Grid,
    timeIdx: pd.DatetimeIndex,
    constype: str = "R",
) -> None:
    """在线火电剩余容量必须覆盖系统备用需求。"""

    # 火电提供旋转备用，RESERVE 资源描述各时段需要覆盖的需求。
    thermal_resources = gridData.getResListFromType("THERMAL")
    reserve_resources = gridData.getResListFromType("RESERVE")

    # 每个调度时段独立检查系统总上备用是否充足。
    for t in timeIdx:
        # 表达式左端最终表示“可用备用减去备用需求”。
        expr = poi.ExprBuilder()
        # 在线容量 Pmax*CU 减实际出力 P，得到每台机组的剩余上调空间。
        for thermal in thermal_resources:
            expr += (
                thermal.Pmax * optmodel.getVar(thermal.id, t, "CU")
                - optmodel.getVar(thermal.id, t, "P")
            )
        # 多个备用需求资源可直接累计，例如不同类别或不同区域需求。
        for reserve in reserve_resources:
            expr -= _reserve_value(reserve, t)

        # 表达式大于等于零表示系统可用备用覆盖全部需求。
        optmodel.addCons((gridData.id, t, constype, "2.9.2"), expr, poi.Geq)


def _reserve_value(resource, period) -> float:
    """读取并校验单个备用资源在指定时段的需求。"""

    # 每个备用资源必须覆盖全部建模时段。
    if period not in resource.TSCapacity:
        raise ValueError(f"Missing reserve requirement for period {period}")
    # 将对象字段转换为模型使用的标准浮点数。
    value = float(resource.TSCapacity[period])
    # 标幺需求乘 capacity 后转换为 MW。
    if resource.isPU:
        value *= float(resource.capacity)
    # 备用需求不允许为负、NaN 或无穷大。
    if not math.isfinite(value) or value < 0.0:
        raise ValueError("Reserve requirement must be finite and nonnegative")
    return value
