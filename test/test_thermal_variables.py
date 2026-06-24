import pandas as pd
import pytest

from src.model.grid import Grid
from src.model.resource import Thermal
from src.model.zone import Zone
from src.optim.opt_model import OptModel
from src.optim.variables import add_thermal_variables


def make_periods(count=3):
    return pd.date_range("2026-01-01 00:00", periods=count, freq="h")


def make_grid(unit_ids=("G1", "G2")):
    grid = Grid(id="TEST")
    grid.addZone(Zone(id="Z1"))
    for unit_id in unit_ids:
        grid.addResource(Thermal(id=unit_id, zoneId="Z1", type="THERMAL"))
    return grid


def test_add_thermal_variables_with_datetime_index():
    opt_model = OptModel()
    periods = make_periods()
    grid = make_grid()

    add_thermal_variables(opt_model, grid, periods)

    expected_keys = {
        ("G1", periods[0]),
        ("G1", periods[1]),
        ("G1", periods[2]),
        ("G2", periods[0]),
        ("G2", periods[1]),
        ("G2", periods[2]),
    }

    assert set(opt_model.vars["thermal_power"].keys()) == expected_keys
    assert set(opt_model.vars["thermal_is_on"].keys()) == expected_keys
    assert set(opt_model.vars["thermal_startup"].keys()) == expected_keys
    assert set(opt_model.vars["thermal_shutdown"].keys()) == expected_keys


def test_reject_duplicate_periods():
    opt_model = OptModel()
    t0 = pd.Timestamp("2026-01-01 00:00")
    grid = make_grid(("G1",))

    with pytest.raises(ValueError, match="时间索引"):
        add_thermal_variables(
            opt_model=opt_model,
            grid=grid,
            periods=[t0, t0],
        )
