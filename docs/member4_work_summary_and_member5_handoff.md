# 成员四工作总结与成员五交接说明

## 1. 文档目的

本文以 `docs/task_division.md` 为工作分工和验收依据，记录成员四负责的水电、
储能、抽水蓄能、风电、光伏和场景约束工作，并记录成员四在交接检查中发现、
代为修复的成员一至成员三接口问题。

本文同时作为成员五继续完成生产模拟应用、结果输出、滚动调度和湖北8760小时
年度运行的交接文档。

## 2. 当前结论

截至2026年7月6日，成员一至成员四向运行应用提供的功能接口已经完成收口：

- 湖北真实24小时数据能够加载并通过增强后的数据校验；
- `CaseData`、Grid和全部时序统一使用 `pandas.DatetimeIndex`；
- 负荷、风电、光伏时序及月装机容量已进入Grid；
- 水电流域三段式数据已完整挂接；
- 火电、水电、储能、风光、联络线、失负荷变量能够登记到统一 `OptModel`；
- 水电、储能和新能源公式已按TanU参考模型完成；
- 非火电变量能够被现有分区功率平衡和完整生产目标函数读取；
- 真实湖北24小时成员一至四模型能够完成构建；
- 专项交付门禁结果为 `PASS`，外部阻塞数为0。

这里的“完成”指成员一至四功能与交接接口完成，不表示湖北8760小时运行结果已经
产生。运行应用、滚动窗口编排、结果拼接和年度物理校验仍属于成员五工作。

## 3. 检查依据

问题判断不是只依赖TanU参考项目，而是同时使用以下四类证据：

1. **分工依据**：`docs/task_division.md` 中各成员任务、公共接口和验收标准；
2. **TanU依据**：参考项目的水电2.3、储能2.4、新能源2.5及目标函数；
3. **代码依据**：当前项目加载器、Grid、OptModel、功率平衡和目标函数的实际接口；
4. **运行依据**：真实湖北数据预检、手算案例、求解器状态和全量回归结果。

## 4. 初始检查发现及代为修复情况

### 4.1 成员一：数据、配置与校验

| 初始问题 | 证据 | 成员四代为修复 | 修复结果 |
| --- | --- | --- | --- |
| 时序切片后重置为整数索引 | `loader.py` 使用 `reset_index(drop=True)`，而正式约束要求 `DatetimeIndex` | 为 `TimeConfig` 增加规范时间轴；所有负荷、风光和直流时序使用同一时间索引 | 24小时及非零起始小时均能保持正确绝对时间 |
| 配置中的负荷、风电和光伏装机表没有读取 | YAML已有 `load_spec`、`wind_spec`、`pv_spec`，但加载器未使用 | 增加字段映射并读取三类容量参数 | 分区最大负荷及风光12个月容量进入 `CaseData` |
| 流域文件名被去掉“鄂”导致无法关联 | 水电机组表为“鄂三峡”等，流域过程键变成“三峡”等 | 保留规范流域名称，并统一月度日期键 | 25份过程表均能匹配，28个含水电流域对象全部获得过程数据 |
| 数据校验错误放行关键空字段 | 原校验返回有效，但Grid内负荷、风光时序和流域过程为空 | 增强时间、容量、场景、流域覆盖及系数顺序校验 | 缺失容量、缺失月份和冲突流域过程能够明确失败 |

### 4.2 成员二：资源对象与Grid构建

| 初始问题 | 证据 | 成员四代为修复 | 修复结果 |
| --- | --- | --- | --- |
| Load只有对象，没有逐时数据和真实峰值容量 | `Load.TSCapacity`为空，capacity取标幺曲线最大值 | 使用负荷参数表设置MW容量，标幺曲线写入 `TSCapacity` | 功率平衡能够按时段读取真实MW负荷 |
| Wind/PV没有时序和月装机 | `TSCapacity`、`monthly_capacity_mw`均为空 | 挂接分区逐时标幺曲线和12个月装机容量 | 正式新能源约束可以直接计算可用出力 |
| 同名流域可能跨多个分区，只挂接第一个 | Grid查找函数只返回一个Basin | 同一流域过程挂接到所有匹配分区Basin | 跨分区同名流域均具备完整过程 |

### 4.3 成员三：系统平衡和目标函数

| 初始问题 | 证据 | 成员四代为修复 | 修复结果 |
| --- | --- | --- | --- |
| 目标函数只有火电成本 | `objectives.py` 仅实现 `setThermalObjective` | 新增 `setProductionObjective` | 火电、弃风弃光和失负荷成本统一进入目标 |
| 没有统一失负荷变量 | 分工要求负荷损失惩罚，现有变量表没有对应变量 | 新增 `setLoadSheddingVarList`，变量键为 `P/shed` | 失负荷可进入平衡和目标，且不超过逐时需求 |
| 功率平衡不能接收固定外来电 | 现有接口只读取省内资源和联络线 | 增加可选 `fixed_external_injection_mw[(zone, timestamp)]` | 成员五可按MW传入各分区外来电注入 |

