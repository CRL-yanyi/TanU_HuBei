# -*- coding: utf-8 -*-
"""非火电资源建模使用的单场景数据接口。

首期只把一个已选择的场景接入优化模型，但数据结构保留场景 ID 和概率，
后续可扩展为多场景而无需在约束中硬编码名称。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class Scenario:
    """一个不可变场景及其按资源列组织的标幺时序。

    ``data`` 的行索引必须是 ``DatetimeIndex``，每一列名称必须等于 Grid 中
    的资源 ID，单元格保存该资源在该时段的可用出力标幺系数。例如 0.6 表示
    可用出力为当月装机容量的 60%。
    """

    id: str  # 场景唯一标识，不在约束代码中硬编码具体名称。
    probability: float  # 场景概率；单场景生产模拟要求为 1.0。
    data: pd.DataFrame  # 行为时间戳，列为资源 ID，值为非负标幺系数。

    def __post_init__(self) -> None:
        # 构造时一次性检查结构错误，避免在逐时建约束过程中延迟失败。
        if not self.id:
            raise ValueError("scenario id must not be empty")
        probability = float(self.probability)
        if not math.isfinite(probability) or probability <= 0.0 or probability > 1.0:
            raise ValueError("scenario probability must be in (0, 1]")
        if not isinstance(self.data.index, pd.DatetimeIndex):
            raise TypeError("scenario data index must be a pandas.DatetimeIndex")
        if self.data.index.empty:
            raise ValueError("scenario data must not be empty")
        if self.data.index.has_duplicates:
            raise ValueError("scenario time index must not contain duplicates")
        if self.data.columns.has_duplicates:
            raise ValueError("scenario resource columns must not contain duplicates")
        if self.data.isna().any().any():
            raise ValueError(f"scenario '{self.id}' contains missing values")

    @property
    def time_index(self) -> pd.DatetimeIndex:
        """返回场景原始时间索引，不生成新的副本或重新排序。"""
        return self.data.index

    def get_value(self, resource_id: str, period: pd.Timestamp) -> float:
        """读取指定资源和时段的标幺系数，并校验为有限非负数。"""
        # 资源列和时间行分别检查，使报错能准确说明缺的是哪一维数据。
        if resource_id not in self.data.columns:
            raise ValueError(
                f"scenario '{self.id}' missing resource '{resource_id}'"
            )
        if period not in self.data.index:
            raise ValueError(
                f"scenario '{self.id}' missing timestamp '{period}'"
            )
        value = float(self.data.at[period, resource_id])
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(
                f"scenario '{self.id}' resource '{resource_id}' at {period} "
                "must be finite and nonnegative"
            )
        return value


@dataclass
class ScenarioSet:
    """按 ID 管理场景，并提供统一的概率、时间和资源时序查询。"""

    scenarios: dict[str, Scenario] = field(default_factory=dict)

    @classmethod
    def from_case_data(
        cls,
        grid,
        case_data,
        scenario_id: str | None = None,
    ) -> "ScenarioSet":
        """把CaseData中的分区风光曲线转换为按资源ID组织的单场景。

        CaseData曲线按分区命名，优化约束按资源ID查询。本工厂负责完成
        ``鄂东 -> WIND鄂东/PV鄂东`` 的映射，并保证时间轴与CaseData一致。
        """
        time_index = getattr(case_data, "time_index", None)
        if not isinstance(time_index, pd.DatetimeIndex):
            raise TypeError("case_data.time_index must be a pandas.DatetimeIndex")

        values: dict[str, pd.Series] = {}
        for resource_type, frame_name in (
            ("WIND", "wind_curves"),
            ("PV", "pv_curves"),
        ):
            frame = getattr(case_data, frame_name, None)
            if frame is None or frame.empty or not frame.index.equals(time_index):
                raise ValueError(
                    f"case_data.{frame_name} must cover the complete time_index"
                )
            for resource in grid.getResListFromType(resource_type):
                if resource.zoneId not in frame.columns:
                    raise ValueError(
                        f"case_data.{frame_name} missing zone '{resource.zoneId}'"
                    )
                values[resource.id] = frame[resource.zoneId].astype(float)

        metadata = getattr(case_data, "metadata", {}) or {}
        raw_id = metadata.get("scenario")
        if scenario_id is None:
            scenario_id = "BASE" if raw_id in (None, 0, "0") else f"S{raw_id}"

        result = cls()
        result.add_scenario(
            Scenario(
                id=str(scenario_id),
                probability=1.0,
                data=pd.DataFrame(values, index=time_index),
            )
        )
        return result

    def add_scenario(self, scenario: Scenario) -> None:
        """登记场景，并确保所有场景使用完全相同的时间轴。"""
        if scenario.id in self.scenarios:
            raise ValueError(f"scenario '{scenario.id}' is duplicated")
        if self.scenarios:
            # 统一时间轴是未来进行多场景期望值计算和逐时比较的前提。
            first_index = next(iter(self.scenarios.values())).time_index
            if not scenario.time_index.equals(first_index):
                raise ValueError("all scenarios must use the same time index")
        self.scenarios[scenario.id] = scenario

    def get_scenario(self, scenario_id: str) -> Scenario:
        """按 ID 返回场景；将底层 KeyError 转成面向数据配置的 ValueError。"""
        try:
            return self.scenarios[scenario_id]
        except KeyError as exc:
            raise ValueError(f"scenario '{scenario_id}' does not exist") from exc

    def get_value(
        self,
        scenario_id: str,
        resource_id: str,
        period: pd.Timestamp,
    ) -> float:
        """读取一个场景、一个资源、一个时段的标幺系数。"""
        return self.get_scenario(scenario_id).get_value(resource_id, period)

    def get_probability(self, scenario_id: str) -> float:
        """返回场景概率。"""
        return float(self.get_scenario(scenario_id).probability)

    def get_time_index(self, scenario_id: str) -> pd.DatetimeIndex:
        """返回场景时间索引。"""
        return self.get_scenario(scenario_id).time_index

    def validate_probabilities(self) -> None:
        """校验场景集合非空且概率总和在数值容差内等于 1。"""
        if not self.scenarios:
            raise ValueError("scenario set must not be empty")
        total = sum(float(item.probability) for item in self.scenarios.values())
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(
                f"scenario probabilities must sum to 1.0, got {total}"
            )

    def require_single_scenario(self, scenario_id: str) -> Scenario:
        """执行当前生产模型的单场景契约并返回被选场景。

        数据结构预留多场景能力，但当前约束和目标函数尚未引入场景维度，
        因此只能接收恰好一个概率为 1 的场景。提前拒绝多场景可防止模型
        静默忽略其他场景。
        """
        if len(self.scenarios) != 1:
            raise ValueError(
                "the current production model requires exactly one scenario"
            )
        scenario = self.get_scenario(scenario_id)
        if not math.isclose(
            float(scenario.probability), 1.0, rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError(
                f"single scenario '{scenario_id}' probability must be 1.0"
            )
        return scenario
