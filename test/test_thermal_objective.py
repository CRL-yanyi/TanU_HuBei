import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.optim.objectives import set_thermal_cost_objective
from src.optim.variables import add_thermal_variables


def test_selects_lower_cost_unit():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1", "G2"], [0])

    demand_balance = poi.ExprBuilder()
    demand_balance += variables.power["G1", 0]
    demand_balance += variables.power["G2", 0]

    model.add_linear_constraint(demand_balance, poi.Eq, 100.0)

    set_thermal_cost_objective(
        model=model,
        variables=variables,
        unit_ids=["G1", "G2"],
        periods=[0],
        variable_cost_yuan_per_mwh={
            "G1": 100.0,
            "G2": 200.0,
        },
        startup_cost_yuan={"G1": 0.0, "G2": 0.0},
        shutdown_cost_yuan={"G1": 0.0, "G2": 0.0},
    )

    model.optimize()

    assert model.get_value(variables.power["G1", 0]) == pytest.approx(100.0)
    assert model.get_value(variables.power["G2", 0]) == pytest.approx(0.0)


def test_calculates_all_cost_components():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    model.add_linear_constraint(
        variables.power["G1", 0],
        poi.Eq,
        10.0,
    )
    model.add_linear_constraint(
        variables.startup["G1", 0],
        poi.Eq,
        1.0,
    )
    model.add_linear_constraint(
        variables.shutdown["G1", 0],
        poi.Eq,
        1.0,
    )

    set_thermal_cost_objective(
        model=model,
        variables=variables,
        unit_ids=["G1"],
        periods=[0],
        variable_cost_yuan_per_mwh={"G1": 20.0},
        startup_cost_yuan={"G1": 100.0},
        shutdown_cost_yuan={"G1": 50.0},
        step_hours=0.5,
    )

    model.optimize()

    objective_value = model.get_model_attribute(
        poi.ModelAttribute.ObjectiveValue
    )

    # 20 yuan/MWh * 10 MW * 0.5 h + 100 + 50 = 250 yuan
    assert objective_value == pytest.approx(250.0)


def test_rejects_missing_cost():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="Missing variable cost"):
        set_thermal_cost_objective(
            model=model,
            variables=variables,
            unit_ids=["G1"],
            periods=[0],
            variable_cost_yuan_per_mwh={},
            startup_cost_yuan={"G1": 100.0},
            shutdown_cost_yuan={"G1": 50.0},
        )


def test_rejects_negative_cost():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="finite and nonnegative"):
        set_thermal_cost_objective(
            model=model,
            variables=variables,
            unit_ids=["G1"],
            periods=[0],
            variable_cost_yuan_per_mwh={"G1": -1.0},
            startup_cost_yuan={"G1": 100.0},
            shutdown_cost_yuan={"G1": 50.0},
        )


def test_rejects_invalid_step_hours():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="step_hours"):
        set_thermal_cost_objective(
            model=model,
            variables=variables,
            unit_ids=["G1"],
            periods=[0],
            variable_cost_yuan_per_mwh={"G1": 20.0},
            startup_cost_yuan={"G1": 100.0},
            shutdown_cost_yuan={"G1": 50.0},
            step_hours=0.0,
        )