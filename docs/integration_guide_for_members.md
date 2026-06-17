<<<<<<< HEAD
# TanU_Hubei 项目集成与数据对接指南 (给成员 2-5 的指导意见)

本指南旨在为 **成员二（对象层）**、**成员三（火电层）**、**成员四（水电储能新源层）** 和 **成员五（系统集成层）** 提供清晰的数据对接、物理单位约定、算法推导说明以及多场景与滚动计算的协同指导，以确保首期单场景及后续 8760 小时生产模拟的顺利打通。

---

## 1. 数据层公共接口调用说明 (给 成员五)

成员五在集成 `run_production_sim` 应用或编写集成测试时，应直接使用成员一交付的加载与校验接口，无需接触任何 Excel 底层文件。

### 1.1 基础调用流程
```python
from src.data.config import TimeConfig, load_case_config
from src.data.loader import load_case, validate_case_data

# 1. 载入算例配置
config_path = "configs/cases/hubei2030.yaml"
# 2. 定义模拟的时段窗口（日前 24h 切片示例：起止小时为 0~23）
time_config = TimeConfig(start_hour=0, end_hour=23)

# 3. 一键载入指定时段和场景的算例数据 (以载入第 1 号场景为例)
case_data = load_case(config_path, time_config=time_config, scenario=1)

# 4. 对载入的数据进行完整性与物理边界校验
report = validate_case_data(case_data)
if not report.is_valid:
    print(f"数据校验未通过！错误原因：{report.errors}")
    # 根据分工原则，不可在应用层绕过错误，需及时反馈给成员一修复数据源
=======
# TanU_Hubei 项目数据对接指南 (给成员二的指导意见)

本指南旨在为 **成员二（对象层）** 提供清晰的数据对接、物理单位约定以及实体对象构建规范，以帮助您理解成员一（数据层）交付的 `CaseData` 容器数据，并顺利将 DataFrame 表格映射组装为规范的电网与资源实体对象（如 `Grid`、`ThermalUnit` 等）。

---

## 1. 数据层公共接口与架构流向

在本项目分层设计中，成员二作为**连接“原始数据”与“数学优化建模”的桥梁**，其主要工作流向如下：

```mermaid
flowchart LR
    A[成员一: load_case] -->|输出 CaseData 容器| B[成员二: build_grid]
    B -->|组装出 Grid 和实体对象| C[成员三、四、五: 优化建模与系统集成]
```

### 1.1 基础装载与调用示例
在集成测试或运行主入口中，成员五将首先调用成员一的数据加载接口，接着将生成的 `CaseData` 传递给您（成员二）的对象构建器：

```python
from src.data.config import TimeConfig
from src.data.loader import load_case, validate_case_data

# 1. 配置时间窗口
time_config = TimeConfig(start_hour=0, end_hour=23)

# 2. 一键载入指定时段和场景的算例数据
case_data = load_case("configs/cases/hubei2030.yaml", time_config=time_config, scenario=1)

# 3. 对载入的数据进行校验 (确保无物理或逻辑边界错误)
report = validate_case_data(case_data)
if not report.is_valid:
    raise ValueError(f"数据初验未通过: {report.errors}")

