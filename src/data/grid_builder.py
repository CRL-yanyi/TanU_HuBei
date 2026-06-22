
from __future__ import annotations

import warnings
from typing import Any

import pandas as pd

from src.model.grid import Grid
from src.model.intertran import Intertran
from src.model.resource import Hydro, Load, PV, Storage, Thermal, Wind
from src.model.zone import Basin, Zone


# 成员一断面表中，如果一端是“外部电网”，说明它不是省内分区之间的普通联络线。
EXTERNAL_GRID_NAME = "外部电网"


# =============================================================================
# 一、通用工具函数
# =============================================================================

def _is_empty_value(value: Any) -> bool:
    """
    判断某个值是否为空。
    为什么需要统一判断：
        Excel 和 pandas 读出来的空值形式不完全一样；
        如果不统一处理，后面可能把空字段误当成合法字段。
    """
    if value is None:
        return True

    if isinstance(value, str):
        return value.strip() == ""

    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        # 如果 pd.isna 不能处理这个对象，就认为它不是空值。
        return False
def _iter_records(df: pd.DataFrame | None) -> list[dict[str, Any]]:
    """
    把 DataFrame 转成“按行读取”的字典列表。
    """
    if df is None or df.empty:
        return []
    return df.to_dict(orient="records")
def _get(row: dict[str, Any], name: str, default: Any = None) -> Any:

  #  从一行数据中读取可选字段。

    if name in row and not _is_empty_value(row[name]):
        return row[name]

    return default
def _require(row: dict[str, Any], name: str, table: str) -> Any:
    #读取必需字段。 如果字段不存在或为空，直接抛 ValueError。
    value = _get(row, name, default=None)

    if _is_empty_value(value):
        raise ValueError(
            f"Missing required field '{name}' in table '{table}'. "
            f"Please check member-1 loader/YAML field mapping. Row: {row}"
        )

    return value


def _require_float(row: dict[str, Any], name: str, table: str) -> float:

    #读取必需数值字段，并转换为 float。
    value = _require(row, name, table)

    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Field '{name}' in table '{table}' must be numeric, got {value!r}. Row: {row}"
        ) from exc


def _optional_float(row: dict[str, Any], name: str, default: float = 0.0) -> float:
    #读取可选数值字段。
    value = _get(row, name, default=None)

    if _is_empty_value(value):
        return default

    return float(value)
def _optional_int(row: dict[str, Any], name: str, default: int = 0) -> int:
    #读取可选整数字段。
    value = _get(row, name, default=None)

    if _is_empty_value(value):
        return default

    return int(value)


def _with_prefix(prefix: str, raw_id: Any) -> str:
    """
    给对象 ID 补统一前缀。
    例如：raw_id="001", prefix="THERMAL" -> "THERMAL001"
    这样可以避免不同资源类型之间 ID 冲突。
    """
    raw = str(raw_id).strip()

    if raw.startswith(prefix):
        return raw

    return f"{prefix}{raw}"


def _resource_name(row: dict[str, Any], raw_id: Any) -> str:
#读取资源名称。
    return str(_get(row, "plant_name", default=raw_id))


def _require_zone_exists(grid: Grid, zone_id: str, source: str) -> None:
    """
    检查分区是否已经存在于 Grid 中。
    """
    if zone_id not in grid.zones:
        raise KeyError(f"{source} references zone '{zone_id}', but it is not in grid '{grid.id}'.")


# =============================================================================
# 二、主入口：CaseData -> Grid
# =============================================================================

def build_grid(case_data) -> Grid:
    """
    从成员一的 CaseData 构建完整 Grid。
    """
    metadata = getattr(case_data, "metadata", {}) or {}#内置函数 getattr(对象, 属性名, 默认值)：
    grid_id = str(metadata.get("case_name", "HUBEI2030"))#从元数据字典 metadata 读取键 case_name（算例名称）；该键值为空，默认兜底字符串：HUBEI2030
    grid = Grid(id=grid_id)## 初始化电网
    _add_zones(grid, case_data)
    _add_basins(grid, case_data)#依次加载各类
    _add_transmissions(grid, case_data)
    _add_thermal_units(grid, case_data)
    _add_hydro_units(grid, case_data)
    _add_storage_units(grid, case_data)
    _add_pumped_storage_units(grid, case_data)
    _add_load_resources(grid, case_data)
    _add_wind_resources(grid, case_data)
    _add_pv_resources(grid, case_data)
    _attach_hydro_flows(grid, case_data)

    return grid
# =============================================================================
# 三、分区对象
# =============================================================================

