# -*- coding: utf-8 -*-
import os
import pandas as pd
import yaml

class CaseConfig:
    """
    配置算例数据文件的具体存放路径、原始单位和中英文列名映射。
    """
    def __init__(self, case_dict):
        self.case_name = case_dict.get('case_name', 'hubei2030')
        self.data_root = case_dict.get('data_root', './湖北2030')
        self.files = case_dict.get('files', {})
        self.directories = case_dict.get('directories', {})
        self.field_mappings = case_dict.get('field_mappings', {})

        self.curves = case_dict.get('curves', {})
        self.dc_flows_config = case_dict.get('dc_flows_config', {})
        self.grid_zone_mapping = case_dict.get('grid_zone_mapping', {})
        self.parameter_defaults = case_dict.get('parameter_defaults', {})

    def get_file_path(self, file_key, base_path=None):
        # 算出文件绝对路径
        filename = self.files.get(file_key)
        if not filename:
            raise ValueError(f"配置文件中没有找到文件代号: '{file_key}'，请检查 YAML 文件。")
        if base_path:
            # 如果提供了 base_path (即项目根目录)，拼接为: base_path + data_root + filename
            return os.path.normpath(os.path.join(base_path, self.data_root, filename))
        return os.path.normpath(os.path.join(self.data_root, filename))

    def get_dir_path(self, dir_key, base_path=None):
        # 算出文件夹绝对路径
        dirname = self.directories.get(dir_key)
        if not dirname:
            raise ValueError(f"配置文件中没有找到文件夹代号: '{dir_key}'，请检查 YAML 文件。")
        if base_path:
            return os.path.normpath(os.path.join(base_path, self.data_root, dirname))
        return os.path.normpath(os.path.join(self.data_root, dirname))

    def get_mapping(self, mapping_key):
        return self.field_mappings.get(mapping_key, {})


class TimeConfig:
    """
    配置模拟运行的时间范围和步长，辅助时序数据切片。
    """
    def __init__(self, start_hour=0, end_hour=23, start_date="2030-01-01"):
        self.start_hour = int(start_hour)  # 0-indexed hour of the year (0 to 8759)
        self.end_hour = int(end_hour)      # 0-indexed hour of the year (0 to 8759)
        self.start_date = str(start_date)
        if self.start_hour < 0:
            raise ValueError("start_hour must be nonnegative")
        if self.end_hour < self.start_hour:
            raise ValueError("end_hour must not be earlier than start_hour")

    @property # 函数包装为变量
    def hours_list(self):
        return list(range(self.start_hour, self.end_hour + 1))

    @property
    def duration_hours(self):
        return self.end_hour - self.start_hour + 1

    @property
    def time_index(self) -> pd.DatetimeIndex:
        """返回与年内小时序号对应的规范逐小时时间索引。"""
        start = pd.Timestamp(self.start_date) + pd.Timedelta(hours=self.start_hour)
        return pd.date_range(start=start, periods=self.duration_hours, freq="h")


def load_case_config(config_path):
    # 输入路径得到配置好的CaseConfig
    with open(config_path, 'r', encoding='utf-8') as f:
        case_dict = yaml.safe_load(f)
    return CaseConfig(case_dict)

class RunConfig:
    """
    成员五运行层配置。

    这个类只做 YAML 到属性的轻量转换，不在这里写建模逻辑。
    保留 member5_0623 中 runner.py 需要的字段名，例如 solver_name、
    rolling_enable、window_hours、overlap_hours 等。
    """

    def __init__(self, run_dict):
        run_dict = run_dict or {}

        self.case_name = run_dict.get("case_name", "hubei2030")
        self.scenario = run_dict.get("scenario", 0)

        simulation = run_dict.get("simulation", {})
        self.mode = str(simulation.get("mode", "UC")).upper()
        self.start_hour = int(simulation.get("start_hour", 0))
        self.end_hour = int(simulation.get("end_hour", 167))
        self.step_hours = float(simulation.get("step_hours", 1.0))

        if self.step_hours != 1.0:
            raise ValueError("当前 TimeConfig 只支持按整小时 start_hour/end_hour 切片，请先保持 step_hours=1.0。")

        solver = run_dict.get("solver", {})
        self.solver_name = str(solver.get("name", "GUROBI")).upper()
        self.mip_gap = float(solver.get("mip_gap", 0.01))
        self.time_limit = int(solver.get("time_limit", 300))
        self.log_to_console = bool(solver.get("log_to_console", False))

        rolling = run_dict.get("rolling", {})
        self.rolling_enable = bool(rolling.get("enable", True))
        self.window_hours = int(rolling.get("window_hours", self.end_hour - self.start_hour + 1))
        self.overlap_hours = int(rolling.get("overlap_hours", 0))

        switches = run_dict.get("switches", {})
        self.include_load_shedding = bool(switches.get("include_load_shedding", True))
        self.enable_transmission = bool(switches.get("enable_transmission", True))

        # 下面这些先保留字段，方便兼容上一版配置；当前 runner 不主动启用未完成模块。
        self.enable_reserve = bool(switches.get("enable_reserve", False))
        self.enable_cascade_hydro = bool(switches.get("enable_cascade_hydro", False))

        self.curtailment_penalty_wind = float(switches.get("curtailment_penalty_wind", 500.0))
        self.curtailment_penalty_pv = float(switches.get("curtailment_penalty_pv", 500.0))
        self.load_shed_penalty = float(switches.get("load_shed_penalty", 100000.0))

        self.default_load_reserve_rate = float(switches.get("default_load_reserve_rate", 0.03))
        self.default_contingency_reserve_rate = float(switches.get("default_contingency_reserve_rate", 0.02))
        self.default_spinning_reserve_rate = float(switches.get("default_spinning_reserve_rate", 0.5))


def load_run_config(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        run_dict = yaml.safe_load(f)
    return RunConfig(run_dict)