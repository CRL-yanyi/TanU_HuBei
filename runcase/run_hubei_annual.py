# -*- coding: utf-8 -*-
import os
import sys
import argparse

# 将项目根目录加入到 Python 模块路径中
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.simulation.runner import run_production_sim
from src.output.formatter import export_simulation_results
from src.visualization.plotter import plot_simulation_results
from src.data.config import load_run_config


def main():
    parser = argparse.ArgumentParser(description="湖北省 2030 年电力生产模拟滚动年度运行程序")
    parser.add_argument(
        "--case",
        type=str,
        default="configs/cases/hubei2030.yaml",
        help="算例数据配置 YAML 文件路径"
    )
    parser.add_argument(
        "--run",
        type=str,
        default="configs/runs/production_base.yaml",
        help="运行控制配置 YAML 文件路径"
    )
    parser.add_argument(
        "--out",
        type=str,
        default="output/hubei2030_sim",
        help="结果及图表输出目录"
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        default=True,
        help="是否在运行结束时生成图表"
    )
    
    args = parser.parse_args()

    # 自动解析相对路径为基于项目根目录的绝对路径
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    def make_abs(path):
        if not os.path.isabs(path):
            return os.path.abspath(os.path.join(project_root, path))
        return os.path.abspath(path)

    args.case = make_abs(args.case)
    args.run = make_abs(args.run)
    args.out = make_abs(args.out)

    # 1. 运行日前检查与环境准备
    print("==================================================")
    print("  湖北 2030 电力生产模拟调度年度滚动仿真程序运行")
    print("==================================================")
    print(f"  算例配置: {args.case}")
    print(f"  运行配置: {args.run}")
    print(f"  输出目录: {args.out}")
    print("--------------------------------------------------")

    # 2. 调用核心模拟程序
    try:
        result = run_production_sim(args.case, args.run)
    except Exception as e:
        print(f"\n[ERROR] 生产模拟执行过程中发生崩溃:")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 3. 导出格式化数据和 CSV 表格
    print("\n[Runner] Exporting results...")
    export_simulation_results(result, args.out)

    # 4. 可视化绘图
    if args.plot:
        print("\n[Runner] Generating visualization plots...")
        plot_simulation_results(result, args.out)

    print("\n==================================================")
    print("  仿真计算及后处理全部执行完毕！")
    print("==================================================")


if __name__ == "__main__":
    main()
