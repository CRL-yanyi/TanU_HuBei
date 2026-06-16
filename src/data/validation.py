# -*- coding: utf-8 -*-
import pandas as pd
from .case_data import CaseData, DataValidationReport

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
