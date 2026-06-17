# -*- coding: utf-8 -*-
import os
import sys

# Add src to Python path if running from runcase directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.config import TimeConfig
from src.data.loader import load_case, validate_case_data

def run_pipeline_for_time_range(start_hour, end_hour, label):
    print(f"\n==================================================")
    print(f" Running Pipeline Verification: {label} ({start_hour}h to {end_hour}h)")
    print(f"==================================================")
    
    config_path = os.path.normpath(os.path.join(
        os.path.dirname(__file__), "../configs/cases/hubei2030.yaml"
    ))
    
    # 1. Initialize time config
    tc = TimeConfig(start_hour=start_hour, end_hour=end_hour)
    print(f"Initialized TimeConfig: duration = {tc.duration_hours} hours")
    
    # 2. Load case data
    print("Loading CaseData...")
    case_data = load_case(config_path, tc)
    print("CaseData loaded successfully.")
    
    # 3. Print unit counts and total capacities
    print("\n--- Resources Summary ---")
    for name, df in [
        ('Zones/分区', case_data.zones),
        ('Thermal/火电机组', case_data.thermal_units),
        ('Hydro/水电机组', case_data.hydro_units),
        ('Storage/储能机组', case_data.storage_units),
        ('Pumped Storage/抽蓄机组', case_data.pumped_storage_units)
    ]:
        count = len(df)
        capacity_str = ""
        if 'p_max_mw' in df.columns:
            total_cap = df['p_max_mw'].sum()
            capacity_str = f", Total Capacity = {total_cap:.2f} MW"
        print(f"  {name}: Count = {count}{capacity_str}")
        
    # 4. Print curve statistics
    print("\n--- Time Series Curves Statistics ---")
    for curve_name, df in [
        ('Load Curves/负荷曲线 (MW)', case_data.load_curves),
        ('Wind Curves/风电出力系数', case_data.wind_curves),
        ('PV Curves/光伏出力系数', case_data.pv_curves)
    ]:
        print(f"  {curve_name}:")
        for col in df.columns:
            col_min = df[col].min()
            col_max = df[col].max()
            col_mean = df[col].mean()
            print(f"    - Zone {col}: Min = {col_min:.4f}, Max = {col_max:.4f}, Mean = {col_mean:.4f}")
            
    # 5. Print DC flows if present
    if not case_data.dc_flows.empty:
        print("\n--- External DC Flows (MW) ---")
        for col in case_data.dc_flows.columns:
            col_min = case_data.dc_flows[col].min()
            col_max = case_data.dc_flows[col].max()
            col_mean = case_data.dc_flows[col].mean()
            print(f"    - DC Line {col}: Min = {col_min:.2f}, Max = {col_max:.2f}, Mean = {col_mean:.2f}")

    # 6. Run validation and print report
    print("\n--- Running Data Validation ---")
    report = validate_case_data(case_data)
    report.print_report()
    
    assert report.is_valid, f"Validation failed for time range: {label}!"
    print(f"\nSuccessfully verified pipeline for {label}.")

<<<<<<< HEAD
if __name__ == "__main__":
    # Test 24-hour window
    run_pipeline_for_time_range(0, 23, "24 Hours Day-Ahead")
    
    # Test 168-hour window
    run_pipeline_for_time_range(0, 167, "168 Hours Week-Ahead")
=======

def test_pipeline_24_hours():
    """测试 24 小时日前窗口 Pipeline"""
    run_pipeline_for_time_range(0, 23, "24 Hours Day-Ahead")

def test_pipeline_168_hours():
    """测试 168 小时周前窗口 Pipeline"""
    run_pipeline_for_time_range(0, 167, "168 Hours Week-Ahead")


# 如果你依然想保留通过右键普通的 "Run" 运行的能力，可以保留这个：
if __name__ == "__main__":
    # 普通 Python 脚本运行入口
    run_pipeline_for_time_range(0, 23, "24 Hours Day-Ahead")
    run_pipeline_for_time_range(0, 167, "168 Hours Week-Ahead")
>>>>>>> dev
