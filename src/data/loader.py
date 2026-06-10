# -*- coding: utf-8 -*-
import os
import re
import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple
from .config import CaseConfig, TimeConfig, load_case_config
from .case_data import CaseData, DataValidationReport

def parse_xml_spreadsheet(file_path: str) -> Dict[str, pd.DataFrame]:
    """
    解析 XML Spreadsheet 2003 格式的 Excel 文件，并进行特殊字符（如 &）容错处理。
    """
    namespaces = {'ss': 'urn:schemas-microsoft-com:office:spreadsheet'}
    with open(file_path, 'rb') as f:
        content = f.read()
    
    # 预处理：替换未转义的 & 符号，防止 XML 解析器报错
    content = content.replace(b'&', b'&amp;')
    content = content.replace(b'&amp;amp;', b'&amp;')
    content = content.replace(b'&amp;lt;', b'&lt;')
    content = content.replace(b'&amp;gt;', b'&gt;')
    content = content.replace(b'&amp;quot;', b'&quot;')
    content = content.replace(b'&amp;apos;', b'&apos;')
    
    # 解码
    try:
        content_str = content.decode('utf-8')
    except UnicodeDecodeError:
        content_str = content.decode('gbk', errors='ignore')
        
    root = ET.fromstring(content_str.encode('utf-8'))
    worksheets = root.findall('.//ss:Worksheet', namespaces)
    sheets_dict = {}
    
    for ws in worksheets:
        sheet_name = ws.get('{urn:schemas-microsoft-com:office:spreadsheet}Name')
        table = ws.find('.//ss:Table', namespaces)
        if table is None:
            continue
            
        rows_data = []
        rows = table.findall('.//ss:Row', namespaces)
        for r in rows:
            cells_data = []
            cells = r.findall('.//ss:Cell', namespaces)
            for c in cells:
                # 处理可能包含的 ss:Index 属性（跳过空列）
                index_attr = c.get('{urn:schemas-microsoft-com:office:spreadsheet}Index')
                if index_attr is not None:
                    target_idx = int(index_attr) - 1
                    while len(cells_data) < target_idx:
                        cells_data.append(None)
                
                data_el = c.find('.//ss:Data', namespaces)
                if data_el is not None:
                    cells_data.append(data_el.text)
                else:
                    cells_data.append(None)
            rows_data.append(cells_data)
            
        if not rows_data:
            continue
            
        # 对齐列长度
        max_len = max(len(row) for row in rows_data)
        for row in rows_data:
            while len(row) < max_len:
                row.append(None)
                
        # 处理表头与重复列名
        header = rows_data[0]
        seen = {}
        resolved_header = []
        for i, h in enumerate(header):
            if h is None or h == '':
                name = f"Unnamed: {i}"
            else:
                name = str(h).strip()
            if name in seen:
                seen[name] += 1
                name = f"{name}.{seen[name]}"
            else:
                seen[name] = 0
            resolved_header.append(name)
            
        df = pd.DataFrame(rows_data[1:], columns=resolved_header)
        
        # 自动尝试将数字类型的字符串转换为数值
        for col in df.columns:
            try:
                df[col] = pd.to_numeric(df[col])
            except (ValueError, TypeError):
                pass
                
        sheets_dict[sheet_name] = df
        
    return sheets_dict


def load_excel(file_path: str) -> Dict[str, pd.DataFrame]:
    """
    智能载入 Excel 文件，自动识别标准 Excel 与 XML Spreadsheet 2003。
    """
    is_xml_spreadsheet = False
    try:
        with open(file_path, 'rb') as f:
            start_bytes = f.read(100)
            if b'<?xml' in start_bytes:
                is_xml_spreadsheet = True
    except Exception:
        pass
        
    if is_xml_spreadsheet:
        return parse_xml_spreadsheet(file_path)
    else:
        xls = pd.ExcelFile(file_path)
        return {sheet: pd.read_excel(xls, sheet_name=sheet) for sheet in xls.sheet_names}


