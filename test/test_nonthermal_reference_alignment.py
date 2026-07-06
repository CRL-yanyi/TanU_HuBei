# -*- coding: utf-8 -*-
"""非火电资源参考公式、边界条件和功率平衡接口联调测试。

该文件仅使用 unittest，可直接在 pytorch_newest 环境运行。测试分为四层：
场景接口契约、水电 2.3、储能 2.4、新能源 2.5，以及与分区功率平衡的联调。
数值断言统一采用 ``1e-6`` 容差。
"""

from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pyoptinterface as poi

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.model.grid import Grid
from src.model.intertran import Intertran
from src.model.resource import Hydro, Load, PV, Storage, Wind
from src.model.zone import Basin, Zone
from src.optim.constraints.hydro import setHydroConstraints
from src.optim.constraints.power_balance import setPowerBalanceCons
from src.optim.constraints.renewable import setRenewableConstraints
from src.optim.constraints.storage import setStorageConstraints
from src.optim.opt_model import OptModel
from src.optim.variables import (
    setHydroVarList,
    setIntertranVarList,
    setRenewableVarList,
    setStorageVarList,
)
from src.scenario import Scenario, ScenarioSet


TOLERANCE = 1e-6


def _assert_optimal(test_case: unittest.TestCase, optmodel: OptModel) -> None:
    """断言求解器以最优状态结束，而不只检查是否产生了变量值。"""
    status = optmodel.getModelAttribute(poi.ModelAttribute.TerminationStatus)
    test_case.assertEqual(status, poi.TerminationStatusCode.OPTIMAL)


def _single_zone_grid() -> Grid:
    """构造不依赖真实湖北数据的最小单分区 Grid。"""
    grid = Grid(id="NONTHERMAL_TEST")
    grid.addZone(Zone(id="Z1"))
    return grid


def _scenario_set(
    scenario_id: str,
    time_idx: pd.DatetimeIndex,
    values: dict[str, list[float]],
) -> ScenarioSet:
    """把按资源组织的固定数值表包装成概率为 1 的单场景。"""
    scenarios = ScenarioSet()
    scenarios.add_scenario(
        Scenario(
            id=scenario_id,
            probability=1.0,
            data=pd.DataFrame(values, index=time_idx),
        )
    )
    return scenarios


class ScenarioContractTests(unittest.TestCase):
    """验证单场景数据结构的正常查询和错误边界。"""

    def test_single_scenario_contract(self) -> None:
        time_idx = pd.date_range("2030-01-01", periods=2, freq="h")
        scenarios = _scenario_set("BASE", time_idx, {"W1": [0.2, 0.3]})
        self.assertAlmostEqual(
            scenarios.get_value("BASE", "W1", time_idx[1]), 0.3
        )
        self.assertAlmostEqual(scenarios.get_probability("BASE"), 1.0)
        self.assertTrue(scenarios.get_time_index("BASE").equals(time_idx))

    def test_scenario_rejects_missing_resource(self) -> None:
        time_idx = pd.date_range("2030-01-01", periods=1, freq="h")
        scenarios = _scenario_set("BASE", time_idx, {"W1": [0.2]})
        with self.assertRaisesRegex(ValueError, "missing resource 'PV1'"):
            scenarios.get_value("BASE", "PV1", time_idx[0])

    def test_current_model_rejects_multiple_scenarios(self) -> None:
        time_idx = pd.date_range("2030-01-01", periods=1, freq="h")
        scenarios = ScenarioSet()
        scenarios.add_scenario(
            Scenario("S1", 0.5, pd.DataFrame({"W1": [0.2]}, index=time_idx))
        )
        scenarios.add_scenario(
            Scenario("S2", 0.5, pd.DataFrame({"W1": [0.3]}, index=time_idx))
        )
        with self.assertRaisesRegex(ValueError, "exactly one scenario"):
            scenarios.require_single_scenario("S1")

    def test_case_data_factory_maps_zone_curves_to_resource_ids(self) -> None:
        grid = Grid(id="SCENARIO_FACTORY")
        grid.addZone(Zone(id="Z1"))
        grid.addZone(Zone(id="Z2"))
        grid.addResource(Wind(id="W1", zoneId="Z1", type="WIND"))
        grid.addResource(PV(id="PV2", zoneId="Z2", type="PV"))
        time_idx = pd.date_range("2030-01-01", periods=2, freq="h")
        case_data = SimpleNamespace(
            time_index=time_idx,
            wind_curves=pd.DataFrame(
                {"Z1": [0.2, 0.3], "Z2": [0.4, 0.5]},
                index=time_idx,
            ),
            pv_curves=pd.DataFrame(
                {"Z1": [0.0, 0.1], "Z2": [0.6, 0.7]},
                index=time_idx,
            ),
            metadata={"scenario": 0},
        )
        scenarios = ScenarioSet.from_case_data(grid, case_data)
        self.assertAlmostEqual(
            scenarios.get_value("BASE", "W1", time_idx[1]), 0.3
        )
        self.assertAlmostEqual(
            scenarios.get_value("BASE", "PV2", time_idx[0]), 0.6
        )


