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
```

---

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
