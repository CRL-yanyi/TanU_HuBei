from dataclasses import dataclass
from typing import Any, Hashable, Iterable

import pyoptinterface as poi


VariableKey = tuple[str, Hashable]


@dataclass
class ThermalVariables:
    """火电机组组合变量集合。"""

    power: dict[VariableKey, Any]
    is_on: dict[VariableKey, Any]
    startup: dict[VariableKey, Any]
    shutdown: dict[VariableKey, Any]


def add_thermal_variables(
    model: Any,
    unit_ids: Iterable[str],
    periods: Iterable[Hashable],
) -> ThermalVariables:
    """创建火电出力、开机、启动和停机变量。"""

    unit_ids = tuple(unit_ids)
    periods = tuple(periods)

    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError("火电机组 ID 不能重复")

    if len(periods) != len(set(periods)):
        raise ValueError("时间索引不能重复")

    keys = [
        (unit_id, period)
        for unit_id in unit_ids
        for period in periods
    ]

    power = model.add_variables(
        keys,
        lb=0.0,
        domain=poi.VariableDomain.Continuous,
        name="thermal_power",
    )
    is_on = model.add_variables(
        keys,
        domain=poi.VariableDomain.Binary,
        name="thermal_is_on",
    )
    startup = model.add_variables(
        keys,
        domain=poi.VariableDomain.Binary,
        name="thermal_startup",
    )
    shutdown = model.add_variables(
        keys,
        domain=poi.VariableDomain.Binary,
        name="thermal_shutdown",
    )

    return ThermalVariables(
        power=power,
        is_on=is_on,
        startup=startup,
        shutdown=shutdown,
    )