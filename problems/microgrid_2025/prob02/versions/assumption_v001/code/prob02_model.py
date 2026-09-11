# -*- coding: utf-8 -*-
"""prob02 计划购电 LP（M1 主口径）的建模、求解与结构自检。

模型 (P2) 严格对应 ``formulation_v001`` / ``assumption_v001``，并按团队裁定 B0 只实现**主口径 M1**：
``365 天 × 144 时段 = 52,560`` 时段的单一确定性 LP（连续变量 315,360、等式约束 105,120、非零元 473,039）。

口径（不得逐问更改）：
``Δt = 1/6 h``、``η_ch = η_dis = 0.9``、``c ≤ 833.3333``、``q_dis ≤ 750.0000``（D10 口径丙 / 勘误 E1）、
``E ∈ [1200, 10800]``、``E_0 = 6000``、``E_T`` 自由（AS04/D2 备选 A）、``α_em = 5``、
目标 ``min Σ (p·b + 5·p·q_em)``（元，**不乘 Δt**，团队裁定 D9）。
求解器：CPU HiGHS（``scipy.optimize.linprog``）；本问不使用 GPU、不依赖随机源（``seed = null``）。

模型间对照（M2–M7）按团队裁定 B1/B5 由 ``ablation`` 阶段在 ``ablations/code/`` 下另建，本模块只提供 M1。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, csr_matrix

DELTA_T = 1.0 / 6.0
ETA_CH = 0.9
ETA_DIS = 0.9
ETA_ROUND_TRIP = ETA_CH * ETA_DIS
E_INIT = 6000.0
E_MIN = 1200.0
E_MAX = 10800.0
E_CAP_MAX = 12000.0
P_MAX = 5000.0
C_CAP = P_MAX * DELTA_T                 # 833.3333 kWh（并网点侧为紧侧）
Q_CAP = P_MAX * DELTA_T * ETA_DIS       # 750.0000 kWh（电池侧为紧侧，D10 口径丙）
ALPHA_EM = 5.0
PERIODS_PER_DAY = 144
DAYS_FULL = 365
DAILY_DELIVERY_START = 31               # 0 基日索引：2025-02-01（1 月为预热期）
TOL = 1e-6
KINDS = ("b", "q_em", "c", "q_dis", "s", "E")

# 解析界（formulation_v001 §3.10；全年）
LOWER_BOUND_FULL_YUAN = 7_525_691.1311
UPPER_NO_STORAGE_FULL_YUAN = 18_298_592.3663
UPPER_NO_STORAGE_DELIVERY_YUAN = 16_407_319.6320
DELIVERY_COST_SCALE_FLOOR_YUAN = 1.0e7   # 交付期总费用的量级自检下限（10^7 元）
SPEC_DATES: tuple[tuple[str, int], ...] = (
    ("2025-03-20", 78),
    ("2025-06-21", 171),
    ("2025-09-23", 265),
    ("2025-12-21", 354),
)
TABLE1_SLOTS: tuple[tuple[str, int], ...] = (
    ("10:00-10:10", 60),
    ("12:00-12:10", 72),
    ("14:00-14:10", 84),
    ("16:00-16:10", 96),
    ("18:00-18:10", 108),
    ("20:00-20:10", 120),
)
BLOCK_ROWS = 24
BLOCKS_PER_DAY = 6


@dataclass(frozen=True)
class LpData:
    """按 ``days`` 展开的 LP 输入（探针模式可短于 365 天）。"""

    price: np.ndarray          # (T,)，附件 1 电价逐日重复
    load_energy: np.ndarray    # (T,)，负载功率 × Δt
    pv_energy: np.ndarray      # (T,)，光伏功率 × Δt
    days: int

    @property
    def periods(self) -> int:
        return int(self.days * PERIODS_PER_DAY)

    @property
    def net_load_energy(self) -> float:
        return float(np.sum(self.load_energy - self.pv_energy))

    @property
    def total_load_energy(self) -> float:
        return float(np.sum(self.load_energy))

    @property
    def total_pv_energy(self) -> float:
        return float(np.sum(self.pv_energy))


@dataclass
class LpSolution:
    data: LpData
    status: int
    message: str
    iterations: int | None
    objective: float
    x: np.ndarray
    equality_residual_max: float
    bound_violation_max: float

    def column(self, kind: str) -> np.ndarray:
        if kind not in KINDS:
            raise ValueError(f"未知变量种类：{kind}")
        periods = self.data.periods
        offset = KINDS.index(kind) * periods
        return self.x[offset : offset + periods]

    def daily(self, kind: str) -> np.ndarray:
        """把某一类变量按 ``(days, 144)`` 展开。"""
        return self.column(kind).reshape(self.data.days, PERIODS_PER_DAY)


def _index(kind: str, period: int, periods: int) -> int:
    return KINDS.index(kind) * periods + period


def build_lp(data: LpData) -> tuple[np.ndarray, csr_matrix, np.ndarray, np.ndarray, np.ndarray]:
    """构造 ``min c^T x s.t. A_eq x = b_eq, l <= x <= u``（与 formulation_v001 §3.9 逐项对应）。

    返回 ``(objective, A_eq, b_eq, lower, upper)``；``A_eq`` 为 CSR 稀疏矩阵
    （``2T × 6T``，非零元 ``9T − 1``）。
    """
    periods = data.periods
    size = len(KINDS) * periods
    if data.load_energy.shape != (periods,) or data.pv_energy.shape != (periods,):
        raise ValueError("load/pv 长度与 days × 144 不一致")

    objective = np.zeros(size)
    objective[0:periods] = data.price
    objective[periods : 2 * periods] = ALPHA_EM * data.price

    lower = np.zeros(size)
    upper = np.empty(size)
    lower[0:periods] = 0.0                                    # b >= 0（无购电上限，AS10）
    upper[0:periods] = np.inf
    lower[periods : 2 * periods] = 0.0                        # q_em >= 0（保留变量，AS07）
    upper[periods : 2 * periods] = np.inf
    lower[2 * periods : 3 * periods] = 0.0                    # 0 <= c <= 833.3333
    upper[2 * periods : 3 * periods] = C_CAP
    lower[3 * periods : 4 * periods] = 0.0                    # 0 <= q_dis <= 750.0000
    upper[3 * periods : 4 * periods] = Q_CAP
    lower[4 * periods : 5 * periods] = 0.0                    # 0 <= s <= PV * Δt
    upper[4 * periods : 5 * periods] = data.pv_energy
    lower[5 * periods : 6 * periods] = E_MIN                  # 1200 <= E <= 10800
    upper[5 * periods : 6 * periods] = E_MAX

    tau = np.arange(periods, dtype=np.int64)
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    vals: list[np.ndarray] = []
    # (R1) 逐时段电量平衡：b + q_em + q_dis − c − s = L·Δt − PV·Δt
    rows.append(tau)
    cols.append(_index("b", 0, periods) + tau)
    vals.append(np.ones(periods))
    rows.append(tau)
    cols.append(_index("q_em", 0, periods) + tau)
    vals.append(np.ones(periods))
    rows.append(tau)
    cols.append(_index("q_dis", 0, periods) + tau)
    vals.append(np.ones(periods))
    rows.append(tau)
    cols.append(_index("c", 0, periods) + tau)
    vals.append(-np.ones(periods))
    rows.append(tau)
    cols.append(_index("s", 0, periods) + tau)
    vals.append(-np.ones(periods))
    # (R2) SOC 动态：E_τ − E_{τ−1} − η_ch·c_τ + q_dis_τ/η_dis = 0，τ = 1 时 RHS = E_0
    rows.append(periods + tau)
    cols.append(_index("E", 0, periods) + tau)
    vals.append(np.ones(periods))
    rows.append(periods + tau[1:])
    cols.append(_index("E", 0, periods) + tau[1:] - 1)
    vals.append(-np.ones(periods - 1))
    rows.append(periods + tau)
    cols.append(_index("c", 0, periods) + tau)
    vals.append(-ETA_CH * np.ones(periods))
    rows.append(periods + tau)
    cols.append(_index("q_dis", 0, periods) + tau)
    vals.append((1.0 / ETA_DIS) * np.ones(periods))

    a_eq = coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(2 * periods, size),
    ).tocsr()
    b_eq = np.concatenate(
        [data.load_energy - data.pv_energy, np.concatenate([[E_INIT], np.zeros(periods - 1)])]
    )
    return objective, a_eq, b_eq, lower, upper


def solve_lp(data: LpData, *, time_limit_seconds: float = 300.0) -> LpSolution:
    """用 CPU HiGHS 求解 LP，并返回含约束残差的解。"""
    objective, a_eq, b_eq, lower, upper = build_lp(data)
    # scipy 的 linprog 只接受 (n, 2) 的界序列/数组；这里用 column_stack 保持 O(n) 内存。
    bounds = np.column_stack((lower, upper))
    result = linprog(
        objective,
        A_eq=a_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
        options={"time_limit": float(time_limit_seconds), "presolve": True},
    )
    if result.x is None:
        x = np.full(objective.shape[0], np.nan)
        equality_residual = float("nan")
        bound_violation = float("nan")
    else:
        x = np.asarray(result.x, dtype=float)
        equality_residual = float(np.max(np.abs(a_eq @ x - b_eq)))
        violation_low = float(np.max(lower - x))
        finite_upper = np.where(np.isfinite(upper), x - upper, -np.inf)
        violation_up = float(np.max(finite_upper))
        bound_violation = max(violation_low, violation_up, 0.0)
    return LpSolution(
        data=data,
        status=int(result.status),
        message=str(result.message),
        iterations=int(result.nit) if result.nit is not None else None,
        objective=float(result.fun) if result.fun is not None else float("nan"),
        x=x,
        equality_residual_max=equality_residual,
        bound_violation_max=bound_violation,
    )


def day_slice(days: int, day: int) -> slice:
    return slice(day * PERIODS_PER_DAY, (day + 1) * PERIODS_PER_DAY)


def state_series(solution: LpSolution) -> np.ndarray:
    """返回长度 ``T + 1`` 的储电量序列 ``[E_0, E_1, …, E_T]``（``E_0 = E_INIT``）。"""
    storage = solution.column("E")
    return np.concatenate([[E_INIT], storage])


def merge_interval_labels(mask: np.ndarray) -> list[tuple[int, int]]:
    """把布尔掩码的连续 True 段合并为 ``(start, stop)`` 半开区间（0 基时段下标）。"""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, flag in enumerate(mask):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


def _format_minutes(total_minutes: int) -> str:
    """把「左端点分钟数」格式化为 ``H:MM``；≥1440 时按 AS01 写 ``+1``。"""
    if total_minutes < 1440:
        return f"{total_minutes // 60}:{total_minutes % 60:02d}"
    shifted = total_minutes - 1440
    return f"{shifted // 60}:{shifted % 60:02d}+1"


def interval_label(labels: list[str], start: int, stop: int) -> str:
    """按 AS12 生成 ``[τ_i, τ_j + 10min)`` 的区间标签（左端点口径）。"""
    start_label = labels[start]
    end_minutes = 10 * (stop + 1)
    return f"{start_label}-{_format_minutes(end_minutes)}"


def emergency_intervals(
    q_em_day: np.ndarray, labels: list[str], *, tol: float = TOL
) -> list[dict[str, Any]]:
    """逐日紧急购电区间（连续 10 分钟时段合并，AS12/A18）。"""
    mask = np.asarray(q_em_day, dtype=float) > tol
    out: list[dict[str, Any]] = []
    for start, stop in merge_interval_labels(mask):
        out.append(
            {
                "slot": interval_label(labels, start, stop),
                "start_period": int(start + 1),
                "stop_period": int(stop),
                "energy_kwh": round(float(np.sum(q_em_day[start:stop])), 6),
            }
        )
    return out


def _round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def evaluate(solution: LpSolution, *, full_horizon: bool = True) -> dict[str, Any]:
    """计算交付指标、结构恒等式 (I1)/(I2)（全期与交付期切片）与全部硬约束检查。"""
    data = solution.data
    days = data.days
    periods = data.periods
    purchase = solution.column("b")
    q_em = solution.column("q_em")
    charge = solution.column("c")
    discharge = solution.column("q_dis")
    spill = solution.column("s")
    state = state_series(solution)

    checks: list[dict[str, Any]] = []

    def record(name: str, value: float, threshold: float, passed: bool, note: str = "") -> None:
        checks.append(
            {"name": name, "value": float(value), "threshold": float(threshold), "passed": bool(passed), "note": note}
        )

    total_purchase = float(np.sum(purchase))
    total_q_em = float(np.sum(q_em))
    total_charge = float(np.sum(charge))
    total_discharge = float(np.sum(discharge))
    total_spill = float(np.sum(spill))
    cost_plan = float(np.sum(data.price * purchase))
    cost_em = float(np.sum(ALPHA_EM * data.price * q_em))
    cost = cost_plan + cost_em
    net_load = data.net_load_energy
    storage_final = float(state[periods])

    delivery_start = min(DAILY_DELIVERY_START, days)
    delivery = np.zeros(periods, dtype=bool)
    delivery[delivery_start * PERIODS_PER_DAY :] = True
    if delivery.any():
        state_at_delivery_start = float(state[delivery_start * PERIODS_PER_DAY])
        net_load_delivery = float(np.sum(data.load_energy[delivery] - data.pv_energy[delivery]))
        cost_delivery = float(
            np.sum(data.price[delivery] * purchase[delivery])
            + np.sum(ALPHA_EM * data.price[delivery] * q_em[delivery])
        )
        identity_i1_delivery = float(
            np.sum(discharge[delivery])
            - (ETA_ROUND_TRIP * np.sum(charge[delivery]) - ETA_DIS * (storage_final - state_at_delivery_start))
        )
        identity_i2_delivery = float(
            np.sum(purchase[delivery])
            - (
                net_load_delivery
                + float(np.sum(spill[delivery]))
                + (1.0 - ETA_ROUND_TRIP) * float(np.sum(charge[delivery]))
                + ETA_DIS * (storage_final - state_at_delivery_start)
                - float(np.sum(q_em[delivery]))
            )
        )
        warmup = slice(0, delivery_start * PERIODS_PER_DAY)
        january_cost = float(
            np.sum(data.price[warmup] * purchase[warmup]) + np.sum(ALPHA_EM * data.price[warmup] * q_em[warmup])
        )
    else:
        net_load_delivery = 0.0
        cost_delivery = 0.0
        january_cost = 0.0
        identity_i1_delivery = 0.0
        identity_i2_delivery = 0.0

    identity_i1 = total_discharge - (ETA_ROUND_TRIP * total_charge - ETA_DIS * (storage_final - E_INIT))
    identity_i2 = total_purchase - (
        net_load
        + total_spill
        + (1.0 - ETA_ROUND_TRIP) * total_charge
        + ETA_DIS * (storage_final - E_INIT)
        - total_q_em
    )

    day_start = state[:periods:PERIODS_PER_DAY]
    day_end = state[PERIODS_PER_DAY :: PERIODS_PER_DAY]
    continuity_gap = float(np.max(np.abs(day_start[1:] - day_end[:-1]))) if days > 1 else 0.0

    worst_bound = solution.bound_violation_max
    storage_upper_gap = max(float(np.max(state[1:])) - E_MAX, 0.0)
    storage_lower_gap = max(E_MIN - float(np.min(state[1:])), 0.0)
    charge_gap = max(float(np.max(charge)) - C_CAP, 0.0)
    discharge_gap = max(float(np.max(discharge)) - Q_CAP, 0.0)
    spill_gap = max(float(np.max(spill - data.pv_energy)), 0.0)
    purchase_gap = max(-float(np.min(purchase)), 0.0)
    q_em_gap = max(-float(np.min(q_em)), 0.0)
    complementarity = float(np.sum(charge * discharge))

    charge_power_ac = charge / DELTA_T
    charge_power_dc = ETA_CH * charge / DELTA_T
    discharge_power_ac = discharge / DELTA_T
    discharge_power_dc = discharge / (ETA_DIS * DELTA_T)
    worst_power = float(
        max(
            np.max(charge_power_ac),
            np.max(charge_power_dc),
            np.max(discharge_power_ac),
            np.max(discharge_power_dc),
        )
    )

    record("equality_residual_max", solution.equality_residual_max, TOL,
           solution.equality_residual_max <= TOL, "(R1)/(R2) 等式残差")
    record("bound_violation_max", worst_bound, TOL, worst_bound <= TOL, "变量界越界量")
    record("storage_upper_violation", storage_upper_gap, TOL,
           float(np.max(state[1:])) <= E_MAX + TOL, "E_τ <= 10800")
    record("storage_lower_violation", storage_lower_gap, TOL,
           float(np.min(state[1:])) >= E_MIN - TOL, "E_τ >= 1200")
    record("charge_cap_violation", charge_gap, TOL, float(np.max(charge)) <= C_CAP + TOL,
           "c_τ <= 833.3333（并网点侧紧）")
    record("discharge_cap_violation", discharge_gap, TOL, float(np.max(discharge)) <= Q_CAP + TOL,
           "q_dis_τ <= 750.0000（电池侧紧，D10 口径丙 / E1）")
    record("spill_bound_violation", spill_gap, TOL, bool(np.all(spill <= data.pv_energy + TOL)),
           "0 <= s_τ <= PV_τ·Δt")
    record("purchase_nonneg_violation", purchase_gap, TOL, float(np.min(purchase)) >= -TOL, "b_τ >= 0")
    record("q_em_nonneg_violation", q_em_gap, TOL, float(np.min(q_em)) >= -TOL, "q_em,τ >= 0")
    record("cross_day_continuity", continuity_gap, TOL, continuity_gap <= TOL, "|E_{d,0} − E_{d−1,144}|")
    record("q_em_zero_total", total_q_em, TOL, total_q_em <= TOL,
           "定理 T1：完全信息 + 无购电上限 ⇒ Σ q_em = 0（AS07/AS10）")
    record("complementarity_sum", complementarity, TOL, complementarity <= TOL,
           "AS07 同时充放电残差（引理 L1）")
    record("max_side_power_kw", worst_power, P_MAX, worst_power <= P_MAX + 1e-3,
           "并网点侧与电池侧换算功率均 <= 5000 kW")
    record("identity_I1_residual", identity_i1, TOL, abs(identity_i1) <= TOL,
           "Σq_dis = η²Σc − η(E_T − E_0)")
    record("identity_I2_residual", identity_i2, TOL, abs(identity_i2) <= TOL,
           "Σb = N + Σs + 0.19Σc + η(E_T − E_0) − Σq_em")
    if delivery_start < days:
        record("identity_I1_delivery_residual", identity_i1_delivery, TOL, abs(identity_i1_delivery) <= TOL,
               "交付期切片（E_{2/1,0} → E_T）")
        record("identity_I2_delivery_residual", identity_i2_delivery, TOL, abs(identity_i2_delivery) <= TOL,
               "交付期切片（N_req）")

    if full_horizon:
        lower_bound = float(np.min(data.price) * (net_load + ETA_DIS * (E_MIN - E_INIT)))
        no_storage_cost = float(np.sum(data.price * np.maximum(data.load_energy - data.pv_energy, 0.0)))
        record("analytic_lower_bound", cost, lower_bound, cost >= lower_bound - 1e-6,
               "C >= min(p)·[N + η(E_min − E_0)]")
        record("analytic_upper_bound", no_storage_cost, cost, cost <= no_storage_cost + 1e-6,
               "无储能可行解的购电费上界")
        record("magnitude_delivery_10m", cost_delivery, DELIVERY_COST_SCALE_FLOOR_YUAN,
               cost_delivery >= DELIVERY_COST_SCALE_FLOOR_YUAN,
               "B2 第 5 条：交付期总费用须为 10^7 元量级（防 D9 的 Δt 误乘）")

    purchase_d = solution.daily("b")
    charge_d = solution.daily("c")
    discharge_d = solution.daily("q_dis")
    spill_d = solution.daily("s")
    q_em_d = solution.daily("q_em")
    price_d = data.price.reshape(days, PERIODS_PER_DAY)
    cost_plan_d = np.sum(price_d * purchase_d, axis=1)
    cost_em_d = np.sum(ALPHA_EM * price_d * q_em_d, axis=1)

    series = {
        "period_index": list(range(1, periods + 1)),
        "price_yuan_per_kwh": [float(v) for v in data.price],
        "load_energy_kwh": [float(v) for v in data.load_energy],
        "pv_energy_kwh": [float(v) for v in data.pv_energy],
        "purchase_kwh": [float(v) for v in purchase],
        "q_em_kwh": [float(v) for v in q_em],
        "charge_kwh": [float(v) for v in charge],
        "discharge_kwh": [float(v) for v in discharge],
        "spill_kwh": [float(v) for v in spill],
        "storage_kwh": [float(v) for v in solution.column("E")],
    }
    return {
        "objective_yuan": _round(cost),
        "objective_plan_yuan": _round(cost_plan),
        "objective_emergency_yuan": _round(cost_em),
        "delivery_cost_yuan": _round(cost_delivery),
        "january_cost_yuan": _round(january_cost),
        "totals": {
            "total_purchase_kwh": _round(total_purchase),
            "total_q_em_kwh": _round(total_q_em),
            "total_charge_kwh": _round(total_charge),
            "total_discharge_kwh": _round(total_discharge),
            "total_spill_kwh": _round(total_spill),
            "net_load_kwh": _round(net_load),
            "net_load_delivery_kwh": _round(net_load_delivery),
            "total_load_kwh": _round(data.total_load_energy),
            "total_pv_kwh": _round(data.total_pv_energy),
            "max_charge_kwh": _round(float(np.max(charge))),
            "max_discharge_kwh": _round(float(np.max(discharge))),
            "max_purchase_kwh": _round(float(np.max(purchase))),
            "max_purchase_power_kw": _round(float(np.max(purchase)) / DELTA_T, 6),
            "max_side_power_kw": _round(worst_power),
            "storage_initial_kwh": _round(E_INIT),
            "storage_final_kwh": _round(storage_final),
            "storage_range_kwh": [_round(float(np.min(state[1:]))), _round(float(np.max(state[1:])))],
            "days_with_emergency": int(np.sum(np.any(q_em_d > TOL, axis=1))),
            "simultaneous_charge_discharge_periods": int(np.sum((charge > TOL) & (discharge > TOL))),
            "day_start_unique_levels": int(len(np.unique(np.round(day_start, 6)))),
        },
        "identities": {
            "I1_residual": float(identity_i1),
            "I2_residual": float(identity_i2),
            "I1_delivery_residual": float(identity_i1_delivery),
            "I2_delivery_residual": float(identity_i2_delivery),
            "continuity_residual_max": float(continuity_gap),
        },
        "daily": {
            "day_index": list(range(days)),
            "purchase_kwh": [_round(v) for v in np.sum(purchase_d, axis=1)],
            "q_em_kwh": [_round(v) for v in np.sum(q_em_d, axis=1)],
            "charge_kwh": [_round(v) for v in np.sum(charge_d, axis=1)],
            "discharge_kwh": [_round(v) for v in np.sum(discharge_d, axis=1)],
            "spill_kwh": [_round(v) for v in np.sum(spill_d, axis=1)],
            "cost_plan_yuan": [_round(v) for v in cost_plan_d],
            "cost_emergency_yuan": [_round(v) for v in cost_em_d],
            "cost_total_yuan": [_round(v) for v in (cost_plan_d + cost_em_d)],
            "state_start_kwh": [_round(v) for v in day_start],
            "state_end_kwh": [_round(v) for v in day_end],
        },
        "checks": checks,
        "checks_failed": [item["name"] for item in checks if not item["passed"]],
        "series": series,
    }


__all__ = [
    "ALPHA_EM",
    "BLOCKS_PER_DAY",
    "BLOCK_ROWS",
    "C_CAP",
    "DAILY_DELIVERY_START",
    "DAYS_FULL",
    "DELTA_T",
    "E_CAP_MAX",
    "E_INIT",
    "E_MAX",
    "E_MIN",
    "ETA_CH",
    "ETA_DIS",
    "ETA_ROUND_TRIP",
    "LpData",
    "LpSolution",
    "P_MAX",
    "PERIODS_PER_DAY",
    "Q_CAP",
    "SPEC_DATES",
    "TABLE1_SLOTS",
    "TOL",
    "build_lp",
    "day_slice",
    "emergency_intervals",
    "evaluate",
    "interval_label",
    "merge_interval_labels",
    "solve_lp",
    "state_series",
]