class HydroReferenceTests(unittest.TestCase):
    """逐项验证参考公式 2.3.1—2.3.3 及月度数据缺失报错。"""

    def test_231_to_233_cross_month(self) -> None:
        # 两个连续时段横跨 1 月和 2 月，用于确认月度参数能正确换月。
        grid = _single_zone_grid()
        basin = Basin(
            id="BASIN_B1",
            zoneId="Z1",
            predicted={
                dt.date(2030, 1, 1): 0.8,
                dt.date(2030, 2, 1): 0.7,
            },
            forced={
                dt.date(2030, 1, 1): 0.2,
                dt.date(2030, 2, 1): 0.3,
            },
            average={
                dt.date(2030, 1, 1): 0.5,
                dt.date(2030, 2, 1): 0.6,
            },
        )
        grid.addBasin(basin)
        grid.addResource(
            Hydro(
                id="H1",
                zoneId="Z1",
                type="HYDRO",
                capacity=100.0,
                Pmax=100.0,
                Pmin=20.0,
                basinId="BASIN_B1",
            )
        )
        time_idx = pd.date_range("2030-01-31 23:00", periods=2, freq="h")
        optmodel = OptModel(solver="GUROBI")
        setHydroVarList(optmodel, grid, time_idx)
        setHydroConstraints(optmodel, grid, time_idx)
        optmodel.setObjective()
        optmodel.optimize()
        _assert_optimal(self, optmodel)

        # 月平均约束分别固定为 50 MW 和 60 MW；Pmin=20 不作为硬约束。
        self.assertAlmostEqual(
            optmodel.getValue(optmodel.getVar("H1", time_idx[0], "P")),
            50.0,
            delta=TOLERANCE,
        )
        self.assertAlmostEqual(
            optmodel.getValue(optmodel.getVar("H1", time_idx[1], "P")),
            60.0,
            delta=TOLERANCE,
        )

    def test_hydro_reference_data_is_required(self) -> None:
        grid = _single_zone_grid()
        grid.addBasin(Basin(id="BASIN_B1", zoneId="Z1"))
        grid.addResource(
            Hydro(
                id="H1",
                zoneId="Z1",
                type="HYDRO",
                capacity=100.0,
                Pmax=100.0,
                basinId="BASIN_B1",
            )
        )
        time_idx = pd.date_range("2030-01-01", periods=1, freq="h")
        optmodel = OptModel(solver="GUROBI")
        setHydroVarList(optmodel, grid, time_idx)
        with self.assertRaisesRegex(ValueError, "missing field 'predicted'"):
            setHydroConstraints(optmodel, grid, time_idx)

    def test_conflicting_hydro_process_is_rejected(self) -> None:
        grid = _single_zone_grid()
        grid.addBasin(
            Basin(
                id="BASIN_B1",
                zoneId="Z1",
                predicted={dt.date(2030, 1, 1): 0.7},
                forced={dt.date(2030, 1, 1): 0.6},
                average={dt.date(2030, 1, 1): 0.5},
            )
        )
        grid.addResource(
            Hydro(
                id="H1",
                zoneId="Z1",
                type="HYDRO",
                capacity=100.0,
                Pmax=100.0,
                basinId="BASIN_B1",
            )
        )
        time_idx = pd.date_range("2030-01-01", periods=1, freq="h")
        optmodel = OptModel(solver="GUROBI")
        setHydroVarList(optmodel, grid, time_idx)
        with self.assertRaisesRegex(ValueError, "forced <= average"):
            setHydroConstraints(optmodel, grid, time_idx)

    def test_rolling_month_energy_uses_prior_state(self) -> None:
        grid = _single_zone_grid()
        grid.addBasin(
            Basin(
                id="BASIN_B1",
                zoneId="Z1",
                predicted={dt.date(2030, 1, 1): 1.0},
                forced={dt.date(2030, 1, 1): 0.0},
                average={dt.date(2030, 1, 1): 0.5},
            )
        )
        grid.addResource(
            Hydro(
                id="H1",
                zoneId="Z1",
                type="HYDRO",
                capacity=100.0,
                Pmax=100.0,
                basinId="BASIN_B1",
            )
        )
        time_idx = pd.date_range("2030-01-31 23:00", periods=1, freq="h")
        optmodel = OptModel(solver="GUROBI")
        setHydroVarList(optmodel, grid, time_idx)
        setHydroConstraints(
            optmodel,
            grid,
            time_idx,
            prior_month_energy_mwh={
                ("Z1:BASIN_B1", 2030, 1): 37150.0
            },
            closed_months={(2030, 1)},
        )
        optmodel.optimize()
        _assert_optimal(self, optmodel)
        self.assertAlmostEqual(
            optmodel.getValue(optmodel.getVar("H1", time_idx[0], "P")),
            50.0,
            delta=TOLERANCE,
        )


