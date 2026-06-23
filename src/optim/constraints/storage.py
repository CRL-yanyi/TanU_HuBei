# -*- coding: utf-8 -*-
from typing import Any, Hashable, Iterable
import pyoptinterface as poi
from src.model.grid import Grid
from src.optim.variables import StorageVariables

def add_storage_constraints(
    model: Any,
    grid: Grid,
    variables: StorageVariables,
    periods: Iterable[Hashable],
    initial_energy: dict[str, float] = None,
) -> dict[str, Any]:
    """添加储能与抽水蓄能充放电、电量平衡和状态约束。"""
    periods_list = list(periods)
    storage_ids = grid.getResIdListFromType("STORAGE")
    
    constraints = {}

    for s_id in storage_ids:
        storage = grid.getResFromId(s_id)
        
        # 1. 物理参数读取
        p_max = storage.Pmax
        e_max = storage.Emax
        e_min = storage.Emin  # 0.0
        eff_c = storage.effC  # 充电效率
        eff_d = storage.effD  # 放电效率
        
        if initial_energy is not None and s_id in initial_energy:
            e0 = initial_energy[s_id]
        else:
            e0 = storage.E0        # 初始能量

        for idx, t in enumerate(periods_list):
            v_charge = variables.charge_power[s_id, t]
            v_discharge = variables.discharge_power[s_id, t]
            v_energy = variables.energy[s_id, t]
            v_ic = variables.is_charging[s_id, t]
            v_id = variables.is_discharging[s_id, t]

            # 1.1 充放电功率上下限与状态关联约束 (2.4.1 & 2.4.2)
            # PC <= IC * Pmax
            constraints[f"storage_charge_limit_{s_id}_{t}"] = model.add_linear_constraint(
                v_charge - v_ic * p_max, poi.Leq, 0.0,
                name=f"storage_charge_limit_{s_id}_{t}",
            )
            # PD <= ID * Pmax
            constraints[f"storage_discharge_limit_{s_id}_{t}"] = model.add_linear_constraint(
                v_discharge - v_id * p_max, poi.Leq, 0.0,
                name=f"storage_discharge_limit_{s_id}_{t}",
            )

            # 1.2 充放电状态互斥约束 (2.4.5)
            # IC + ID <= 1
            constraints[f"storage_excl_{s_id}_{t}"] = model.add_linear_constraint(
                v_ic + v_id, poi.Leq, 1.0,
                name=f"storage_excl_{s_id}_{t}",
            )

            # 1.3 能量状态上下限约束 (2.4.4)
            # Emin <= E_t <= Emax
            constraints[f"storage_energy_min_{s_id}_{t}"] = model.add_linear_constraint(
                v_energy, poi.Geq, e_min,
                name=f"storage_energy_min_{s_id}_{t}",
            )
            constraints[f"storage_energy_max_{s_id}_{t}"] = model.add_linear_constraint(
                v_energy, poi.Leq, e_max,
                name=f"storage_energy_max_{s_id}_{t}",
            )

            # 1.4 能量状态 (SOC) 递推约束 (2.4.3)
            # 充电增加能量（乘以效率），放电减少能量（除以效率）
            efficiency_term = v_charge * eff_c - v_discharge / eff_d

            if idx > 0:
                # E_t = E_{t-1} + PC*effC - PD/effD
                t_prev = periods_list[idx - 1]
                v_energy_prev = variables.energy[s_id, t_prev]
                constraints[f"storage_soc_trans_{s_id}_{t}"] = model.add_linear_constraint(
                    v_energy - v_energy_prev - efficiency_term, poi.Eq, 0.0,
                    name=f"storage_soc_trans_{s_id}_{t}",
                )
            else:
                # 初始时刻递推：E_0 = E0 + PC*effC - PD/effD
                constraints[f"storage_soc_trans_init_{s_id}_{t}"] = model.add_linear_constraint(
                    v_energy - efficiency_term, poi.Eq, e0,
                    name=f"storage_soc_trans_init_{s_id}_{t}",
                )

        # 1.5 周期末端电量平衡（守恒）约束 (2.4.6)
        # 优化周期结束时的能量必须回到初始电量 E0，用于支持跨周期循环
        t_end = periods_list[-1]
        v_energy_end = variables.energy[s_id, t_end]
        constraints[f"storage_soc_end_{s_id}"] = model.add_linear_constraint(
            v_energy_end, poi.Eq, e0,
            name=f"storage_soc_end_{s_id}",
        )

    return constraints
