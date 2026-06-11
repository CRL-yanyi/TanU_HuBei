import datetime  # 导入 datetime，用来构造风电和光伏的分月容量字典
import pandas as pd  # 导入 pandas，用来判断 DataFrame 是否为空、处理缺失值和读取行数据
from src.model.grid import Grid  # 导入成员二定义的 Grid 对象
from src.model.zone import Zone, Basin  # 导入成员二定义的 Zone 和 Basin 对象
from src.model.intertran import Intertran  # 导入成员二定义的 Intertran 联络线对象
from src.model.resource import Thermal, Hydro, Storage, Wind, PV, Load  # 导入成员二定义的各类资源对象
def _is_empty_value(value) -> bool:
    # 定义一个工具函数，用来判断某个值是不是空值，-> bool:执行后一定返回布尔值
    return value is None or pd.isna(value) or value == ""  # 如果值是 None、NaN 或空字符串，就认为它是空值
def _first(row: dict, names: list[str], default=None):  # 定义一个工具函数，从多个候选字段名里取第一个存在的值
    for name in names:  # 遍历候选字段名列表
        if name in row and not _is_empty_value(row[name]):  # 如果字段存在并且不是空值
            return row[name]  # 返回这个字段的值
    return default  # 如果所有候选字段都不存在，就返回默认值
def _safe_float(value, default: float = 0.0) -> float:  # 定义一个工具函数，把值安全转换成 float
    if _is_empty_value(value):  # 如果值是空值
        return default  # 返回默认值
    return float(value)  # 否则把值转换成 float 并返回
def _safe_int(value, default: int = 0) -> int:  # 定义一个工具函数，把值安全转换成 int
    if _is_empty_value(value):  # 如果值是空值
        return default  # 返回默认值
    return int(value)  # 否则把值转换成 int 并返回
def _with_prefix(prefix: str, raw_id) -> str:  # 定义一个工具函数，给资源 ID 补统一前缀
    raw = str(raw_id).strip()  # 先把原始 ID 转成字符串，并去掉前后空格
    if raw.startswith(prefix):  # 如果原始 ID 已经带有这个前缀
        return raw  # 直接返回原始 ID，避免重复加前缀
    return prefix + raw  # 如果没有前缀，就补上前缀后返回
def _iter_records(df: pd.DataFrame):  # 定义一个工具函数，把 DataFrame 一行一行转成字典
    if df is None or df.empty:  # 如果 DataFrame 不存在或者为空
        return []  # 返回空列表，避免后面循环报错
    return df.to_dict(orient="records")  # 把 DataFrame 转换成由行字典组成的列表
def build_grid(case_data) -> Grid:  # 定义成员二最核心的函数：从 CaseData 构建 Grid
    grid = Grid(id=str(case_data.metadata.get("case_name", "HUBEI2030")))  # 创建 Grid 对象，优先使用 metadata 里的 case_name
    _add_zones(grid, case_data)  # 第一步：把 case_data.zones 转成 Grid 里的 Zone
    _add_basins(grid, case_data)  # 第二步：根据水电和流域数据先创建 Basin
    _add_transmissions(grid, case_data)  # 第三步：把 case_data.transmissions 转成 Intertran
    _add_thermal_units(grid, case_data)  # 第四步：把 case_data.thermal_units 转成 Thermal
    _add_hydro_units(grid, case_data)  # 第五步：把 case_data.hydro_units 转成 Hydro，并挂到 Basin 下面
    _add_storage_units(grid, case_data)  # 第六步：把 case_data.storage_units 转成 Storage
    _add_pumped_storage_units(grid, case_data)  # 第七步：把 case_data.pumped_storage_units 抽蓄资源也先转成 Storage
    _add_load_resources(grid, case_data)  # 第八步：根据 load_curves 的列创建 Load 资源
    _add_wind_resources(grid, case_data)  # 第九步：根据 wind_curves 的列创建 Wind 资源
    _add_pv_resources(grid, case_data)  # 第十步：根据 pv_curves 的列创建 PV 资源
    _attach_hydro_flows(grid, case_data)  # 第十一步：把 hydro_flows 里的流域过程挂到 Basin 上
    return grid  # 返回完整 Grid，供成员三、四、五使用
