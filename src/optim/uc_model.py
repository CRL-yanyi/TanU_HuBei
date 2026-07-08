# -*- coding: utf-8 -*-
from typing import Any, Iterable, Hashable, Dict
import pandas as pd
import pyoptinterface as poi

from src.scenario import ScenarioSet
from src.optim.opt_model import OptModel

from src.optim.variables import (
    setThermalVarList,
    setHydroVarList,
    setStorageVarList,
    setRenewableVarList,
    setIntertranVarList,
    setLoadSheddingVarList,
)
from src.optim.constraints.thermal import setThermalUCCons, setThermalEDCons
from src.optim.constraints.hydro import setHydroConstraints
from src.optim.constraints.storage import setStorageConstraints
from src.optim.constraints.renewable import setRenewableConstraints
from src.optim.constraints.transmission import setIntertranCons
from src.optim.constraints.power_balance import setPowerBalanceCons
from src.optim.constraints.reserve import setSystemReserveCons
from src.optim.objectives import setProductionObjective


class UCModel:
    """
    单个时间窗口内的 Unit Commitment (机组组合) 优化模型封装类
    """
    def __init__(self, solver_name: str, time_limit: float, mip_gap: float, log_to_console: bool = False):
        self.solver_name = solver_name
        self.time_limit = time_limit
        self.mip_gap = mip_gap
        self.log_to_console = log_to_console

        self.optmodel = OptModel(modelName="window_uc",solver=self.solver_name,)

        # 保留 member5_0623 中 runner.py 对 uc_model.model 的访问方式
        self.model = self.optmodel.model

        # 求解器参数设置
        try:
            self.model.set_raw_parameter("MIPGap", float(self.mip_gap))
        except Exception:
            pass

        try:
            self.model.set_model_attribute(poi.ModelAttribute.TimeLimitSec,float(self.time_limit),)
        except Exception:
            pass

        try:
            self.model.set_model_attribute(poi.ModelAttribute.Silent,not self.log_to_console,)
        except Exception:
            pass

        self.periods = None          # DatetimeIndex
        self.period_alias = {}       # int hour -> Timestamp

        # 变量占位符
        self.thermal_vars = None
        self.hydro_vars = None
        self.storage_vars = None
        self.renewable_vars = None
        self.trans_vars = None
        self.load_shed_vars = None

    @property
    def load_shed(self):
        """兼容接口：返回失负荷变量字典"""
        return self.load_shed_vars.load_shed if self.load_shed_vars else {}

    def _to_time_index(self, periods, case_data, run_config) -> pd.DatetimeIndex:
        """
        兼容旧 runner.py 传入的整数小时 periods。
        新版约束内部统一使用 DatetimeIndex。
        """
        if isinstance(periods, pd.DatetimeIndex):
            time_idx = periods
            self.period_alias = {p: p for p in time_idx}
            return time_idx

        periods = list(periods)
        if not periods:
            raise ValueError("periods must not be empty")

        start_offset = int(periods[0]) - int(run_config.start_hour)
        end_offset = int(periods[-1]) - int(run_config.start_hour)

        time_idx = case_data.time_index[start_offset:end_offset + 1]

        self.period_alias = {
            old_period: timestamp
            for old_period, timestamp in zip(periods, time_idx)
        }

        return time_idx

    def to_timestamp(self, period):
        """
        把旧 runner.py 中的整数小时转换为新版变量使用的 Timestamp。
        如果本身已经是 Timestamp，则原样返回。
        """
        return self.period_alias.get(period, period)

    def to_period(self, period):
        return self.to_timestamp(period)

    def build(self, grid, periods: list[int], run_config, case_data, states: dict):
        """
        核心装配方法：定义变量 -> 拼装约束 -> 设置目标函数
        """
        self.periods = self._to_time_index(periods, case_data, run_config)

        self.add_variables(grid, self.periods, run_config)
        self.add_constraints(grid, self.periods, run_config, case_data, states)
        self.set_objective(grid, self.periods, run_config)

    def value(self, res_id, period, var_type, idx="0") -> float:
        """
        统一读取变量求解值。

        示例：
            uc_model.value("THERMAL001", 0, "P")
            uc_model.value("THERMAL001", 0, "CU")
            uc_model.value("STORAGE001", 0, "P", "PC")
            uc_model.value("PV鄂东", 0, "P", "curt")
        """
        p = self.to_timestamp(period)
        var = self.optmodel.getVar(res_id, p, var_type, idx)
        return float(self.optmodel.getValue(var))

    def add_variables(self, grid, periods, run_config):
        """声明所有模块决策变量"""
        setThermalVarList(self.optmodel, grid, periods)
        setHydroVarList(self.optmodel, grid, periods)
        setStorageVarList(self.optmodel, grid, periods)
        setRenewableVarList(self.optmodel, grid, periods)
        setIntertranVarList(self.optmodel, grid, periods)

        if run_config.include_load_shedding:
            setLoadSheddingVarList(self.optmodel, grid, periods)

    def add_constraints(self, grid, periods, run_config, case_data, states: dict):
        """添加各类物理规律与电网运行约束"""
        window_case_data = self._slice_case_data(case_data, periods)

        scenario_set = ScenarioSet.from_case_data(grid,window_case_data,)
        scenario_id = next(iter(scenario_set.scenarios.keys()))

        # 1. 火电约束
        if run_config.mode == "UC":
            setThermalUCCons(self.optmodel, grid, periods)
        elif run_config.mode == "ED":
            setThermalEDCons(self.optmodel, grid, periods)
        else:
            raise ValueError("simulation.mode must be UC or ED")

        # 2. 水电约束
        setHydroConstraints(self.optmodel, grid, periods)

        # 3. 储能 / 抽蓄约束
        setStorageConstraints(
            self.optmodel,
            grid,
            periods,
            initial_energy=states.get("storage_energy") or None,
        )

        # 4. 新能源约束
        setRenewableConstraints(
            self.optmodel,
            grid,
            periods,
            scenario_set,
            scenario_id,
        )

        # 5. 断面约束
        if run_config.enable_transmission:
            setIntertranCons(self.optmodel, grid, periods)

        # 6. 系统旋转备用约束
        if run_config.enable_reserve:
            setSystemReserveCons(self.optmodel, grid, periods)

        # 7. 分区功率平衡
        fixed_external_injection_mw = self._build_external_injection(case_data=window_case_data,periods=periods,)

        setPowerBalanceCons(
            self.optmodel,
            grid,
            periods,
            include_load_shedding=run_config.include_load_shedding,
            fixed_external_injection_mw=fixed_external_injection_mw,
        )

    def _build_external_injection(self, case_data, periods: pd.DatetimeIndex):
        """
        构造外来直流固定注入。

        保留 member5_0623 中外来直流处理思路：
        1. 从 metadata 中读取 dc_target_zones；
        2. 从断面表或 metadata 中读取直流容量；
        3. 按 dc_flows 时序 × 容量，得到各分区逐时外来电注入。
        """
        dc_target_zones = case_data.metadata.get("dc_target_zones") or {}

        if not dc_target_zones:
            return None

        dc_capacities = {}
        config_capacities = case_data.metadata.get("dc_capacities") or {}

        for line_name in dc_target_zones.keys():
            limit_mw = 0.0

            if hasattr(case_data, "transmissions") and not case_data.transmissions.empty:
                row = case_data.transmissions[
                    case_data.transmissions["line_name"] == line_name
                    ]
                if not row.empty:
                    limit_mw = float(row.iloc[0]["limit_mw"])

            if limit_mw == 0.0:
                limit_mw = float(config_capacities.get(line_name, 0.0))

            dc_capacities[line_name] = limit_mw

        fixed_external_injection_mw = {}

        for zone_id in self.grid.zones:
            for t in periods:
                injection = 0.0

                if case_data.dc_flows is not None and not case_data.dc_flows.empty:
                    for line_name, target_zone in dc_target_zones.items():
                        if target_zone == zone_id and line_name in case_data.dc_flows.columns:
                            limit_mw = dc_capacities.get(line_name, 1.0)
                            injection += float(case_data.dc_flows.at[t, line_name]) * limit_mw

                fixed_external_injection_mw[zone_id, t] = injection

        return fixed_external_injection_mw

    def set_objective(self, grid, periods, run_config):
        """
        设置目标函数。
        """
        setProductionObjective(
            self.optmodel,
            grid,
            periods,
            include_load_shedding=run_config.include_load_shedding,
        )

    def solve(self) -> poi.TerminationStatusCode:
        """调用底层的求解器进行优化计算"""
        self.optmodel.optimize()
        return self.model.get_model_attribute(poi.ModelAttribute.TerminationStatus)

    def _slice_case_data(self, case_data, periods: pd.DatetimeIndex):
        """
        为当前窗口生成轻量 case_data 视图。

        原始 case_data 是完整 168 小时或更长时段；
        但新能源 ScenarioSet 要求 case_data.time_index 与当前窗口 periods 完全一致。
        """

        class WindowCaseData:
            pass

        obj = WindowCaseData()

        for name, value in case_data.__dict__.items():
            setattr(obj, name, value)

        obj.time_index = periods
        obj.load_curves = case_data.load_curves.loc[periods].copy()
        obj.wind_curves = case_data.wind_curves.loc[periods].copy()
        obj.pv_curves = case_data.pv_curves.loc[periods].copy()

        if case_data.dc_flows is not None and not case_data.dc_flows.empty:
            obj.dc_flows = case_data.dc_flows.loc[periods].copy()

        metadata = dict(getattr(case_data, "metadata", {}) or {})
        metadata["start_timestamp"] = periods[0]
        metadata["end_timestamp"] = periods[-1]
        metadata["loaded_hours"] = len(periods)
        obj.metadata = metadata

        return obj
