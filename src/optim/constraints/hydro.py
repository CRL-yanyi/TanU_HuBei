# -*- coding: utf-8 -*-
import math
from typing import Any, Hashable, Iterable, Mapping
import pyoptinterface as poi
from src.model.grid import Grid
from src.optim.variables import HydroVariables

def get_month_from_hour(hour: int) -> int:
    """
    根据年内小时数 (0 ~ 8759) 计算对应的自然月份 (1 ~ 12)。
    基于非闰年 (2030年) 各月小时数累加。
    """
    month_limits = [744, 1416, 2160, 2880, 3624, 4344, 5088, 5832, 6552, 7296, 8016, 8760]
    for m, limit in enumerate(month_limits, start=1):
        if hour < limit:
            return m
    return 12


def add_hydro_constraints(
    model: Any,
    grid: Grid,
    variables: HydroVariables,
    periods: Iterable[Hashable],
) -> dict[str, Any]:
    """添加水电机组出力与流域水文过程约束。"""
    periods_list = list(periods)
    hydro_ids = grid.getResIdListFromType("HYDRO")
    
    constraints = {}

    # 1. 常规水电单机容量上下限约束
    for h_id in hydro_ids:
        hydro = grid.getResFromId(h_id)
        for t in periods_list:
            # Pmin <= p_h,t <= Pmax
            constraints[f"hydro_min_{h_id}_{t}"] = model.add_linear_constraint(
                variables.power[h_id, t], poi.Geq, hydro.Pmin,
                name=f"hydro_min_{h_id}_{t}",
            )
            constraints[f"hydro_max_{h_id}_{t}"] = model.add_linear_constraint(
                variables.power[h_id, t], poi.Leq, hydro.Pmax,
                name=f"hydro_max_{h_id}_{t}",
            )

    # 2. 流域水文过程约束
    for zone in grid.zones.values():
        for basin in zone.basinDict.values():
            if not basin.hydroDict:
                continue
            
            # 2.1 逐时水文流量边界约束 (2.3.1 & 2.3.2)
            for t in periods_list:
                # 获取该小时所对应的自然月份
                month = get_month_from_hour(int(t))
                
                # 当前流域下所有水电的总出力
                sum_expr = poi.ExprBuilder()
                for h_id in basin.hydroDict:
                    sum_expr += variables.power[h_id, t]

                # (2.3.1) 预想出力上限限制
                if month in basin.predicted:
                    pred_factor = basin.predicted[month]
                    ub_val = pred_factor * basin.capacity
                    constraints[f"basin_predicted_{basin.id}_{t}"] = model.add_linear_constraint(
                        sum_expr, poi.Leq, ub_val,
                        name=f"basin_predicted_{basin.id}_{t}",
                    )

                # (2.3.2) 强迫出力下限限制
                if month in basin.forced:
                    force_factor = basin.forced[month]
                    lb_val = force_factor * basin.capacity
                    constraints[f"basin_forced_{basin.id}_{t}"] = model.add_linear_constraint(
                        sum_expr, poi.Geq, lb_val,
                        name=f"basin_forced_{basin.id}_{t}",
                    )

            # 2.2 周期内平均出力（发电量）总量等式约束 (2.3.3)
            # 按月份分组进行约束（防止跨月计算时总量混淆）
            months_in_periods = set(get_month_from_hour(int(t)) for t in periods_list)
            for m in months_in_periods:
                if m not in basin.average:
                    continue
                t_in_month = [t for t in periods_list if get_month_from_hour(int(t)) == m]
                if not t_in_month:
                    continue

                sum_energy = poi.ExprBuilder()
                for t in t_in_month:
                    for h_id in basin.hydroDict:
                        sum_energy += variables.power[h_id, t]

                # 期望周期总能量 = 运行小时数 * 平均负荷系数 * 流域容量
                avg_factor = basin.average[m]
                target_energy = len(t_in_month) * avg_factor * basin.capacity

                constraints[f"basin_avg_energy_{basin.id}_month{m}"] = model.add_linear_constraint(
                    sum_energy, poi.Eq, target_energy,
                    name=f"basin_avg_energy_{basin.id}_month{m}",
                )

    return constraints
