# -*- coding: utf-8 -*-
"""统一优化模型包装。"""

from __future__ import annotations

import itertools
from collections.abc import Hashable, Iterable, Mapping
from typing import Any

import pyoptinterface as poi
from pyoptinterface import copt, gurobi, highs


VarKey = tuple[str, Hashable, str, Hashable]#资源、调度时段、变量类型、索引
ConsKey = tuple[str, Hashable, str, str]#约束所属对象、时段、约束类别和公式编号


class OptModel:
    """统一保存变量、约束、约束表达式和目标函数。"""

    def __init__(self, modelName: str = "model", solver: str = "GUROBI"):
        # 保存模型名称，便于日志、结果文件和多模型场景区分。
        self.name = modelName
        # vars 创建统一变量字典。
        self.vars: dict[VarKey, Any] = {}
        # cons 创建约束对象字典。
        self.cons: dict[ConsKey, Any] = {}
        # cons_expr 保存约束左端表达式。
        self.cons_expr: dict[ConsKey, Any] = {}
        # obj 是各成本模块共同累加的目标函数表达式。
        self.obj = poi.ExprBuilder()

        # 求解器名称统一转为大写。
        solver = solver.upper()
        # 三个分支只负责创建底层模型，成员3其余代码不依赖具体求解器 API。
        if solver == "GUROBI":
            self.model = gurobi.Model()
        elif solver == "COPT":
            self.model = copt.Model()
        elif solver == "HIGHS":
            self.model = highs.Model()
        else:
            raise ValueError("solver must be one of GUROBI, COPT, or HIGHS")

    def setVarList(
        self,
        resId: Iterable[str],#：资源 ID
        timeIdx: Iterable[Hashable],#时段
        varType: str,#变量类型标识
        idx: Hashable | Iterable[Hashable] | None = None,#子索引
        lb: float = 0.0,
        ub: float = 1e8,
    ) -> list[VarKey]:
        """批量创建变量并登记到统一变量表。"""

        # 将可迭代输入固化，防止生成器被多次遍历后丢失内容。
        resource_ids = tuple(resId)
        periods = tuple(timeIdx)
        # 子索引统一转为元组；普通变量缺省使用字符串 "0"。
        indices = _normalise_indices(idx)

        # C 表示机组组合变量，一次创建开机、启动和停机三组二进制变量。
        if varType == "C":
            variable_types = ("CU", "CV", "CW")
            domain = poi.VariableDomain.Binary
            name = "Commit"
        # P、E、AUX 分别表示功率、能量和辅助连续变量。
        elif varType in {"P", "E", "AUX"}:
            variable_types = (varType,)
            domain = poi.VariableDomain.Continuous
            name = varType
        else:
            raise ValueError(f"Invalid variable type: {varType}")

        #  (资源、时段、变量类型、子索引) 的完整变量键。
        keys = list(
            itertools.product(resource_ids, periods, variable_types, indices)
        )
        # 重复键意味着同一决策变量被创建两次，应在建模阶段立即报错。
        duplicate_keys = [key for key in keys if key in self.vars]
        if duplicate_keys:
            raise ValueError(f"Variable already exists: {duplicate_keys[0]}")
        # 空资源列表合法，例如某个算例没有火电或没有联络线。
        if not keys:
            return []

        # 由 PyOptInterface 批量创建变量，因此同一代码可适配三种后端。
        variables = self.model.add_variables(
            keys,
            lb=lb,
            ub=ub,
            domain=domain,
            name=name,
        )
        # 将求解器变量对象并入统一变量表，供所有约束模块按键读取。
        self.vars.update(variables)
        return keys

    def registerVarList(
        self,
        variables: Mapping[tuple[str, Hashable], Any],
        varType: str,
        idx: Hashable = "0",
    ) -> None:
        """把其他成员已创建的变量登记到统一变量表。"""

        # 成员4变量原索引为 (resource_id, period)，此处补齐类型和子索引。
        for (resource_id, period), variable in variables.items():
            key = (resource_id, period, varType, idx)
            # 禁止覆盖已有变量，否则功率平衡可能引用到错误的变量对象。
            if key in self.vars:
                raise ValueError(f"Variable already exists: {key}")
            self.vars[key] = variable

    def getVar(
        self,
        resId: str,
        timeIdx: Hashable,
        varType: str,
        idx: Hashable = "0",
    ) -> Any:
        """统一键读取变量。"""

        # 根据调用参数构造唯一变量键。
        key = (resId, timeIdx, varType, idx)
        # 找不到变量时补充完整键值。
        try:
            return self.vars[key]
        except KeyError as exc:
            raise KeyError(f"Invalid variable key: {key}") from exc

    def addCons(
        self,
        key: ConsKey,
        expr: Any,
        sense: Any,
        rhs: float = 0.0,
    ) -> Any:
        """添加线性约束，并同时保存约束对象和左端表达式。"""

        # 约束键必须唯一，防止后建约束静默覆盖先建约束的诊断信息。
        if key in self.cons:
            raise ValueError(f"Constraint already exists: {key}")
        # 将表达式、关系符和右端值交给统一建模接口创建约束。
        con = self.model.add_linear_constraint(expr, sense, rhs, name=str(key))
        # 同步登记约束对象和表达式，保持与 TanU OptModel 的组织方式一致。
        self.cons[key] = con
        self.cons_expr[key] = expr
        return con

    def setObjective(self, sense: Any = poi.ObjectiveSense.Minimize) -> None:
        """将已累计在 ``obj`` 中的表达式设置为模型目标函数。"""

        # 目标函数只在成本项累加完毕后统一写入底层模型。
        self.model.set_objective(self.obj, sense)

    def optimize(self) -> None:
        # 调用当前后端执行优化求解。
        self.model.optimize()

    def getValue(self, variable: Any) -> float:
        # 从求解器读取指定变量的最终数值。
        return self.model.get_value(variable)

    def getModelAttribute(self, attribute: Any) -> Any:
        # 读取目标值、终止状态等模型级属性。
        return self.model.get_model_attribute(attribute)


def _normalise_indices(
    idx: Hashable | Iterable[Hashable] | None,
) -> tuple[Hashable, ...]:
    """把单个或多个变量子索引转换成统一元组。"""

    # 未指定子索引时采用 TanU 的默认索引 "0"。
    if idx is None:
        return ("0",)
    # 字符串本身可迭代，但这里应把它视为一个完整索引而不是拆成字符。
    if isinstance(idx, (str, bytes)) or not isinstance(idx, Iterable):
        return (idx,)
    # 列表、元组等多索引输入直接固化为元组。
    return tuple(idx)
