import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.power_balance import add_power_balance_constraints
from src.optim.constraints.reserve import add_system_reserve_constraints
from src.optim.constraints.thermal import add_thermal_uc_constraints
from src.optim.objectives import set_thermal_cost_objective
from src.optim.variables import add_thermal_variables


def make_grid():
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))

    g1 = Thermal(
        id="G1",
        zoneId="Z1",
        type="THERMAL",
        Pmin=20.0,
        Pmax=100.0,
        capacity=100.0,
        rampUp=50.0,
        rampDown=50.0,
        minON=1,
        minOFF=1,
        startUpCost=500.0,
        shutDownCost=50.0,
    )
    g1.startUpCapacity = 100.0
    g1.shutDownCapacity = 100.0
    g1.linearCost = 100.0

    g2 = Thermal(
        id="G2",
        zoneId="Z1",
        type="THERMAL",
        Pmin=10.0,
        Pmax=80.0,
        capacity=80.0,
        rampUp=40.0,
        rampDown=40.0,
        minON=1,
        minOFF=1,
        startUpCost=1000.0,
        shutDownCost=100.0,
    )
    g2.startUpCapacity = 80.0
    g2.shutDownCapacity = 80.0
    g2.linearCost = 200.0

    grid.addResource(g1)
    grid.addResource(g2)
    return grid


def test_two_unit_three_period_uc():
    model = gurobi.Model()
    grid = make_grid()
    unit_ids = ["G1", "G2"]
    periods = [0, 1, 2]

    variables = add_thermal_variables(model, unit_ids, periods)

    add_thermal_uc_constraints(
        model=model,
        grid=grid,
        variables=variables,
        periods=periods,
        initial_on={"G1": 1, "G2": 0},
        initial_power_mw={"G1": 50.0, "G2": 0.0},
        initial_on_hours={"G1": 2.0, "G2": 0.0},
        initial_off_hours={"G1": 0.0, "G2": 2.0},
    )

    add_power_balance_constraints(
        model=model,
        grid=grid,
        periods=periods,
        demand_mw={
            ("Z1", 0): 50.0,
            ("Z1", 1): 140.0,
            ("Z1", 2): 60.0,
        },
        supply_groups=[
            {
                "variables": variables.power,
                "resource_zones": {"G1": "Z1", "G2": "Z1"},
            }
        ],
    )

    add_system_reserve_constraints(
        model=model,
        grid=grid,
        variables=variables,
        periods=periods,
        reserve_requirement_mw={0: 20.0, 1: 20.0, 2: 20.0},
    )

    set_thermal_cost_objective(
        model=model,
        grid=grid,
        variables=variables,
        periods=periods,
    )

    model.optimize()

    assert model.get_model_attribute(
        poi.ModelAttribute.TerminationStatus
    ) == poi.TerminationStatusCode.OPTIMAL

    expected_power = {
        ("G1", 0): 50.0,
        ("G1", 1): 100.0,
        ("G1", 2): 60.0,
        ("G2", 0): 0.0,
        ("G2", 1): 40.0,
        ("G2", 2): 0.0,
    }

    for key, expected in expected_power.items():
        assert model.get_value(variables.power[key]) == pytest.approx(expected)

    assert model.get_value(variables.startup["G2", 1]) == pytest.approx(1.0)
    assert model.get_value(variables.shutdown["G2", 2]) == pytest.approx(1.0)

    objective_value = model.get_model_attribute(poi.ModelAttribute.ObjectiveValue)
    assert objective_value == pytest.approx(30100.0)
