import pandas as pd  # 导入 pandas，用来构造假的 DataFrame 数据
import pytest  # 导入 pytest，用来测试错误情况
from src.data.case_data import CaseData  # 导入成员一写好的 CaseData 数据结构
from src.data.grid_builder import build_grid  # 导入你成员二要写的 build_grid 函数

#造输入，得到DataFrame 就是假装成员一已经从 Excel 里读出来、整理好了的数据。
def make_minimal_case_data() -> CaseData:  # 定义一个函数，用来构造最小假的 CaseData
    zones = pd.DataFrame(  # 构造分区表
        {  # 开始定义分区表字段
            "zone_name": ["WH", "EX"],  # 定义两个分区：WH 和 EX
        }  # 结束定义分区表字段
    )  # 完成分区表 DataFrame

    transmissions = pd.DataFrame(  # 构造联络线表
        {  # 开始定义联络线字段
            "line_id": ["line_001"],  # 定义联络线 ID
            "line_name": ["EX_to_WH"],  # 定义联络线名称
            "zone_from": ["EX"],  # 定义联络线起始分区
            "zone_to": ["WH"],  # 定义联络线终止分区
            "type": ["AC"],  # 定义联络线类型为交流 AC
            "capacity_to_zone_mw": [3000.0],  # 定义正向输电容量，单位 MW
            "capacity_from_zone_mw": [3000.0],  # 定义反向输电容量，单位 MW
        }  # 结束定义联络线字段
    )  # 完成联络线表 DataFrame

    thermal_units = pd.DataFrame(  # 构造火电机组表
        {  # 开始定义火电字段
            "unit_id": ["thermal_001"],  # 定义火电机组 ID
            "unit_name": ["火电1"],  # 定义火电机组名称
            "zone_name": ["WH"],  # 定义火电所属分区
            "p_min_mw": [100.0],  # 定义火电最小出力，单位 MW
            "p_max_mw": [600.0],  # 定义火电最大出力，单位 MW
            "ramp_up_mw_per_h": [200.0],  # 定义火电上爬坡能力，单位 MW/h
            "ramp_down_mw_per_h": [200.0],  # 定义火电下爬坡能力，单位 MW/h
            "min_on_h": [2],  # 定义最小开机时间，单位小时
            "min_off_h": [2],  # 定义最小停机时间，单位小时
        }  # 结束定义火电字段
    )  # 完成火电机组表 DataFrame

    hydro_units = pd.DataFrame(  # 构造水电机组表
        {  # 开始定义水电字段
            "unit_id": ["hydro_001"],  # 定义水电机组 ID
            "unit_name": ["水电1"],  # 定义水电机组名称
            "zone_name": ["EX"],  # 定义水电所属分区
            "basin_name": ["basin_001"],  # 定义水电所属流域
            "p_min_mw": [0.0],  # 定义水电最小出力，单位 MW
            "p_max_mw": [1000.0],  # 定义水电最大出力，单位 MW
        }  # 结束定义水电字段
    )  # 完成水电机组表 DataFrame

    storage_units = pd.DataFrame(  # 构造储能表
        {  # 开始定义储能字段
            "unit_id": ["storage_001"],  # 定义储能 ID
            "unit_name": ["储能1"],  # 定义储能名称
            "zone_name": ["WH"],  # 定义储能所属分区
            "p_max_mw": [100.0],  # 定义储能功率上限，单位 MW
            "e_max_mwh": [200.0],  # 定义储能电量上限，单位 MWh
            "e_min_mwh": [0.0],  # 定义储能电量下限，单位 MWh
            "e_initial_mwh": [100.0],  # 定义储能初始电量，单位 MWh
            "charge_efficiency": [0.95],  # 定义充电效率
            "discharge_efficiency": [0.95],  # 定义放电效率
        }  # 结束定义储能字段
    )  # 完成储能表 DataFrame

    pumped_storage_units = pd.DataFrame()  # 构造空的抽蓄表，最小测试先不测抽蓄

    load_curves = pd.DataFrame(  # 构造负荷时序
        {  # 开始定义负荷时序字段
            "WH": [1000.0, 1100.0],  # 定义 WH 分区 2 小时负荷
            "EX": [500.0, 600.0],  # 定义 EX 分区 2 小时负荷
        }  # 结束定义负荷时序字段
    )  # 完成负荷时序 DataFrame

    wind_curves = pd.DataFrame(  # 构造风电时序
        {  # 开始定义风电时序字段
            "WH": [0.2, 0.3],  # 定义 WH 分区 2 小时风电标幺值
            "EX": [0.4, 0.5],  # 定义 EX 分区 2 小时风电标幺值
        }  # 结束定义风电时序字段
    )  # 完成风电时序 DataFrame

    pv_curves = pd.DataFrame(  # 构造光伏时序
        {  # 开始定义光伏时序字段
            "WH": [0.0, 0.1],  # 定义 WH 分区 2 小时光伏标幺值
            "EX": [0.0, 0.2],  # 定义 EX 分区 2 小时光伏标幺值
        }  # 结束定义光伏时序字段
    )  # 完成光伏时序 DataFrame
