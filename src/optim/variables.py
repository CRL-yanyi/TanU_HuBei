# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Any, Hashable, Iterable

import pandas as pd
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


@dataclass
class LoadSheddingVariables:
    """分区负荷对应的失负荷功率变量集合。"""

    power: dict[VariableKey, Any]


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


# =============================================================================
# 非火电资源变量接口：统一登记到当前项目的 OptModel
# =============================================================================

def _normalise_time_index(time_idx: pd.DatetimeIndex) -> tuple[pd.Timestamp, ...]:
    """校验正式接口的时间索引，并转为变量创建函数可遍历的元组。

    约束层依赖真实时间戳判断自然月、日末和时间步长，因此正式接口不接受
    ``range`` 等整数序号。这里提前拒绝空索引和重复时刻，避免出现变量重名，
    或者同一时刻被重复计入月度电量与储能能量递推。
    """
    if not isinstance(time_idx, pd.DatetimeIndex):
        raise TypeError("time_idx must be a pandas.DatetimeIndex")
    if time_idx.empty:
        raise ValueError("time_idx must not be empty")
    if time_idx.has_duplicates:
        raise ValueError("time_idx must not contain duplicate timestamps")
    # tuple 保留 Timestamp 本身，不改变时区、日期或分钟精度。
    return tuple(time_idx)


def setHydroVarList(optmodel, gridData, timeIdx: pd.DatetimeIndex) -> HydroVariables:
    """创建并登记水电单机出力变量 ``P[机组, 时段]``，单位为 MW。

    变量下界固定为 0；单机出力上限以及流域预想、强迫和月均电量约束在
    ``setHydroConstraints`` 中添加。此处不设置 ``Pmin``，与参考模型一致。
    """
    periods = _normalise_time_index(timeIdx)
    # Grid 是资源 ID 的唯一来源，确保变量键可被功率平衡直接查询。
    unit_ids = tuple(gridData.getResIdListFromType("HYDRO"))
    optmodel.setVarList(unit_ids, periods, "P", lb=0.0)

    # 返回的轻量包装对象供约束构造器复用；变量本体仍由 OptModel 统一持有。
    return HydroVariables(
        power={
            (unit_id, period): optmodel.getVar(unit_id, period, "P")
            for unit_id in unit_ids
            for period in periods
        }
    )


def setStorageVarList(
    optmodel,
    gridData,
    timeIdx: pd.DatetimeIndex,
    *,
    relax_binary: bool = False,
) -> StorageVariables:
    """创建并登记储能、抽蓄的功率、能量和运行状态变量。

    变量键含义如下：

    - ``P/PC``：充电功率，MW；
    - ``P/PD``：放电功率，MW；
    - ``E``：时段末储能量，MWh；
    - ``CS``：充电状态，取 0 或 1；
    - ``DS``：放电状态，取 0 或 1。

    ``relax_binary=True`` 仅供连续松弛或诊断算例使用，此时 CS、DS 的取值
    区间仍为 [0, 1]，但不再要求整数。正式生产模拟应保留默认值 ``False``。
    """
    periods = _normalise_time_index(timeIdx)
    # 普通电化学储能和抽水蓄能在 Grid 中都归入 STORAGE，使用同一套公式。
    unit_ids = tuple(gridData.getResIdListFromType("STORAGE"))

    # PC、PD 共用主类型 P，通过 idx 区分，保持与 OptModel.getVar 接口一致。
    optmodel.setVarList(unit_ids, periods, "P", idx="PC", lb=0.0)
    optmodel.setVarList(unit_ids, periods, "P", idx="PD", lb=0.0)
    optmodel.setVarList(unit_ids, periods, "E", lb=0.0)

    keys = [(unit_id, period) for unit_id in unit_ids for period in periods]
    state_domain = (
        poi.VariableDomain.Continuous if relax_binary else poi.VariableDomain.Binary
    )
    charging = optmodel.model.add_variables(
        keys,
        lb=0.0,
        ub=1.0,
        domain=state_domain,
        name="storage_is_charging",
    )
    discharging = optmodel.model.add_variables(
        keys,
        lb=0.0,
        ub=1.0,
        domain=state_domain,
        name="storage_is_discharging",
    )
    # 状态变量由底层模型批量创建后登记，后续约束和功率平衡均按统一键读取。
    optmodel.registerVarList(charging, "CS")
    optmodel.registerVarList(discharging, "DS")

    # 包装对象只保存对已登记变量的引用，不会重复创建第二套变量。
    return StorageVariables(
        charge_power={
            key: optmodel.getVar(key[0], key[1], "P", "PC") for key in keys
        },
        discharge_power={
            key: optmodel.getVar(key[0], key[1], "P", "PD") for key in keys
        },
        energy={key: optmodel.getVar(key[0], key[1], "E") for key in keys},
        is_charging={
            key: optmodel.getVar(key[0], key[1], "CS") for key in keys
        },
        is_discharging={
            key: optmodel.getVar(key[0], key[1], "DS") for key in keys
        },
    )


def setRenewableVarList(
    optmodel,
    gridData,
    timeIdx: pd.DatetimeIndex,
) -> RenewableVariables:
    """创建并登记风电、光伏的实际出力和弃电变量，单位均为 MW。

    ``P`` 表示进入功率平衡的实际出力，``P/curt`` 表示同一时段的弃电量。
    约束层通过 ``P + P/curt = 场景系数 × 当月装机容量`` 保证可用功率守恒。
    """
    periods = _normalise_time_index(timeIdx)
    # 风电和光伏数学形式相同，合并为一组资源 ID 批量建模。
    unit_ids = tuple(
        gridData.getResIdListFromType("WIND")
        + gridData.getResIdListFromType("PV")
    )
    optmodel.setVarList(unit_ids, periods, "P", lb=0.0)
    optmodel.setVarList(unit_ids, periods, "P", idx="curt", lb=0.0)

    # 与水电、储能相同，返回值只提供类型清晰的变量字典视图。
    return RenewableVariables(
        power={
            (unit_id, period): optmodel.getVar(unit_id, period, "P")
            for unit_id in unit_ids
            for period in periods
        },
        curtailment={
            (unit_id, period): optmodel.getVar(unit_id, period, "P", "curt")
            for unit_id in unit_ids
            for period in periods
        },
    )


def setLoadSheddingVarList(
    optmodel,
    gridData,
    timeIdx: pd.DatetimeIndex,
) -> LoadSheddingVariables:
    """创建并登记失负荷变量 ``P/shed``，单位为MW。

    这里只设置非负下界；逐时上界由功率平衡模块限制为对应负荷需求。
    """
    periods = _normalise_time_index(timeIdx)
    load_ids = tuple(gridData.getResIdListFromType("LOAD"))
    optmodel.setVarList(load_ids, periods, "P", idx="shed", lb=0.0)
    return LoadSheddingVariables(
        power={
            (load_id, period): optmodel.getVar(
                load_id, period, "P", "shed"
            )
            for load_id in load_ids
            for period in periods
        }
    )
