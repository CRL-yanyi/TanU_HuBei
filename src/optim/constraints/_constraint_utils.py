# -*- coding: utf-8 -*-
"""非火电资源约束共享的时间与参数校验工具。"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Hashable, Mapping
from typing import Any

import pandas as pd


def validate_time_index(time_idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """校验正式建模接口使用的时间索引。

    非火电约束会根据相邻时间戳计算时间步长，并依据日期和月份切分日末、
    月末，因此索引必须非空、无重复、严格递增且等间隔。函数返回原对象，
    便于调用方在完成校验后继续保持 ``DatetimeIndex`` 类型。
    """
    if not isinstance(time_idx, pd.DatetimeIndex):
        raise TypeError("time_idx must be a pandas.DatetimeIndex")
    if time_idx.empty:
        raise ValueError("time_idx must not be empty")
    if time_idx.has_duplicates:
        raise ValueError("time_idx must not contain duplicate timestamps")
    if not time_idx.is_monotonic_increasing:
        raise ValueError("time_idx must be monotonic increasing")
    if len(time_idx) >= 2:
        # 所有相邻时刻必须使用同一间隔，例如全为 1 小时或全为 15 分钟。
        deltas = time_idx[1:] - time_idx[:-1]
        if any(delta != deltas[0] for delta in deltas):
            raise ValueError("time_idx must use a constant time step")
        if deltas[0] <= pd.Timedelta(0):
            raise ValueError("time_idx time step must be positive")
    return time_idx


def step_hours(time_idx: pd.DatetimeIndex) -> float:
    """返回时间索引对应的小时步长，用于 MW 与 MWh 之间换算。

    多时段索引直接使用前两个时刻之差；单时段索引优先读取 ``freq``。
    单时段且没有频率信息时按 1 小时处理，这是兼容旧小时级算例的约定。
    """
    validate_time_index(time_idx)
    if len(time_idx) >= 2:
        hours = (time_idx[1] - time_idx[0]) / pd.Timedelta(hours=1)
    elif time_idx.freq is not None:
        hours = pd.Timedelta(time_idx.freq).total_seconds() / 3600.0
    else:
        hours = 1.0
    hours = float(hours)
    if not math.isfinite(hours) or hours <= 0.0:
        raise ValueError("time_idx time step must be finite and positive")
    return hours


def is_last_period_of_day(time_idx: pd.DatetimeIndex, index: int) -> bool:
    """判断指定时段是否为当前调度日的最后一个时段。

    最后一个索引必然是本次建模窗口的日末；其余时段通过比较下一时刻的
    自然日判断。该规则可同时处理 1 小时和 15 分钟等固定步长。
    """
    if index == len(time_idx) - 1:
        return True
    return time_idx[index].date() != time_idx[index + 1].date()


def month_start(timestamp: pd.Timestamp) -> dt.date:
    """把时间戳归一为自然月首日，作为月度参数的规范键。"""
    return dt.date(timestamp.year, timestamp.month, 1)


def month_value(
    values: Mapping[Hashable, Any],
    timestamp: pd.Timestamp,
    *,
    owner: str,
    field: str,
) -> float:
    """读取时间戳所在自然月的参数值。

    规范格式是 ``datetime.date(年, 月, 1)``。为兼容既有数据，还依次接受
    pandas 月首时间戳、整数月份、字符串月份和 ``YYYY-MM``。找到值后必须
    转为有限浮点数；所有候选键均不存在时，错误信息会包含对象、字段和月份。
    """
    key_date = month_start(timestamp)
    # 候选键按“参考项目规范格式在前、历史兼容格式在后”的顺序查找。
    candidates = (
        key_date,
        pd.Timestamp(key_date),
        timestamp.month,
        str(timestamp.month),
        f"{timestamp.year:04d}-{timestamp.month:02d}",
    )
    for key in candidates:
        if key in values:
            value = float(values[key])
            if not math.isfinite(value):
                raise ValueError(
                    f"{owner} field '{field}' for {key_date:%Y-%m} must be finite"
                )
            return value
    raise ValueError(
        f"{owner} missing field '{field}' for month {key_date:%Y-%m}"
    )


def finite_nonnegative(value: Any, *, owner: str, field: str) -> float:
    """把模型参数转换为有限非负浮点数。

    ``owner`` 和 ``field`` 仅用于形成可定位的错误信息，例如明确指出具体
    资源或流域的哪个字段非法；函数本身不改变原始对象。
    """
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{owner} field '{field}' must be finite and nonnegative")
    return result
