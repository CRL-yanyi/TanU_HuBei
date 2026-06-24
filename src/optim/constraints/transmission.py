# -*- coding: utf-8 -*-
from typing import Any, Hashable, Iterable

import pyoptinterface as poi

from src.model.grid import Grid
from src.optim.variables import TransmissionVariables


def add_transmission_constraints(
    model: Any,
    grid: Grid,
    variables: TransmissionVariables,
    periods: Iterable[Hashable],
) -> dict[str, Any]:
    """添加区域间输电断面潮流上下限约束。"""

    constraints: dict[str, Any] = {}
    periods = tuple(periods)

    # 1. 按 Grid 中的跨区断面逐时段建立潮流上下限
    for line in grid.intertrans.values():
        # 正方向为 fromZone -> toZone，反方向容量写成负下限
        capacity_from = float(line.capacityFromZone)
        capacity_to = float(line.capacityToZone)
        if capacity_from < 0.0 or capacity_to < 0.0:
            raise ValueError(f"Invalid transmission limits for {line.id}")

        flow_min = -capacity_from#反方向最大容量
        flow_max = capacity_to#正方向最大容量。

        # 1.1 断面停运时强制潮流为 0
        if getattr(line, "status", 1) == 0:
            flow_min = 0.0
            flow_max = 0.0

        if flow_max < flow_min:
            raise ValueError(f"Invalid transmission limits for {line.id}")

        for period in periods:
            key = (line.id, period)
            if key not in variables.flow:
                raise KeyError(f"Missing transmission flow variable: {key}")

            flow = variables.flow[key]
            # 1.2 断面下限：F_l,t >= -capacityFromZone
            constraints[f"transmission_min_{line.id}_{period}"] = (
                model.add_linear_constraint(
                    flow,
                    poi.Geq,
                    flow_min,
                    name=f"transmission_min[{line.id},{period}]",
                )
            )
            # 1.3 断面上限：F_l,t <= capacityToZone
            constraints[f"transmission_max_{line.id}_{period}"] = (
                model.add_linear_constraint(
                    flow,
                    poi.Leq,
                    flow_max,
                    name=f"transmission_max[{line.id},{period}]",
                )
            )

    return constraints