def _add_zones(grid: Grid, case_data) -> None:  # 定义添加分区的内部函数
    for row in _iter_records(case_data.zones):  # 遍历成员一提供的分区表
        zone_name = _first(row, ["zone_name", "name", "分区名称", "分区"], default=None)  # 优先读取规范字段 zone_name
        zone_id = _first(row, ["zone_id", "id", "分区ID"], default=zone_name)  # 优先读取 zone_id，如果没有就用 zone_name
        if _is_empty_value(zone_id):  # 如果分区 ID 为空
            raise ValueError("Zone id is empty in case_data.zones")  # 抛出错误，提示分区 ID 缺失
        zone = Zone(id=str(zone_id), name=str(zone_name or zone_id))  # 创建 Zone 对象
        grid.addZone(zone)  # 把 Zone 加入 Grid
def _add_basins(grid: Grid, case_data) -> None:  # 定义添加流域的内部函数
    seen = set()  # 创建集合，用来记录已经添加过的 basin，避免重复
    for row in _iter_records(case_data.hydro_units):  # 遍历水电机组表，因为水电通常带有流域信息
        zone_id = _first(row, ["zone_name", "zone_id", "所属分区"], default=None)  # 读取水电所属分区
        basin_raw = _first(row, ["basin_name", "basin_id", "river_basin", "流域"], default="UNKNOWN")  # 读取水电所属流域
        if _is_empty_value(zone_id):  # 如果水电分区为空
            continue  # 先跳过，因为后面添加 Hydro 时也会报更明确的错误
        basin_id = _with_prefix("BASIN", basin_raw)  # 给流域 ID 加 BASIN 前缀，保持旧程序风格
        key = (str(zone_id), basin_id)  # 用分区和流域 ID 组成唯一键
        if key in seen:  # 如果这个分区里的这个流域已经添加过
            continue  # 跳过，避免重复添加
        basin = Basin(id=basin_id, zoneId=str(zone_id))  # 创建 Basin 对象
        grid.addBasin(basin)  # 把 Basin 添加到对应 Zone 下
        seen.add(key)  # 记录这个 Basin 已经添加过
    for basin_name in case_data.hydro_flows.keys():  # 遍历成员一读取的流域三段式数据
        basin_id = _with_prefix("BASIN", basin_name)  # 给流域名称补 BASIN 前缀
        if any(basin_id in zone.basinDict for zone in grid.zones.values()):  # 如果这个流域已经在某个分区里存在
            continue  # 已经存在就不用重复创建
        if len(grid.zones) == 1:  # 如果系统里只有一个分区
            only_zone_id = next(iter(grid.zones.keys()))  # 取出唯一分区 ID
            grid.addBasin(Basin(id=basin_id, zoneId=only_zone_id))  # 把该流域挂到唯一分区下
def _add_transmissions(grid: Grid, case_data) -> None:  # 定义添加联络线的内部函数
    for row in _iter_records(case_data.transmissions):  # 遍历成员一提供的联络线表
        raw_id = _first(row, ["line_id", "id", "line_name", "断面名称"], default=None)  # 读取联络线 ID
        line_name = _first(row, ["line_name", "name", "断面名称"], default=raw_id)  # 读取联络线名称
        from_zone = _first(row, ["zone_from", "from_zone", "fromZone", "送端分区"], default=None)  # 读取起始分区
        to_zone = _first(row, ["zone_to", "to_zone", "toZone", "受端分区"], default=None)  # 读取终止分区
        if _is_empty_value(raw_id) or _is_empty_value(from_zone) or _is_empty_value(to_zone):  # 如果关键字段缺失
            continue  # 第一版先跳过不完整联络线，后续可以改成严格报错
        if str(from_zone) == "外部电网" or str(to_zone) == "外部电网":  # 如果一端是外部电网
            continue  # 第一版 Grid 先只建省内分区间联络线
        capacity = _safe_float(_first(row, ["capacity_mw", "capacity", "输电能力"], default=0.0))  # 读取联络线容量
        intertran = Intertran(id=_with_prefix("INTERTRAN", raw_id), fromZone=str(from_zone), toZone=str(to_zone), type="AC", capacityToZone=capacity, capacityFromZone=capacity)  # 创建 Intertran 对象
        grid.addIntertran(intertran)  # 把联络线加入 Grid
