# -*- coding: utf-8 -*-
import os
import pandas as pd
from typing import Dict, List, Tuple
from .config import CaseConfig, TimeConfig, load_case_config
from .case_data import CaseData
from .excel_reader import load_excel
from .helpers import load_single_curve, get_zone_by_grid
from .validation import validate_case_data

def load_case(case_config_path: str, time_config: TimeConfig = None, scenario: int = None) -> CaseData:
    """
    核心函数：加载湖北2030所有文件，做英文重命名与单位换算，并按时间范围切片。
    """
    # 计算项目根目录 (case_config_path 位于 configs/cases/ 下，往上退 3 级即为项目根目录)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(case_config_path))))
    config = load_case_config(case_config_path)
    
    # 1. 读取拓扑与基础机组
    # 1.1 分区
    zone_file = config.get_file_path('zone', project_root)
    zone_df = list(load_excel(zone_file).values())[0]
    zone_df = zone_df.rename(columns=config.get_mapping('zone'))
    
    # 1.2 联络线与断面
    trans_file = config.get_file_path('transmission', project_root)
    trans_df = list(load_excel(trans_file).values())[0]
    trans_df = trans_df.rename(columns=config.get_mapping('transmission'))
    
    # 1.3 火电
    thermal_file = config.get_file_path('thermal', project_root)
    thermal_df = list(load_excel(thermal_file).values())[0]
    thermal_df = thermal_df.rename(columns=config.get_mapping('thermal'))

    # 火电机组变动成本换算: 变动运行费(元/kWh) * 1000 = 元/MWh
    thermal_defaults = config.parameter_defaults.get('thermal', {})
    if 'fuel_cost_per_kwh' not in thermal_defaults or 'vom_cost_per_mwh' not in thermal_defaults:
        raise KeyError(
            "配置文件中的 'parameter_defaults.thermal' 节点必须配置 'fuel_cost_per_kwh' 和 'vom_cost_per_mwh'！")
    default_fuel_cost = thermal_defaults['fuel_cost_per_kwh']
    default_vom_cost = thermal_defaults['vom_cost_per_mwh']
    # 火电机组变动成本换算: 变动运行费(元/千瓦时) * 1000 = 元/MWh
    if 'fuel_cost_per_kwh' in thermal_df.columns:
        # 若原始数据为空，提供配置中的默认燃料成本
        thermal_df['fuel_cost_per_kwh'] = thermal_df['fuel_cost_per_kwh'].fillna(default_fuel_cost)
        thermal_df['fuel_cost_per_mwh'] = thermal_df['fuel_cost_per_kwh'] * 1000.0

        # 若无变动运维成本，使用配置中的默认运维成本
        vom_series = thermal_df['vom_cost_per_mwh'] if 'vom_cost_per_mwh' in thermal_df.columns else pd.Series(0.0,
                                                                                                               index=thermal_df.index)
        vom_series = vom_series.fillna(default_vom_cost)
        thermal_df['vom_cost_per_mwh'] = vom_series + thermal_df['fuel_cost_per_mwh']

    # 1.4 水电
    hydro_file = config.get_file_path('hydro', project_root)
    hydro_df = list(load_excel(hydro_file).values())[0]
    hydro_df = hydro_df.rename(columns=config.get_mapping('hydro'))

    # 1.5 储能
    storage_file = config.get_file_path('storage', project_root)
    storage_df = list(load_excel(storage_file).values())[0]

    # 从配置读取默认参数，如果缺失直接抛出报错
    storage_defaults = config.parameter_defaults.get('storage', {})
    if 'init_soc_percent' not in storage_defaults:
        raise KeyError("配置文件中的 'parameter_defaults.storage' 节点必须配置 'init_soc_percent'！")
    default_storage_soc = storage_defaults['init_soc_percent']

    # 构造或推导缺少的属性
    # 1.5.1 初始电量(%)
    storage_df['初始电量(%)'] = default_storage_soc

    # 1.5.2 额定容量(MWh) = 额定功率(MW) * 充电时间(h)
    if '额定功率(MW)' in storage_df.columns and '充电时间(h)' in storage_df.columns:
        storage_df['额定容量(MWh)'] = storage_df['额定功率(MW)'] * storage_df['充电时间(h)']
    # 1.5.3 所属分区
    if '所属电网' in storage_df.columns:
        storage_df['所属分区'] = storage_df['所属电网'].apply(lambda x: get_zone_by_grid(x, config.grid_zone_mapping))

    storage_df = storage_df.rename(columns=config.get_mapping('storage'))
    # 效率转为标幺值 0~1
    for col in ['charge_efficiency', 'discharge_efficiency']:
        if col in storage_df.columns:
            if storage_df[col].max() > 1.0:
                storage_df[col] = storage_df[col] / 100.0

    # 1.6 抽水蓄能
    pumped_file = config.get_file_path('pumped_storage', project_root)
    pumped_df = list(load_excel(pumped_file).values())[0]

    # 从配置读取默认参数，如果缺失直接抛出报错
    pumped_defaults = config.parameter_defaults.get('pumped_storage', {})
    if 'init_soc_percent' not in pumped_defaults:
        raise KeyError("配置文件中的 'parameter_defaults.pumped_storage' 节点必须配置 'init_soc_percent'！")

    default_pumped_soc = pumped_defaults['init_soc_percent']

    # 构造或推导缺少的属性
    # 1.6.1 初始电量(%)
    pumped_df['初始电量(%)'] = default_pumped_soc

    # 1.6.2 额定容量(MWh) = 额定功率(MW) * 抽水时间(h)
    if '额定功率(MW)' in pumped_df.columns and '抽水时间(h)' in pumped_df.columns:
        pumped_df['额定容量(MWh)'] = pumped_df['额定功率(MW)'] * pumped_df['抽水时间(h)']

    pumped_df = pumped_df.rename(columns=config.get_mapping('pumped_storage'))

    for col in ['charge_efficiency', 'discharge_efficiency']:
        if col in pumped_df.columns:
            if pumped_df[col].max() > 1.0:
                pumped_df[col] = pumped_df[col] / 100.0

    # 2. 读取基础与多场景时序曲线 (从 YAML 中读取曲线配置)
    curves_config = config.curves
    zones_list = curves_config.get('zones', [])
    load_pattern = curves_config.get('load_pattern', '{zone}负荷.xls')
    wind_pattern = curves_config.get('wind_pattern', '{zone}风{suffix}.xls')
    pv_pattern = curves_config.get('pv_pattern', '{zone}光{suffix}.xls')

    load_dict = {}
    wind_dict = {}
    pv_dict = {}

    # 场景回退机制实现：获取多场景文件夹路径和后缀
    scenario_dir = config.get_dir_path('multi_scenario', project_root)
    suffix = str(scenario) if (scenario is not None and scenario != 0) else ""

    for z in zones_list:
        # 2.1 负荷 (按模板动态渲染文件名)
        load_filename = load_pattern.format(zone=z)
        load_dict[z] = load_single_curve(
            os.path.normpath(os.path.join(project_root, config.data_root, load_filename)))

        # 2.2 风电 (优先在多场景文件夹找场景专属文件，找不到直接抛出 FileNotFoundError)
        wind_filename = wind_pattern.format(zone=z, suffix=suffix)
        wind_file_path = os.path.join(scenario_dir, wind_filename)
        if not os.path.exists(wind_file_path):
            raise FileNotFoundError(
                f"[ERROR] 场景数据缺失：未找到分区 '{z}' 在场景 '{scenario}' 下的风电时序文件: {wind_file_path}"
            )
        wind_dict[z] = load_single_curve(wind_file_path)
        # 2.3 光伏 (优先在多场景文件夹找场景专属文件，找不到直接抛出 FileNotFoundError)
        pv_filename = pv_pattern.format(zone=z, suffix=suffix)
        pv_file_path = os.path.join(scenario_dir, pv_filename)
        if not os.path.exists(pv_file_path):
            raise FileNotFoundError(
                f"[ERROR] 场景数据缺失：未找到分区 '{z}' 在场景 '{scenario}' 下的光伏时序文件: {pv_file_path}"
            )
        pv_dict[z] = load_single_curve(pv_file_path)

    load_curves = pd.DataFrame(load_dict)
    wind_curves = pd.DataFrame(wind_dict)
    pv_curves = pd.DataFrame(pv_dict)

    # 3. 读取外来电直流电力流 (电力流/ 365*25 格式)
    flow_dir = config.get_dir_path('power_flows', project_root)

    # 此时 dc_lines 是一个字典：{"列名": "文件名"}
    dc_lines_dict = config.dc_flows_config.get('lines', {})
    dc_dict = {}

    for line_clean_name, file_key in dc_lines_dict.items():
        file_path = os.path.join(flow_dir, f"{file_key}.xlsx")
        if os.path.exists(file_path):
            dc_dict[line_clean_name] = load_single_curve(file_path)

    dc_flows = pd.DataFrame(dc_dict)

    # 4. 读取流域三段式流量过程 (流域三段式/ 1*12 格式)
    basin_flow_dir = config.get_dir_path('hydro_basin_flows', project_root)
    hydro_flows = {}
    if os.path.exists(basin_flow_dir):
        for f in os.listdir(basin_flow_dir):
            if f.endswith(('.xls', '.xlsx')) and f.startswith('鄂'):
                # 解析文件名中的流域和类型，例如 鄂三峡平均.xls -> basin='三峡', type='平均'
                name = f.replace('.xlsx', '').replace('.xls', '')
                proc_type = name[-2:]  # 平均、强迫、预想
                basin_name = name[1:-2] # 移除前面的 '鄂' 和后面的类型
                
                if proc_type in ['平均', '强迫', '预想']:
                    file_path = os.path.join(basin_flow_dir, f)
                    sheets = load_excel(file_path)
                    first_df = list(sheets.values())[0]
                    # 1 row, 12 cols (representing 1-12 months)
                    # Convert to pd.Series representing 12 months
                    month_data = first_df.iloc[0].values[:12]
                    
                    if basin_name not in hydro_flows:
                        hydro_flows[basin_name] = pd.DataFrame(index=['平均', '强迫', '预想'], columns=list(range(1, 13)))
                    hydro_flows[basin_name].loc[proc_type] = month_data

    # 5. 时间范围切片
    if time_config is not None:
        load_curves = load_curves.iloc[time_config.hours_list].reset_index(drop=True)
        wind_curves = wind_curves.iloc[time_config.hours_list].reset_index(drop=True)
        pv_curves = pv_curves.iloc[time_config.hours_list].reset_index(drop=True)
        if not dc_flows.empty:
            dc_flows = dc_flows.iloc[time_config.hours_list].reset_index(drop=True)

    metadata = {
        'case_config_path': case_config_path,
        'loaded_hours': len(load_curves),
        'scenario': scenario
    }

    return CaseData(
        zones=zone_df,
        transmissions=trans_df,
        thermal_units=thermal_df,
        hydro_units=hydro_df,
        storage_units=storage_df,
        pumped_storage_units=pumped_df,
        load_curves=load_curves,
        wind_curves=wind_curves,
        pv_curves=pv_curves,
        hydro_flows=hydro_flows,
        dc_flows=dc_flows,
        metadata=metadata
    )
