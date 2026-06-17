
# dataclass 用于快速定义数据类，会自动生成 __init__、__repr__ 等方法。
# field 用于给可变类型字段设置默认值，比如 dict、list。
from dataclasses import dataclass, field
from src.model.intertran import Intertran
# Resource 是所有资源的父类。
# Hydro 是水电资源类，因为水电需要额外挂接到 Basin。
from src.model.resource import Hydro, Resource
# Basin 表示流域对象。
# Zone 表示电网分区对象。
from src.model.zone import Basin, Zone
TYPE_SET = frozenset([
    "THERMAL",   # 火电
    "HYDRO",     # 水电
    "STORAGE",   # 储能，包括普通电化学储能和抽水蓄能
    "WIND",      # 风电
    "PV",        # 光伏
    "LOAD",      # 负荷
    "RESERVE",   # 备用资源，预留类型
])


# 当前允许的联络线类型集合。
#
# AC 表示交流联络线；
# DC 表示直流联络线。
INTERTRAN_TYPE_SET = frozenset(["AC", "DC"])


@dataclass
class Grid:
    id: str
    zones: dict[str, Zone] = field(default_factory=dict)
    intertrans: dict[str, Intertran] = field(default_factory=dict)

    resources: dict[str, Resource] = field(default_factory=dict)

    sceKeyList: list[str] = field(default_factory=list)

    def addZone(self, zone: Zone) -> Zone:
        """
        添加分区对象到 Grid 中。
        """

        # 如果当前分区 ID 已经存在于 grid.zones 中，
        # 说明出现了重复分区。
        if zone.id in self.zones:
            raise ValueError(f"Zone {zone.id} is duplicated in grid {self.id}")

        # 将分区对象加入 Grid。
        # key 使用 zone.id，方便后续通过分区 ID 快速查询 Zone。
        self.zones[zone.id] = zone

        # 返回刚刚添加的 Zone 对象，便于调用方继续使用。
        return zone

    def addBasin(self, basin: Basin) -> Basin:
        # 检查 Basin 所属分区是否已经存在于 Grid。
        #
        # 如果分区不存在，就不能添加 Basin，
        # 因为 Basin 必须挂在某个 Zone 下面。
        if basin.zoneId not in self.zones:
            raise KeyError(f"Zone {basin.zoneId} is not in grid {self.id}")

        # 检查该分区下是否已经有同名 Basin。
        # basinDict 是 Zone 对象内部保存流域对象的字典。
        if basin.id in self.zones[basin.zoneId].basinDict:
            raise ValueError(f"Basin {basin.id} is duplicated in zone {basin.zoneId}")

        # 把 Basin 加入所属分区的 basinDict 中。
        self.zones[basin.zoneId].basinDict[basin.id] = basin

        # 返回添加成功的 Basin。
        return basin

    def addIntertran(self, intertran: Intertran) -> Intertran:
        """
        添加分区间联络线 / 输电断面。
        主要检查：
            1. 联络线 ID 不能重复；
            2. 联络线类型必须是 AC 或 DC；
            3. 起点分区必须存在；
            4. 终点分区必须存在。
        """
        # 检查联络线 ID 是否重复。
        if intertran.id in self.intertrans:
            raise ValueError(f"Intertran {intertran.id} is duplicated in grid {self.id}")
        # 检查联络线类型是否合法。
        #
        # 当前只允许 AC 和 DC。
        if intertran.type not in INTERTRAN_TYPE_SET:
            raise ValueError(f"Intertran type {intertran.type} is not valid")
        # 检查起点分区是否存在。
        #
        # 如果 fromZone 不存在，说明这条线路连接到了一个不存在的分区。
        if intertran.fromZone not in self.zones:
            raise KeyError(f"fromZone {intertran.fromZone} is not in grid {self.id}")

        # 检查终点分区是否存在。
        if intertran.toZone not in self.zones:
            raise KeyError(f"toZone {intertran.toZone} is not in grid {self.id}")

        # 将联络线加入 Grid 的全局联络线字典。
        self.intertrans[intertran.id] = intertran

        # 在起点分区记录这条流出线路。
        self.zones[intertran.fromZone].outFlow.append(intertran.id)

        # 在终点分区记录这条流入线路。
        self.zones[intertran.toZone].inFlow.append(intertran.id)

        # 返回添加成功的联络线对象。
        return intertran

    def addResource(self, resource: Resource) -> str:
        """
        添加资源对象。
        主要检查：
            1. 资源 ID 不能重复；
            2. 资源类型必须合法；
            3. 资源所属分区必须存在；
            4. 如果是水电，还要检查对应 Basin 是否存在。
        """
        # 检查资源 ID 是否重复。
        if resource.id in self.resources:
            raise ValueError(f"Resource {resource.id} is duplicated in grid {self.id}")

        # 检查资源类型是否合法。
        # resource.type 必须属于 TYPE_SET 中定义的类型。
        if resource.type not in TYPE_SET:
            raise ValueError(f"Resource type {resource.type} is not valid")

        # 检查资源所属分区是否存在。
        # 每个资源都必须挂接到一个已经存在的 Zone。
        if resource.zoneId not in self.zones:
            raise KeyError(f"Zone {resource.zoneId} is not in grid {self.id}")

        # 将资源对象加入 Grid 的全局资源字典。
        self.resources[resource.id] = resource

        # 把资源 ID 加入所属分区的资源列表。
        # 这样后续可以从 Zone 快速找到该分区下有哪些资源。
        self.zones[resource.zoneId].resKeyList.append(resource.id)

        # 如果该资源需要时序数据，
        # 就把它的 ID 加入 sceKeyList。
        # 一般 Load、Wind、PV 会设置 isSeries=True。
        if resource.isSeries:
            self.sceKeyList.append(resource.id)

        # 如果资源类型是 HYDRO，
        # 还需要额外把它挂到 Basin.hydroDict 中。这样成员四做水电流域约束时，可以通过 Basin 找到该流域下所有水电机组。
        if resource.type == "HYDRO":
            self._add_hydro_to_basin(resource)

        # 返回添加成功的资源 ID。
        return resource.id

    def _add_hydro_to_basin(self, resource: Resource) -> None:
        hydro = resource

        # 检查对象类型是否真的是 Hydro。
        # 这种情况说明构建对象时出了问题，需要立即报错。
        if not isinstance(hydro, Hydro):
            raise TypeError(f"Resource {resource.id} type is HYDRO but object is not Hydro")
        # 检查该水电机组所属的 Basin 是否存在。
        # Basin 是挂在 Zone 下面的，所以要先通过 hydro.zoneId 找到 Zone，再在该 Zone 的 basinDict 中查找 hydro.basinId。
        if hydro.basinId not in self.zones[hydro.zoneId].basinDict:
            raise KeyError(f"Basin {hydro.basinId} is not in zone {hydro.zoneId}")
        # 取出对应 Basin 对象。
        basin = self.zones[hydro.zoneId].basinDict[hydro.basinId]
        # 把水电机组加入 Basin 的 hydroDict。
        # key 是 hydro.id；
        # value 是 Hydro 对象。
        basin.hydroDict[hydro.id] = hydro
        # 累加流域装机容量。这样 Basin.capacity 可以表示该流域下所有水电资源的总容量。
        basin.capacity += hydro.capacity
    def getResFromId(self, resId: str) -> Resource:
        """根据资源 ID 查询资源对象。如果资源 ID 不存在，就抛出 KeyError。
        """
        # 检查资源 ID 是否存在。
        if resId not in self.resources:
            raise KeyError(f"Resource {resId} is not in grid {self.id}")
        # 返回资源对象。
        return self.resources[resId]

    def getResIdListFromType(self, type: str) -> list[str]:
        """根据资源类型查询资源 ID 列表。"""
        # 检查资源类型是否合法。
        if type not in TYPE_SET:
            raise ValueError(f"Resource type {type} is not valid")
        # 遍历所有资源，筛选出类型匹配的资源 ID。
        return [res.id for res in self.resources.values() if res.type == type]
    def getResListFromType(self, type: str) -> list[Resource]:
        """ 根据资源类型查询资源对象列表。
        """
        # 检查资源类型是否合法。
        if type not in TYPE_SET:
            raise ValueError(f"Resource type {type} is not valid")
        # 遍历所有资源，筛选出类型匹配的资源对象。
        return [res for res in self.resources.values() if res.type == type]
    def getStorageListFromSubtype(self, subtype: str) -> list[Resource]:

        # 遍历所有资源。
        # 先筛选 type == "STORAGE"，
        # 再通过 getattr 获取 subtype。
        #
        # getattr(res, "subtype", "") 的意思是：  如果 res 有 subtype 属性也就是子类型，就取 subtype；  如果没有 subtype 属性，就返回空字符串，避免报错。
        return [
            res for res in self.resources.values()
            if res.type == "STORAGE" and getattr(res, "subtype", "") == subtype
        ]

    def getResIdListFromZoneAndType(self, zone: str, type: str) -> list[str]:
        """ 根据分区和资源类型查询资源 ID 列表。
        """
        # 检查分区是否存在。
        if zone not in self.zones:
            raise KeyError(f"Zone {zone} is not in grid {self.id}")
        # 检查资源类型是否合法。
        if type not in TYPE_SET:
            raise ValueError(f"Resource type {type} is not valid")
        # 遍历所有资源，
        # 同时筛选 zoneId 和 type。
        return [
            res.id for res in self.resources.values()
            if res.zoneId == zone and res.type == type
        ]

    def getResListFromZoneAndType(self, zone: str, type: str) -> list[Resource]:
        """
        根据分区和资源类型查询资源对象列表。
        """
        # 检查分区是否存在。
        if zone not in self.zones:
            raise KeyError(f"Zone {zone} is not in grid {self.id}")
        # 检查资源类型是否合法。
        if type not in TYPE_SET:
            raise ValueError(f"Resource type {type} is not valid")
        # 遍历所有资源，
        # 同时筛选 zoneId 和 type。
        return [
            res for res in self.resources.values()
            if res.zoneId == zone and res.type == type
        ]

    def getIntertranListFromZoneAndType(
        self,
        zoneId: str,
        type: str,
    ) -> tuple[list[Intertran], list[Intertran]]:
        """查询某个分区下某种类型的联络线。 """
        # 检查分区是否存在。
        if zoneId not in self.zones:
            raise KeyError(f"Zone {zoneId} is not in grid {self.id}")

        # 检查联络线类型是否合法。
        if type not in INTERTRAN_TYPE_SET:
            raise ValueError(f"Intertran type {type} is not valid")

        # 筛选所有流入该分区的联络线。
        # line.toZone == zoneId 表示该线路的终点是当前分区。
        inFlowList = [
            line for line in self.intertrans.values()#表达式 for 临时变量 in 可遍历对象
            if line.type == type and line.toZone == zoneId
        ]

        # 筛选所有从该分区流出的联络线。
        # line.fromZone == zoneId 表示该线路的起点是当前分区。
        outFlowList = [
            line for line in self.intertrans.values()
            if line.type == type and line.fromZone == zoneId
        ]

        # 返回流入线路列表和流出线路列表。
        return inFlowList, outFlowList

    def getBasinListFromZone(self, zoneId: str) -> list[Basin]:
        """
        查询某个分区下的所有 Basin 对象。
        """

        # 检查分区是否存在。
        if zoneId not in self.zones:
            raise KeyError(f"Zone {zoneId} is not in grid {self.id}")
        # basinDict 是字典，values() 是所有 Basin 对象， list(...) 把它转成列表返回。
        return list(self.zones[zoneId].basinDict.values())
    def summary(self) -> dict:
        """
        输出 Grid 摘要信息。

        """

        # 先取出所有 STORAGE 类型资源。
        #
        # 这里包括普通储能和抽水蓄能。
        storage_list = self.getResListFromType("STORAGE")

        # 返回 Grid 的结构摘要。
        return {
            # Grid 编号。
            "grid_id": self.id,

            # 分区数量。
            "num_zones": len(self.zones),

            # 联络线数量。
            "num_intertrans": len(self.intertrans),

            # 全部资源数量。
            "num_resources": len(self.resources),

            # 火电资源数量。
            "num_thermal": len(self.getResListFromType("THERMAL")),

            # 水电资源数量。
            "num_hydro": len(self.getResListFromType("HYDRO")),

            # 储能资源总数量，包括普通储能和抽水蓄能。
            "num_storage": len(storage_list),

            # 普通电化学储能数量。
            #
            # getattr(res, "subtype", "") 用于安全获取 subtype。
            # 如果某个资源没有 subtype 字段，也不会报错。
            "num_battery_storage": len(
                [
                    res for res in storage_list
                    if getattr(res, "subtype", "") == "BATTERY_STORAGE"
                ]
            ),

            # 抽水蓄能数量。
            "num_pumped_storage": len(
                [
                    res for res in storage_list
                    if getattr(res, "subtype", "") == "PUMPED_STORAGE"
                ]
            ),

            # 风电资源数量。
            "num_wind": len(self.getResListFromType("WIND")),

            # 光伏资源数量。
            "num_pv": len(self.getResListFromType("PV")),

            # 负荷资源数量。
            "num_load": len(self.getResListFromType("LOAD")),
        }
