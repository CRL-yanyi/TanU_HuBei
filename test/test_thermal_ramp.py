import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.optim.constraints.thermal import (
    add_thermal_commitment_constraints,
    add_thermal_ramp_constraints,
)
from src.optim.variables import add_thermal_variables


def build_ramp_model(
    periods,
    initial_on,
    initial_power,
    ramp_up=20.0,
    ramp_down=20.0,
    startup_ramp=40.0,
    shutdown_ramp=40.0,
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
    add_thermal_ramp_constraints(
        model=model,
        variables=variables,
        unit_ids=["G1"],
        periods=periods,
        ramp_up_mw_per_h={"G1": ramp_up},
        ramp_down_mw_per_h={"G1": ramp_down},
        startup_ramp_mw={"G1": startup_ramp},
        shutdown_ramp_mw={"G1": shutdown_ramp},
        initial_on={"G1": initial_on},
        initial_power_mw={"G1": initial_power},
        step_hours=1.0,
    )

    return model, variables


def test_normal_ramp_up_limit():
    model, variables = build_ramp_model(
        periods=[0],
        initial_on=1,
        initial_power=50.0,
    )

    model.add_linear_constraint(variables.is_on["G1", 0], poi.Eq, 1)
    model.set_objective(
        -variables.power["G1", 0],
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    assert model.get_value(variables.power["G1", 0]) == pytest.approx(70.0)


def test_normal_ramp_down_limit():
    model, variables = build_ramp_model(
        periods=[0],
        initial_on=1,
        initial_power=50.0,
    )

    model.add_linear_constraint(variables.is_on["G1", 0], poi.Eq, 1)
    model.set_objective(
        variables.power["G1", 0],
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    assert model.get_value(variables.power["G1", 0]) == pytest.approx(30.0)


def test_startup_ramp_limit():
    model, variables = build_ramp_model(
        periods=[0],
        initial_on=0,
        initial_power=0.0,
        startup_ramp=40.0,
    )

    model.add_linear_constraint(variables.is_on["G1", 0], poi.Eq, 1)
    model.set_objective(
        -variables.power["G1", 0],
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    assert model.get_value(variables.power["G1", 0]) == pytest.approx(40.0)
    assert model.get_value(variables.startup["G1", 0]) == pytest.approx(1.0)


def test_shutdown_ramp_allows_shutdown():
    model, variables = build_ramp_model(
        periods=[0],
        initial_on=1,
        initial_power=40.0,
        shutdown_ramp=40.0,
    )

    model.add_linear_constraint(variables.is_on["G1", 0], poi.Eq, 0)
    model.optimize()

    assert model.get_value(variables.power["G1", 0]) == pytest.approx(0.0)
    assert model.get_value(variables.shutdown["G1", 0]) == pytest.approx(1.0)


def test_reject_nonzero_power_when_initially_off():
    model = gurobi.Model()
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="初始停机时出力必须为 0"):
        add_thermal_ramp_constraints(
            model=model,
            variables=variables,
            unit_ids=["G1"],
            periods=[0],
            ramp_up_mw_per_h={"G1": 20.0},
            ramp_down_mw_per_h={"G1": 20.0},
            startup_ramp_mw={"G1": 40.0},
            shutdown_ramp_mw={"G1": 40.0},
            initial_on={"G1": 0},
            initial_power_mw={"G1": 10.0},
        )