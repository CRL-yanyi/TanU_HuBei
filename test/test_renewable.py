import pytest
import pyoptinterface as poi
from pyoptinterface import gurobi

from src.model.grid import Grid
from src.model.zone import Zone
from src.model.resource import Wind, PV
from src.optim.variables import add_renewable_variables
from src.optim.constraints.renewable import add_renewable_constraints


def test_renewable_balance_and_curtailment():
    """测试 (2.5.1) 出力与弃电的平衡。"""
    grid = Grid(id="test_grid")
    zone = Zone(id="Z1")
    grid.addZone(zone)

    # 添加一个风电和一个光伏
    wind = Wind(id="W1", zoneId="Z1", type="WIND", capacity=100.0)
    wind.TSCapacity = {"T1": 0.8, "T2": 0.5}  # 预测出力系数
    grid.addResource(wind)

    pv = PV(id="P1", zoneId="Z1", type="PV", capacity=50.0)
    pv.TSCapacity = {"T1": 1.0, "T2": 0.0}
    grid.addResource(pv)

    periods = ["T1", "T2"]
    
    model = gurobi.Model()
    variables = add_renewable_variables(model, ["W1", "P1"], periods)
    add_renewable_constraints(model, grid, variables, periods)

    # 人为限制出力，检查弃电量是否正确
    # W1在T1: pre=80, 限制 power=50 -> curt=30
    model.add_linear_constraint(variables.power["W1", "T1"], poi.Eq, 50.0)
    
    # 设定目标函数为最小化弃电量（测试是否可以消纳到最大限度）
    obj = variables.curtailment["W1", "T1"] + variables.curtailment["W1", "T2"] + \
          variables.curtailment["P1", "T1"] + variables.curtailment["P1", "T2"]
    model.set_objective(obj, sense=poi.ObjectiveSense.Minimize)
    
    model.optimize()
    assert model.get_model_attribute(poi.ModelAttribute.TerminationStatus) == poi.TerminationStatusCode.OPTIMAL
    
    # 验证 W1 T1
    assert model.get_value(variables.power["W1", "T1"]) == pytest.approx(50.0)
    assert model.get_value(variables.curtailment["W1", "T1"]) == pytest.approx(30.0)

    # 验证 W1 T2 (全额消纳，因为最小化了弃电量)
    assert model.get_value(variables.power["W1", "T2"]) == pytest.approx(50.0)
    assert model.get_value(variables.curtailment["W1", "T2"]) == pytest.approx(0.0)
    
    # 验证 P1
    assert model.get_value(variables.power["P1", "T1"]) == pytest.approx(50.0)
    assert model.get_value(variables.curtailment["P1", "T1"]) == pytest.approx(0.0)
    assert model.get_value(variables.power["P1", "T2"]) == pytest.approx(0.0)
    assert model.get_value(variables.curtailment["P1", "T2"]) == pytest.approx(0.0)


def test_renewable_ramping():
    """测试 (2.5.2) & (2.5.3) 爬坡限制。"""
    grid = Grid(id="test_grid")
    zone = Zone(id="Z1")
    grid.addZone(zone)

    wind = Wind(id="W1", zoneId="Z1", type="WIND", capacity=100.0)
    wind.TSCapacity = {"T1": 1.0, "T2": 1.0, "T3": 1.0}
    # 动态加上 rampUp 和 rampDown
    wind.rampUp = 20.0
    wind.rampDown = 10.0
    grid.addResource(wind)

    periods = ["T1", "T2", "T3"]
    model = gurobi.Model()
    variables = add_renewable_variables(model, ["W1"], periods)
    add_renewable_constraints(model, grid, variables, periods)

    # 固定 T1 的出力为 30
    model.add_linear_constraint(variables.power["W1", "T1"], poi.Eq, 30.0)
    # T2 最多只能是 30 + 20 = 50（上爬坡），T3 最多只能是 50 + 20 = 70
    # 为强制验证上爬坡限制被激活，我们最大化发电量
    obj = variables.power["W1", "T1"] + variables.power["W1", "T2"] + variables.power["W1", "T3"]
    model.set_objective(obj, sense=poi.ObjectiveSense.Maximize)
    
    model.optimize()
    assert model.get_model_attribute(poi.ModelAttribute.TerminationStatus) == poi.TerminationStatusCode.OPTIMAL
    assert model.get_value(variables.power["W1", "T1"]) == pytest.approx(30.0)
    assert model.get_value(variables.power["W1", "T2"]) == pytest.approx(50.0) # 受限于上爬坡 20
    assert model.get_value(variables.power["W1", "T3"]) == pytest.approx(70.0) # 受限于上爬坡 20

    # 验证下爬坡限制
    model2 = gurobi.Model()
    variables2 = add_renewable_variables(model2, ["W1"], periods)
    add_renewable_constraints(model2, grid, variables2, periods)

    # 固定 T1 的出力为 80
    model2.add_linear_constraint(variables2.power["W1", "T1"], poi.Eq, 80.0)
    # 最小化发电量，观察 T2 和 T3 能降到多低
    # T2 最少是 80 - 10 = 70，T3 最少是 70 - 10 = 60
    obj2 = variables2.power["W1", "T1"] + variables2.power["W1", "T2"] + variables2.power["W1", "T3"]
    model2.set_objective(obj2, sense=poi.ObjectiveSense.Minimize)

    model2.optimize()
    assert model2.get_model_attribute(poi.ModelAttribute.TerminationStatus) == poi.TerminationStatusCode.OPTIMAL
    assert model2.get_value(variables2.power["W1", "T1"]) == pytest.approx(80.0)
    assert model2.get_value(variables2.power["W1", "T2"]) == pytest.approx(70.0) # 受限于下爬坡 10
    assert model2.get_value(variables2.power["W1", "T3"]) == pytest.approx(60.0) # 受限于下爬坡 10
