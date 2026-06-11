from dataclasses import dataclass, field  # 导入 dataclass 和 field，用于定义 Grid 数据类
from src.model.zone import Zone, Basin  # 导入 Zone 和 Basin 对象
from src.model.intertran import Intertran  # 导入 Intertran 联络线对象
from src.model.resource import Resource, Hydro  # 导入 Resource 和 Hydro 资源对象
TYPE_SET = frozenset(["THERMAL", "HYDRO", "STORAGE", "WIND", "PV", "LOAD", "RESERVE"])  # 定义允许的资源类型集合
INTERTRAN_TYPE_SET = frozenset(["AC", "DC"])  # 定义允许的联络线类型集合
@dataclass  # 声明 Grid 是一个数据类
class Grid:  # 定义完整电网对象
    id: str  # Grid 唯一编号，例如 HUBEI2030
    zones: dict[str, Zone] = field(default_factory=dict)  # 保存所有分区对象，key 是 zoneId
    intertrans: dict[str, Intertran] = field(default_factory=dict)  # 保存所有联络线对象，key 是 intertranId
    resources: dict[str, Resource] = field(default_factory=dict)  # 保存所有资源对象，key 是 resourceId
    sceKeyList: list[str] = field(default_factory=list)  # 保存需要时序数据的资源 ID
    def addZone(self, zone: Zone) -> Zone:  # 定义添加分区的方法
        if zone.id in self.zones:  # 判断分区 ID 是否已经存在
            raise ValueError(f"Zone {zone.id} is duplicated in grid {self.id}")  # 如果重复就报错
        self.zones[zone.id] = zone  # 把分区对象放入 Grid 的 zones 字典
        return zone  # 返回刚添加的分区对象
    def addBasin(self, basin: Basin) -> Basin:  # 定义添加流域的方法
        if basin.zoneId not in self.zones:  # 判断流域所属分区是否存在
            raise KeyError(f"Zone {basin.zoneId} is not in grid {self.id}")  # 如果分区不存在就报错
        if basin.id in self.zones[basin.zoneId].basinDict:  # 判断流域 ID 是否在该分区重复
            raise ValueError(f"Basin {basin.id} is duplicated in zone {basin.zoneId}")  # 如果重复就报错
        #self.zones[basin.zoneId].asinDictb[basin.id] = basin
        self.zones[basin.zoneId].basinDict[basin.id] = basin
        # 把流域加入对应分区的 basinDict
        return basin  # 返回刚添加的流域对象
    def addIntertran(self, intertran: Intertran) -> Intertran:  # 定义添加联络线的方法
        if intertran.id in self.intertrans:  # 判断联络线 ID 是否重复
            raise ValueError(f"Intertran {intertran.id} is duplicated in grid {self.id}")  # 如果重复就报错
        if intertran.type not in INTERTRAN_TYPE_SET:  # 判断联络线类型是否合法
            raise ValueError(f"Intertran type {intertran.type} is not valid")  # 如果类型非法就报错
        if intertran.fromZone not in self.zones:  # 判断起始分区是否存在
            raise KeyError(f"fromZone {intertran.fromZone} is not in grid {self.id}")  # 如果起始分区不存在就报错
        if intertran.toZone not in self.zones:  # 判断终止分区是否存在
            raise KeyError(f"toZone {intertran.toZone} is not in grid {self.id}")  # 如果终止分区不存在就报错
        self.intertrans[intertran.id] = intertran  # 把联络线加入 Grid 的 intertrans 字典
        self.zones[intertran.fromZone].outFlow.append(intertran.id)  # 把联络线加入起始分区的流出列表
        self.zones[intertran.toZone].inFlow.append(intertran.id)  # 把联络线加入终止分区的流入列表
        return intertran  # 返回刚添加的联络线对象
    def addResource(self, resource: Resource) -> str:  # 定义添加资源的方法
        if resource.id in self.resources:  # 判断资源 ID 是否重复
            raise ValueError(f"Resource {resource.id} is duplicated in grid {self.id}")  # 如果重复就报错
        if resource.type not in TYPE_SET:  # 判断资源类型是否合法
            raise ValueError(f"Resource type {resource.type} is not valid")  # 如果资源类型非法就报错
        if resource.zoneId not in self.zones:  # 判断资源所属分区是否存在
            raise KeyError(f"Zone {resource.zoneId} is not in grid {self.id}")  # 如果分区不存在就报错
        self.resources[resource.id] = resource  # 把资源加入 Grid 的 resources 字典
        self.zones[resource.zoneId].resKeyList.append(resource.id)  # 把资源 ID 加入对应分区的资源列表，append向列表末尾追加一个元素。
        if resource.isSeries:  # 判断该资源是否需要时序数据
            self.sceKeyList.append(resource.id)  # 如果需要时序数据，就加入 sceKeyList
        if resource.type == "HYDRO":  # 判断资源是否为水电
            self._add_hydro_to_basin(resource)  # 如果是水电，就把它挂到对应流域下面
        return resource.id  # 返回刚添加的资源 ID
    def _add_hydro_to_basin(self, resource: Resource) -> None:  # 定义内部方法，把水电加入流域
        hydro = resource  # 把通用 Resource 变量命名为 hydro，方便理解
        if not isinstance(hydro, Hydro):  # 判断这个对象是否真的是 Hydro 类型
            raise TypeError(f"Resource {resource.id} type is HYDRO but object is not Hydro")  # 如果类型不一致就报错
        if hydro.basinId not in self.zones[hydro.zoneId].basinDict:  # 判断水电所属流域是否存在
            raise KeyError(f"Basin {hydro.basinId} is not in zone {hydro.zoneId}")  # 如果流域不存在就报错
        basin = self.zones[hydro.zoneId].basinDict[hydro.basinId]  # 取出对应流域对象，根据水电对象的分区 ID、流域 ID，逐级找到对应的流域数据并赋值给变量。
        basin.hydroDict[hydro.id] = hydro  # 把水电机组加入流域的 hydroDict
        basin.capacity += hydro.capacity  # 把水电容量累加到流域总容量
    def getResFromId(self, resId: str) -> Resource:  # 定义按资源 ID 查询资源的方法
        if resId not in self.resources:  # 判断资源 ID 是否存在
            raise KeyError(f"Resource {resId} is not in grid {self.id}")  # 如果资源不存在就报错
        return self.resources[resId]  # 返回对应资源对象
    def getResIdListFromType(self, type: str) -> list[str]:  # 定义按资源类型查询资源 ID 列表的方法
        if type not in TYPE_SET:  # 判断资源类型是否合法
            raise ValueError(f"Resource type {type} is not valid")  # 如果类型非法就报错
        return [res.id for res in self.resources.values() if res.type == type]  # 返回该类型所有资源 ID
    def getResListFromType(self, type: str) -> list[Resource]:  # 定义按资源类型查询资源对象列表的方法
        if type not in TYPE_SET:  # 判断资源类型是否合法
            raise ValueError(f"Resource type {type} is not valid")  # 如果类型非法就报错
        return [res for res in self.resources.values() if res.type == type]  # 返回该类型所有资源对象
    def getResIdListFromZoneAndType(self, zone: str, type: str) -> list[str]:  # 定义按分区和类型查询资源 ID 的方法
        if zone not in self.zones:  # 判断分区是否存在
            raise KeyError(f"Zone {zone} is not in grid {self.id}")  # 如果分区不存在就报错
        if type not in TYPE_SET:  # 判断资源类型是否合法
            raise ValueError(f"Resource type {type} is not valid")  # 如果类型非法就报错
        return [res.id for res in self.resources.values() if res.zoneId == zone and res.type == type]  # 返回符合条件的资源 ID
    def getResListFromZoneAndType(self, zone: str, type: str) -> list[Resource]:  # 定义按分区和类型查询资源对象的方法
        if zone not in self.zones:  # 判断分区是否存在
            raise KeyError(f"Zone {zone} is not in grid {self.id}")  # 如果分区不存在就报错
        if type not in TYPE_SET:  # 判断资源类型是否合法
            raise ValueError(f"Resource type {type} is not valid")  # 如果类型非法就报错
        return [res for res in self.resources.values() if res.zoneId == zone and res.type == type]  # 返回符合条件的资源对象
    def getIntertranListFromZoneAndType(self, zoneId: str, type: str) -> tuple[list[Intertran], list[Intertran]]:  # 定义查询某分区联络线的方法
        if zoneId not in self.zones:  # 判断分区是否存在
            raise KeyError(f"Zone {zoneId} is not in grid {self.id}")  # 如果分区不存在就报错
        if type not in INTERTRAN_TYPE_SET:  # 判断联络线类型是否合法
            raise ValueError(f"Intertran type {type} is not valid")  # 如果类型非法就报错
        inFlowList = [line for line in self.intertrans.values() if line.type == type and line.toZone == zoneId]  # 查询流入该分区的联络线
        outFlowList = [line for line in self.intertrans.values() if line.type == type and line.fromZone == zoneId]  # 查询流出该分区的联络线
        return inFlowList, outFlowList  # 返回流入列表和流出列表
    def getBasinListFromZone(self, zoneId: str) -> list[Basin]:  # 定义查询某分区流域对象的方法
        if zoneId not in self.zones:  # 判断分区是否存在
            raise KeyError(f"Zone {zoneId} is not in grid {self.id}")  # 如果分区不存在就报错
        return list(self.zones[zoneId].basinDict.values())  # 返回该分区所有流域对象
    def summary(self) -> dict:  # 定义 Grid 摘要方法
        return {  # 返回一个字典作为摘要
            "grid_id": self.id,  # 输出 Grid ID
            "num_zones": len(self.zones),  # 输出分区数量
            "num_intertrans": len(self.intertrans),  # 输出联络线数量
            "num_resources": len(self.resources),  # 输出资源总数量
            "num_thermal": len(self.getResListFromType("THERMAL")),  # 输出火电数量
            "num_hydro": len(self.getResListFromType("HYDRO")),  # 输出水电数量
            "num_storage": len(self.getResListFromType("STORAGE")),  # 输出储能数量
            "num_wind": len(self.getResListFromType("WIND")),  # 输出风电数量
            "num_pv": len(self.getResListFromType("PV")),  # 输出光伏数量
            "num_load": len(self.getResListFromType("LOAD")),  # 输出负荷数量
        }  # 结束摘要字典