def _add_thermal_units(grid: Grid, case_data) -> None:  # 定义添加火电机组的内部函数
    for row in _iter_records(case_data.thermal_units):  # 遍历火电机组表
        raw_id = _first(row, ["unit_id", "id", "机组编码"], default=None)  # 读取火电机组 ID
        zone_id = _first(row, ["zone_name", "zone_id", "所属分区"], default=None)  # 读取火电所属分区
        if _is_empty_value(raw_id) or _is_empty_value(zone_id):  # 如果机组 ID 或分区为空
            raise ValueError(f"Thermal unit has empty unit_id or zone_name: {row}")  # 抛出错误，提示火电基础字段缺失
        p_max = _safe_float(_first(row, ["p_max_mw", "capacity_mw", "装机容量"], default=0.0))  # 读取最大出力
        p_min = _safe_float(_first(row, ["p_min_mw", "最小出力"], default=0.0))  # 读取最小出力
        thermal = Thermal(id=_with_prefix("THERMAL", raw_id), name=str(_first(row, ["unit_name", "name", "机组名称"], default=raw_id)), zoneId=str(zone_id), type="THERMAL", capacity=p_max, Pmax=p_max, Pmin=p_min)  # 创建 Thermal 对象
        thermal.rampUp = _safe_float(_first(row, ["ramp_up_mw_per_h", "rampUp", "上爬坡"], default=p_max))  # 设置上爬坡能力
        thermal.rampDown = _safe_float(_first(row, ["ramp_down_mw_per_h", "rampDown", "下爬坡"], default=p_max))  # 设置下爬坡能力
        thermal.minON = _safe_int(_first(row, ["min_on_h", "minON", "最小开机时间"], default=0))  # 设置最小开机时间
        thermal.minOFF = _safe_int(_first(row, ["min_off_h", "minOFF", "最小停机时间"], default=0))  # 设置最小停机时间
        thermal.startUpCost = _safe_float(_first(row, ["startup_cost", "startUpCost", "启动成本"], default=0.0))  # 设置启动成本
        thermal.shutDownCost = _safe_float(_first(row, ["shutdown_cost", "shutDownCost", "停机成本"], default=0.0))  # 设置停机成本
        grid.addResource(thermal)  # 把火电资源加入 Grid
def _add_hydro_units(grid: Grid, case_data) -> None:  # 定义添加水电机组的内部函数
    for row in _iter_records(case_data.hydro_units):  # 遍历水电机组表
        raw_id = _first(row, ["unit_id", "id", "机组编码"], default=None)  # 读取水电机组 ID
        zone_id = _first(row, ["zone_name", "zone_id", "所属分区"], default=None)  # 读取水电所属分区
        basin_raw = _first(row, ["basin_name", "basin_id", "river_basin", "流域"], default="UNKNOWN")  # 读取水电所属流域
        if _is_empty_value(raw_id) or _is_empty_value(zone_id):  # 如果机组 ID 或分区为空
            raise ValueError(f"Hydro unit has empty unit_id or zone_name: {row}")  # 抛出错误，提示水电基础字段缺失
        p_max = _safe_float(_first(row, ["p_max_mw", "capacity_mw", "装机容量"], default=0.0))  # 读取最大出力
        p_min = _safe_float(_first(row, ["p_min_mw", "最小出力"], default=0.0))  # 读取最小出力
        hydro = Hydro(id=_with_prefix("HYDRO", raw_id), name=str(_first(row, ["unit_name", "name", "机组名称"], default=raw_id)), zoneId=str(zone_id), type="HYDRO", capacity=p_max, Pmax=p_max, Pmin=p_min, basinId=_with_prefix("BASIN", basin_raw))  # 创建 Hydro 对象
        hydro.rampUp = _safe_float(_first(row, ["ramp_up_mw_per_h", "rampUp", "上爬坡"], default=p_max))  # 设置水电上爬坡能力
        hydro.rampDown = _safe_float(_first(row, ["ramp_down_mw_per_h", "rampDown", "下爬坡"], default=p_max))  # 设置水电下爬坡能力
        grid.addResource(hydro)  # 把水电资源加入 Grid，并自动挂到 Basin 下
