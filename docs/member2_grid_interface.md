# 成员二 Grid 接口使用说明

本文档面向成员三、成员四、成员五，说明如何使用成员二提供的 `Grid` 对象和 `build_grid(case_data)` 接口。

当前版本已经完成成员二 Grid 构建模块第一版可交付：

- 支持从成员一 `CaseData` 构建 `Grid`
- 支持 `Zone`、`Basin`、`Intertran`、`Thermal`、`Hydro`、`Storage`、`Pumped Storage`、`Load`、`Wind`、`PV`
- 支持基础异常校验
- 支持真实湖北 2030 数据集成测试
- 支持真实 Grid 内部对象关联校验

---

## 1. Grid 在项目中的位置

项目数据主链路如下：

```text
真实湖北 2030 Excel / 配置文件
    ↓
成员一 load_case(config_path)
    ↓
CaseData
    ↓
成员二 build_grid(case_data)
    ↓
Grid
    ↓
成员三 / 成员四 / 成员五使用 Grid 写约束、场景、输出和校验
```

成员二模块不直接读取 Excel，不调用优化器，也不写求解约束。成员二只负责：

```text
CaseData -> build_grid(case_data) -> Grid
```

---

## 2. 如何构建 Grid

### 2.1 从成员一 loader 构建真实湖北 2030 Grid

```python
from pathlib import Path  # 导入 Path，用来处理配置文件路径
from src.data.loader import load_case  # 导入成员一提供的 load_case 函数
from src.data.grid_builder import build_grid  # 导入成员二提供的 build_grid 函数

project_root = Path(__file__).resolve().parents[1]  # 获取项目根目录 TanU_HuBei
config_path = project_root / "configs" / "cases" / "hubei2030.yaml"  # 构造湖北 2030 配置文件路径
case_data = load_case(str(config_path))  # 调用成员一 loader，读取真实数据并生成 CaseData
grid = build_grid(case_data)  # 调用成员二 build_grid，把 CaseData 转成 Grid
```

### 2.2 从测试用 Fake CaseData 构建 Grid

Fake CaseData 是测试文件中手写的小型 CaseData，用于单独测试成员二模块。它不依赖真实 Excel 文件。

```python
case_data = make_minimal_case_data()  # 构造测试用最小 CaseData
grid = build_grid(case_data)  # 调用成员二 build_grid，构建 Grid
```

---

## 3. Grid 里面包含什么

`Grid` 是全系统对象容器，主要包含：

| 属性 | 类型 | 含义 | 使用者 |
|---|---|---|---|
| `grid.id` | `str` | 算例 ID，例如 `HUBEI2030` | 所有成员 |
| `grid.zones` | `dict[str, Zone]` | 分区对象字典 | 成员三、四、五 |
| `grid.resources` | `dict[str, Resource]` | 所有资源对象字典 | 成员三、四、五 |
| `grid.intertrans` | `dict[str, Intertran]` | 联络线/断面对象字典 | 成员三、五 |
| `grid.sceKeyList` | `list` | 场景资源 ID 列表，后续扩展使用 | 成员四、五 |

---

## 4. 主要对象说明

### 4.1 Zone：分区对象

`Zone` 表示湖北电网中的一个分区。

常用字段：

| 字段 | 含义 |
|---|---|
| `zone.id` | 分区 ID |
| `zone.name` | 分区名称 |
| `zone.resKeyList` | 该分区下所有资源 ID |
| `zone.inFlow` | 流入该分区的联络线 ID |
| `zone.outFlow` | 流出该分区的联络线 ID |
| `zone.basinDict` | 该分区下的流域字典 |

### 4.2 Basin：水电流域对象

`Basin` 表示水电流域，用于组织水电机组。

常用字段：

| 字段 | 含义 |
|---|---|
| `basin.id` | 流域 ID |
| `basin.zoneId` | 所属分区 ID |
| `basin.capacity` | 流域总水电容量 |
| `basin.hydroDict` | 该流域下的水电机组字典 |
| `basin.average` | 平均水文过程 |
| `basin.forced` | 强迫水文过程 |
| `basin.predicted` | 预想水文过程 |

### 4.3 Intertran：联络线/断面对象

`Intertran` 表示分区之间的联络线或断面。

常用字段：

| 字段 | 含义 |
|---|---|
| `intertran.id` | 联络线 ID |
| `intertran.fromZone` | 起始分区 |
| `intertran.toZone` | 终止分区 |
| `intertran.type` | 联络线类型，例如 `AC` |
| `intertran.capacityToZone` | 正向容量 |
| `intertran.capacityFromZone` | 反向容量 |

