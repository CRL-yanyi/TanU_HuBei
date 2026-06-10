import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.optim.constraints.thermal import (
    add_thermal_commitment_constraints,
    add_thermal_minimum_time_constraints,
)
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
    variables = add_thermal_variables(model, ["G1"], periods)

    add_thermal_commitment_constraints(
        model=model,
        variables=variables,
        unit_ids=["G1"],
        periods=periods,
        initial_on={"G1": initial_on},
    )
    add_thermal_minimum_time_constraints(
        model=model,
        variables=variables,
        unit_ids=["G1"],
        periods=periods,
        min_up_hours={"G1": min_up_hours},
        min_down_hours={"G1": min_down_hours},
        initial_on={"G1": initial_on},
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

    expected_status = [1.0, 1.0, 1.0, 0.0]
    actual_status = [
        model.get_value(variables.is_on["G1", t])
        for t in periods
    ]

    assert actual_status == pytest.approx(expected_status)


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

    expected_status = [0.0, 0.0, 1.0]
    actual_status = [
        model.get_value(variables.is_on["G1", t])
        for t in periods
    ]

    assert actual_status == pytest.approx(expected_status)


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

    actual_status = [
        model.get_value(variables.is_on["G1", t])
        for t in periods
    ]

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

    actual_status = [
        model.get_value(variables.is_on["G1", t])
        for t in periods
    ]

    assert actual_status == pytest.approx([0.0, 0.0, 1.0])


def test_reject_non_positive_step_hours():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="时间步长"):
        add_thermal_minimum_time_constraints(
            model=model,
            variables=variables,
            unit_ids=["G1"],
            periods=[0],
            min_up_hours={"G1": 1},
            min_down_hours={"G1": 1},
            initial_on={"G1": 0},
            initial_on_hours={"G1": 0},
            initial_off_hours={"G1": 1},
            step_hours=0,
        )