# -*- coding: utf-8 -*-
import os
import time
import math
from typing import Any, List, Dict, Tuple
import pandas as pd
import pyoptinterface as poi

from src.data.config import load_case_config, load_run_config, RunConfig
from src.data.loader import load_case
from src.data.grid_builder import build_grid
from src.optim.variables import (
    add_thermal_variables,
    add_hydro_variables,
    add_storage_variables,
    add_renewable_variables,
    add_transmission_variables
)
from src.optim.constraints.thermal import add_thermal_uc_constraints, add_thermal_ed_constraints
from src.optim.constraints.hydro import add_hydro_constraints
from src.optim.constraints.storage import add_storage_constraints
from src.optim.constraints.renewable import add_renewable_constraints
from src.optim.constraints.transmission import add_transmission_constraints
from src.optim.constraints.power_balance import add_power_balance_constraints
from src.optim.constraints.reserve import add_system_reserve_constraints
from src.optim.objectives import set_thermal_cost_objective, _thermal_linear_cost
from src.simulation.result import SimulationResult
from src.validation.validator import validate_simulation_result


def run_production_sim(case_config_path: str, run_config_path: str) -> SimulationResult:
    """
    运行电网生产模拟仿真，整合所有资源模块并支持滚动调度。
    """
    # 1. 载入运行配置与算例基础数据
    run_config = load_run_config(run_config_path)
    case_config = load_case_config(case_config_path)
    
    # 初始化整个模拟周期的时间范围
    from src.data.config import TimeConfig
    tc = TimeConfig(start_hour=run_config.start_hour, end_hour=run_config.end_hour)
    case_data = load_case(case_config_path, tc, scenario=getattr(run_config, "scenario", None))
    grid = build_grid(case_data)
    
    # 保存原始储能 E0，供物理后验校验使用
    original_e0 = {u.id: u.E0 for u in grid.getResListFromType("STORAGE")}
    
    # 2. 挂接风电和光伏时序容量系数 (TSCapacity)
    for wind_unit in grid.getResListFromType("WIND"):
        zone_id = wind_unit.zoneId
        if zone_id in case_data.wind_curves.columns:
            wind_unit.TSCapacity = {t: float(case_data.wind_curves.at[t, zone_id]) for t in case_data.wind_curves.index}

    for pv_unit in grid.getResListFromType("PV"):
        zone_id = pv_unit.zoneId
        if zone_id in case_data.pv_curves.columns:
            pv_unit.TSCapacity = {t: float(case_data.pv_curves.at[t, zone_id]) for t in case_data.pv_curves.index}

    # 3. 划分滚动窗口
    total_hours = run_config.end_hour - run_config.start_hour + 1
    window_hours = run_config.window_hours
    overlap_hours = run_config.overlap_hours
    
    if not run_config.rolling_enable or total_hours <= window_hours:
        windows = [(run_config.start_hour, run_config.end_hour, run_config.end_hour)]
    else:
        windows = []
        w_start = run_config.start_hour
        while w_start <= run_config.end_hour:
            w_end_model = min(w_start + window_hours - 1, run_config.end_hour)
            w_end_keep = min(w_start + window_hours - overlap_hours - 1, run_config.end_hour)
            if w_end_model == run_config.end_hour:
                w_end_keep = run_config.end_hour
            windows.append((w_start, w_end_model, w_end_keep))
            w_start = w_end_keep + 1

    # 4. 滚动循环优化准备
    # 初始化状态缓冲器（传递给下一个窗口）
    prev_thermal_on: Dict[str, int] = {}
    prev_thermal_power: Dict[str, float] = {}
    prev_thermal_on_hours: Dict[str, float] = {}
    prev_thermal_off_hours: Dict[str, float] = {}
    
    # 存储最终合并的所有时段数据
    merged_zonal_balance: List[Dict[str, Any]] = []
    merged_thermal_units: List[Dict[str, Any]] = []
    merged_storage_units: List[Dict[str, Any]] = []
    merged_renewable_units: List[Dict[str, Any]] = []
    merged_transmission_lines: List[Dict[str, Any]] = []
    
    total_objective_val = 0.0
    total_solve_time = 0.0
    final_status = "OPTIMAL"
    vars_num = 0
    bin_vars_num = 0
    cont_vars_num = 0
    cons_num = 0
    l_cons_num = 0
    q_cons_num = 0
    total_best_bound = 0.0
    
    # 直流外来电落地对应关系
    dc_target_zones = {
        "第三直流入鄂": "鄂东",
        "陕湖直流": "鄂西北",
        "灵宝直流": "鄂东",
        "金上直流": "鄂东"
    }

    # 5. 循环窗口优化
    for idx, (w_start, w_end_model, w_end_keep) in enumerate(windows):
        print(f"[Simulation] Solving Window {idx+1}/{len(windows)}: hours [{w_start} ~ {w_end_model}] (keeping to {w_end_keep})")
        
        # 5.1 创建求解模型对象
        if run_config.solver_name == "gurobi":
            from pyoptinterface import gurobi
            model = gurobi.Model()
        elif run_config.solver_name == "copt":
            from pyoptinterface import copt
            model = copt.Model()
        elif run_config.solver_name == "cbc":
            from pyoptinterface import cbc
            model = cbc.Model()
        else:
            raise ValueError(f"Unsupported solver: {run_config.solver_name}")
            
        # 配置求解器参数
        if run_config.solver_name == "gurobi":
            model.set_raw_parameter("MIPGap", float(run_config.mip_gap))
        elif run_config.solver_name == "copt":
            model.set_raw_parameter("MIPGap", float(run_config.mip_gap))
        elif run_config.solver_name == "cbc":
            try:
                model.set_raw_parameter("allowableGap", float(run_config.mip_gap))
            except Exception:
                pass
        model.set_model_attribute(poi.ModelAttribute.TimeLimitSec, float(run_config.time_limit))
        if not run_config.log_to_console:
            model.set_model_attribute(poi.ModelAttribute.Silent, True)

        periods = list(range(w_start, w_end_model + 1))
        step_hours = run_config.step_hours

        # 5.2 声明各模块决策变量
        thermal_ids = [u.id for u in grid.getResListFromType("THERMAL")]
        hydro_ids = [u.id for u in grid.getResListFromType("HYDRO")]
        storage_ids = [u.id for u in grid.getResListFromType("STORAGE")]
        renewable_ids = [u.id for u in grid.getResListFromType("WIND") + grid.getResListFromType("PV")]
        line_ids = list(grid.intertrans.keys())

        thermal_vars = add_thermal_variables(model, thermal_ids, periods)
        hydro_vars = add_hydro_variables(model, hydro_ids, periods)
        storage_vars = add_storage_variables(model, storage_ids, periods)
        renewable_vars = add_renewable_variables(model, renewable_ids, periods)
        trans_vars = add_transmission_variables(model, line_ids, periods)
        
        # 增加失负荷惩罚连续变量
        load_shed = model.add_variables(
            [(zone_id, t) for zone_id in grid.zones for t in periods],
            lb=0.0,
            domain=poi.VariableDomain.Continuous,
            name="load_shed",
        )

        # 5.3 载入上个窗口保留的储能初始SOC（直接修改 grid 中对象的 E0 属性）
        # 第一个窗口保留原始 E0
        if idx > 0:
            for s_id in storage_ids:
                storage_unit = grid.getResFromId(s_id)
                # 从上一轮状态缓存中取出上次保留时段的 E_end
                last_energy = next_storage_energy.get(s_id, storage_unit.E0)
                storage_unit.E0 = last_energy

        # 5.4 构建各类物理和运行约束
        # 5.4.1 火电机组约束
        if run_config.mode == "UC":
            add_thermal_uc_constraints(
                model=model,
                grid=grid,
                variables=thermal_vars,
                periods=periods,
                initial_on=prev_thermal_on if idx > 0 else None,
                initial_power_mw=prev_thermal_power if idx > 0 else None,
                initial_on_hours=prev_thermal_on_hours if idx > 0 else None,
                initial_off_hours=prev_thermal_off_hours if idx > 0 else None,
                step_hours=step_hours,
            )
        else:
            # ED 经济调度模式下，将状态固定为已知开停计划（通常从 case_data 获取）
            raise NotImplementedError("Economic Dispatch (ED) is not fully integrated yet.")

        # 5.4.2 水电约束
        add_hydro_constraints(model, grid, hydro_vars, periods)

        # 5.4.3 储电与抽蓄约束
        add_storage_constraints(model, grid, storage_vars, periods)

        # 5.4.4 新能源机组约束
        add_renewable_constraints(model, grid, renewable_vars, periods)

        # 5.4.5 断面潮流输电容量约束
        if run_config.enable_transmission:
            add_transmission_constraints(model, grid, trans_vars, periods)

        # 5.4.6 系统旋转备用约束
        if run_config.enable_reserve:
            # 备用需求目前从各分区分摊，这里简化为求和
            reserve_req = {}
            for t in periods:
                total_req = 0.0
                for zone_id, zone_obj in grid.zones.items():
                    # 备用率 = 负荷备用率 + 事故备用率 * 事故热备用比例
                    rate = getattr(zone_obj, "load_reserve_rate", 0.03) + \
                           getattr(zone_obj, "contingency_reserve_rate", 0.02) * getattr(zone_obj, "spinning_reserve_rate", 0.5)
                    load_res = grid.resources.get(f"LOAD{zone_id}")
                    peak_load = load_res.capacity if load_res is not None else 1.0
                    total_req += float(case_data.load_curves.at[t, zone_id]) * peak_load * rate
                reserve_req[t] = total_req
                
            add_system_reserve_constraints(model, grid, thermal_vars, periods, reserve_req)

        # 5.4.7 分区电力供需平衡约束 (直流注入在此处理)
        # 获取分区负荷时序 (Scheme B: 乘以真实的物理最大负荷进行物理量化)
        demand_mw = {}
        for zone_id in grid.zones:
            load_res = grid.resources.get(f"LOAD{zone_id}")
            peak_load = load_res.capacity if load_res is not None else 1.0
            for t in periods:
                demand_mw[zone_id, t] = float(case_data.load_curves.at[t, zone_id]) * peak_load
        
        # 预先获取直流通道的容量规格 (用于 Scheme B)
        dc_capacities = {}
        for line_name in dc_target_zones.keys():
            limit_mw = 0.0
            if hasattr(case_data, "transmissions") and not case_data.transmissions.empty:
                row = case_data.transmissions[case_data.transmissions['line_name'] == line_name]
                if not row.empty:
                    limit_mw = float(row.iloc[0]['limit_mw'])
            # '第三直流入鄂' 在断面表中极限标称为 0.0，在 2030 实际应采用 UHVDC 典型值 8000.0 MW
            if limit_mw == 0.0 and line_name == "第三直流入鄂":
                limit_mw = 8000.0
            dc_capacities[line_name] = limit_mw

        # 计算外来直流电力的各分区时序注入
        fixed_external_injection_mw = {}
        for zone_id in grid.zones:
            for t in periods:
                injection = 0.0
                if not case_data.dc_flows.empty:
                    for line_name, target_zone in dc_target_zones.items():
                        if target_zone == zone_id and line_name in case_data.dc_flows.columns:
                            limit_mw = dc_capacities.get(line_name, 1.0)
                            injection += float(case_data.dc_flows.at[t, line_name]) * limit_mw
                fixed_external_injection_mw[zone_id, t] = injection

        # 构筑平衡式资源组
        supply_groups = [
            {
                "variables": thermal_vars.power,
                "resource_zones": {u.id: u.zoneId for u in grid.getResListFromType("THERMAL")},
                "coefficient": 1.0,
            },
            {
                "variables": hydro_vars.power,
                "resource_zones": {u.id: u.zoneId for u in grid.getResListFromType("HYDRO")},
                "coefficient": 1.0,
            },
            {
                "variables": renewable_vars.power,
                "resource_zones": {u.id: u.zoneId for u in grid.getResListFromType("WIND") + grid.getResListFromType("PV")},
                "coefficient": 1.0,
            },
            {
                "variables": storage_vars.discharge_power,
                "resource_zones": {u.id: u.zoneId for u in grid.getResListFromType("STORAGE")},
                "coefficient": 1.0,
            },
            # 失负荷补偿项
            {
                "variables": load_shed,
                "resource_zones": {zone_id: zone_id for zone_id in grid.zones},
                "coefficient": 1.0,
            }
        ]
        
        demand_groups = [
            {
                "variables": storage_vars.charge_power,
                "resource_zones": {u.id: u.zoneId for u in grid.getResListFromType("STORAGE")},
                "coefficient": 1.0,
            }
        ]

        add_power_balance_constraints(
            model=model,
            grid=grid,
            periods=periods,
            demand_mw=demand_mw,
            supply_groups=supply_groups,
            demand_groups=demand_groups,
            transmission_flow=trans_vars.flow,
            fixed_external_injection_mw=fixed_external_injection_mw,
        )

        # 5.5 设置目标函数
        costs = set_thermal_cost_objective(model, grid, thermal_vars, periods, step_hours)
        total_cost_expr = poi.ExprBuilder()
        total_cost_expr += costs["total_cost"]
        
        # 弃电惩罚
        for k in grid.getResListFromType("WIND") + grid.getResListFromType("PV"):
            penalty = float(getattr(k, "curtailmentPenalty", 500.0))
            for t in periods:
                total_cost_expr += penalty * step_hours * renewable_vars.curtailment[k.id, t]

        # 失负荷惩罚
        for zone_id in grid.zones:
            for t in periods:
                total_cost_expr += run_config.load_shed_penalty * step_hours * load_shed[zone_id, t]

        model.set_objective(total_cost_expr, poi.ObjectiveSense.Minimize)

        # 5.6 求解模型并计时
        start_t = time.time()
        model.optimize()
        solve_duration = time.time() - start_t
        total_solve_time += solve_duration

        # 5.7 检查并处理求解结果
        status_code = model.get_model_attribute(poi.ModelAttribute.TerminationStatus)
        if status_code != poi.TerminationStatusCode.OPTIMAL:
            print(f"[WARNING] Solver terminated with non-optimal status: {status_code}")
            final_status = str(status_code)
            # 如果不可解，直接跳出或抛出异常以方便定位
            if status_code in (poi.TerminationStatusCode.INFEASIBLE, poi.TerminationStatusCode.INFEASIBLE_OR_UNBOUNDED):
                raise ValueError(f"Model is infeasible at window {idx+1}! Optimize failed.")

        obj_val = model.get_model_attribute(poi.ModelAttribute.ObjectiveValue)
        total_objective_val += obj_val

        try:
            obj_bound = model.get_model_attribute(poi.ModelAttribute.ObjectiveBound)
        except Exception:
            obj_bound = obj_val
        total_best_bound += obj_bound

        if idx == 0:
            try:
                vars_num = model.get_model_raw_attribute_int('NumVars')
            except Exception:
                vars_num = model.number_of_variables()
                
            try:
                bin_vars_num = model.get_model_raw_attribute_int('NumBinVars')
            except Exception:
                bin_vars_num = 0
            
            cont_vars_num = vars_num - bin_vars_num
            
            try:
                l_cons_num = model.get_model_raw_attribute_int('NumConstrs')
            except Exception:
                l_cons_num = model.number_of_constraints(poi.ConstraintType.Linear)
                
            try:
                q_cons_num = model.get_model_raw_attribute_int('NumQConstrs')
            except Exception:
                q_cons_num = model.number_of_constraints(poi.ConstraintType.Quadratic)
                
            cons_num = l_cons_num + q_cons_num

        # 5.8 提取需要保留的非重叠时段 (w_start 到 w_end_keep) 结果
        keep_periods = list(range(w_start, w_end_keep + 1))
        
        # 5.8.1 提取机组出力和直流潮流，拼接结果
        # 火电机组
        for unit in grid.getResListFromType("THERMAL"):
            u_id = unit.id
            for t in keep_periods:
                p_val = float(model.get_value(thermal_vars.power[u_id, t]))
                on_val = int(round(model.get_value(thermal_vars.is_on[u_id, t])))
                st_val = int(round(model.get_value(thermal_vars.startup[u_id, t])))
                sd_val = int(round(model.get_value(thermal_vars.shutdown[u_id, t])))
                merged_thermal_units.append({
                    "unit_id": u_id,
                    "hour": t,
                    "power": p_val,
                    "is_on": on_val,
                    "startup": st_val,
                    "shutdown": sd_val
                })
                

                
        # 储能机组
        for unit in grid.getResListFromType("STORAGE"):
            u_id = unit.id
            for t in keep_periods:
                ch_val = float(model.get_value(storage_vars.charge_power[u_id, t]))
                dis_val = float(model.get_value(storage_vars.discharge_power[u_id, t]))
                e_val = float(model.get_value(storage_vars.energy[u_id, t]))
                isc_val = int(round(model.get_value(storage_vars.is_charging[u_id, t])))
                isd_val = int(round(model.get_value(storage_vars.is_discharging[u_id, t])))
                merged_storage_units.append({
                    "unit_id": u_id,
                    "hour": t,
                    "charge_power": ch_val,
                    "discharge_power": dis_val,
                    "energy": e_val,
                    "is_charging": isc_val,
                    "is_discharging": isd_val
                })
                
        # 新能源机组
        for unit in grid.getResListFromType("WIND") + grid.getResListFromType("PV"):
            u_id = unit.id
            for t in keep_periods:
                act_val = float(model.get_value(renewable_vars.power[u_id, t]))
                cur_val = float(model.get_value(renewable_vars.curtailment[u_id, t]))
                # 预测出力
                forecast_factor = unit.TSCapacity.get(t, 0.0)
                
                # Scheme B: 根据当前时段 t 映射到月份，获取实际物理容量以缩放预测出力值
                from src.optim.constraints.hydro import get_month_from_hour
                try:
                    month = get_month_from_hour(int(t))
                    cap_val = unit.monthly_capacities.get(month, unit.capacity)
                except (ValueError, TypeError):
                    cap_val = unit.capacity
                
                pre_val = cap_val * forecast_factor
                merged_renewable_units.append({
                    "unit_id": u_id,
                    "zone": getattr(unit, "zoneId", "unknown"),
                    "hour": t,
                    "forecast_power": pre_val,
                    "actual_power": act_val,
                    "curtailment": cur_val
                })

        # 区域输电潮流
        for l_id, line in grid.intertrans.items():
            for t in keep_periods:
                flow_val = float(model.get_value(trans_vars.flow[l_id, t]))
                merged_transmission_lines.append({
                    "line_id": l_id,
                    "hour": t,
                    "flow": flow_val
                })

        # 分区电量平衡数据拼接
        for zone_id in grid.zones:
            for t in keep_periods:
                ld_shed = float(model.get_value(load_shed[zone_id, t]))
                # 查找当前分区和时刻下的各项供给求和
                th_p = sum(float(model.get_value(thermal_vars.power[u.id, t])) for u in grid.getResListFromType("THERMAL") if u.zoneId == zone_id)
                hy_p = sum(float(model.get_value(hydro_vars.power[u.id, t])) for u in grid.getResListFromType("HYDRO") if u.zoneId == zone_id)
                rn_p = sum(float(model.get_value(renewable_vars.power[u.id, t])) for u in grid.getResListFromType("WIND") + grid.getResListFromType("PV") if u.zoneId == zone_id)
                
                ch_p = sum(float(model.get_value(storage_vars.charge_power[u.id, t])) for u in grid.getResListFromType("STORAGE") if u.zoneId == zone_id)
                dis_p = sum(float(model.get_value(storage_vars.discharge_power[u.id, t])) for u in grid.getResListFromType("STORAGE") if u.zoneId == zone_id)
                
                dc_inj = fixed_external_injection_mw[zone_id, t]
                load_val = demand_mw[zone_id, t]
                
                # 断面外部流入/流出
                import_flow = 0.0
                export_flow = 0.0
                for line in grid.intertrans.values():
                    flow_val = float(model.get_value(trans_vars.flow[line.id, t]))
                    if zone_id == line.toZone:
                        if flow_val >= 0:
                            import_flow += flow_val
                        else:
                            export_flow += abs(flow_val)
                    elif zone_id == line.fromZone:
                        if flow_val >= 0:
                            export_flow += flow_val
                        else:
                            import_flow += abs(flow_val)
                
                # 新风光弃电
                curt_val = sum(float(model.get_value(renewable_vars.curtailment[u.id, t])) for u in grid.getResListFromType("WIND") + grid.getResListFromType("PV") if u.zoneId == zone_id)

                merged_zonal_balance.append({
                    "zone": zone_id,
                    "hour": t,
                    "load": load_val,
                    "thermal": th_p,
                    "hydro": hy_p,
                    "renewable": rn_p,
                    "storage_charge": ch_p,
                    "storage_discharge": dis_p,
                    "dc_injection": dc_inj,
                    "line_import": import_flow,
                    "line_export": export_flow,
                    "curtailment": curt_val,
                    "load_shed": ld_shed
                })

        # 5.9 边界状态提取与缓存（供下一个窗口使用）
        if run_config.rolling_enable and w_end_keep < run_config.end_hour:
            # 5.9.1 储能剩余电量
            next_storage_energy = {}
            for s_id in storage_ids:
                next_storage_energy[s_id] = float(model.get_value(storage_vars.energy[s_id, w_end_keep]))
            
            # 5.9.2 火电机组启停及开/停持续时间
            for unit in grid.getResListFromType("THERMAL"):
                u_id = unit.id
                state = int(round(model.get_value(thermal_vars.is_on[u_id, w_end_keep])))
                p_val = float(model.get_value(thermal_vars.power[u_id, w_end_keep]))
                
                prev_thermal_on[u_id] = state
                prev_thermal_power[u_id] = p_val
                
                # 计算在该窗口内回溯的连续状态时间
                count = 0
                h = w_end_keep
                while h >= w_start:
                    curr_state = int(round(model.get_value(thermal_vars.is_on[u_id, h])))
                    if curr_state == state:
                        count += 1
                        h -= 1
                    else:
                        break
                
                # 如果回溯到窗口起点仍一致，需累加更上一轮的持续时间
                if h < w_start:
                    if idx > 0:
                        prev_hours = prev_thermal_on_hours[u_id] if state == 1 else prev_thermal_off_hours[u_id]
                        total_hours_so_far = count * step_hours + prev_hours
                    else:
                        # 第一个窗口前的值为机组初始 initT
                        init_t = float(getattr(unit, "initT", 0.0))
                        total_hours_so_far = count * step_hours + (max(init_t, 0.0) if state == 1 else max(-init_t, 0.0))
                else:
                    total_hours_so_far = count * step_hours

                if state == 1:
                    prev_thermal_on_hours[u_id] = total_hours_so_far
                    prev_thermal_off_hours[u_id] = 0.0
                else:
                    prev_thermal_on_hours[u_id] = 0.0
                    prev_thermal_off_hours[u_id] = total_hours_so_far

    # 5.10 计算系统汇总指标
    gen_cost = 0.0
    gen_startup = 0.0
    gen_startdown = 0.0
    for row in merged_thermal_units:
        unit = grid.getResFromId(row['unit_id'])
        linear_cost = _thermal_linear_cost(unit)
        startup_unit_cost = float(getattr(unit, "startUpCost", 0.0))
        shutdown_unit_cost = float(getattr(unit, "shutDownCost", 0.0))
        
        gen_cost += linear_cost * row['power'] * step_hours
        gen_startup += startup_unit_cost * row['startup']
        gen_startdown += shutdown_unit_cost * row['shutdown']

    bes_pc = 0.0
    bes_pd = 0.0
    hes_pc = 0.0
    hes_pd = 0.0
    for row in merged_storage_units:
        unit = grid.getResFromId(row['unit_id'])
        subtype = getattr(unit, "subtype", "BATTERY_STORAGE")
        if subtype == "BATTERY_STORAGE":
            bes_pc += row['charge_power'] * step_hours
            bes_pd += row['discharge_power'] * step_hours
        elif subtype == "PUMPED_STORAGE":
            hes_pc += row['charge_power'] * step_hours
            hes_pd += row['discharge_power'] * step_hours

    load_curt = sum(row['load_shed'] for row in merged_zonal_balance) * step_hours
    runit_curt = sum(row['curtailment'] for row in merged_renewable_units) * step_hours
    
    runit_cost = 0.0
    for row in merged_renewable_units:
        unit = grid.getResFromId(row['unit_id'])
        penalty = float(getattr(unit, "curtailmentPenalty", 500.0))
        runit_cost += penalty * row['curtailment'] * step_hours

    total_forecast = sum(row['forecast_power'] for row in merged_renewable_units)
    total_actual = sum(row['actual_power'] for row in merged_renewable_units)
    total_load = sum(row['load'] for row in merged_zonal_balance)

    consumption_rate = total_actual / total_forecast if total_forecast > 1e-6 else 1.0
    renewable_rate = total_actual / total_load if total_load > 1e-6 else 0.0
    
    if abs(total_objective_val) > 1e-6:
        final_mip_gap = abs(total_objective_val - total_best_bound) / abs(total_objective_val)
    else:
        final_mip_gap = 0.0

    # 6. 打造成最终 SimulationResult 对象
    res = SimulationResult(
        status=final_status,
        objective_value=total_objective_val,
        solve_time=total_solve_time,
        best_bound=total_best_bound,
        mip_gap=final_mip_gap,
        vars_num=vars_num,
        bin_vars_num=bin_vars_num,
        cont_vars_num=cont_vars_num,
        cons_num=cons_num,
        l_cons_num=l_cons_num,
        q_cons_num=q_cons_num,
        gen_cost=gen_cost,
        gen_startup=gen_startup,
        gen_startdown=gen_startdown,
        bes_pc=bes_pc,
        bes_pd=bes_pd,
        hes_pc=hes_pc,
        hes_pd=hes_pd,
        load_curt=load_curt,
        runit_curt=runit_curt,
        runit_cost=runit_cost,
        consumption_rate=consumption_rate,
        renewable_rate=renewable_rate,
        zonal_balance=pd.DataFrame(merged_zonal_balance),
        thermal_units=pd.DataFrame(merged_thermal_units),
        storage_units=pd.DataFrame(merged_storage_units),
        renewable_units=pd.DataFrame(merged_renewable_units),
        transmission_lines=pd.DataFrame(merged_transmission_lines)
    )

    # 7. 还原储能初始 SOC 属性，避免影响后验物理校验
    for s_id, e0_val in original_e0.items():
        grid.getResFromId(s_id).E0 = e0_val

    # 8. 调用物理规则后验证
    print("\n[Simulation] Run completed. Running physical validation...")
    validation_report = validate_simulation_result(grid, res, run_config)
    if not validation_report.is_valid:
        print("[WARNING] Physical validation failed! Violations detected.")
        validation_report.print_report()
    else:
        print("[Simulation] Physical validation passed successfully.")

    return res