class StorageReferenceTests(unittest.TestCase):
    """验证储能 2.4.1—2.4.6、效率、时间步长和充放电互斥。"""

    def _solve_two_period_cycle(
        self,
        efficiency: float,
        time_idx: pd.DatetimeIndex,
    ) -> tuple[float, float, float]:
        """求解两时段“先放后充”循环，返回放电、充电和末端能量。"""
        grid = _single_zone_grid()
        grid.addResource(
            Storage(
                id="S1",
                zoneId="Z1",
                type="STORAGE",
                capacity=50.0,
                Pmax=50.0,
                Emax=100.0,
                Emin=0.0,
                E0=50.0,
                EnT=50.0,
                effC=efficiency,
                effD=efficiency,
            )
        )
        optmodel = OptModel(solver="GUROBI")
        setStorageVarList(optmodel, grid, time_idx)
        setStorageConstraints(optmodel, grid, time_idx)
        discharge_first = optmodel.getVar("S1", time_idx[0], "P", "PD")
        optmodel.model.set_objective(
            discharge_first, poi.ObjectiveSense.Maximize
        )
        optmodel.optimize()
        _assert_optimal(self, optmodel)
        return (
            optmodel.getValue(discharge_first),
            optmodel.getValue(optmodel.getVar("S1", time_idx[1], "P", "PC")),
            optmodel.getValue(optmodel.getVar("S1", time_idx[1], "E")),
        )

    def test_241_to_246_efficiency_matrix(self) -> None:
        # 手算关系：第二时段以 50 MW 充电并回到 E=50 MWh 时，
        # 第一时段最大放电量为 50 × effC × effD。
        time_idx = pd.date_range("2030-01-01", periods=2, freq="h")
        for efficiency in (0.8, 0.9, 1.0):
            with self.subTest(efficiency=efficiency):
                discharge, charge, terminal_energy = (
                    self._solve_two_period_cycle(efficiency, time_idx)
                )
                self.assertAlmostEqual(
                    discharge,
                    50.0 * efficiency * efficiency,
                    delta=TOLERANCE,
                )
                self.assertAlmostEqual(charge, 50.0, delta=TOLERANCE)
                self.assertAlmostEqual(
                    terminal_energy, 50.0, delta=TOLERANCE
                )

    def test_15_minute_soc_scaling(self) -> None:
        grid = _single_zone_grid()
        grid.addResource(
            Storage(
                id="S1",
                zoneId="Z1",
                type="STORAGE",
                capacity=50.0,
                Pmax=50.0,
                Emax=100.0,
                Emin=0.0,
                E0=50.0,
                EnT=50.0,
                effC=0.9,
                effD=0.9,
            )
        )
        time_idx = pd.date_range("2030-01-01", periods=2, freq="15min")
        optmodel = OptModel(solver="GUROBI")
        setStorageVarList(optmodel, grid, time_idx)
        setStorageConstraints(optmodel, grid, time_idx)
        optmodel.addCons(
            ("S1", time_idx[0], "TEST_PC", "fixed"),
            optmodel.getVar("S1", time_idx[0], "P", "PC"),
            poi.Eq,
            10.0,
        )
        optmodel.setObjective()
        optmodel.optimize()
        _assert_optimal(self, optmodel)
        self.assertAlmostEqual(
            optmodel.getValue(optmodel.getVar("S1", time_idx[0], "E")),
            52.25,
            delta=TOLERANCE,
        )
        self.assertAlmostEqual(
            optmodel.getValue(optmodel.getVar("S1", time_idx[1], "P", "PD")),
            8.1,
            delta=TOLERANCE,
        )

    def test_charge_and_discharge_are_mutually_exclusive(self) -> None:
        grid = _single_zone_grid()
        grid.addResource(
            Storage(
                id="S1",
                zoneId="Z1",
                type="STORAGE",
                Pmax=50.0,
                Emax=100.0,
                E0=50.0,
                EnT=50.0,
                effC=0.9,
                effD=0.9,
            )
        )
        time_idx = pd.date_range("2030-01-01", periods=1, freq="h")
        optmodel = OptModel(solver="GUROBI")
        setStorageVarList(optmodel, grid, time_idx)
        setStorageConstraints(optmodel, grid, time_idx)
        optmodel.addCons(
            ("S1", time_idx[0], "TEST_PC", "fixed"),
            optmodel.getVar("S1", time_idx[0], "P", "PC"),
            poi.Geq,
            10.0,
        )
        optmodel.addCons(
            ("S1", time_idx[0], "TEST_PD", "fixed"),
            optmodel.getVar("S1", time_idx[0], "P", "PD"),
            poi.Geq,
            10.0,
        )
        optmodel.optimize()
        status = optmodel.getModelAttribute(poi.ModelAttribute.TerminationStatus)
        self.assertIn(
            status,
            (
                poi.TerminationStatusCode.INFEASIBLE,
                poi.TerminationStatusCode.INFEASIBLE_OR_UNBOUNDED,
            ),
        )

    def test_rolling_initial_energy_override_does_not_mutate_grid(self) -> None:
        grid = _single_zone_grid()
        storage = Storage(
            id="S1",
            zoneId="Z1",
            type="STORAGE",
            capacity=50.0,
            Pmax=50.0,
            Emax=100.0,
            Emin=0.0,
            E0=50.0,
            EnT=60.0,
            effC=1.0,
            effD=1.0,
        )
        grid.addResource(storage)
        time_idx = pd.date_range("2030-01-01", periods=2, freq="h")
        optmodel = OptModel(solver="GUROBI")
        setStorageVarList(optmodel, grid, time_idx)
        setStorageConstraints(
            optmodel,
            grid,
            time_idx,
            initial_energy={"S1": 60.0},
        )
        flow = sum(
            optmodel.getVar("S1", period, "P", "PC")
            + optmodel.getVar("S1", period, "P", "PD")
            for period in time_idx
        )
        optmodel.model.set_objective(flow, poi.ObjectiveSense.Minimize)
        optmodel.optimize()
        _assert_optimal(self, optmodel)
        self.assertAlmostEqual(optmodel.getValue(flow), 0.0, delta=TOLERANCE)
        self.assertEqual(storage.E0, 50.0)


