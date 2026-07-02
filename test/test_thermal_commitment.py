"""验证窗口初始状态与 CU/CV/CW 状态转换关系。"""

import pandas as pd
import pyoptinterface as poi
import pytest

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.thermal import setThermalUCCons
from src.optim.opt_model import OptModel
from src.optim.variables import setThermalVarList


def solve_transition(initial_on, target_on):
    """求解一个单时段状态转换，并返回启动、停机变量值。"""

    # initT 正负号表达窗口开始前状态，initialPower 与该状态保持一致。
    optmodel = OptModel()
    periods = pd.date_range("2026-01-01", periods=1, freq="h")
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    grid.addResource(Thermal(
        id="G1", zoneId="Z1", type="THERMAL", Pmax=100.0,
        rampUp=100.0, rampDown=100.0,
        startUpCapacity=100.0, shutDownCapacity=100.0,
        initT=1 if initial_on else -1,
        initialPower=10.0 if initial_on else 0.0,
    ))
    setThermalVarList(optmodel, grid, periods)
    setThermalUCCons(optmodel, grid, periods)
    on = optmodel.getVar("G1", periods[0], "CU")
    startup = optmodel.getVar("G1", periods[0], "CV")
    shutdown = optmodel.getVar("G1", periods[0], "CW")
    optmodel.model.add_linear_constraint(on, poi.Eq, target_on)
    optmodel.model.set_objective(startup + shutdown, poi.ObjectiveSense.Minimize)
    optmodel.optimize()
    # 返回求解后的启动和停机指示量供参数化用例检查。
    return optmodel.getValue(startup), optmodel.getValue(shutdown)


@pytest.mark.parametrize(("initial_on", "target_on", "startup", "shutdown"), [
    (0, 0, 0.0, 0.0), (0, 1, 1.0, 0.0),
    (1, 0, 0.0, 1.0), (1, 1, 0.0, 0.0),
])
def test_commitment_transition(initial_on, target_on, startup, shutdown):
    """四种初始/目标状态组合应推导出正确启停动作。"""

    # 参数表覆盖保持停机、启动、停机和保持开机四种情况。
    actual_startup, actual_shutdown = solve_transition(initial_on, target_on)
    assert actual_startup == pytest.approx(startup)
    assert actual_shutdown == pytest.approx(shutdown)


def test_reject_nonzero_power_when_initially_off():
    """窗口开始前停机时，initialPower 必须为零。"""

    optmodel = OptModel()
    periods = pd.date_range("2026-01-01", periods=1, freq="h")
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    grid.addResource(Thermal(id="G1", zoneId="Z1", type="THERMAL",
                             Pmax=100.0, rampUp=100.0, rampDown=100.0,
                             initT=-1, initialPower=10.0))
    setThermalVarList(optmodel, grid, periods)
    with pytest.raises(ValueError, match="Initial power must be 0"):
        setThermalUCCons(optmodel, grid, periods)
    # 创建变量和 UC 约束后，把第一时段 CU 固定到目标状态。
    # 最小化启停次数，排除多余的 CV/CW 同时取值。
