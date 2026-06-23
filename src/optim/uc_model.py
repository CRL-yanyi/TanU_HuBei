# -*- coding: utf-8 -*-
from typing import Any, Iterable, Hashable, Dict
import pyoptinterface as poi

from src.optim.variables import (
    add_thermal_variables,
    add_hydro_variables,
    add_storage_variables,
    add_renewable_variables,
    add_transmission_variables,
    add_load_shed_variables
)
from src.optim.constraints.thermal import add_thermal_uc_constraints
from src.optim.constraints.hydro import add_hydro_constraints
from src.optim.constraints.storage import add_storage_constraints
from src.optim.constraints.renewable import add_renewable_constraints
from src.optim.constraints.transmission import add_transmission_constraints
from src.optim.constraints.power_balance import add_power_balance_constraints
from src.optim.constraints.reserve import add_system_reserve_constraints
from src.optim.objectives import set_grid_objective


class UCModel:
    """
    单个时间窗口内的 Unit Commitment (机组组合) 优化模型封装类
    """
    def __init__(self, solver_name: str, time_limit: float, mip_gap: float, log_to_console: bool = False):
        self.solver_name = solver_name
        self.time_limit = time_limit
        self.mip_gap = mip_gap
        self.log_to_console = log_to_console
        
        # 初始化 POI 模型
        if self.solver_name == "gurobi":
            from pyoptinterface import gurobi
            self.model = gurobi.Model()
        elif self.solver_name == "copt":
            from pyoptinterface import copt
            self.model = copt.Model()
        else:
            raise ValueError(f"Unsupported solver: {self.solver_name}")
            
        # 设置求解参数
        if self.solver_name == "gurobi":
            self.model.set_raw_parameter("MIPGap", float(self.mip_gap))
        elif self.solver_name == "copt":
            self.model.set_raw_parameter("MIPGap", float(self.mip_gap))
        elif self.solver_name == "cbc":
            try:
                self.model.set_raw_parameter("allowableGap", float(self.mip_gap))
            except Exception:
                pass
        self.model.set_model_attribute(poi.ModelAttribute.TimeLimitSec, float(self.time_limit))
        if not self.log_to_console:
            self.model.set_model_attribute(poi.ModelAttribute.Silent, True)

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

    def build(self, grid, periods: list[int], run_config, case_data, states: dict):
        """
        核心装配方法：定义变量 -> 拼装约束 -> 设置目标函数
        """
        # 1. 声明变量
        self.add_variables(grid, periods)
        
        # 2. 构筑物理约束
        self.add_constraints(grid, periods, run_config, case_data, states)
        
        # 3. 设置目标优化函数与惩罚费用
        self.set_objective(grid, periods, run_config)

    def add_variables(self, grid, periods: list[int]):
        """声明所有模块决策变量"""
        thermal_ids = [u.id for u in grid.getResListFromType("THERMAL")]
        hydro_ids = [u.id for u in grid.getResListFromType("HYDRO")]
        storage_ids = [u.id for u in grid.getResListFromType("STORAGE")]
        renewable_ids = [u.id for u in grid.getResListFromType("WIND") + grid.getResListFromType("PV")]
        line_ids = list(grid.intertrans.keys())
        zone_ids = list(grid.zones.keys())

        self.thermal_vars = add_thermal_variables(self.model, thermal_ids, periods)
        self.hydro_vars = add_hydro_variables(self.model, hydro_ids, periods)
        self.storage_vars = add_storage_variables(self.model, storage_ids, periods)
        self.renewable_vars = add_renewable_variables(self.model, renewable_ids, periods)
        self.trans_vars = add_transmission_variables(self.model, line_ids, periods)
        self.load_shed_vars = add_load_shed_variables(self.model, zone_ids, periods)

    def add_constraints(self, grid, periods: list[int], run_config, case_data, states: dict):
        """添加各类物理规律与电网运行约束"""
        step_hours = run_config.step_hours

        # 1. 火电约束
        if run_config.mode == "UC":
            add_thermal_uc_constraints(
                model=self.model,
                grid=grid,
                variables=self.thermal_vars,
                periods=periods,
                initial_on=states.get("thermal_on"),
                initial_power_mw=states.get("thermal_power"),
                initial_on_hours=states.get("thermal_on_hours"),
                initial_off_hours=states.get("thermal_off_hours"),
                step_hours=step_hours,
            )
        else:
            raise NotImplementedError("Economic Dispatch (ED) mode is not integrated yet.")

        # 2. 水电约束
        add_hydro_constraints(self.model, grid, self.hydro_vars, periods)

        # 3. 储电与抽蓄约束
        add_storage_constraints(
            model=self.model,
            grid=grid,
            variables=self.storage_vars,
            periods=periods,
            initial_energy=states.get("storage_energy"),
        )

        # 4. 新能源限电约束
        add_renewable_constraints(self.model, grid, self.renewable_vars, periods)

        # 5. 断面潮流输电容量约束
        if run_config.enable_transmission:
            add_transmission_constraints(self.model, grid, self.trans_vars, periods)

        # 6. 系统旋转备用约束
        if run_config.enable_reserve:
            reserve_req = {}
            for t in periods:
                total_req = 0.0
                for zone_id, zone_obj in grid.zones.items():
                    rate = getattr(zone_obj, "load_reserve_rate", run_config.default_load_reserve_rate) + \
                           getattr(zone_obj, "contingency_reserve_rate", run_config.default_contingency_reserve_rate) * \
                           getattr(zone_obj, "spinning_reserve_rate", run_config.default_spinning_reserve_rate)
                    load_res = grid.resources.get(f"LOAD{zone_id}")
                    peak_load = load_res.capacity if load_res is not None else 1.0
                    total_req += float(case_data.load_curves.at[t, zone_id]) * peak_load * rate
                reserve_req[t] = total_req
                
            add_system_reserve_constraints(self.model, grid, self.thermal_vars, periods, reserve_req)

        # 7. 分区电力供需平衡约束
        # 7.1 计算分区负荷和直流通道容量限制
        dc_target_zones = case_data.metadata.get("dc_target_zones") or {}
        dc_capacities = {}
        config_capacities = case_data.metadata.get("dc_capacities") or {}
        for line_name in dc_target_zones.keys():
            limit_mw = 0.0
            if hasattr(case_data, "transmissions") and not case_data.transmissions.empty:
                row = case_data.transmissions[case_data.transmissions['line_name'] == line_name]
                if not row.empty:
                    limit_mw = float(row.iloc[0]['limit_mw'])
            if limit_mw == 0.0:
                limit_mw = float(config_capacities.get(line_name, 0.0))
            dc_capacities[line_name] = limit_mw

        demand_mw = {}
        fixed_external_injection_mw = {}
        for zone_id in grid.zones:
            load_res = grid.resources.get(f"LOAD{zone_id}")
            peak_load = load_res.capacity if load_res is not None else 1.0
            for t in periods:
                demand_mw[zone_id, t] = float(case_data.load_curves.at[t, zone_id]) * peak_load
                
                injection = 0.0
                if not case_data.dc_flows.empty:
                    for line_name, target_zone in dc_target_zones.items():
                        if target_zone == zone_id and line_name in case_data.dc_flows.columns:
                            limit_mw = dc_capacities.get(line_name, 1.0)
                            injection += float(case_data.dc_flows.at[t, line_name]) * limit_mw
                fixed_external_injection_mw[zone_id, t] = injection

        # 7.2 构造供给和需求资源组，传递给通用平衡约束器
        supply_groups = [
            {
                "variables": self.thermal_vars.power,
                "resource_zones": {u.id: u.zoneId for u in grid.getResListFromType("THERMAL")},
            },
            {
                "variables": self.hydro_vars.power,
                "resource_zones": {u.id: u.zoneId for u in grid.getResListFromType("HYDRO")},
            },
            {
                "variables": self.renewable_vars.power,
                "resource_zones": {u.id: u.zoneId for u in grid.getResListFromType("WIND") + grid.getResListFromType("PV")},
            },
            {
                "variables": self.storage_vars.discharge_power,
                "resource_zones": {u.id: u.zoneId for u in grid.getResListFromType("STORAGE")},
            },
            {
                "variables": self.load_shed_vars.load_shed,
                "resource_zones": {zone_id: zone_id for zone_id in grid.zones},
            }
        ]
        
        demand_groups = [
            {
                "variables": self.storage_vars.charge_power,
                "resource_zones": {u.id: u.zoneId for u in grid.getResListFromType("STORAGE")},
            }
        ]

        add_power_balance_constraints(
            model=self.model,
            grid=grid,
            periods=periods,
            demand_mw=demand_mw,
            supply_groups=supply_groups,
            demand_groups=demand_groups,
            transmission_flow=self.trans_vars.flow,
            fixed_external_injection_mw=fixed_external_injection_mw,
        )

    def set_objective(self, grid, periods: list[int], run_config):
        """设置系统的优化目标函数及各项惩罚费用"""
        set_grid_objective(
            model=self.model,
            grid=grid,
            periods=periods,
            thermal_vars=self.thermal_vars,
            renewable_vars=self.renewable_vars,
            load_shed_vars=self.load_shed_vars,
            step_hours=run_config.step_hours,
            curtailment_penalty_wind=run_config.curtailment_penalty_wind,
            curtailment_penalty_pv=run_config.curtailment_penalty_pv,
            load_shed_penalty=run_config.load_shed_penalty,
        )

    def solve(self) -> poi.TerminationStatusCode:
        """调用底层的求解器进行优化计算"""
        self.model.optimize()
        return self.model.get_model_attribute(poi.ModelAttribute.TerminationStatus)
