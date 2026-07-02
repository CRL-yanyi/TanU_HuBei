"""成员3 UC 全链路集成测试。"""

import pandas as pd
import pyoptinterface as poi
import pytest

from src.model.grid import Grid
from src.model.resource import Load, Reserve, Thermal
from src.model.zone import Zone
from src.optim.constraints.power_balance import setPowerBalanceCons
from src.optim.constraints.reserve import setSystemReserveCons
from src.optim.constraints.thermal import setThermalUCCons
from src.optim.objectives import setThermalObjective
from src.optim.opt_model import OptModel
from src.optim.variables import setThermalVarList


def test_two_unit_three_period_uc():
    """两台不同成本机组应完成三时段经济机组组合。"""

    # 建立三小时调度窗口和单分区 Grid。
    periods = pd.date_range("2026-01-01", periods=3, freq="h")
    grid = Grid(id="TEST"); grid.addZone(Zone(id="Z1"))
    # G1 成本低且初始在线，应优先承担负荷。
    grid.addResource(Thermal(
        id="G1", zoneId="Z1", type="THERMAL", Pmin=20, Pmax=100,
        rampUp=50, rampDown=50, minON=1, minOFF=1, initT=2,
        initialPower=50, startUpCost=500, shutDownCost=50,
        startUpCapacity=100, shutDownCapacity=100, variableCost=100,
    ))
    # G2 成本高且初始停机，只在第二时段高负荷时启动。
    grid.addResource(Thermal(
        id="G2", zoneId="Z1", type="THERMAL", Pmin=10, Pmax=80,
        rampUp=40, rampDown=40, minON=1, minOFF=1, initT=-2,
        initialPower=0, startUpCost=1000, shutDownCost=100,
        startUpCapacity=80, shutDownCapacity=80, variableCost=200,
    ))
    # Load 和 Reserve 对象直接携带逐时需求，不再额外传参数字典。
    grid.addResource(Load(id="D1", zoneId="Z1", type="LOAD",
                          TSCapacity=dict(zip(periods, [50, 140, 60]))))
    grid.addResource(Reserve(id="R1", zoneId="Z1", type="RESERVE",
                             TSCapacity={t: 20 for t in periods}))

    # 按“变量、机组约束、系统约束、目标”顺序完成建模。
    optmodel = OptModel()
    setThermalVarList(optmodel, grid, periods)
    setThermalUCCons(optmodel, grid, periods)
    setPowerBalanceCons(optmodel, grid, periods)
    setSystemReserveCons(optmodel, grid, periods)
    setThermalObjective(optmodel, grid, periods)
    optmodel.optimize()

    # 求解器必须找到全局最优解。
    assert optmodel.getModelAttribute(poi.ModelAttribute.TerminationStatus) == poi.TerminationStatusCode.OPTIMAL
    # expected 给出经济调度下每台机组的逐时出力。
    expected = {
        ("G1", periods[0]): 50, ("G1", periods[1]): 100,
        ("G1", periods[2]): 60, ("G2", periods[0]): 0,
        ("G2", periods[1]): 40, ("G2", periods[2]): 0,
    }
    for (unit, period), value in expected.items():
        assert optmodel.getValue(optmodel.getVar(unit, period, "P")) == pytest.approx(value)
    # G2 在第二时段启动、第三时段停机。
    assert optmodel.getValue(optmodel.getVar("G2", periods[1], "CV")) == pytest.approx(1)
    assert optmodel.getValue(optmodel.getVar("G2", periods[2], "CW")) == pytest.approx(1)
    # 最终成本包括电量、启动和停机三部分。
    assert optmodel.getModelAttribute(poi.ModelAttribute.ObjectiveValue) == pytest.approx(30100)
