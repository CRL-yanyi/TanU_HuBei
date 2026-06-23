import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.objectives import set_grid_objective
from src.optim.variables import add_thermal_variables


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


def test_set_grid_objective():
    model = gurobi.Model()
    grid = make_grid()
    variables = add_thermal_variables(model, ["G1"], [0])

    model.add_linear_constraint(variables.power["G1", 0], poi.Eq, 10.0)
    model.add_linear_constraint(variables.startup["G1", 0], poi.Eq, 1.0)
    model.add_linear_constraint(variables.shutdown["G1", 0], poi.Eq, 1.0)

    expressions = set_grid_objective(
        model=model,
        grid=grid,
        thermal_vars=variables,
        periods=[0],
    )

    model.optimize()

    assert "variable_cost" in expressions
    assert "startup_cost" in expressions
    assert "shutdown_cost" in expressions
    assert "total_cost" in expressions
    
    objective_value = model.get_model_attribute(poi.ModelAttribute.ObjectiveValue)
    assert objective_value == pytest.approx(80.0)


def test_reject_non_positive_step_hours():
    model = gurobi.Model()
    grid = make_grid()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="step_hours"):
        set_grid_objective(
            model=model,
            grid=grid,
            thermal_vars=variables,
            periods=[0],
            step_hours=0,
        )
