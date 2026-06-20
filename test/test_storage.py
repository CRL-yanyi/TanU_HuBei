# -*- coding: utf-8 -*-
import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.model.grid import Grid
from src.model.zone import Zone
from src.model.resource import Storage
from src.optim.variables import add_storage_variables
from src.optim.constraints.storage import add_storage_constraints

def test_storage_charge_discharge_limits_and_efficiency():
    grid = Grid(id="TEST_GRID")
    zone = Zone(id="Z1")
    grid.addZone(zone)
    
    storage = Storage(
        id="STORAGES1",
        zoneId="Z1",
        type="STORAGE",
        capacity=50.0,
        Pmax=50.0,
        Emax=100.0,
        Emin=0.0,
        E0=50.0,
        effC=0.9,
        effD=0.9,
    )
    grid.addResource(storage)
    
    periods = [0, 1]
    
    model = gurobi.Model()
    vars = add_storage_variables(model, ["STORAGES1"], periods, relax_binary=False)
    add_storage_constraints(model, grid, vars, periods)
    
    # Minimize charging, maximize discharging to get energy out
    # Since E_end = E0 + C0 * effC - D0 / effD + C1 * effC - D1 / effD = E0
    # To maximize D0:
    # D0 is limited by:
    # 1. Pmax = 50.0
    # 2. Available energy at t=0: E0 = 50.0 -> D0 / effD <= E0 -> D0 <= 50.0 * 0.9 = 45.0.
    # 3. Re-charging capability at t=1: C1 is limited by Pmax (50.0). 
    #    To restore energy: C1 * effC = D0 / effD -> D0 = C1 * effC * effD = 50.0 * 0.9 * 0.9 = 40.5.
    # So max D0 is 40.5.
    model.set_objective(vars.discharge_power["STORAGES1", 0], poi.ObjectiveSense.Maximize)
    model.optimize()
    
    d0 = model.get_value(vars.discharge_power["STORAGES1", 0])
    c1 = model.get_value(vars.charge_power["STORAGES1", 1])
    
    assert d0 == pytest.approx(40.5)
    assert c1 == pytest.approx(50.0)

def test_storage_simultaneous_charge_discharge_exclusion():
    grid = Grid(id="TEST_GRID")
    zone = Zone(id="Z1")
    grid.addZone(zone)
    
    storage = Storage(
        id="STORAGES1",
        zoneId="Z1",
        type="STORAGE",
        capacity=50.0,
        Pmax=50.0,
        Emax=100.0,
        Emin=0.0,
        E0=50.0,
        effC=0.9,
        effD=0.9,
    )
    grid.addResource(storage)
    
    periods = [0]
    
    model = gurobi.Model()
    vars = add_storage_variables(model, ["STORAGES1"], periods, relax_binary=False)
    add_storage_constraints(model, grid, vars, periods)
    
    c_var = vars.charge_power["STORAGES1", 0]
    d_var = vars.discharge_power["STORAGES1", 0]
    
    # Force both charge and discharge to be >= 10.0 MW
    model.add_linear_constraint(c_var, poi.Geq, 10.0)
    model.add_linear_constraint(d_var, poi.Geq, 10.0)
    
    model.optimize()
    # Should be infeasible because they cannot charge and discharge simultaneously
    status = model.get_model_attribute(poi.ModelAttribute.TerminationStatus)
    assert status in [poi.TerminationStatusCode.INFEASIBLE, poi.TerminationStatusCode.INFEASIBLE_OR_UNBOUNDED]