def _add_storage_units(grid: Grid, case_data) -> None:  # 定义添加普通储能的内部函数
    for row in _iter_records(case_data.storage_units):  # 遍历储能机组表
        _add_one_storage(grid, row, "STORAGE")  # 调用通用储能添加函数
def _add_pumped_storage_units(grid: Grid, case_data) -> None:  # 定义添加抽水蓄能的内部函数
    for row in _iter_records(case_data.pumped_storage_units):  # 遍历抽水蓄能机组表
        _add_one_storage(grid, row, "STORAGE")  # 第一版先把抽蓄也作为 STORAGE 类型处理
def _add_one_storage(grid: Grid, row: dict, res_type: str) -> None:  # 定义添加单个储能资源的通用函数
    raw_id = _first(row, ["unit_id", "id", "机组编码"], default=None)  # 读取储能 ID
    zone_id = _first(row, ["zone_name", "zone_id", "所属分区"], default=None)  # 读取储能所属分区
    if _is_empty_value(raw_id) or _is_empty_value(zone_id):  # 如果储能 ID 或分区为空
        raise ValueError(f"Storage unit has empty unit_id or zone_name: {row}")  # 抛出错误，提示储能基础字段缺失
    p_max = _safe_float(_first(row, ["p_max_mw", "capacity_mw", "rated_power_mw", "额定功率(MW)"], default=0.0))  # 读取储能功率容量
    e_max = _safe_float(_first(row, ["e_max_mwh", "energy_capacity_mwh", "额定容量(MWh)"], default=0.0))  # 读取储能能量容量
    storage = Storage(id=_with_prefix("STORAGE", raw_id), name=str(_first(row, ["unit_name", "name", "机组名称"], default=raw_id)), zoneId=str(zone_id), type=res_type, capacity=p_max, Pmax=p_max, Pmin=0.0)  # 创建 Storage 对象
    storage.Emax = e_max  # 设置最大能量
    storage.Emin = _safe_float(_first(row, ["e_min_mwh"], default=0.0))  # 设置最小能量
    storage.E0 = _safe_float(_first(row, ["e_initial_mwh", "initial_energy_mwh"], default=0.5 * e_max))  # 设置初始能量
    storage.EnT = _safe_float(_first(row, ["e_terminal_mwh", "terminal_energy_mwh"], default=storage.E0))  # 设置末端目标能量
    storage.effC = _safe_float(_first(row, ["charge_efficiency"], default=1.0))  # 设置充电效率
    storage.effD = _safe_float(_first(row, ["discharge_efficiency"], default=1.0))  # 设置放电效率
    grid.addResource(storage)  # 把储能加入 Grid