class RenewableReferenceTests(unittest.TestCase):
    """验证新能源可用功率守恒、月装机换月、爬坡缩放和缺参报错。"""

    def test_251_monthly_capacity_and_curtailment(self) -> None:
        # 1 月可用功率为 100×0.5=50 MW，固定出力 20 后弃电应为 30 MW；
        # 2 月换为 200×0.25=50 MW，最小弃电目标会使实际出力达到 50 MW。
        grid = _single_zone_grid()
        wind = Wind(id="W1", zoneId="Z1", type="WIND")
        wind.monthly_capacity_mw = {
            dt.date(2030, 1, 1): 100.0,
            dt.date(2030, 2, 1): 200.0,
        }
        grid.addResource(wind)
        time_idx = pd.date_range("2030-01-31 23:00", periods=2, freq="h")
        scenarios = _scenario_set("BASE", time_idx, {"W1": [0.5, 0.25]})

        optmodel = OptModel(solver="GUROBI")
        setRenewableVarList(optmodel, grid, time_idx)
        setRenewableConstraints(
            optmodel, grid, time_idx, scenarios, "BASE"
        )
        optmodel.addCons(
            ("W1", time_idx[0], "TEST_P", "fixed"),
            optmodel.getVar("W1", time_idx[0], "P"),
            poi.Eq,
            20.0,
        )
        curtailment = sum(
            optmodel.getVar("W1", period, "P", "curt")
            for period in time_idx
        )
        optmodel.model.set_objective(
            curtailment, poi.ObjectiveSense.Minimize
        )
        optmodel.optimize()
        _assert_optimal(self, optmodel)
        self.assertAlmostEqual(
            optmodel.getValue(
                optmodel.getVar("W1", time_idx[0], "P", "curt")
            ),
            30.0,
            delta=TOLERANCE,
        )
        self.assertAlmostEqual(
            optmodel.getValue(optmodel.getVar("W1", time_idx[1], "P")),
            50.0,
            delta=TOLERANCE,
        )

    def test_252_253_ramp_uses_time_step(self) -> None:
        # rampUp=20 MW/h，在 15 分钟步长下每段最多增加 5 MW。
        grid = _single_zone_grid()
        wind = Wind(
            id="W1",
            zoneId="Z1",
            type="WIND",
            rampUp=20.0,
            rampDown=20.0,
        )
        wind.monthly_capacity_mw = {dt.date(2030, 1, 1): 100.0}
        grid.addResource(wind)
        time_idx = pd.date_range("2030-01-01", periods=3, freq="15min")
        scenarios = _scenario_set("BASE", time_idx, {"W1": [1.0, 1.0, 1.0]})
        optmodel = OptModel(solver="GUROBI")
        setRenewableVarList(optmodel, grid, time_idx)
        setRenewableConstraints(
            optmodel, grid, time_idx, scenarios, "BASE"
        )
        optmodel.addCons(
            ("W1", time_idx[0], "TEST_P", "fixed"),
            optmodel.getVar("W1", time_idx[0], "P"),
            poi.Eq,
            30.0,
        )
        generation = sum(
            optmodel.getVar("W1", period, "P") for period in time_idx
        )
        optmodel.model.set_objective(
            generation, poi.ObjectiveSense.Maximize
        )
        optmodel.optimize()
        _assert_optimal(self, optmodel)
        expected = (30.0, 35.0, 40.0)
        actual = tuple(
            optmodel.getValue(optmodel.getVar("W1", period, "P"))
            for period in time_idx
        )
        for value, target in zip(actual, expected):
            self.assertAlmostEqual(value, target, delta=TOLERANCE)

    def test_monthly_capacity_is_required(self) -> None:
        grid = _single_zone_grid()
        grid.addResource(Wind(id="W1", zoneId="Z1", type="WIND"))
        time_idx = pd.date_range("2030-01-01", periods=1, freq="h")
        scenarios = _scenario_set("BASE", time_idx, {"W1": [0.5]})
        optmodel = OptModel(solver="GUROBI")
        setRenewableVarList(optmodel, grid, time_idx)
        with self.assertRaisesRegex(ValueError, "monthly_capacity_mw"):
            setRenewableConstraints(
                optmodel, grid, time_idx, scenarios, "BASE"
            )


