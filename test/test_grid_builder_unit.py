import pytest
import pandas as pd
from types import SimpleNamespace

# 待测试核心函数：根据算例数据构建完整电网模型
from src.data.grid_builder import build_grid
# 电网顶层模型类
from src.model.grid import Grid


def make_fake_case_data():
    """
    构造一个最小但完整的 CaseData 替身。
    目的：不依赖成员一真实 Excel，也能测试成员二 build_grid 的对象构建逻辑。
    实现思路：用 SimpleNamespace 模拟真实读取Excel后的 case_data 数据容器，
    内置全部建模需要的表单DataFrame与字典，包含2个分区、火电/水电/储能/抽蓄/联络线/负荷风光时序/水库来水等全套最小样本数据。
    """
    return SimpleNamespace(
        # 分区基础表：两个片区 鄂东、鄂西
        zones=pd.DataFrame({
            "zone_name": ["鄂东", "鄂西"]
        }),

        # 跨区联络线：鄂东-鄂西输电断面，传输限额1000MW
        transmissions=pd.DataFrame({
            "line_name": ["鄂东-鄂西断面"],
            "zone_from": ["鄂东"],
            "zone_to": ["鄂西"],
            "limit_mw": [1000.0],
        }),

        # 火电机组表单：1台鄂东火电T1，包含出力上下限、爬坡、启停成本、最小启停时间等火电特有参数
        thermal_units=pd.DataFrame({
            "unit_id": ["T1"],
            "unit_name": ["鄂东火电1"],
            "zone_name": ["鄂东"],
            "p_min_mw": [100.0],
            "p_max_mw": [600.0],
            "ramp_up_mw_per_h": [300.0],
            "ramp_down_mw_per_h": [300.0],
            "min_on_h": [3],
            "min_off_h": [3],
            "startup_cost": [10000.0],
            "shutdown_cost": [5000.0],
        }),

        # 常规水电机组：鄂西清江1台水电H1，出力0~200MW，绑定流域清江
        hydro_units=pd.DataFrame({
            "unit_id": ["H1"],
            "unit_name": ["鄂西水电1"],
            "zone_name": ["鄂西"],
            "basin_name": ["清江"],
            "p_min_mw": [0.0],
            "p_max_mw": [200.0],
        }),

        # 电化学储能：鄂东储能S1，额定功率、容量、充放效率、初始SOC
        storage_units=pd.DataFrame({
            "unit_id": ["S1"],
            "unit_name": ["鄂东储能1"],
            "zone_name": ["鄂东"],
            "p_max_mw": [50.0],
            "energy_capacity_mwh": [100.0],
            "charge_efficiency": [0.95],
            "discharge_efficiency": [0.95],
            "init_soc": [50.0],
        }),

        # 抽水蓄能：鄂西抽蓄PS1，参数独立表单，代码内部统一归类为STORAGE类型
        pumped_storage_units=pd.DataFrame({
            "unit_id": ["PS1"],
            "unit_name": ["鄂西抽蓄1"],
            "zone_name": ["鄂西"],
            "p_max_mw": [300.0],
            "energy_capacity_mwh": [1200.0],
            "charge_efficiency": [0.90],
            "discharge_efficiency": [0.90],
            "init_soc": [50.0],
        }),

        # 分时负荷曲线：3个时段，列名=分区名，值为各时段负荷功率
        load_curves=pd.DataFrame({
            "鄂东": [100.0, 110.0, 120.0],
            "鄂西": [80.0, 85.0, 90.0],
        }),

        # 风电时序出力曲线
        wind_curves=pd.DataFrame({
            "鄂东": [10.0, 12.0, 15.0],
            "鄂西": [5.0, 5.0, 6.0],
        }),

        # 光伏时序出力曲线
        pv_curves=pd.DataFrame({
            "鄂东": [0.0, 20.0, 10.0],
            "鄂西": [0.0, 15.0, 8.0],
        }),

        # 流域来水数据字典：key=流域名，value=来水表格，区分平均/强迫/预想三种来水场景
        hydro_flows={
            "清江": pd.DataFrame(
                {
                    1: [10.0, 12.0, 9.0],
                    2: [11.0, 13.0, 10.0],
                },
                index=["平均", "强迫", "预想"],
            )
        },

        # 直流外送/入时序功率
        dc_flows=pd.DataFrame({
            "DC1": [0.0, 1.0, 2.0]
        }),

        # 算例元信息，case_name作为全局grid_id
        metadata={
            "case_name": "UNIT_TEST"
        },
    )


# ========== 正向功能测试：正常数据可成功构建电网 ==========
def test_build_grid_from_fake_case_data_success():
    """
    测试目标：输入一套完整合法模拟数据，build_grid能正常生成Grid实例，
    校验电网顶层基础统计信息（分区、线路、各类电源数量、算例ID）是否与模拟数据匹配。
    """
    # 生成模拟算例数据
    case_data = make_fake_case_data()
    # 执行核心建模函数
    grid = build_grid(case_data)

    # 校验返回对象类型是Grid
    assert isinstance(grid, Grid)
    # 校验全局算例ID取自metadata.case_name
    assert grid.id == "UNIT_TEST"

    # 校验电网内分区集合正确
    assert set(grid.zones.keys()) == {"鄂东", "鄂西"}

    # 获取电网整体统计摘要，校验各类资源数量
    summary = grid.summary()
    assert summary["num_zones"] == 2
    assert summary["num_intertrans"] == 1    # 1条跨区联络线
    assert summary["num_thermal"] == 1      # 1台火电
    assert summary["num_hydro"] == 1        # 1台常规水电
    # 普通储能+抽蓄，代码内部统一归为storage统计，合计2台
    assert summary["num_storage"] == 2
    assert summary["num_load"] == 2         # 2个分区负荷时序
    assert summary["num_wind"] == 2         # 两区风电时序
    assert summary["num_pv"] == 2            # 两区光伏时序


