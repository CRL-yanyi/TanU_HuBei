"""成员3固定开停机状态 ED 全链路集成测试。"""

import pandas as pd
import pyoptinterface as poi
import pytest

from src.model.grid import Grid
from src.model.resource import Load, Reserve, Thermal
from src.model.zone import Zone
from src.optim.constraints.power_balance import setPowerBalanceCons
from src.optim.constraints.reserve import setSystemReserveCons
from src.optim.constraints.thermal import setThermalEDCons
from src.optim.objectives import setThermalObjective
from src.optim.opt_model import OptModel
from src.optim.variables import setThermalVarList


def test_fixed_status_economic_dispatch():
    """给定两台机组 ONOFF 后，应得到成本最小的逐时出力。"""

    # 两小时窗口内 G1 始终在线，G2 只在第二小时在线。
    periods = pd.date_range("2026-01-01", periods=2, freq="h")
    grid = Grid(id="TEST"); grid.addZone(Zone(id="Z1"))
    grid.addResource(Thermal(
        id="G1", zoneId="Z1", type="THERMAL", Pmin=20, Pmax=100,
        rampUp=50, rampDown=50, initT=1, initialPower=50,
        startUpCost=500, shutDownCost=50, startUpCapacity=100,
        shutDownCapacity=100, variableCost=100, ONOFF={periods[0]: 1, periods[1]: 1},
    ))
    grid.addResource(Thermal(
        id="G2", zoneId="Z1", type="THERMAL", Pmin=10, Pmax=80,
        rampUp=40, rampDown=40, initT=-1, initialPower=0,
        startUpCost=1000, shutDownCost=100, startUpCapacity=80,
        shutDownCapacity=80, variableCost=200, ONOFF={periods[0]: 0, periods[1]: 1},
    ))
    # 固定负荷和备用需求均放入 Grid 资源对象。
    grid.addResource(Load(id="D1", zoneId="Z1", type="LOAD",
                          TSCapacity=dict(zip(periods, [80, 130]))))
    grid.addResource(Reserve(id="R1", zoneId="Z1", type="RESERVE",
                             TSCapacity={t: 20 for t in periods}))

    # ED 入口固定状态，系统模块随后建立平衡和备用约束。
    optmodel = OptModel()
    setThermalVarList(optmodel, grid, periods)
    setThermalEDCons(optmodel, grid, periods)
    setPowerBalanceCons(optmodel, grid, periods)
    setSystemReserveCons(optmodel, grid, periods)
    setThermalObjective(optmodel, grid, periods)
    optmodel.optimize()

    # 验证求解状态、逐机出力、G2 启动动作和总成本。
    assert optmodel.getModelAttribute(poi.ModelAttribute.TerminationStatus) == poi.TerminationStatusCode.OPTIMAL
    expected = {
        ("G1", periods[0]): 80, ("G1", periods[1]): 100,
        ("G2", periods[0]): 0, ("G2", periods[1]): 30,
    }
    for (unit, period), value in expected.items():
        assert optmodel.getValue(optmodel.getVar(unit, period, "P")) == pytest.approx(value)
    assert optmodel.getValue(optmodel.getVar("G2", periods[1], "CV")) == pytest.approx(1)
    assert optmodel.getModelAttribute(poi.ModelAttribute.ObjectiveValue) == pytest.approx(25000)
