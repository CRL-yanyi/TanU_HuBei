import pandas as pd
import pyoptinterface as poi
import pytest

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.reserve import add_system_reserve_constraints
from src.optim.constraints.thermal import add_thermal_uc_constraints
from src.optim.opt_model import OptModel
from src.optim.variables import add_thermal_variables


def make_periods(count=1):
    return pd.date_range("2026-01-01 00:00", periods=count, freq="h")


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
        initT=1,
        initialPower=50.0,
    )
    unit.startUpCapacity = 100.0
    unit.shutDownCapacity = 100.0
    grid.addResource(unit)
    return grid


def test_system_reserve_limits_thermal_dispatch():
    opt_model = OptModel()
    periods = make_periods()
    grid = make_grid()
    add_thermal_variables(opt_model, grid, periods)

    add_thermal_uc_constraints(opt_model=opt_model, grid=grid, periods=periods)
    add_system_reserve_constraints(
        opt_model=opt_model,
        grid=grid,
        periods=periods,
        reserve_requirement_mw={periods[0]: 20.0},
    )

    is_on = opt_model.vars["thermal_is_on"]
    power = opt_model.vars["thermal_power"]
    opt_model.model.add_linear_constraint(is_on["G1", periods[0]], poi.Eq, 1)
    opt_model.model.set_objective(power["G1", periods[0]], poi.ObjectiveSense.Maximize)
    opt_model.optimize()

    assert opt_model.get_value(power["G1", periods[0]]) == pytest.approx(80.0)


def test_system_reserve_returns_dict():
    opt_model = OptModel()
    periods = make_periods()
    grid = make_grid()
    add_thermal_variables(opt_model, grid, periods)

    constraints = add_system_reserve_constraints(
        opt_model=opt_model,
        grid=grid,
        periods=periods,
        reserve_requirement_mw={periods[0]: 0.0},
    )

    assert set(constraints) == {f"system_reserve_{periods[0]}"}


def test_reject_missing_reserve_requirement():
    opt_model = OptModel()
    periods = make_periods()
    grid = make_grid()
    add_thermal_variables(opt_model, grid, periods)

    with pytest.raises(ValueError, match="Missing reserve requirement"):
        add_system_reserve_constraints(
            opt_model=opt_model,
            grid=grid,
            periods=periods,
            reserve_requirement_mw={},
        )


def test_reject_invalid_reserve_requirement():
    opt_model = OptModel()
    periods = make_periods()
    grid = make_grid()
    add_thermal_variables(opt_model, grid, periods)

    with pytest.raises(ValueError, match="finite and nonnegative"):
        add_system_reserve_constraints(
            opt_model=opt_model,
            grid=grid,
            periods=periods,
            reserve_requirement_mw={periods[0]: -1.0},
        )