### 4.4 成员四：非火电资源建模

成员四初始实现已有水储风光变量和约束原型，但与TanU参考模型、当前统一
`OptModel`、真实时间索引和成员五滚动运行接口尚未完全一致。本轮完成了完整重构、
参考公式追踪、兼容入口保留、真实数据预检和交付门禁。

## 5. 成员四完成的核心模型

### 5.1 变量接口

正式接口统一登记到 `OptModel.vars`：

| 资源 | 变量 | 含义 | 单位 |
| --- | --- | --- | --- |
| 水电 | `P` | 单机实际出力 | MW |
| 储能/抽蓄 | `P/PC` | 充电功率 | MW |
| 储能/抽蓄 | `P/PD` | 放电功率 | MW |
| 储能/抽蓄 | `E` | 时段末能量 | MWh |
| 储能/抽蓄 | `CS` | 充电状态 | 0/1 |
| 储能/抽蓄 | `DS` | 放电状态 | 0/1 |
| 风电/光伏 | `P` | 实际出力 | MW |
| 风电/光伏 | `P/curt` | 弃电功率 | MW |
| 负荷 | `P/shed` | 失负荷功率 | MW |

阿杰此前编写的 `add_hydro_variables`、`add_storage_variables` 和
`add_renewable_variables` 仍作为旧测试兼容入口保留；正式集成使用 `set*VarList`。

### 5.2 水电约束

与TanU `hydromodel.py` 对应：

- 单机出力：`0 <= P(h,t) <= Pmax(h)`；
- 2.3.1：流域总出力不超过预想系数乘流域容量；
- 2.3.2：流域总出力不低于强迫系数乘流域容量；
- 2.3.3：自然月累计电量满足月平均过程；
- 不额外增加参考项目不存在的单机 `Pmin` 硬约束；
- 强制校验 `0 <= 强迫 <= 平均 <= 预想 <= 1`；
- 使用“分区+流域”作为唯一约束所有者，避免跨区同名流域覆盖。

滚动运行接口允许成员五传入：

```python
prior_month_energy_mwh[(basin_owner, year, month)]
closed_months={(year, month)}
```

未关闭月份只累计已保留时段电量；月份关闭时使用此前累计电量和当前窗口变量共同
完成整月电量等式。

### 5.3 储能与抽蓄约束

与TanU `storagemodel.py` 对应：

```text
PC(t) <= CS(t) * Pmax
PD(t) <= DS(t) * Pmax
CS(t) + DS(t) <= 1
Emin <= E(t) <= Emax
E(t) = E(t-1) + [PC(t)*effC - PD(t)/effD] * Δt
E(日末) = EnT
```

普通储能和抽水蓄能共用该数学行为，通过 `subtype` 区分技术类型。正式接口的
`initial_energy` 参数允许成员五传入上一窗口边界能量，且不会修改Grid原始 `E0`。

### 5.4 风电和光伏约束

与TanU `renewablemodel.py` 对应：

```text
available(t) = scenario_factor(t) * monthly_capacity_mw(month)
P(t) + Pcurt(t) = available(t)
P(t) - P(t-1) <= rampUp * Δt
P(t-1) - P(t) <= rampDown * Δt
```

跨月窗口自动切换月装机容量，15分钟等非整小时场景按实际时间步长缩放爬坡能力。

### 5.5 单场景接口

`ScenarioSet.from_case_data(grid, case_data, scenario_id)` 负责把分区风光曲线转换为
按资源ID组织的数据表：

```text
行：DatetimeIndex
列：WIND鄂东、WIND鄂西、PV鄂东等资源ID
值：逐时非负标幺系数
```

当前模型只允许一个概率为1的场景，但保留场景ID、概率和时序结构，不在约束中
硬编码场景名称。

## 6. 成员五正式接入顺序

成员五应以正式接口为主，不再以整数时段和旧 `add_*` 入口作为生产接口：

