import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.model.grid import Grid
from src.model.intertran import Intertran
from src.model.zone import Zone
from src.optim.constraints.power_balance import add_power_balance_constraints
from src.optim.variables import add_thermal_variables, add_transmission_variables


def make_grid(with_line=False):
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
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
    model = gurobi.Model()
    grid = make_grid()
    thermal = add_thermal_variables(model, ["G1"], [0])

    add_power_balance_constraints(
        model=model,
        grid=grid,
        periods=[0],
        demand_mw={("Z1", 0): 50.0},
        supply_groups=[
            {
                "variables": thermal.power,
                "resource_zones": {"G1": "Z1"},
            }
        ],
    )

    model.optimize()
    assert model.get_value(thermal.power["G1", 0]) == pytest.approx(50.0)


def test_two_zone_power_balance_with_transmission():
    model = gurobi.Model()
    grid = make_grid(with_line=True)
    thermal = add_thermal_variables(model, ["G1"], [0])
    transmission = add_transmission_variables(model, ["INTERTRANL1"], [0])

    add_power_balance_constraints(
        model=model,
        grid=grid,
        periods=[0],
        demand_mw={
            ("Z1", 0): 40.0,
            ("Z2", 0): 60.0,
        },
        supply_groups=[
            {
                "variables": thermal.power,
                "resource_zones": {"G1": "Z1"},
            }
        ],
        transmission_flow=transmission.flow,
    )

    model.add_linear_constraint(thermal.power["G1", 0], poi.Eq, 100.0)
    model.optimize()

    assert model.get_value(transmission.flow["INTERTRANL1", 0]) == pytest.approx(60.0)


def test_external_injection_offsets_demand():
    model = gurobi.Model()
    grid = make_grid()
    thermal = add_thermal_variables(model, ["G1"], [0])

    add_power_balance_constraints(
        model=model,
        grid=grid,
        periods=[0],
        demand_mw={("Z1", 0): 50.0},
        supply_groups=[
            {
                "variables": thermal.power,
                "resource_zones": {"G1": "Z1"},
            }
        ],
        fixed_external_injection_mw={("Z1", 0): 20.0},
    )

    model.optimize()
    assert model.get_value(thermal.power["G1", 0]) == pytest.approx(30.0)


def test_demand_group_subtracts_from_balance():
    model = gurobi.Model()
    grid = make_grid()
    thermal = add_thermal_variables(model, ["G1"], [0])
    load = add_thermal_variables(model, ["L1"], [0])

    add_power_balance_constraints(
        model=model,
        grid=grid,
        periods=[0],
        demand_mw={("Z1", 0): 50.0},
        supply_groups=[
            {
                "variables": thermal.power,
                "resource_zones": {"G1": "Z1"},
            }
        ],
        demand_groups=[
            {
                "variables": load.power,
                "resource_zones": {"L1": "Z1"},
            }
        ],
    )

    model.add_linear_constraint(load.power["L1", 0], poi.Eq, 10.0)
    model.optimize()
    assert model.get_value(thermal.power["G1", 0]) == pytest.approx(60.0)


def test_reject_missing_demand():
    model = gurobi.Model()
    grid = make_grid()

    with pytest.raises(ValueError, match="Missing zonal demand"):
        add_power_balance_constraints(
            model=model,
            grid=grid,
            periods=[0],
            demand_mw={},
        )


def test_reject_missing_transmission_variable():
    model = gurobi.Model()
    grid = make_grid(with_line=True)

    with pytest.raises(KeyError, match="Missing transmission flow"):
        add_power_balance_constraints(
            model=model,
            grid=grid,
            periods=[0],
            demand_mw={
                ("Z1", 0): 0.0,
                ("Z2", 0): 0.0,
            },
            transmission_flow={},
        )