def test_resource_zone_links_are_built_correctly():
    """
    测试目标：校验各类电源与所属分区的绑定关系是否正确，
    分区对象能正确查询到自己下辖的机组ID，机组ID格式拼接规则正确（类型+unit_id）。
    """
    grid = build_grid(make_fake_case_data())

    # 按分区+电源类型查询机组ID，校验拼接前缀：THERMAL/HYDRO/STORAGE
    assert grid.getResIdListFromZoneAndType("鄂东", "THERMAL") == ["THERMALT1"]
    assert grid.getResIdListFromZoneAndType("鄂西", "HYDRO") == ["HYDROH1"]
    assert "STORAGES1" in grid.getResIdListFromZoneAndType("鄂东", "STORAGE")
    assert "STORAGEPS1" in grid.getResIdListFromZoneAndType("鄂西", "STORAGE")

    # 校验分区自身资源列表包含对应机组
    assert "THERMALT1" in grid.zones["鄂东"].resKeyList
    assert "HYDROH1" in grid.zones["鄂西"].resKeyList


def test_transmission_links_are_built_correctly():
    """
    测试目标：校验跨区联络线完整加载，线路ID拼接规则、送受端分区、传输限额参数正确。
    """
    grid = build_grid(make_fake_case_data())

    # 校验联络线ID：INTERTRAN+线路名称
    assert "INTERTRAN鄂东-鄂西断面" in grid.intertrans

    intertran = grid.intertrans["INTERTRAN鄂东-鄂西断面"]
    # 校验线路两端分区
    assert intertran.fromZone == "鄂东"
    assert intertran.toZone == "鄂西"
    # 双向传输限额均为1000MW
    assert intertran.capacityToZone == 1000.0
    assert intertran.capacityFromZone == 1000.0


def test_hydro_is_attached_to_basin_and_hydro_flow():
    """
    测试目标：校验水电-流域-来水时序三者绑定关系，
    流域挂载在对应分区，流域内包含水电、来水时序数据正确读取。
    """
    grid = build_grid(make_fake_case_data())

    # 清江流域挂载在鄂西分区
    assert "BASIN清江" in grid.zones["鄂西"].basinDict

    basin = grid.zones["鄂西"].basinDict["BASIN清江"]
    # 流域下绑定水电H1
    assert "HYDROH1" in basin.hydroDict
    # 流域总装机等于水电最大出力
    assert basin.capacity == 200.0

    # 校验三种场景来水数值读取正确
    assert basin.average[1] == 10.0
    assert basin.forced[1] == 12.0
    assert basin.predicted[1] == 9.0


def test_series_resources_are_added_to_sce_key_list():
    """
    测试目标：负荷、风电、光伏这类时序资源ID全部存入grid全局时序资源列表sceKeyList，
    用于后续8760时序循环、场景优化遍历。
    """
    grid = build_grid(make_fake_case_data())

    # 预期所有时序资源ID（LOAD/WIND/PV+分区名）
    expected_series_ids = {
        "LOAD鄂东", "LOAD鄂西",
        "WIND鄂东", "WIND鄂西",
        "PV鄂东", "PV鄂西",
    }

    # 校验全局时序资源集合完全匹配
    assert set(grid.sceKeyList) == expected_series_ids


# ========== 异常用例测试：非法输入必须抛出指定错误，校验参数校验逻辑 ==========
def test_build_grid_rejects_resource_with_unknown_zone():
    """
    测试目标：机组所属分区不存在时，build_grid必须抛出KeyError，阻断建模。
    修改火电行zone_name为不存在分区，捕获预期报错。
    """
    case_data = make_fake_case_data()
    # 篡改机组所属分区为不存在的值
    case_data.thermal_units.loc[0, "zone_name"] = "不存在的分区"

    # 预期抛出KeyError，错误信息包含非法分区名
    with pytest.raises(KeyError, match="Zone 不存在的分区"):
        build_grid(case_data)


def test_build_grid_rejects_load_curve_with_unknown_zone():
    """
    测试目标：负荷曲线存在未定义的分区列，校验时序数据分区一致性，抛出KeyError。
    """
    case_data = make_fake_case_data()
    # 新增一列不存在分区的负荷时序
    case_data.load_curves["不存在的分区"] = [1.0, 2.0, 3.0]
    with pytest.raises(KeyError, match="load_curves references zone '不存在的分区'"):
        build_grid(case_data)


def test_build_grid_rejects_duplicate_resource_id():
    """
    测试目标：不允许存在重复unit_id的机组，重复数据抛ValueError提示duplicated。
    将火电表拼接自身制造重复机组。
    """
    case_data = make_fake_case_data()
    case_data.thermal_units = pd.concat(
        [case_data.thermal_units, case_data.thermal_units],
        ignore_index=True,#pd.concat用于连接对象
    )

    with pytest.raises(ValueError, match="duplicated"):
        build_grid(case_data)
#期望报错的信息里包含 "duplicated"

def test_build_grid_rejects_intertran_with_unknown_endpoint():
    """
    测试目标：联络线送/受端分区不存在时，抛出KeyError阻断建模。
    修改线路toZone为非法分区。
    """
    case_data = make_fake_case_data()
    case_data.transmissions.loc[0, "zone_to"] = "不存在的分区"

    with pytest.raises(KeyError, match="toZone 不存在的分区"):
        build_grid(case_data)