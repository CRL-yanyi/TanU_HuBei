# -*- coding: utf-8 -*-
import os
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

    def get_file_path(self, file_key, base_path=None):
        # 算出文件绝对路径
        filename = self.files.get(file_key)
        if not filename:
            raise ValueError(f"配置文件中没有找到文件代号: '{file_key}'，请检查 YAML 文件。")
        if base_path:
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
        self.start_hour = start_hour  # 0-indexed hour of the year (0 to 8759)
        self.end_hour = end_hour      # 0-indexed hour of the year (0 to 8759)
        self.start_date = start_date

    @property # 函数包装为变量
    def hours_list(self):
        return list(range(self.start_hour, self.end_hour + 1))

    @property
    def duration_hours(self):
        return self.end_hour - self.start_hour + 1


def load_case_config(config_path):
    # 输入路径得到配置好的CaseConfig
    with open(config_path, 'r', encoding='utf-8') as f:
        case_dict = yaml.safe_load(f)
    return CaseConfig(case_dict)
