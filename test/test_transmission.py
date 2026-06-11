import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.optim.constraints.transmission import (
    add_transmission_limit_constraints,
)
from src.optim.variables import add_transmission_variables


def test_add_transmission_variables():
    model = gurobi.Model()

    variables = add_transmission_variables(
        model=model,
        line_ids=["L1", "L2"],
        periods=[0, 1],
    )

    assert set(variables.flow.keys()) == {
        ("L1", 0),
        ("L1", 1),
        ("L2", 0),
        ("L2", 1),
    }


def test_positive_flow_limit():
    model = gurobi.Model()
    variables = add_transmission_variables(model, ["L1"], [0])

    add_transmission_limit_constraints(
        model=model,
        variables=variables,
        line_ids=["L1"],
        periods=[0],
        flow_min_mw={"L1": -20.0},
        flow_max_mw={"L1": 50.0},
    )

    model.set_objective(
        -variables.flow["L1", 0],
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    assert model.get_value(variables.flow["L1", 0]) == pytest.approx(50.0)


def test_negative_flow_limit():
    model = gurobi.Model()
    variables = add_transmission_variables(model, ["L1"], [0])

    add_transmission_limit_constraints(
        model=model,
        variables=variables,
        line_ids=["L1"],
        periods=[0],
        flow_min_mw={"L1": -20.0},
        flow_max_mw={"L1": 50.0},
    )

    model.set_objective(
        variables.flow["L1", 0],
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    assert model.get_value(variables.flow["L1", 0]) == pytest.approx(-20.0)


def test_one_way_transmission():
    model = gurobi.Model()
    variables = add_transmission_variables(model, ["L1"], [0])

    add_transmission_limit_constraints(
        model=model,
        variables=variables,
        line_ids=["L1"],
        periods=[0],
        flow_min_mw={"L1": 0.0},
        flow_max_mw={"L1": 50.0},
    )

    model.set_objective(
        variables.flow["L1", 0],
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    assert model.get_value(variables.flow["L1", 0]) == pytest.approx(0.0)


def test_reject_invalid_transmission_limits():
    model = gurobi.Model()
    variables = add_transmission_variables(model, ["L1"], [0])

    with pytest.raises(ValueError, match="上下限不合法"):
        add_transmission_limit_constraints(
            model=model,
            variables=variables,
            line_ids=["L1"],
            periods=[0],
            flow_min_mw={"L1": 50.0},
            flow_max_mw={"L1": -20.0},
        )


def test_reject_duplicate_line_ids():
    model = gurobi.Model()

    with pytest.raises(ValueError, match="断面 ID"):
        add_transmission_variables(
            model=model,
            line_ids=["L1", "L1"],
            periods=[0],
        )