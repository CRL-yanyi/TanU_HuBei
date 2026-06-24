import pandas as pd
import pyoptinterface as poi
import pytest

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.thermal import add_thermal_uc_constraints
from src.optim.opt_model import OptModel
from src.optim.variables import add_thermal_variables


def make_periods(count=1, freq="h"):
    return pd.date_range("2026-01-01 00:00", periods=count, freq=freq)


def build_ramp_model(
    periods,
    initial_on,
    initial_power,
    ramp_up=20.0,
    ramp_down=20.0,
    startup_ramp=40.0,
    shutdown_ramp=40.0,
):
    opt_model = OptModel()
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    unit = Thermal(
        id="G1",
        zoneId="Z1",
        type="THERMAL",
        Pmin=0.0,
        Pmax=100.0,
        rampUp=ramp_up,
        rampDown=ramp_down,
        minON=0,
        minOFF=0,
        initT=1 if initial_on == 1 else -1,
        initialPower=initial_power,
    )
    unit.startUpCapacity = startup_ramp
    unit.shutDownCapacity = shutdown_ramp
    grid.addResource(unit)

    add_thermal_variables(opt_model, grid, periods)
    add_thermal_uc_constraints(opt_model=opt_model, grid=grid, periods=periods)

    return opt_model


def test_normal_ramp_up_limit():
    periods = make_periods()
    t0 = periods[0]
    opt_model = build_ramp_model(periods, initial_on=1, initial_power=50.0)
    is_on = opt_model.vars["thermal_is_on"]
    power = opt_model.vars["thermal_power"]

    opt_model.model.add_linear_constraint(is_on["G1", t0], poi.Eq, 1)
    opt_model.model.set_objective(-power["G1", t0], poi.ObjectiveSense.Minimize)
    opt_model.optimize()

    assert opt_model.get_value(power["G1", t0]) == pytest.approx(70.0)


def test_normal_ramp_down_limit():
    periods = make_periods()
    t0 = periods[0]
    opt_model = build_ramp_model(periods, initial_on=1, initial_power=50.0)
    is_on = opt_model.vars["thermal_is_on"]
    power = opt_model.vars["thermal_power"]

    opt_model.model.add_linear_constraint(is_on["G1", t0], poi.Eq, 1)
    opt_model.model.set_objective(power["G1", t0], poi.ObjectiveSense.Minimize)
    opt_model.optimize()

    assert opt_model.get_value(power["G1", t0]) == pytest.approx(30.0)


def test_startup_ramp_limit():
    periods = make_periods()
    t0 = periods[0]
    opt_model = build_ramp_model(
        periods,
        initial_on=0,
        initial_power=0.0,
        startup_ramp=40.0,
    )
    is_on = opt_model.vars["thermal_is_on"]
    power = opt_model.vars["thermal_power"]
    startup = opt_model.vars["thermal_startup"]

    opt_model.model.add_linear_constraint(is_on["G1", t0], poi.Eq, 1)
    opt_model.model.set_objective(-power["G1", t0], poi.ObjectiveSense.Minimize)
    opt_model.optimize()

    assert opt_model.get_value(power["G1", t0]) == pytest.approx(40.0)
    assert opt_model.get_value(startup["G1", t0]) == pytest.approx(1.0)


def test_shutdown_ramp_allows_shutdown():
    periods = make_periods()
    t0 = periods[0]
    opt_model = build_ramp_model(
        periods,
        initial_on=1,
        initial_power=40.0,
        shutdown_ramp=40.0,
    )
    is_on = opt_model.vars["thermal_is_on"]
    power = opt_model.vars["thermal_power"]
    shutdown = opt_model.vars["thermal_shutdown"]

    opt_model.model.add_linear_constraint(is_on["G1", t0], poi.Eq, 0)
    opt_model.optimize()

    assert opt_model.get_value(power["G1", t0]) == pytest.approx(0.0)
    assert opt_model.get_value(shutdown["G1", t0]) == pytest.approx(1.0)


def test_datetime_index_infers_ramp_step_hours():
    periods = make_periods(2, freq="30min")
    t0 = periods[0]
    opt_model = build_ramp_model(periods, initial_on=1, initial_power=50.0)
    is_on = opt_model.vars["thermal_is_on"]
    power = opt_model.vars["thermal_power"]

    opt_model.model.add_linear_constraint(is_on["G1", t0], poi.Eq, 1)
    opt_model.model.set_objective(-power["G1", t0], poi.ObjectiveSense.Minimize)
    opt_model.optimize()

    assert opt_model.get_value(power["G1", t0]) == pytest.approx(60.0)
