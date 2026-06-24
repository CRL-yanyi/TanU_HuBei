import pandas as pd
import pyoptinterface as poi
import pytest

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.thermal import add_thermal_uc_constraints
from src.optim.opt_model import OptModel
from src.optim.variables import add_thermal_variables


def make_periods(count, freq="h"):
    return pd.date_range("2026-01-01 00:00", periods=count, freq=freq)


def build_model(
    periods,
    initial_on,
    initial_on_hours,
    initial_off_hours,
    min_up_hours,
    min_down_hours,
):
    opt_model = OptModel()
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    init_t = initial_on_hours if initial_on == 1 else -initial_off_hours
    unit = Thermal(
        id="G1",
        zoneId="Z1",
        type="THERMAL",
        Pmin=0.0,
        Pmax=100.0,
        rampUp=100.0,
        rampDown=100.0,
        minON=min_up_hours,
        minOFF=min_down_hours,
        initT=init_t,
        initialPower=10.0 if initial_on == 1 else 0.0,
    )
    unit.startUpCapacity = 100.0
    unit.shutDownCapacity = 100.0
    grid.addResource(unit)

    add_thermal_variables(opt_model, grid, periods)
    add_thermal_uc_constraints(
        opt_model=opt_model,
        grid=grid,
        periods=periods,
    )

    return opt_model


def test_unit_stays_on_for_minimum_up_time():
    periods = make_periods(4)
    opt_model = build_model(
        periods=periods,
        initial_on=0,
        initial_on_hours=0,
        initial_off_hours=10,
        min_up_hours=3,
        min_down_hours=0,
    )
    is_on = opt_model.vars["thermal_is_on"]

    opt_model.model.add_linear_constraint(is_on["G1", periods[0]], poi.Eq, 1)
    opt_model.model.set_objective(
        poi.quicksum(is_on["G1", t] for t in periods),
        poi.ObjectiveSense.Minimize,
    )
    opt_model.optimize()

    actual_status = [opt_model.get_value(is_on["G1", t]) for t in periods]
    assert actual_status == pytest.approx([1.0, 1.0, 1.0, 0.0])


def test_unit_stays_off_for_minimum_down_time():
    periods = make_periods(3)
    opt_model = build_model(
        periods=periods,
        initial_on=1,
        initial_on_hours=10,
        initial_off_hours=0,
        min_up_hours=0,
        min_down_hours=2,
    )
    is_on = opt_model.vars["thermal_is_on"]

    opt_model.model.add_linear_constraint(is_on["G1", periods[0]], poi.Eq, 0)
    opt_model.model.set_objective(
        -poi.quicksum(is_on["G1", t] for t in periods),
        poi.ObjectiveSense.Minimize,
    )
    opt_model.optimize()

    actual_status = [opt_model.get_value(is_on["G1", t]) for t in periods]
    assert actual_status == pytest.approx([0.0, 0.0, 1.0])


def test_initial_on_residual_time_is_enforced():
    periods = make_periods(3)
    opt_model = build_model(
        periods=periods,
        initial_on=1,
        initial_on_hours=1,
        initial_off_hours=0,
        min_up_hours=3,
        min_down_hours=0,
    )
    is_on = opt_model.vars["thermal_is_on"]

    opt_model.model.set_objective(
        poi.quicksum(is_on["G1", t] for t in periods),
        poi.ObjectiveSense.Minimize,
    )
    opt_model.optimize()

    actual_status = [opt_model.get_value(is_on["G1", t]) for t in periods]
    assert actual_status == pytest.approx([1.0, 1.0, 0.0])


def test_initial_off_residual_time_is_enforced():
    periods = make_periods(3)
    opt_model = build_model(
        periods=periods,
        initial_on=0,
        initial_on_hours=0,
        initial_off_hours=1,
        min_up_hours=0,
        min_down_hours=3,
    )
    is_on = opt_model.vars["thermal_is_on"]

    opt_model.model.set_objective(
        -poi.quicksum(is_on["G1", t] for t in periods),
        poi.ObjectiveSense.Minimize,
    )
    opt_model.optimize()

    actual_status = [opt_model.get_value(is_on["G1", t]) for t in periods]
    assert actual_status == pytest.approx([0.0, 0.0, 1.0])


def test_datetime_index_infers_step_hours():
    periods = make_periods(3, freq="30min")
    opt_model = build_model(
        periods=periods,
        initial_on=0,
        initial_on_hours=0,
        initial_off_hours=10,
        min_up_hours=1,
        min_down_hours=0,
    )
    is_on = opt_model.vars["thermal_is_on"]

    opt_model.model.add_linear_constraint(is_on["G1", periods[0]], poi.Eq, 1)
    opt_model.model.set_objective(
        poi.quicksum(is_on["G1", t] for t in periods),
        poi.ObjectiveSense.Minimize,
    )
    opt_model.optimize()

    actual_status = [opt_model.get_value(is_on["G1", t]) for t in periods]
    assert actual_status == pytest.approx([1.0, 1.0, 0.0])