### 4.4 Resource：资源对象

所有电源、负荷、储能都属于资源对象。

通用字段：

| 字段 | 含义 |
|---|---|
| `resource.id` | 资源 ID |
| `resource.zoneId` | 所属分区 ID |
| `resource.type` | 资源类型 |
| `resource.capacity` | 资源容量 |
| `resource.Pmin` | 最小出力 |
| `resource.Pmax` | 最大出力 |

当前支持的资源类型：

| 类型 | 含义 | 主要使用者 |
|---|---|---|
| `THERMAL` | 火电 | 成员三 |
| `HYDRO` | 水电 | 成员四 |
| `STORAGE` | 储能/抽蓄 | 成员四 |
| `LOAD` | 负荷 | 成员三、五 |
| `WIND` | 风电 | 成员四 |
| `PV` | 光伏 | 成员四 |

---

## 5. 成员三如何使用 Grid

成员三主要负责火电机组组合、系统核心约束、分区平衡等。

### 5.1 查询所有火电

```python
thermal_units = grid.getResListFromType("THERMAL")  # 查询 Grid 中所有火电资源
```

### 5.2 查询某个分区的火电

```python
thermal_units_in_zone = grid.getResListFromZoneAndType("鄂东", "THERMAL")  # 查询鄂东分区所有火电资源
```

### 5.3 查询负荷资源

```python
load_units = grid.getResListFromType("LOAD")  # 查询 Grid 中所有负荷资源
```

### 5.4 查询某个分区的负荷

```python
load_units_in_zone = grid.getResListFromZoneAndType("鄂东", "LOAD")  # 查询鄂东分区负荷资源
```

### 5.5 查询联络线流入和流出

```python
in_lines, out_lines = grid.getIntertranListFromZoneAndType("鄂东", "AC")  # 查询鄂东分区 AC 联络线流入和流出
```

成员三可以用 `in_lines` 和 `out_lines` 写分区功率平衡约束。

---

## 6. 成员四如何使用 Grid

成员四主要负责水电、储能、新能源和场景约束。

### 6.1 查询所有水电

```python
hydro_units = grid.getResListFromType("HYDRO")  # 查询 Grid 中所有水电资源
```

### 6.2 查询某个分区的水电

```python
hydro_units_in_zone = grid.getResListFromZoneAndType("鄂西", "HYDRO")  # 查询鄂西分区所有水电资源
```

### 6.3 查询某个分区的流域

```python
basins = grid.getBasinListFromZone("鄂西")  # 查询鄂西分区下所有流域
```

### 6.4 查询水电所属流域

```python
hydro = hydro_units[0]  # 取出一个水电资源对象
zone = grid.zones[hydro.zoneId]  # 找到水电所属分区
basin = zone.basinDict[hydro.basinId]  # 根据水电 basinId 找到对应 Basin
```

### 6.5 查询储能和抽蓄

```python
storage_units = grid.getResListFromType("STORAGE")  # 查询所有储能和抽蓄资源
```

### 6.6 查询风电和光伏

```python
wind_units = grid.getResListFromType("WIND")  # 查询所有风电资源
pv_units = grid.getResListFromType("PV")  # 查询所有光伏资源
```

---

## 7. 成员五如何使用 Grid

成员五主要负责应用集成、年度运行、结果输出和物理校验。

### 7.1 输出 Grid 摘要

```python
summary = grid.summary()  # 获取 Grid 摘要字典
print(summary)  # 打印 Grid 摘要
```

### 7.2 遍历所有资源

```python
for resource_id, resource in grid.resources.items():  # 遍历 Grid 中所有资源
    print(resource_id, resource.type, resource.zoneId, resource.capacity)  # 打印资源 ID、类型、分区和容量
```

### 7.3 遍历所有分区

```python
for zone_id, zone in grid.zones.items():  # 遍历 Grid 中所有分区
    print(zone_id, len(zone.resKeyList), len(zone.inFlow), len(zone.outFlow))  # 打印分区资源数、流入线数、流出线数
```

### 7.4 校验资源分区关系

```python
for resource_id, resource in grid.resources.items():  # 遍历每个资源对象
    assert resource.zoneId in grid.zones  # 检查资源所属分区是否存在
```

### 7.5 校验联络线分区关系