def _add_load_resources(grid: Grid, case_data) -> None:  # 定义根据负荷曲线创建 Load 资源的函数
    for zone_id in case_data.load_curves.columns:  # 遍历负荷曲线的每一列，每列通常对应一个分区
        #if str(zone_id) not in grid.zones:  # 如果该列对应的分区不在 Grid 中
            #continue  # 第一版先跳过无法对应分区的负荷列
        if str(zone_id) not in grid.zones:  # 判断负荷曲线对应的分区是否存在于 Grid 中
            raise KeyError(f"Load curve zone {zone_id} is not in grid {grid.id}")  # 如果负荷分区不存在，就明确报错
        max_load = _safe_float(case_data.load_curves[zone_id].max(), default=0.0)  # 用负荷曲线最大值作为容量
        load = Load(id=_with_prefix("LOAD", zone_id), name=f"{zone_id}负荷", zoneId=str(zone_id), type="LOAD", capacity=max_load, Pmax=max_load, Pmin=0.0)  # 创建 Load 对象
        grid.addResource(load)  # 把负荷资源加入 Grid
def _add_wind_resources(grid: Grid, case_data) -> None:  # 定义根据风电曲线创建 Wind 资源的函数
    for zone_id in case_data.wind_curves.columns:  # 遍历风电曲线的每一列，每列通常对应一个分区
        #if str(zone_id) not in grid.zones:  # 如果该列对应的分区不在 Grid 中
            #continue  # 第一版先跳过无法对应分区的风电列
        if str(zone_id) not in grid.zones:  # 判断风电曲线对应的分区是否存在于 Grid 中
            raise KeyError(f"Wind curve zone {zone_id} is not in grid {grid.id}")  # 如果风电分区不存在，就明确报错
        wind = Wind(id=_with_prefix("WIND", zone_id), name=f"{zone_id}风电", zoneId=str(zone_id), type="WIND", capacity=1.0, Pmax=1.0, Pmin=0.0)  # 创建 Wind 对象，容量先用 1.0 表示时序标幺
        grid.addResource(wind)  # 把风电资源加入 Grid
def _add_pv_resources(grid: Grid, case_data) -> None:  # 定义根据光伏曲线创建 PV 资源的函数
    for zone_id in case_data.pv_curves.columns:  # 遍历光伏曲线的每一列，每列通常对应一个分区
        #if str(zone_id) not in grid.zones:  # 如果该列对应的分区不在 Grid 中
            #continue  # 第一版先跳过无法对应分区的光伏列
        if str(zone_id) not in grid.zones:  # 判断光伏曲线对应的分区是否存在于 Grid 中
            raise KeyError(f"PV curve zone {zone_id} is not in grid {grid.id}")  # 如果光伏分区不存在，就明确报错
        pv = PV(id=_with_prefix("PV", zone_id), name=f"{zone_id}光伏", zoneId=str(zone_id), type="PV", capacity=1.0, Pmax=1.0, Pmin=0.0)  # 创建 PV 对象，容量先用 1.0 表示时序标幺
        grid.addResource(pv)  # 把光伏资源加入 Grid
def _attach_hydro_flows(grid: Grid, case_data) -> None:  # 定义把流域三段式数据挂到 Basin 的函数
    for basin_name, flow_df in case_data.hydro_flows.items():  # 遍历成员一读取的 hydro_flows 字典
        basin_id = _with_prefix("BASIN", basin_name)  # 把流域名称转换成 Basin ID
        basin = None  # 先准备一个空变量，用来保存找到的 Basin
        for zone in grid.zones.values():  # 遍历 Grid 中所有分区
            if basin_id in zone.basinDict:  # 如果该分区里有这个 Basin
                basin = zone.basinDict[basin_id]  # 取出这个 Basin
                break  # 找到后退出循环
        if basin is None:  # 如果所有分区都找不到这个 Basin
            continue  # 第一版先跳过，后续可以改成警告或报错
        if "平均" in flow_df.index:  # 如果三段式表里有平均过程
            basin.average = flow_df.loc["平均"].to_dict()  # 把平均过程转成字典存入 Basin
        if "强迫" in flow_df.index:  # 如果三段式表里有强迫过程
            basin.forced = flow_df.loc["强迫"].to_dict()  # 把强迫过程转成字典存入 Basin
        if "预想" in flow_df.index:  # 如果三段式表里有预想过程
            basin.predicted = flow_df.loc["预想"].to_dict()  # 把预想过程转成字典存入 Basin
