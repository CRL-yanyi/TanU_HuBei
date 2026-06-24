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
        initT=1,
        initialPower=50.0,
    )
    thermal.startUpCapacity = p_max
    thermal.shutDownCapacity = p_max
    grid.addResource(thermal)
    return grid


def test_thermal_capacity_limits_from_grid():
    opt_model = OptModel()
    grid = make_grid()
    periods = make_periods()
    t0 = periods[0]
    add_thermal_variables(opt_model, grid, periods)

    add_thermal_uc_constraints(opt_model=opt_model, grid=grid, periods=periods)

    is_on = opt_model.vars["thermal_is_on"]
    power = opt_model.vars["thermal_power"]

    opt_model.model.add_linear_constraint(is_on["G1", t0], poi.Eq, 1.0)
    opt_model.model.set_objective(power["G1", t0], poi.ObjectiveSense.Minimize)
    opt_model.optimize()
    assert opt_model.get_value(power["G1", t0]) == pytest.approx(20.0)

    opt_model.model.set_objective(power["G1", t0], poi.ObjectiveSense.Maximize)
    opt_model.optimize()
    assert opt_model.get_value(power["G1", t0]) == pytest.approx(100.0)


def test_reject_invalid_capacity_limits():
    opt_model = OptModel()
    grid = make_grid(p_min=100.0, p_max=20.0)
    periods = make_periods()
    add_thermal_variables(opt_model, grid, periods)

    with pytest.raises(ValueError, match="Invalid output limits"):
        add_thermal_uc_constraints(opt_model, grid, periods)


def test_reject_missing_capacity_parameter():
    opt_model = OptModel()
    grid = make_grid()
    periods = make_periods()
    grid.getResFromId("G1").Pmin = None
    add_thermal_variables(opt_model, grid, periods)

    with pytest.raises(ValueError, match="Pmin"):
        add_thermal_uc_constraints(opt_model, grid, periods)
