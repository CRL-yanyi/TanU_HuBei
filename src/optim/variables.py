# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Any, Hashable, Iterable

import pyoptinterface as poi


VariableKey = tuple[str, Hashable]


def setThermalVarList(optmodel, gridData, timeIdx):
    """创建火电出力和启停变量，直接登记到 ``optmodel.vars``。"""

    # 从 Grid 统一取得火电 ID，变量创建函数不再接收额外 ID 列表。
    thermal_ids = gridData.getResIdListFromType("THERMAL")
    # P 是非负连续出力变量，单位为 MW。
    optmodel.setVarList(thermal_ids, timeIdx, "P", lb=0.0)
    # C 会一次创建 CU、CV、CW 三类 0/1 机组组合变量。
    optmodel.setVarList(thermal_ids, timeIdx, "C", lb=0.0, ub=1.0)



def setIntertranVarList(optmodel, gridData, timeIdx):
    """创建可双向取值的区域间输电功率变量。"""

    # 负值表示反向潮流；真实上下限由 transmission.py 的断面约束给出。
    optmodel.setVarList(gridData.intertrans, timeIdx, "P", lb=-1e8, ub=1e8)


@dataclass
class HydroVariables:
    """水电机组决策变量集合。"""

    power: dict[VariableKey, Any]


def add_hydro_variables(
    model: Any,
    unit_ids: Iterable[str],
    periods: Iterable[Hashable],
) -> HydroVariables:
    """创建水电机组出力变量。"""

    unit_ids = tuple(unit_ids)
    periods = tuple(periods)

    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError("水电机组 ID 不能重复")

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
        name="hydro_power",
    )

    return HydroVariables(power=power)


@dataclass
class StorageVariables:
    """储能机组决策变量集合。"""

    charge_power: dict[VariableKey, Any]
    discharge_power: dict[VariableKey, Any]
    energy: dict[VariableKey, Any]
    is_charging: dict[VariableKey, Any]
    is_discharging: dict[VariableKey, Any]


def add_storage_variables(
    model: Any,
    unit_ids: Iterable[str],
    periods: Iterable[Hashable],
    relax_binary: bool = False,
) -> StorageVariables:
    """创建储能及抽蓄决策变量。"""

    unit_ids = tuple(unit_ids)
    periods = tuple(periods)

    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError("储能机组 ID 不能重复")

    if len(periods) != len(set(periods)):
        raise ValueError("时间索引不能重复")

    keys = [
        (unit_id, period)
        for unit_id in unit_ids
        for period in periods
    ]

    charge_power = model.add_variables(
        keys,
        lb=0.0,
        domain=poi.VariableDomain.Continuous,
        name="storage_charge",
    )
    discharge_power = model.add_variables(
        keys,
        lb=0.0,
        domain=poi.VariableDomain.Continuous,
        name="storage_discharge",
    )
    energy = model.add_variables(
        keys,
        lb=0.0,
        domain=poi.VariableDomain.Continuous,
        name="storage_energy",
    )

    state_domain = (
        poi.VariableDomain.Continuous if relax_binary else poi.VariableDomain.Binary
    )

    is_charging = model.add_variables(
        keys,
        lb=0.0,
        ub=1.0,
        domain=state_domain,
        name="storage_is_charging",
    )
    is_discharging = model.add_variables(
        keys,
        lb=0.0,
        ub=1.0,
        domain=state_domain,
        name="storage_is_discharging",
    )

    return StorageVariables(
        charge_power=charge_power,
        discharge_power=discharge_power,
        energy=energy,
        is_charging=is_charging,
        is_discharging=is_discharging,
    )


@dataclass
class RenewableVariables:
    """新能源（风电、光伏）机组决策变量集合。"""

    power: dict[VariableKey, Any]
    curtailment: dict[VariableKey, Any]


def add_renewable_variables(
    model: Any,
    unit_ids: Iterable[str],
    periods: Iterable[Hashable],
) -> RenewableVariables:
    """创建新能源机组出力与弃电变量。"""

    unit_ids = tuple(unit_ids)
    periods = tuple(periods)

    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError("新能源机组 ID 不能重复")

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
        name="renewable_power",
    )
    curtailment = model.add_variables(
        keys,
        lb=0.0,
        domain=poi.VariableDomain.Continuous,
        name="renewable_curtailment",
    )

    return RenewableVariables(
        power=power,
        curtailment=curtailment,
    )
