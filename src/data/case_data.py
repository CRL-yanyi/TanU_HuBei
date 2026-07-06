# -*- coding: utf-8 -*-
import pandas as pd
from typing import Dict, List

class CaseData:
    """
    统一的数据载入载体结构，直接供给对象层构建 Grid 使用。
    """

    def __init__(
        self,
        zones,
        transmissions,
        thermal_units,
        hydro_units,
        storage_units,
        pumped_storage_units,
        load_curves,
        wind_curves,
        pv_curves,
        hydro_flows=None,
        dc_flows=None,
        metadata=None,
        *,
        time_index=None,
        load_spec=None,
        wind_spec=None,
        pv_spec=None,
    ):

        self.zones = zones                  # 分区
        self.transmissions = transmissions  # 输电线路
        self.thermal_units = thermal_units  # 火电机组
        self.hydro_units = hydro_units      # 水电机组
        self.storage_units = storage_units  # 储能机组
        self.pumped_storage_units = pumped_storage_units # 抽蓄机组
    
        # 8760 小时时序曲线数据
        self.load_curves = load_curves      # 全年负荷曲线
        self.wind_curves = wind_curves      # 全年风光曲线
        self.pv_curves = pv_curves          # 全年光伏曲线
        self.time_index = (
            time_index
            if time_index is not None
            else getattr(load_curves, "index", pd.DatetimeIndex([]))
        )

        # 分区负荷及风光月装机参数。可选默认值保持脱敏旧测试兼容。
        self.load_spec = load_spec if load_spec is not None else pd.DataFrame()
        self.wind_spec = wind_spec if wind_spec is not None else pd.DataFrame()
        self.pv_spec = pv_spec if pv_spec is not None else pd.DataFrame()

        # 流域流量/出力过程线 (字典存储)
        self.hydro_flows = hydro_flows if hydro_flows is not None else {}
        # 外部直流输入时序 (Pandas表格)
        self.dc_flows = dc_flows if dc_flows is not None else pd.DataFrame()
        # 算例元数据 (创建时间、版本号等)
        self.metadata = metadata if metadata is not None else {}


class DataValidationReport:
    """
    存储数据校验过程中的错误、警告与结构化摘要。
    """
    def __init__(self, is_valid, errors=None, warnings=None, summary=None):

        self.is_valid = is_valid
        self.errors = errors if errors is not None else []
        self.warnings = warnings if warnings is not None else []
        self.summary = summary if summary is not None else {}

    def print_report(self):
        print(f"--- Data Validation Report (Valid: {self.is_valid}) ---")
        print(f"Summary: {self.summary}")
        if self.errors:
            print("Errors:")
            for err in self.errors:
                print(f"  - [ERROR] {err}")
        if self.warnings:
            print("Warnings:")
            for warn in self.warnings:
                print(f"  - [WARN] {warn}")
