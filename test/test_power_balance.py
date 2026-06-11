import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.optim.constraints.power_balance import (
    ZonalVariableGroup,
    add_power_balance_constraints,
)
from src.optim.variables import (
    add_thermal_variables,
    add_transmission_variables,
)


def test_single_zone_power_balance():
    model = gurobi.Model()
    thermal = add_thermal_variables(model, ["G1"], [0])

    thermal_group = ZonalVariableGroup(
        variables=thermal.power,
        resource_zones={"G1": "Z1"},
    )

    add_power_balance_constraints(
        model=model,
        zones=["Z1"],
        periods=[0],
        demand_mw={("Z1", 0): 80.0},
        supply_groups=[thermal_group],
    )

    model.set_objective(
        thermal.power["G1", 0],
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    assert model.get_value(thermal.power["G1", 0]) == pytest.approx(80.0)


def test_transmission_flow_sign_between_two_zones():
    model = gurobi.Model()

    thermal = add_thermal_variables(model, ["G1"], [0])
    transmission = add_transmission_variables(model, ["L1"], [0])

    thermal_group = ZonalVariableGroup(
        variables=thermal.power,
        resource_zones={"G1": "ZA"},
    )

    add_power_balance_constraints(
        model=model,
        zones=["ZA", "ZB"],
        periods=[0],
        demand_mw={
            ("ZA", 0): 0.0,
            ("ZB", 0): 30.0,
        },
        supply_groups=[thermal_group],
        transmission_flow=transmission.flow,
        line_from_zone={"L1": "ZA"},
        line_to_zone={"L1": "ZB"},
    )

    model.set_objective(
        thermal.power["G1", 0],
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    assert model.get_value(thermal.power["G1", 0]) == pytest.approx(30.0)
    assert model.get_value(transmission.flow["L1", 0]) == pytest.approx(30.0)


def test_fixed_external_injection_reduces_generation():
    model = gurobi.Model()
    thermal = add_thermal_variables(model, ["G1"], [0])

    thermal_group = ZonalVariableGroup(
        variables=thermal.power,
        resource_zones={"G1": "Z1"},
    )

    add_power_balance_constraints(
        model=model,
        zones=["Z1"],
        periods=[0],
        demand_mw={("Z1", 0): 50.0},
        supply_groups=[thermal_group],
        fixed_external_injection_mw={("Z1", 0): 20.0},
    )

    model.set_objective(
        thermal.power["G1", 0],
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    assert model.get_value(thermal.power["G1", 0]) == pytest.approx(30.0)


def test_storage_charging_is_counted_as_demand():
    model = gurobi.Model()
    thermal = add_thermal_variables(model, ["G1"], [0])

    storage_charge = {
        ("S1", 0): model.add_variable(
            lb=0.0,
            name="storage_charge[S1,0]",
        )
    }

    thermal_group = ZonalVariableGroup(
        variables=thermal.power,
        resource_zones={"G1": "Z1"},
    )
    storage_charge_group = ZonalVariableGroup(
        variables=storage_charge,
        resource_zones={"S1": "Z1"},
    )

    model.add_linear_constraint(
        storage_charge["S1", 0],
        poi.Eq,
        10.0,
    )

    add_power_balance_constraints(
        model=model,
        zones=["Z1"],
        periods=[0],
        demand_mw={("Z1", 0): 50.0},
        supply_groups=[thermal_group],
        demand_groups=[storage_charge_group],
    )

    model.set_objective(
        thermal.power["G1", 0],
        poi.ObjectiveSense.Minimize,
    )
    model.optimize()

    assert model.get_value(thermal.power["G1", 0]) == pytest.approx(60.0)


def test_reject_missing_demand():
    model = gurobi.Model()

    with pytest.raises(ValueError, match="缺少分区负荷参数"):
        add_power_balance_constraints(
            model=model,
            zones=["Z1"],
            periods=[0],
            demand_mw={},
        )


def test_reject_unknown_transmission_zone():
    model = gurobi.Model()
    transmission = add_transmission_variables(model, ["L1"], [0])

    with pytest.raises(ValueError, match="终点分区不存在"):
        add_power_balance_constraints(
            model=model,
            zones=["ZA"],
            periods=[0],
            demand_mw={("ZA", 0): 0.0},
            transmission_flow=transmission.flow,
            line_from_zone={"L1": "ZA"},
            line_to_zone={"L1": "UNKNOWN"},
        )