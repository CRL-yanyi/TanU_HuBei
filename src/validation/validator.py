# -*- coding: utf-8 -*-
from typing import Dict, Any, List
import pandas as pd
import numpy as np

from src.model.grid import Grid
from src.data.config import RunConfig
from src.simulation.result import SimulationResult
from src.data.case_data import DataValidationReport


def validate_simulation_result(grid: Grid, result: SimulationResult, run_config: RunConfig) -> DataValidationReport:
    """
    对仿真运行结果进行物理规则后校验。
    检查电量平衡、机组出力范围、储能SOC更新、断面潮流等。
    """
    errors: List[str] = []
    warnings: List[str] = []
    summary: Dict[str, Any] = {}

    periods = list(range(run_config.start_hour, run_config.end_hour + 1))
    tolerance = 1e-3  # 浮点数比较容差 (MW / MWh)

    # 1. 检验分区电力平衡
    if not result.zonal_balance.empty:
        # 按 zone & hour 索引以方便查询
        zb_indexed = result.zonal_balance.set_index(['zone', 'hour'])
        
        balance_failures = 0
        for zone_id in grid.zones:
            for t in periods:
                key = (zone_id, t)
                if key not in zb_indexed.index:
                    errors.append(f"Zonal balance result missing for zone {zone_id} at hour {t}")
                    continue
                
                row = zb_indexed.loc[key]
                load = float(row['load'])
                thermal = float(row['thermal'])
                hydro = float(row['hydro'])
                renewable = float(row['renewable'])
                ch = float(row['storage_charge'])
                dis = float(row['storage_discharge'])
                dc = float(row['dc_injection'])
                imp = float(row['line_import'])
                exp = float(row['line_export'])
                curt = float(row['curtailment'])
                shed = float(row['load_shed'])

                # 平衡式：发电供给 + 直流注入 + 跨区流入 + 失负荷 - 本地负荷 - 充电需求 - 跨区流出
                imbalance = (thermal + hydro + renewable + dis + dc + imp + shed) - (load + ch + exp)
                if abs(imbalance) > tolerance:
                    balance_failures += 1
                    if balance_failures <= 5:  # 限制打印前几个错误
                        errors.append(
                            f"Power imbalance in zone {zone_id} at hour {t}: "
                            f"Supply={thermal+hydro+renewable+dis+dc+imp+shed:.2f} MW, "
                            f"Demand={load+ch+exp:.2f} MW, Imbalance={imbalance:.4f} MW"
                        )
        
        summary["power_balance_failures"] = balance_failures

    # 2. 校验火电机组出力与状态边界
    if not result.thermal_units.empty:
        tu_indexed = result.thermal_units.set_index(['unit_id', 'hour'])
        thermal_failures = 0
        
        for unit in grid.getResListFromType("THERMAL"):
            u_id = unit.id
            p_min = unit.Pmin
            p_max = unit.Pmax
            
            for t in periods:
                key = (u_id, t)
                if key not in tu_indexed.index:
                    continue
                
                row = tu_indexed.loc[key]
                p_val = float(row['power'])
                is_on = int(row['is_on'])
                
                if is_on == 0:
                    if abs(p_val) > tolerance:
                        thermal_failures += 1
                        errors.append(f"Thermal unit {u_id} is offline at hour {t} but generating {p_val:.2f} MW")
                else:
                    if p_val < p_min - tolerance or p_val > p_max + tolerance:
                        thermal_failures += 1
                        errors.append(f"Thermal unit {u_id} output {p_val:.2f} MW violates bounds [{p_min}, {p_max}] at hour {t}")
                        
        summary["thermal_bounds_failures"] = thermal_failures

    # 3. 校验储能与抽水蓄能 SOC 更新逻辑
    if not result.storage_units.empty:
        su_indexed = result.storage_units.set_index(['unit_id', 'hour'])
        storage_failures = 0
        
        for unit in grid.getResListFromType("STORAGE"):
            u_id = unit.id
            eff_c = unit.effC
            eff_d = unit.effD
            e_init = unit.E0
            e_min = unit.Emin
            e_max = unit.Emax
            
            for idx, t in enumerate(periods):
                key = (u_id, t)
                if key not in su_indexed.index:
                    continue
                
                row = su_indexed.loc[key]
                ch_p = float(row['charge_power'])
                dis_p = float(row['discharge_power'])
                e_val = float(row['energy'])
                
                # 能量范围校验
                if e_val < e_min - tolerance or e_val > e_max + tolerance:
                    storage_failures += 1
                    errors.append(f"Storage unit {u_id} energy {e_val:.2f} MWh violates limits [{e_min}, {e_max}] at hour {t}")
                
                # 时序递推守恒校验
                if idx == 0:
                    prev_e = e_init
                else:
                    prev_key = (u_id, periods[idx - 1])
                    prev_e = float(su_indexed.loc[prev_key]['energy'])
                    
                expected_e = prev_e + ch_p * eff_c - dis_p / eff_d
                if abs(e_val - expected_e) > tolerance:
                    storage_failures += 1
                    if storage_failures <= 5:
                        errors.append(
                            f"Storage {u_id} SOC transition error at hour {t}: "
                            f"Stored={e_val:.3f} MWh, Expected={expected_e:.3f} MWh, Diff={e_val-expected_e:.4f} MWh"
                        )
                        
        summary["storage_soc_failures"] = storage_failures

    # 4. 校验新能源实际出力与弃电之和是否等于预测有功
    if not result.renewable_units.empty:
        ru_indexed = result.renewable_units.set_index(['unit_id', 'hour'])
        ren_failures = 0
        
        for unit in grid.getResListFromType("WIND") + grid.getResListFromType("PV"):
            u_id = unit.id
            for t in periods:
                key = (u_id, t)
                if key not in ru_indexed.index:
                    continue
                
                row = ru_indexed.loc[key]
                pre_val = float(row['forecast_power'])
                act_val = float(row['actual_power'])
                cur_val = float(row['curtailment'])
                
                if abs(act_val + cur_val - pre_val) > tolerance:
                    ren_failures += 1
                    if ren_failures <= 5:
                        errors.append(
                            f"Renewable unit {u_id} balance error at hour {t}: "
                            f"Actual={act_val:.2f} MW, Curt={cur_val:.2f} MW, Forecast={pre_val:.2f} MW"
                        )
                        
        summary["renewable_balance_failures"] = ren_failures

    # 5. 校验断面潮流越限
    if not result.transmission_lines.empty:
        line_indexed = result.transmission_lines.set_index(['line_id', 'hour'])
        line_failures = 0
        
        for l_id, line in grid.intertrans.items():
            flow_min = -float(line.capacityFromZone)
            flow_max = float(line.capacityToZone)
            
            # 如果断面停运
            if getattr(line, "status", 1) == 0:
                flow_min = 0.0
                flow_max = 0.0
                
            for t in periods:
                key = (l_id, t)
                if key not in line_indexed.index:
                    continue
                
                flow_val = float(line_indexed.loc[key]['flow'])
                if flow_val < flow_min - tolerance or flow_val > flow_max + tolerance:
                    line_failures += 1
                    errors.append(
                        f"Transmission line {l_id} flow {flow_val:.2f} MW violates capacity limits [{flow_min}, {flow_max}] at hour {t}"
                    )
                    
        summary["transmission_limit_failures"] = line_failures

    # 汇总结论
    is_valid = len(errors) == 0
    return DataValidationReport(is_valid=is_valid, errors=errors, warnings=warnings, summary=summary)
