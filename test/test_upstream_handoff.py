# -*- coding: utf-8 -*-
"""成员一至四向年度运行层交接前的功能闭环测试。"""

from __future__ import annotations

import datetime as dt
import unittest
from pathlib import Path

import pandas as pd
import pyoptinterface as poi

from src.data.config import TimeConfig
from src.data.grid_builder import build_grid
from src.data.loader import load_case, validate_case_data
from src.model.grid import Grid
from src.model.resource import Load, Wind
from src.model.zone import Zone
from src.optim.constraints.hydro import setHydroConstraints
from src.optim.constraints.power_balance import setPowerBalanceCons
from src.optim.constraints.renewable import setRenewableConstraints
from src.optim.constraints.storage import setStorageConstraints
from src.optim.constraints.thermal import setThermalUCCons
from src.optim.constraints.transmission import setIntertranCons
from src.optim.objectives import setProductionObjective
from src.optim.opt_model import OptModel
from src.optim.variables import (
    setHydroVarList,
    setIntertranVarList,
    setLoadSheddingVarList,
    setRenewableVarList,
    setStorageVarList,
    setThermalVarList,
)
from src.scenario import Scenario, ScenarioSet


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DataAndGridHandoffTests(unittest.TestCase):
    """验证真实湖北数据能够形成成员五可直接消费的规范对象。"""

    def test_time_config_preserves_absolute_hour_position(self) -> None:
        config = TimeConfig(start_hour=24, end_hour=47)
        self.assertEqual(config.time_index[0], pd.Timestamp("2030-01-02"))
        self.assertEqual(config.time_index[-1], pd.Timestamp("2030-01-02 23:00"))

    def test_real_24_hour_case_and_grid_are_complete(self) -> None:
        case_data = load_case(
            str(PROJECT_ROOT / "configs" / "cases" / "hubei2030.yaml"),
            TimeConfig(0, 23),
            scenario=0,
        )
        report = validate_case_data(case_data)
        self.assertTrue(report.is_valid, report.errors)
        self.assertIsInstance(case_data.time_index, pd.DatetimeIndex)

        grid = build_grid(case_data)
        for load in grid.getResListFromType("LOAD"):
            self.assertEqual(len(load.TSCapacity), 24)
            self.assertTrue(load.isPU)
        for resource in (
            grid.getResListFromType("WIND")
            + grid.getResListFromType("PV")
        ):
            self.assertEqual(len(resource.TSCapacity), 24)
            self.assertEqual(len(resource.monthly_capacity_mw), 12)
        for zone in grid.zones.values():
            for basin in zone.basinDict.values():
                if basin.hydroDict:
                    self.assertTrue(basin.predicted)
                    self.assertTrue(basin.forced)
                    self.assertTrue(basin.average)

        scenarios = ScenarioSet.from_case_data(grid, case_data)
        scenario = scenarios.require_single_scenario("BASE")
        self.assertTrue(scenario.time_index.equals(case_data.time_index))
        self.assertEqual(
            set(scenario.data.columns),
            {
                resource.id
                for resource in (
                    grid.getResListFromType("WIND")
                    + grid.getResListFromType("PV")
                )
            },
        )

    def test_data_validation_rejects_missing_capacity_and_conflicting_flow(
        self,
    ) -> None:
        config_path = str(
            PROJECT_ROOT / "configs" / "cases" / "hubei2030.yaml"
        )
        missing_capacity = load_case(config_path, TimeConfig(0, 23))
        missing_capacity.wind_spec = pd.DataFrame()
        report = validate_case_data(missing_capacity)
        self.assertFalse(report.is_valid)
        self.assertTrue(
            any("wind_spec" in error for error in report.errors),
            report.errors,
        )

        conflicting_flow = load_case(config_path, TimeConfig(0, 23))
        basin_name = next(iter(conflicting_flow.hydro_flows))
        flow = conflicting_flow.hydro_flows[basin_name]
        month = flow.columns[0]
        flow.at["强迫", month] = 0.9
        flow.at["平均", month] = 0.5
        flow.at["预想", month] = 0.7
        report = validate_case_data(conflicting_flow)
        self.assertFalse(report.is_valid)
        self.assertTrue(
            any("顺序冲突" in error for error in report.errors),
            report.errors,
        )

    def test_real_24_hour_upstream_model_constructs(self) -> None:
        case_data = load_case(
            str(PROJECT_ROOT / "configs" / "cases" / "hubei2030.yaml"),
            TimeConfig(0, 23),
            scenario=0,
        )
        grid = build_grid(case_data)
        time_idx = case_data.time_index
        scenarios = ScenarioSet.from_case_data(grid, case_data)
        optmodel = OptModel(solver="GUROBI")

        setThermalVarList(optmodel, grid, time_idx)
        setHydroVarList(optmodel, grid, time_idx)
        setStorageVarList(optmodel, grid, time_idx)
        setRenewableVarList(optmodel, grid, time_idx)
        setIntertranVarList(optmodel, grid, time_idx)
        setLoadSheddingVarList(optmodel, grid, time_idx)

        setThermalUCCons(optmodel, grid, time_idx)
        setHydroConstraints(optmodel, grid, time_idx)
        setStorageConstraints(optmodel, grid, time_idx)
        setRenewableConstraints(
            optmodel,
            grid,
            time_idx,
            scenarios,
            "BASE",
        )
        setIntertranCons(optmodel, grid, time_idx)
        setPowerBalanceCons(
            optmodel,
            grid,
            time_idx,
            include_load_shedding=True,
        )
        setProductionObjective(
            optmodel,
            grid,
            time_idx,
            include_load_shedding=True,
        )

        self.assertGreater(len(optmodel.vars), 0)
        self.assertGreater(len(optmodel.cons), 0)


