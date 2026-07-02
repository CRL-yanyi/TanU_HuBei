"""验证分区功率平衡中的负荷和联络线符号。"""

import pandas as pd
import pyoptinterface as poi
import pytest

from src.model.grid import Grid
from src.model.intertran import Intertran
from src.model.resource import Load, Thermal
from src.model.zone import Zone
from src.optim.constraints.power_balance import setPowerBalanceCons
from src.optim.opt_model import OptModel
from src.optim.variables import setIntertranVarList, setThermalVarList


def test_single_zone_power_balance_reads_load_resource():
    """单分区中火电出力应自动等于 Load.TSCapacity。"""

    # 构造 50 MW 固定负荷和一台无容量约束的火电机组。
    periods = pd.date_range("2026-01-01", periods=1, freq="h")
    grid = Grid(id="TEST"); grid.addZone(Zone(id="Z1"))
    grid.addResource(Thermal(id="G1", zoneId="Z1", type="THERMAL"))
    grid.addResource(Load(id="D1", zoneId="Z1", type="LOAD",
                          TSCapacity={periods[0]: 50.0}))
    optmodel = OptModel(); setThermalVarList(optmodel, grid, periods)
    # 平衡式 P_thermal-50=0，因此无需额外目标即可得到 50 MW。
    setPowerBalanceCons(optmodel, grid, periods)
    optmodel.optimize()
    assert optmodel.getValue(optmodel.getVar("G1", periods[0], "P")) == pytest.approx(50)


def test_two_zone_balance_uses_intertran_variable():
    """起点发电应通过正向联络线供应终点分区负荷。"""

    # Z1 发电 100 MW，其中本地消纳 40 MW，剩余 60 MW 流向 Z2。
    periods = pd.date_range("2026-01-01", periods=1, freq="h")
    grid = Grid(id="TEST"); grid.addZone(Zone(id="Z1")); grid.addZone(Zone(id="Z2"))
    grid.addResource(Thermal(id="G1", zoneId="Z1", type="THERMAL"))
    grid.addResource(Load(id="D1", zoneId="Z1", type="LOAD", TSCapacity={periods[0]: 40}))
    grid.addResource(Load(id="D2", zoneId="Z2", type="LOAD", TSCapacity={periods[0]: 60}))
    grid.addIntertran(Intertran(id="L1", fromZone="Z1", toZone="Z2",
                                capacityToZone=100, capacityFromZone=100))
    # 火电和输电变量都登记到同一个 OptModel 变量表。
    optmodel = OptModel(); setThermalVarList(optmodel, grid, periods)
    setIntertranVarList(optmodel, grid, periods)
    setPowerBalanceCons(optmodel, grid, periods)
    # 固定总发电后，两条分区平衡等式共同确定断面潮流。
    optmodel.model.add_linear_constraint(optmodel.getVar("G1", periods[0], "P"), poi.Eq, 100)
    optmodel.optimize()
    assert optmodel.getValue(optmodel.getVar("INTERTRANL1", periods[0], "P")) == pytest.approx(60)


def test_missing_load_series_is_rejected():
    """负荷缺少当前时段数据时不能建立不完整平衡式。"""

    periods = pd.date_range("2026-01-01", periods=1, freq="h")
    grid = Grid(id="TEST"); grid.addZone(Zone(id="Z1"))
    grid.addResource(Load(id="D1", zoneId="Z1", type="LOAD"))
    with pytest.raises(ValueError, match="Missing time-series value"):
        setPowerBalanceCons(OptModel(), grid, periods)
