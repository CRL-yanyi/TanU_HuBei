import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.optim.constraints.thermal import (
    add_thermal_fixed_status_constraints,
)
from src.optim.variables import add_thermal_variables


def test_fixes_status_and_derives_transitions():
    model = gurobi.Model()
    periods = [0, 1, 2, 3]
    variables = add_thermal_variables(model, ["G1"], periods)

    constraints = add_thermal_fixed_status_constraints(
        model=model,
        variables=variables,
        unit_ids=["G1"],
        periods=periods,
        fixed_on={
            ("G1", 0): 0,
            ("G1", 1): 1,
            ("G1", 2): 1,
            ("G1", 3): 0,
        },
        initial_on={"G1": 0},
    )

    model.set_objective(
        variables.power["G1", 0],
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    expected_on = [0.0, 1.0, 1.0, 0.0]
    expected_startup = [0.0, 1.0, 0.0, 0.0]
    expected_shutdown = [0.0, 0.0, 0.0, 1.0]

    for index, period in enumerate(periods):
        key = ("G1", period)

        assert model.get_value(variables.is_on[key]) == pytest.approx(
            expected_on[index]
        )
        assert model.get_value(variables.startup[key]) == pytest.approx(
            expected_startup[index]
        )
        assert model.get_value(variables.shutdown[key]) == pytest.approx(
            expected_shutdown[index]
        )

    assert set(constraints.is_on) == {("G1", period) for period in periods}
    assert set(constraints.startup) == set(constraints.is_on)
    assert set(constraints.shutdown) == set(constraints.is_on)


def test_derives_shutdown_from_initial_status():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    add_thermal_fixed_status_constraints(
        model=model,
        variables=variables,
        unit_ids=["G1"],
        periods=[0],
        fixed_on={("G1", 0): 0},
        initial_on={"G1": 1},
    )

    model.set_objective(
        variables.power["G1", 0],
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    assert model.get_value(variables.startup["G1", 0]) == pytest.approx(0.0)
    assert model.get_value(variables.shutdown["G1", 0]) == pytest.approx(1.0)


def test_rejects_missing_fixed_status():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="Missing fixed commitment status"):
        add_thermal_fixed_status_constraints(
            model=model,
            variables=variables,
            unit_ids=["G1"],
            periods=[0],
            fixed_on={},
            initial_on={"G1": 0},
        )


def test_rejects_invalid_fixed_status():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="must be 0 or 1"):
        add_thermal_fixed_status_constraints(
            model=model,
            variables=variables,
            unit_ids=["G1"],
            periods=[0],
            fixed_on={("G1", 0): 2},
            initial_on={"G1": 0},
        )


def test_rejects_missing_initial_status():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="Missing initial commitment status"):
        add_thermal_fixed_status_constraints(
            model=model,
            variables=variables,
            unit_ids=["G1"],
            periods=[0],
            fixed_on={("G1", 0): 1},
            initial_on={},
        )