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
from src.optim.uc_model import UCModel
from src.optim.objectives import _thermal_linear_cost
from src.simulation.result import SimulationResult
from src.validation.validator import validate_simulation_result


def update_rolling_states(
    uc_model: UCModel,
    grid: Any,
    w_start: int,
    w_end_keep: int,
    step_hours: float,
    states: dict,
    idx: int
) -> dict:
    """
    从当前窗口求解完的 UCModel 中提取并更新滚动接力状态（包括储能SOC、火电开关状态和持续运行小时数）
    """
    model = uc_model.model
    thermal_vars = uc_model.thermal_vars
    storage_vars = uc_model.storage_vars
    
    # 1. 储能剩余电量 (SOC)
    next_storage_energy = {}
    for s_id in [u.id for u in grid.getResListFromType("STORAGE")]:
        next_storage_energy[s_id] = float(model.get_value(storage_vars.energy[s_id, w_end_keep]))
    states["storage_energy"] = next_storage_energy

    # 2. 火电机组状态接力
    for unit in grid.getResListFromType("THERMAL"):
        u_id = unit.id
        state = int(round(model.get_value(thermal_vars.is_on[u_id, w_end_keep])))
        p_val = float(model.get_value(thermal_vars.power[u_id, w_end_keep]))
        
        states["thermal_on"][u_id] = state
        states["thermal_power"][u_id] = p_val
        
        # 回溯在该窗口内的连续开关机状态时间
        count = 0
        h = w_end_keep
        while h >= w_start:
            curr_state = int(round(model.get_value(thermal_vars.is_on[u_id, h])))
            if curr_state == state:
                count += 1
                h -= 1
            else:
                break
        
        if h < w_start:
            if idx > 0:
                prev_hours = states["thermal_on_hours"][u_id] if state == 1 else states["thermal_off_hours"][u_id]
                total_hours_so_far = count * step_hours + prev_hours
            else:
                init_t = float(getattr(unit, "initT", 0.0))
                total_hours_so_far = count * step_hours + (max(init_t, 0.0) if state == 1 else max(-init_t, 0.0))
        else:
            total_hours_so_far = count * step_hours

        if state == 1:
            states["thermal_on_hours"][u_id] = total_hours_so_far
            states["thermal_off_hours"][u_id] = 0.0
        else:
            states["thermal_on_hours"][u_id] = 0.0
            states["thermal_off_hours"][u_id] = total_hours_so_far

    return states


