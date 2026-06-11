from dataclasses import dataclass, field  # 导入 dataclass 和 field，用于定义资源数据类
@dataclass  # 声明 Resource 是一个基础资源类
class Resource:  # 定义所有资源的共同父类
    id: str  # 资源唯一编号，例如 THERMAL001、HYDRO001
    zoneId: str  # 资源所属分区 ID
    type: str  # 资源类型，例如 THERMAL、HYDRO、STORAGE、WIND、PV、LOAD
    name: str = ""  # 资源名称，默认空字符串
    capacity: float = 0.0  # 资源容量，单位 MW
    isSeries: bool = False  # 是否需要对应时序数据，例如负荷、风电、光伏通常为 True
    isPU: bool = False  # 是否使用标幺值，False 表示使用 MW、MWh 等有名值
    Pmin: float = 0.0  # 最小出力，单位 MW
    Pmax: float = 0.0  # 最大出力，单位 MW
@dataclass  # 声明 Thermal 是火电资源类
class Thermal(Resource):  # 定义火电机组对象
    mustRun: bool = False  # 是否必须运行，True 表示强制开机
    startUpCost: float = 0.0  # 启动成本，单位元
    shutDownCost: float = 0.0  # 停机成本，单位元
    shutDownCapacity: float = 0.0  # 停机爬坡相关容量，单位 MW
    startUpCapacity: float = 0.0  # 启动爬坡相关容量，单位 MW
    rampUp: float = 0.0  # 上爬坡能力，单位 MW/h
    rampDown: float = 0.0  # 下爬坡能力，单位 MW/h
    minON: int = 0  # 最小开机时间，单位小时
    minOFF: int = 0  # 最小停机时间，单位小时
    initT: int = 0  # 初始开停机持续时间，正数表示已开机，负数表示已停机
    fuelType: str = "COAL"  # 燃料类型，默认 COAL
@dataclass  # 声明 Hydro 是水电资源类
class Hydro(Resource):  # 定义水电机组对象
    mustRun: bool = False  # 是否必须运行，默认 False
    rampDown: float = 0.0  # 下爬坡能力，单位 MW/h
    rampUp: float = 0.0  # 上爬坡能力，单位 MW/h
    basinId: str = ""  # 所属流域 ID
    ECapacity: float = 0.0  # 水电能量容量，单位 MWh
    hydroType: str = "CONV"  # 水电类型，默认常规水电
@dataclass  # 声明 Storage 是储能资源类
class Storage(Resource):  # 定义储能或抽蓄对象
    Emax: float = 0.0  # 最大能量，单位 MWh
    Emin: float = 0.0  # 最小能量，单位 MWh
    E0: float = 0.0  # 初始能量，单位 MWh
    EnT: float = 0.0  # 末端目标能量，单位 MWh
    effC: float = 1.0  # 充电效率，0 到 1
    effD: float = 1.0  # 放电效率，0 到 1
@dataclass  # 声明 Wind 是风电资源类
class Wind(Resource):  # 定义风电资源对象
    isSeries: bool = True  # 风电需要时序数据，所以默认 True
    curtailmentPenalty: float = 500.0  # 弃风惩罚成本，单位元/MWh
    TSCapacity: dict = field(default_factory=dict)  # 分月或分时容量，单位 MW
@dataclass  # 声明 PV 是光伏资源类
class PV(Resource):  # 定义光伏资源对象
    isSeries: bool = True  # 光伏需要时序数据，所以默认 True
    curtailmentPenalty: float = 500.0  # 弃光惩罚成本，单位元/MWh
    TSCapacity: dict = field(default_factory=dict)  # 分月或分时容量，单位 MW
@dataclass  # 声明 Load 是负荷资源类
class Load(Resource):  # 定义负荷对象
    isSeries: bool = True  # 负荷需要时序数据，所以默认 True
    curtailmentPenalty: float = 100000.0  # 切负荷惩罚成本，单位元/MWh
