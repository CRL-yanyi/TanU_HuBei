import pandas as pd
import pyoptinterface as poi
import pytest

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.thermal import add_thermal_uc_constraints
from src.optim.opt_model import OptModel
from src.optim.variables import add_thermal_variables


def make_periods(count=1):
    return pd.date_range("2026-01-01 00:00", periods=count, freq="h")


def make_grid(initial_on: int):
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
        initT=1 if initial_on == 1 else -1,
        initialPower=10.0 if initial_on == 1 else 0.0,
    )
    unit.startUpCapacity = 100.0
    unit.shutDownCapacity = 100.0
    grid.addResource(unit)
    return grid


def solve_transition(initial_on: int, target_on: int):
    opt_model = OptModel()
    grid = make_grid(initial_on)
    periods = make_periods()
    t0 = periods[0]
    add_thermal_variables(opt_model, grid, periods)

    add_thermal_uc_constraints(opt_model=opt_model, grid=grid, periods=periods)

    is_on = opt_model.vars["thermal_is_on"]
    startup = opt_model.vars["thermal_startup"]
    shutdown = opt_model.vars["thermal_shutdown"]

    opt_model.model.add_linear_constraint(is_on["G1", t0], poi.Eq, target_on)
    opt_model.model.set_objective(
        startup["G1", t0] + shutdown["G1", t0],
        poi.ObjectiveSense.Minimize,
    )
    opt_model.optimize()

    return (
        opt_model.get_value(startup["G1", t0]),
        opt_model.get_value(shutdown["G1", t0]),
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


def test_reject_nonzero_power_when_initially_off():
    opt_model = OptModel()
    grid = make_grid(initial_on=0)
    grid.getResFromId("G1").initialPower = 10.0
    periods = make_periods()
    add_thermal_variables(opt_model, grid, periods)

    with pytest.raises(ValueError, match="Initial power must be 0"):
        add_thermal_uc_constraints(opt_model=opt_model, grid=grid, periods=periods)