def flatten_365_24_to_8760(df: pd.DataFrame) -> pd.Series:
    """
    将 365天 * 24小时 的二维行排列 DataFrame 展平为 8760 小时的一维时序数据。
    """
    # 过滤掉非小时字段，通常保留 0-23、0时-23时或后 24 列
    hourly_cols = [c for c in df.columns if c != '日期' and c != 'Date' and not str(c).startswith('Unnamed')]
    if len(hourly_cols) != 24:
        # fallback: 直接取最后 24 列
        hourly_cols = list(df.columns[-24:])
    
    # 扁平化数据
    flat_data = df[hourly_cols].values.flatten()
    return pd.Series(flat_data)


def load_single_curve(file_path: str) -> pd.Series:
    """
    通用曲线加载器：自动处理 365*24 二维格式 与 8760*2 一维格式。
    """
    sheets = load_excel(file_path)
    first_sheet = list(sheets.values())[0]
    
    if first_sheet.shape[1] >= 24:
        # 365天 * 24小时格式
        return flatten_365_24_to_8760(first_sheet)
    else:
        # 8760 一维行格式，取第二列数据
        val_col = [c for c in first_sheet.columns if c != '日期' and c != 'Date'][0]
        return first_sheet[val_col]


def get_zone_by_grid(grid_name: str, mapping: dict) -> str:
    """
    根据所属电网名称及配置的映射字典推导所属分区。
    """
    if not isinstance(grid_name, str) or not mapping:
        return ""
    for city, zone in mapping.items():
        if city in grid_name:
            return zone
    return ""


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
    if 'fuel_cost_per_kwh' in thermal_df.columns:
        # 若原始数据为空，提供默认值 0.35 元/kWh (即 350 元/MWh) 以免 NaN 导致计算或求解报错
        thermal_df['fuel_cost_per_kwh'] = thermal_df['fuel_cost_per_kwh'].fillna(0.35)
        thermal_df['fuel_cost_per_mwh'] = thermal_df['fuel_cost_per_kwh'] * 1000.0
        
        # 若无变动运维成本，默认为 0.0 元/MWh
        vom_series = thermal_df['vom_cost_per_mwh'] if 'vom_cost_per_mwh' in thermal_df.columns else pd.Series(0.0, index=thermal_df.index)
        vom_series = vom_series.fillna(0.0)
        thermal_df['vom_cost_per_mwh'] = vom_series + thermal_df['fuel_cost_per_mwh']
        
    # 1.4 水电
    hydro_file = config.get_file_path('hydro', project_root)
    hydro_df = list(load_excel(hydro_file).values())[0]
    hydro_df = hydro_df.rename(columns=config.get_mapping('hydro'))
    
    # 1.5 储能
    storage_file = config.get_file_path('storage', project_root)
    storage_df = list(load_excel(storage_file).values())[0]
    
    # 构造或推导缺少的属性
    # 1.5.1 初始电量(%) = 50.0
    storage_df['初始电量(%)'] = 50.0
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
    
    # 构造或推导缺少的属性
    # 1.6.1 初始电量(%) = 50.0 (默认值)
    pumped_df['初始电量(%)'] = 50.0
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

        # 2.2 风电 (优先在多场景文件夹找场景专属文件，找不到则回退到基础文件)
        wind_filename = wind_pattern.format(zone=z, suffix=suffix)
        wind_file_path = os.path.join(scenario_dir, wind_filename)
        if not os.path.exists(wind_file_path):
            wind_file_path = os.path.join(scenario_dir, wind_pattern.format(zone=z, suffix=""))
        wind_dict[z] = load_single_curve(wind_file_path)

        # 2.3 光伏 (若有特定分区命名覆盖则用覆盖模板，否则用默认模板)
        pv_filename = pv_pattern.format(zone=z, suffix=suffix)
        pv_file_path = os.path.join(scenario_dir, pv_filename)
        if not os.path.exists(pv_file_path):
            pv_file_path = os.path.join(scenario_dir, pv_pattern.format(zone=z, suffix=""))
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