```python
case_data = load_case(case_config_path, time_config, scenario=0)
report = validate_case_data(case_data)
grid = build_grid(case_data)
time_idx = case_data.time_index
scenario_set = ScenarioSet.from_case_data(grid, case_data)

optmodel = OptModel(solver="GUROBI")

setThermalVarList(optmodel, grid, time_idx)
setHydroVarList(optmodel, grid, time_idx)
setStorageVarList(optmodel, grid, time_idx)
setRenewableVarList(optmodel, grid, time_idx)
setIntertranVarList(optmodel, grid, time_idx)
setLoadSheddingVarList(optmodel, grid, time_idx)

setThermalUCCons(optmodel, grid, time_idx)
setHydroConstraints(optmodel, grid, time_idx, ...)
setStorageConstraints(optmodel, grid, time_idx, ...)
setRenewableConstraints(optmodel, grid, time_idx, scenario_set, "BASE")
setIntertranCons(optmodel, grid, time_idx)
setPowerBalanceCons(
    optmodel,
    grid,
    time_idx,
    include_load_shedding=True,
    fixed_external_injection_mw=external_injection,
)
setProductionObjective(
    optmodel,
    grid,
    time_idx,
    include_load_shedding=True,
)
```

外来电映射必须由成员五在运行层根据配置和 `case_data.dc_flows` 换算为MW后传入，
不得重新在功率平衡模块硬编码通道名称。

## 7. 验证机制与结果

### 7.1 专项交付门禁

运行：

```powershell
D:\ZMAPP\anconda\envs\pytorch_newest\python.exe test\validate_nonthermal_delivery.py
```

当前结果：

```text
Delivery decision: PASS
专项测试数量: 22
失败: 0
错误: 0
外部阻塞: 0
最大功率平衡残差: 0.000e+00
重复求解差异: 0.000e+00
```

专项测试覆盖：

- 场景接口和多分区资源映射；
- 水电2.3.1—2.3.3、缺参、冲突过程、跨月及滚动月累计；
- 储能2.4.1—2.4.6、效率矩阵、15分钟SOC、互斥和窗口状态；
- 新能源2.5.1—2.5.3、跨月容量、弃电及爬坡；
- 与分区功率平衡的两分区联调；
- 失负荷、固定外来电和完整目标函数；
- 真实湖北24小时数据、Grid、ScenarioSet及成员一至四模型构建。

### 7.2 全量回归

运行：

```powershell
D:\ZMAPP\anconda\envs\pytorch_newest\python.exe -m pytest -q -p no:cacheprovider
```

最终结果：

```text
85 passed
3 subtests passed
12 warnings
0 failures
```

12条警告均来自真实Grid有意跳过四条外部输电通道；这些通道由成员五按固定外来电
注入处理，不属于省内普通联络线，也不是测试失败。

## 8. 对照整体里程碑的当前进展

| 里程碑 | 当前状态 | 说明 |
| --- | --- | --- |
| M0 接口冻结 | 基本完成 | 正式接口已统一为 `OptModel + DatetimeIndex + ScenarioSet` |
| M1 数据到Grid | 完成 | 真实24小时数据、容量、时序和流域关联通过检查 |
| M2 24小时生产模拟闭环 | 成员一至四完成 | 模型能够构建；求解、结果提取和物理报告由成员五完成 |
| M3 湖北168小时 | 未开始 | 成员五运行后，全体按责任模块分析结果 |
| M4 滚动8760小时 | 接口已准备，应用未实现 | 水储状态契约已提供，滚动编排和结果拼接属于成员五 |
| M5 首期验收 | 未开始 | 需完成年度运行、交叉审核、PR和合并 |

## 9. 成员五剩余工作

成员五可以在当前接口基础上开始以下工作：

1. 填写 `configs/runs/production_base.yaml`；
2. 将成员五运行分支迁移到正式 `set*` 和 `DatetimeIndex` 接口；
3. 实现固定外来电MW注入映射；
4. 构建统一生产模拟应用和 `SimulationResult`；
5. 提取火电、水电、储能、风光、失负荷和联络线逐时结果；
6. 实现结果物理校验、指标、输出和运行日志；
7. 先运行湖北24小时，再运行168小时；
8. 实现滚动窗口中火电、储能和水电状态传递；
9. 拼接并校验8760小时结果，保证无重复和缺失时段。

成员五远程分支现有运行骨架仍使用旧 `add_* + 整数时段` 接口，不能原样作为最终
集成版本，需要按本文件第6节迁移。

## 10. 当前已知但不属于错误的警告

Grid构建时会提示四条外部输电通道未作为省内普通联络线加入Grid。这是有意行为：
这些通道应由成员五通过 `case_data.dc_flows` 转换成固定分区注入，再传给功率平衡，
不应伪装成省内可控联络线。

## 11. Git与交付状态

- 当前工作分支：`feature/member4_recoding`；
- 工作区保持未提交，供负责人在PyCharm中检查；
- 未修改、未提交 `湖北2030/` 原始资料；
- 尚未完成指定成员审核和合并到 `dev`；
- 负责人确认后自行创建提交和Pull Request。
