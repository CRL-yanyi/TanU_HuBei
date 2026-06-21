import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.thermal import add_thermal_ed_constraints
from src.optim.variables import add_thermal_variables


def make_grid():
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    unit = Thermal(
        id="G1",
        zoneId="Z1",
        type="THERMAL",
        Pmin=0.0,
        Pmax=100.0,
        rampUp=100.0,
        rampDown=100.0,
    )
    unit.startUpCapacity = 100.0
    unit.shutDownCapacity = 100.0
    grid.addResource(unit)
    return grid


def test_fixed_status_sets_commitment_and_transitions():
    model = gurobi.Model()
    grid = make_grid()
    variables = add_thermal_variables(model, ["G1"], [0, 1, 2])

    constraints = add_thermal_ed_constraints(
        model=model,
        grid=grid,
        variables=variables,
        periods=[0, 1, 2],
        fixed_on={
            ("G1", 0): 0,
            ("G1", 1): 1,
            ("G1", 2): 0,
        },
        initial_on={"G1": 0},
        initial_power_mw={"G1": 0.0},
    )
    model.optimize()

    assert "thermal_fixed_on_G1_0" in constraints
    assert model.get_value(variables.is_on["G1", 0]) == pytest.approx(0.0)
    assert model.get_value(variables.is_on["G1", 1]) == pytest.approx(1.0)
    assert model.get_value(variables.is_on["G1", 2]) == pytest.approx(0.0)
    assert model.get_value(variables.startup["G1", 1]) == pytest.approx(1.0)
    assert model.get_value(variables.shutdown["G1", 2]) == pytest.approx(1.0)


def test_fixed_status_allows_ed_capacity():
    model = gurobi.Model()
    grid = make_grid()
    grid.getResFromId("G1").Pmin = 20.0
    variables = add_thermal_variables(model, ["G1"], [0])

    add_thermal_ed_constraints(
        model=model,
        grid=grid,
        variables=variables,
        periods=[0],
        fixed_on={("G1", 0): 1},
        initial_on={"G1": 1},
        initial_power_mw={"G1": 50.0},
    )

    model.set_objective(variables.power["G1", 0], poi.ObjectiveSense.Minimize)
    model.optimize()
    assert model.get_value(variables.power["G1", 0]) == pytest.approx(20.0)


def test_rejects_missing_fixed_status():
    model = gurobi.Model()
    grid = make_grid()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="Missing fixed commitment"):
        add_thermal_ed_constraints(
            model=model,
            grid=grid,
            variables=variables,
            periods=[0],
            fixed_on={},
            initial_on={"G1": 0},
        )


def test_rejects_invalid_fixed_status():
    model = gurobi.Model()
    grid = make_grid()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="must be 0 or 1"):
        add_thermal_ed_constraints(
            model=model,
            grid=grid,
            variables=variables,
            periods=[0],
            fixed_on={("G1", 0): 2},
            initial_on={"G1": 0},
        )
