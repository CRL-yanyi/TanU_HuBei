"""验证常规、启动和停机爬坡约束。"""

import pandas as pd
import pyoptinterface as poi
import pytest

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.thermal import setThermalUCCons
from src.optim.opt_model import OptModel
from src.optim.variables import setThermalVarList


def make_model(init_t=1, initial_power=50.0, ramp=20.0, start=40.0, stop=30.0):
    """创建可配置初始状态和三类爬坡能力的单时段模型。"""

    periods = pd.date_range("2026-01-01", periods=1, freq="h")
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    grid.addResource(Thermal(
        id="G1", zoneId="Z1", type="THERMAL", Pmax=100.0,
        rampUp=ramp, rampDown=ramp, startUpCapacity=start,
        shutDownCapacity=stop, initT=init_t, initialPower=initial_power,
    ))
    optmodel = OptModel()
    setThermalVarList(optmodel, grid, periods)
    setThermalUCCons(optmodel, grid, periods)
    return optmodel, periods[0]


def test_regular_ramp_up_and_down():
    """在线机组从 50 MW 出发，一小时只能上升或下降 20 MW。"""

    # 固定 CU=1 后最大化出力，验证上爬坡边界为 70 MW。
    optmodel, t = make_model()
    on, power = optmodel.getVar("G1", t, "CU"), optmodel.getVar("G1", t, "P")
    optmodel.model.add_linear_constraint(on, poi.Eq, 1)
    optmodel.model.set_objective(power, poi.ObjectiveSense.Maximize)
    optmodel.optimize()
    assert optmodel.getValue(power) == pytest.approx(70.0)

    optmodel.model.set_objective(power, poi.ObjectiveSense.Minimize)
    optmodel.optimize()
    assert optmodel.getValue(power) == pytest.approx(30.0)


def test_startup_capacity_limits_first_output():
    """停机机组启动后的第一时段出力不超过启动容量。"""

    # 初始停机并强制首时段开机，模型应自动令 CV=1。
    optmodel, t = make_model(init_t=-1, initial_power=0.0)
    optmodel.model.add_linear_constraint(optmodel.getVar("G1", t, "CU"), poi.Eq, 1)
    power = optmodel.getVar("G1", t, "P")
    optmodel.model.set_objective(power, poi.ObjectiveSense.Maximize)
    optmodel.optimize()
    assert optmodel.getValue(power) == pytest.approx(40.0)
    assert optmodel.getValue(optmodel.getVar("G1", t, "CV")) == pytest.approx(1.0)


def test_shutdown_capacity_limits_previous_output():
    """从允许的初始出力停机时，应得到 P=0 且 CW=1。"""

    optmodel, t = make_model(initial_power=30.0, stop=30.0)
    optmodel.model.add_linear_constraint(optmodel.getVar("G1", t, "CU"), poi.Eq, 0)
    optmodel.optimize()
    assert optmodel.getValue(optmodel.getVar("G1", t, "P")) == pytest.approx(0.0)
    assert optmodel.getValue(optmodel.getVar("G1", t, "CW")) == pytest.approx(1.0)
    # 改为最小化出力，验证下爬坡边界为 30 MW。
