import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
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
        minON=0,
        minOFF=0,
    )
    unit.startUpCapacity = 100.0
    unit.shutDownCapacity = 100.0
    grid.addResource(unit)
    return grid


def solve_transition(initial_on: int, target_on: int):
    model = gurobi.Model()
    grid = make_grid()
    variables = add_thermal_variables(model, ["G1"], [0])

    add_thermal_uc_constraints(
        model=model,
        grid=grid,
        variables=variables,
        periods=[0],
        initial_on={"G1": initial_on},
        initial_power_mw={"G1": 0.0 if initial_on == 0 else 10.0},
    )

    model.add_linear_constraint(variables.is_on["G1", 0], poi.Eq, target_on)
    model.set_objective(
        variables.startup["G1", 0] + variables.shutdown["G1", 0],
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    return (
        model.get_value(variables.startup["G1", 0]),
        model.get_value(variables.shutdown["G1", 0]),
    )


@pytest.mark.parametrize(
    ("initial_on", "target_on", "expected_startup", "expected_shutdown"),
    [
        (0, 0, 0.0, 0.0),
        (0, 1, 1.0, 0.0),
        (1, 0, 0.0, 1.0),
        (1, 1, 0.0, 0.0),
    ],
)
def test_commitment_transition(
    initial_on,
    target_on,
    expected_startup,
    expected_shutdown,
):
    startup, shutdown = solve_transition(initial_on, target_on)

    assert startup == pytest.approx(expected_startup)
    assert shutdown == pytest.approx(expected_shutdown)


def test_reject_invalid_initial_state():
    model = gurobi.Model()
    grid = make_grid()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="must be 0 or 1"):
        add_thermal_uc_constraints(
            model=model,
            grid=grid,
            variables=variables,
            periods=[0],
            initial_on={"G1": 2},
        )
