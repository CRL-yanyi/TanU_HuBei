"""验证在线火电剩余容量覆盖系统旋转备用需求。"""

import pandas as pd
import pyoptinterface as poi
import pytest

from src.model.grid import Grid
from src.model.resource import Reserve, Thermal
from src.model.zone import Zone
from src.optim.constraints.reserve import setSystemReserveCons
from src.optim.constraints.thermal import setThermalUCCons
from src.optim.opt_model import OptModel
from src.optim.variables import setThermalVarList


def make_case(requirement):
    """创建一台 100 MW 火电和给定 MW 备用需求。"""

    # 火电初始在线且爬坡充分，不让其他约束干扰备用边界测试。
    periods = pd.date_range("2026-01-01", periods=1, freq="h")
    grid = Grid(id="TEST"); grid.addZone(Zone(id="Z1"))
    grid.addResource(Thermal(id="G1", zoneId="Z1", type="THERMAL",
                             Pmax=100, rampUp=100, rampDown=100, initT=1,
                             initialPower=50, startUpCapacity=100,
                             shutDownCapacity=100))
    grid.addResource(Reserve(id="R1", zoneId="Z1", type="RESERVE",
                             TSCapacity={periods[0]: requirement}))
    optmodel = OptModel(); setThermalVarList(optmodel, grid, periods)
    return optmodel, grid, periods


def test_system_reserve_limits_dispatch():
    """20 MW 备用需求应把在线机组最大出力限制在 80 MW。"""

    # 添加 UC 和备用约束，并固定机组处于开机状态。
    optmodel, grid, periods = make_case(20)
    setThermalUCCons(optmodel, grid, periods)
    setSystemReserveCons(optmodel, grid, periods)
    power = optmodel.getVar("G1", periods[0], "P")
    optmodel.model.add_linear_constraint(optmodel.getVar("G1", periods[0], "CU"), poi.Eq, 1)
    # 最大化出力，使备用约束恰好达到边界。
    optmodel.model.set_objective(power, poi.ObjectiveSense.Maximize)
    optmodel.optimize()
    assert optmodel.getValue(power) == pytest.approx(80)
    # 约束表达式还应使用 Grid ID 和公式编号登记。
    assert ("TEST", periods[0], "R", "2.9.2") in optmodel.cons_expr


def test_missing_reserve_requirement_is_rejected():
    """备用资源必须包含每个调度时段的需求值。"""

    optmodel, grid, periods = make_case(0)
    grid.getResFromId("R1").TSCapacity = {}
    with pytest.raises(ValueError, match="Missing reserve requirement"):
        setSystemReserveCons(optmodel, grid, periods)


def test_invalid_reserve_requirement_is_rejected():
    """负备用需求不具有物理意义，应在建模阶段报错。"""

    optmodel, grid, periods = make_case(-1)
    with pytest.raises(ValueError, match="finite and nonnegative"):
        setSystemReserveCons(optmodel, grid, periods)
