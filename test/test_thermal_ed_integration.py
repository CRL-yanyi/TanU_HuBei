import pandas as pd
import pyoptinterface as poi
import pytest

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.power_balance import add_power_balance_constraints
from src.optim.constraints.reserve import add_system_reserve_constraints
from src.optim.constraints.thermal import add_thermal_ed_constraints
from src.optim.objectives import set_thermal_cost_objective
from src.optim.opt_model import OptModel
from src.optim.variables import add_thermal_variables


def make_periods():
    return pd.date_range("2026-01-01 00:00", periods=2, freq="h")


def make_grid(periods):
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))

    g1 = Thermal(
        id="G1",
        zoneId="Z1",
        type="THERMAL",
        Pmin=20.0,
        Pmax=100.0,
        capacity=100.0,
        rampUp=50.0,
        rampDown=50.0,
        initT=1,
        initialPower=50.0,
        startUpCost=500.0,
        shutDownCost=50.0,
    )
    g1.startUpCapacity = 100.0
    g1.shutDownCapacity = 100.0
    g1.linearCost = 100.0
    g1.ONOFF = {periods[0]: 1, periods[1]: 1}

    g2 = Thermal(
        id="G2",
        zoneId="Z1",
        type="THERMAL",
        Pmin=10.0,
        Pmax=80.0,
        capacity=80.0,
        rampUp=40.0,
        rampDown=40.0,
        initT=-1,
        initialPower=0.0,
        startUpCost=1000.0,
        shutDownCost=100.0,
    )
    g2.startUpCapacity = 80.0
    g2.shutDownCapacity = 80.0
    g2.linearCost = 200.0
    g2.ONOFF = {periods[0]: 0, periods[1]: 1}

    grid.addResource(g1)
    grid.addResource(g2)
    return grid


def test_fixed_status_economic_dispatch():
    opt_model = OptModel()
    periods = make_periods()
    grid = make_grid(periods)
    add_thermal_variables(opt_model, grid, periods)

    add_thermal_ed_constraints(
        opt_model=opt_model,
        grid=grid,
        periods=periods,
    )

    add_power_balance_constraints(
        model=opt_model.model,
        grid=grid,
        periods=periods,
        demand_mw={
            ("Z1", periods[0]): 80.0,
            ("Z1", periods[1]): 130.0,
        },
        supply_groups=[
            {
                "variables": opt_model.vars["thermal_power"],
                "resource_zones": {"G1": "Z1", "G2": "Z1"},
            }
        ],
    )

    add_system_reserve_constraints(
        opt_model=opt_model,
        grid=grid,
        periods=periods,
        reserve_requirement_mw={periods[0]: 20.0, periods[1]: 20.0},
    )

    set_thermal_cost_objective(
        opt_model=opt_model,
        grid=grid,
        periods=periods,
    )

    opt_model.optimize()

    assert opt_model.get_model_attribute(
        poi.ModelAttribute.TerminationStatus
    ) == poi.TerminationStatusCode.OPTIMAL

    power = opt_model.vars["thermal_power"]
    startup = opt_model.vars["thermal_startup"]
    expected_power = {
        ("G1", periods[0]): 80.0,
        ("G1", periods[1]): 100.0,
        ("G2", periods[0]): 0.0,
        ("G2", periods[1]): 30.0,
    }

    for key, expected in expected_power.items():
        assert opt_model.get_value(power[key]) == pytest.approx(expected)

    assert opt_model.get_value(startup["G2", periods[1]]) == pytest.approx(1.0)

    objective_value = opt_model.get_model_attribute(poi.ModelAttribute.ObjectiveValue)
    assert objective_value == pytest.approx(25000.0)
