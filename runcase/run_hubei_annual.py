# -*- coding: utf-8 -*-
import os
import sys

# 将项目根目录加入到 Python 模块路径中
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.config import load_run_config, load_case_config, TimeConfig
from src.data.loader import load_case
from src.data.grid_builder import build_grid
from src.simulation.runner import RollingSimulator
from src.output.formatter import export_simulation_results
from src.visualization.plotter import plot_simulation_results


if __name__ == "__main__":
    # 获取项目根目录，并自动转换为绝对路径
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    case_config_path = os.path.join(project_root, "configs", "cases", "hubei2030.yaml")
    run_config_path = os.path.join(project_root, "configs", "runs", "production_base.yaml")
    out_dir = os.path.join(project_root, "output", "hubei2030_sim")

    print("==================================================")
    print("  湖北 2030 电力生产模拟年度滚动仿真运行程序")
    print("==================================================")

    # 1. 读入数据 (Read config and case time-series curves)
    print("\n[Step 1] Loading case and run configurations...")
    run_config = load_run_config(run_config_path)
    case_config = load_case_config(case_config_path)
    tc = TimeConfig(start_hour=run_config.start_hour, end_hour=run_config.end_hour)
    case_data = load_case(case_config_path, tc, scenario=getattr(run_config, "scenario", None))

    # 2. 建立 grid (Build grid)
    print("\n[Step 2] Building grid and loading renewable profiles...")
    grid = build_grid(case_data)

    # 3. 建立模型 (Initialize RollingSimulator model)
    print("\n[Step 3] Initializing RollingSimulator model object...")
    simulator = RollingSimulator(grid, run_config, case_data)

    # 4. 建立约束与目标函数 (Prepare rolling window spaces and boundaries)
    print("\n[Step 4] Pre-building rolling simulation window schedules...")
    simulator.build_model()

    # 5. 求解 (Solve rolling window optimizations)
    print("\n[Step 5] Solving rolling optimization models...")
    result = simulator.solve()

    # 6. 输出 (Export results and draw plots)
    print("\n[Step 6] Exporting results and generating visualization...")
    export_simulation_results(result, out_dir)
    plot_simulation_results(result, out_dir)

    print("\n==================================================")
    print("  仿真计算与后处理全部执行完毕！")
    print("==================================================")
