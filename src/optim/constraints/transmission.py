# -*- coding: utf-8 -*-
"""区域间可控输电约束。"""

import pandas as pd
import pyoptinterface as poi

from src.model.grid import Grid
from src.model.intertran import Intertran
from src.optim.opt_model import OptModel


def setIntertranCons(
    optmodel: OptModel,
    gridData: Grid,
    timeIdx: pd.DatetimeIndex,
) -> None:
    """薄入口：为 Grid 中全部可控断面添加容量约束。"""

    # 每条 Intertran 独立建立正向和反向输电容量限制。
    for intertran in gridData.intertrans.values():
        setIntertranPCons(optmodel, intertran, timeIdx)


def setIntertranPCons(
    optmodel: OptModel,
    res: Intertran,
    timeIdx: pd.DatetimeIndex,
    constype: str = "P",
) -> None:
    """断面潮流范围：``-capacityFromZone <= P <= capacityToZone``。"""

    # capacityFromZone 表示反向容量，capacityToZone 表示正向容量。
    capacity_from = float(res.capacityFromZone)
    capacity_to = float(res.capacityToZone)
    # 容量参数本身必须非负，方向通过潮流变量正负号表达。
    if capacity_from < 0.0 or capacity_to < 0.0:
        raise ValueError(f"Invalid transmission limits for {res.id}")

    # 停运线路上下限均设为 0；投运线路允许双向潮流。
    lower = -capacity_from if res.status else 0.0
    upper = capacity_to if res.status else 0.0
    # 对每个调度时段建立一对上下限约束。
    for t in timeIdx:
        # P 变量正值表示 fromZone 流向 toZone。
        flow = optmodel.getVar(res.id, t, "P")

        # 下限移项为 flow-lower >= 0，对应公式 2.7.1。
        expr = poi.ExprBuilder()
        expr += flow - lower
        optmodel.addCons((res.id, t, constype, "2.7.1"), expr, poi.Geq)

        # 上限移项为 flow-upper <= 0，对应公式 2.7.2。
        expr = poi.ExprBuilder()
        expr += flow - upper
        optmodel.addCons((res.id, t, constype, "2.7.2"), expr, poi.Leq)
