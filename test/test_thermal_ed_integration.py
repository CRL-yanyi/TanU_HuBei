import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.optim.constraints.power_balance import (
    ZonalVariableGroup,
    add_power_balance_constraints,
)
from src.optim.constraints.reserve import add_system_reserve_constraints
from src.optim.constraints.thermal import (
    add_thermal_capacity_constraints,
    add_thermal_fixed_status_constraints,
    add_thermal_ramp_constraints,
)
from src.optim.objectives import set_thermal_cost_objective
from src.optim.variables import add_thermal_variables


def test_fixed_status_economic_dispatch():
    model = gurobi.Model()

    unit_ids = ["G1", "G2"]
    periods = [0, 1]
    initial_on = {"G1": 1, "G2": 0}
    p_max_mw = {"G1": 100.0, "G2": 80.0}

    variables = add_thermal_variables(model, unit_ids, periods)

    add_thermal_fixed_status_constraints(
        model=model,
        variables=variables,
        unit_ids=unit_ids,
        periods=periods,
        fixed_on={
            ("G1", 0): 1,
            ("G1", 1): 1,
            ("G2", 0): 0,
            ("G2", 1): 1,
        },
        initial_on=initial_on,
    )

    add_thermal_capacity_constraints(
        model=model,
        variables=variables,
        unit_ids=unit_ids,
        periods=periods,
        p_min_mw={"G1": 20.0, "G2": 10.0},
        p_max_mw=p_max_mw,
    )

    add_thermal_ramp_constraints(
        model=model,
        variables=variables,
        unit_ids=unit_ids,
        periods=periods,
        ramp_up_mw_per_h={"G1": 50.0, "G2": 40.0},
        ramp_down_mw_per_h={"G1": 50.0, "G2": 40.0},
        startup_ramp_mw={"G1": 100.0, "G2": 80.0},
        shutdown_ramp_mw={"G1": 100.0, "G2": 80.0},
        initial_on=initial_on,
        initial_power_mw={"G1": 50.0, "G2": 0.0},
    )

    thermal_supply = ZonalVariableGroup(
        variables=variables.power,
        resource_zones={"G1": "Z1", "G2": "Z1"},
    )

    add_power_balance_constraints(
        model=model,
        zones=["Z1"],
        periods=periods,
        demand_mw={
            ("Z1", 0): 80.0,
            ("Z1", 1): 130.0,
        },
        supply_groups=[thermal_supply],
    )

    add_system_reserve_constraints(
        model=model,
        variables=variables,
        unit_ids=unit_ids,
        periods=periods,
        p_max_mw=p_max_mw,
        reserve_requirement_mw={0: 20.0, 1: 20.0},
    )

    set_thermal_cost_objective(
        model=model,
        variables=variables,
        unit_ids=unit_ids,
        periods=periods,
        variable_cost_yuan_per_mwh={
            "G1": 100.0,
            "G2": 200.0,
        },
        startup_cost_yuan={"G1": 500.0, "G2": 1000.0},
        shutdown_cost_yuan={"G1": 50.0, "G2": 100.0},
    )

    model.optimize()

    assert model.get_model_attribute(
        poi.ModelAttribute.TerminationStatus
    ) == poi.TerminationStatusCode.OPTIMAL

    expected_power = {
        ("G1", 0): 80.0,
        ("G1", 1): 100.0,
        ("G2", 0): 0.0,
        ("G2", 1): 30.0,
    }

    for key, expected in expected_power.items():
        assert model.get_value(variables.power[key]) == pytest.approx(expected)

    assert model.get_value(variables.startup["G2", 1]) == pytest.approx(1.0)

    objective_value = model.get_model_attribute(
        poi.ModelAttribute.ObjectiveValue
    )
    assert objective_value == pytest.approx(25000.0)