#把读出来的数据塞进成员一的 CaseData，模拟成员一 loader.py 的输出
    return CaseData(  # 返回成员一的 CaseData 对象
        zones=zones,  # 传入分区表
        transmissions=transmissions,  # 传入联络线表
        thermal_units=thermal_units,  # 传入火电表
        hydro_units=hydro_units,  # 传入水电表
        storage_units=storage_units,  # 传入储能表
        pumped_storage_units=pumped_storage_units,  # 传入抽蓄表
        load_curves=load_curves,  # 传入负荷时序
        wind_curves=wind_curves,  # 传入风电时序
        pv_curves=pv_curves,  # 传入光伏时序
        hydro_flows={},  # 传入空的流域过程数据
        dc_flows=pd.DataFrame(),  # 传入空的外来直流时序
        metadata={"case_name": "minimal_test"},  # 传入测试用元数据
    )  # 完成 CaseData 构造


def test_build_grid_from_minimal_case_data():  # 定义最小测试函数
    case_data = make_minimal_case_data()  # 构造假的最小 CaseData

    grid = build_grid(case_data)  # 调用你成员二写的 build_grid 函数

    #assert grid.id == "HUBEI2030"  # 检查 Grid 的 ID 是否正确
    assert grid.id == "minimal_test"

    assert "WH" in grid.zones  # 检查 WH 分区是否成功加入 Grid

    assert "EX" in grid.zones  # 检查 EX 分区是否成功加入 Grid

    thermal_list = grid.getResListFromZoneAndType("WH", "THERMAL")  # 查询 WH 分区的火电资源

    assert len(thermal_list) == 1  # 检查 WH 分区火电数量是否为 1

    assert thermal_list[0].id == "THERMALthermal_001"  # 检查火电 ID 是否按旧程序规则加上 THERMAL 前缀

    hydro_list = grid.getResListFromZoneAndType("EX", "HYDRO")  # 查询 EX 分区的水电资源

    assert len(hydro_list) == 1  # 检查 EX 分区水电数量是否为 1

    assert hydro_list[0].id == "HYDROhydro_001"  # 检查水电 ID 是否按旧程序规则加上 HYDRO 前缀

    storage_list = grid.getResListFromZoneAndType("WH", "STORAGE")  # 查询 WH 分区的储能资源

    assert len(storage_list) == 1  # 检查 WH 分区储能数量是否为 1

    ac_in, ac_out = grid.getIntertranListFromZoneAndType("WH", "AC")  # 查询 WH 分区的交流联络线流入和流出

    assert len(ac_in) == 1  # 检查 WH 有 1 条交流流入联络线

    assert len(ac_out) == 0  # 检查 WH 没有交流流出联络线

    assert ac_in[0].id == "INTERTRANline_001"  # 检查联络线 ID 是否按旧程序规则加上 INTERTRAN 前缀

    basin_list = grid.getBasinListFromZone("EX")  # 查询 EX 分区的流域列表

    assert len(basin_list) == 1  # 检查 EX 分区流域数量是否为 1

    assert basin_list[0].id == "BASINbasin_001"
    # 检查流域 ID 是否按旧程序规则加上 BASIN 前缀
    load_list = grid.getResListFromZoneAndType("WH", "LOAD")  # 查询 WH 分区的负荷资源

    assert len(load_list) == 1  # 检查 WH 分区是否创建了 1 个负荷资源

    assert load_list[0].id == "LOADWH"  # 检查负荷 ID 是否按当前规则生成

    assert load_list[0].capacity == 1100.0  # 检查负荷容量是否等于 WH 负荷曲线最大值

    wind_list = grid.getResListFromZoneAndType("WH", "WIND")  # 查询 WH 分区的风电资源

    assert len(wind_list) == 1  # 检查 WH 分区是否创建了 1 个风电资源

    assert wind_list[0].id == "WINDWH"  # 检查风电 ID 是否按当前规则生成

    assert wind_list[0].Pmax == 1.0  # 检查风电最大出力是否为标幺上限 1.0

    pv_list = grid.getResListFromZoneAndType("WH", "PV")  # 查询 WH 分区的光伏资源

    assert len(pv_list) == 1  # 检查 WH 分区是否创建了 1 个光伏资源

    assert pv_list[0].id == "PVWH"  # 检查光伏 ID 是否按当前规则生成

    assert pv_list[0].Pmax == 1.0  # 检查光伏最大出力是否为标幺上限 1.0

    #添加异常测试 1：资源分区不存在
