# -*- coding: utf-8 -*-
import os
from dataclasses import dataclass, field
from typing import Dict, Any
import pandas as pd


@dataclass
class SimulationResult:
    """
    统一的仿真结果数据结构，包含求解状态和多维度的时序运行结果 DataFrame。
    """
    # 求解器状态与指标
    status: str = "UNDEFINED"
    objective_value: float = float('nan')
    solve_time: float = 0.0

    # 补充求解器与指标
    best_bound: float = float('nan')
    mip_gap: float = float('nan')
    vars_num: int = 0
    bin_vars_num: int = 0
    cont_vars_num: int = 0
    cons_num: int = 0
    l_cons_num: int = 0
    q_cons_num: int = 0

    # 细分成本/电量指标
    gen_cost: float = 0.0
    gen_startup: float = 0.0
    gen_startdown: float = 0.0

    bes_pc: float = 0.0
    bes_pd: float = 0.0
    hes_pc: float = 0.0
    hes_pd: float = 0.0

    load_curt: float = 0.0
    runit_curt: float = 0.0
    runit_cost: float = 0.0

    consumption_rate: float = 0.0
    renewable_rate: float = 0.0

    # 结果时序数据表
    # 1. zonal_balance: columns=[zone, hour, load, thermal, hydro, wind, pv, storage_charge, storage_discharge, line_import, line_export, wind_curt, pv_curt, load_shed]
    zonal_balance: pd.DataFrame = field(default_factory=pd.DataFrame)
    
    # 2. thermal_units: columns=[unit_id, hour, power, is_on, startup, shutdown]
    thermal_units: pd.DataFrame = field(default_factory=pd.DataFrame)
    
    # 3. storage_units: columns=[unit_id, hour, charge_power, discharge_power, energy, is_charging, is_discharging]
    storage_units: pd.DataFrame = field(default_factory=pd.DataFrame)
    
    # 4. renewable_units: columns=[unit_id, hour, forecast_power, actual_power, curtailment, zone]
    renewable_units: pd.DataFrame = field(default_factory=pd.DataFrame)
    
    # 5. transmission_lines: columns=[line_id, hour, flow]
    transmission_lines: pd.DataFrame = field(default_factory=pd.DataFrame)

    def save_to_excel(self, file_path: str) -> None:
        """
        将所有运行结果 DataFrame 导出为多 Sheet 的 Excel 文件。
        """
        dir_name = os.path.dirname(file_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)

        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            # 1. 写入 Summary 页
            summary_data = [
                ("Running time(s)", self.solve_time),
                ("Objective value(y)", self.objective_value),
                ("best bound", self.best_bound),
                ("MIPGap", self.mip_gap),
                ("", ""),
                ("vars num", self.vars_num),
                ("bin vars num", self.bin_vars_num),
                ("cont vars num", self.cont_vars_num),
                ("cons num", self.cons_num),
                ("L cons num", self.l_cons_num),
                ("q cons num", self.q_cons_num),
                ("", ""),
                ("Gen_cost", self.gen_cost),
                ("Gen_StartUp", self.gen_startup),
                ("Gen_StartDown", self.gen_startdown),
                ("", ""),
                ("BES_PC", self.bes_pc),
                ("BES_PD", self.bes_pd),
                ("HES_PC", self.hes_pc),
                ("HES_PD", self.hes_pd),
                ("", ""),
                ("Load_Curt", self.load_curt),
                ("rUnit_Curt", self.runit_curt),
                ("rUnit_Cost", self.runit_cost),
                ("", ""),
                ("consumption rate", self.consumption_rate),
                ("renewable rate", self.renewable_rate)
            ]
            summary_df = pd.DataFrame(summary_data, columns=["指标", "数值"])
            summary_df.to_excel(writer, sheet_name="Summary", index=False)

            # 2. 写入火电机组出力数据表
            if not self.thermal_units.empty:
                # 只呈现出力，行是时间，列是各台机组
                thermal_pivot = self.thermal_units.pivot(index='hour', columns='unit_id', values='power')
                thermal_pivot.index.name = '时间'
                thermal_pivot.columns.name = '机组ID'
                thermal_pivot.to_excel(writer, sheet_name="ThermalUnits")

            # 3. 写入储能机组数据表
            if not self.storage_units.empty:
                # 纵坐标为时间，横坐标为各个机组以及充放电情况
                storage_pivot = self.storage_units.pivot(index='hour', columns='unit_id', values=['charge_power', 'discharge_power', 'energy'])
                # 重排级别，使 unit_id 在上方，指标在下方
                storage_pivot = storage_pivot.reorder_levels([1, 0], axis=1).sort_index(axis=1)
                storage_pivot.index.name = '时间'
                # 重命名底层指标列以提高可读性
                storage_pivot = storage_pivot.rename(columns={
                    'charge_power': '充电功率(MW)',
                    'discharge_power': '放电功率(MW)',
                    'energy': '蓄电量(MWh)'
                }, level=1)
                storage_pivot.columns.names = [None, None]
                storage_pivot.to_excel(writer, sheet_name="StorageUnits")

            # 4. 写入新能源数据表
            if not self.renewable_units.empty:
                # 横坐标为区域，纵坐标为时间
                if 'zone' in self.renewable_units.columns:
                    # 分区域和时间累加
                    ren_zone = self.renewable_units.groupby(['zone', 'hour'])[['actual_power', 'forecast_power', 'curtailment']].sum().reset_index()
                    ren_pivot = ren_zone.pivot(index='hour', columns='zone', values=['actual_power', 'forecast_power', 'curtailment'])
                    ren_pivot = ren_pivot.reorder_levels([1, 0], axis=1).sort_index(axis=1)
                    ren_pivot.index.name = '时间'
                    ren_pivot = ren_pivot.rename(columns={
                        'actual_power': '实际出力(MW)',
                        'forecast_power': '预测出力(MW)',
                        'curtailment': '弃电功率(MW)'
                    }, level=1)
                    ren_pivot.columns.names = [None, None]
                    ren_pivot.to_excel(writer, sheet_name="RenewableUnits")
                else:
                    # 兼容没有 zone 的情况，退化为按 unit_id 进行透视
                    ren_pivot = self.renewable_units.pivot(index='hour', columns='unit_id', values=['actual_power', 'forecast_power', 'curtailment'])
                    ren_pivot = ren_pivot.reorder_levels([1, 0], axis=1).sort_index(axis=1)
                    ren_pivot.index.name = '时间'
                    ren_pivot.columns.names = [None, None]
                    ren_pivot.to_excel(writer, sheet_name="RenewableUnits")

            # 5. 写入联络线数据表
            if not self.transmission_lines.empty:
                trans_pivot = self.transmission_lines.pivot(index='hour', columns='line_id', values='flow')
                trans_pivot.index.name = '时间'
                trans_pivot.columns.name = '联络线ID'
                trans_pivot.to_excel(writer, sheet_name="TransmissionLines")

            # 6. 保留原有的 ZonalBalance 页 (作为详细参考)
            if not self.zonal_balance.empty:
                self.zonal_balance.to_excel(writer, sheet_name="ZonalBalance", index=False)

    def save_to_csv(self, output_dir: str) -> None:
        """
        将所有运行结果分别保存为独立的 CSV 文件。
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # 导出汇总
        pd.DataFrame({
            "status": [self.status],
            "objective_value": [self.objective_value],
            "solve_time": [self.solve_time]
        }).to_csv(os.path.join(output_dir, "summary.csv"), index=False)

        if not self.zonal_balance.empty:
            self.zonal_balance.to_csv(os.path.join(output_dir, "zonal_balance.csv"), index=False)
        if not self.thermal_units.empty:
            self.thermal_units.to_csv(os.path.join(output_dir, "thermal_units.csv"), index=False)
        if not self.storage_units.empty:
            self.storage_units.to_csv(os.path.join(output_dir, "storage_units.csv"), index=False)
        if not self.renewable_units.empty:
            self.renewable_units.to_csv(os.path.join(output_dir, "renewable_units.csv"), index=False)
        if not self.transmission_lines.empty:
            self.transmission_lines.to_csv(os.path.join(output_dir, "transmission_lines.csv"), index=False)
