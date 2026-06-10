import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.optim.constraints.thermal import add_thermal_commitment_constraints
from src.optim.variables import add_thermal_variables


def solve_transition(initial_on: int, target_on: int):
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    add_thermal_commitment_constraints(
        model=model,
        variables=variables,
        unit_ids=["G1"],
        periods=[0],
        initial_on={"G1": initial_on},
    )

    model.add_linear_constraint(
        variables.is_on["G1", 0],
        poi.Eq,
        target_on,
    )
    model.set_objective(
        variables.startup["G1", 0] + variables.shutdown["G1", 0],
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    return (
        model.get_value(variables.startup["G1", 0]),
        model.get_value(variables.shutdown["G1", 0]),
    )


@pytest.mark.parametrize(
    ("initial_on", "target_on", "expected_startup", "expected_shutdown"),
    [
        (0, 0, 0.0, 0.0),
        (0, 1, 1.0, 0.0),
        (1, 0, 0.0, 1.0),
        (1, 1, 0.0, 0.0),
    ],
)
def test_commitment_transition(
    initial_on,
    target_on,
    expected_startup,
    expected_shutdown,
):
    startup, shutdown = solve_transition(initial_on, target_on)

    assert startup == pytest.approx(expected_startup)
    assert shutdown == pytest.approx(expected_shutdown)


def test_reject_invalid_initial_state():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="必须为 0 或 1"):
        add_thermal_commitment_constraints(
            model=model,
            variables=variables,
            unit_ids=["G1"],
            periods=[0],
            initial_on={"G1": 2},
        )


def test_reject_missing_initial_state():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="缺少初始开机状态"):
        add_thermal_commitment_constraints(
            model=model,
            variables=variables,
            unit_ids=["G1"],
            periods=[0],
            initial_on={},
        )