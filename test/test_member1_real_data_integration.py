# -*- coding: utf-8 -*-

import os

import pytest

from src.data.config import TimeConfig
from src.data.loader import load_case, validate_case_data
from src.data.grid_builder import build_grid


def find_case_config_path():

    # 1. 优先从环境变量中读取配置文件路径。
    env_path = os.getenv("HUBEI_CASE_CONFIG")
    # 读取操作系统环境变量
    # 如果环境变量存在，并且对应路径确实存在，就直接返回绝对路径。
    if env_path and os.path.exists(env_path):
        return os.path.abspath(env_path)

    # 2. 获取当前测试文件的绝对路径。
    # __file__ 表示当前 Python 文件的位置。
    current_file = os.path.abspath(__file__)

    # 获取当前测试文件所在目录。
    current_dir = os.path.dirname(current_file)

    # 3. 从当前目录开始，逐级向上查找项目根目录。
    while True:
        # 假设 current_dir 是项目根目录，
        # 那么配置文件应该位于：
        # current_dir/configs/cases/hubei2030.yaml
        candidate = os.path.join(
            current_dir,
            "configs",
            "cases",
            "hubei2030.yaml",
        )

        # 如果候选路径存在，说明找到了配置文件。
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
        # 获取上一级目录。
        parent_dir = os.path.dirname(current_dir)
        # 如果上一级目录和当前目录相同，
        # 说明已经到达文件系统根目录，不能再继续向上查找。
        if parent_dir == current_dir:
            break
        # 继续向上一级目录查找。
        current_dir = parent_dir

    # 4. 如果所有目录都没有找到配置文件，就主动报错。
    raise FileNotFoundError(
        "未找到成员一真实数据配置文件。"
        "请确认项目根目录下存在 configs/cases/hubei2030.yaml，"
        "或设置环境变量 HUBEI_CASE_CONFIG。"
    )


@pytest.fixture(scope="module")
def real_case_data_24h():
    """
    真实数据对接测试：调用成员一 load_case。

    这里只取前 24 小时数据，避免测试时间太长，
    同时也能证明成员一 CaseData 到成员二 Grid 的数据链路已经打通。
    """

    # 自动查找真实数据配置文件路径。
    config_path = find_case_config_path()

    # 调用成员一的数据加载接口，返回 CaseData。# 加载算例数据：指定配置文件路径、截取0-23时共24小时时序、使用0号基准场景
    return load_case(
        config_path,
        time_config=TimeConfig(start_hour=0, end_hour=23),
        scenario=0,
    )


@pytest.fixture(scope="module")# # module作用域：整个测试文件仅加载一次算例
def real_grid_24h(real_case_data_24h):

    # 调用成员二的核心接口 build_grid。
    return build_grid(real_case_data_24h)


@pytest.mark.integration
def test_member1_real_data_validation_passes(real_case_data_24h):
    """
    测试成员一真实 CaseData 是否通过数据校验。
    只有 CaseData 校验通过，后面才应该进入成员二 build_grid。
    """

    # 调用成员一的数据校验函数。
    report = validate_case_data(real_case_data_24h)

    # 如果校验不通过，就输出详细错误信息，方便定位问题。
    assert report.is_valid, (
        "真实 CaseData 校验未通过，不能进入build_grid。\n"
        f"errors={report.errors}\n"
        f"warnings={report.warnings}\n"
        f"summary={report.summary}"
    )


@pytest.mark.integration
def test_member1_case_data_time_series_are_24h(real_case_data_24h):
    """
    测试成员一返回的时序数据是否正确切片为 24 小时。
    因为 real_case_data_24h 中设置了：
        TimeConfig(start_hour=0, end_hour=23)
    所以负荷、风电、光伏、外来直流曲线都应该是 24 行。
    """
    # 检查负荷曲线长度。
    assert len(real_case_data_24h.load_curves) == 24
    # 检查风电曲线长度。
    assert len(real_case_data_24h.wind_curves) == 24
    # 检查光伏曲线长度。
    assert len(real_case_data_24h.pv_curves) == 24
    # 外来直流数据可能为空。
    # 如果不为空，也应该被切片成 24 小时。
    if not real_case_data_24h.dc_flows.empty:
        assert len(real_case_data_24h.dc_flows) == 24


