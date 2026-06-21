import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.reserve import add_system_reserve_constraints
from src.optim.constraints.thermal import add_thermal_uc_constraints
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


def test_system_reserve_limits_thermal_dispatch():
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
    add_system_reserve_constraints(
        model=model,
        grid=grid,
        variables=variables,
        periods=[0],
        reserve_requirement_mw={0: 20.0},
    )

    model.add_linear_constraint(variables.is_on["G1", 0], poi.Eq, 1)
    model.set_objective(variables.power["G1", 0], poi.ObjectiveSense.Maximize)
    model.optimize()

    assert model.get_value(variables.power["G1", 0]) == pytest.approx(80.0)


def test_system_reserve_returns_dict():
    model = gurobi.Model()
    grid = make_grid()
    variables = add_thermal_variables(model, ["G1"], [0])

    constraints = add_system_reserve_constraints(
        model=model,
        grid=grid,
        variables=variables,
        periods=[0],
        reserve_requirement_mw={0: 0.0},
    )

    assert set(constraints) == {"system_reserve_0"}


def test_reject_missing_reserve_requirement():
    model = gurobi.Model()
    grid = make_grid()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="Missing reserve requirement"):
        add_system_reserve_constraints(
            model=model,
            grid=grid,
            variables=variables,
            periods=[0],
            reserve_requirement_mw={},
        )


def test_reject_invalid_reserve_requirement():
    model = gurobi.Model()
    grid = make_grid()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="finite and nonnegative"):
        add_system_reserve_constraints(
            model=model,
            grid=grid,
            variables=variables,
            periods=[0],
            reserve_requirement_mw={0: -1.0},
        )