def test_invalid_thermal_zone_should_fail():  # 定义测试：火电机组所属分区不存在时应该失败
    case_data = make_minimal_case_data()  # 先构造一个正常的最小 CaseData
    case_data.thermal_units.loc[0, "zone_name"] = "NOT_EXIST"  # 故意把火电所属分区改成不存在的分区
    with pytest.raises(KeyError):  # 期望 build_grid 抛出 KeyError
            build_grid(case_data)  # 调用 build_grid，应该因为火电分区不存在而失败
    #添加异常测试 2：联络线起始分区不存在
def test_invalid_transmission_from_zone_should_fail():  # 定义测试：联络线起始分区不存在时应该失败
    case_data = make_minimal_case_data()  # 先构造一个正常的最小 CaseData
    case_data.transmissions.loc[0, "zone_from"] = "NOT_EXIST"  # 故意把联络线起始分区改成不存在的分区
    with pytest.raises(KeyError):  # 期望 build_grid 抛出 KeyError
            build_grid(case_data)  # 调用 build_grid，应该因为联络线起始分区不存在而失败
    #添加异常测试 3：联络线终止分区不存在
def test_invalid_transmission_to_zone_should_fail():  # 定义测试：联络线终止分区不存在时应该失败
    case_data = make_minimal_case_data()  # 先构造一个正常的最小 CaseData
    case_data.transmissions.loc[0, "zone_to"] = "NOT_EXIST"  # 故意把联络线终止分区改成不存在的分区
    with pytest.raises(KeyError):  # 期望 build_grid 抛出 KeyError
            build_grid(case_data)  # 调用 build_grid，应该因为联络线终止分区不存在而失败
    #添加异常测试 4：重复资源 ID
def test_duplicate_thermal_resource_id_should_fail():  # 定义测试：重复火电资源 ID 应该失败
    case_data = make_minimal_case_data()  # 先构造一个正常的最小 CaseData
    duplicated_row = case_data.thermal_units.iloc[[0]].copy()  # 复制第一行火电数据，制造重复机组
    case_data.thermal_units = pd.concat(  # 把原火电表和复制出来的火电表拼接起来
            [case_data.thermal_units, duplicated_row],  # 第一个是原表，第二个是重复行
            ignore_index=True,  # 重置索引，避免索引重复干扰测试
        )  # 完成重复火电表构造
    with pytest.raises(ValueError):  # 期望 build_grid 抛出 ValueError
            build_grid(case_data)  # 调用 build_grid，应该因为资源 ID 重复而失败
    #添加异常测试 5：重复分区 ID
