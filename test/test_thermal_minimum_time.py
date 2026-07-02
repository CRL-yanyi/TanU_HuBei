"""验证最小开停机滑动窗口和滚动窗口初始剩余时间。"""

import pandas as pd
import pyoptinterface as poi
import pytest

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.thermal import setThermalUCCons
from src.optim.opt_model import OptModel
from src.optim.variables import setThermalVarList


def build_model(min_on=0, min_off=0, init_t=-5):
    """按给定最小持续时间和初始状态创建四时段 UC 模型。"""

    # init_t>0 表示已开机，相应初始出力设为 20 MW；停机则设为 0。
    periods = pd.date_range("2026-01-01", periods=4, freq="h")
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    grid.addResource(Thermal(
        id="G1", zoneId="Z1", type="THERMAL", Pmax=100.0,
        rampUp=100.0, rampDown=100.0, startUpCapacity=100.0,
        shutDownCapacity=100.0, minON=min_on, minOFF=min_off,
        initT=init_t, initialPower=20.0 if init_t > 0 else 0.0,
    ))
    optmodel = OptModel()
    setThermalVarList(optmodel, grid, periods)
    setThermalUCCons(optmodel, grid, periods)
    return optmodel, periods


def solve_status(optmodel, periods, objective):
    """设置测试目标、求解模型并按时间顺序返回 CU。"""

    optmodel.model.set_objective(objective, poi.ObjectiveSense.Minimize)
    optmodel.optimize()
    return [optmodel.getValue(optmodel.getVar("G1", t, "CU")) for t in periods]


def test_minimum_up_time_keeps_unit_online():
    """第一时段启动后，三小时最小开机时间内必须保持在线。"""

    # 固定首时段开机，并最小化在线时段数以触发约束边界。
    optmodel, periods = build_model(min_on=3)
    optmodel.model.add_linear_constraint(optmodel.getVar("G1", periods[0], "CU"), poi.Eq, 1)
    objective = sum(optmodel.getVar("G1", t, "CU") for t in periods)
    assert solve_status(optmodel, periods, objective)[:3] == pytest.approx([1, 1, 1])


def test_minimum_down_time_keeps_unit_offline():
    """第一时段停机后，两小时最小停机时间内不能重新启动。"""

    # 最大化在线时段数，验证模型仍不能提前开机。
    optmodel, periods = build_model(min_off=2, init_t=3)
    optmodel.model.add_linear_constraint(optmodel.getVar("G1", periods[0], "CU"), poi.Eq, 0)
    objective = -sum(optmodel.getVar("G1", t, "CU") for t in periods)
    assert solve_status(optmodel, periods, objective)[:2] == pytest.approx([0, 0])


def test_initial_residual_time_is_added():
    """窗口前已开机两小时，minON=4 时还需强制开机两小时。"""

    optmodel, periods = build_model(min_on=4, init_t=2)
    objective = sum(optmodel.getVar("G1", t, "CU") for t in periods)
    assert solve_status(optmodel, periods, objective)[:2] == pytest.approx([1, 1])
