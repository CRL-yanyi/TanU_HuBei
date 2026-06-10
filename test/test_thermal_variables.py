import pytest
from pyoptinterface import gurobi

from src.optim.variables import add_thermal_variables


def test_add_thermal_variables():
    model = gurobi.Model()

    variables = add_thermal_variables(
        model=model,
        unit_ids=["G1", "G2"],
        periods=range(3),
    )

    expected_keys = {
        ("G1", 0),
        ("G1", 1),
        ("G1", 2),
        ("G2", 0),
        ("G2", 1),
        ("G2", 2),
    }

    assert set(variables.power.keys()) == expected_keys
    assert set(variables.is_on.keys()) == expected_keys
    assert set(variables.startup.keys()) == expected_keys
    assert set(variables.shutdown.keys()) == expected_keys


def test_reject_duplicate_unit_ids():
    model = gurobi.Model()

    with pytest.raises(ValueError, match="机组 ID"):
        add_thermal_variables(
            model=model,
            unit_ids=["G1", "G1"],
            periods=range(3),
        )


def test_reject_duplicate_periods():
    model = gurobi.Model()

    with pytest.raises(ValueError, match="时间索引"):
        add_thermal_variables(
            model=model,
            unit_ids=["G1"],
            periods=[0, 0],
        )