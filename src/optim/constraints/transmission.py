import math
from dataclasses import dataclass
from typing import Any, Hashable, Iterable, Mapping

import pyoptinterface as poi

from src.optim.variables import TransmissionVariables


ConstraintKey = tuple[str, Hashable]


@dataclass
class TransmissionLimitConstraints:
    """区域间输电断面上下限约束句柄。"""

    lower: dict[ConstraintKey, Any]
    upper: dict[ConstraintKey, Any]


def add_transmission_limit_constraints(
    model: Any,
    variables: TransmissionVariables,
    line_ids: Iterable[str],
    periods: Iterable[Hashable],
    flow_min_mw: Mapping[str, float],
    flow_max_mw: Mapping[str, float],
) -> TransmissionLimitConstraints:
    """添加区域间可控断面的正向和反向输送限制。"""

    line_ids = tuple(line_ids)
    periods = tuple(periods)

    lower_constraints = {}
    upper_constraints = {}

    for line_id in line_ids:
        if line_id not in flow_min_mw or line_id not in flow_max_mw:
            raise ValueError(f"断面 {line_id} 缺少输送上下限参数")

        minimum = float(flow_min_mw[line_id])
        maximum = float(flow_max_mw[line_id])

        if not math.isfinite(minimum) or not math.isfinite(maximum):
            raise ValueError(f"断面 {line_id} 的输送上下限必须是有限数值")

        if maximum < minimum:
            raise ValueError(f"断面 {line_id} 的输送上下限不合法")

        for period in periods:
            key = (line_id, period)

            if key not in variables.flow:
                raise KeyError(f"缺少断面变量索引: {key}")

            flow = variables.flow[key]

            lower_constraints[key] = model.add_linear_constraint(
                flow,
                poi.Geq,
                minimum,
                name=f"transmission_lower[{line_id},{period}]",
            )
            upper_constraints[key] = model.add_linear_constraint(
                flow,
                poi.Leq,
                maximum,
                name=f"transmission_upper[{line_id},{period}]",
            )

    return TransmissionLimitConstraints(
        lower=lower_constraints,
        upper=upper_constraints,
    )