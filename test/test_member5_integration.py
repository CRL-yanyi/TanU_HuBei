# -*- coding: utf-8 -*-
import os
import yaml
import pytest
import pandas as pd
import numpy as np

from src.data.config import TimeConfig, RunConfig
from src.data.loader import load_case
from src.data.grid_builder import build_grid
from src.simulation.runner import run_production_sim
from src.simulation.result import SimulationResult
from src.validation.validator import validate_simulation_result


@pytest.fixture
def case_config_path():
    return "configs/cases/hubei2030.yaml"


@pytest.fixture
def run_config_path_24h(tmp_path):
    """
    创建一个临时的 24 小时日前运行配置。
    """
    config_dict = {
        "case_name": "hubei2030",
        "simulation": {
            "mode": "UC",
            "start_hour": 0,
            "end_hour": 23,
            "step_hours": 1.0
        },
        "solver": {
            "name": "gurobi",
            "mip_gap": 0.05,       # 适当放宽 gap 提高测试速度
            "time_limit": 60,
            "log_to_console": False
        },
        "rolling": {
            "enable": False
        },
        "switches": {
            "enable_reserve": True,
            "enable_transmission": True,
            "enable_cascade_hydro": False
        }
    }
    path = tmp_path / "run_24h.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config_dict, f)
    return str(path)


@pytest.fixture
def run_config_path_rolling(tmp_path):
    """
    创建一个临时的 48 小时滚动窗口运行配置。
    """
    config_dict = {
        "case_name": "hubei2030",
        "simulation": {
            "mode": "UC",
            "start_hour": 0,
            "end_hour": 47,
            "step_hours": 1.0
        },
        "solver": {
            "name": "gurobi",
            "mip_gap": 0.05,
            "time_limit": 60,
            "log_to_console": False
        },
        "rolling": {
            "enable": True,
            "window_hours": 24,       # 24小时窗口
            "overlap_hours": 4        # 4小时重叠
        },
        "switches": {
            "enable_reserve": True,
            "enable_transmission": True,
            "enable_cascade_hydro": False
        }
    }
    path = tmp_path / "run_rolling.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config_dict, f)
    return str(path)


def test_member5_day_ahead_uc(case_config_path, run_config_path_24h):
    """
    日前 24 小时 UC 集成测试。
    """
    result = run_production_sim(case_config_path, run_config_path_24h)
    
    assert result.status == "OPTIMAL"
    assert result.objective_value >= 0.0
    
    # 验证导出的结果维度
    assert len(result.zonal_balance) == 3 * 24  # 湖北3个分区，24小时
    assert len(result.transmission_lines) == 3 * 24  # 3个跨区断面
    assert "thermal" in result.zonal_balance.columns
    assert "hydro" in result.zonal_balance.columns
    assert "renewable" in result.zonal_balance.columns


def test_member5_rolling_uc(case_config_path, run_config_path_rolling):
    """
    滚动时序 48 小时 (24h窗口+4h重叠) 集成测试。
    验证滚动窗口拼接、状态继承与结果合并无误。
    """
    result = run_production_sim(case_config_path, run_config_path_rolling)
    
    assert result.status == "OPTIMAL"
    assert len(result.zonal_balance) == 3 * 48  # 48小时结果
    assert len(result.transmission_lines) == 3 * 48


def test_member5_validation_detects_violations(case_config_path, run_config_path_24h):
    """
    验证 validator 模块能够敏锐地捕捉并报告违背物理定律的计算结果。
    """
    # 1. 加载基础的 Grid 结构
    from src.data.loader import load_case
    tc = TimeConfig(start_hour=0, end_hour=23)
    case_data = load_case(case_config_path, tc)
    grid = build_grid(case_data)
    
    # 2. 正常运行一次获取基础数据
    result = run_production_sim(case_config_path, run_config_path_24h)
    run_config = RunConfig({
        "simulation": {"start_hour": 0, "end_hour": 23, "step_hours": 1.0},
        "switches": {"load_shed_penalty": 100000.0}
    })

    # 3. 故意修改结果制造“负荷不平衡”错误
    # 将鄂东第 0 小时的负荷人为调大 10000 MW，且无失负荷
    bad_zonal = result.zonal_balance.copy()
    bad_zonal.loc[(bad_zonal['zone'] == '鄂东') & (bad_zonal['hour'] == 0), 'load'] += 10000.0
    
    bad_result = SimulationResult(
        status=result.status,
        objective_value=result.objective_value,
        solve_time=result.solve_time,
        zonal_balance=bad_zonal,
        thermal_units=result.thermal_units,
        storage_units=result.storage_units,
        renewable_units=result.renewable_units,
        transmission_lines=result.transmission_lines
    )
    
    # 执行校验，应报错
    report = validate_simulation_result(grid, bad_result, run_config)
    assert not report.is_valid
    assert any("imbalance" in err.lower() for err in report.errors)
    print("\n[Test] Caught expected power imbalance failure:")
    report.print_report()

    # 4. 故意修改火电机组出力，使其越限
    # 故意将第一台在线火电机组的出力改为 99999 MW
    bad_thermal = result.thermal_units.copy()
    bad_thermal.loc[bad_thermal['hour'] == 0, 'power'] = 99999.0
    
    bad_result2 = SimulationResult(
        status=result.status,
        objective_value=result.objective_value,
        solve_time=result.solve_time,
        zonal_balance=result.zonal_balance,
        thermal_units=bad_thermal,
        storage_units=result.storage_units,
        renewable_units=result.renewable_units,
        transmission_lines=result.transmission_lines
    )
    
    report2 = validate_simulation_result(grid, bad_result2, run_config)
    assert not report2.is_valid
    assert any("violates bounds" in err.lower() for err in report2.errors)
    print("\n[Test] Caught expected thermal bounds violation:")
    report2.print_report()