def test_duplicate_zone_id_should_fail():  # 定义测试：重复分区 ID 应该失败
    case_data = make_minimal_case_data()  # 先构造一个正常的最小 CaseData
    duplicated_zone = case_data.zones.iloc[[0]].copy()  # 复制第一行分区数据，制造重复分区
    case_data.zones = pd.concat(  # 把原分区表和复制出来的分区表拼接起来
            [case_data.zones, duplicated_zone],  # 第一个是原表，第二个是重复行
            ignore_index=True,  # 重置索引，避免索引重复干扰测试
    )  # 完成重复分区表构造
    with pytest.raises(ValueError):  # 期望 build_grid 抛出 ValueError
            build_grid(case_data)  # 调用 build_grid，应该因为分区 ID 重复而失败
def test_build_grid_with_pumped_storage():  # 定义测试：检查抽蓄是否能被加入 Grid
    case_data = make_minimal_case_data()  # 构造一个正常的最小 CaseData

    case_data.pumped_storage_units = pd.DataFrame(  # 手动构造抽蓄 DataFrame
        {  # 开始定义抽蓄字段
            "unit_id": ["pumped_001"],  # 定义抽蓄机组 ID
            "unit_name": ["抽蓄1"],  # 定义抽蓄机组名称
            "zone_name": ["EX"],  # 定义抽蓄所属分区
            "p_max_mw": [300.0],  # 定义抽蓄最大功率，单位 MW
            "e_max_mwh": [1200.0],  # 定义抽蓄最大电量，单位 MWh
            "e_min_mwh": [0.0],  # 定义抽蓄最小电量，单位 MWh
            "e_initial_mwh": [600.0],  # 定义抽蓄初始电量，单位 MWh
            "charge_efficiency": [0.9],  # 定义抽蓄充电效率
            "discharge_efficiency": [0.9],  # 定义抽蓄放电效率
        }  # 结束定义抽蓄字段
    )  # 完成抽蓄 DataFrame 构造

    grid = build_grid(case_data)  # 调用 build_grid 构建 Grid

    storage_list = grid.getResListFromZoneAndType("EX", "STORAGE")  # 查询 EX 分区的 STORAGE 资源

    assert len(storage_list) == 1  # 检查 EX 分区是否有 1 个 STORAGE 资源，也就是抽蓄

    assert storage_list[0].id == "STORAGEpumped_001"  # 检查抽蓄资源 ID 是否正确

    assert storage_list[0].Pmax == 300.0  # 检查抽蓄最大功率是否正确

    assert storage_list[0].Emax == 1200.0  # 检查抽蓄最大电量是否正确

    assert storage_list[0].E0 == 600.0  # 检查抽蓄初始电量是否正确

    assert storage_list[0].effC == 0.9  # 检查抽蓄充电效率是否正确

    assert storage_list[0].effD == 0.9  # 检查抽蓄放电效率是否正确
def test_invalid_load_curve_zone_should_fail():  # 定义测试：负荷曲线分区不存在时应该失败
    case_data = make_minimal_case_data()  # 构造一个正常的最小 CaseData

    case_data.load_curves["NOT_EXIST"] = [100.0, 200.0]  # 故意添加一个不存在分区的负荷曲线列

    with pytest.raises(KeyError):  # 期望 build_grid 抛出 KeyError
        build_grid(case_data)  # 调用 build_grid，应该因为负荷曲线分区不存在而失败
def test_invalid_wind_curve_zone_should_fail():  # 定义测试：风电曲线分区不存在时应该失败
    case_data = make_minimal_case_data()  # 构造一个正常的最小 CaseData

    case_data.wind_curves["NOT_EXIST"] = [0.1, 0.2]  # 故意添加一个不存在分区的风电曲线列

    with pytest.raises(KeyError):  # 期望 build_grid 抛出 KeyError
        build_grid(case_data)  # 调用 build_grid，应该因为风电曲线分区不存在而失败
def test_invalid_pv_curve_zone_should_fail():  # 定义测试：光伏曲线分区不存在时应该失败
    case_data = make_minimal_case_data()  # 构造一个正常的最小 CaseData

    case_data.pv_curves["NOT_EXIST"] = [0.0, 0.1]  # 故意添加一个不存在分区的光伏曲线列

    with pytest.raises(KeyError):  # 期望 build_grid 抛出 KeyError
        build_grid(case_data)  # 调用 build_grid，应该因为光伏曲线分区不存在而失败
