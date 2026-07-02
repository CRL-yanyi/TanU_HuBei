# 成员3：火电与系统核心约束接口契约

## 1. 设计原则

成员3优化代码采用 TanU 风格：

- 所有变量统一保存在 `OptModel.vars`；
- 变量键统一为 `(resource_id, period, variable_type, index)`；
- 约束函数直接接收 `OptModel`、资源对象和 `pandas.DatetimeIndex`；
- 每条约束同时登记到 `OptModel.cons` 和 `OptModel.cons_expr`；
- 参数从 `Grid`、`Thermal`、`Load`、`Reserve`、`Intertran` 读取；
- 优化层不读取 Excel，也不进行单位换算。

`OptModel` 支持 `GUROBI`、`COPT` 和 `HIGHS` 三种后端，默认使用 `GUROBI`。

## 2. 主要接口

| 功能 | 接口 |
|---|---|
| 火电变量 | `setThermalVarList(optmodel, gridData, timeIdx)` |
| 输电变量 | `setIntertranVarList(optmodel, gridData, timeIdx)` |
| 火电 UC | `setThermalUCCons(optmodel, gridData, timeIdx)` |
| 火电 ED | `setThermalEDCons(optmodel, gridData, timeIdx)` |
| 输电断面 | `setIntertranCons(optmodel, gridData, timeIdx)` |
| 分区平衡 | `setPowerBalanceCons(optmodel, gridData, timeIdx)` |
| 系统备用 | `setSystemReserveCons(optmodel, gridData, timeIdx)` |
| 火电目标 | `setThermalObjective(optmodel, gridData, timeIdx)` |

火电变量类型：

- `P`：火电出力；
- `CU`：开机状态；
- `CV`：启动状态；
- `CW`：停机状态。

例如：

```python
power = optmodel.getVar("G1", timeIdx[0], "P")
is_on = optmodel.getVar("G1", timeIdx[0], "CU")
```

## 3. 火电对象字段

成员3直接读取 `Thermal` 的以下字段：

| 字段 | 单位 | 说明 |
|---|---|---|
| `Pmin` / `Pmax` | MW | 最小、最大出力 |
| `minON` / `minOFF` | h | 最小开机、停机时间 |
| `rampUp` / `rampDown` | MW/h | 常规爬坡能力 |
| `startUpCapacity` / `shutDownCapacity` | MW | 启动、停机容量 |
| `initT` | h | 正数表示已开机时长，负数表示已停机时长 |
| `initialPower` | MW | 优化窗口开始前出力 |
| `ONOFF` | 0/1 序列 | ED 固定开停机状态 |
| `linearCost` / `variableCost` | 元/MWh | 线性发电成本，前者未提供时使用后者 |
| `startUpCost` / `shutDownCost` | 元/次 | 启动、停机成本 |

`timeIdx` 必须是 `pandas.DatetimeIndex`，爬坡、最小开停机时间和电量成本会由其频率自动换算。

## 4. UC 与 ED

`setThermalUCCons` 包含出力上下限、状态转换、启停互斥、初始剩余时间、最小开停机和爬坡约束。

`setThermalEDCons` 从 `Thermal.ONOFF` 固定 `CU/CV/CW`，再调用与 UC 相同的出力上下限和爬坡公式，不重复维护两套数学公式。

`mustRun` 属于可选约束，需要时对机组单独调用：

```python
setThermalConsMustRun(optmodel, thermal, timeIdx)
```

## 5. 成员4变量接入

功率平衡只从统一变量表取变量。成员4继续使用现有变量 dataclass 时，在添加功率平衡前登记一次：

```python
optmodel.registerVarList(hydro_variables.power, "P")
optmodel.registerVarList(renewable_variables.power, "P")
optmodel.registerVarList(storage_variables.charge_power, "P", "PC")
optmodel.registerVarList(storage_variables.discharge_power, "P", "PD")
```

功率平衡符号约定：发电和储能放电为正，储能充电和负荷为负，联络线在起点分区为负、终点分区为正。

固定负荷存放在 `Load.TSCapacity`；备用需求存放在 `Reserve.TSCapacity`。当 `isPU=True` 时，时序值乘以资源 `capacity` 转为 MW。

## 6. 推荐调用顺序

```python
optmodel = OptModel("dispatch", solver="GUROBI")
setThermalVarList(optmodel, grid, timeIdx)
setIntertranVarList(optmodel, grid, timeIdx)

setThermalUCCons(optmodel, grid, timeIdx)  # ED 时改用 setThermalEDCons
setIntertranCons(optmodel, grid, timeIdx)

# 添加成员4约束，并通过 registerVarList 登记成员4变量
setPowerBalanceCons(optmodel, grid, timeIdx)
setSystemReserveCons(optmodel, grid, timeIdx)
setThermalObjective(optmodel, grid, timeIdx)

optmodel.optimize()
```

目标函数应在全部成本项准备完成后统一设置，其他约束模块不调用 `model.set_objective()`。
