import pandas as pd
import pyoptinterface as poi
import pytest

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.thermal import add_thermal_ed_constraints
from src.optim.opt_model import OptModel
from src.optim.variables import add_thermal_variables


def make_periods(count):
    return pd.date_range("2026-01-01 00:00", periods=count, freq="h")


def make_grid(periods, onoff=None):
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
        initT=-1,
        initialPower=0.0,
    )
    unit.startUpCapacity = 100.0
    unit.shutDownCapacity = 100.0
    unit.ONOFF = onoff if onoff is not None else {period: 1 for period in periods}
    grid.addResource(unit)
    return grid


def test_fixed_status_sets_commitment_and_transitions():
    opt_model = OptModel()
    periods = make_periods(3)
    grid = make_grid(
        periods,
        {
            periods[0]: 0,
            periods[1]: 1,
            periods[2]: 0,
        },
    )
    add_thermal_variables(opt_model, grid, periods)

    add_thermal_ed_constraints(
        opt_model=opt_model,
        grid=grid,
        periods=periods,
    )
    opt_model.optimize()

    is_on = opt_model.vars["thermal_is_on"]
    startup = opt_model.vars["thermal_startup"]
    shutdown = opt_model.vars["thermal_shutdown"]

    assert f"thermal_fixed_on_G1_{periods[0]}" in opt_model.cons
    assert opt_model.get_value(is_on["G1", periods[0]]) == pytest.approx(0.0)
    assert opt_model.get_value(is_on["G1", periods[1]]) == pytest.approx(1.0)
    assert opt_model.get_value(is_on["G1", periods[2]]) == pytest.approx(0.0)
    assert opt_model.get_value(startup["G1", periods[1]]) == pytest.approx(1.0)
    assert opt_model.get_value(shutdown["G1", periods[2]]) == pytest.approx(1.0)


def test_fixed_status_allows_ed_capacity():
    opt_model = OptModel()
    periods = make_periods(1)
    grid = make_grid(periods, {periods[0]: 1})
    grid.getResFromId("G1").Pmin = 20.0
    grid.getResFromId("G1").initT = 1
    grid.getResFromId("G1").initialPower = 50.0
    add_thermal_variables(opt_model, grid, periods)

    add_thermal_ed_constraints(opt_model=opt_model, grid=grid, periods=periods)

    power = opt_model.vars["thermal_power"]
    opt_model.model.set_objective(power["G1", periods[0]], poi.ObjectiveSense.Minimize)
    opt_model.optimize()
    assert opt_model.get_value(power["G1", periods[0]]) == pytest.approx(20.0)


def test_rejects_missing_fixed_status():
    opt_model = OptModel()
    periods = make_periods(1)
    grid = make_grid(periods, {})
    add_thermal_variables(opt_model, grid, periods)

    with pytest.raises(ValueError, match="Missing fixed commitment"):
        add_thermal_ed_constraints(
            opt_model=opt_model,
            grid=grid,
            periods=periods,
        )


def test_rejects_invalid_fixed_status():
    opt_model = OptModel()
    periods = make_periods(1)
    grid = make_grid(periods, {periods[0]: 2})
    add_thermal_variables(opt_model, grid, periods)

    with pytest.raises(ValueError, match="must be 0 or 1"):
        add_thermal_ed_constraints(
            opt_model=opt_model,
            grid=grid,
            periods=periods,
        )
