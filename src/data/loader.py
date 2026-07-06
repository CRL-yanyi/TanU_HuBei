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

    # 1.5 分区负荷、风电和光伏容量参数
    load_spec_file = config.get_file_path('load_spec', project_root)
    load_spec_df = list(load_excel(load_spec_file).values())[0]
    load_spec_df = load_spec_df.rename(columns=config.get_mapping('load_spec'))

    wind_spec_file = config.get_file_path('wind_spec', project_root)
    wind_spec_df = list(load_excel(wind_spec_file).values())[0]
    wind_spec_df = wind_spec_df.rename(
        columns=config.get_mapping('renewable_spec')
    )

    pv_spec_file = config.get_file_path('pv_spec', project_root)
    pv_spec_df = list(load_excel(pv_spec_file).values())[0]
    pv_spec_df = pv_spec_df.rename(
        columns=config.get_mapping('renewable_spec')
    )

    # 1.6 储能
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

    # 1.7 抽水蓄能
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
                # 保留原始流域名称中的“鄂”，与水电机组表的 basin_name 一致。
                name = f.replace('.xlsx', '').replace('.xls', '')
                proc_type = name[-2:]  # 平均、强迫、预想
                basin_name = name[:-2]
                
                if proc_type in ['平均', '强迫', '预想']:
                    file_path = os.path.join(basin_flow_dir, f)
                    sheets = load_excel(file_path)
                    first_df = list(sheets.values())[0]
                    # 1 row, 12 cols (representing 1-12 months)
                    # Convert to pd.Series representing 12 months
                    month_data = first_df.iloc[0].values[:12]
                    
                    if basin_name not in hydro_flows:
                        month_keys = [
                            pd.Timestamp(2030, month, 1).date()
                            for month in range(1, 13)
                        ]
                        hydro_flows[basin_name] = pd.DataFrame(
                            index=['平均', '强迫', '预想'],
                            columns=month_keys,
                        )
                    hydro_flows[basin_name].loc[proc_type] = month_data

    # 5. 时间范围切片
    if time_config is not None:
        time_index = time_config.time_index
        load_curves = load_curves.iloc[time_config.hours_list].copy()
        wind_curves = wind_curves.iloc[time_config.hours_list].copy()
        pv_curves = pv_curves.iloc[time_config.hours_list].copy()
        if not dc_flows.empty:
            dc_flows = dc_flows.iloc[time_config.hours_list].copy()
    else:
        time_index = pd.date_range(
            start="2030-01-01",
            periods=len(load_curves),
            freq="h",
        )

    # 所有逐时时序共享同一 DatetimeIndex，避免模型按位置错配资源数据。
    for frame in (load_curves, wind_curves, pv_curves):
        frame.index = time_index
    if not dc_flows.empty:
        dc_flows.index = time_index

    metadata = {
        'case_name': config.case_name,
        'case_config_path': case_config_path,
        'loaded_hours': len(load_curves),
        'scenario': scenario,
        'start_timestamp': time_index[0] if len(time_index) else None,
        'end_timestamp': time_index[-1] if len(time_index) else None,
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
        time_index=time_index,
        load_spec=load_spec_df,
        wind_spec=wind_spec_df,
        pv_spec=pv_spec_df,
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

    time_index = getattr(case_data, "time_index", None)
    if not isinstance(time_index, pd.DatetimeIndex):
        errors.append("CaseData.time_index 必须是 pandas.DatetimeIndex")
    elif len(time_index) != load_len:
        errors.append(
            f"CaseData.time_index 长度 {len(time_index)} 与时序长度 {load_len} 不一致"
        )
    else:
        if time_index.has_duplicates or not time_index.is_monotonic_increasing:
            errors.append("CaseData.time_index 必须无重复且严格递增")
        if len(time_index) >= 2:
            deltas = time_index[1:] - time_index[:-1]
            if any(delta != pd.Timedelta(hours=1) for delta in deltas):
                errors.append("CaseData.time_index 必须使用连续1小时时间步长")

    for name, frame in (
        ("load_curves", case_data.load_curves),
        ("wind_curves", case_data.wind_curves),
        ("pv_curves", case_data.pv_curves),
        ("dc_flows", case_data.dc_flows),
    ):
        if frame is None or frame.empty:
            if name != "dc_flows":
                errors.append(f"时序表 '{name}' 为空")
            continue
        if isinstance(time_index, pd.DatetimeIndex) and not frame.index.equals(
            time_index
        ):
            errors.append(f"时序表 '{name}' 的索引与 CaseData.time_index 不一致")
        values = frame.to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values < 0.0).any():
            errors.append(f"时序表 '{name}' 必须全部为有限非负数")
        if name in {"load_curves", "wind_curves", "pv_curves"} and (
            values > 1.0
        ).any():
            errors.append(f"标幺时序表 '{name}' 不得大于1.0")

    # 4. 分区负荷和风光装机参数校验
    load_spec = getattr(case_data, "load_spec", pd.DataFrame())
    if load_spec.empty or not {"zone_name", "peak_load_mw"}.issubset(
        load_spec.columns
    ):
        errors.append("load_spec 缺少 zone_name 或 peak_load_mw")
    else:
        missing_zones = zone_names - set(load_spec["zone_name"].astype(str))
        if missing_zones:
            errors.append(f"load_spec 缺少分区: {sorted(missing_zones)}")
        peak_values = pd.to_numeric(load_spec["peak_load_mw"], errors="coerce")
        if peak_values.isna().any() or (peak_values <= 0.0).any():
            errors.append("load_spec.peak_load_mw 必须为有限正数")

    month_columns = [f"month_{month:02d}_mw" for month in range(1, 13)]
    for name in ("wind_spec", "pv_spec"):
        spec = getattr(case_data, name, pd.DataFrame())
        required = {"zone_name", *month_columns}
        if spec.empty or not required.issubset(spec.columns):
            errors.append(f"{name} 缺少分区或12个月装机容量字段")
            continue
        missing_zones = zone_names - set(spec["zone_name"].astype(str))
        if missing_zones:
            errors.append(f"{name} 缺少分区: {sorted(missing_zones)}")
        capacity_values = spec[month_columns].apply(
            pd.to_numeric, errors="coerce"
        )
        if (
            capacity_values.isna().any().any()
            or not np.isfinite(capacity_values.to_numpy()).all()
            or (capacity_values < 0.0).any().any()
        ):
            errors.append(f"{name} 的月装机容量必须为有限非负数")

    # 5. 流域三段式完整性和上下界一致性
    expected_basins = (
        set(case_data.hydro_units["basin_name"].dropna().astype(str))
        if "basin_name" in case_data.hydro_units.columns
        else set()
    )
    actual_basins = set(case_data.hydro_flows)
    missing_basins = expected_basins - actual_basins
    if missing_basins:
        errors.append(f"hydro_flows 缺少流域: {sorted(missing_basins)}")
    for basin_name in sorted(expected_basins & actual_basins):
        flow = case_data.hydro_flows[basin_name]
        required_rows = {"平均", "强迫", "预想"}
        if not required_rows.issubset(flow.index) or len(flow.columns) != 12:
            errors.append(f"流域 {basin_name} 缺少平均、强迫、预想或12个月数据")
            continue
        numeric = flow.loc[["平均", "强迫", "预想"]].apply(
            pd.to_numeric, errors="coerce"
        )
        if (
            numeric.isna().any().any()
            or not np.isfinite(numeric.to_numpy()).all()
            or (numeric < 0.0).any().any()
            or (numeric > 1.0).any().any()
        ):
            errors.append(f"流域 {basin_name} 三段式系数必须位于[0, 1]")
            continue
        conflict = (
            (numeric.loc["强迫"] > numeric.loc["平均"])
            | (numeric.loc["平均"] > numeric.loc["预想"])
        )
        if conflict.any():
            errors.append(f"流域 {basin_name} 存在强迫、平均、预想顺序冲突")

    # 6. 物理参数合理性校验
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
        'curve_length_hours': load_len,
        'time_start': time_index[0] if isinstance(time_index, pd.DatetimeIndex) and len(time_index) else None,
        'time_end': time_index[-1] if isinstance(time_index, pd.DatetimeIndex) and len(time_index) else None,
        'hydro_basin_processes': len(actual_basins),
    }

    return DataValidationReport(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
        summary=summary
    )
