"""验证输电变量的 TanU 登记方式和断面容量约束。"""

import pandas as pd
import pyoptinterface as poi
import pytest

from src.model.grid import Grid
from src.model.intertran import Intertran
from src.model.zone import Zone
from src.optim.constraints.transmission import setIntertranCons
from src.optim.opt_model import OptModel
from src.optim.variables import setIntertranVarList


def make_grid(cap_to=100.0, cap_from=50.0, status=1):
    """创建两个分区及一条可配置容量和状态的联络线。"""

    # Intertran 会自动给 L1 增加 INTERTRAN 前缀。
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1")); grid.addZone(Zone(id="Z2"))
    grid.addIntertran(Intertran(id="L1", fromZone="Z1", toZone="Z2",
                                capacityToZone=cap_to,
                                capacityFromZone=cap_from, status=status))
    return grid


def test_intertran_capacity_limits():
    """最大化和最小化潮流应分别达到正向、反向容量。"""

    # 创建双向潮流变量并添加上下限约束。
    periods = pd.date_range("2026-01-01", periods=1, freq="h")
    grid, optmodel = make_grid(), OptModel()
    setIntertranVarList(optmodel, grid, periods)
    setIntertranCons(optmodel, grid, periods)
    flow = optmodel.getVar("INTERTRANL1", periods[0], "P")
    # 最大化验证 fromZone->toZone 的 100 MW 正向容量。
    optmodel.model.set_objective(flow, poi.ObjectiveSense.Maximize)
    optmodel.optimize()
    assert optmodel.getValue(flow) == pytest.approx(100.0)
    # 最小化验证 toZone->fromZone 的 50 MW 反向容量。
    optmodel.model.set_objective(flow, poi.ObjectiveSense.Minimize)
    optmodel.optimize()
    assert optmodel.getValue(flow) == pytest.approx(-50.0)


def test_out_of_service_line_is_zero():
    """status=0 时断面潮流上下限都应收紧到零。"""

    periods = pd.date_range("2026-01-01", periods=1, freq="h")
    grid, optmodel = make_grid(status=0), OptModel()
    setIntertranVarList(optmodel, grid, periods)
    setIntertranCons(optmodel, grid, periods)
    optmodel.optimize()
    assert optmodel.getValue(optmodel.getVar("INTERTRANL1", periods[0], "P")) == pytest.approx(0)


def test_reject_invalid_transmission_limits():
    """负的正向或反向容量参数应被拒绝。"""

    periods = pd.date_range("2026-01-01", periods=1, freq="h")
    grid, optmodel = make_grid(cap_to=-1), OptModel()
    setIntertranVarList(optmodel, grid, periods)
    with pytest.raises(ValueError, match="Invalid transmission limits"):
        setIntertranCons(optmodel, grid, periods)
