# 成员 3：火电与系统核心约束接口契约

## 1. 文档目的

本文说明成员 2、4、5 如何调用成员 3 提供的火电 UC、系统平衡、输电、备用和成本模块。

优化层只接收规范参数，不读取 Excel、不保存结果、不负责创建 `Grid`。

## 2. 当前实现

| 功能 | 文件 | 主要接口 |
|---|---|---|
| 火电变量 | `src/optim/variables.py` | `add_thermal_variables` |
| 输电变量 | `src/optim/variables.py` | `add_transmission_variables` |
| 火电约束 | `src/optim/constraints/thermal.py` | 容量、启停、最小开停机、爬坡 |
| 功率平衡 | `src/optim/constraints/power_balance.py` | `add_power_balance_constraints` |
| 断面限制 | `src/optim/constraints/transmission.py` | `add_transmission_limit_constraints` |
| 系统备用 | `src/optim/constraints/reserve.py` | `add_system_reserve_constraints` |
| 火电成本 | `src/optim/objectives.py` | `set_thermal_cost_objective` |

所有变量以 `(resource_id, period)` 为索引。

## 3. 成员 2 需要提供的火电字段

| 字段 | 单位 | 说明 |
|---|---|---|
| `unit_id` | 无 | 全局唯一机组编号 |
| `zone_name` | 无 | 所属分区 |
| `p_min_mw` | MW | 最小技术出力 |
| `p_max_mw` | MW | 最大出力 |
| `min_up_time_h` | h | 最小连续开机时间 |
| `min_down_time_h` | h | 最小连续停机时间 |
| `ramp_up_mw_per_h` | MW/h | 常规向上爬坡能力 |
| `ramp_down_mw_per_h` | MW/h | 常规向下爬坡能力 |
| `startup_ramp_mw` | MW | 启动时允许增加的出力 |
| `shutdown_ramp_mw` | MW | 停机时允许降低的出力 |
| `variable_cost_yuan_per_mwh` | 元/MWh | 线性发电成本 |
| `startup_cost_yuan` | 元/次 | 启动成本 |
| `shutdown_cost_yuan` | 元/次 | 停机成本 |

优化层不负责从百分比、标幺值或“万元”换算这些字段。

数据层或对象层还需为每个运行窗口提供：

- `initial_on`
- `initial_power_mw`
- `initial_on_hours`
- `initial_off_hours`

缺失参数不得在优化层静默填充，应由对应数据或对象模块处理。

## 4. 成员 4 接入功率平衡

水电、风电、光伏、储能放电和负荷损失变量作为 supply_groups 接入；储能充电、抽水及其他附加用电作为 demand_groups 接入。

```python
ZonalVariableGroup(
    variables=resource_power,
    resource_zones=resource_zones,
)
```

符号约定：

- 发电和储能放电为正供给；
- 储能充电和抽水为需求；
- 断面正方向为 `from_zone -> to_zone`；
- 起点分区减去断面功率，终点分区加上断面功率；
- 外来直流通过 `fixed_external_injection_mw` 接入。

当前成本函数只包含火电发电、启动和停机成本。弃风弃光及负荷损失惩罚仍需后续公共目标函数接口接入。

## 5. 成员 5 推荐调用顺序

1. 创建 PyOptInterface 模型；
2. 创建火电和输电变量；
3. 添加火电容量约束；
4. UC 模式添加启停转换和最小开停机约束；
5. 添加火电爬坡约束；
6. 调用成员 4 的水电、储能和新能源约束；
7. 添加输电断面限制；
8. 添加逐分区功率平衡；
9. 按配置添加系统备用；
10. 最后设置成本目标函数；
11. 调用求解器并提取结果。

目标函数必须最后统一设置，其他模块不应重复调用 `model.set_objective()`。

## 6. UC 与 ED 模式差异

| 内容 | UC | ED |
|---|---|---|
| `is_on` | 二进制决策 | 使用给定状态 |
| `startup`、`shutdown` | 决策变量 | 根据给定状态确定 |
| 启停转换 | 启用 | 状态变化时启用 |
| 最小开停机时间 | 启用 | 通常不启用 |
| 容量约束 | 启用 | 启用 |
| 爬坡约束 | 启用 | 启用 |
| 功率平衡、断面、备用 | 启用 | 启用 |
| 启停成本 | 计入 | 按运行约定处理 |

当前变量函数创建二进制启停变量，因此当前正式支持 UC。若需要真正的 LP 型 ED，应增加固定状态或连续变量模式，不能只在运行入口中临时绕过。

## 7. 滚动窗口状态

下一个窗口至少需要接收：

- 上一个窗口末时段的 `is_on`；
- 上一个窗口末时段的 `power`；
- 截至窗口末连续开机小时数；
- 截至窗口末连续停机小时数。

成员 5 负责提取和传递状态，成员 3 的约束函数负责消费这些初始参数。

## 8. 当前测试与限制

成员 3 当前已有 47 项测试，包括两台机组、三个时段的完整 UC 集成算例。

尚未完成：

- 与成员 2 的正式 `Grid` 和 `ThermalUnit` 对象适配；
- 弃风弃光和负荷损失惩罚成本；
- 真正的 LP 型 ED 变量模式；
- 湖北 24 小时和 168 小时真实数据联调。