@pytest.mark.integration
def test_real_case_data_can_build_grid(real_case_data_24h, real_grid_24h):
    """
    测试真实 CaseData 是否能够成功构建 Grid。
    这个测试重点检查：
    1. Grid 中对象数量是否和 CaseData 中的数据表匹配；
    """
    grid = real_grid_24h
    case_data = real_case_data_24h

    # Grid 中的分区数量应该等于 CaseData 中的分区表行数。
    assert len(grid.zones) == len(case_data.zones)
    # Grid 至少应该有一个分区。
    assert len(grid.zones) > 0
    # Grid 至少应该有资源。
    assert len(grid.resources) > 0
    # 火电资源数量应该等于 thermal_units 表行数。
    assert len(grid.getResListFromType("THERMAL")) == len(case_data.thermal_units)
    # 水电资源数量应该等于 hydro_units 表行数。
    assert len(grid.getResListFromType("HYDRO")) == len(case_data.hydro_units)
    # 当前 grid_builder 把普通储能和抽蓄都作为 STORAGE 类型接入。
    assert len(grid.getResListFromType("STORAGE")) == (
        len(case_data.storage_units) + len(case_data.pumped_storage_units)
    )
    # 负荷资源数量应该等于 load_curves 的列数。
    assert len(grid.getResListFromType("LOAD")) == len(case_data.load_curves.columns)
    # 风电资源数量应该等于 wind_curves 的列数。
    assert len(grid.getResListFromType("WIND")) == len(case_data.wind_curves.columns)
    # 光伏资源数量应该等于 pv_curves 的列数。
    assert len(grid.getResListFromType("PV")) == len(case_data.pv_curves.columns)


@pytest.mark.integration
def test_real_grid_all_resources_link_to_existing_zones(real_grid_24h):
    """
    测试 Grid 中所有资源是否都挂接到了已存在的分区。
    检查两个方向：
    1. resource.zoneId 必须存在于 grid.zones；
    2. resource.id 必须挂回对应 zone.resKeyList。
    """

    grid = real_grid_24h

    for res_id, resource in grid.resources.items():
        # 资源所属分区必须存在。
        assert resource.zoneId in grid.zones, (
            f"资源 {res_id} 的 zoneId={resource.zoneId} 不在 grid.zones 中"
        )

        # 资源必须挂回所属分区的资源列表。
        assert res_id in grid.zones[resource.zoneId].resKeyList, (
            f"资源 {res_id} 没有挂回所属分区 {resource.zoneId}.resKeyList"
        )


@pytest.mark.integration
def test_real_grid_all_zone_resource_lists_are_consistent(real_grid_24h):
    """
    测试 Zone.resKeyList 和 Grid.resources 是否一致。
    这个测试是从分区出发，检查分区记录的资源是否真实存在，
    并且资源自身的 zoneId 是否和当前分区一致。
    """
    grid = real_grid_24h
    for zone_id, zone in grid.zones.items():
        for res_id in zone.resKeyList:
            # 分区记录的资源 ID 必须存在于 grid.resources。
            assert res_id in grid.resources, (
                f"分区 {zone_id}.resKeyList 中的资源 {res_id} 不在 grid.resources 中"
            )
            # 资源自身记录的 zoneId 必须和当前分区一致。
            assert grid.resources[res_id].zoneId == zone_id, (
                f"资源 {res_id} 在分区 {zone_id} 下，"
                f"但自身 zoneId={grid.resources[res_id].zoneId}"
            )


