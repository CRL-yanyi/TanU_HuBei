# -*- coding: utf-8 -*-
import math
from typing import Any, Hashable, Iterable, Mapping, Sequence

import pyoptinterface as poi

from src.model.grid import Grid


VariableKey = tuple[str, Hashable]
BalanceKey = tuple[str, Hashable]


def add_power_balance_constraints(
    model: Any,
    grid: Grid,
    periods: Iterable[Hashable],
    demand_mw: Mapping[BalanceKey, float],
    supply_groups: Sequence[Mapping[str, Any]] = (),
    demand_groups: Sequence[Mapping[str, Any]] = (),
    transmission_flow: Mapping[VariableKey, Any] | None = None,
    fixed_external_injection_mw: Mapping[BalanceKey, float] | None = None,
) -> dict[str, Any]:
    """添加分区功率平衡约束，按 Grid 分区和跨区断面组织表达式。"""

    periods = tuple(periods)
    transmission_flow = transmission_flow or {}
    fixed_external_injection_mw = fixed_external_injection_mw or {}
    constraints: dict[str, Any] = {}

    # 1. 对每个分区、每个时段建立一条功率平衡等式
    for zone_id in grid.zones:
        for period in periods:
            key = (zone_id, period)
            if key not in demand_mw:
                raise ValueError(f"Missing zonal demand: {key}")

            demand = float(demand_mw[key])
            injection = float(fixed_external_injection_mw.get(key, 0.0))
            if not math.isfinite(demand) or demand < 0.0:
                raise ValueError(f"Demand must be finite and nonnegative: {key}")
            if not math.isfinite(injection):
                raise ValueError(f"External injection must be finite: {key}")

            # 1.1 平衡式初值：固定外部注入 - 本地负荷
            expr = poi.ExprBuilder()
            expr += injection - demand

            # 1.2 供给侧资源：火电、水电、新能源、储能放电等
            for group in supply_groups:
                expr += _sum_group_for_zone(group, zone_id, period)

            # 1.3 需求侧资源：储能充电、抽水等
            for group in demand_groups:
                expr -= _sum_group_for_zone(group, zone_id, period)

            # 1.4 跨区潮流：fromZone 流出为负，toZone 流入为正
            for line in grid.intertrans.values():
                flow_key = (line.id, period)
                if flow_key not in transmission_flow:
                    raise KeyError(f"Missing transmission flow variable: {flow_key}")

                flow = transmission_flow[flow_key]
                if zone_id == line.fromZone:
                    expr -= flow
                if zone_id == line.toZone:
                    expr += flow

            constraints[f"power_balance_{zone_id}_{period}"] = (
                model.add_linear_constraint(
                    expr,
                    poi.Eq,
                    0.0,
                    name=f"power_balance[{zone_id},{period}]",
                )
            )

    return constraints


def _sum_group_for_zone(
    group: Mapping[str, Any],
    zone_id: str,
    period: Hashable,
) -> Any:
    # 2. 资源组按 resource_zones 过滤，只汇总属于当前分区的变量
    variables = group["variables"]
    resource_zones = group["resource_zones"]
    coefficient = float(group.get("coefficient", 1.0))

    expr = poi.ExprBuilder()
    for resource_id, resource_zone in resource_zones.items():
        if resource_zone != zone_id:
            continue

        key = (resource_id, period)
        if key not in variables:
            raise KeyError(f"Missing resource variable: {key}")

        expr += coefficient * variables[key]

    return expr
