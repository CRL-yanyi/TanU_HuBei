import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.thermal import add_thermal_uc_constraints
from src.optim.variables import add_thermal_variables


def make_grid(p_min=20.0, p_max=100.0):
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    thermal = Thermal(
        id="G1",
        zoneId="Z1",
        type="THERMAL",
        Pmin=p_min,
        Pmax=p_max,
        capacity=p_max,
        rampUp=p_max,
        rampDown=p_max,
        minON=0,
        minOFF=0,
    )
    thermal.startUpCapacity = p_max
    thermal.shutDownCapacity = p_max
    grid.addResource(thermal)
    return grid


def test_thermal_capacity_limits_from_grid():
    model = gurobi.Model()
    grid = make_grid()
    variables = add_thermal_variables(model, ["G1"], [0])

    add_thermal_uc_constraints(
        model=model,
        grid=grid,
        variables=variables,
        periods=[0],
        initial_on={"G1": 1},
        initial_power_mw={"G1": 50.0},
    )

    model.add_linear_constraint(variables.is_on["G1", 0], poi.Eq, 1.0)
    model.set_objective(variables.power["G1", 0], poi.ObjectiveSense.Minimize)
    model.optimize()
    assert model.get_value(variables.power["G1", 0]) == pytest.approx(20.0)

    model.set_objective(variables.power["G1", 0], poi.ObjectiveSense.Maximize)
    model.optimize()
    assert model.get_value(variables.power["G1", 0]) == pytest.approx(100.0)


def test_reject_invalid_capacity_limits():
    model = gurobi.Model()
    grid = make_grid(p_min=100.0, p_max=20.0)
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="Invalid output limits"):
        add_thermal_uc_constraints(model, grid, variables, [0])


def test_reject_missing_capacity_parameter():
    model = gurobi.Model()
    grid = make_grid()
    grid.getResFromId("G1").Pmin = None
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="Pmin"):
        add_thermal_uc_constraints(model, grid, variables, [0])
