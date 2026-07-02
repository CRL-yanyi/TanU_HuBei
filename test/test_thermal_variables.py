"""验证火电变量使用 TanU 统一键创建和登记。"""

import pandas as pd
import pytest

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.opt_model import OptModel
from src.optim.variables import setThermalVarList


def make_periods(count=3):
    """创建带一小时时间频率的测试调度窗口。"""

    return pd.date_range("2026-01-01", periods=count, freq="h")


def make_grid(unit_ids=("G1", "G2")):
    """创建包含指定火电机组的单分区 Grid。"""

    # 所有测试机组放在同一分区，变量测试不涉及网络结构。
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    for unit_id in unit_ids:
        grid.addResource(Thermal(id=unit_id, zoneId="Z1", type="THERMAL"))
    return grid


def test_set_thermal_var_list_uses_tanu_keys():
    """P、CU、CV、CW 应具有完全相同的资源和时段索引。"""

    # 准备模型、三时段窗口和两台火电机组。
    optmodel = OptModel()
    periods = make_periods()
    # 调用待测接口，将四类变量直接登记到 optmodel.vars。
    setThermalVarList(optmodel, make_grid(), periods)

    # expected 是每类变量都应覆盖的 (机组ID, 时段) 组合。
    expected = {(g, t) for g in ("G1", "G2") for t in periods}
    # 逐类过滤统一四元组键，验证类型和默认子索引均正确。
    for variable_type in ("P", "CU", "CV", "CW"):
        actual = {
            (resource_id, period)
            for resource_id, period, kind, index in optmodel.vars
            if kind == variable_type and index == "0"
        }
        assert actual == expected


def test_reject_duplicate_variable_creation():
    """重复调用变量创建接口时不允许覆盖已有变量。"""

    # 首次调用正常建立变量。
    optmodel = OptModel()
    periods = make_periods(1)
    grid = make_grid(("G1",))
    setThermalVarList(optmodel, grid, periods)

    # 第二次使用相同键，应由 OptModel 主动报出重复变量。
    with pytest.raises(ValueError, match="Variable already exists"):
        setThermalVarList(optmodel, grid, periods)
