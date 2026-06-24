from dataclasses import dataclass, field


@dataclass
class Resource:
    id: str
    zoneId: str
    type: str
    name: str = ""
    capacity: float = 0.0
    isSeries: bool = False
    isPU: bool = False
    Pmin: float = 0.0
    Pmax: float = 0.0


@dataclass
class Thermal(Resource):

    mustRun: bool = False
    startUpCost: float = 0.0
    shutDownCost: float = 0.0
    shutDownCapacity: float = 0.0
    startUpCapacity: float = 0.0
    rampUp: float = 0.0        # 上爬坡能力，单位 MW/h
    rampDown: float = 0.0      # 下爬坡能力，单位 MW/h
    minON: int = 0             # 最小开机时间，单位小时
    minOFF: int = 0            # 最小停机时间，单位小时
    initT: int = 0             # 初始开停机持续时间
    initialPower: float | None = None
    ONOFF: dict = field(default_factory=dict)
    fuelType: str = "COAL"

    # 对齐成员一 loader 处理后的火电变动成本，单位 元/MWh。
    variableCost: float = 0.0


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

    isSeries: bool = True
    curtailmentPenalty: float = 100000.0