def extract_window_results(
    uc_model: UCModel,
    grid: Any,
    keep_periods: list[int],
    step_hours: float,
    case_data: Any,
    dc_target_zones: dict,
    dc_capacities: dict,
    merged_thermal_units: list,
    merged_storage_units: list,
    merged_renewable_units: list,
    merged_transmission_lines: list,
    merged_zonal_balance: list
):
    """
    从当前窗口求解完的 UCModel 中提取非重叠时段 (keep_periods) 的出力结果并追加到 merged 列表中
    """
    model = uc_model.model
    thermal_vars = uc_model.thermal_vars
    hydro_vars = uc_model.hydro_vars
    storage_vars = uc_model.storage_vars
    renewable_vars = uc_model.renewable_vars
    trans_vars = uc_model.trans_vars
    load_shed = uc_model.load_shed

    # 1. 提取火电机组出力
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

    # 2. 提取储能出力
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

    # 3. 提取新能源出力
    for unit in grid.getResListFromType("WIND") + grid.getResListFromType("PV"):
        u_id = unit.id
        for t in keep_periods:
            act_val = float(model.get_value(renewable_vars.power[u_id, t]))
            cur_val = float(model.get_value(renewable_vars.curtailment[u_id, t]))
            forecast_factor = unit.TSCapacity.get(t, 0.0)
            
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

    # 4. 提取断面联络线潮流
    for l_id, line in grid.intertrans.items():
        for t in keep_periods:
            flow_val = float(model.get_value(trans_vars.flow[l_id, t]))
            merged_transmission_lines.append({
                "line_id": l_id,
                "hour": t,
                "flow": flow_val
            })

    # 5. 提取并计算分区平衡曲线
    for zone_id in grid.zones:
        # 获取高峰负荷配置
        load_res = grid.resources.get(f"LOAD{zone_id}")
        peak_load = load_res.capacity if load_res is not None else 1.0
        
        for t in keep_periods:
            # 基础平衡项
            ld_shed = float(model.get_value(load_shed[zone_id, t]))
            th_p = sum(float(model.get_value(thermal_vars.power[u.id, t])) for u in grid.getResListFromType("THERMAL") if u.zoneId == zone_id)
            hy_p = sum(float(model.get_value(hydro_vars.power[u.id, t])) for u in grid.getResListFromType("HYDRO") if u.zoneId == zone_id)
            rn_p = sum(float(model.get_value(renewable_vars.power[u.id, t])) for u in grid.getResListFromType("WIND") + grid.getResListFromType("PV") if u.zoneId == zone_id)
            
            ch_p = sum(float(model.get_value(storage_vars.charge_power[u.id, t])) for u in grid.getResListFromType("STORAGE") if u.zoneId == zone_id)
            dis_p = sum(float(model.get_value(storage_vars.discharge_power[u.id, t])) for u in grid.getResListFromType("STORAGE") if u.zoneId == zone_id)
            
            # 计算外来直流时序注入
            injection = 0.0
            if not case_data.dc_flows.empty:
                for line_name, target_zone in dc_target_zones.items():
                    if target_zone == zone_id and line_name in case_data.dc_flows.columns:
                        limit_mw = dc_capacities.get(line_name, 1.0)
                        injection += float(case_data.dc_flows.at[t, line_name]) * limit_mw
            dc_inj = injection
            load_val = float(case_data.load_curves.at[t, zone_id]) * peak_load
            
            # 联络线总流入流出
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


