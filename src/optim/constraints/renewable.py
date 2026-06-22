from typing import Any, Hashable, Iterable
import pyoptinterface as poi

from src.model.grid import Grid
from src.optim.variables import RenewableVariables


def add_renewable_constraints(
    model: Any,
    grid: Grid,
    variables: RenewableVariables,
    periods: Iterable[Hashable],
) -> dict[str, Any]:
    """
    为风电和光伏等新能源机组添加物理约束。
    依据技术手册 2.5 章节：新能源机组模型。
    """
    periods = tuple(periods)
    if not periods:
        return {}

    # 找到所有的风电和光伏机组
    wind_units = grid.getResListFromType("WIND")
    pv_units = grid.getResListFromType("PV")
    renewable_units = wind_units + pv_units

    constraints = {}

    for k in renewable_units:
        # 读取爬坡参数（如果有），否则默认为无限制
        ramp_up = getattr(k, "rampUp", float('inf'))
        ramp_down = getattr(k, "rampDown", float('inf'))

        from src.optim.constraints.hydro import get_month_from_hour

        for i, t in enumerate(periods):
            # 获取时序预测系数 (标幺值)
            forecast_factor = k.TSCapacity.get(t, 0.0)
            
            # Scheme B: 根据当前时段 t 映射到月份，并获取该月份的风光装机容量
            try:
                hour_val = int(t)
                month = get_month_from_hour(hour_val)
                cap_val = k.monthly_capacities.get(month, k.capacity)
            except (ValueError, TypeError):
                # 单元测试中的时段可能是 'T1' 等字符串，此时退化为使用默认 capacity
                cap_val = k.capacity
            
            # (2.5.1) 新新能源弃电与出力平衡
            # P_power + P_curt = Capacity * Forecast_Factor
            p_pre = cap_val * forecast_factor
            constraints[f"ren_power_balance_{k.id}_{t}"] = model.add_linear_constraint(
                variables.power[k.id, t] + variables.curtailment[k.id, t], poi.Eq, p_pre,
                name=f"ren_power_balance_{k.id}_{t}",
            )

            # (2.5.2) 上爬坡限制
            # P[t] - P[t-1] <= rampUp
            if i > 0 and ramp_up != float('inf'):
                t_prev = periods[i - 1]
                constraints[f"ren_ramp_up_{k.id}_{t}"] = model.add_linear_constraint(
                    variables.power[k.id, t] - variables.power[k.id, t_prev], poi.Leq, ramp_up,
                    name=f"ren_ramp_up_{k.id}_{t}",
                )

            # (2.5.3) 下爬坡限制
            # P[t-1] - P[t] <= rampDown
            if i > 0 and ramp_down != float('inf'):
                t_prev = periods[i - 1]
                constraints[f"ren_ramp_down_{k.id}_{t}"] = model.add_linear_constraint(
                    variables.power[k.id, t_prev] - variables.power[k.id, t], poi.Leq, ramp_down,
                    name=f"ren_ramp_down_{k.id}_{t}",
                )
            
            # ---------------------------------------------------------
            # 以下为 SOS2 模型框架 (2.5.4 - 2.5.6) 的接口预留。
            # 由于当前 Wind / PV 数据类缺失分段曲线点（如 P_re^l 等），
            # 此处不产生真实约束，仅作为接口展示。
            # 
            # if hasattr(k, "piecewise_points") and k.piecewise_points:
            #     # (2.5.4) sum(lambda_l) = 1
            #     expr_sum = poi.quicksum(variables.lambda_sos[k.id, l, t] for l in k.piecewise_points)
            #     model.add_linear_constraint(expr_sum, poi.Eq, 1.0)
            #
            #     # (2.5.5) power = sum(P_re^l * lambda_l)
            #     expr_power = poi.quicksum(P_re_l * variables.lambda_sos[k.id, l, t] for l in k.piecewise_points)
            #     model.add_linear_constraint(variables.power[k.id, t] - expr_power, poi.Eq, 0.0)
            #
            #     # (2.5.6) lambda is SOS2
            #     # poi 提供 add_sos2_constraint 方法：
            #     # model.add_sos2_constraint([variables.lambda_sos[k.id, l, t] for l in k.piecewise_points])
            # ---------------------------------------------------------

    return constraints