class SystemInterfaceHandoffTests(unittest.TestCase):
    """验证失负荷、外来电、弃电和完整目标函数能够共同求解。"""

    def test_external_injection_load_shedding_and_curtailment_cost(self) -> None:
        time_idx = pd.date_range("2030-01-01", periods=1, freq="h")
        grid = Grid(id="SYSTEM_HANDOFF")
        grid.addZone(Zone(id="Z1"))
        load = Load(
            id="L1",
            zoneId="Z1",
            type="LOAD",
            capacity=100.0,
            isPU=False,
            curtailmentPenalty=100000.0,
        )
        load.TSCapacity = {time_idx[0]: 100.0}
        grid.addResource(load)
        wind = Wind(
            id="W1",
            zoneId="Z1",
            type="WIND",
            curtailmentPenalty=500.0,
        )
        wind.monthly_capacity_mw = {dt.date(2030, 1, 1): 100.0}
        grid.addResource(wind)
        scenarios = ScenarioSet()
        scenarios.add_scenario(
            Scenario(
                id="BASE",
                probability=1.0,
                data=pd.DataFrame({"W1": [0.5]}, index=time_idx),
            )
        )

        optmodel = OptModel(solver="GUROBI")
        setRenewableVarList(optmodel, grid, time_idx)
        setLoadSheddingVarList(optmodel, grid, time_idx)
        setRenewableConstraints(
            optmodel, grid, time_idx, scenarios, "BASE"
        )
        optmodel.addCons(
            ("W1", time_idx[0], "TEST", "fixed"),
            optmodel.getVar("W1", time_idx[0], "P"),
            poi.Eq,
            0.0,
        )
        setPowerBalanceCons(
            optmodel,
            grid,
            time_idx,
            include_load_shedding=True,
            fixed_external_injection_mw={("Z1", time_idx[0]): 20.0},
        )
        setProductionObjective(
            optmodel,
            grid,
            time_idx,
            include_load_shedding=True,
        )
        optmodel.optimize()

        status = optmodel.getModelAttribute(
            poi.ModelAttribute.TerminationStatus
        )
        self.assertEqual(status, poi.TerminationStatusCode.OPTIMAL)
        self.assertAlmostEqual(
            optmodel.getValue(optmodel.getVar("L1", time_idx[0], "P", "shed")),
            80.0,
            delta=1e-6,
        )
        self.assertAlmostEqual(
            optmodel.getValue(
                optmodel.getVar("W1", time_idx[0], "P", "curt")
            ),
            50.0,
            delta=1e-6,
        )
        self.assertAlmostEqual(
            optmodel.getModelAttribute(poi.ModelAttribute.ObjectiveValue),
            8_025_000.0,
            delta=1e-6,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
