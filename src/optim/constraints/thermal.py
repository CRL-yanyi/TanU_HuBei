import math
from dataclasses import dataclass
from typing import Any, Hashable, Iterable, Mapping

import pyoptinterface as poi

from src.optim.variables import ThermalVariables


ConstraintKey = tuple[str, Hashable]


@dataclass
class ThermalCapacityConstraints:
    """火电出力上下限约束句柄。"""

    lower: dict[ConstraintKey, Any]
    upper: dict[ConstraintKey, Any]


def add_thermal_capacity_constraints(
    model: Any,
    variables: ThermalVariables,
    unit_ids: Iterable[str],
    periods: Iterable[Hashable],
    p_min_mw: Mapping[str, float],
    p_max_mw: Mapping[str, float],
) -> ThermalCapacityConstraints:
    """添加火电机组出力上下限约束。"""

    unit_ids = tuple(unit_ids)
    periods = tuple(periods)

    lower_constraints = {}
    upper_constraints = {}

    for unit_id in unit_ids:
        if unit_id not in p_min_mw or unit_id not in p_max_mw:
            raise ValueError(f"机组 {unit_id} 缺少出力上下限参数")

        minimum = float(p_min_mw[unit_id])
        maximum = float(p_max_mw[unit_id])

        if not math.isfinite(minimum) or not math.isfinite(maximum):
            raise ValueError(f"机组 {unit_id} 的出力上下限必须是有限数值")

        if minimum < 0.0 or maximum < minimum:
            raise ValueError(f"机组 {unit_id} 的出力上下限不合法")

        for period in periods:
            key = (unit_id, period)

            if key not in variables.power or key not in variables.is_on:
                raise KeyError(f"缺少火电变量索引: {key}")

            power = variables.power[key]
            is_on = variables.is_on[key]

            lower_constraints[key] = model.add_linear_constraint(
                power - minimum * is_on,
                poi.Geq,
                0.0,
                name=f"thermal_capacity_lower[{unit_id},{period}]",
            )
            upper_constraints[key] = model.add_linear_constraint(
                power - maximum * is_on,
                poi.Leq,
                0.0,
                name=f"thermal_capacity_upper[{unit_id},{period}]",
            )

    return ThermalCapacityConstraints(
        lower=lower_constraints,
        upper=upper_constraints,
    )