# -*- coding: utf-8 -*-
import pandas as pd
from .excel_reader import load_excel

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
