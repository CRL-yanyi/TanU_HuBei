import math
from dataclasses import dataclass
from typing import Any, Hashable, Iterable, Mapping, Sequence

import pyoptinterface as poi


VariableKey = tuple[str, Hashable]
BalanceKey = tuple[str, Hashable]


@dataclass(frozen=True)
class ZonalVariableGroup:
    """一组需要接入分区功率平衡的资源变量。"""

    variables: Mapping[VariableKey, Any]
    resource_zones: Mapping[str, str]
    coefficient: float = 1.0


@dataclass
class PowerBalanceConstraints:
    """分区逐时功率平衡约束句柄。"""

    balance: dict[BalanceKey, Any]


def add_power_balance_constraints(
    model: Any,
    zones: Iterable[str],
    periods: Iterable[Hashable],
    demand_mw: Mapping[BalanceKey, float],
    supply_groups: Sequence[ZonalVariableGroup] = (),
    demand_groups: Sequence[ZonalVariableGroup] = (),
    transmission_flow: Mapping[VariableKey, Any] | None = None,
    line_from_zone: Mapping[str, str] | None = None,
    line_to_zone: Mapping[str, str] | None = None,
    fixed_external_injection_mw: Mapping[BalanceKey, float] | None = None,
) -> PowerBalanceConstraints:
    """添加逐分区、逐时功率平衡约束。"""

    zones = tuple(zones)
    periods = tuple(periods)
    transmission_flow = transmission_flow or {}
    line_from_zone = line_from_zone or {}
    line_to_zone = line_to_zone or {}
    fixed_external_injection_mw = fixed_external_injection_mw or {}

    if len(zones) != len(set(zones)):
        raise ValueError("分区 ID 不能重复")

    if len(periods) != len(set(periods)):
        raise ValueError("时间索引不能重复")

    if set(line_from_zone) != set(line_to_zone):
        raise ValueError("断面起点和终点映射必须包含相同的断面 ID")

    zone_set = set(zones)

    for line_id in line_from_zone:
        if line_from_zone[line_id] not in zone_set:
            raise ValueError(f"断面 {line_id} 的起点分区不存在")
        if line_to_zone[line_id] not in zone_set:
            raise ValueError(f"断面 {line_id} 的终点分区不存在")

    balance_constraints = {}

    for zone in zones:
        for period in periods:
            key = (zone, period)

            if key not in demand_mw:
                raise ValueError(f"缺少分区负荷参数: {key}")

            demand = float(demand_mw[key])
            external_injection = float(
                fixed_external_injection_mw.get(key, 0.0)
            )

            if not math.isfinite(demand) or demand < 0.0:
                raise ValueError(f"分区负荷必须是有限非负数: {key}")

            if not math.isfinite(external_injection):
                raise ValueError(f"外来固定注入必须是有限数值: {key}")

            expression = poi.ExprBuilder()
            expression += external_injection - demand

            for group in supply_groups:
                expression += _sum_group_for_zone(group, zone, period)

            for group in demand_groups:
                expression -= _sum_group_for_zone(group, zone, period)

            for line_id, from_zone in line_from_zone.items():
                flow_key = (line_id, period)
                if flow_key not in transmission_flow:
                    raise KeyError(f"缺少断面变量索引: {flow_key}")

                flow = transmission_flow[flow_key]
                to_zone = line_to_zone[line_id]

                if zone == from_zone:
                    expression -= flow
                if zone == to_zone:
                    expression += flow

            balance_constraints[key] = model.add_linear_constraint(
                expression,
                poi.Eq,
                0.0,
                name=f"power_balance[{zone},{period}]",
            )

    return PowerBalanceConstraints(balance=balance_constraints)


def _sum_group_for_zone(
    group: ZonalVariableGroup,
    zone: str,
    period: Hashable,
):
    """汇总一个资源变量组在指定分区和时段的功率。"""

    expression = poi.ExprBuilder()

    for resource_id, resource_zone in group.resource_zones.items():
        if resource_zone != zone:
            continue

        key = (resource_id, period)
        if key not in group.variables:
            raise KeyError(f"缺少资源变量索引: {key}")

        expression += group.coefficient * group.variables[key]

    return expression