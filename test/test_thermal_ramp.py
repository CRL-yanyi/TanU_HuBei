import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.constraints.thermal import add_thermal_uc_constraints
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
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    unit = Thermal(
        id="G1",
        zoneId="Z1",
        type="THERMAL",
        Pmin=0.0,
        Pmax=100.0,
        rampUp=ramp_up,
        rampDown=ramp_down,
        minON=0,
        minOFF=0,
    )
    unit.startUpCapacity = startup_ramp
    unit.shutDownCapacity = shutdown_ramp
    grid.addResource(unit)

    variables = add_thermal_variables(model, ["G1"], periods)
    add_thermal_uc_constraints(
        model=model,
        grid=grid,
        variables=variables,
        periods=periods,
        initial_on={"G1": initial_on},
        initial_power_mw={"G1": initial_power},
    )

    return model, variables


def test_normal_ramp_up_limit():
    model, variables = build_ramp_model([0], initial_on=1, initial_power=50.0)

    model.add_linear_constraint(variables.is_on["G1", 0], poi.Eq, 1)
    model.set_objective(-variables.power["G1", 0], poi.ObjectiveSense.Minimize)
    model.optimize()

    assert model.get_value(variables.power["G1", 0]) == pytest.approx(70.0)


def test_normal_ramp_down_limit():
    model, variables = build_ramp_model([0], initial_on=1, initial_power=50.0)

    model.add_linear_constraint(variables.is_on["G1", 0], poi.Eq, 1)
    model.set_objective(variables.power["G1", 0], poi.ObjectiveSense.Minimize)
    model.optimize()

    assert model.get_value(variables.power["G1", 0]) == pytest.approx(30.0)


def test_startup_ramp_limit():
    model, variables = build_ramp_model(
        [0],
        initial_on=0,
        initial_power=0.0,
        startup_ramp=40.0,
    )

    model.add_linear_constraint(variables.is_on["G1", 0], poi.Eq, 1)
    model.set_objective(-variables.power["G1", 0], poi.ObjectiveSense.Minimize)
    model.optimize()

    assert model.get_value(variables.power["G1", 0]) == pytest.approx(40.0)
    assert model.get_value(variables.startup["G1", 0]) == pytest.approx(1.0)


def test_shutdown_ramp_allows_shutdown():
    model, variables = build_ramp_model(
        [0],
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
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    grid.addResource(Thermal(id="G1", zoneId="Z1", type="THERMAL", Pmax=100.0))
    variables = add_thermal_variables(model, ["G1"], [0])

    with pytest.raises(ValueError, match="Initial power must be 0"):
        add_thermal_uc_constraints(
            model=model,
            grid=grid,
            variables=variables,
            periods=[0],
            initial_on={"G1": 0},
            initial_power_mw={"G1": 10.0},
        )
