from pathlib import Path  # 导入 Path，用来处理配置文件路径

import pytest  # 导入 pytest，用来跳过没有配置文件时的测试

from src.data.loader import load_case  # 导入成员一写的 load_case 函数

from src.data.grid_builder import build_grid  # 导入成员二写的 build_grid 函数


def test_build_grid_from_real_loader_case():  # 定义测试函数：从成员一真实 loader 输出的 CaseData 构建 Grid，只检查了数量大于0
    project_root = Path(__file__).resolve().parents[1]  # 获取项目根目录，也就是 TanU_HuBei 目录

    config_path = project_root / "configs" / "cases"/"hubei2030.yaml"   # 拼出默认算例配置文件路径

    if not config_path.exists():  # 判断配置文件是否存在
        pytest.skip(f"找不到配置文件：{config_path}")  # 如果配置文件不存在，就跳过这个测试

    case_data = load_case(str(config_path))  # 调用成员一的 load_case，读取真实数据并生成 CaseData

    grid = build_grid(case_data)  # 调用成员二的 build_grid，把真实 CaseData 转成 Grid

    assert grid is not None  # 检查 Grid 是否成功创建

    assert len(grid.zones) > 0  # 检查 Grid 中至少有一个分区

    assert len(grid.resources) > 0  # 检查 Grid 中至少有一个资源

    assert isinstance(grid.resources, dict)  # 检查 Grid.resources 是否是字典

    assert isinstance(grid.zones, dict)  # 检查 Grid.zones 是否是字典
    #增强真实 loader 测试
    thermal_units = grid.getResListFromType("THERMAL")  # 查询真实 Grid 中所有火电资源

    hydro_units = grid.getResListFromType("HYDRO")  # 查询真实 Grid 中所有水电资源

    storage_units = grid.getResListFromType("STORAGE")  # 查询真实 Grid 中所有储能和抽蓄资源

    load_units = grid.getResListFromType("LOAD")  # 查询真实 Grid 中所有负荷资源

    wind_units = grid.getResListFromType("WIND")  # 查询真实 Grid 中所有风电资源

    pv_units = grid.getResListFromType("PV")  # 查询真实 Grid 中所有光伏资源

    #ac_lines = grid.getIntertransListFromType("AC")  # 查询真实 Grid 中所有交流联络线
    ac_lines = [line for line in grid.intertrans.values() if line.type == "AC"]  # 从 Grid 的 intertrans 字典中筛选所有 AC 联络线

    assert len(thermal_units) > 0  # 检查真实 Grid 中至少有火电资源

    assert len(hydro_units) > 0  # 检查真实 Grid 中至少有水电资源

    assert len(load_units) > 0  # 检查真实 Grid 中至少有负荷资源

    assert len(wind_units) > 0  # 检查真实 Grid 中至少有风电资源

    assert len(pv_units) > 0  # 检查真实 Grid 中至少有光伏资源

    #assert len(ac_lines) >= 0  # 检查交流联络线查询接口可以正常运行
    assert isinstance(ac_lines, list)  # 检查 AC 联络线统计结果是列表
    #打印真实 Grid 摘要
    print("Grid ID:", grid.id)  # 打印 Grid 的 ID

    print("Zone count:", len(grid.zones))  # 打印分区数量

    print("Resource count:", len(grid.resources))  # 打印资源总数量

    print("Thermal count:", len(thermal_units))  # 打印火电数量

    print("Hydro count:", len(hydro_units))  # 打印水电数量

    print("Storage count:", len(storage_units))  # 打印储能和抽蓄数量

    print("Load count:", len(load_units))  # 打印负荷资源数量

    print("Wind count:", len(wind_units))  # 打印风电资源数量

    print("PV count:", len(pv_units))  # 打印光伏资源数量

    print("AC line count:", len(ac_lines))  # 打印交流联络线数量
    print(grid.summary())  # 打印 Grid 摘要信息
def test_real_grid_object_links_are_valid():  # 定义测试函数：检查真实 Grid 内部对象关联是否正确
    project_root = Path(__file__).resolve().parents[1]  # 获取项目根目录，也就是 TanU_HuBei 目录

    config_path = project_root / "configs" / "cases" / "hubei2030.yaml"  # 构造湖北 2030 配置文件路径

    if not config_path.exists():  # 判断配置文件是否存在
        pytest.skip(f"找不到配置文件：{config_path}")  # 如果配置文件不存在，就跳过测试

    case_data = load_case(str(config_path))  # 调用成员一 loader，读取真实湖北 2030 数据

    grid = build_grid(case_data)  # 调用成员二 build_grid，构建真实 Grid

    for resource_id, resource in grid.resources.items():  # 遍历 Grid 中的每一个资源对象
        assert resource.zoneId in grid.zones, f"资源 {resource_id} 的分区不存在：{resource.zoneId}"  # 检查资源所属分区是否存在

    for zone_id, zone in grid.zones.items():  # 遍历 Grid 中的每一个分区对象
        for resource_id in zone.resKeyList:  # 遍历该分区记录的所有资源 ID
            assert resource_id in grid.resources, f"分区 {zone_id} 引用了不存在的资源：{resource_id}"  # 检查分区引用的资源是否存在

    for intertran_id, intertran in grid.intertrans.items():  # 遍历 Grid 中的每一条联络线
        assert intertran.fromZone in grid.zones, f"联络线 {intertran_id} 的起始分区不存在：{intertran.fromZone}"  # 检查起始分区是否存在
        assert intertran.toZone in grid.zones, f"联络线 {intertran_id} 的终止分区不存在：{intertran.toZone}"  # 检查终止分区是否存在

    for zone_id, zone in grid.zones.items():  # 遍历 Grid 中的每一个分区
        for intertran_id in zone.inFlow:  # 遍历该分区的流入联络线 ID
            assert intertran_id in grid.intertrans, f"分区 {zone_id} 的 inFlow 引用了不存在的联络线：{intertran_id}"  # 检查流入联络线是否存在
        for intertran_id in zone.outFlow:  # 遍历该分区的流出联络线 ID
            assert intertran_id in grid.intertrans, f"分区 {zone_id} 的 outFlow 引用了不存在的联络线：{intertran_id}"  # 检查流出联络线是否存在

    for resource_id, resource in grid.resources.items():  # 再次遍历 Grid 中的每一个资源对象
        if resource.type == "HYDRO":  # 判断当前资源是否是水电资源
            zone = grid.zones[resource.zoneId]  # 取出水电所属分区对象
            assert resource.basinId in zone.basinDict, f"水电 {resource_id} 的流域不存在：{resource.basinId}"  # 检查水电所属流域是否存在
            basin = zone.basinDict[resource.basinId]  # 取出水电所属流域对象
            assert resource_id in basin.hydroDict, f"水电 {resource_id} 没有挂到流域 {resource.basinId} 下"  # 检查水电是否挂到 Basin.hydroDict
