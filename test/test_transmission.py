import pandas as pd
import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.model.grid import Grid
from src.model.intertran import Intertran
from src.model.zone import Zone
from src.optim.constraints.transmission import add_transmission_constraints
from src.optim.variables import add_transmission_variables


def make_periods(count=1):
    return pd.date_range("2026-01-01 00:00", periods=count, freq="h")


def make_grid(cap_to=100.0, cap_from=50.0, status=1):
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    grid.addZone(Zone(id="Z2"))
    grid.addIntertran(
        Intertran(
            id="L1",
            fromZone="Z1",
            toZone="Z2",
            capacityToZone=cap_to,
            capacityFromZone=cap_from,
            status=status,
        )
    )
    return grid


def test_add_transmission_constraints_limits_flow():
    model = gurobi.Model()
    periods = make_periods()
    grid = make_grid()
    variables = add_transmission_variables(model, ["INTERTRANL1"], periods)

    add_transmission_constraints(model, grid, variables, periods)

    model.set_objective(
        variables.flow["INTERTRANL1", periods[0]], poi.ObjectiveSense.Maximize
    )
    model.optimize()
    assert model.get_value(variables.flow["INTERTRANL1", periods[0]]) == pytest.approx(
        100.0
    )

    model.set_objective(
        variables.flow["INTERTRANL1", periods[0]], poi.ObjectiveSense.Minimize
    )
    model.optimize()
    assert model.get_value(variables.flow["INTERTRANL1", periods[0]]) == pytest.approx(
        -50.0
    )


def test_out_of_service_line_is_fixed_to_zero():
    model = gurobi.Model()
    periods = make_periods()
    grid = make_grid(status=0)
    variables = add_transmission_variables(model, ["INTERTRANL1"], periods)

    add_transmission_constraints(model, grid, variables, periods)
    model.optimize()

    assert model.get_value(variables.flow["INTERTRANL1", periods[0]]) == pytest.approx(
        0.0
    )


def test_reject_invalid_transmission_limits():
    model = gurobi.Model()
    periods = make_periods()
    grid = make_grid(cap_to=-10.0, cap_from=50.0)
    variables = add_transmission_variables(model, ["INTERTRANL1"], periods)

    with pytest.raises(ValueError, match="Invalid transmission limits"):
        add_transmission_constraints(model, grid, variables, periods)