def validate_case_data(case_data: CaseData) -> DataValidationReport:
    """
    对已载入的数据类做业务和物理常识性校验。
    """
    errors = []
    warnings = []
    
    # 1. 检验必填字段与非空
    for name, df in [
        ('zones', case_data.zones),
        ('transmissions', case_data.transmissions),
        ('thermal_units', case_data.thermal_units),
        ('hydro_units', case_data.hydro_units),
        ('storage_units', case_data.storage_units)
    ]:
        if df.empty:
            errors.append(f"数据表 '{name}' 为空，无法进行生产模拟！")
            continue
            
        # 必须含有主键列
        if name.endswith('units'):
            if 'unit_id' not in df.columns:
                errors.append(f"数据表 '{name}' 缺少必需的主键列 'unit_id'！")
            else:
                # 检查主键是否重复
                dups = df['unit_id'].duplicated().sum()
                if dups > 0:
                    errors.append(f"数据表 '{name}' 存在 {dups} 个重复的 'unit_id' 机组编码！")
                    
    # 2. 检查分区与资源关联关系是否闭环
    zone_names = set(case_data.zones['zone_name'].tolist()) if 'zone_name' in case_data.zones.columns else set()
    
    # 各机组的分区列
    for unit_type, df in [
        ('火电', case_data.thermal_units),
        ('水电', case_data.hydro_units),
        ('储能', case_data.storage_units)
    ]:
        if not df.empty and 'zone_name' in df.columns:
            unassociated = df[~df['zone_name'].isin(zone_names)]['unit_id'].tolist()
            if unassociated:
                errors.append(f"以下{unit_type}机组关联的分区未在分区表中定义: {unassociated}")
                
    # 联络线的分区关联
    if not case_data.transmissions.empty and 'zone_from' in case_data.transmissions.columns and 'zone_to' in case_data.transmissions.columns:
        for side in ['zone_from', 'zone_to']:
            unassociated_trans = case_data.transmissions[
                ~case_data.transmissions[side].isin(zone_names) & 
                (case_data.transmissions[side] != '外部电网')
            ]['line_name'].tolist()
            if unassociated_trans:
                warnings.append(f"以下联络线的 {side} 分区未在分区表中定义且不是'外部电网': {unassociated_trans}")

    # 3. 时序数据校验
    load_len = len(case_data.load_curves)
    wind_len = len(case_data.wind_curves)
    pv_len = len(case_data.pv_curves)
    
    if load_len != wind_len or load_len != pv_len:
        errors.append(f"时序曲线数据长度不一致！负荷: {load_len}, 风电: {wind_len}, 光伏: {pv_len}")
        
    # 检查负荷曲线是否含有负值
    if not case_data.load_curves.empty:
        neg_loads = (case_data.load_curves < 0).sum().sum()
        if neg_loads > 0:
            errors.append("负荷曲线中检测到负数负荷值，请检查原始数据！")

    # 4. 物理参数合理性校验
    # 储能效率和 SOC 范围 [0, 1]
    if not case_data.storage_units.empty:
        for col in ['charge_efficiency', 'discharge_efficiency']:
            if col in case_data.storage_units.columns:
                eff_violations = case_data.storage_units[
                    (case_data.storage_units[col] < 0) |
                    (case_data.storage_units[col] > 1.0)
                ]['unit_id'].tolist()
                if eff_violations:
                    errors.append(f"以下储能机组的 {col} 超出标幺值范围 [0, 1.0]: {eff_violations}")

    # 机组出力上下限关系: p_min_mw <= p_max_mw
    if not case_data.thermal_units.empty and 'p_min_mw' in case_data.thermal_units.columns and 'p_max_mw' in case_data.thermal_units.columns:
        violations = case_data.thermal_units[
            case_data.thermal_units['p_min_mw'] > case_data.thermal_units['p_max_mw']
        ]['unit_id'].tolist()
        if violations:
            errors.append(f"以下火电机组的最小出力大于最大出力限制: {violations}")

    is_valid = len(errors) == 0
    summary = {
        'total_zones': len(case_data.zones),
        'total_thermal_units': len(case_data.thermal_units),
        'total_hydro_units': len(case_data.hydro_units),
        'total_storage_units': len(case_data.storage_units),
        'total_pumped_storage_units': len(case_data.pumped_storage_units),
        'curve_length_hours': load_len
    }

    return DataValidationReport(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
        summary=summary
    )
