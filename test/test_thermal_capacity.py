"""验证火电出力上下限约束及容量参数校验。"""

import pandas as pd
import pyoptinterface as poi
import pytest

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.thermal import setThermalUCCons
from src.optim.opt_model import OptModel
from src.optim.variables import setThermalVarList


def make_grid(p_min=20.0, p_max=100.0):
    """创建一台已开机且爬坡不构成额外限制的测试机组。"""

    # 机组初始出力位于上下限内，启停容量取 Pmax 以放宽启动过程。
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    unit = Thermal(id="G1", zoneId="Z1", type="THERMAL", Pmin=p_min,
                   Pmax=p_max, rampUp=p_max, rampDown=p_max, initT=1,
                   initialPower=50.0, startUpCapacity=p_max,
                   shutDownCapacity=p_max)
    grid.addResource(unit)
    return grid


def test_thermal_capacity_limits_from_resource():
    """开机状态下最小化/最大化出力应分别达到 Pmin/Pmax。"""

    # 准备单机单时段 UC 模型并添加完整常规约束。
    optmodel = OptModel()
    periods = pd.date_range("2026-01-01", periods=1, freq="h")
    grid = make_grid()
    setThermalVarList(optmodel, grid, periods)
    setThermalUCCons(optmodel, grid, periods)
    # 取出统一变量表中的出力 P 和开机状态 CU。
    power = optmodel.getVar("G1", periods[0], "P")
    on = optmodel.getVar("G1", periods[0], "CU")
    optmodel.model.add_linear_constraint(on, poi.Eq, 1.0)

    optmodel.model.set_objective(power, poi.ObjectiveSense.Minimize)
    optmodel.optimize()
    assert optmodel.getValue(power) == pytest.approx(20.0)

    optmodel.model.set_objective(power, poi.ObjectiveSense.Maximize)
    optmodel.optimize()
    assert optmodel.getValue(power) == pytest.approx(100.0)


def test_reject_invalid_capacity_limits():
    """Pmin 大于 Pmax 时应在建立容量约束阶段报错。"""

    optmodel = OptModel()
    periods = pd.date_range("2026-01-01", periods=1, freq="h")
    grid = make_grid(100.0, 20.0)
    setThermalVarList(optmodel, grid, periods)
    with pytest.raises(ValueError, match="Invalid output limits"):
        setThermalUCCons(optmodel, grid, periods)


def test_reject_missing_capacity_parameter():
    """缺少 Pmin 时不得静默使用默认值。"""

    optmodel = OptModel()
    periods = pd.date_range("2026-01-01", periods=1, freq="h")
    grid = make_grid()
    grid.getResFromId("G1").Pmin = None
    setThermalVarList(optmodel, grid, periods)
    with pytest.raises(ValueError, match="Pmin"):
        setThermalUCCons(optmodel, grid, periods)
    # 固定机组开机，先最小化出力验证 Pmin 下限。
    # 再最大化同一变量，验证 Pmax 上限。
