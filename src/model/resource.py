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

    # 对齐成员一 loader 处理后的火电变动成本，单位 元/MWh。
    variableCost: float = 0.0
    linearCost: float | None = None  # 兼容 TanU 命名；未提供时使用 variableCost


@dataclass
class Hydro(Resource):

    mustRun: bool = False
    rampDown: float = 0.0
    rampUp: float = 0.0
    basinId: str = ""
    ECapacity: float = 0.0
    hydroType: str = "CONV"


@dataclass
class Storage(Resource):

    subtype: str = "BATTERY_STORAGE"
    Emax: float = 0.0       # 最大能量，单位 MWh
    Emin: float = 0.0       # 最小能量，单位 MWh
    E0: float = 0.0         # 初始能量，单位 MWh
    EnT: float = 0.0        # 末端目标能量，单位 MWh
    effC: float = 1.0       # 充电效率，标幺值 0~1
    effD: float = 1.0       # 放电效率，标幺值 0~1


@dataclass
class Wind(Resource):

    isSeries: bool = True
    curtailmentPenalty: float = 500.0
    TSCapacity: dict = field(default_factory=dict)


@dataclass
class PV(Resource):

    isSeries: bool = True
    curtailmentPenalty: float = 500.0
    TSCapacity: dict = field(default_factory=dict)


@dataclass
class Load(Resource):
    """分区固定负荷及其逐时时序。"""

    # 负荷天然属于时序资源，因此加入 Grid 时会登记到 sceKeyList。
    isSeries: bool = True
    # 预留的负荷损失惩罚成本，本次成员3目标函数暂未使用。
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
