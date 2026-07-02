"""验证火电发电、启动和停机成本统一累计。"""

import pandas as pd
import pyoptinterface as poi
import pytest

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.objectives import setThermalObjective
from src.optim.opt_model import OptModel
from src.optim.variables import setThermalVarList


def test_thermal_objective_accumulates_three_costs():
    """10 MW 发电加一次启停的总成本应为 80 元。"""

    # 成本构成为 2*10*1 小时 + 50 启动 + 10 停机。
    periods = pd.date_range("2026-01-01", periods=1, freq="h")
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    grid.addResource(Thermal(id="G1", zoneId="Z1", type="THERMAL",
                             variableCost=2.0, startUpCost=50.0,
                             shutDownCost=10.0))
    # 创建火电四类变量，并用等式固定本测试需要的变量值。
    optmodel = OptModel()
    setThermalVarList(optmodel, grid, periods)
    optmodel.model.add_linear_constraint(optmodel.getVar("G1", periods[0], "P"), poi.Eq, 10)
    optmodel.model.add_linear_constraint(optmodel.getVar("G1", periods[0], "CV"), poi.Eq, 1)
    optmodel.model.add_linear_constraint(optmodel.getVar("G1", periods[0], "CW"), poi.Eq, 1)
    # 设置成员3目标、求解并读取模型最优目标值。
    setThermalObjective(optmodel, grid, periods)
    optmodel.optimize()
    value = optmodel.getModelAttribute(poi.ModelAttribute.ObjectiveValue)
    assert value == pytest.approx(80.0)
