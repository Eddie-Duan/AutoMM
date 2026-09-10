# -*- coding: utf-8 -*-
"""prob01 计划购电 LP 的建模、求解与结构自检。

模型 (P1) 严格对应 formulation_v001 / assumption_v003，并按团队勘误 E1 取
``q_dis_t <= 750.00``（D10 口径丙）。求解器：CPU HiGHS（``scipy.optimize.linprog``），
本问为确定性 LP，不使用 GPU、不依赖随机种子。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import linprog

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
TOL = 1e-6
KINDS = ("b", "c", "q", "s", "E")


@dataclass(frozen=True)
class LpData:
    """已按 ``periods`` 截断的 LP 输入（仅在探针模式下短于 144）。"""

    price: np.ndarray
    load_kw: np.ndarray
    pv_kw: np.ndarray
    periods: int
    time_labels: tuple[str, ...] = ()

    @property
    def load_energy(self) -> np.ndarray:
        return self.load_kw * DELTA_T

    @property
    def pv_energy(self) -> np.ndarray:
        return self.pv_kw * DELTA_T

    @property
    def net_load_energy(self) -> float:
        return float(np.sum(self.load_energy - self.pv_energy))


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
        offset = KINDS.index(kind) * self.data.periods
        return self.x[offset : offset + self.data.periods]


def _index(kind: str, period: int, periods: int) -> int:
    return KINDS.index(kind) * periods + period


def build_lp(data: LpData) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[tuple[float, float | None]]]:
    """构造 ``min c^T x s.t. A_eq x = b_eq, l <= x <= u``（与 formulation_v001 §3.8 逐项对应）。"""
    periods = data.periods
    size = len(KINDS) * periods
    objective = np.zeros(size)
    for period in range(periods):
        objective[_index("b", period, periods)] = data.price[period]

    rows: list[np.ndarray] = []
    rhs: list[float] = []
    for period in range(periods):                        # (R1) 逐时段电量平衡，单位 kWh
        row = np.zeros(size)
        row[_index("b", period, periods)] = 1.0
        row[_index("q", period, periods)] = 1.0
        row[_index("c", period, periods)] = -1.0
        row[_index("s", period, periods)] = -1.0
        rows.append(row)
        rhs.append(data.load_energy[period] - data.pv_energy[period])
    for period in range(periods):                        # (R2) SOC 动态，单位 kWh
        row = np.zeros(size)
        row[_index("E", period, periods)] = 1.0
        if period > 0:
            row[_index("E", period - 1, periods)] = -1.0
        row[_index("c", period, periods)] = -ETA_CH
        row[_index("q", period, periods)] = 1.0 / ETA_DIS
        rows.append(row)
        rhs.append(E_INIT if period == 0 else 0.0)

    bounds: list[tuple[float, float | None]] = []
    for kind in KINDS:
        for period in range(periods):
            if kind == "b":
                bounds.append((0.0, None))                                  # (AS15) 无购电上限
            elif kind == "c":
                bounds.append((0.0, C_CAP))                                 # (R7a) 833.3333
            elif kind == "q":
                bounds.append((0.0, Q_CAP))                                 # (R7b) 750.0000
            elif kind == "s":
                bounds.append((0.0, data.pv_energy[period]))                # (R3)
            else:
                # (R4)+(R6)：末时段固定为 E_INIT，其余落在运行区间内；E 下标 t 表示第 t 时段末状态。
                bounds.append((E_INIT, E_INIT) if period == periods - 1 else (E_MIN, E_MAX))
    return objective, np.array(rows, dtype=float), np.array(rhs, dtype=float), bounds


def solve_lp(data: LpData, *, time_limit_seconds: float = 60.0) -> LpSolution:
    """求解 LP，并返回含约束残差的解。"""
    objective, a_eq, b_eq, bounds = build_lp(data)
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
        equality_residual = float(np.max(np.abs(a_eq @ x - b_eq))) if a_eq.size else 0.0
        lower = np.array([item[0] for item in bounds], dtype=float)
        upper = np.array([np.inf if item[1] is None else item[1] for item in bounds], dtype=float)
        bound_violation = float(max(np.max(lower - x), np.max(x - upper)))
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


def evaluate(solution: LpSolution, *, full_horizon: bool = True) -> dict[str, Any]:
    """计算交付指标、结构恒等式 (I1)/(I2) 与全部硬约束检查。"""
    data = solution.data
    periods = data.periods
    purchase = solution.column("b")
    charge = solution.column("c")
    discharge = solution.column("q")
    spill = solution.column("s")
    storage = solution.column("E")

    checks: list[dict[str, Any]] = []

    def record(name: str, value: float, threshold: float, passed: bool, note: str = "") -> None:
        checks.append(
            {"name": name, "value": float(value), "threshold": float(threshold), "passed": bool(passed), "note": note}
        )

    total_purchase = float(np.sum(purchase))
    total_charge = float(np.sum(charge))
    total_discharge = float(np.sum(discharge))
    total_spill = float(np.sum(spill))
    cost = float(np.sum(data.price * purchase))
    net_load = data.net_load_energy

    identity_i1 = total_discharge - ETA_ROUND_TRIP * total_charge
    identity_i2 = total_purchase - net_load - total_spill - (1.0 - ETA_ROUND_TRIP) * total_charge

    worst_bound = solution.bound_violation_max
    endpoint_gap = abs(float(storage[-1]) - E_INIT)
    storage_upper_gap = max(float(np.max(storage)) - E_MAX, 0.0)
    storage_lower_gap = max(E_MIN - float(np.min(storage)), 0.0)
    charge_gap = max(float(np.max(charge)) - C_CAP, 0.0)
    discharge_gap = max(float(np.max(discharge)) - Q_CAP, 0.0)
    spill_gap = max(float(np.max(spill - data.pv_energy)), 0.0)
    purchase_gap = max(-float(np.min(purchase)), 0.0)
    complementarity = float(np.sum(charge * discharge))

    record("equality_residual_max", solution.equality_residual_max, TOL,
           solution.equality_residual_max <= TOL, "R1/R2 等式残差")
    record("bound_violation_max", worst_bound, TOL, worst_bound <= TOL, "变量界越界量")
    record("periodic_endpoint_gap", endpoint_gap, TOL, endpoint_gap <= TOL, "E_144 = E_0 = 6000")
    record("storage_upper_violation", storage_upper_gap, TOL,
           float(np.max(storage)) <= E_MAX + TOL, "E_t <= 10800")
    record("storage_lower_violation", storage_lower_gap, TOL,
           float(np.min(storage)) >= E_MIN - TOL, "E_t >= 1200")
    record("charge_cap_violation", charge_gap, TOL, float(np.max(charge)) <= C_CAP + TOL,
           "c_t <= 833.3333（并网点侧紧）")
    record("discharge_cap_violation", discharge_gap, TOL, float(np.max(discharge)) <= Q_CAP + TOL,
           "q_dis_t <= 750.0000（电池侧紧，D10 口径丙）")
    record("spill_bound_violation", spill_gap, TOL, bool(np.all(spill <= data.pv_energy + TOL)),
           "0 <= s_t <= PV_t*dt")
    record("purchase_nonneg_violation", purchase_gap, TOL, float(np.min(purchase)) >= -TOL, "b_t >= 0")
    record("complementarity_sum", complementarity, TOL, complementarity <= TOL,
           "AS07 同时充放电残差")
    record("identity_I1_residual", identity_i1, TOL, abs(identity_i1) <= TOL, "sum q = 0.81 * sum c")
    record("identity_I2_residual", identity_i2, TOL, abs(identity_i2) <= TOL, "sum b = N + sum s + 0.19 * sum c")

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
    record("max_side_power_kw", worst_power, P_MAX, worst_power <= P_MAX + 1e-3,
           "并网点侧与电池侧换算功率均 <= 5000 kW")

    if full_horizon:
        lower_bound = float(np.min(data.price) * net_load)
        no_storage_cost = float(np.sum(data.price * np.maximum(data.load_energy - data.pv_energy, 0.0)))
        record("analytic_lower_bound", lower_bound, cost, cost >= lower_bound - 1e-6, "C >= min(p) * N")
        record("analytic_upper_bound", no_storage_cost, cost, cost <= no_storage_cost + 1e-6, "无储能可行解上界")
        record("magnitude_10k", cost, 1e3, cost >= 1e4, "D9 量纲自检：费用须为 10^4 元量级")

    block_charge = [round(float(np.sum(charge[k * 24 : (k + 1) * 24])), 6) for k in range(periods // 24)]
    block_discharge = [round(float(np.sum(discharge[k * 24 : (k + 1) * 24])), 6) for k in range(periods // 24)]

    return {
        "objective_yuan": round(cost, 6),
        "total_purchase_kwh": round(total_purchase, 6),
        "total_charge_kwh": round(total_charge, 6),
        "total_discharge_kwh": round(total_discharge, 6),
        "total_spill_kwh": round(total_spill, 6),
        "net_load_kwh": round(net_load, 6),
        "max_charge_kwh": round(float(np.max(charge)), 6),
        "max_discharge_kwh": round(float(np.max(discharge)), 6),
        "storage_range_kwh": [round(float(np.min(storage)), 6), round(float(np.max(storage)), 6)],
        "storage_initial_kwh": E_INIT,
        "storage_final_kwh": round(float(storage[-1]), 6),
        "max_side_power_kw": round(worst_power, 6),
        "simultaneous_charge_discharge_periods": int(np.sum((charge > TOL) & (discharge > TOL))),
        "identity_I1_residual": float(identity_i1),
        "identity_I2_residual": float(identity_i2),
        "block_charge_kwh": block_charge,
        "block_discharge_kwh": block_discharge,
        "checks": checks,
        "checks_failed": [item["name"] for item in checks if not item["passed"]],
        "series": {
            "period_index": list(range(1, periods + 1)),
            "time_label": list(data.time_labels),
            "price_yuan_per_kwh": [float(v) for v in data.price],
            "load_energy_kwh": [float(v) for v in data.load_energy],
            "pv_energy_kwh": [float(v) for v in data.pv_energy],
            "purchase_kwh": [float(v) for v in purchase],
            "charge_kwh": [float(v) for v in charge],
            "discharge_kwh": [float(v) for v in discharge],
            "spill_kwh": [float(v) for v in spill],
            "storage_kwh": [float(v) for v in storage],
        },
    }
