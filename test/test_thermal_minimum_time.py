import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.thermal import add_thermal_uc_constraints
from src.optim.variables import add_thermal_variables


def build_model(
    periods,
    initial_on,
    initial_on_hours,
    initial_off_hours,
    min_up_hours,
    min_down_hours,
):
    model = gurobi.Model()
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
        minON=min_up_hours,
        minOFF=min_down_hours,
    )
    unit.startUpCapacity = 100.0
    unit.shutDownCapacity = 100.0
    grid.addResource(unit)

    variables = add_thermal_variables(model, ["G1"], periods)
    add_thermal_uc_constraints(
        model=model,
        grid=grid,
        variables=variables,
        periods=periods,
        initial_on={"G1": initial_on},
        initial_power_mw={"G1": 0.0 if initial_on == 0 else 10.0},
        initial_on_hours={"G1": initial_on_hours},
        initial_off_hours={"G1": initial_off_hours},
        step_hours=1.0,
    )

    return model, variables


def test_unit_stays_on_for_minimum_up_time():
    periods = [0, 1, 2, 3]
    model, variables = build_model(
        periods=periods,
        initial_on=0,
        initial_on_hours=0,
        initial_off_hours=10,
        min_up_hours=3,
        min_down_hours=0,
    )

    model.add_linear_constraint(variables.is_on["G1", 0], poi.Eq, 1)
    model.set_objective(
        poi.quicksum(variables.is_on["G1", t] for t in periods),
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    actual_status = [model.get_value(variables.is_on["G1", t]) for t in periods]
    assert actual_status == pytest.approx([1.0, 1.0, 1.0, 0.0])


def test_unit_stays_off_for_minimum_down_time():
    periods = [0, 1, 2]
    model, variables = build_model(
        periods=periods,
        initial_on=1,
        initial_on_hours=10,
        initial_off_hours=0,
        min_up_hours=0,
        min_down_hours=2,
    )

    model.add_linear_constraint(variables.is_on["G1", 0], poi.Eq, 0)
    model.set_objective(
        -poi.quicksum(variables.is_on["G1", t] for t in periods),
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    actual_status = [model.get_value(variables.is_on["G1", t]) for t in periods]
    assert actual_status == pytest.approx([0.0, 0.0, 1.0])


def test_initial_on_residual_time_is_enforced():
    periods = [0, 1, 2]
    model, variables = build_model(
        periods=periods,
        initial_on=1,
        initial_on_hours=1,
        initial_off_hours=0,
        min_up_hours=3,
        min_down_hours=0,
    )

    model.set_objective(
        poi.quicksum(variables.is_on["G1", t] for t in periods),
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    actual_status = [model.get_value(variables.is_on["G1", t]) for t in periods]
    assert actual_status == pytest.approx([1.0, 1.0, 0.0])


def test_initial_off_residual_time_is_enforced():
    periods = [0, 1, 2]
    model, variables = build_model(
        periods=periods,
        initial_on=0,
        initial_on_hours=0,
        initial_off_hours=1,
        min_up_hours=0,
        min_down_hours=3,
    )

    model.set_objective(
        -poi.quicksum(variables.is_on["G1", t] for t in periods),
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    actual_status = [model.get_value(variables.is_on["G1", t]) for t in periods]
    assert actual_status == pytest.approx([0.0, 0.0, 1.0])


def test_reject_non_positive_step_hours():
    model = gurobi.Model()
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    grid.addResource(Thermal(id="G1", zoneId="Z1", type="THERMAL", Pmax=100.0))
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="step_hours"):
        add_thermal_uc_constraints(
            model=model,
            grid=grid,
            variables=variables,
            periods=[0],
            step_hours=0,
        )