def _add_zones(grid: Grid, case_data) -> None:
    #根据 case_data.zones 创建 Zone 对象。
    for row in _iter_records(case_data.zones):
        zone_name = str(_require(row, "zone_name", "zones"))

        zone = Zone(
            id=zone_name,
            name=zone_name,
        )

        grid.addZone(zone)


# =============================================================================
# 四、流域对象
# =============================================================================

def _add_basins(grid: Grid, case_data) -> None:
  #根据 case_data.hydro_units 中的 basin_name 创建 Basin 对象。
    seen: set[tuple[str, str]] = set()

    for row in _iter_records(case_data.hydro_units):
        zone_name = str(_require(row, "zone_name", "hydro_units"))
        basin_name = str(_require(row, "basin_name", "hydro_units"))
        basin_id = _with_prefix("BASIN", basin_name)

        # 同一个分区下同一个流域只创建一次。
        key = (zone_name, basin_id)
        if key in seen:
            continue

        basin = Basin(
            id=basin_id,
            zoneId=zone_name,
        )

        grid.addBasin(basin)
        seen.add(key)


# =============================================================================
# 五、联络线 / 断面对象
# =============================================================================

def _add_transmissions(grid: Grid, case_data) -> None:

    #根据 case_data.transmissions 创建 Intertran 对象。
    for row in _iter_records(case_data.transmissions):
        line_name = str(_require(row, "line_name", "transmissions"))
        from_zone = str(_require(row, "zone_from", "transmissions"))
        to_zone = str(_require(row, "zone_to", "transmissions"))

        # 外部电网不作为省内普通联络线建模。
        if from_zone == EXTERNAL_GRID_NAME or to_zone == EXTERNAL_GRID_NAME:
            warnings.warn(
                f"Skip external transmission '{line_name}': {from_zone} -> {to_zone}. "
                "It should be handled through case_data.dc_flows in power balance.",
                UserWarning,
                stacklevel=2,
            )
            continue

        limit_mw = _require_float(row, "limit_mw", "transmissions")
        # 成员一输出 line_type，但具体值不一定就是 AC/DC。
        raw_line_type = str(_get(row, "line_type", default="AC")).upper()
        intertran_type = raw_line_type if raw_line_type in {"AC", "DC"} else "AC"

        intertran = Intertran(
            id=_with_prefix("INTERTRAN", line_name),
            fromZone=from_zone,
            toZone=to_zone,
            type=intertran_type,
            capacityToZone=limit_mw,
            capacityFromZone=limit_mw,
        )


        intertran.controlType = _get(row, "control_type", default="")
        intertran.rawLineType = raw_line_type

        grid.addIntertran(intertran)


# =============================================================================
# 六、火电资源对象
# =============================================================================

def _add_thermal_units(grid: Grid, case_data) -> None:
    #根据 case_data.thermal_units 创建 Thermal 对象。
    for row in _iter_records(case_data.thermal_units):
        unit_id = _require(row, "unit_id", "thermal_units")
        zone_name = str(_require(row, "zone_name", "thermal_units"))

        p_max = _require_float(row, "p_max_mw", "thermal_units")
        p_min = _optional_float(row, "p_min_mw", default=0.0)

        thermal = Thermal(
            id=_with_prefix("THERMAL", unit_id),
            name=_resource_name(row, unit_id),
            zoneId=zone_name,
            type="THERMAL",
            capacity=p_max,
            Pmax=p_max,
            Pmin=p_min,
        )

        # 成员一字段是 ramp_rate_mw_per_min，单位 MW/min。
        # 你 Resource.Thermal 注释中的 rampUp/rampDown 是 MW/h。
        # 因此这里做对象层单位适配：MW/min * 60 = MW/h。
        ramp_rate_mw_per_min = _optional_float(row, "ramp_rate_mw_per_min", default=p_max / 60.0)
        thermal.rampUp = ramp_rate_mw_per_min * 60.0
        thermal.rampDown = ramp_rate_mw_per_min * 60.0

        thermal.minON = _optional_int(row, "min_up_time_h", default=0)
        thermal.minOFF = _optional_int(row, "min_down_time_h", default=0)

        # 从 Excel 中读取启停费用 (万元)，折算为元
        startup_shutdown_cost_10k = _optional_float(row, "startup_shutdown_cost_10k", default=0.0)
        thermal.startUpCost = startup_shutdown_cost_10k * 10000.0
        thermal.shutDownCost = 0.0
        # 火电变动成本，单位 元/MWh。
        thermal.variableCost = _optional_float(row, "vom_cost_per_mwh", default=0.0)

        # 保存一些成员一已经输出、后续可能有用的附加字段。
        thermal.plantName = _get(row, "plant_name", default="")
        thermal.busName = _get(row, "bus_name", default="")
        thermal.voltageKv = _optional_float(row, "voltage_kv", default=0.0)
        thermal.commissionDate = _get(row, "commission_date", default=None)
        thermal.retirementDate = _get(row, "retirement_date", default=None)
        thermal.fuelCostPerKwh = _optional_float(row, "fuel_cost_per_kwh", default=0.0)
        thermal.fuelCostPerMwh = _optional_float(row, "fuel_cost_per_mwh", default=0.0)

        grid.addResource(thermal)


