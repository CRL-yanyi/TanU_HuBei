from dataclasses import dataclass  # 引入 dataclass 装饰器，用于消除样板代码，自动生成 __init__、__repr__ 等方法

@dataclass  # 使用数据类装饰器，声明这是一个纯数据容器对象（符合对象层不写优化逻辑的原则）
class Intertran:  # 定义跨区传输线路（或称联络线、断面）类
    id: str  # 线路或断面的唯一标识符（ID）
    fromZone: str  # 起始分区（发送端）的 ID，用于建立与其他 Zone 对象的拓扑关联
    toZone: str  # 目标分区（接收端）的 ID
    status: int = 1  # 线路运行状态：通常 1 代表投运（可用），0 代表停运/检修，默认值为 1
    type: str = "DC"  # 线路类型：如 "DC" (直流) 或 "AC" (交流)，默认值为直流
    lossRate: float = 0.0  # 线路的传输损耗率，通常为小数（例如 0.05 表示 5% 的线损率）
    cost: float = 0.0  # 传输的网损成本或过网费参数（参与目标函数计算时的经济属性）
    isPU: bool = False  # 参数是否采用标幺值 (Per Unit) 系统的标志，False 表示默认使用实际物理单位（如 MW）
    capacityToZone: float = 0.0  # 正向传输容量上限（即从 fromZone 流向 toZone 的最大功率，单位通常为 MW）
    capacityFromZone: float = 0.0  # 反向传输容量上限（即从 toZone 流向 fromZone 的最大功率，单位通常为 MW）

    def __post_init__(self):  # dataclass 提供的数据初始化后置钩子方法，在实例创建后自动执行
        if not self.id.startswith("INTERTRAN"):  # 检查传入的 ID 是否带有标准的前缀
            self.id = "INTERTRAN" + str(self.id)  # 如果没有，强制为其添加 "INTERTRAN" 前缀，保证 Grid 中对象命名规范统一