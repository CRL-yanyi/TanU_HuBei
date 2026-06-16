# -*- coding: utf-8 -*-
import os
import pytest
import pandas as pd
from src.data.config import TimeConfig, load_case_config
from src.data.loader import load_case, validate_case_data
from src.data.case_data import CaseData

# Path to the hubei2030 case configuration
CONFIG_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), '../../configs/cases/hubei2030.yaml'))

def test_config_parsing():
    """
    测试配置文件是否被正确读取和解析。
    """
    config = load_case_config(CONFIG_PATH)
    assert config.case_name == "hubei2030"
    assert "zone" in config.files
    assert "thermal" in config.files
    assert "storage" in config.files

def test_time_config():
    """
    测试 TimeConfig 辅助类属性。
    """
    tc = TimeConfig(start_hour=0, end_hour=23)
    assert tc.duration_hours == 24
    assert len(tc.hours_list) == 24
    assert tc.hours_list[0] == 0
    assert tc.hours_list[-1] == 23

def test_data_loading_and_slicing():
    """
    测试短时段（24小时）数据切片载入是否成功，各表格和曲线长度符合预期。
    """
    tc = TimeConfig(start_hour=0, end_hour=23)
    case_data = load_case(CONFIG_PATH, tc)
    
    assert isinstance(case_data, CaseData)
    assert not case_data.zones.empty
    assert not case_data.thermal_units.empty
    assert not case_data.storage_units.empty
    
    # 检验曲线数据长度
    assert len(case_data.load_curves) == 24
    assert len(case_data.wind_curves) == 24
    assert len(case_data.pv_curves) == 24
    assert len(case_data.dc_flows) == 24

def test_unit_conversions():
    """
    测试数据载入过程中的单位自动转换：
    - 火电：变动运行费(元/kWh) * 1000 = vom_cost_per_mwh (元/MWh)
    - 储能：效率、SOC 从百分比转换为标幺值 0~1
    """
    tc = TimeConfig(start_hour=0, end_hour=0)
    case_data = load_case(CONFIG_PATH, tc)
    
    # 检查储能效率标幺值
    for col in ['charge_efficiency', 'discharge_efficiency']:
        assert case_data.storage_units[col].max() <= 1.0
        assert case_data.storage_units[col].min() >= 0.0

    # 检查火电机组的 vom_cost_per_mwh (变动运维 + 燃料换算费用)
    assert 'vom_cost_per_mwh' in case_data.thermal_units.columns
    assert (case_data.thermal_units['vom_cost_per_mwh'] > 100).all() # 燃料加变动运维必定大于 100 元/MWh

def test_data_validation():
    """
    测试载入的湖北数据是否能通过核心规则校验。
    """
    tc = TimeConfig(start_hour=0, end_hour=23)
    case_data = load_case(CONFIG_PATH, tc)
    
    report = validate_case_data(case_data)
    assert report.is_valid is True
    assert len(report.errors) == 0
    
    # 测试构造错误：故意制造重复 ID，期望触发校验失败
    bad_thermal = case_data.thermal_units.copy()
    bad_thermal.loc[1, 'unit_id'] = bad_thermal.loc[0, 'unit_id'] # 制造重复ID
    
    bad_case_data = CaseData(
        zones=case_data.zones,
        transmissions=case_data.transmissions,
        thermal_units=bad_thermal,
        hydro_units=case_data.hydro_units,
        storage_units=case_data.storage_units,
        pumped_storage_units=case_data.pumped_storage_units,
        load_curves=case_data.load_curves,
        wind_curves=case_data.wind_curves,
        pv_curves=case_data.pv_curves,
        hydro_flows=case_data.hydro_flows,
        dc_flows=case_data.dc_flows,
        metadata=case_data.metadata
    )
    
    bad_report = validate_case_data(bad_case_data)
    assert bad_report.is_valid is False
    assert any("重复的 'unit_id'" in err for err in bad_report.errors)