```python
for intertran_id, intertran in grid.intertrans.items():  # 遍历每条联络线
    assert intertran.fromZone in grid.zones  # 检查联络线起始分区是否存在
    assert intertran.toZone in grid.zones  # 检查联络线终止分区是否存在
```

---

## 8. 当前真实湖北 2030 Grid 摘要

当前真实 loader 集成测试输出如下：

| 指标 | 数量 |
|---|---:|
| Grid ID | `HUBEI2030` |
| 分区数量 | 3 |
| 联络线数量 | 3 |
| 资源总数 | 608 |
| 火电数量 | 134 |
| 水电数量 | 322 |
| 储能/抽蓄数量 | 143 |
| 负荷数量 | 3 |
| 风电数量 | 3 |
| 光伏数量 | 3 |

对应 `grid.summary()` 输出：

```python
{
    "grid_id": "HUBEI2030",
    "num_zones": 3,
    "num_intertrans": 3,
    "num_resources": 608,
    "num_thermal": 134,
    "num_hydro": 322,
    "num_storage": 143,
    "num_wind": 3,
    "num_pv": 3,
    "num_load": 3,
}
```

---

## 9. 当前测试结果

当前成员二 Grid 构建模块已经通过以下测试：

| 测试文件 | 测试数量 | 说明 |
|---|---:|---|
| `test_grid_builder_minimal.py` | 10 passed | Fake CaseData 单元测试、基础异常测试、风光荷和抽蓄测试 |
| `test_grid_builder_with_loader.py` | 2 passed | 真实湖北 2030 loader 集成测试、真实 Grid 对象关联校验 |
| 合计 | 12 passed | 成员二 Grid 构建模块第一版可交付 |

---

## 10. 当前已经完成的对象关联校验

真实 Grid 已经通过以下关联校验：

- 每个资源都能找到所属分区
- 每个 `Zone.resKeyList` 都指向真实资源
- 每条联络线的 `fromZone` 和 `toZone` 都存在
- 每个 `Zone.inFlow` 和 `Zone.outFlow` 都指向真实联络线
- 每个水电资源都能找到所属 `Basin`
- 每个水电资源都已经挂到 `Basin.hydroDict` 下

---

## 11. 当前接口使用注意事项

### 11.1 ID 前缀规则

当前对象 ID 采用旧程序风格，会自动带类型前缀。

| 原始 ID | Grid 中实际 ID |
|---|---|
| `thermal_001` | `THERMALthermal_001` |
| `hydro_001` | `HYDROhydro_001` |
| `storage_001` | `STORAGEstorage_001` |
| `line_001` | `INTERTRANline_001` |
| `basin_001` | `BASINbasin_001` |
| `鄂东` 负荷 | `LOAD鄂东` |
| `鄂东` 风电 | `WIND鄂东` |
| `鄂东` 光伏 | `PV鄂东` |

### 11.2 查询资源时推荐用接口，不推荐直接拼 ID

推荐：

```python
thermal_units = grid.getResListFromZoneAndType("鄂东", "THERMAL")  # 推荐：按分区和类型查询火电
```

不推荐：

```python
thermal = grid.resources["THERMALxxx"]  # 不推荐：直接依赖具体 ID 字符串
```

### 11.3 成员二对象层不负责优化变量

成员二只提供对象和查询接口，不负责：

- 创建优化变量
- 添加约束
- 调用求解器
- 输出最终优化结果

这些由成员三、成员四、成员五在自己的模块中完成。

---

## 12. 推荐给其他成员的调用方式

最推荐其他成员这样使用：

```python
case_data = load_case(str(config_path))  # 成员一读取数据，得到 CaseData
grid = build_grid(case_data)  # 成员二构建 Grid
thermal_units = grid.getResListFromType("THERMAL")  # 成员三查询火电
hydro_units = grid.getResListFromType("HYDRO")  # 成员四查询水电
storage_units = grid.getResListFromType("STORAGE")  # 成员四查询储能和抽蓄
load_units = grid.getResListFromType("LOAD")  # 成员三或成员五查询负荷
wind_units = grid.getResListFromType("WIND")  # 成员四查询风电
pv_units = grid.getResListFromType("PV")  # 成员四查询光伏
```

---

## 13. 当前结论

成员二 Grid 构建模块第一版已经可交付。成员三、成员四、成员五可以基于 `Grid` 查询分区、资源、联络线和流域，继续编写火电约束、水电约束、储能约束、新能源约束、分区平衡约束和结果校验逻辑。
