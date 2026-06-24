import pandas as pd
import pyoptinterface as poi
import pytest

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.objectives import set_thermal_cost_objective
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
        Pmax=100.0,
        startUpCost=50.0,
        shutDownCost=10.0,
    )
    unit.linearCost = 2.0
    grid.addResource(unit)
    return grid


def test_set_thermal_cost_objective():
    opt_model = OptModel()
    periods = make_periods()
    grid = make_grid()
    add_thermal_variables(opt_model, grid, periods)

    power = opt_model.vars["thermal_power"]
    startup = opt_model.vars["thermal_startup"]
    shutdown = opt_model.vars["thermal_shutdown"]

    opt_model.model.add_linear_constraint(power["G1", periods[0]], poi.Eq, 10.0)
    opt_model.model.add_linear_constraint(startup["G1", periods[0]], poi.Eq, 1.0)
    opt_model.model.add_linear_constraint(shutdown["G1", periods[0]], poi.Eq, 1.0)

    expressions = set_thermal_cost_objective(
        opt_model=opt_model,
        grid=grid,
        periods=periods,
    )

    opt_model.optimize()

    assert set(expressions) == {
        "variable_cost",
        "startup_cost",
        "shutdown_cost",
        "total_cost",
    }
    objective_value = opt_model.get_model_attribute(poi.ModelAttribute.ObjectiveValue)
    assert objective_value == pytest.approx(80.0)


def test_reject_non_positive_step_hours():
    opt_model = OptModel()
    periods = make_periods()
    grid = make_grid()
    add_thermal_variables(opt_model, grid, periods)

    with pytest.raises(ValueError, match="step_hours"):
        set_thermal_cost_objective(
            opt_model=opt_model,
            grid=grid,
            periods=periods,
            step_hours=0,
        )