# 4. 【核心调用】：将校验通过的 case_data 传递给成员二的构建器
# grid = build_grid(case_data) 
>>>>>>> dev
```

---

<<<<<<< HEAD
## 2. `CaseData` 容器数据规范与消费指引 (给 成员二、三、四)

成员二构建 `Grid` 及其子对象时，将直接消费 `CaseData` 中的各类 DataFrame 与 Dict。请注意以下字段和单位约定：

### 2.1 统一的物理单位约定 (全员必须严格遵守)
为了避免优化模型中的物理量单位错乱，所有原始表格中的单位在加载阶段已被统一转换为以下**国际/行业标准单位**：

| 物理量类别 | 转换前原始单位 | 转换后统一单位 (CaseData) | 适用字段示例 |
| --- | --- | --- | --- |
| **功率/出力上限/下限** | 万千瓦 或 MW | **MW (兆瓦)** | `p_max_mw` / `p_min_mw` / `limit_mw` |
| **能量/电量容量** | 万千瓦时 或 MWh | **MWh (兆瓦时)** | `energy_capacity_mwh` |
| **电价 / 经济成本** | 元/千瓦时 或 元/kWh | **元/MWh** | `fuel_cost_per_mwh` / `vom_cost_per_mwh` |
| **效率 / SOC / 备用率** | 百分比 (%) | **标幺值 (0.0 ~ 1.0)** | `efficiency` / `init_soc` / `load_reserve_rate` |
| **时间尺度** | 小时 / 天 | **小时 (Hour)** | `min_up_time_h` / `min_down_time_h` |

### 2.2 ⚠️ 关键衍生数据与属性补齐说明 (重点阅读)
加载器在读取常规储能和抽水蓄能数据时，自动推导并补齐了部分原始文件中**缺失**的物理属性。消费这些 DataFrame 时，请注意：

1. **常规储能的分区补齐 (`zone_name`)**：
   * **现状**：原始 `储能机组.xls` 中**不含分区列**。
   * **实现**：代码已通过常规储能机组的 `"所属电网"` 字段，自动使用地名关键字（如 "武汉" -> "鄂东"）动态生成了 `"zone_name"` (所属分区) 列。
   * **指引 (成员二)**：构建 `StorageUnit` 对象时，直接读取 `case_data.storage_units['zone_name']` 即可，可完美与其所属分区 `Zone` 对象进行拓扑绑定。
2. **储能与抽蓄的效率标幺化 (`charge_efficiency` & `discharge_efficiency`)**：
   * **现状**：原始表格中分别为百分比数值（如 90%）。
   * **实现**：代码已将其转换为 0.0 ~ 1.0 的标幺值（如 0.90）。
   * **指引 (成员四)**：储能 SOC 状态更新方程中，充电时效率应使用 `charge_efficiency`（乘以充电功率），放电时效率应使用 `discharge_efficiency`（除以放电功率）。
3. **额定容量自动补齐 (`energy_capacity_mwh`)**：
   * **现状**：原始表格中**不含额定容量**。
   * **实现**：加载器已自动执行乘积计算：容量 = 功率 * 充/抽水时间，生成了该列。
   * **指引 (成员四)**：储能最大 SOC 限制中，容量上限请直接读取 `energy_capacity_mwh`。
4. **火电机组变动总成本 (`vom_cost_per_mwh`)**：
   * **现状**：原始 `火电机组.xls` 中变动运行费列为空，且无变动运维费。
   * **实现**：代码默认以 `0.35` 元/kWh（折合燃料成本 350 元/MWh）填充了空值，并与运维变动成本进行了叠加，存入 `vom_cost_per_mwh` 中。
   * **指引 (成员三)**：在构建火电机组的运行成本目标函数时，请直接读取并使用 `vom_cost_per_mwh` 作为机组出力的线性变动成本系数。

---

## 3. 多场景时序曲线加载机制 (给 成员四、五)

为支持首期及后续的多场景运行，时序加载器内置了**自动路径识别与回退机制**。

### 3.1 时序曲线的数据格式
* `case_data.load_curves` / `wind_curves` / `pv_curves` 均为 DataFrame 格式。
* 列名为分区名称（如 `"鄂东"`、`"鄂西"`、`"鄂西北"`），行索引为当前时间切片内的小时序号（如日前 24 小时切片时为 0~23）。
* 负荷曲线数值单位为 **MW**；风、光曲线数值为 **出力系数 (0.0 ~ 1.0)**。
* **指引 (成员四)**：新能源机组在 $t$ 时刻的可用出力上限，应为该机组的额定容量乘以对应分区在 $t$ 时刻的出力系数。

### 3.2 场景回退表现
* 当运行 `load_case(..., scenario=scenario_id)` 时，如果指定分区的特定场景时序文件（如 `鄂西北风1.xls`）不存在，代码会自动回退加载该分区的基准时序文件（如 `鄂西北风.xls`），不会触发文件未找到异常。
* **指引 (成员五)**：这允许您在集成测试时，直接循环 `scenario = 0 ~ 9` 进行多场景调度测试，系统会自动兼容已去重分区的场景回退。

---

## 4. 滚动年度运行状态传递指引 (给 成员五)

在打通 24 小时和 168 小时短周期模拟后，成员五需要通过滚动调度拼接出全年 8760 小时的运行结果。以下是状态跨窗口传递的交接要点：

1. **时间分片定位**：
   使用 `TimeConfig(start_hour, end_hour)` 进行向前滚动。例如，若按日滚动，窗口长度为 24h，第 1 天配置 `TimeConfig(0, 23)`，第 2 天配置 `TimeConfig(24, 47)`。加载器会自动截取时序数据并重置 DataFrame 索引为 0 开始，方便模型构建。
2. **状态参数传递继承**：
   为保证相邻滚动窗口在衔接处的物理连续性，必须在日前窗口求解完毕后，将期末状态写入下一个窗口的边界条件中：
   * **火电机组启停状态**：第 $N$ 窗口最后一个时刻机组的开关机状态、以及其已连续开/停的小时数，必须传递给第 $N+1$ 窗口作为初始启停状态，用以校验最小开机/停机时间约束（成员三主责约束）。
   * **储能机组 SOC**：第 $N$ 窗口最后一个时刻（例如第 23 小时）的期末储能 SOC 值，必须传递并赋值给第 $N+1$ 窗口的 `init_soc`（初始 SOC）作为边界值（成员四主责约束）。

---

## 5. 联络与集成建议

* **代码修改互审机制**：根据分工契约，当您拉取代码并调用 `CaseData` 遇到数据结构不适配时，请勿在您的本地代码或模型层硬写 Excel 解析或临时绕过，请将问题记录并反馈给**成员一**，由数据层更新加载器和配置文件，并通过 Pull Request 合并，从而保证项目“数据-对象-约束-求解”这一主链路的纯净与高度解耦。
=======
## 2. 数据层 (CaseData) 输入与转换规范

数据加载器已将原始表格中的所有非标准单位进行了统一换算，您在消费 `CaseData` 里的各类 DataFrame 时，必须严格遵循以下单位体系和字段含义。

### 2.1 统一的物理单位约定

| 物理量类别 | 转换前原始单位 | 转换后统一单位 (CaseData) | 适用字段示例 |
| --- | --- | --- | --- |
| **功率 / 出力上下限** | 万千瓦 或 MW | **MW (兆瓦)** | `p_max_mw` / `p_min_mw` / `limit_mw` |
| **能量 / 储能电量容量** | 万千瓦时 或 MWh | **MWh (兆瓦时)** | `energy_capacity_mwh` |
| **电价 / 经济运行成本** | 元/千瓦时 或 元/kWh | **元/MWh** | `fuel_cost_per_mwh` / `vom_cost_per_mwh` |
| **效率 / SOC / 备用率** | 百分比 (%) | **标幺值 (0.0 ~ 1.0)** | `charge_efficiency` / `init_soc` / `load_reserve_rate` |
| **时间尺度** | 小时 / 天 | **小时 (Hour)** | `min_up_time_h` / `min_down_time_h` |

### 2.2 CaseData 容器内各数据表字段字典

#### 2.2.1 分区表 (`case_data.zones`)
* `zone_name` (str): 分区唯一名称（如 "鄂东", "鄂西", "鄂西北"）
* `load_reserve_rate` (float): 负荷备用率（标幺值，如 0.03）
* `contingency_reserve_rate` (float): 事故备用率（标幺值）
* `spinning_reserve_rate` (float): 事故热备用比例（标幺值）
* `non_spinning_reserve_rate` (float): 事故冷备用比例（标幺值）
* `security_power_mw` (float): 保安电源容量（MW）
* `inter_regional_support_rate` (float): 跨区调剂比例

#### 2.2.2 火电机组表 (`case_data.thermal_units`)
* `unit_id` (str): 全局唯一机组编码
* `plant_name` (str): 所属厂站名称
* `zone_name` (str): 所属分区名称
* `p_max_mw` (float): 额定最大出力（MW）
* `p_min_mw` (float): 最小技术出力（MW）
* `min_up_time_h` (float): 最小连续运行时间（h）
* `min_down_time_h` (float): 最小连续停机时间（h）
* `ramp_rate_mw_per_min` (float): 爬坡速率（MW/min）
* `fuel_cost_per_mwh` (float): 燃料成本（元/MWh，已由 元/kWh 乘 1000 转换而来）
* `vom_cost_per_mwh` (float): 变动总成本（元/MWh，已由默认燃料与变动运维成本叠加所得）

#### 2.2.3 储能机组表 (`case_data.storage_units`) 与 抽蓄机组表 (`case_data.pumped_storage_units`)
* `unit_id` (str): 机组编码
* `zone_name` (str): 所属分区名称（**储能分区已由所属电网地名自动补齐，如 "武汉" -> "鄂东"**）
* `p_max_mw` (float): 额定最大充放电功率（MW）
* `energy_capacity_mwh` (float): 额定容量（MWh，**已由额定功率乘充电时间自动推导补齐**）
* `charge_efficiency` (float): 充电/抽水效率（标幺值，如 0.75）
* `discharge_efficiency` (float): 放电/发电效率（标幺值，如 0.75）
* `init_soc` (float): 初始电量比例（标幺值，默认值为 0.5）

#### 2.2.4 区域断面表 (`case_data.transmissions`)
* `line_name` (str): 断面名称
* `line_type` (str): 断面类型
* `zone_from` (str): 起点分区
* `zone_to` (str): 终点分区
* `limit_mw` (float): 正向极限输送功率（MW）

### 2.3 ⚠️ 关键衍生数据与属性补齐说明
数据加载器在读取原始文件时，自动为您执行了部分属性补齐，在构造实体对象时可以直接读取：
1. **储能所属分区 (`zone_name`) 自动推导**：原始储能表格中无分区列，代码已根据机组 `"所属电网"` 自动匹配映射为所属分区（如 "武汉" 映射为 "鄂东"）。
2. **额定容量 (`energy_capacity_mwh`) 自动乘积计算**：原始储能与抽蓄中无容量列，代码已通过功率与充放电时间相乘，自动补齐了该属性。
3. **效率标幺值化**：原始百分比（如 90%）均已被折算为 0.0 ~ 1.0 范围的标幺值（如 0.90）。

---

## 3. 对象层 (Grid & Resource Objects) 适配规范

成员二需要基于 `CaseData` 实例化具体的 Python 对象。推荐的属性契约示例如下：

```python
# 示例：火电机组对象定义
class ThermalUnit:
    def __init__(self, row: pd.Series):
        self.unit_id: str = row['unit_id']
        self.zone_name: str = row['zone_name']
        self.p_max: float = float(row['p_max_mw'])
        self.p_min: float = float(row['p_min_mw'])
        self.min_up_time: float = float(row['min_up_time_h'])
        self.min_down_time: float = float(row['min_down_time_h'])
        # 转换爬坡单位：将 MW/min 转换为优化模型使用的 MW/h
        self.ramp_up_limit: float = float(row['ramp_rate_mw_per_min']) * 60.0  
        self.ramp_down_limit: float = float(row['ramp_rate_mw_per_min']) * 60.0 
        self.startup_ramp: float = self.p_min   # 默认启动出力限制为最小技术出力
        self.shutdown_ramp: float = self.p_min  # 默认停机出力限制为最小技术出力
        self.vom_cost: float = float(row['vom_cost_per_mwh'])
        self.startup_cost: float = 0.0          # 可初始化为 0
        self.shutdown_cost: float = 0.0
```

> [!WARNING]
> 对象层的所有实体必须提供**干净的属性存取**，实体类中**严禁**包含任何数学规划求解库（如 PyOptInterface、Gurobi）变量、约束生成或文件 I/O 代码，以保证实体类具有极高的纯净性与可重用性。

---

## 4. Git 协作与数据安全守则

1. **严格禁止误提交原始数据**：
   本地 `datasets/hubei2030/` 下的原始 Excel 算例文件以及产生的 `*.lp`, `*.log` 文件已被 `.gitignore` 排除。在提 PR 前，必须使用 `git status` 确认没有误带入敏感的大文件。
2. **分支与 PR 规范**：
   - 特性分支统一命名为 `feature/<name>`。
   - 所有修改在合并前，必须由至少一名其他成员进行 Review，且必须通过本地全部单元测试（`pytest`）。
>>>>>>> dev
