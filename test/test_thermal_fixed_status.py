"""验证 ED 从 Thermal.ONOFF 固定开机、启动和停机状态。"""

import pandas as pd
import pytest

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.thermal import setThermalEDCons
from src.optim.opt_model import OptModel
from src.optim.variables import setThermalVarList


def make_model(onoff):
    """创建一台初始停机机组，并注入待测试的 ONOFF 容器。"""

    periods = pd.date_range("2026-01-01", periods=3, freq="h")
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    grid.addResource(Thermal(
        id="G1", zoneId="Z1", type="THERMAL", Pmin=20.0, Pmax=100.0,
        rampUp=100.0, rampDown=100.0, startUpCapacity=100.0,
        shutDownCapacity=100.0, initT=-1, initialPower=0.0, ONOFF=onoff,
    ))
    optmodel = OptModel()
    setThermalVarList(optmodel, grid, periods)
    return optmodel, grid, periods


def test_ed_fixes_commitment_startup_and_shutdown():
    """状态序列 0->1->0 应产生一次启动和一次停机。"""

    # 建立 ED 约束并求解，CU/CV/CW 会被固定为确定值。
    optmodel, grid, periods = make_model([0, 1, 0])
    setThermalEDCons(optmodel, grid, periods)
    optmodel.optimize()
    assert [optmodel.getValue(optmodel.getVar("G1", t, "CU")) for t in periods] == pytest.approx([0, 1, 0])
    assert optmodel.getValue(optmodel.getVar("G1", periods[1], "CV")) == pytest.approx(1)
    assert optmodel.getValue(optmodel.getVar("G1", periods[2], "CW")) == pytest.approx(1)
    assert ("G1", periods[0], "FixedOnOff", "CU") in optmodel.cons


def test_ed_requires_fixed_commitment():
    """ED 缺少 ONOFF 时序时应明确报错。"""

    optmodel, grid, periods = make_model({})
    with pytest.raises(ValueError, match="Missing fixed commitment"):
        setThermalEDCons(optmodel, grid, periods)


def test_ed_rejects_non_binary_commitment():
    """ONOFF 中除 0、1 外的状态值均不合法。"""

    optmodel, grid, periods = make_model([0, 2, 0])
    with pytest.raises(ValueError, match="must be 0 or 1"):
        setThermalEDCons(optmodel, grid, periods)
    # 同时检查约束使用 TanU 元组键登记到 optmodel.cons。
