import pandas as pd
import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.model.grid import Grid
from src.model.intertran import Intertran
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.power_balance import add_power_balance_constraints
from src.optim.opt_model import OptModel
from src.optim.variables import add_thermal_variables, add_transmission_variables


def make_periods(count=1):
    return pd.date_range("2026-01-01 00:00", periods=count, freq="h")


def make_grid(with_line=False):
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    grid.addResource(Thermal(id="G1", zoneId="Z1", type="THERMAL"))
    if with_line:
        grid.addZone(Zone(id="Z2"))
        grid.addIntertran(
            Intertran(
                id="L1",
                fromZone="Z1",
                toZone="Z2",
                capacityToZone=100.0,
                capacityFromZone=100.0,
            )
        )
    return grid


def test_single_zone_power_balance():
    opt_model = OptModel()
    periods = make_periods()
    grid = make_grid()
    add_thermal_variables(opt_model, grid, periods)

    add_power_balance_constraints(
        model=opt_model.model,
        grid=grid,
        periods=periods,
        demand_mw={("Z1", periods[0]): 50.0},
        supply_groups=[
            {
                "variables": opt_model.vars["thermal_power"],
                "resource_zones": {"G1": "Z1"},
            }
        ],
    )

    opt_model.optimize()
    assert opt_model.get_value(opt_model.vars["thermal_power"]["G1", periods[0]]) == pytest.approx(50.0)


def test_two_zone_power_balance_with_transmission():
    opt_model = OptModel()
    periods = make_periods()
    grid = make_grid(with_line=True)
    add_thermal_variables(opt_model, grid, periods)
    transmission = add_transmission_variables(opt_model.model, ["INTERTRANL1"], periods)

    add_power_balance_constraints(
        model=opt_model.model,
        grid=grid,
        periods=periods,
        demand_mw={
            ("Z1", periods[0]): 40.0,
            ("Z2", periods[0]): 60.0,
        },
        supply_groups=[
            {
                "variables": opt_model.vars["thermal_power"],
                "resource_zones": {"G1": "Z1"},
            }
        ],
        transmission_flow=transmission.flow,
    )

    opt_model.model.add_linear_constraint(
        opt_model.vars["thermal_power"]["G1", periods[0]], poi.Eq, 100.0
    )
    opt_model.optimize()

    assert opt_model.get_value(transmission.flow["INTERTRANL1", periods[0]]) == pytest.approx(
        60.0
    )


def test_external_injection_offsets_demand():
    opt_model = OptModel()
    periods = make_periods()
    grid = make_grid()
    add_thermal_variables(opt_model, grid, periods)

    add_power_balance_constraints(
        model=opt_model.model,
        grid=grid,
        periods=periods,
        demand_mw={("Z1", periods[0]): 50.0},
        supply_groups=[
            {
                "variables": opt_model.vars["thermal_power"],
                "resource_zones": {"G1": "Z1"},
            }
        ],
        fixed_external_injection_mw={("Z1", periods[0]): 20.0},
    )

    opt_model.optimize()
    assert opt_model.get_value(opt_model.vars["thermal_power"]["G1", periods[0]]) == pytest.approx(30.0)


def test_demand_group_subtracts_from_balance():
    opt_model = OptModel()
    periods = make_periods()
    grid = make_grid()
    add_thermal_variables(opt_model, grid, periods)
    load = opt_model.model.add_variables(
        [("L1", periods[0])],
        lb=0.0,
        domain=poi.VariableDomain.Continuous,
        name="load_power",
    )

    add_power_balance_constraints(
        model=opt_model.model,
        grid=grid,
        periods=periods,
        demand_mw={("Z1", periods[0]): 50.0},
        supply_groups=[
            {
                "variables": opt_model.vars["thermal_power"],
                "resource_zones": {"G1": "Z1"},
            }
        ],
        demand_groups=[
            {
                "variables": load,
                "resource_zones": {"L1": "Z1"},
            }
        ],
    )

    opt_model.model.add_linear_constraint(load["L1", periods[0]], poi.Eq, 10.0)
    opt_model.optimize()
    assert opt_model.get_value(opt_model.vars["thermal_power"]["G1", periods[0]]) == pytest.approx(60.0)


def test_reject_missing_demand():
    model = gurobi.Model()
    periods = make_periods()
    grid = make_grid()

    with pytest.raises(ValueError, match="Missing zonal demand"):
        add_power_balance_constraints(
            model=model,
            grid=grid,
            periods=periods,
            demand_mw={},
        )


def test_reject_missing_transmission_variable():
    model = gurobi.Model()
    periods = make_periods()
    grid = make_grid(with_line=True)

    with pytest.raises(KeyError, match="Missing transmission flow"):
        add_power_balance_constraints(
            model=model,
            grid=grid,
            periods=periods,
            demand_mw={
                ("Z1", periods[0]): 0.0,
                ("Z2", periods[0]): 0.0,
            },
            transmission_flow={},
        )
