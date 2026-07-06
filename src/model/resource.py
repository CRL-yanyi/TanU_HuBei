from dataclasses import dataclass, field


@dataclass
class Resource:
    id: str
    zoneId: str
    type: str
    name: str = ""
    capacity: float = 0.0
    isSeries: bool = False#数据是不是随时间变化的序列数据。
    isPU: bool = False#数据是不是标幺值
    Pmin: float = 0.0
    Pmax: float = 0.0


@dataclass
class Thermal(Resource):
    """火电机组静态参数、窗口初值和 ED 固定状态。"""

    # 火电运行状态和一次启停成本参数。
    mustRun: bool = False       # 是否强制开机；为 True 时可调用 must-run 约束固定开机
    startUpCost: float = 0.0    # 启动成本，单位 元/次
    shutDownCost: float = 0.0   # 停机成本，单位 元/次

    # 启动、停机过程中的特殊爬坡容量；为 0 时约束层按 Pmax 放宽处理。
    shutDownCapacity: float = 0.0  # 停机时允许保留的出力或停机爬坡容量
    startUpCapacity: float = 0.0   # 启动时允许达到的最大出力或启动爬坡容量
    rampUp: float = 0.0        # 上爬坡能力，单位 MW/h
    rampDown: float = 0.0      # 下爬坡能力，单位 MW/h

    # 最小连续开机/停机时间和滚动窗口初始状态。
    minON: int = 0             # 最小开机时间，单位小时
    minOFF: int = 0            # 最小停机时间，单位小时
    initT: int = 0             # 初始开停机持续时间；正数为已开机小时，负数为已停机小时
    initialPower: float | None = None  # 窗口开始前出力，缺省时由约束层按状态推导
    ONOFF: dict = field(default_factory=dict)  # ED 固定开停机状态，键可为时段或序号
    fuelType: str = "COAL"#燃料类型

    # 对齐数据加载器处理后的火电变动成本，单位 元/MWh。
    variableCost: float = 0.0
    linearCost: float | None = None  # 兼容 TanU 命名；未提供时使用 variableCost


@dataclass
class Hydro(Resource):
    """单台水电机组的静态参数及其所属流域。

    当前参考约束直接使用 ``Pmax`` 限制单机出力，并通过 ``basinId`` 找到
    流域后施加预想、强迫和月均电量约束。其余字段为既有模型兼容参数。
    """

    mustRun: bool = False  # 是否强制运行；当前水电参考约束暂不读取该字段。
    rampDown: float = 0.0  # 下爬坡能力，单位 MW/h；保留供扩展约束使用。
    rampUp: float = 0.0    # 上爬坡能力，单位 MW/h；保留供扩展约束使用。
    basinId: str = ""      # 所属流域 ID，用于将单机出力聚合到 Basin。
    ECapacity: float = 0.0  # 机组可用电量容量，单位 MWh；保留兼容旧数据。
    hydroType: str = "CONV"  # 水电类型，默认 CONV 表示常规水电。


@dataclass
class Storage(Resource):
    """普通储能或抽水蓄能的功率、能量和效率参数。"""

    # subtype 仅用于区分技术类型；当前两类资源共用同一套 2.4 约束。
    subtype: str = "BATTERY_STORAGE"
    Emax: float = 0.0       # 最大能量，单位 MWh
    Emin: float = 0.0       # 最小能量，单位 MWh
    E0: float = 0.0         # 建模窗口开始前的初始能量，单位 MWh
    EnT: float = 0.0        # 每个自然日最后时段的目标能量，单位 MWh
    effC: float = 1.0       # 充电效率，合法区间为 (0, 1]
    effD: float = 1.0       # 放电效率，合法区间为 (0, 1]


@dataclass
class Wind(Resource):
    """风电资源的时序、月装机容量和爬坡参数。"""

    isSeries: bool = True  # 风电可用功率随时间变化，需要场景时序。
    curtailmentPenalty: float = 500.0  # 弃风惩罚，单位 元/MWh。
    # 旧接口逐时标幺系数，键为时段；正式接口改由 ScenarioSet 提供。
    TSCapacity: dict = field(default_factory=dict)
    # 正式接口的装机容量，单位 MW；规范键为每个自然月的月首日期。
    monthly_capacity_mw: dict = field(default_factory=dict)
    rampUp: float = float("inf")    # 上爬坡能力，单位 MW/h；inf 表示不限制。
    rampDown: float = float("inf")  # 下爬坡能力，单位 MW/h；inf 表示不限制。


@dataclass
class PV(Resource):
    """光伏资源的时序、月装机容量和爬坡参数。"""

    isSeries: bool = True  # 光伏可用功率随时间变化，需要场景时序。
    curtailmentPenalty: float = 500.0  # 弃光惩罚，单位 元/MWh。
    # 旧接口逐时标幺系数，键为时段；正式接口改由 ScenarioSet 提供。
    TSCapacity: dict = field(default_factory=dict)
    # 正式接口的装机容量，单位 MW；规范键为每个自然月的月首日期。
    monthly_capacity_mw: dict = field(default_factory=dict)
    rampUp: float = float("inf")    # 上爬坡能力，单位 MW/h；inf 表示不限制。
    rampDown: float = float("inf")  # 下爬坡能力，单位 MW/h；inf 表示不限制。


@dataclass
class Load(Resource):
    """分区固定负荷及其逐时时序。"""

    # 负荷天然属于时序资源，因此加入 Grid 时会登记到 sceKeyList。
    isSeries: bool = True
    # 预留的负荷损失惩罚成本，当前目标函数暂未使用。
    curtailmentPenalty: float = 100000.0
    # 键为调度时段，值为 MW；若 isPU=True，则值为相对 capacity 的标幺值。
    TSCapacity: dict = field(default_factory=dict)  # 逐时负荷；isPU=True 时为标幺值


@dataclass
class Reserve(Resource):
    """系统旋转备用需求资源。"""

    # 备用需求随时段变化，也需要登记为 Grid 时序资源。
    isSeries: bool = True
    # 键为调度时段，值为 MW 或标幺备用需求。
    TSCapacity: dict = field(default_factory=dict)  # 逐时备用需求