# =============================================================================
# 七、水电资源对象
# =============================================================================

def _add_hydro_units(grid: Grid, case_data) -> None:
    #根据 case_data.hydro_units 创建 Hydro 对象。
    for row in _iter_records(case_data.hydro_units):
        unit_id = _require(row, "unit_id", "hydro_units")
        zone_name = str(_require(row, "zone_name", "hydro_units"))
        basin_name = str(_require(row, "basin_name", "hydro_units"))

        p_max = _require_float(row, "p_max_mw", "hydro_units")
        p_min = _optional_float(row, "p_min_mw", default=0.0)

        hydro = Hydro(
            id=_with_prefix("HYDRO", unit_id),
            name=_resource_name(row, unit_id),
            zoneId=zone_name,
            type="HYDRO",
            capacity=p_max,
            Pmax=p_max,
            Pmin=p_min,
            basinId=_with_prefix("BASIN", basin_name),
        )

        # 成员一 YAML 当前没有水电爬坡字段。
        # 第一版先默认水电每小时可从 0 到满发。
        hydro.rampUp = p_max
        hydro.rampDown = p_max

        # 保存成员一输出的附加字段。
        hydro.plantName = _get(row, "plant_name", default="")
        hydro.busName = _get(row, "bus_name", default="")

        grid.addResource(hydro)


# =============================================================================
# 八、普通储能和抽水蓄能资源对象
# =============================================================================

def _add_storage_units(grid: Grid, case_data) -> None:
    #添加储能。
    for row in _iter_records(case_data.storage_units):
        _add_one_storage(
            grid=grid,
            row=row,
            table="storage_units",
            subtype="BATTERY_STORAGE",
        )


def _add_pumped_storage_units(grid: Grid, case_data) -> None:
    """
    添加抽水蓄能。
    """
    for row in _iter_records(case_data.pumped_storage_units):
        _add_one_storage(
            grid=grid,
            row=row,
            table="pumped_storage_units",
            subtype="PUMPED_STORAGE",
        )


def _add_one_storage(grid: Grid, row: dict[str, Any], table: str, subtype: str) -> None:
    """
    添加单个普通储能或抽蓄资源。
    """
    unit_id = _require(row, "unit_id", table)
    zone_name = str(_require(row, "zone_name", table))

    p_max = _require_float(row, "p_max_mw", table)
    energy_capacity_mwh = _require_float(row, "energy_capacity_mwh", table)
    init_soc_percent = _require_float(row, "init_soc", table)

    storage = Storage(
        id=_with_prefix("STORAGE", unit_id),
        name=_resource_name(row, unit_id),
        zoneId=zone_name,
        type="STORAGE",
        capacity=p_max,
        Pmax=p_max,
        Pmin=0.0,
    )

    storage.subtype = subtype
    storage.Emax = energy_capacity_mwh
    storage.Emin = 0.0
    storage.E0 = init_soc_percent / 100.0 * energy_capacity_mwh
    storage.EnT = storage.E0

    # 成员一 loader 已经把效率从百分数转成 0~1 标幺值。
    storage.effC = _require_float(row, "charge_efficiency", table)
    storage.effD = _require_float(row, "discharge_efficiency", table)

    # 保存成员一输出的附加字段。
    storage.plantName = _get(row, "plant_name", default="")
    storage.busName = _get(row, "bus_name", default="")
    storage.initSocPercent = init_soc_percent

    grid.addResource(storage)


# =============================================================================
# 九、负荷、风电、光伏时序资源对象
# =============================================================================

def _add_load_resources(grid: Grid, case_data) -> None:
    """
    根据 case_data.load_curves 的列名创建 Load 对象。
    """
    if case_data.load_curves is None or case_data.load_curves.empty:
        return

    for zone_name in case_data.load_curves.columns:
        zone_name = str(zone_name)
        _require_zone_exists(grid, zone_name, "load_curves")

        # 从 load_spec 中获取真实的物理峰值负荷
        peak_load = 1.0
        if hasattr(case_data, "load_spec") and case_data.load_spec is not None and not case_data.load_spec.empty:
            row = case_data.load_spec[case_data.load_spec['分区名称'] == zone_name]
            if not row.empty:
                peak_load = float(row.iloc[0]['年最大负荷（MW）'])

        load = Load(
            id=_with_prefix("LOAD", zone_name),
            name=f"{zone_name}负荷",
            zoneId=zone_name,
            type="LOAD",
            capacity=peak_load,
            Pmax=peak_load,
            Pmin=0.0,
        )

        grid.addResource(load)


