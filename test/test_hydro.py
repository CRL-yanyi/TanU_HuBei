# -*- coding: utf-8 -*-
import pyoptinterface as poi
import pytest
from pyoptinterface import gurobi

from src.model.grid import Grid
from src.model.zone import Zone, Basin
from src.model.resource import Hydro
from src.optim.variables import add_hydro_variables
from src.optim.constraints.hydro import add_hydro_constraints

def test_hydro_capacity_limits():
    grid = Grid(id="TEST_GRID")
    zone = Zone(id="Z1")
    grid.addZone(zone)
    
    basin = Basin(id="BASINB1", zoneId="Z1")
    grid.addBasin(basin)
    
    hydro = Hydro(
        id="HYDROH1",
        zoneId="Z1",
        type="HYDRO",
        capacity=100.0,
        Pmax=100.0,
        Pmin=10.0,
        basinId="BASINB1",
    )
    grid.addResource(hydro)
    
    model = gurobi.Model()
    vars = add_hydro_variables(model, ["HYDROH1"], [0, 1])
    add_hydro_constraints(model, grid, vars, [0, 1])
    
    # 参考项目只使用非负变量和 Pmax，不设置单机 Pmin 硬约束。
    model.set_objective(vars.power["HYDROH1", 0] + vars.power["HYDROH1", 1], poi.ObjectiveSense.Minimize)
    model.optimize()
    assert model.get_value(vars.power["HYDROH1", 0]) == pytest.approx(0.0)
    assert model.get_value(vars.power["HYDROH1", 1]) == pytest.approx(0.0)
    
    # Maximize power output -> should hit Pmax
    model.set_objective(vars.power["HYDROH1", 0] + vars.power["HYDROH1", 1], poi.ObjectiveSense.Maximize)
    model.optimize()
    assert model.get_value(vars.power["HYDROH1", 0]) == pytest.approx(100.0)
    assert model.get_value(vars.power["HYDROH1", 1]) == pytest.approx(100.0)

def test_hydro_basin_bounds():
    grid = Grid(id="TEST_GRID")
    zone = Zone(id="Z1")
    grid.addZone(zone)
    
    basin = Basin(
        id="BASINB1",
        zoneId="Z1",
        capacity=0.0,
        predicted={1: 0.8}, # 0.8 * 200 = 160 MW upper limit
        forced={1: 0.3},    # 0.3 * 200 = 60 MW lower limit
    )
    grid.addBasin(basin)
    
    h1 = Hydro(id="HYDROH1", zoneId="Z1", type="HYDRO", capacity=100.0, Pmax=150.0, Pmin=0.0, basinId="BASINB1")
    h2 = Hydro(id="HYDROH2", zoneId="Z1", type="HYDRO", capacity=100.0, Pmax=150.0, Pmin=0.0, basinId="BASINB1")
    
    grid.addResource(h1)
    grid.addResource(h2)
    
    # hour 0 is in Jan -> Month = 1
    periods = [0]
    
    model = gurobi.Model()
    vars = add_hydro_variables(model, ["HYDROH1", "HYDROH2"], periods)
    add_hydro_constraints(model, grid, vars, periods)
    
    # Maximize total output -> should hit predicted bound of 160.0 (instead of 300.0 sum of Pmax)
    model.set_objective(vars.power["HYDROH1", 0] + vars.power["HYDROH2", 0], poi.ObjectiveSense.Maximize)
    model.optimize()
    total_power = model.get_value(vars.power["HYDROH1", 0]) + model.get_value(vars.power["HYDROH2", 0])
    assert total_power == pytest.approx(160.0)
    
    # Minimize total output -> should hit forced bound of 60.0 (instead of 0.0 sum of Pmin)
    model.set_objective(vars.power["HYDROH1", 0] + vars.power["HYDROH2", 0], poi.ObjectiveSense.Minimize)
    model.optimize()
    total_power = model.get_value(vars.power["HYDROH1", 0]) + model.get_value(vars.power["HYDROH2", 0])
    assert total_power == pytest.approx(60.0)

def test_hydro_basin_average_energy():
    grid = Grid(id="TEST_GRID")
    zone = Zone(id="Z1")
    grid.addZone(zone)
    
    basin = Basin(
        id="BASINB1",
        zoneId="Z1",
        capacity=0.0,
        average={1: 0.5}, # average power factor = 0.5 -> average power = 50 MW
    )
    grid.addBasin(basin)
    
    h1 = Hydro(id="HYDROH1", zoneId="Z1", type="HYDRO", capacity=100.0, Pmax=100.0, Pmin=0.0, basinId="BASINB1")
    grid.addResource(h1)
    
    periods = [0, 1, 2, 3] # 4 hours in Jan
    
    model = gurobi.Model()
    vars = add_hydro_variables(model, ["HYDROH1"], periods)
    add_hydro_constraints(model, grid, vars, periods)
    
    # Total energy must be strictly equal to: 4 * 0.5 * 100 = 200 MWh
    model.set_objective(vars.power["HYDROH1", 0], poi.ObjectiveSense.Minimize)
    model.optimize()
    
    total_energy = sum(model.get_value(vars.power["HYDROH1", t]) for t in periods)
    assert total_energy == pytest.approx(200.0)
