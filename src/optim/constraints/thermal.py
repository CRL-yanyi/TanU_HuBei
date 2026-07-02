# -*- coding: utf-8 -*-
"""火电机组约束。

每个函数只建立一种物理约束，直接从 ``OptModel`` 取变量、构造表达式，并登记约束及其表达式。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import pandas as pd
import pyoptinterface as poi

from src.model.grid import Grid
from src.model.resource import Thermal
from src.optim.opt_model import OptModel


def setThermalUCCons(
    optmodel: OptModel,
    gridData: Grid,
    timeIdx: pd.DatetimeIndex,
) -> None:
    """添加常规 UC 必需的火电约束。"""

    # UC 的时间索引必须无重复且具有正时间步长。
    _check_time_index(timeIdx)
    # 各机组相互独立建立物理约束，系统耦合由平衡和备用模块负责。
    for thermal in gridData.getResListFromType("THERMAL"):
        # 常规约束依次覆盖容量、状态、最小持续时间和爬坡过程。
        setThermalConsPmin(optmodel, thermal, timeIdx)
        setThermalConsPmax(optmodel, thermal, timeIdx)
        setThermalConsInitState(optmodel, thermal, timeIdx)#初始状态衔接
        setThermalConsState(optmodel, thermal, timeIdx)#启停状态转移
        setThermalConsStartStopExclusion(optmodel, thermal, timeIdx)#启停互斥
        setThermalConsOnOffT0(optmodel, thermal, timeIdx)#窗口初始剩余开停机时长
        setThermalConsOn(optmodel, thermal, timeIdx)#最小开机时间
        setThermalConsOff(optmodel, thermal, timeIdx)#最小停机时间
        setThermalConsRampUp(optmodel, thermal, timeIdx)
        setThermalConsRampDown(optmodel, thermal, timeIdx)


def setThermalEDCons(
    optmodel: OptModel,
    gridData: Grid,
    timeIdx: pd.DatetimeIndex,
) -> None:
    """添加固定开停机状态的 ED 火电约束。"""

    # ED 与 UC 使用同一时间索引校验规则。
    _check_time_index(timeIdx)
    for thermal in gridData.getResListFromType("THERMAL"):
        # 先固定 CU/CV/CW，再复用 UC 的容量和爬坡公式，避免维护两套公式。
        setThermalConsFixedStatus(optmodel, thermal, timeIdx)
        setThermalConsPmin(optmodel, thermal, timeIdx)
        setThermalConsPmax(optmodel, thermal, timeIdx)
        setThermalConsRampUp(optmodel, thermal, timeIdx)
        setThermalConsRampDown(optmodel, thermal, timeIdx)


def setThermalConsPmin(
    optmodel: OptModel,
    res: Thermal,#资源类型
    timeIdx: pd.DatetimeIndex,
    constype: str = "P",#变量名
) -> None:
    """最小技术出力：``P[g,t] >= Pmin[g] * CU[g,t]``。"""

    # 同时校验 Pmin/Pmax，并取出本约束需要的 Pmin。
    p_min, _ = _output_limits(res)
    for t in timeIdx:
        # pg 为机组出力，ug 为开机状态；停机时 ug=0 会将 pg 下限降为 0。
        pg = optmodel.getVar(res.id, t, "P")
        ug = optmodel.getVar(res.id, t, "CU")
        # 将不等式移项为 pg - Pmin*ug >= 0。
        expr = poi.ExprBuilder()
        expr += pg - p_min * ug
        optmodel.addCons((res.id, t, constype, "2.2.3a"), expr, poi.Geq)#调用 OptModel 添加约束


def setThermalConsPmax(
    optmodel: OptModel,
    res: Thermal,
    timeIdx: pd.DatetimeIndex,
    constype: str = "P",
) -> None:
    """最大出力：``P[g,t] <= Pmax[g] * CU[g,t]``。"""

    # 同时校验 Pmin/Pmax，并取出本约束需要的 Pmax。
    _, p_max = _output_limits(res)
    for t in timeIdx:
        # pg 为机组出力，ug=0 时该上限会强制 pg=0。
        pg = optmodel.getVar(res.id, t, "P")
        ug = optmodel.getVar(res.id, t, "CU")
        # 将不等式移项为 pg - Pmax*ug <= 0。
        expr = poi.ExprBuilder()
        expr += pg - p_max * ug
        optmodel.addCons((res.id, t, constype, "2.2.3b"), expr, poi.Leq)


def setThermalConsInitState(
    optmodel: OptModel,
    res: Thermal,
    timeIdx: pd.DatetimeIndex,
    constype: str = "OnOff",
) -> None:
    """连接窗口开始前状态和第一时段启停变量。"""

    # 空窗口没有第一时段，因此无需建立初始状态连接约束。
    if len(timeIdx) == 0:
        return
    # t 是当前滚动窗口的第一个调度时段。
    t = timeIdx[0]
    # CU-CV+CW 等于窗口开始前状态，保证第一时段启停动作定义正确。
    expr = poi.ExprBuilder()
    expr += (
        optmodel.getVar(res.id, t, "CU")
        - optmodel.getVar(res.id, t, "CV")
        + optmodel.getVar(res.id, t, "CW")
        - _initial_status(res)
    )
    optmodel.addCons((res.id, t, constype, "2.2.8"), expr, poi.Eq)


def setThermalConsState(
    optmodel: OptModel,
    res: Thermal,
    timeIdx: pd.DatetimeIndex,
    constype: str = "OnOff",
) -> None:
    """状态转换：``CU[t]-CU[t-1]-CV[t]+CW[t]=0``。"""

    # 第一时段已由 setThermalConsInitState 处理，此处从第二时段开始。
    for i in range(1, len(timeIdx)):
        # t_prev 和 t 分别表示相邻的前后时段。
        t, t_prev = timeIdx[i], timeIdx[i - 1]
        # 状态变化只能由启动 CV 或停机 CW 解释。
        expr = poi.ExprBuilder()
        expr += (
            optmodel.getVar(res.id, t, "CU")
            - optmodel.getVar(res.id, t_prev, "CU")
            - optmodel.getVar(res.id, t, "CV")
            + optmodel.getVar(res.id, t, "CW")
        )
        optmodel.addCons((res.id, t, constype, "2.2.10"), expr, poi.Eq)


def setThermalConsStartStopExclusion(
    optmodel: OptModel,
    res: Thermal,
    timeIdx: pd.DatetimeIndex,
    constype: str = "OnOff",
) -> None:
    """同一时段不能同时启动和停机。"""

    # 对每个时段限制 CV+CW<=1，排除同时启动和停机的无意义解。
    for t in timeIdx:
        expr = poi.ExprBuilder()
        expr += optmodel.getVar(res.id, t, "CV") + optmodel.getVar(
            res.id, t, "CW"
        )
        optmodel.addCons((res.id, t, constype, "2.2.10b"), expr, poi.Leq, 1.0)


def setThermalConsOnOffT0(
    optmodel: OptModel,
    res: Thermal,
    timeIdx: pd.DatetimeIndex,
    constype: str = "OnOffT0",
) -> None:
    """补足滚动窗口开始时尚未满足的最小开停机时间。"""

    # 将最小开停机小时数按调度步长换算为时段数量。
    step_hours = _step_hours(timeIdx)
    # initT 的符号决定窗口开始前机组处于开机还是停机状态。
    initial_state = _initial_status(res)
    # 开机机组只需补足 minON 中尚未运行的剩余小时。
    if initial_state:
        remaining = max(0.0, _number(res, "minON") - _initial_hours(res, True))
    # 停机机组对应补足 minOFF 中尚未停机的剩余小时。
    else:
        remaining = max(0.0, _number(res, "minOFF") - _initial_hours(res, False))

    # 在剩余时段内把 CU 固定为窗口开始前状态。
    for t in timeIdx[: math.ceil(remaining / step_hours)]:
        expr = poi.ExprBuilder()
        expr += optmodel.getVar(res.id, t, "CU") - initial_state
        optmodel.addCons((res.id, t, constype, "2.2.6"), expr, poi.Eq)


def setThermalConsOn(
    optmodel: OptModel,
    res: Thermal,
    timeIdx: pd.DatetimeIndex,
    constype: str = "OnOff",
) -> None:
    """最小开机时间约束。"""

    # window 表示最小开机时间覆盖多少个离散调度时段。
    window = math.ceil(_number(res, "minON") / _step_hours(timeIdx))
    # 只覆盖一个或零个时段时，状态转换约束已经足够。
    if window <= 1:
        return
    # 对每个完整滑动窗口累计其中发生的启动动作。
    for i in range(window - 1, len(timeIdx)):
        t = timeIdx[i]
        expr = poi.ExprBuilder()
        # 窗口内任意一次启动都要求窗口末端 CU=1。
        for j in range(i - window + 1, i + 1):
            expr += optmodel.getVar(res.id, timeIdx[j], "CV")
        expr -= optmodel.getVar(res.id, t, "CU")
        optmodel.addCons((res.id, t, constype, "2.2.11"), expr, poi.Leq)


def setThermalConsOff(
    optmodel: OptModel,
    res: Thermal,
    timeIdx: pd.DatetimeIndex,
    constype: str = "OnOff",
) -> None:
    """最小停机时间约束。"""

    # window 表示最小停机时间覆盖多少个离散调度时段。
    window = math.ceil(_number(res, "minOFF") / _step_hours(timeIdx))
    if window <= 1:
        return
    # 对每个完整滑动窗口累计其中发生的停机动作。
    for i in range(window - 1, len(timeIdx)):
        t = timeIdx[i]
        expr = poi.ExprBuilder()
        # 窗口内任意一次停机都要求窗口末端 CU=0。
        for j in range(i - window + 1, i + 1):
            expr += optmodel.getVar(res.id, timeIdx[j], "CW")
        expr += optmodel.getVar(res.id, t, "CU") - 1.0
        optmodel.addCons((res.id, t, constype, "2.2.12"), expr, poi.Leq)


def setThermalConsRampUp(
    optmodel: OptModel,
    res: Thermal,
    timeIdx: pd.DatetimeIndex,
    constype: str = "RAMP",
) -> None:
    """常规及启动上爬坡约束。"""

    # step_hours 将 MW/h 爬坡速率转换为当前时段允许变化的 MW。
    step_hours = _step_hours(timeIdx)
    # 启动容量缺省为 0 时按 Pmax 放宽，兼容尚未补齐的真实数据。
    _, p_max = _output_limits(res)
    ramp_up = _number(res, "rampUp")
    startup_capacity = _ramp_capacity(res, "startUpCapacity", p_max)
    # 第一时段的前状态和前出力来自 Thermal 的滚动窗口初值。
    status_prev = _initial_status(res)
    power_prev = _initial_power(res, status_prev)
    _check_initial_power(res, status_prev, power_prev)

    # 逐时建立 P[t]-P[t-1] 的上升幅度限制。
    for t in timeIdx:
        expr = poi.ExprBuilder()
        expr += (
            optmodel.getVar(res.id, t, "P")
            - power_prev
            - ramp_up * step_hours * status_prev
            - startup_capacity * optmodel.getVar(res.id, t, "CV")
        )
        optmodel.addCons((res.id, t, constype, "2.2.4"), expr, poi.Leq)
        # 当前时段变量成为下一轮循环的前时段变量。
        power_prev = optmodel.getVar(res.id, t, "P")
        status_prev = optmodel.getVar(res.id, t, "CU")


def setThermalConsRampDown(
    optmodel: OptModel,
    res: Thermal,
    timeIdx: pd.DatetimeIndex,
    constype: str = "RAMP",
) -> None:
    """常规及停机下爬坡约束。"""

    # 下爬坡速率同样需要按时段长度缩放。
    step_hours = _step_hours(timeIdx)
    _, p_max = _output_limits(res)
    ramp_down = _number(res, "rampDown")
    shutdown_capacity = _ramp_capacity(res, "shutDownCapacity", p_max)
    status_prev = _initial_status(res)
    power_prev = _initial_power(res, status_prev)
    _check_initial_power(res, status_prev, power_prev)

    # 逐时建立 P[t-1]-P[t] 的下降幅度限制。
    for t in timeIdx:
        # pg、ug 分别为当前出力和当前开机状态。
        pg = optmodel.getVar(res.id, t, "P")
        ug = optmodel.getVar(res.id, t, "CU")
        expr = poi.ExprBuilder()
        expr += (
            power_prev
            - pg
            - ramp_down * step_hours * ug
            - shutdown_capacity * optmodel.getVar(res.id, t, "CW")
        )
        optmodel.addCons((res.id, t, constype, "2.2.5"), expr, poi.Leq)
        # 保存当前出力和状态，供下一时段约束使用。
        power_prev = pg
        status_prev = ug


def setThermalConsMustRun(
    optmodel: OptModel,
    res: Thermal,
    timeIdx: pd.DatetimeIndex,
    constype: str = "OnOff",
) -> None:
    """必开机组约束：``mustRun`` 机组在所有时段保持开机。"""

    # 非必开机组不生成额外约束，因此该函数可按需统一调用。
    if not res.mustRun:
        return
    for t in timeIdx:
        expr = poi.ExprBuilder()
        expr += optmodel.getVar(res.id, t, "CU") - 1.0
        optmodel.addCons((res.id, t, constype, "2.2.9"), expr, poi.Eq)


def setThermalConsFixedStatus(
    optmodel: OptModel,
    res: Thermal,
    timeIdx: pd.DatetimeIndex,
    constype: str = "FixedOnOff",
) -> None:
    """ED 固定状态：从 ``Thermal.ONOFF`` 固定 CU/CV/CW。"""

    # 第一时段的启停动作需要与窗口开始前状态比较。
    status_prev = _initial_status(res)
    for i, t in enumerate(timeIdx):
        # status 从 Thermal.ONOFF 的时段键、序号键或列表中读取。
        status = _fixed_status(res, t, i)
        # 根据相邻状态差自动推导固定的启动和停机指示量。
        values = {
            "CU": status,
            "CV": max(status - status_prev, 0),
            "CW": max(status_prev - status, 0),
        }
        # 为 CU、CV、CW 分别建立等式，将二进制变量固定到给定值。
        for variable_type, value in values.items():
            expr = poi.ExprBuilder()
            expr += optmodel.getVar(res.id, t, variable_type) - value
            optmodel.addCons(
                (res.id, t, constype, variable_type), expr, poi.Eq
            )
        # 当前固定状态成为下一时段的比较基准。
        status_prev = status


def _check_time_index(timeIdx: pd.DatetimeIndex) -> None:
    """校验成员3接口统一使用的时间索引。"""

    # 普通整数列表无法可靠推导物理时间步长，因此不再接受。
    if not isinstance(timeIdx, pd.DatetimeIndex):
        raise TypeError("timeIdx must be a pandas.DatetimeIndex")
    if timeIdx.has_duplicates:
        raise ValueError("timeIdx must not contain duplicate periods")
    _step_hours(timeIdx)


def _step_hours(timeIdx: pd.DatetimeIndex) -> float:
    """从相邻时间戳或 DatetimeIndex.freq 推导调度步长。"""

    # 多时段优先使用实际相邻时间差，可发现排序错误。
    if len(timeIdx) >= 2:
        hours = (timeIdx[1] - timeIdx[0]) / pd.Timedelta(hours=1)
    # 单时段没有相邻差值，改用 DatetimeIndex 自带频率。
    elif timeIdx.freq is not None:
        hours = timeIdx.freq.nanos / (3600 * 1e9)
    # 单时段且没有频率时采用项目默认的一小时步长。
    else:
        hours = 1.0
    if not math.isfinite(hours) or hours <= 0.0:
        raise ValueError("timeIdx frequency must be positive")
    return float(hours)


def _output_limits(res: Thermal) -> tuple[float, float]:
    """读取并校验机组最小、最大出力。"""

    p_min, p_max = _number(res, "Pmin"), _number(res, "Pmax")
    if p_max < p_min:
        raise ValueError(f"Invalid output limits for unit {res.id}")
    return p_min, p_max


def _number(res: Thermal, field: str, default=None) -> float:
    """统一读取非负有限的火电数值参数。"""

    # getattr 支持少量兼容字段使用默认值，同时保留缺字段错误提示。
    value = getattr(res, field, default)
    if value is None:
        raise ValueError(f"Thermal unit {res.id} is missing field {field}")
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{field} must be finite and nonnegative: {res.id}")
    return value


def _ramp_capacity(res: Thermal, field: str, fallback: float) -> float:
    """读取启停容量；零值按 Pmax 放宽。"""

    value = _number(res, field, fallback)
    return fallback if value == 0.0 else value


def _initial_status(res: Thermal) -> int:
    """将 initT 的正负号转换为窗口开始前的 0/1 状态。"""

    init_t = float(res.initT)
    if not math.isfinite(init_t):
        raise ValueError(f"initT must be finite: {res.id}")
    return int(init_t > 0.0)


def _initial_hours(res: Thermal, online: bool) -> float:
    """从 initT 提取已经连续开机或停机的小时数。"""

    init_t = float(res.initT)
    return max(init_t, 0.0) if online else max(-init_t, 0.0)


def _initial_power(res: Thermal, initial_status: int) -> float:
    """读取窗口开始前出力，并为缺省值提供物理合理的回退。"""

    value = res.initialPower
    if value is None:
        value = _number(res, "Pmin") if initial_status else 0.0
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"Initial power must be finite and nonnegative: {res.id}")
    return value


def _check_initial_power(res: Thermal, status: int, power: float) -> None:
    """停机状态下初始出力必须为零。"""

    if status == 0 and power != 0.0:
        raise ValueError(f"Initial power must be 0 when unit {res.id} is offline")


def _fixed_status(res: Thermal, period: pd.Timestamp, index: int) -> int:
    """兼容字典、场景字典和列表三种 ONOFF 保存格式。"""

    values = res.ONOFF
    if not values:
        raise ValueError(f"Missing fixed commitment: {(res.id, period)}")
    try:
        if isinstance(values, Mapping):
            if period in values:
                return _as_binary(values[period], res, period)
            if index in values:
                return _as_binary(values[index], res, period)
            if "S0" in values:
                values = values["S0"]
        if isinstance(values, Mapping):
            value = values[period] if period in values else values[index]
        elif isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            value = values[index]
        else:
            raise TypeError
        return _as_binary(value, res, period)
    except (IndexError, KeyError, TypeError) as exc:
        raise ValueError(f"Missing fixed commitment: {(res.id, period)}") from exc


def _as_binary(value, res: Thermal, period: pd.Timestamp) -> int:
    """将固定状态转为整数并限制为 0 或 1。"""

    value = int(value)
    if value not in (0, 1):
        raise ValueError(f"fixed commitment must be 0 or 1: {(res.id, period)}")
    return value
