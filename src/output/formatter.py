# -*- coding: utf-8 -*-
import os
import pandas as pd
from src.simulation.result import SimulationResult


def export_simulation_results(result: SimulationResult, output_dir: str, excel_name: str = "simulation_result.xlsx") -> None:
    """
    导出所有的运行结果数据到指定的文件夹，包含 CSV 格式文件和格式化的 Excel 文件。
    """
    os.makedirs(output_dir, exist_ok=True)

    # 1. 导出 CSV 文件夹
    csv_dir = os.path.join(output_dir, "csv")
    result.save_to_csv(csv_dir)
    print(f"[Formatter] Exported CSVs to: {csv_dir}")

    # 2. 导出格式化的 Excel
    excel_path = os.path.join(output_dir, excel_name)
    result.save_to_excel(excel_path)
    
    # 3. 计算并输出系统级核心指标报告
    print_metrics_summary(result)
    print(f"[Formatter] Exported Formatted Excel to: {excel_path}")


def print_metrics_summary(result: SimulationResult) -> None:
    """
    计算并打印系统运行的宏观技术经济指标。
    """
    print("\n=================== SYSTEM METRICS SUMMARY ===================")
    print(f"  求解状态 (Solver Status): {result.status}")
    print(f"  总运行成本 (Total System Cost): {result.objective_value:,.2f} 元")
    print(f"  求解时间 (Solve Time): {result.solve_time:.2f} 秒")
    
    if result.zonal_balance.empty:
        print("  无电量平衡结果数据。")
        print("==============================================================")
        return

    zb = result.zonal_balance
    total_load = zb['load'].sum()
    total_thermal = zb['thermal'].sum()
    total_hydro = zb['hydro'].sum()
    total_renewable = zb['renewable'].sum()
    total_curt = zb['curtailment'].sum()
    total_shed = zb['load_shed'].sum()

    print(f"  总负荷电量 (Total Demand): {total_load:,.2f} MWh")
    print(f"  火电总发电量 (Thermal Generation): {total_thermal:,.2f} MWh ({total_thermal/total_load*100:.2f}%)")
    print(f"  水电总发电量 (Hydro Generation): {total_hydro:,.2f} MWh ({total_hydro/total_load*100:.2f}%)")
    print(f"  新能源消纳电量 (Renewable Utilized): {total_renewable:,.2f} MWh ({total_renewable/total_load*100:.2f}%)")
    
    curt_rate = 0.0
    if total_renewable + total_curt > 0:
        curt_rate = total_curt / (total_renewable + total_curt) * 100
    print(f"  新能源总弃电量 (Renewable Curtailed): {total_curt:,.2f} MWh (弃风弃光率: {curt_rate:.2f}%)")
    print(f"  总系统缺电量 (Load Shedding): {total_shed:,.2f} MWh")
    print("==============================================================")
