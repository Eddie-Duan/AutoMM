# -*- coding: utf-8 -*-
"""prob03 输入读取与 ``result3.xlsx`` 填报。

只读 ``data/附件1.xlsx``（电价列）、``data/附件2.xlsx``（实际负载/光伏）、``data/附件3.xlsx``（整点预报）
与模板 ``data/附件5/result3.xlsx``；不修改任何原始数据。

口径来源：prob03 ``assumption_v001``（AS01/AS02/AS05/AS16 + 团队裁定 B0–B7）与 ``formulation_v001`` §3.2/§7。

纪律（AS02 / B5）：
  * 附件 1 **只使用电价列**（第 2 列）；其负载/光伏预测列、附件 4、2026 年数据均不进入模型；
  * 附件 3 的日期列只在每日 ``0:00`` 行出现（其余为空白字符串），实现按**前向填充**解析并把
    ``2025-1-1`` 规范为 ``2025-01-01``；
  * 附件 3 的整点预报按 AS05 的「整点点值 + 整点锚定线性插值」降尺度（在 ``prob03_model`` 实现）。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import openpyxl
from openpyxl.utils import get_column_letter

EXPECTED_HEADER_A1 = ("时间", "电价", "小区负载", "光伏发电预测功率")
LOAD_SHEET = "小区负载"
PV_SHEET = "光伏发电实际功率"
PLAN_SHEET = "计划购电量"
ADJUST_SHEET = "调整购电量"
STORAGE_SHEET = "充放电量"
EMERGENCY_SHEET = "紧急购电量"
PLAN_HEADER_FIRST = "日期\\时间"
PLAN_HEADER_ENERGY = "全天购电量"
PLAN_HEADER_COST = "全天购电费"
STORAGE_HEADER = ("日期", "时间段", "充电量", "放电量", "时刻", "储电量")
EMERGENCY_HEADER = ("日期", "购电时间段", "购电量")
BLOCK_ROWS = 24
BLOCKS_PER_DAY = 6
PERIODS_PER_DAY = 144
ZERO_INTERVAL_TEXT = "—"
A2_DATE_HEADER = "日期\\时间"
DECISION_HOURS: tuple[int, ...] = (0, 6, 12, 18)
FC_HORIZON = 24


class InputValidationError(RuntimeError):
    """输入结构与 accepted 假设不一致时严格失败。"""


@dataclass(frozen=True)
class Attachment1:
    """附件 1 的 144 个时段电价（元/kWh）与时间标签（只含电价列）。"""

    price: np.ndarray
    time_labels: list[str]
    header: list[str]
    md5: str

    @property
    def periods(self) -> int:
        return int(self.price.shape[0])


@dataclass(frozen=True)
class Attachment2:
    """附件 2 的逐日实际负载/光伏功率（365 天 × 144 个 10 分钟点，单位 kW）。"""

    load_kw: np.ndarray
    pv_kw: np.ndarray
    dates: list[str]
    time_labels: list[str]
    md5: str

    @property
    def days(self) -> int:
        return int(self.load_kw.shape[0])

    @property
    def periods_per_day(self) -> int:
        return int(self.load_kw.shape[1])


@dataclass(frozen=True)
class Attachment3:
    """附件 3 的整点预报表 ``A[d, s, k]``（kW；``s`` 为 ``DECISION_HOURS`` 下标，``k = 1..24``）。"""

    fc_kw: np.ndarray          # (days, 4, 24)
    dates: list[str]
    slots: list[str]
    md5: str

    @property
    def days(self) -> int:
        return int(self.fc_kw.shape[0])

    def row(self, day: int, hour: int) -> np.ndarray:
        """返回第 ``day`` 天、发布时刻 ``hour`` 的 24 维整点预报向量。"""
        if hour not in DECISION_HOURS:
            raise ValueError(f"未知发布时刻：{hour}")
        return self.fc_kw[day, DECISION_HOURS.index(hour), :]


def md5_of(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clock_label(value: Any) -> str:
    """把附件时间戳格式化为 ``H:MM``（datetime/time 走 strftime，字符串原样返回）。"""
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    return str(value).strip()


def _date_label(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()


def canonical_date(value: Any) -> str:
    """把附件 3 的日期（``2025-1-1`` 字符串或 datetime）规范为 ``YYYY-MM-DD``；空白返回空串。"""
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    if not text:
        return ""
    parts = text.split("-") if "-" in text else text.split("/")
    if len(parts) == 3:
        try:
            return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
        except ValueError:
            return text
    return text


def _slot_hour(value: Any) -> int:
    """把附件 3 的 ``预报时刻`` 解析为整点小时数（``0:00`` → 0）。"""
    if value is None:
        raise InputValidationError("附件 3 存在空的预报时刻")
    if hasattr(value, "strftime"):
        return int(value.strftime("%H"))
    text = str(value).strip()
    if not text:
        raise InputValidationError("附件 3 存在空的预报时刻")
    head = text.split(":")[0].strip()
    try:
        return int(head)
    except ValueError as exc:
        raise InputValidationError(f"附件 3 预报时刻无法解析：{value!r}") from exc


def read_attachment1(path: Path, expected_rows: int = PERIODS_PER_DAY) -> Attachment1:
    """读取附件 1 第 1 个工作表；只保留电价列与时间标签。"""
    if not path.is_file():
        raise InputValidationError(f"附件 1 不存在：{path}")
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        rows = [row for row in sheet.iter_rows(min_row=1, max_col=4, values_only=True)]
    finally:
        workbook.close()
    if len(rows) < 2:
        raise InputValidationError("附件 1 没有数据行")
    header = [str(item).strip() for item in rows[0]]
    if tuple(header) != EXPECTED_HEADER_A1:
        raise InputValidationError(f"附件 1 表头不匹配：{header} != {list(EXPECTED_HEADER_A1)}")
    body = rows[1:]
    if len(body) != expected_rows:
        raise InputValidationError(f"附件 1 数据行数 {len(body)} != 期望 {expected_rows}")
    labels = [_clock_label(row[0]) for row in body]
    try:
        price = np.array([float(row[1]) for row in body], dtype=float)
    except (TypeError, ValueError) as exc:
        raise InputValidationError(f"附件 1 电价列存在非数值单元格：{exc}") from exc
    if not np.all(np.isfinite(price)):
        raise InputValidationError("附件 1 电价列含 NaN/Inf")
    if np.any(price <= 0):
        raise InputValidationError("附件 1 存在非正电价：目标函数与对偶前提被破坏")
    return Attachment1(price=price, time_labels=labels, header=header, md5=md5_of(path))


def _read_power_sheet(
    sheet: Any, *, name: str, expected_days: int, expected_periods: int
) -> tuple[list[str], list[str], np.ndarray]:
    rows = [row for row in sheet.iter_rows(min_row=1, max_col=expected_periods + 1, values_only=True)]
    if len(rows) != expected_days + 1:
        raise InputValidationError(f"附件 2『{name}』行数 {len(rows)} != 表头 + {expected_days}")
    header = ["" if item is None else str(item) for item in rows[0]]
    if header[0].strip() != A2_DATE_HEADER:
        raise InputValidationError(f"附件 2『{name}』首列表头不是 {A2_DATE_HEADER}：{header[0]!r}")
    if len(header) != expected_periods + 1:
        raise InputValidationError(f"附件 2『{name}』列数 {len(header)} != {expected_periods + 1}")
    body = rows[1:]
    dates = [_date_label(row[0]) for row in body]
    try:
        values = np.array([[float(item) for item in row[1:]] for row in body], dtype=float)
    except (TypeError, ValueError) as exc:
        raise InputValidationError(f"附件 2『{name}』存在非数值单元格：{exc}") from exc
    if values.shape != (expected_days, expected_periods):
        raise InputValidationError(f"附件 2『{name}』矩阵形状 {values.shape} 不符")
    if not np.all(np.isfinite(values)):
        raise InputValidationError(f"附件 2『{name}』含 NaN/Inf")
    if np.any(values < 0):
        raise InputValidationError(f"附件 2『{name}』存在负功率")
    return header, dates, values


def read_attachment2(
    path: Path, expected_days: int = 365, expected_periods: int = PERIODS_PER_DAY
) -> Attachment2:
    """读取附件 2 的『小区负载』与『光伏发电实际功率』（均为实际值）。"""
    if not path.is_file():
        raise InputValidationError(f"附件 2 不存在：{path}")
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        titles = list(workbook.sheetnames)
        for name in (LOAD_SHEET, PV_SHEET):
            if name not in titles:
                raise InputValidationError(f"附件 2 缺少工作表『{name}』：{titles}")
        load_header, load_dates, load = _read_power_sheet(
            workbook[LOAD_SHEET], name=LOAD_SHEET, expected_days=expected_days, expected_periods=expected_periods
        )
        pv_header, pv_dates, pv = _read_power_sheet(
            workbook[PV_SHEET], name=PV_SHEET, expected_days=expected_days, expected_periods=expected_periods
        )
    finally:
        workbook.close()
    if load_dates != pv_dates:
        raise InputValidationError("附件 2 两个工作表的日期序列不一致")
    _validate_dates(load_dates)
    if load_header[1:] != pv_header[1:]:
        raise InputValidationError("附件 2 两个工作表的时间标签不一致")
    return Attachment2(
        load_kw=load,
        pv_kw=pv,
        dates=load_dates,
        time_labels=[str(item) for item in load_header[1:]],
        md5=md5_of(path),
    )


def _validate_dates(dates: Sequence[str]) -> None:
    try:
        parsed = [datetime.strptime(item, "%Y-%m-%d").date() for item in dates]
    except ValueError as exc:
        raise InputValidationError(f"附件 2 日期列无法解析：{exc}") from exc
    for index in range(1, len(parsed)):
        if (parsed[index] - parsed[index - 1]).days != 1:
            raise InputValidationError(f"附件 2 日期不连续：{dates[index - 1]} -> {dates[index]}")
    if parsed[0].isoformat() != "2025-01-01":
        raise InputValidationError(f"附件 2 首日不是 2025-01-01：{dates[0]}")


def read_attachment3(
    path: Path, *, expected_days: int = 365, hours: Sequence[int] = DECISION_HOURS
) -> Attachment3:
    """读取附件 3 的整点预报表，返回 ``(days, 4, 24)`` 张量与规范日期/时刻序列。

    日期列只在每日首个发布时刻行出现（其余为空白），实现按前向填充解析；
    每日必须恰有 ``len(hours)`` 行且发布时刻按 ``0:00 → 6:00 → 12:00 → 18:00`` 升序。
    """
    if not path.is_file():
        raise InputValidationError(f"附件 3 不存在：{path}")
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        rows = [row for row in sheet.iter_rows(min_row=1, max_col=2 + FC_HORIZON, values_only=True)]
    finally:
        workbook.close()
    if len(rows) < 2:
        raise InputValidationError("附件 3 没有数据行")
    header = [str(item).strip() if item is not None else "" for item in rows[0]]
    if header[:2] != ["日期", "预报时刻"]:
        raise InputValidationError(f"附件 3 表头前两列异常：{header[:2]}")
    body = rows[1:]
    expected_rows = expected_days * len(hours)
    if len(body) != expected_rows:
        raise InputValidationError(f"附件 3 数据行数 {len(body)} != 期望 {expected_rows}")

    current = ""
    filled: list[str] = []
    for row in body:
        text = canonical_date(row[0])
        if text:
            current = text
        filled.append(current)

    dates: list[str] = []
    slot_texts: list[str] = []
    fc = np.empty((expected_days, len(hours), FC_HORIZON), dtype=float)
    for day in range(expected_days):
        day_dates = set()
        for slot_index, hour in enumerate(hours):
            offset = day * len(hours) + slot_index
            day_dates.add(filled[offset])
            got_hour = _slot_hour(body[offset][1])
            if got_hour != int(hour):
                raise InputValidationError(
                    f"附件 3 第 {offset + 2} 行预报时刻 {body[offset][1]!r} != 期望 {hour}:00"
                )
            try:
                values = np.array([float(item) for item in body[offset][2:]], dtype=float)
            except (TypeError, ValueError) as exc:
                raise InputValidationError(f"附件 3 第 {offset + 2} 行存在非数值预报：{exc}") from exc
            fc[day, slot_index, :] = values
        if len(day_dates) != 1 or not day_dates.pop():
            raise InputValidationError(f"附件 3 第 {day + 1} 天的日期前向填充不唯一")
        dates.append(filled[day * len(hours)])
        slot_texts.append(f"{int(hours[0])}:00")
    if not np.all(np.isfinite(fc)):
        raise InputValidationError("附件 3 预报含 NaN/Inf")
    if np.any(fc < 0):
        raise InputValidationError("附件 3 存在负预报")
    for index in range(1, len(dates)):
        if dates[index] == dates[index - 1]:
            raise InputValidationError(f"附件 3 日期未推进：{dates[index]}")
    return Attachment3(fc_kw=fc, dates=dates, slots=slot_texts, md5=md5_of(path))


def inspect_template(path: Path) -> dict[str, Any]:
    """读取 ``result3.xlsx`` 模板的逐行标签/表头，用于 AS01/AS16 对齐校验（不写入）。"""
    if not path.is_file():
        raise InputValidationError(f"模板不存在：{path}")
    workbook = openpyxl.load_workbook(path, data_only=True)
    try:
        titles = list(workbook.sheetnames)
        for name in (PLAN_SHEET, ADJUST_SHEET, STORAGE_SHEET, EMERGENCY_SHEET):
            if name not in titles:
                raise InputValidationError(f"模板缺少工作表『{name}』：{titles}")
        detail: dict[str, Any] = {}
        for name in (PLAN_SHEET, ADJUST_SHEET):
            sheet = workbook[name]
            header = [cell.value for cell in sheet[1]]
            if len(header) != PERIODS_PER_DAY + 3:
                raise InputValidationError(f"模板『{name}』列数 {len(header)} != 147")
            if str(header[0]).strip() != PLAN_HEADER_FIRST:
                raise InputValidationError(f"模板『{name}』首列表头异常：{header[0]!r}")
            if str(header[PERIODS_PER_DAY + 1]).strip() != PLAN_HEADER_ENERGY:
                raise InputValidationError(f"模板『{name}』第 146 列不是『{PLAN_HEADER_ENERGY}』")
            if str(header[PERIODS_PER_DAY + 2]).strip() != PLAN_HEADER_COST:
                raise InputValidationError(f"模板『{name}』第 147 列不是『{PLAN_HEADER_COST}』")
            labels = [str(item) for item in header[1 : PERIODS_PER_DAY + 1]]
            dates = [_date_label(sheet.cell(row=row, column=1).value) for row in range(2, sheet.max_row + 1)]
            detail[name] = {"labels": labels, "dates": dates, "rows": len(dates)}

        storage = workbook[STORAGE_SHEET]
        storage_header = ["" if cell.value is None else str(cell.value) for cell in storage[1]]
        if tuple(storage_header[: len(STORAGE_HEADER)]) != STORAGE_HEADER:
            raise InputValidationError(f"模板『{STORAGE_SHEET}』表头异常：{storage_header}")
        storage_blocks = [
            str(storage.cell(row=2 + k, column=2).value) for k in range(BLOCKS_PER_DAY)
        ]

        emergency = workbook[EMERGENCY_SHEET]
        emergency_header = ["" if cell.value is None else str(cell.value) for cell in emergency[1]]
        if tuple(emergency_header[: len(EMERGENCY_HEADER)]) != EMERGENCY_HEADER:
            raise InputValidationError(f"模板『{EMERGENCY_SHEET}』表头异常：{emergency_header}")

        merged = {name: [str(rng) for rng in workbook[name].merged_cells.ranges] for name in titles}
    finally:
        workbook.close()
    plan = detail[PLAN_SHEET]
    adjust = detail[ADJUST_SHEET]
    if plan["labels"] != adjust["labels"]:
        raise InputValidationError("模板『计划购电量』与『调整购电量』列标签不一致")
    return {
        "plan_labels": plan["labels"],
        "plan_dates": plan["dates"],
        "plan_rows": plan["rows"],
        "adjust_labels": adjust["labels"],
        "adjust_rows": adjust["rows"],
        "storage_header": storage_header,
        "storage_blocks": storage_blocks,
        "emergency_header": emergency_header,
        "merged": merged,
        "md5": md5_of(path),
    }


def _assign(sheet: Any, *, row: int, column: int, value: Any) -> None:
    """显式写单元格，``value=None`` 也**真正清空**（防 openpyxl 静默 no-op）。"""
    sheet.cell(row=row, column=column).value = value


# 交付数值的有效位（团队勘误 R10，2026-09-11）：求解器返回解带 1e-10 级噪声，
# 若不规整就会出现 ``1199.999999997668`` 这类**表观越界**（题面下界 1200）与 19 位小数，
# 评阅人会当成数据错误。交付 xlsx 一律按 6 位小数写入（绝对误差 ≤ 5e-7kWh，远小于任何报告量级）。
DELIVERY_DECIMALS = 6
# 附录 1 的运行区间（题面硬参数；此处只用于**交付投影**，不参与建模）。
STATE_MIN_KWH = 1200.0
STATE_MAX_KWH = 10800.0


def _num(value: Any) -> float:
    """交付数值规整：保留 ``DELIVERY_DECIMALS`` 位小数。"""
    return float(round(float(value), DELIVERY_DECIMALS))


def _state(value: Any, *, clip_log: list[float]) -> float:
    """储电量交付值：先规整，再投影到 ``[1200, 10800]``，并把最大修正量记入 ``clip_log``。"""
    raw = float(value)
    rounded = round(raw, DELIVERY_DECIMALS)
    projected = min(max(rounded, STATE_MIN_KWH), STATE_MAX_KWH)
    clip_log.append(abs(projected - raw))
    return float(projected)


def _clear_rows(sheet: Any, *, first_row: int, last_row: int, last_column: int) -> None:
    for row in range(first_row, last_row + 1):
        for column in range(1, last_column + 1):
            _assign(sheet, row=row, column=column, value=None)


def _residual_report(*, workbook: Any, days: int, emergency_rows: int) -> list[str]:
    """复核填报后的工作簿：枚举**应空却仍有值**的单元格（防静默 no-op 复发）。"""
    residuals: list[str] = []
    for name in (PLAN_SHEET, ADJUST_SHEET):
        sheet = workbook[name]
        for row in range(days + 2, int(sheet.max_row) + 1):
            for column in range(1, PERIODS_PER_DAY + 4):
                if sheet.cell(row=row, column=column).value is not None:
                    residuals.append(f"{name}!{get_column_letter(column)}{row}（超出行数）")
                    break
    storage = workbook[STORAGE_SHEET]
    for index in range(days):
        for block in range(BLOCKS_PER_DAY):
            row = 2 + index * BLOCKS_PER_DAY + block
            if block != 0 and storage.cell(row=row, column=1).value is not None:
                residuals.append(f"充放电量!A{row}（日期只写块首行）")
            if block >= 2 and storage.cell(row=row, column=5).value is not None:
                residuals.append(f"充放电量!E{row}（时刻只写每日前两行）")
            if block >= 2 and storage.cell(row=row, column=6).value is not None:
                residuals.append(f"充放电量!F{row}（储电量只写每日前两行）")
    expected_storage_rows = 1 + days * BLOCKS_PER_DAY
    for row in range(expected_storage_rows + 1, int(storage.max_row) + 1):
        for column in range(1, len(STORAGE_HEADER) + 1):
            if storage.cell(row=row, column=column).value is not None:
                residuals.append(f"充放电量!{get_column_letter(column)}{row}（超出行数）")
                break
    emergency = workbook[EMERGENCY_SHEET]
    for row in range(1 + emergency_rows + 1, int(emergency.max_row) + 1):
        for column in range(1, len(EMERGENCY_HEADER) + 1):
            if emergency.cell(row=row, column=column).value is not None:
                residuals.append(f"紧急购电量!{get_column_letter(column)}{row}（超出行数）")
                break
    for name in workbook.sheetnames:
        for row in workbook[name].iter_rows(values_only=True):
            for value in row:
                if isinstance(value, str) and "⁝" in value:
                    residuals.append(f"{name}!不得残留模板 ⁝ 压缩行")
    total = len(residuals)
    if total > 200:
        residuals = residuals[:200] + [f"…（共 {total} 处，已截断）"]
    return residuals


def fill_result3_workbook(
    *,
    template: Path,
    dest: Path,
    dates: Sequence[str],
    planned_kwh: np.ndarray,
    adjusted_kwh: np.ndarray,
    charge_kwh: np.ndarray,
    discharge_kwh: np.ndarray,
    state_start_kwh: np.ndarray,
    state_end_kwh: np.ndarray,
    day_energy_planned_kwh: np.ndarray,
    day_energy_adjusted_kwh: np.ndarray,
    day_cost_yuan: np.ndarray,
    emergency_intervals: Sequence[Sequence[tuple[str, float]]],
) -> dict[str, Any]:
    """把交付期解填入 ``result3.xlsx`` 四个工作表（保留模板标签与样式，只写数值单元格）。

    口径（AS16 + 团队裁定 D4-A/D8-A/D11-A）：
      * ``计划购电量``：``b``；末两列 ``全天购电量 = Σb``、``全天购电费 = C_total``；
      * ``调整购电量``：最终量 ``q``（替代量）；末两列 ``Σq``、``C_total``；
      * ``充放电量``：334 天 × 6 个 4 小时块，日期只写块首行；``时刻``/``储电量`` 写在每日前两行；
      * ``紧急购电量``：每日期至少 1 行；``J_d = 0`` 的日期写 ``时间段 = —``、``购电量 = 0``。
    """
    days = len(dates)
    planned = np.asarray(planned_kwh, dtype=float)
    adjusted = np.asarray(adjusted_kwh, dtype=float)
    charge = np.asarray(charge_kwh, dtype=float)
    discharge = np.asarray(discharge_kwh, dtype=float)
    clip_log: list[float] = []
    if planned.shape != (days, PERIODS_PER_DAY):
        raise InputValidationError(f"planned 形状 {planned.shape} != ({days}, {PERIODS_PER_DAY})")
    for label, array in (("adjusted", adjusted), ("charge", charge), ("discharge", discharge)):
        if array.shape != planned.shape:
            raise InputValidationError(f"{label} 形状与 planned 不一致")
    if len(emergency_intervals) != days:
        raise InputValidationError("emergency_intervals 天数与 dates 不一致")
    if not template.is_file():
        raise InputValidationError(f"模板不存在：{template}")

    workbook = openpyxl.load_workbook(template)
    try:
        titles = list(workbook.sheetnames)
        for name in (PLAN_SHEET, ADJUST_SHEET, STORAGE_SHEET, EMERGENCY_SHEET):
            if name not in titles:
                raise InputValidationError(f"模板缺少工作表『{name}』：{titles}")

        for name, values, energy, cost_source in (
            (PLAN_SHEET, planned, day_energy_planned_kwh, day_cost_yuan),
            (ADJUST_SHEET, adjusted, day_energy_adjusted_kwh, day_cost_yuan),
        ):
            sheet = workbook[name]
            if sheet.max_row < days + 1:
                raise InputValidationError(f"模板『{name}』只有 {sheet.max_row - 1} 行，少于 {days} 天")
            for index, date_text in enumerate(dates):
                row = 2 + index
                actual = _date_label(sheet.cell(row=row, column=1).value)
                if actual != date_text:
                    raise InputValidationError(f"模板『{name}』第 {row} 行日期 {actual!r} != {date_text!r}")
                for period in range(PERIODS_PER_DAY):
                    _assign(sheet, row=row, column=2 + period, value=_num(values[index, period]))
                _assign(sheet, row=row, column=PERIODS_PER_DAY + 2, value=_num(energy[index]))
                _assign(sheet, row=row, column=PERIODS_PER_DAY + 3, value=_num(cost_source[index]))
            if sheet.max_row > days + 1:
                _clear_rows(sheet, first_row=days + 2, last_row=sheet.max_row, last_column=PERIODS_PER_DAY + 3)

        storage = workbook[STORAGE_SHEET]
        storage_blocks = [str(storage.cell(row=2 + k, column=2).value) for k in range(BLOCKS_PER_DAY)]
        blocks_filled = 0
        for index, date_text in enumerate(dates):
            date_value = datetime.strptime(date_text, "%Y-%m-%d")
            for block in range(BLOCKS_PER_DAY):
                row = 2 + index * BLOCKS_PER_DAY + block
                start = block * BLOCK_ROWS
                stop = start + BLOCK_ROWS
                _assign(storage, row=row, column=1, value=date_value if block == 0 else None)
                _assign(storage, row=row, column=2, value=storage_blocks[block])
                _assign(storage, row=row, column=3, value=_num(np.sum(charge[index, start:stop])))
                _assign(storage, row=row, column=4, value=_num(np.sum(discharge[index, start:stop])))
                _assign(
                    storage,
                    row=row,
                    column=5,
                    value="00:00:00" if block == 0 else ("24:00" if block == 1 else None),
                )
                _assign(
                    storage,
                    row=row,
                    column=6,
                    value=_state(state_start_kwh[index], clip_log=clip_log) if block == 0 else (
                        _state(state_end_kwh[index], clip_log=clip_log) if block == 1 else None
                    ),
                )
                blocks_filled += 1
        expected_storage_rows = 1 + days * BLOCKS_PER_DAY
        if storage.max_row > expected_storage_rows:
            _clear_rows(storage, first_row=expected_storage_rows + 1, last_row=storage.max_row, last_column=6)

        emergency = workbook[EMERGENCY_SHEET]
        row = 2
        interval_rows = 0
        for index, date_text in enumerate(dates):
            date_value = datetime.strptime(date_text, "%Y-%m-%d")
            intervals = list(emergency_intervals[index])
            if not intervals:
                intervals = [(ZERO_INTERVAL_TEXT, 0.0)]
            for order, (slot, kwh) in enumerate(intervals):
                _assign(emergency, row=row, column=1, value=date_value if order == 0 else None)
                _assign(emergency, row=row, column=2, value=slot)
                _assign(emergency, row=row, column=3, value=_num(kwh))
                row += 1
                interval_rows += 1
        expected_emergency_rows = row - 1
        if emergency.max_row > expected_emergency_rows:
            _clear_rows(emergency, first_row=expected_emergency_rows + 1, last_row=emergency.max_row, last_column=3)

        dest.parent.mkdir(parents=True, exist_ok=True)
        residuals = _residual_report(workbook=workbook, days=days, emergency_rows=interval_rows)
        workbook.save(dest)
    finally:
        workbook.close()
    return {
        "plan_rows_filled": days,
        "plan_periods_per_row": PERIODS_PER_DAY,
        "adjust_rows_filled": days,
        "storage_blocks_filled": blocks_filled,
        "emergency_rows_filled": interval_rows,
        "storage_blocks": storage_blocks,
        "format_residuals": residuals,
        "delivery_decimals": DELIVERY_DECIMALS,
        "storage_projection": {
            "bounds_kwh": [STATE_MIN_KWH, STATE_MAX_KWH],
            "max_abs_correction_kwh": max(clip_log) if clip_log else 0.0,
            "cells": len(clip_log),
        },
    }


def write_json(path: Path, payload: Any) -> None:
    """写 JSON；显式拒绝 NaN/Inf，避免把非有限值伪装成合法结果。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    path.write_text(text + "\n", encoding="utf-8")


def delivery_dates(all_dates: Sequence[str], start_day_index: int) -> list[str]:
    """交付期日期列表（默认 2025-02-01 … 2025-12-31，334 天）。"""
    return [str(item) for item in all_dates[start_day_index:]]


def day_offset(dates: Sequence[str], target: str) -> int:
    """在附件 2 的日期序列中定位目标的 0 基日索引；找不到时严格失败。"""
    for index, item in enumerate(dates):
        if item == target:
            return index
    raise InputValidationError(f"附件 2 日期序列中找不到 {target}")


__all__ = [
    "ADJUST_SHEET",
    "Attachment1",
    "Attachment2",
    "Attachment3",
    "BLOCKS_PER_DAY",
    "BLOCK_ROWS",
    "DECISION_HOURS",
    "EMERGENCY_SHEET",
    "FC_HORIZON",
    "InputValidationError",
    "PERIODS_PER_DAY",
    "PLAN_SHEET",
    "STORAGE_SHEET",
    "ZERO_INTERVAL_TEXT",
    "canonical_date",
    "day_offset",
    "delivery_dates",
    "fill_result3_workbook",
    "inspect_template",
    "md5_of",
    "read_attachment1",
    "read_attachment2",
    "read_attachment3",
    "write_json",
]