@pytest.mark.integration
def test_real_grid_all_intertrans_link_to_existing_zones(real_grid_24h):
    """
    测试 Grid 中所有联络线是否都连接到已存在的分区。
    """

    grid = real_grid_24h

    for line_id, line in grid.intertrans.items():
        # 检查起点分区是否存在。
        assert line.fromZone in grid.zones, (
            f"{line_id}.fromZone 不存在: {line.fromZone}"
        )

        # 检查终点分区是否存在。
        assert line.toZone in grid.zones, (
            f"{line_id}.toZone 不存在: {line.toZone}"
        )

        # 检查线路是否挂到起点分区的 outFlow。[line.fromZone].outFlow：分区的送出线路 ID 列表
        assert line_id in grid.zones[line.fromZone].outFlow, (
            f"{line_id} 没有挂到起点分区 {line.fromZone}.outFlow"
        )

        # 检查线路是否挂到终点分区的 inFlow。
        assert line_id in grid.zones[line.toZone].inFlow, (
            f"{line_id} 没有挂到终点分区 {line.toZone}.inFlow"
        )

        # 检查正向容量不能为负。
        assert line.capacityToZone >= 0

        # 检查反向容量不能为负。
        assert line.capacityFromZone >= 0


@pytest.mark.integration
def test_real_grid_hydro_units_link_to_basins(real_grid_24h):
    """
    测试所有水电资源是否正确挂接到流域 Basin。
    水电资源除了属于某个分区 zoneId，
    还应该属于某个流域 basinId。
    """

    grid = real_grid_24h

    for hydro in grid.getResListFromType("HYDRO"):#按资源类型过滤，返回该类型全部资源实例列表。
        # 根据水电资源的 zoneId 找到所属分区。
        zone = grid.zones[hydro.zoneId]

        # 检查所属流域是否存在。
        assert hydro.basinId in zone.basinDict, (
            f"水电 {hydro.id} 的 basinId={hydro.basinId} "
            f"不在分区 {hydro.zoneId} 的 basinDict 中"
        )

        # 取出对应流域对象。
        basin = zone.basinDict[hydro.basinId]

        # 检查水电资源是否挂到了流域 hydroDict。
        assert hydro.id in basin.hydroDict, (
            f"水电 {hydro.id} 没有挂到流域 {hydro.basinId}.hydroDict"
        )


@pytest.mark.integration
def test_real_grid_storage_parameters_are_reasonable(real_grid_24h):
    """
    测试储能和抽蓄资源参数是否合理。
    当前 grid_builder 把普通储能和抽蓄都作为 STORAGE 类型接入。
    """

    grid = real_grid_24h

    for storage in grid.getResListFromType("STORAGE"):
        # 最大功率不能为负。
        assert storage.Pmax >= 0

        # 最大能量容量不能为负。
        assert storage.Emax >= 0

        # 初始能量不能为负。
        assert storage.E0 >= 0

        # 充电效率必须在 0 到 1 之间。
        assert 0 <= storage.effC <= 1.0, (
            f"{storage.id} 充电效率异常: {storage.effC}"
        )

        # 放电效率必须在 0 到 1 之间。
        assert 0 <= storage.effD <= 1.0, (
            f"{storage.id} 放电效率异常: {storage.effD}"
        )


@pytest.mark.integration
def test_real_grid_series_resources_are_registered(real_case_data_24h, real_grid_24h):
    """
    测试所有需要时序数据的资源是否登记到 grid.sceKeyList。

    当前需要时序数据的资源包括：
    1. LOAD：负荷；
    2. WIND：风电；
    3. PV：光伏。

    这些资源应该满足：
    1. 资源 ID 出现在 grid.sceKeyList 中；
    2. 资源存在于 grid.resources 中；
    3. 资源的 isSeries 字段为 True。
    """

    grid = real_grid_24h
    case_data = real_case_data_24h

    # 预期时序资源数量 =
    # 负荷曲线列数 + 风电曲线列数 + 光伏曲线列数。
    expected_series_count = (
        len(case_data.load_curves.columns)
        + len(case_data.wind_curves.columns)
        + len(case_data.pv_curves.columns)
    )

    # 检查 sceKeyList 中登记的时序资源数量是否正确。
    assert len(grid.sceKeyList) == expected_series_count

    # 检查每个时序资源是否真实存在，并且 isSeries=True。
    for res_id in grid.sceKeyList:
        assert res_id in grid.resources
        assert grid.resources[res_id].isSeries is True