def _solve_power_balance_integration_case() -> tuple[float, tuple[float, ...]]:
    """求解两分区联调模型并返回最大平衡残差和联络线潮流。

    Z1 包含水电、储能和 40 MW 负荷，Z2 包含风光和 40 MW 负荷，两区通过
    一条可双向联络线连接。函数直接调用现有功率平衡约束，验证非火电变量键
    能被 OptModel 和分区平衡正确读取。
    """
    grid = Grid(id="POWER_BALANCE_INTEGRATION")
    grid.addZone(Zone(id="Z1"))
    grid.addZone(Zone(id="Z2"))
    grid.addBasin(
        Basin(
            id="BASIN_B1",
            zoneId="Z1",
            predicted={dt.date(2030, 1, 1): 1.0},
            forced={dt.date(2030, 1, 1): 0.0},
            average={dt.date(2030, 1, 1): 0.5},
        )
    )
    grid.addResource(
        Hydro(
            id="H1",
            zoneId="Z1",
            type="HYDRO",
            capacity=100.0,
            Pmax=100.0,
            basinId="BASIN_B1",
        )
    )
    grid.addResource(
        Storage(
            id="S1",
            zoneId="Z1",
            type="STORAGE",
            Pmax=0.0,
            Emax=0.0,
            E0=0.0,
            EnT=0.0,
            effC=1.0,
            effD=1.0,
        )
    )
    wind = Wind(id="W1", zoneId="Z2", type="WIND")
    wind.monthly_capacity_mw = {dt.date(2030, 1, 1): 100.0}
    grid.addResource(wind)
    pv = PV(id="PV1", zoneId="Z2", type="PV")
    pv.monthly_capacity_mw = {dt.date(2030, 1, 1): 50.0}
    grid.addResource(pv)
    time_idx = pd.date_range("2030-01-01", periods=2, freq="h")
    for zone_id in ("Z1", "Z2"):
        load = Load(
            id=f"LOAD{zone_id}",
            zoneId=zone_id,
            type="LOAD",
            capacity=40.0,
            Pmax=40.0,
        )
        load.TSCapacity = {period: 40.0 for period in time_idx}
        grid.addResource(load)
    grid.addIntertran(
        Intertran(
            id="L12",
            fromZone="Z1",
            toZone="Z2",
            type="AC",
            capacityToZone=100.0,
            capacityFromZone=100.0,
        )
    )
    scenarios = _scenario_set(
        "BASE",
        time_idx,
        {"W1": [0.2, 0.2], "PV1": [0.2, 0.2]},
    )

    optmodel = OptModel(solver="GUROBI")
    setHydroVarList(optmodel, grid, time_idx)
    setStorageVarList(optmodel, grid, time_idx)
    setRenewableVarList(optmodel, grid, time_idx)
    setIntertranVarList(optmodel, grid, time_idx)
    setHydroConstraints(optmodel, grid, time_idx)
    setStorageConstraints(optmodel, grid, time_idx)
    setRenewableConstraints(optmodel, grid, time_idx, scenarios, "BASE")
    setPowerBalanceCons(optmodel, grid, time_idx)
    curtailment = sum(
        optmodel.getVar(resource_id, period, "P", "curt")
        for resource_id in ("W1", "PV1")
        for period in time_idx
    )
    optmodel.model.set_objective(curtailment, poi.ObjectiveSense.Minimize)
    optmodel.optimize()
    status = optmodel.getModelAttribute(poi.ModelAttribute.TerminationStatus)
    if status != poi.TerminationStatusCode.OPTIMAL:
        raise AssertionError(f"integration model status is {status}")

    flows = tuple(
        optmodel.getValue(optmodel.getVar("INTERTRANL12", period, "P"))
        for period in time_idx
    )
    max_residual = 0.0
    for period in time_idx:
        hydro_power = optmodel.getValue(optmodel.getVar("H1", period, "P"))
        line_flow = optmodel.getValue(
            optmodel.getVar("INTERTRANL12", period, "P")
        )
        wind_power = optmodel.getValue(optmodel.getVar("W1", period, "P"))
        pv_power = optmodel.getValue(optmodel.getVar("PV1", period, "P"))
        residual_z1 = hydro_power - 40.0 - line_flow
        residual_z2 = wind_power + pv_power - 40.0 + line_flow
        max_residual = max(
            max_residual, abs(residual_z1), abs(residual_z2)
        )
    return max_residual, flows


class PowerBalanceIntegrationTests(unittest.TestCase):
    """验证非火电变量与分区功率平衡联调及重复求解确定性。"""

    def test_nonthermal_variables_work_with_power_balance(self) -> None:
        max_residual, flows = _solve_power_balance_integration_case()
        self.assertLessEqual(max_residual, TOLERANCE)
        for flow in flows:
            self.assertAlmostEqual(flow, 10.0, delta=TOLERANCE)

    def test_integration_result_is_deterministic(self) -> None:
        first = _solve_power_balance_integration_case()
        second = _solve_power_balance_integration_case()
        self.assertAlmostEqual(first[0], second[0], delta=TOLERANCE)
        for left, right in zip(first[1], second[1]):
            self.assertAlmostEqual(left, right, delta=TOLERANCE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
