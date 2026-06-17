from __future__ import annotations  # 允许在类型标注里提前使用后面才定义的类名
from dataclasses import dataclass, field  # 导入 dataclass 和 field，用来快速定义数据类
@dataclass  # 声明 Zone 是一个数据类，Python 会自动生成初始化函数
class Zone:  # 定义分区对象，表示湖北电网中的一个区域
    id: str  # 分区唯一编号为字符串类型，例如 WH、EX、EZ 等
    name: str = ""  # 分区名称，例如武汉、鄂西、鄂东等，默认空字符串
    ## 定义字段：list[str]：类型注解，表示该字段是字符串列表，field()：dataclasses 专用字段配置函数，default_factory=list默认值为空列表，
    resKeyList: list[str] = field(default_factory=list)  # 保存该分区下所有资源 ID
    inFlow: list[str] = field(default_factory=list)  # 保存流入该分区的联络线 ID
    outFlow: list[str] = field(default_factory=list)  # 保存流出该分区的联络线 ID
    basinDict: dict[str, Basin] = field(default_factory=dict)  # 保存该分区下的流域对象
@dataclass  # 声明 Basin 是一个数据类
class Basin:  # 定义流域对象，主要给水电资源使用
    id: str  # 流域唯一编号，例如 BASIN001
    zoneId: str  # 流域所属分区 ID
    capacity: float = 0.0  # 流域总水电容量，单位 MW
    hydroDict: dict[str, object] = field(default_factory=dict)  # 保存该流域下的水电机组
    #dict[str, object]字典的键 必须是字符串 str。字典的值为任意类型 object（数字、字符串等）
    average: dict = field(default_factory=dict)  # 保存平均水电过程数据
    forced: dict = field(default_factory=dict)  # 保存强迫水电过程数据
    predicted: dict = field(default_factory=dict)  # 保存预想水电过程数据
    dayEnergy: dict = field(default_factory=dict)  # 保存日能量数据