def _add_wind_resources(grid: Grid, case_data) -> None:
    """
    根据 case_data.wind_curves 的列名创建 Wind 对象。
    当前成员一 wind_curves 是分区时序曲线。
    """
    if case_data.wind_curves is None or case_data.wind_curves.empty:
        return

    for zone_name in case_data.wind_curves.columns:
        zone_name = str(zone_name)
        _require_zone_exists(grid, zone_name, "wind_curves")

        # 读取月度装机规格 (包括增建容量)
        monthly_caps = {}
        if hasattr(case_data, "wind_spec") and case_data.wind_spec is not None and not case_data.wind_spec.empty:
            row = case_data.wind_spec[case_data.wind_spec['分区名称'] == zone_name]
            if not row.empty:
                for m in range(1, 13):
                    val = float(row.iloc[0][f"{m}月末"])
                    added = float(row.iloc[0].get("增建容量", 0.0))
                    if pd.isna(added):
                        added = 0.0
                    monthly_caps[m] = val + added

        wind = Wind(
            id=_with_prefix("WIND", zone_name),
            name=f"{zone_name}风电",
            zoneId=zone_name,
            type="WIND",
            capacity=1.0,
            Pmax=1.0,
            Pmin=0.0,
        )
        wind.monthly_capacities = monthly_caps

        grid.addResource(wind)


def _add_pv_resources(grid: Grid, case_data) -> None:
    """
    根据 case_data.pv_curves 的列名创建 PV 对象。
    """
    if case_data.pv_curves is None or case_data.pv_curves.empty:
        return

    for zone_name in case_data.pv_curves.columns:
        zone_name = str(zone_name)
        _require_zone_exists(grid, zone_name, "pv_curves")

        # 读取月度装机规格 (包括增建容量)
        monthly_caps = {}
        if hasattr(case_data, "pv_spec") and case_data.pv_spec is not None and not case_data.pv_spec.empty:
            row = case_data.pv_spec[case_data.pv_spec['分区名称'] == zone_name]
            if not row.empty:
                for m in range(1, 13):
                    val = float(row.iloc[0][f"{m}月末"])
                    added = float(row.iloc[0].get("增建容量", 0.0))
                    if pd.isna(added):
                        added = 0.0
                    monthly_caps[m] = val + added

        pv = PV(
            id=_with_prefix("PV", zone_name),
            name=f"{zone_name}光伏",
            zoneId=zone_name,
            type="PV",
            capacity=1.0,
            Pmax=1.0,
            Pmin=0.0,
        )
        pv.monthly_capacities = monthly_caps

        grid.addResource(pv)


# =============================================================================
# 十、流域三段式数据挂接
# =============================================================================

def _attach_hydro_flows(grid: Grid, case_data) -> None:
    """
  1. 从 case_data.hydro_flows 里拿到每个流域的水电过程表；
2. 根据流域名找到 Grid 中对应的 Basin 对象；
3. 把“平均 / 强迫 / 预想”三行数据分别存到 basin.average / basin.forced / basin.predicted。
    """
    hydro_flows = getattr(case_data, "hydro_flows", {}) or {}

    for basin_name, flow_df in hydro_flows.items():
        basin_id = _with_prefix("BASIN", basin_name)
        basin = _find_basin(grid, basin_id)

        if basin is None:
            warnings.warn(
                f"Hydro flow basin '{basin_id}' has no matching Basin object in Grid; skipped.",
                UserWarning,
                stacklevel=2,
            )
            continue

        if "平均" in flow_df.index:
            basin.average = flow_df.loc["平均"].to_dict()

        if "强迫" in flow_df.index:
            basin.forced = flow_df.loc["强迫"].to_dict()

        if "预想" in flow_df.index:
            basin.predicted = flow_df.loc["预想"].to_dict()


def _find_basin(grid: Grid, basin_id: str) -> Basin | None:
    """
    在 Grid 的所有 Zone 中查找 Basin。

    Basin 被存放在：
        grid.zones[zone_id].basinDict
    """
    # 尝试直接查找
    for zone in grid.zones.values():
        if basin_id in zone.basinDict:
            return zone.basinDict[basin_id]

    # 尝试容错带 '鄂' 前缀的流域名称
    alt_basin_id = basin_id.replace("BASIN", "BASIN鄂")
    for zone in grid.zones.values():
        if alt_basin_id in zone.basinDict:
            return zone.basinDict[alt_basin_id]

    return None
