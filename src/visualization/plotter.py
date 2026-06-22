# -*- coding: utf-8 -*-
import os
import pandas as pd
from src.simulation.result import SimulationResult


def plot_simulation_results(result: SimulationResult, output_dir: str) -> None:
    """
    对仿真结果进行核心指标的可视化绘图（电力平衡堆叠图和储能 SOC 时序图）。
    """
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        import matplotlib.pyplot as plt
        # 设置支持中文的字体
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial']
        plt.rcParams['axes.unicode_minus'] = False
    except ImportError:
        print("[Plotter] Matplotlib is not installed. Skipping visualization.")
        return

    # 1. 绘制每个分区的电力平衡平衡图
    if not result.zonal_balance.empty:
        zb = result.zonal_balance
        zones = zb['zone'].unique()
        
        for zone in zones:
            df_zone = zb[zb['zone'] == zone].sort_values('hour')
            hours = df_zone['hour'].values
            
            # 各项电源供给 (正向)
            thermal = df_zone['thermal'].values
            hydro = df_zone['hydro'].values
            renewable = df_zone['renewable'].values
            dis = df_zone['storage_discharge'].values
            dc = df_zone['dc_injection'].values
            imp = df_zone['line_import'].values
            shed = df_zone['load_shed'].values
            
            # 各项负荷需求 (负向)
            load = -df_zone['load'].values
            ch = -df_zone['storage_charge'].values
            exp = -df_zone['line_export'].values
            
            plt.figure(figsize=(12, 6.5))
            
            # 堆叠图绘制
            # 正向供给
            plt.bar(hours, thermal, width=1.0, label='火电 (Thermal)', color='#ff9999')
            plt.bar(hours, hydro, bottom=thermal, width=1.0, label='水电 (Hydro)', color='#66b3ff')
            plt.bar(hours, renewable, bottom=thermal+hydro, width=1.0, label='新能源 (Renewables)', color='#99ff99')
            plt.bar(hours, dis, bottom=thermal+hydro+renewable, width=1.0, label='储能放电 (Storage Dis)', color='#ffcc99')
            plt.bar(hours, dc, bottom=thermal+hydro+renewable+dis, width=1.0, label='直流外来电 (DC Import)', color='#c2c2f0')
            plt.bar(hours, imp, bottom=thermal+hydro+renewable+dis+dc, width=1.0, label='跨区流入 (Line Import)', color='#ffb266')
            plt.bar(hours, shed, bottom=thermal+hydro+renewable+dis+dc+imp, width=1.0, label='失负荷 (Load Shed)', color='#d9d9d9', hatch='//')

            # 负向负荷
            plt.bar(hours, load, width=1.0, label='分区负荷 (Demand)', color='#e5e5e5')
            plt.bar(hours, ch, bottom=load, width=1.0, label='储能充电 (Storage Ch)', color='#ffcc99', alpha=0.7)
            plt.bar(hours, exp, bottom=load+ch, width=1.0, label='跨区流出 (Line Export)', color='#ffb266', alpha=0.7)

            plt.axhline(0, color='black', linewidth=0.8, linestyle='--')
            plt.title(f"{zone} 分区逐时电力平衡图 (Power Balance)", fontsize=14)
            plt.xlabel("仿真小时数 (Hour)", fontsize=11)
            plt.ylabel("有功功率 (MW)", fontsize=11)
            
            # 把图例放在外面
            plt.legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=9)
            plt.grid(True, linestyle=':', alpha=0.5)
            plt.tight_layout()
            
            save_path = os.path.join(output_dir, f"power_balance_{zone}.png")
            plt.savefig(save_path, dpi=150)
            plt.close()
            print(f"[Plotter] Generated plot: {save_path}")

    # 2. 绘制储能/抽蓄 SOC (能量状态) 变化图
    if not result.storage_units.empty:
        su = result.storage_units
        unit_ids = su['unit_id'].unique()
        
        plt.figure(figsize=(10, 5))
        for u_id in unit_ids:
            df_unit = su[su['unit_id'] == u_id].sort_values('hour')
            plt.plot(df_unit['hour'], df_unit['energy'], label=f"{u_id} SOC")
            
        plt.title("储能/抽蓄电站库容/能量时序图 (Storage Energy Status)", fontsize=13)
        plt.xlabel("仿真小时数 (Hour)", fontsize=11)
        plt.ylabel("当前储能电量 (MWh)", fontsize=11)
        plt.legend(loc='best', fontsize=9)
        plt.grid(True, linestyle=':', alpha=0.5)
        plt.tight_layout()
        
        save_path = os.path.join(output_dir, "storage_soc.png")
        plt.savefig(save_path, dpi=150)
        plt.close()
        print(f"[Plotter] Generated plot: {save_path}")
