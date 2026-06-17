import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.optim.constraints.thermal import add_thermal_capacity_constraints
from src.optim.variables import add_thermal_variables


def solve_single_period(is_on_value: int):
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    add_thermal_capacity_constraints(
        model=model,
        variables=variables,
        unit_ids=["G1"],
        periods=[0],
        p_min_mw={"G1": 20.0},
        p_max_mw={"G1": 100.0},
    )

    model.add_linear_constraint(
        variables.is_on["G1", 0],
        poi.Eq,
        is_on_value,
    )
    model.set_objective(
        variables.power["G1", 0],
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    return model, variables


def test_power_is_zero_when_unit_is_off():
    model, variables = solve_single_period(is_on_value=0)

    assert model.get_value(variables.power["G1", 0]) == pytest.approx(0.0)


def test_power_is_at_least_minimum_when_unit_is_on():
    model, variables = solve_single_period(is_on_value=1)

    assert model.get_value(variables.power["G1", 0]) == pytest.approx(20.0)


def test_reject_invalid_capacity_limits():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="上下限不合法"):
        add_thermal_capacity_constraints(
            model=model,
            variables=variables,
            unit_ids=["G1"],
            periods=[0],
            p_min_mw={"G1": 100.0},
            p_max_mw={"G1": 20.0},
        )


def test_reject_missing_capacity_parameter():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="缺少出力上下限"):
        add_thermal_capacity_constraints(
            model=model,
            variables=variables,
            unit_ids=["G1"],
            periods=[0],
            p_min_mw={},
            p_max_mw={"G1": 100.0},
        )