import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.optim.constraints.reserve import add_system_reserve_constraints
from src.optim.constraints.thermal import add_thermal_capacity_constraints
from src.optim.variables import add_thermal_variables


def build_two_unit_model(reserve_requirement_mw):
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1", "G2"], [0])

    add_thermal_capacity_constraints(
        model=model,
        variables=variables,
        unit_ids=["G1", "G2"],
        periods=[0],
        p_min_mw={"G1": 0.0, "G2": 0.0},
        p_max_mw={"G1": 100.0, "G2": 100.0},
    )

    generation = poi.ExprBuilder()
    generation += variables.power["G1", 0]
    generation += variables.power["G2", 0]

    model.add_linear_constraint(
        generation,
        poi.Eq,
        80.0,
    )

    add_system_reserve_constraints(
        model=model,
        variables=variables,
        unit_ids=["G1", "G2"],
        periods=[0],
        p_max_mw={"G1": 100.0, "G2": 100.0},
        reserve_requirement_mw={0: reserve_requirement_mw},
    )

    online_units = poi.ExprBuilder()
    online_units += variables.is_on["G1", 0]
    online_units += variables.is_on["G2", 0]

    model.set_objective(
        online_units,
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    return model, variables


def test_high_reserve_requires_two_online_units():
    model, variables = build_two_unit_model(50.0)

    online_count = (
        model.get_value(variables.is_on["G1", 0])
        + model.get_value(variables.is_on["G2", 0])
    )

    assert online_count == pytest.approx(2.0)


def test_low_reserve_requires_only_one_online_unit():
    model, variables = build_two_unit_model(20.0)

    online_count = (
        model.get_value(variables.is_on["G1", 0])
        + model.get_value(variables.is_on["G2", 0])
    )

    assert online_count == pytest.approx(1.0)


def test_creates_one_constraint_per_period():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0, 1])

    constraints = add_system_reserve_constraints(
        model=model,
        variables=variables,
        unit_ids=["G1"],
        periods=[0, 1],
        p_max_mw={"G1": 100.0},
        reserve_requirement_mw={0: 10.0, 1: 20.0},
    )

    assert set(constraints.requirement) == {0, 1}


def test_rejects_missing_capacity():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="Missing maximum capacity"):
        add_system_reserve_constraints(
            model=model,
            variables=variables,
            unit_ids=["G1"],
            periods=[0],
            p_max_mw={},
            reserve_requirement_mw={0: 10.0},
        )


def test_rejects_missing_reserve_requirement():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="Missing reserve requirement"):
        add_system_reserve_constraints(
            model=model,
            variables=variables,
            unit_ids=["G1"],
            periods=[0],
            p_max_mw={"G1": 100.0},
            reserve_requirement_mw={},
        )


def test_rejects_negative_reserve_requirement():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="finite and nonnegative"):
        add_system_reserve_constraints(
            model=model,
            variables=variables,
            unit_ids=["G1"],
            periods=[0],
            p_max_mw={"G1": 100.0},
            reserve_requirement_mw={0: -1.0},
        )