def compute_simulation_result(
    grid: Any,
    run_config: Any,
    merged_thermal_units: list,
    merged_storage_units: list,
    merged_renewable_units: list,
    merged_transmission_lines: list,
    merged_zonal_balance: list,
    total_objective_val: float,
    total_solve_time: float,
    total_best_bound: float,
    final_status: str,
    vars_num: int,
    bin_vars_num: int,
    cont_vars_num: int,
    cons_num: int,
    l_cons_num: int,
    q_cons_num: int
) -> SimulationResult:
    """
    仿真循环结束后，统一计算系统级指标并组装成 SimulationResult 对象返回
    """
    step_hours = run_config.step_hours

    # 1. 计算火电细分成本
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

    # 2. 计算储能与抽蓄充放电量
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

    # 3. 计算失负荷与新能源弃电量
    load_curt = sum(row['load_shed'] for row in merged_zonal_balance) * step_hours
    runit_curt = sum(row['curtailment'] for row in merged_renewable_units) * step_hours
    
    # 新能源弃能惩罚成本
    runit_cost = 0.0
    for row in merged_renewable_units:
        unit = grid.getResFromId(row['unit_id'])
        penalty = float(getattr(unit, "curtailmentPenalty", 500.0))
        runit_cost += penalty * row['curtailment'] * step_hours

    # 4. 计算新能源消纳率与渗透率
    total_forecast = sum(row['forecast_power'] for row in merged_renewable_units)
    total_actual = sum(row['actual_power'] for row in merged_renewable_units)
    total_load = sum(row['load'] for row in merged_zonal_balance)

    consumption_rate = total_actual / total_forecast if total_forecast > 1e-6 else 1.0
    renewable_rate = total_actual / total_load if total_load > 1e-6 else 0.0
    
    # 5. 计算 MIP 寻优 Gap
    if abs(total_objective_val) > 1e-6:
        final_mip_gap = abs(total_objective_val - total_best_bound) / abs(total_objective_val)
    else:
        final_mip_gap = 0.0

    return SimulationResult(
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


class RollingSimulator:
    """
    滚动电力生产模拟优化仿真器类
    """
    def __init__(self, grid, run_config, case_data):
        self.grid = grid
        self.run_config = run_config
        self.case_data = case_data
        self.windows = []

    def build_model(self) -> None:
        """
        划分滚动时间窗口，初始化仿真时间片列表
        """
        total_hours = self.run_config.end_hour - self.run_config.start_hour + 1
        window_hours = self.run_config.window_hours
        overlap_hours = self.run_config.overlap_hours
        
        if not self.run_config.rolling_enable or total_hours <= window_hours:
            self.windows = [(self.run_config.start_hour, self.run_config.end_hour, self.run_config.end_hour)]
        else:
            self.windows = []
            w_start = self.run_config.start_hour
            while w_start <= self.run_config.end_hour:
                w_end_model = min(w_start + window_hours - 1, self.run_config.end_hour)
                w_end_keep = min(w_start + window_hours - overlap_hours - 1, self.run_config.end_hour)
                if w_end_model == self.run_config.end_hour:
                    w_end_keep = self.run_config.end_hour
                self.windows.append((w_start, w_end_model, w_end_keep))
                w_start = w_end_keep + 1

    def solve(self) -> SimulationResult:
        """
        核心滚动循环方法，调用 UCModel 进行每个时间片的建模求解，提取并整合最终年度仿真结果
        """
        grid = self.grid
        run_config = self.run_config
        case_data = self.case_data
        windows = self.windows

        # 初始化状态缓冲区（上一窗口的接力状态）
        states = {
            "thermal_on": {},
            "thermal_power": {},
            "thermal_on_hours": {},
            "thermal_off_hours": {},
            "storage_energy": {}
        }
        
        # 结果汇总数据结构
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
        
        # 直流外来电落地关系与容量规格 (预先计算)
        dc_target_zones = case_data.metadata.get("dc_target_zones")
        dc_capacities = {}
        config_capacities = case_data.metadata.get("dc_capacities") or {}
        for line_name in dc_target_zones.keys():
            limit_mw = 0.0
            if hasattr(case_data, "transmissions") and not case_data.transmissions.empty:
                row = case_data.transmissions[case_data.transmissions['line_name'] == line_name]
                if not row.empty:
                    limit_mw = float(row.iloc[0]['limit_mw'])
            if limit_mw == 0.0:
                limit_mw = float(config_capacities.get(line_name, 0.0))
            dc_capacities[line_name] = limit_mw

        # 开始时间片滚动求解循环
        for idx, (w_start, w_end_model, w_end_keep) in enumerate(windows):
            print(f"[Simulation] Solving Window {idx+1}/{len(windows)}: hours [{w_start} ~ {w_end_model}] (keeping to {w_end_keep})")
            
            # 1. 实例化并配置当前窗口的优化模型 (类似师兄的 uc = SUC())
            uc_model = UCModel(
                solver_name=run_config.solver_name,
                time_limit=run_config.time_limit,
                mip_gap=run_config.mip_gap,
                log_to_console=run_config.log_to_console
            )
            
            # 2. 建立变量与构建约束、目标函数 (类似师兄的 uc.buildModel())
            periods = list(range(w_start, w_end_model + 1))
            uc_model.build(grid, periods, run_config, case_data, states)
            
            # 3. 模型求解 (类似师兄的 solveModel())
            start_t = time.time()
            status_code = uc_model.solve()
            solve_duration = time.time() - start_t
            total_solve_time += solve_duration

            # 检查求解状态
            if status_code != poi.TerminationStatusCode.OPTIMAL:
                print(f"[WARNING] Solver terminated with non-optimal status: {status_code}")
                final_status = str(status_code)
                if status_code in (poi.TerminationStatusCode.INFEASIBLE, poi.TerminationStatusCode.INFEASIBLE_OR_UNBOUNDED):
                    raise ValueError(f"Model is infeasible at window {idx+1}! Optimize failed.")

            # 4. 统计首个窗口的模型规模与最优目标边界
            obj_val = uc_model.model.get_model_attribute(poi.ModelAttribute.ObjectiveValue)
            total_objective_val += obj_val
            try:
                obj_bound = uc_model.model.get_model_attribute(poi.ModelAttribute.ObjectiveBound)
            except Exception:
                obj_bound = obj_val
            total_best_bound += obj_bound

            if idx == 0:
                try:
                    vars_num = uc_model.model.get_model_raw_attribute_int('NumVars')
                except Exception:
                    vars_num = uc_model.model.number_of_variables()
                try:
                    bin_vars_num = uc_model.model.get_model_raw_attribute_int('NumBinVars')
                except Exception:
                    bin_vars_num = 0
                cont_vars_num = vars_num - bin_vars_num
                try:
                    l_cons_num = uc_model.model.get_model_raw_attribute_int('NumConstrs')
                except Exception:
                    l_cons_num = uc_model.model.number_of_constraints(poi.ConstraintType.Linear)
                try:
                    q_cons_num = uc_model.model.get_model_raw_attribute_int('NumQConstrs')
                except Exception:
                    q_cons_num = uc_model.model.number_of_constraints(poi.ConstraintType.Quadratic)
                cons_num = l_cons_num + q_cons_num

            # 5. 提取当前窗口保留时段结果
            keep_periods = list(range(w_start, w_end_keep + 1))
            extract_window_results(
                uc_model=uc_model,
                grid=grid,
                keep_periods=keep_periods,
                step_hours=run_config.step_hours,
                case_data=case_data,
                dc_target_zones=dc_target_zones,
                dc_capacities=dc_capacities,
                merged_thermal_units=merged_thermal_units,
                merged_storage_units=merged_storage_units,
                merged_renewable_units=merged_renewable_units,
                merged_transmission_lines=merged_transmission_lines,
                merged_zonal_balance=merged_zonal_balance
            )

            # 6. 提取并更新下一轮的滚动初始状态 (类似师兄的 reInit())
            if run_config.rolling_enable and w_end_keep < run_config.end_hour:
                states = update_rolling_states(
                    uc_model=uc_model,
                    grid=grid,
                    w_start=w_start,
                    w_end_keep=w_end_keep,
                    step_hours=run_config.step_hours,
                    states=states,
                    idx=idx
                )

        # 7. 统计系统全年指标汇总
        res = compute_simulation_result(
            grid=grid,
            run_config=run_config,
            merged_thermal_units=merged_thermal_units,
            merged_storage_units=merged_storage_units,
            merged_renewable_units=merged_renewable_units,
            merged_transmission_lines=merged_transmission_lines,
            merged_zonal_balance=merged_zonal_balance,
            total_objective_val=total_objective_val,
            total_solve_time=total_solve_time,
            total_best_bound=total_best_bound,
            final_status=final_status,
            vars_num=vars_num,
            bin_vars_num=bin_vars_num,
            cont_vars_num=cont_vars_num,
            cons_num=cons_num,
            l_cons_num=l_cons_num,
            q_cons_num=q_cons_num
        )

        # 8. 年度后验物理合法性校验
        print("\n[Simulation] Run completed. Running physical validation...")
        validation_report = validate_simulation_result(grid, res, run_config)
        if not validation_report.is_valid:
            print("[WARNING] Physical validation failed! Violations detected.")
            validation_report.print_report()
        else:
            print("[Simulation] Physical validation passed successfully.")

        return res


def run_production_sim(case_config_path: str, run_config_path: str) -> SimulationResult:
    """
    电网生产模拟滚动年度运行一键接口，兼容旧版测试与依赖
    """
    run_config = load_run_config(run_config_path)
    case_config = load_case_config(case_config_path)
    
    from src.data.config import TimeConfig
    tc = TimeConfig(start_hour=run_config.start_hour, end_hour=run_config.end_hour)
    case_data = load_case(case_config_path, tc, scenario=getattr(run_config, "scenario", None))
    
    grid = build_grid(case_data)
    
    simulator = RollingSimulator(grid, run_config, case_data)
    simulator.build_model()
    return simulator.solve()
