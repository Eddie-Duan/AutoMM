# -*- coding: utf-8 -*-
"""prob02 鲁棒性/敏感性实验（隔离 task 入口）。

实验设计见同版本 ``robustness/plan.md``（预注册；核心结论、稳定性判据 S1–S6、扰动对象、
范围与样本量在实验批运行前冻结，事后不得修改）。

本脚本只读 ``data/``（经 ``--data``/``--data2``）与 accepted 产物（``--reference``），
向 ``--output`` 写：

- ``solver_status.json``  基线可行标记 + 基线复现闸门（供 task_worker 判定 feasible_incumbent）
- ``baseline_check.json`` accepted run002 基线逐项复现结果（相对差 ≤ 1e-6 才继续）
- ``raw_samples.jsonl``   每个情景/随机样本一行的原始指标（失败样本保留，不删除）
- ``trajectories/*.json`` 矩阵/结构情景的逐日轨迹（噪声样本不落大数组）
- ``summary.json``        分族统计、95% 置信区间、S1–S6 判定、structural findings
- ``sensitivity.json``    OAT 弹性、±20% 龙卷风数据
- ``figures/*.png``       敏感性图（robustness 图件不登记为交付图表）
- ``run_manifest.json``   追踪信息（task_id、代码 sha256、输入 md5、种子、计数、耗时）

口径与 accepted M1 一致（团队裁定 B0/D8-A）：``min Σ(p·b + α_em·p·q_em)``（元，**不乘 Δt**）、
``E_τ = E_{τ−1} + η_ch·c_τ − q_dis_τ/η_dis``、口径丙 ``c ≤ P·Δt``、``q_dis ≤ P·Δt·η_dis``、
``E ∈ [1200,10800]``、``E_0 = E_init``、``E_T`` 自由（AS04/D2-A）、全年 365 天滚动。

**边界纪律（团队裁定 B5 / D8-A）**：
- 本脚本不重复跑 M5（终端 = 6000）与 M4（逐日独立）：它们在 ``ablation`` 出数，报告只引用结论并注明来源；
- ``b`` 上限情景（R2/D3）按 B5 由 robustness 出敏感性小表；与 ``ablation`` 的 M6/M6′ 属**独立**计算，
  数值不得互相替代，若不一致须在报告中登记冲突；
- 随机实验固定种子；原始样本、逐日轨迹与汇总统计分文件保存。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

HERE = Path(__file__).resolve()
VERSION_DIR = HERE.parents[2]                       # .../assumption_v001
ACCEPTED_CODE = VERSION_DIR / "code"
RUN002_DIR = VERSION_DIR / "results" / "prob02_v001_f001_run002"
ROOT = HERE.parents[7]
for _extra in (ACCEPTED_CODE, ROOT / "scripts"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from automm.common import config_section  # noqa: E402
from prob02_io import read_attachment1, read_attachment2, write_json  # noqa: E402

DT = 1.0 / 6.0
TOL = 1e-6
PPD = 144
DAYS_FULL = 365
KINDS = ("b", "q_em", "c", "q_dis", "s", "E")
E_INIT0 = 6000.0
E_MIN0 = 1200.0
E_MAX0 = 10800.0
P_MAX0 = 5000.0
ETA0 = 0.9
ALPHA0 = 5.0
DELIVERY_START = 31                                 # 2025-02-01（1 月为预热期）
SPEC_DATES: tuple[tuple[str, int], ...] = (
    ("2025-03-20", 78),
    ("2025-06-21", 171),
    ("2025-09-23", 265),
    ("2025-12-21", 354),
)
TABLE1_POSITIONS: tuple[int, ...] = (60, 72, 84, 96, 108, 120)   # 1 基位置（AS01 左端点）
SEED = 20260910
CRITERIA = ("S1", "S2", "S3", "S4", "S5", "S6")


# --------------------------------------------------------------------------- #
# 参数与模型
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Params:
    """单次实验的全部结构参数（默认值 = accepted 基线 M1）。"""

    label: str
    family: str
    eta_ch: float = ETA0
    eta_dis: float = ETA0
    e_init: float = E_INIT0
    e_min: float = E_MIN0
    e_max: float = E_MAX0
    p_max: float = P_MAX0
    alpha_em: float = ALPHA0
    b_cap_kwh: float | None = None
    s_cap: str = "pv"                                # "pv"（AS09 accepted）| "physical"（D5-B）
    sell_price: float = 0.0                          # 元/kWh（仅结构情景 s_sell）
    solver_method: str = "highs"
    presolve: bool = True
    note: str = ""

    @property
    def c_cap(self) -> float:
        """口径丙：并网点侧与电池侧同时 ≤ P_max，取更严者。"""
        return float(min(self.p_max * DT, self.p_max * DT / self.eta_ch))

    @property
    def q_cap(self) -> float:
        return float(min(self.p_max * DT, self.p_max * DT * self.eta_dis))

    def as_dict(self) -> dict[str, Any]:
        return {
            "eta_ch": self.eta_ch,
            "eta_dis": self.eta_dis,
            "e_init": self.e_init,
            "e_min": self.e_min,
            "e_max": self.e_max,
            "p_max": self.p_max,
            "alpha_em": self.alpha_em,
            "b_cap_kwh": self.b_cap_kwh,
            "b_cap_kw": (self.b_cap_kwh / DT) if self.b_cap_kwh is not None else None,
            "c_cap_kwh": self.c_cap,
            "q_cap_kwh": self.q_cap,
            "s_cap": self.s_cap,
            "sell_price": self.sell_price,
            "solver_method": self.solver_method,
            "presolve": self.presolve,
        }


@dataclass
class Case:
    params: Params
    price: np.ndarray
    load_energy: np.ndarray
    pv_energy: np.ndarray
    days: int
    disturbance: dict[str, Any] = field(default_factory=dict)


def _col(kind: str, periods: int) -> int:
    return KINDS.index(kind) * periods


def build_lp(case: Case) -> tuple[np.ndarray, Any, np.ndarray, np.ndarray, np.ndarray]:
    """构造参数化 LP（默认参数下与 accepted ``prob02_model.build_lp`` 逐项一致）。"""
    spec = case.params
    days = case.days
    periods = days * PPD
    size = len(KINDS) * periods
    price = case.price
    load = case.load_energy
    pv = case.pv_energy
    if price.shape != (periods,) or load.shape != (periods,) or pv.shape != (periods,):
        raise ValueError("price/load/pv 长度与 days × 144 不一致")

    objective = np.zeros(size)
    objective[0:periods] = price
    objective[periods : 2 * periods] = spec.alpha_em * price
    if spec.sell_price:
        objective[4 * periods : 5 * periods] = -spec.sell_price

    lower = np.zeros(size)
    upper = np.empty(size)
    upper[0:periods] = spec.b_cap_kwh if spec.b_cap_kwh is not None else np.inf    # b >= 0（可选上限）
    upper[periods : 2 * periods] = np.inf                                         # q_em >= 0
    upper[2 * periods : 3 * periods] = spec.c_cap                                 # 0 <= c <= c_cap
    upper[3 * periods : 4 * periods] = spec.q_cap                                 # 0 <= q_dis <= q_cap
    if spec.s_cap == "physical":
        upper[4 * periods : 5 * periods] = np.maximum(pv - load, 0.0)
    else:
        upper[4 * periods : 5 * periods] = pv
    lower[5 * periods : 6 * periods] = spec.e_min
    upper[5 * periods : 6 * periods] = spec.e_max

    tau = np.arange(periods, dtype=np.int64)
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    vals: list[np.ndarray] = []

    def push(row: np.ndarray, col: np.ndarray, value: np.ndarray) -> None:
        rows.append(row)
        cols.append(col)
        vals.append(value)

    # (R1) 逐时段电量平衡：b + q_em + q_dis − c − s = L·Δt − PV·Δt
    push(tau, _col("b", periods) + tau, np.ones(periods))
    push(tau, _col("q_em", periods) + tau, np.ones(periods))
    push(tau, _col("q_dis", periods) + tau, np.ones(periods))
    push(tau, _col("c", periods) + tau, -np.ones(periods))
    push(tau, _col("s", periods) + tau, -np.ones(periods))
    # (R2) SOC 动态：E_τ − E_{τ−1} − η_ch·c_τ + q_dis_τ/η_dis = 0（τ=1 时 RHS = E_0）
    push(periods + tau, _col("E", periods) + tau, np.ones(periods))
    push(periods + tau[1:], _col("E", periods) + tau[1:] - 1, -np.ones(periods - 1))
    push(periods + tau, _col("c", periods) + tau, -spec.eta_ch * np.ones(periods))
    push(periods + tau, _col("q_dis", periods) + tau, (1.0 / spec.eta_dis) * np.ones(periods))

    a_eq = coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(2 * periods, size),
    ).tocsr()
    b_eq = np.concatenate([load - pv, np.concatenate([[spec.e_init], np.zeros(periods - 1)])])
    return objective, a_eq, b_eq, lower, upper


@dataclass
class Solved:
    params: Params
    status: int
    message: str
    iterations: int | None
    objective: float
    x: np.ndarray
    equality_residual_max: float
    bound_violation_max: float
    wall_seconds: float


def solve_case(case: Case, *, time_limit: float) -> Solved:
    objective, a_eq, b_eq, lower, upper = build_lp(case)
    bounds = np.column_stack((lower, upper))
    started = time.perf_counter()
    result = linprog(
        objective,
        A_eq=a_eq,
        b_eq=b_eq,
        bounds=bounds,
        method=case.params.solver_method,
        options={"time_limit": float(time_limit), "presolve": bool(case.params.presolve)},
    )
    wall = time.perf_counter() - started
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
    return Solved(
        params=case.params,
        status=int(result.status),
        message=str(result.message),
        iterations=int(result.nit) if result.nit is not None else None,
        objective=float(result.fun) if result.fun is not None else float("nan"),
        x=x,
        equality_residual_max=equality_residual,
        bound_violation_max=bound_violation,
        wall_seconds=wall,
    )


# --------------------------------------------------------------------------- #
# 指标与硬检查
# --------------------------------------------------------------------------- #


def _num(value: Any, digits: int = 6) -> float | None:
    try:
        item = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(item):
        return None
    return round(item, digits)


def _series(case: Case, x: np.ndarray) -> np.ndarray:
    """长度 T+1 的储电量序列 [E_0, E_1, …, E_T]。"""
    periods = case.days * PPD
    return np.concatenate([[case.params.e_init], x[_col("E", periods) : _col("E", periods) + periods]])


def evaluate(case: Case, solved: Solved) -> dict[str, Any]:
    """计算交付/结构指标、恒等式 (I1)/(I2)（全期与交付期切片）与硬约束检查。"""
    spec = case.params
    days = case.days
    periods = days * PPD
    x = solved.x
    record: dict[str, Any] = {
        "label": spec.label,
        "family": spec.family,
        "params": spec.as_dict(),
        "disturbance": case.disturbance,
        "note": spec.note,
        "solver_status": solved.status,
        "solver_message": solved.message,
        "iterations": solved.iterations,
        "wall_seconds": round(solved.wall_seconds, 6),
        "feasible": bool(solved.status == 0 and np.all(np.isfinite(x))),
        "objective_yuan": None,
        "checks_failed": [],
    }
    if not record["feasible"]:
        return record

    purchase = x[0:periods]
    q_em = x[periods : 2 * periods]
    charge = x[2 * periods : 3 * periods]
    discharge = x[3 * periods : 4 * periods]
    spill = x[4 * periods : 5 * periods]
    state = _series(case, x)
    price = case.price
    load = case.load_energy
    pv = case.pv_energy

    total_purchase = float(np.sum(purchase))
    total_q_em = float(np.sum(q_em))
    total_charge = float(np.sum(charge))
    total_discharge = float(np.sum(discharge))
    total_spill = float(np.sum(spill))
    cost_plan = float(np.sum(price * purchase))
    cost_em = float(np.sum(spec.alpha_em * price * q_em))
    cost = cost_plan + cost_em
    net_load = float(np.sum(load - pv))
    storage_final = float(state[periods])

    has_delivery = days > DELIVERY_START
    delivery = np.zeros(periods, dtype=bool)
    if has_delivery:
        delivery[DELIVERY_START * PPD :] = True
    net_load_delivery = float(np.sum(load[delivery] - pv[delivery]))
    state_delivery_start = float(state[DELIVERY_START * PPD]) if has_delivery else float(state[0])
    cost_delivery = float(
        np.sum(price[delivery] * purchase[delivery]) + np.sum(spec.alpha_em * price[delivery] * q_em[delivery])
    )
    january = slice(0, DELIVERY_START * PPD)
    january_cost = float(
        np.sum(price[january] * purchase[january]) + np.sum(spec.alpha_em * price[january] * q_em[january])
    )
    round_trip = spec.eta_ch * spec.eta_dis
    identity_i1 = total_discharge - (round_trip * total_charge - spec.eta_dis * (storage_final - spec.e_init))
    identity_i2 = total_purchase - (
        net_load
        + total_spill
        + (1.0 - round_trip) * total_charge
        + spec.eta_dis * (storage_final - spec.e_init)
        - total_q_em
    )
    identity_i1_delivery = float(np.sum(discharge[delivery])) - (
        round_trip * float(np.sum(charge[delivery])) - spec.eta_dis * (storage_final - state_delivery_start)
    )
    identity_i2_delivery = float(np.sum(purchase[delivery])) - (
        net_load_delivery
        + float(np.sum(spill[delivery]))
        + (1.0 - round_trip) * float(np.sum(charge[delivery]))
        + spec.eta_dis * (storage_final - state_delivery_start)
        - float(np.sum(q_em[delivery]))
    )

    day_start = state[:periods:PPD]
    day_end = state[PPD::PPD]
    continuity = float(np.max(np.abs(day_start[1:] - day_end[:-1]))) if days > 1 else 0.0

    charge_ac = charge / DT
    charge_dc = spec.eta_ch * charge / DT
    discharge_ac = discharge / DT
    discharge_dc = discharge / (spec.eta_dis * DT)
    worst_power = float(max(np.max(charge_ac), np.max(charge_dc), np.max(discharge_ac), np.max(discharge_dc)))
    s_upper = np.maximum(pv - load, 0.0) if spec.s_cap == "physical" else pv

    no_storage_cost = float(np.sum(price * np.maximum(load - pv, 0.0)))
    lower_bound = float(np.min(price) * (net_load + spec.eta_dis * (spec.e_min - spec.e_init)))
    physical_surplus = float(np.sum(np.maximum(pv - load, 0.0)))

    checks: list[dict[str, Any]] = []

    def check(name: str, value: float, threshold: float, passed: bool, note: str = "") -> None:
        checks.append(
            {"name": name, "value": _num(value), "threshold": _num(threshold), "passed": bool(passed), "note": note}
        )

    check("equality_residual_max", solved.equality_residual_max, TOL, solved.equality_residual_max <= TOL,
          "(R1)/(R2) 等式残差")
    check("bound_violation_max", solved.bound_violation_max, TOL, solved.bound_violation_max <= TOL, "变量界越界量")
    check("storage_upper_violation", max(float(np.max(state[1:])) - spec.e_max, 0.0), TOL,
          float(np.max(state[1:])) <= spec.e_max + TOL, "E_τ <= e_max")
    check("storage_lower_violation", max(spec.e_min - float(np.min(state[1:])), 0.0), TOL,
          float(np.min(state[1:])) >= spec.e_min - TOL, "E_τ >= e_min")
    check("charge_cap_violation", max(float(np.max(charge)) - spec.c_cap, 0.0), TOL,
          float(np.max(charge)) <= spec.c_cap + TOL, "c_τ <= c_cap（口径丙）")
    check("discharge_cap_violation", max(float(np.max(discharge)) - spec.q_cap, 0.0), TOL,
          float(np.max(discharge)) <= spec.q_cap + TOL, "q_dis_τ <= q_cap（口径丙）")
    check("spill_bound_violation", max(float(np.max(spill - s_upper)), 0.0), TOL,
          bool(np.all(spill <= s_upper + TOL)), "0 <= s_τ <= s 上界")
    check("purchase_nonneg_violation", max(-float(np.min(purchase)), 0.0), TOL,
          float(np.min(purchase)) >= -TOL, "b_τ >= 0")
    check("q_em_nonneg_violation", max(-float(np.min(q_em)), 0.0), TOL, float(np.min(q_em)) >= -TOL, "q_em,τ >= 0")
    if spec.b_cap_kwh is not None:
        check("purchase_cap_violation", max(float(np.max(purchase)) - spec.b_cap_kwh, 0.0), TOL,
              float(np.max(purchase)) <= spec.b_cap_kwh + TOL, "b_τ <= b_cap")
    check("cross_day_continuity", continuity, TOL, continuity <= TOL, "|E_{d,0} − E_{d−1,144}|")
    check("complementarity_sum", float(np.sum(charge * discharge)), TOL,
          float(np.sum(charge * discharge)) <= TOL, "同时充放电残差（引理 L1）")
    check("max_side_power_kw", worst_power, spec.p_max, worst_power <= spec.p_max + 1e-3,
          "并网点侧与电池侧换算功率均 <= P_max")
    check("identity_I1_residual", identity_i1, TOL, abs(identity_i1) <= TOL, "Σq_dis = η²Σc − η(E_T − E_0)")
    check("identity_I2_residual", identity_i2, TOL, abs(identity_i2) <= TOL,
          "Σb = N + Σs + (1−η²)Σc + η(E_T − E_0) − Σq_em")
    if has_delivery:
        check("identity_I1_delivery_residual", identity_i1_delivery, TOL,
              abs(identity_i1_delivery) <= TOL, "交付期切片")
        check("identity_I2_delivery_residual", identity_i2_delivery, TOL,
              abs(identity_i2_delivery) <= TOL, "交付期切片")
    check("analytic_lower_bound", cost, lower_bound, cost >= lower_bound - 1e-6, "C >= min(p)·[N + η(E_min − E_0)]")
    check("analytic_upper_bound", no_storage_cost, cost, cost <= no_storage_cost + 1e-6, "无储能可行解购电费上界")
    check("q_em_zero_total", total_q_em, TOL, total_q_em <= TOL, "完全信息 + 无上限（且 α_em>1）⇒ Σq_em = 0")

    purchase_d = purchase.reshape(days, PPD)
    spill_d = spill.reshape(days, PPD)
    q_em_d = q_em.reshape(days, PPD)
    price_d = price.reshape(days, PPD)
    cost_total_d = np.sum(price_d * purchase_d, axis=1) + np.sum(spec.alpha_em * price_d * q_em_d, axis=1)
    day_purchase = np.sum(purchase_d, axis=1)

    spec_dates: dict[str, Any] = {}
    for date_text, day_index in SPEC_DATES:
        if day_index >= days:
            continue
        spec_dates[date_text] = {
            "day_index": int(day_index),
            "purchase_kwh": round(float(day_purchase[day_index]), 9),
            "cost_yuan": round(float(cost_total_d[day_index]), 9),
            "slots_kwh": [round(float(purchase_d[day_index, position - 1]), 9) for position in TABLE1_POSITIONS],
            "storage_0_00_kwh": round(float(day_start[day_index]), 9),
            "storage_24_00_kwh": round(float(day_end[day_index]), 9),
        }

    record.update(
        {
            "objective_yuan": _num(cost),
            "objective_plan_yuan": _num(cost_plan),
            "objective_emergency_yuan": _num(cost_em),
            "delivery_cost_yuan": _num(cost_delivery),
            "january_cost_yuan": _num(january_cost),
            "no_storage_cost_yuan": _num(no_storage_cost),
            "total_purchase_kwh": _num(total_purchase),
            "total_q_em_kwh": _num(total_q_em),
            "total_charge_kwh": _num(total_charge),
            "total_discharge_kwh": _num(total_discharge),
            "total_spill_kwh": _num(total_spill),
            "physical_surplus_kwh": _num(physical_surplus),
            "net_load_kwh": _num(net_load),
            "net_load_delivery_kwh": _num(net_load_delivery),
            "storage_initial_kwh": _num(spec.e_init),
            "storage_final_kwh": _num(storage_final),
            "storage_min_kwh": _num(float(np.min(state[1:]))),
            "storage_max_kwh": _num(float(np.max(state[1:]))),
            "max_charge_kwh": _num(float(np.max(charge))),
            "max_discharge_kwh": _num(float(np.max(discharge))),
            "max_purchase_kwh": _num(float(np.max(purchase))),
            "max_purchase_power_kw": _num(float(np.max(purchase)) / DT),
            "max_side_power_kw": _num(worst_power),
            "sell_revenue_yuan": _num(-float(np.sum(spec.sell_price * spill))) if spec.sell_price else 0.0,
            "days_with_emergency": int(np.sum(np.any(q_em_d > TOL, axis=1))),
            "simultaneous_charge_discharge_periods": int(np.sum((charge > TOL) & (discharge > TOL))),
            "day_start_unique_levels": int(len(np.unique(np.round(day_start, 6)))),
            "equality_residual_max": _num(solved.equality_residual_max, 12),
            "bound_violation_max": _num(solved.bound_violation_max, 12),
            "identity_I1_residual": _num(identity_i1, 9),
            "identity_I2_residual": _num(identity_i2, 9),
            "identity_I1_delivery_residual": _num(identity_i1_delivery, 9),
            "identity_I2_delivery_residual": _num(identity_i2_delivery, 9),
            "continuity_residual_max": _num(continuity, 9),
            "spec_dates": spec_dates,
            "checks": checks,
            "checks_failed": [item["name"] for item in checks if not item["passed"]],
            "_daily": {
                "purchase_kwh": [round(float(v), 6) for v in day_purchase],
                "q_em_kwh": [round(float(v), 6) for v in np.sum(q_em_d, axis=1)],
                "cost_total_yuan": [round(float(v), 6) for v in cost_total_d],
                "storage_start_kwh": [round(float(v), 6) for v in day_start],
                "storage_end_kwh": [round(float(v), 6) for v in day_end],
                "spill_kwh": [round(float(v), 6) for v in np.sum(spill_d, axis=1)],
            },
        }
    )
    return record


# --------------------------------------------------------------------------- #
# 实验矩阵（预注册；见 plan.md §3）
# --------------------------------------------------------------------------- #


def build_matrix() -> list[Params]:
    matrix: list[Params] = [Params(label="baseline", family="baseline", note="accepted M1 基线复现闸门")]
    # eta（两侧同步）：±5% / ±10% / ±20%（η=1.0 为 +11.1% 的物理上界档）
    for value in (0.72, 0.81, 0.855, 0.945, 0.99, 1.0):
        matrix.append(Params(label=f"eta_both_{value:g}", family="eta", eta_ch=value, eta_dis=value,
                             note=f"eta_ch=eta_dis={value:g}"))
    # eta 单侧（±10%）
    for value in (0.81, 0.99):
        matrix.append(Params(label=f"eta_ch_{value:g}", family="eta_asym", eta_ch=value, note=f"仅 η_ch={value:g}"))
        matrix.append(Params(label=f"eta_dis_{value:g}", family="eta_asym", eta_dis=value, note=f"仅 η_dis={value:g}"))
    # E_init：±5% / ±10% / ±20%
    for value in (4800.0, 5400.0, 5700.0, 6300.0, 6600.0, 7200.0):
        matrix.append(Params(label=f"e_init_{value:g}", family="init", e_init=value, note=f"E_init={value:g} kWh"))
    # alpha_em：±5% / ±10% / ±20%
    for value in (4.0, 4.5, 4.75, 5.25, 5.5, 6.0):
        matrix.append(Params(label=f"alpha_em_{value:g}", family="alpha", alpha_em=value, note=f"α_em={value:g}"))
    # P_max（口径丙同步换算）：±5% / ±10% / ±20%
    for value in (4000.0, 4500.0, 4750.0, 5250.0, 5500.0, 6000.0):
        matrix.append(Params(label=f"p_max_{value:g}", family="pmax", p_max=value, note=f"P_max={value:g} kW"))
    # E 运行窗口：±20%
    matrix.append(Params(label="e_min_960", family="ewin", e_min=960.0, note="E_min −20%"))
    matrix.append(Params(label="e_min_1440", family="ewin", e_min=1440.0, note="E_min +20%"))
    matrix.append(Params(label="e_max_8640", family="ewin", e_max=8640.0, note="E_max −20%"))
    # 求解器设置
    for method in ("highs-ds", "highs-ipm"):
        matrix.append(Params(label=f"solver_{method}", family="solver", solver_method=method,
                             note=f"同一模型改用 {method}"))
    matrix.append(Params(label="solver_highs_nopresolve", family="solver", presolve=False, note="关闭 presolve"))
    # 结构情景：s 的界（D5-A accepted vs D5-B 物理盈余）
    matrix.append(Params(label="s_bound_physical", family="s_bound", s_cap="physical",
                         note="s 收紧为物理盈余 max(0, PV−L)（D5-B）；目标系数仍为 0"))
    # 结构情景：售电收益（AS09 松界的边界压力，非交付口径）
    matrix.append(Params(label="s_sell_0.50_pvbound", family="s_sell", sell_price=0.50,
                         note="s 取 AS09 松界 + 0.50 元/kWh 售电：检验非物理套利路径"))
    matrix.append(Params(label="s_sell_0.50_physical", family="s_sell", sell_price=0.50, s_cap="physical",
                         note="先收紧物理界再给售电价：对照条"))
    # 结构情景：α_em < 1（机制边界演示）
    matrix.append(Params(label="alpha_em_0.50", family="alpha_lt1", alpha_em=0.50,
                         note="α_em=0.5<1：机制边界演示，非题面参数扰动"))
    # 购电上限情景族（R2 原网格 + M6′）
    for kw in (10326.0, 8459.0, 6000.0, 5000.0, 4375.0, 4218.75, 4000.0, 3750.0, 3000.0, 2000.0):
        matrix.append(Params(label=f"b_cap_{kw:g}kW", family="b_cap", b_cap_kwh=kw * DT,
                             note=f"b/Δt <= {kw:g} kW"))
    return matrix


NOISE_FAMILIES: tuple[tuple[str, str, float, bool], ...] = (
    # (family, mode, sigma, price_noise)
    ("noise_white_5", "independent", 0.05, False),
    ("noise_white_10", "independent", 0.10, False),
    ("noise_day_5", "per_day", 0.05, False),
    ("noise_joint_day_5", "per_day", 0.05, True),
)


def build_noise_cases(price: np.ndarray, load_kw: np.ndarray, pv_kw: np.ndarray,
                      seed: int, samples: int) -> list[Case]:
    """构造噪声样本；``price`` 为单日 144 点电价，逐日重复后叠加因子。"""
    days, ppd = load_kw.shape
    base_price_full = np.tile(price, days)
    cases: list[Case] = []
    for family_index, (family, mode, sigma, price_noise) in enumerate(NOISE_FAMILIES):
        for sample in range(samples):
            rng = np.random.default_rng(seed + family_index * 100003 + sample)
            if mode == "independent":
                f_load = np.maximum(0.2, 1.0 + sigma * rng.standard_normal((days, ppd)))
                f_pv = np.maximum(0.0, 1.0 + sigma * rng.standard_normal((days, ppd)))
                if price_noise:
                    f_price = np.maximum(0.05, 1.0 + sigma * rng.standard_normal((days, ppd)))
                else:
                    f_price = np.ones((days, ppd))
            else:
                day_load = np.maximum(0.2, 1.0 + sigma * rng.standard_normal(days))
                day_pv = np.maximum(0.0, 1.0 + sigma * rng.standard_normal(days))
                f_load = np.repeat(day_load[:, None], ppd, axis=1)
                f_pv = np.repeat(day_pv[:, None], ppd, axis=1)
                if price_noise:
                    day_price = np.maximum(0.05, 1.0 + sigma * rng.standard_normal(days))
                    f_price = np.repeat(day_price[:, None], ppd, axis=1)
                else:
                    f_price = np.ones((days, ppd))
            new_load = load_kw * f_load
            new_pv = pv_kw * f_pv
            new_price_full = (price[None, :] * f_price).reshape(-1)
            disturbance = {
                "family": family,
                "mode": mode,
                "sigma": sigma,
                "price_noise": bool(price_noise),
                "sample": sample,
                "load_energy_ratio": round(float(np.sum(new_load) / np.sum(load_kw)), 9),
                "pv_energy_ratio": round(float(np.sum(new_pv) / np.sum(pv_kw)), 9),
                "price_sum_ratio": round(float(np.sum(new_price_full) / np.sum(base_price_full)), 9),
            }
            cases.append(
                Case(
                    params=Params(label=f"{family}_s{sample:03d}", family=family,
                                  note=f"{mode} σ={sigma:.2f} price_noise={price_noise} sample={sample}"),
                    price=new_price_full,
                    load_energy=new_load.reshape(-1) * DT,
                    pv_energy=new_pv.reshape(-1) * DT,
                    days=days,
                    disturbance=disturbance,
                )
            )
    return cases


# --------------------------------------------------------------------------- #
# 统计与判据
# --------------------------------------------------------------------------- #


def bootstrap_ci(values: np.ndarray, seed: int, resamples: int = 1000) -> list[float]:
    if values.size == 0:
        return [float("nan"), float("nan")]
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, values.size, size=(resamples, values.size))
    means = values[draws].mean(axis=1)
    return [round(float(np.percentile(means, 2.5)), 6), round(float(np.percentile(means, 97.5)), 6)]


def summarize(values: list[Any]) -> dict[str, Any]:
    array = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    if array.size == 0:
        return {"count": 0}
    std = float(np.std(array, ddof=1)) if array.size > 1 else 0.0
    return {
        "count": int(array.size),
        "mean": round(float(np.mean(array)), 6),
        "std": round(std, 6),
        "min": round(float(np.min(array)), 6),
        "p2_5": round(float(np.percentile(array, 2.5)), 6),
        "p25": round(float(np.percentile(array, 25)), 6),
        "median": round(float(np.median(array)), 6),
        "p75": round(float(np.percentile(array, 75)), 6),
        "p97_5": round(float(np.percentile(array, 97.5)), 6),
        "max": round(float(np.max(array)), 6),
        "ci95_mean": bootstrap_ci(array, SEED),
    }


def _rel_diff(got: float, want: float) -> float:
    scale = max(abs(want), 1.0)
    return abs(got - want) / scale


def _oat_table(groups: dict[str, list[dict[str, Any]]], family: str, key: str, grid: list[float],
               x0: float, base_cost: float) -> dict[str, Any]:
    items = {round(item["params"][key], 9): item for item in groups.get(family, [])}
    result: dict[str, Any] = {"grid": grid, "cost": {}, "relative_change": {}, "elasticity": {}}
    for value in grid:
        item = items.get(round(float(value), 9))
        if not item or not item.get("feasible") or item["objective_yuan"] is None:
            continue
        delta = (item["objective_yuan"] - base_cost) / base_cost
        result["cost"][str(value)] = item["objective_yuan"]
        result["relative_change"][str(value)] = round(delta, 6)
        if abs(value - x0) > 1e-12:
            result["elasticity"][str(value)] = round(delta / ((value - x0) / x0), 6)
    return result


def evaluate_criteria(records: list[dict[str, Any]], baseline: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(record["family"], []).append(record)
    base_cost = float(baseline["objective_yuan"])
    core_families = {"baseline", "eta", "eta_asym", "init", "alpha", "pmax", "ewin", "s_bound", "solver"}
    noise_families = sorted(name for name in groups if name.startswith("noise_"))

    summary: dict[str, Any] = {
        "baseline_objective_yuan": base_cost,
        "baseline_delivery_cost_yuan": baseline["delivery_cost_yuan"],
        "baseline_no_storage_cost_yuan": baseline["no_storage_cost_yuan"],
        "families": {},
    }
    base_delivery_cost = float(baseline["delivery_cost_yuan"] or 0.0)
    for family, items in sorted(groups.items()):
        feasible = [item for item in items if item.get("feasible")]
        delivery_deltas = (
            [
                (item["delivery_cost_yuan"] - base_delivery_cost) / base_delivery_cost
                for item in feasible
                if item.get("delivery_cost_yuan") is not None
            ]
            if base_delivery_cost > 0
            else []
        )
        summary["families"][family] = {
            "count": len(items),
            "feasible_count": len(feasible),
            "feasible_rate": round(len(feasible) / len(items), 6),
            "objective": summarize([item["objective_yuan"] for item in feasible]),
            "relative_delta": summarize([(item["objective_yuan"] - base_cost) / base_cost for item in feasible]),
            "delivery_relative_delta": summarize(delivery_deltas),
            "checks_failed_union": sorted({name for item in items for name in item.get("checks_failed", [])}),
            "labels": [item["label"] for item in items],
        }

    # OAT 网格（baseline 作为 x0 网格点补入对应族）
    oat_groups = {name: list(items) for name, items in groups.items()}
    for family in ("eta", "init", "alpha", "pmax", "ewin"):
        oat_groups.setdefault(family, []).append(baseline)
    grids = {
        "eta": ("eta", "eta_ch", [0.72, 0.81, 0.855, 0.9, 0.945, 0.99, 1.0], ETA0),
        "e_init": ("init", "e_init", [4800.0, 5400.0, 5700.0, 6000.0, 6300.0, 6600.0, 7200.0], E_INIT0),
        "alpha_em": ("alpha", "alpha_em", [4.0, 4.5, 4.75, 5.0, 5.25, 5.5, 6.0], ALPHA0),
        "p_max": ("pmax", "p_max", [4000.0, 4500.0, 4750.0, 5000.0, 5250.0, 5500.0, 6000.0], P_MAX0),
        "e_min": ("ewin", "e_min", [960.0, 1200.0, 1440.0], E_MIN0),
        "e_max": ("ewin", "e_max", [8640.0, 10800.0], E_MAX0),
    }
    sensitivity: dict[str, Any] = {"baseline_objective_yuan": base_cost, "oat": {}, "tornado_20pct": {}}
    for name, (family, key, grid, x0) in grids.items():
        sensitivity["oat"][name] = _oat_table(oat_groups, family, key, grid, x0, base_cost)

    def rel_change(family: str, key: str, value: float) -> float | None:
        for item in oat_groups.get(family, []):
            if abs(item["params"][key] - value) <= 1e-9 and item.get("feasible") and item["objective_yuan"] is not None:
                return (item["objective_yuan"] - base_cost) / base_cost
        return None

    for name, (family, key, grid, x0) in grids.items():
        low = min(grid, key=lambda v: abs(v - x0 * 0.8))
        high = min(grid, key=lambda v: abs(v - x0 * 1.2))
        sensitivity["tornado_20pct"][name] = {
            "low_value": low,
            "high_value": high,
            "low_relative_change": _num(rel_change(family, key, low)),
            "high_relative_change": _num(rel_change(family, key, high)),
        }

    # ---------- S1 可行率 ----------
    def hard_ok(item: dict[str, Any]) -> bool:
        return bool(item.get("feasible")) and not item.get("checks_failed")

    core_records = [item for item in records if item["family"] in core_families or item["family"] in noise_families]
    param_records = [item for item in core_records if item["family"] not in noise_families]
    core_rate = sum(1 for item in core_records if hard_ok(item)) / max(len(core_records), 1)
    param_rate = sum(1 for item in param_records if hard_ok(item)) / max(len(param_records), 1)
    s1_pass = core_rate >= 0.95 and param_rate >= 0.99

    # ---------- S2 幅度与符号方向 ----------
    amp_detail: dict[str, Any] = {}
    amp = 0.0
    eta_amp = 0.0
    for name, (family, key, grid, x0) in grids.items():
        for value in (x0 * 0.8, x0 * 1.2):
            change = rel_change(family, key, value)
            if change is None:
                continue
            amp_detail[f"{name}@{value:.6g}"] = round(change, 6)
            amp = max(amp, abs(change))
            if name == "eta":
                eta_amp = max(eta_amp, abs(change))
    eta_low = rel_change("eta", "eta_ch", 0.72)
    eta_high = rel_change("eta", "eta_ch", 1.0)
    pmax_low = rel_change("pmax", "p_max", 4000.0)
    pmax_high = rel_change("pmax", "p_max", 6000.0)
    e_init_elasticities = list(sensitivity["oat"]["e_init"].get("elasticity", {}).values())
    directions = {
        "dC_deta_nonpositive": bool(eta_low is not None and eta_high is not None and eta_high <= eta_low + 1e-12),
        "dC_dpmax_nonpositive": bool(pmax_low is not None and pmax_high is not None and pmax_high <= pmax_low + 1e-12),
        "e_init_elasticity_within_1p5": (
            bool(e_init_elasticities) and all(abs(item) <= 1.5 for item in e_init_elasticities)
        ),
    }
    s2_pass = amp <= 0.25 and eta_amp <= 0.35 and all(directions.values())

    # ---------- S3 噪声区间 ----------
    noise_all = [item for item in records if item["family"] in noise_families and item.get("feasible")]
    noise_cost = np.asarray([item["objective_yuan"] for item in noise_all], dtype=float)
    if noise_cost.size:
        half_width = float((np.percentile(noise_cost, 97.5) - np.percentile(noise_cost, 2.5)) / 2.0 / base_cost)
        mean_shift = float(abs(np.mean(noise_cost) - base_cost) / base_cost)
    else:
        half_width, mean_shift = float("nan"), float("nan")
    noise_detail: dict[str, Any] = {}
    for family in noise_families:
        values = [item["objective_yuan"] for item in groups.get(family, []) if item.get("feasible")]
        entry = summarize(values)
        if values:
            array = np.asarray(values, dtype=float)
            entry["p2_5_half_width_ratio"] = round(
                float((np.percentile(array, 97.5) - np.percentile(array, 2.5)) / 2.0 / base_cost), 6
            )
            entry["mean_shift_ratio"] = round(float(abs(np.mean(array) - base_cost) / base_cost), 6)
        noise_detail[family] = entry
    s3_pass = bool(
        np.isfinite(half_width) and half_width <= 0.20 and np.isfinite(mean_shift) and mean_shift <= 0.10
    )

    # ---------- S4 套利方向 ----------
    direction_records = [
        item for item in core_records
        if item.get("feasible") and item.get("no_storage_cost_yuan") is not None and item["objective_yuan"] is not None
    ]
    s4_failures = [
        item["label"] for item in direction_records
        if not (item["objective_yuan"] < item["no_storage_cost_yuan"] - 1e-6)
    ]

    # ---------- S5 交付表稳定性（参数 OAT ±10%） ----------
    def is_within_10pct(item: dict[str, Any]) -> bool:
        spec = item["params"]
        pairs = (
            ("eta_ch", spec["eta_ch"], ETA0), ("eta_dis", spec["eta_dis"], ETA0),
            ("e_init", spec["e_init"], E_INIT0), ("p_max", spec["p_max"], P_MAX0),
            ("alpha_em", spec["alpha_em"], ALPHA0),
        )
        changed = [abs(value - x0) / x0 for _, value, x0 in pairs if abs(value - x0) > 1e-12]
        if not changed:
            return False
        return bool(max(changed) <= 0.100001 and spec["e_min"] == E_MIN0 and spec["e_max"] == E_MAX0)

    base_spec = baseline["spec_dates"]
    s5_checked, s5_failures = 0, []
    s5_worst = {"purchase": 0.0, "cost": 0.0, "slot_ratio": 0.0}
    for item in records:
        if item["family"] not in {"eta", "eta_asym", "init", "alpha", "pmax"} or not item.get("feasible"):
            continue
        if not is_within_10pct(item):
            continue
        s5_checked += 1
        for date_text, base_entry in base_spec.items():
            entry = item["spec_dates"].get(date_text)
            if not entry:
                continue
            purchase_delta = _rel_diff(entry["purchase_kwh"], base_entry["purchase_kwh"])
            cost_delta = _rel_diff(entry["cost_yuan"], base_entry["cost_yuan"])
            s5_worst["purchase"] = max(s5_worst["purchase"], purchase_delta)
            s5_worst["cost"] = max(s5_worst["cost"], cost_delta)
            if base_entry["purchase_kwh"] > 0:
                for ours, want in zip(entry["slots_kwh"], base_entry["slots_kwh"]):
                    s5_worst["slot_ratio"] = max(s5_worst["slot_ratio"], abs(ours - want) / base_entry["purchase_kwh"])
            if purchase_delta > 0.10 or cost_delta > 0.10 or s5_worst["slot_ratio"] > 0.15:
                s5_failures.append(f"{item['label']}@{date_text}")

    # ---------- S6 求解器一致性 ----------
    solver_records = [baseline] + [item for item in groups.get("solver", []) if item.get("feasible")]
    solver_objectives = {item["label"]: item["objective_yuan"] for item in solver_records}
    solver_pairs: dict[str, Any] = {}
    s6_pass = True
    labels = list(solver_objectives)
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            a, b = labels[i], labels[j]
            if solver_objectives[a] is None or solver_objectives[b] is None:
                s6_pass = False
                continue
            delta = _rel_diff(solver_objectives[a], solver_objectives[b])
            solver_pairs[f"{a}|{b}"] = round(delta, 12)
            s6_pass = s6_pass and delta <= 1e-6

    criteria = {
        "S1": {
            "name": "可行率（核心族；参数族与噪声族分开）",
            "threshold": "参数族 >= 0.99 且整体 >= 0.95",
            "value": {"core_rate": round(core_rate, 6), "param_rate": round(param_rate, 6),
                      "core_count": len(core_records), "param_count": len(param_records)},
            "passed": bool(s1_pass),
            "failures": [item["label"] for item in core_records if not hard_ok(item)][:30],
        },
        "S2": {
            "name": "OAT ±20% 最大相对偏移与符号方向",
            "threshold": "max|ΔC|/C* <= 0.25（eta 档 <= 0.35）且方向判据全通过",
            "value": {"max_abs_relative_change": round(amp, 6), "eta_extreme": round(eta_amp, 6),
                      "detail": amp_detail, "directions": directions},
            "passed": bool(s2_pass),
        },
        "S3": {
            "name": "噪声传播 95% 区间与均值偏移",
            "threshold": "2.5–97.5 分位半宽/C* <= 0.20 且 |均值偏移| <= 0.10",
            "value": {"half_width_ratio": _num(half_width), "mean_shift_ratio": _num(mean_shift),
                      "samples": int(noise_cost.size), "families": noise_detail},
            "passed": bool(s3_pass),
        },
        "S4": {
            "name": "套利方向（C_opt < 同扰动数据下的无储能购电费）",
            "threshold": "核心族 100% 成立",
            "value": {"checked": len(direction_records), "failures": s4_failures[:30]},
            "passed": bool(len(direction_records) > 0 and not s4_failures),
        },
        "S5": {
            "name": "交付表稳定性（参数 OAT ±10% 的 4 个指定日期与表 1 六时段）",
            "threshold": "全天购电量/购电费相对偏差 <= 0.10；表 1 每 slot 绝对偏差 <= 0.15×当日全天购电量",
            "value": {"cases_checked": s5_checked, "worst": {k: round(v, 6) for k, v in s5_worst.items()},
                      "failures": s5_failures[:30]},
            "passed": bool(s5_checked > 0 and not s5_failures),
        },
        "S6": {
            "name": "求解器设置一致性（highs / highs-ds / highs-ipm / 关闭 presolve）",
            "threshold": "目标值两两相对差 <= 1e-6",
            "value": {"objectives": solver_objectives, "pairwise_relative_diff": solver_pairs},
            "passed": bool(s6_pass),
        },
    }
    failed = [name for name in CRITERIA if not criteria[name]["passed"]]
    summary["criteria"] = criteria
    summary["criteria_failed"] = failed
    summary["stability_grade"] = "稳定" if not failed else (
        "条件稳定" if len(failed) <= 1 else "脆弱（需缩小适用范围）"
    )

    # ---------- 结构情景发现 ----------
    b_cap_rows = []
    for item in sorted(groups.get("b_cap", []), key=lambda entry: -(entry["params"]["b_cap_kw"] or 0.0)):
        b_cap_rows.append({
            "b_cap_kw": item["params"]["b_cap_kw"],
            "feasible": bool(item.get("feasible")),
            "total_q_em_kwh": item.get("total_q_em_kwh"),
            "emergency_cost_yuan": item.get("objective_emergency_yuan"),
            "objective_yuan": item.get("objective_yuan"),
            "delivery_cost_yuan": item.get("delivery_cost_yuan"),
            "days_with_emergency": item.get("days_with_emergency"),
            "max_purchase_power_kw": item.get("max_purchase_power_kw"),
            "checks_failed": item.get("checks_failed", []),
        })
    # b_cap 降序排列：上限从大到小 ⇒ Σq_em 单调不减、费用单调不降
    zero_caps = [row["b_cap_kw"] for row in b_cap_rows if row["feasible"] and (row["total_q_em_kwh"] or 0.0) <= TOL]
    active_caps = [row["b_cap_kw"] for row in b_cap_rows if row["feasible"] and (row["total_q_em_kwh"] or 0.0) > TOL]
    cap_costs = [row["objective_yuan"] for row in b_cap_rows if row["feasible"] and row["objective_yuan"] is not None]
    cap_qem = [row["total_q_em_kwh"] for row in b_cap_rows if row["feasible"] and row["total_q_em_kwh"] is not None]

    s_bound_items = [item for item in groups.get("s_bound", []) if item.get("feasible")]
    s_bound_entry = s_bound_items[0] if s_bound_items else {}
    s_bound_delta = (
        (s_bound_entry["objective_yuan"] - base_cost) / base_cost
        if s_bound_entry.get("objective_yuan") is not None else None
    )

    structural = {
        "b_cap": {
            "rows": b_cap_rows,
            "threshold_bracket": {
                "no_activation_below_or_equal_kw": max(zero_caps) if zero_caps else None,
                "activation_at_or_below_kw": min(active_caps) if active_caps else None,
                "expected_from_R5_kw": [4218.75, 4375.0],
            },
            "monotone_cost_non_decreasing": bool(
                all(cap_costs[i] <= cap_costs[i + 1] + 1e-6 for i in range(len(cap_costs) - 1))
            ),
            "monotone_q_em_non_increasing": bool(
                all(cap_qem[i] >= cap_qem[i + 1] - 1e-6 for i in range(len(cap_qem) - 1))
            ),
            "note": "b 上限下降 ⇒ Σq_em 单调不减、总费用单调不降；上限 ≥ β 时 Σq_em = 0（团队勘误 R5）。",
        },
        "s_bound": {
            "physical_objective_yuan": s_bound_entry.get("objective_yuan"),
            "physical_total_spill_kwh": s_bound_entry.get("total_spill_kwh"),
            "baseline_total_spill_kwh": baseline["total_spill_kwh"],
            "relative_change": _num(s_bound_delta),
            "note": "D5-B 收紧 s 上界为物理盈余：目标系数为 0；若最优值不变，则 AS09 松界在无售电口径下无套利路径。",
        },
        "s_sell": [
            {
                "label": item["label"],
                "objective_yuan": item.get("objective_yuan"),
                "total_spill_kwh": item.get("total_spill_kwh"),
                "physical_surplus_kwh": item.get("physical_surplus_kwh"),
                "sell_revenue_yuan": item.get("sell_revenue_yuan"),
                "checks_failed": item.get("checks_failed", []),
            }
            for item in groups.get("s_sell", [])
        ],
        "alpha_lt1": [
            {
                "label": item["label"],
                "objective_yuan": item.get("objective_yuan"),
                "total_q_em_kwh": item.get("total_q_em_kwh"),
                "days_with_emergency": item.get("days_with_emergency"),
                "checks_failed": item.get("checks_failed", []),
            }
            for item in groups.get("alpha_lt1", [])
        ],
        "cited_not_rerun": {
            "M4_daily_independent": {
                "value": "交付期 −17,803.27 元（相对全年滚动口径）",
                "source": "assumption_v001 §6 只读探针 / 团队裁定 B1（M4）+ D8-A",
                "note": "robustness 不重复跑；数值以 ablation 的 M4 为准。",
            },
            "M5_terminal_6000": {
                "value": "交付期 +2,217.08 元（+0.018%）",
                "source": "assumption_v001 §6 只读探针 / 团队裁定 B1（M5）+ D8-A / B5",
                "note": "M5 只在 ablation 出数；robustness 仅引用结论并注明来源，不重复计算。",
            },
        },
    }
    summary["structural_findings"] = structural
    return summary, sensitivity


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="prob02 robustness 实验（隔离 task 入口）")
    parser.add_argument("--data", default="data/附件1.xlsx", help="附件 1（只读；只用电价列）")
    parser.add_argument("--data2", default="data/附件2.xlsx", help="附件 2（只读；实际负载/光伏）")
    parser.add_argument("--reference", default=str(RUN002_DIR), help="accepted run002 目录（只读基线闸门）")
    parser.add_argument("--output", required=True, help="输出目录（必须在 assumption_v001 内）")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--samples", type=int, default=25, help="每个噪声族样本数（4 族，默认合计 100）")
    parser.add_argument("--time-limit", type=float, default=120.0, help="单次 LP 的 HiGHS 时限（秒）")
    parser.add_argument("--families", default="all", help="all 或逗号分隔的情景族")
    parser.add_argument("--days", type=int, default=DAYS_FULL, help="优化天数（< 365 为接口自检探针）")
    parser.add_argument("--no-figures", action="store_true")
    return parser.parse_args(argv)


def _write_baseline_failure(output: Path, baseline_check: dict[str, Any], total: int, started: float) -> int:
    write_json(
        output / "run_manifest.json",
        {
            "stage": "robustness",
            "question_id": "prob02",
            "outcome": "baseline_mismatch",
            "checks_failed": ["baseline_reproduction"],
            "cases_total": total,
            "baseline_check": baseline_check,
            "wall_clock_seconds": round(time.perf_counter() - started, 3),
        },
    )
    print("基线复现失败，整批作废（exit 4）", file=sys.stderr)
    return 4


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    probe_mode = args.days < DAYS_FULL
    reference_dir = Path(args.reference)
    if not reference_dir.is_absolute():
        reference_dir = ROOT / reference_dir

    attachment1 = read_attachment1(Path(args.data), expected_rows=PPD)
    attachment2 = read_attachment2(Path(args.data2), expected_days=DAYS_FULL, expected_periods=PPD)
    days = int(args.days)
    periods = days * PPD
    base_price = attachment1.price
    base_load = attachment2.load_kw[:days]
    base_pv = attachment2.pv_kw[:days]

    all_families = {"baseline", "eta", "eta_asym", "init", "alpha", "pmax", "ewin", "solver",
                    "s_bound", "s_sell", "alpha_lt1", "b_cap"} | {name for name, *_ in NOISE_FAMILIES}
    families = all_families if args.families == "all" else {x.strip() for x in args.families.split(",") if x.strip()}
    unknown = families - all_families
    if unknown:
        print(f"未知情景族：{sorted(unknown)}", file=sys.stderr)
        return 3

    matrix = [spec for spec in build_matrix() if spec.family in families]
    records: list[dict[str, Any]] = []
    trajectories: dict[str, dict[str, Any]] = {}
    for spec in matrix:
        case = Case(
            params=spec,
            price=np.tile(base_price, days),
            load_energy=base_load.reshape(-1) * DT,
            pv_energy=base_pv.reshape(-1) * DT,
            days=days,
        )
        solved = solve_case(case, time_limit=args.time_limit)
        record = evaluate(case, solved)
        daily = record.pop("_daily", None)
        if daily:
            trajectories[spec.label] = {"label": spec.label, "family": spec.family, "daily": daily}
        record["kind"] = "matrix"
        records.append(record)
        print(f"[matrix] {spec.label} feasible={record['feasible']} C={record.get('objective_yuan')} "
              f"q_em={record.get('total_q_em_kwh')} t={record['wall_seconds']:.2f}s", flush=True)

    wanted_noise = {name for name in families if name.startswith("noise_")}
    if wanted_noise:
        noise_cases = [case for case in build_noise_cases(base_price, base_load, base_pv, args.seed, args.samples)
                       if case.params.family in wanted_noise]
        for index, case in enumerate(noise_cases, start=1):
            solved = solve_case(case, time_limit=args.time_limit)
            record = evaluate(case, solved)
            record.pop("_daily", None)
            record["kind"] = "noise"
            records.append(record)
            if index % 10 == 0 or index == len(noise_cases):
                print(f"[noise] {index}/{len(noise_cases)} {case.params.label} C={record.get('objective_yuan')}",
                      flush=True)

    with (output / "raw_samples.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    for label, payload in trajectories.items():
        write_json(output / "trajectories" / f"{label}.json", payload)
    print(f"[raw] {len(records)} 条样本写入 raw_samples.jsonl", flush=True)

    baseline = next((item for item in records if item["label"] == "baseline"), None)
    reference_solution = json.loads((reference_dir / "solution.json").read_text(encoding="utf-8"))
    reference_tables = json.loads((reference_dir / "tables.json").read_text(encoding="utf-8"))
    reference_manifest = json.loads((reference_dir / "run_manifest.json").read_text(encoding="utf-8"))
    ref_totals = reference_solution["totals"]
    baseline_check: dict[str, Any] = {
        "reference_dir": str(reference_dir.as_posix()),
        "reference_files_sha256": {
            name: hashlib.sha256((reference_dir / name).read_bytes()).hexdigest()
            for name in ("solution.json", "tables.json", "run_manifest.json", "solver_status.json")
        },
        "reference_task_id": reference_manifest.get("task_id"),
        "probe_mode": probe_mode,
        "compared": {},
        "spec_dates_compared": {},
        "passed": False,
    }
    if baseline is None or not baseline.get("feasible"):
        baseline_check["error"] = "baseline 未运行或不可行"
    else:
        pairs = {
            "objective_yuan": (baseline["objective_yuan"], reference_solution["objective_yuan"]),
            "delivery_cost_yuan": (baseline["delivery_cost_yuan"], reference_solution["delivery_cost_yuan"]),
            "total_purchase_kwh": (baseline["total_purchase_kwh"], ref_totals["total_purchase_kwh"]),
            "total_charge_kwh": (baseline["total_charge_kwh"], ref_totals["total_charge_kwh"]),
            "total_discharge_kwh": (baseline["total_discharge_kwh"], ref_totals["total_discharge_kwh"]),
            "total_spill_kwh": (baseline["total_spill_kwh"], ref_totals["total_spill_kwh"]),
            "storage_final_kwh": (baseline["storage_final_kwh"], ref_totals["storage_final_kwh"]),
            "max_side_power_kw": (baseline["max_side_power_kw"], ref_totals["max_side_power_kw"]),
        }
        ok = True
        for name, (got, want) in pairs.items():
            if got is None or want is None:
                entry = {"ours": got, "reference": want, "relative_diff": None, "passed": False}
            else:
                delta = _rel_diff(got, want)
                entry = {"ours": got, "reference": want, "relative_diff": delta, "passed": delta <= 1e-6}
            baseline_check["compared"][name] = entry
            ok = ok and entry["passed"]
        for date_text, entry in reference_tables.get("table1", {}).items():
            ours = baseline["spec_dates"].get(date_text)
            if not ours:
                continue
            slot_deltas = [abs(a - b["purchase_kwh"]) for a, b in zip(ours["slots_kwh"], entry["slots"])]
            passed = bool(
                _rel_diff(ours["purchase_kwh"], entry["all_day_energy_kwh"]) <= 1e-6
                and _rel_diff(ours["cost_yuan"], entry["all_day_cost_yuan"]) <= 1e-6
                and (max(slot_deltas) if slot_deltas else 0.0) <= 1e-6
            )
            baseline_check["spec_dates_compared"][date_text] = {
                "day_purchase_relative_diff": _rel_diff(ours["purchase_kwh"], entry["all_day_energy_kwh"]),
                "day_cost_relative_diff": _rel_diff(ours["cost_yuan"], entry["all_day_cost_yuan"]),
                "max_slot_abs_diff_kwh": round(max(slot_deltas), 9) if slot_deltas else None,
                "passed": passed,
            }
            ok = ok and passed
        baseline_check["passed"] = bool(ok)

    total_cases = len(records)
    infeasible = [item["label"] for item in records if not item.get("feasible")]
    write_json(
        output / "solver_status.json",
        {
            "solver": "scipy.optimize.linprog",
            "method": "highs",
            "device": "cpu",
            "gpu_required": False,
            "seed": args.seed,
            "feasible_incumbent": bool(baseline and baseline.get("feasible")),
            "baseline_feasible": bool(baseline and baseline.get("feasible")),
            "baseline_check_passed": baseline_check["passed"],
            "cases_total": total_cases,
            "cases_infeasible": len(infeasible),
            "equality_residual_max": baseline.get("equality_residual_max") if baseline else None,
            "bound_violation_max": baseline.get("bound_violation_max") if baseline else None,
            "probe_mode": probe_mode,
        },
    )
    write_json(output / "baseline_check.json", baseline_check)
    if not baseline_check["passed"] and not probe_mode:
        return _write_baseline_failure(output, baseline_check, total_cases, started)

    summary, sensitivity = evaluate_criteria(records, baseline)
    summary["cases_total"] = total_cases
    summary["cases_infeasible"] = infeasible
    summary["checks_failed_union"] = sorted({name for item in records for name in item.get("checks_failed", [])})
    summary["probe_mode"] = probe_mode
    write_json(output / "summary.json", summary)
    write_json(output / "sensitivity.json", sensitivity)

    figures: list[str] = []
    if not args.no_figures:
        try:
            figures = render_figures(output, records, baseline, summary, sensitivity)
        except Exception as exc:  # 图件失败不使数值结果作废
            print(f"[figures] 生成失败：{exc}", file=sys.stderr)
            figures = []

    code_files = sorted(HERE.parent.glob("*.py"))
    manifest = {
        "stage": "robustness",
        "problem_id": "microgrid_2025",
        "question_id": "prob02",
        "assumption_version": "assumption_v001",
        "formulation_version": "formulation_v001",
        "model": "M1 + 参数/噪声/结构扰动",
        "task_id": os.environ.get("AUTOMM_TASK_ID"),
        "output_directory": str(output.as_posix()),
        "probe_mode": probe_mode,
        "input": {
            "attachment1": str(Path(args.data).as_posix()),
            "attachment1_md5": attachment1.md5,
            "attachment2": str(Path(args.data2).as_posix()),
            "attachment2_md5": attachment2.md5,
            "days": days,
            "periods": periods,
        },
        "reference": {
            "dir": str(reference_dir.as_posix()),
            "task_id": reference_manifest.get("task_id"),
            "sha256": baseline_check["reference_files_sha256"],
        },
        "seed": args.seed,
        "noise_samples_per_family": args.samples,
        "noise_samples_total": len([item for item in records if item["kind"] == "noise"]),
        "families": sorted(families),
        "cases_total": total_cases,
        "cases_infeasible": infeasible,
        "checks_failed": summary["criteria_failed"],
        "baseline_check": baseline_check["passed"],
        "stability_grade": summary["stability_grade"],
        "figures": figures,
        "code_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in code_files},
        "accepted_code_sha256": {
            name: hashlib.sha256((ACCEPTED_CODE / name).read_bytes()).hexdigest()
            for name in ("prob02_model.py", "prob02_io.py", "run_prob02.py")
        },
        "device": "cpu",
        "gpu_required": False,
        "gpu_serial_constraint": "本 task 不使用 GPU",
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "platform": platform.platform(),
        },
        "outcome": "completed" if not summary["criteria_failed"] else "completed_with_findings",
        "wall_clock_seconds": round(time.perf_counter() - started, 3),
    }
    write_json(output / "run_manifest.json", manifest)
    print(json.dumps({"outcome": manifest["outcome"], "cases": total_cases,
                      "criteria_failed": summary["criteria_failed"],
                      "wall_clock_seconds": manifest["wall_clock_seconds"]}, ensure_ascii=False))
    return 0


# --------------------------------------------------------------------------- #
# 图件
# --------------------------------------------------------------------------- #


def render_figures(
    output: Path,
    records: list[dict[str, Any]],
    baseline: dict[str, Any],
    summary: dict[str, Any],
    sensitivity: dict[str, Any],
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    style = config_section("visualization", "microgrid_2025", "prob02")
    palette = style.get("palette", {})
    primary = palette.get("primary", "#1F4E79")
    secondary = palette.get("secondary", "#70AD47")
    accent = palette.get("accent", "#ED7D31")
    neutral = palette.get("neutral", "#7F8C8D")
    warning = palette.get("warning", "#C00000")
    available = {font.name for font in font_manager.fontManager.ttflist}
    candidates = [style.get("preferred_font"), *style.get("fallback_fonts", [])]
    font = next((str(item) for item in candidates if item and item in available), None)
    if font is None:
        raise RuntimeError("未找到配置中的中文字体，拒绝出图（避免方框字符）")
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": [font, "DejaVu Sans"],
        "font.size": style.get("font_size", 11),
        "axes.titlesize": style.get("title_size", 14),
        "axes.unicode_minus": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.22,
        "figure.dpi": int(style.get("dpi", 180)),
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
    })
    figure_dir = output / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(record["family"], []).append(record)
    base_cost = float(baseline["objective_yuan"])
    figures: list[str] = []

    # 图 1 龙卷风图（±20%）
    tornado = sensitivity["tornado_20pct"]
    names = [name for name in ("eta", "e_init", "alpha_em", "p_max", "e_min", "e_max")
             if tornado.get(name, {}).get("low_relative_change") is not None]
    fig, ax = plt.subplots(figsize=(8.6, 4.2))
    for index, name in enumerate(names):
        low = (tornado[name]["low_relative_change"] or 0.0) * 100
        high = (tornado[name]["high_relative_change"] or 0.0) * 100
        ax.barh(index, low, color=warning, alpha=0.85, label="低档（−20%）" if index == 0 else None)
        ax.barh(index, high, color=primary, alpha=0.85, label="高档（+20%）" if index == 0 else None)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(
        [f"{name}\n({tornado[name]['low_value']:g} / {tornado[name]['high_value']:g})" for name in names]
    )
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("全天总购电费相对变化（%）")
    ax.set_title("龙卷风图：参数 OAT ±20%（最近网格点）")
    ax.legend(loc="lower right", frameon=False)
    fig.tight_layout()
    fig.savefig(figure_dir / "robustness_tornado.png")
    plt.close(fig)
    figures.append("robustness_tornado.png")

    # 图 2 响应曲线
    panels = (
        ("eta", "eta_ch", "η（两侧同步）"),
        ("init", "e_init", "E_init（kWh）"),
        ("alpha", "alpha_em", "α_em"),
        ("pmax", "p_max", "P_max（kW）"),
        ("ewin", "e_min", "E_min（kWh）"),
        ("ewin", "e_max", "E_max（kWh）"),
    )
    fig, axes = plt.subplots(2, 3, figsize=(12, 6))
    for ax, (family, key, label) in zip(axes.ravel(), panels):
        items = sorted(
            [item for item in groups.get(family, []) if item.get("feasible") and item["params"][key] is not None],
            key=lambda item: item["params"][key],
        )
        xs = [item["params"][key] for item in items]
        ys = [item["objective_yuan"] for item in items]
        ax.plot(xs, ys, marker="o", color=primary, linewidth=1.6)
        ax.axhline(base_cost, color=neutral, linestyle="--", linewidth=0.9)
        ax.set_xlabel(label)
        ax.set_ylabel("全天总购电费（元）")
        ax.set_title(f"{key}")
    fig.tight_layout()
    fig.savefig(figure_dir / "robustness_response_curves.png")
    plt.close(fig)
    figures.append("robustness_response_curves.png")

    # 图 3 噪声 ECDF
    fig, ax = plt.subplots(figsize=(8, 4.6))
    colors = (primary, secondary, accent, warning)
    for color, family in zip(colors, [name for name in sorted(groups) if name.startswith("noise_")]):
        values = np.sort(np.asarray(
            [item["objective_yuan"] for item in groups[family] if item.get("feasible")], dtype=float
        ))
        if values.size:
            ax.step(values, np.arange(1, values.size + 1) / values.size, where="post",
                    color=color, label=f"{family} (n={values.size})")
    ax.axvline(base_cost, color="black", linestyle=":", label="accepted 基线")
    ax.set_xlabel("全天总购电费（元）")
    ax.set_ylabel("经验分布 ECDF")
    ax.set_title("输入噪声传播（4 族 × 25 样本）")
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(figure_dir / "robustness_noise_ecdf.png")
    plt.close(fig)
    figures.append("robustness_noise_ecdf.png")

    # 图 4 购电上限灵敏度（R2 网格 + M6′）
    rows = sorted([row for row in summary["structural_findings"]["b_cap"]["rows"] if row["feasible"]],
                  key=lambda row: row["b_cap_kw"])
    if rows:
        labels = [f"{row['b_cap_kw']:g}" for row in rows] + ["∞（基线）"]
        q_em = [row["total_q_em_kwh"] or 0.0 for row in rows] + [0.0]
        cost = [row["objective_yuan"] or 0.0 for row in rows] + [base_cost]
        positions = np.arange(len(labels))
        fig, ax1 = plt.subplots(figsize=(10, 4.4))
        ax1.bar(positions, q_em, color=accent, alpha=0.85)
        ax1.set_xticks(positions)
        ax1.set_xticklabels(labels, rotation=40)
        ax1.set_xlabel("b 的功率上限（kW）")
        ax1.set_ylabel("Σq_em（kWh）", color=accent)
        ax2 = ax1.twinx()
        ax2.plot(positions, cost, marker="o", color=primary)
        ax2.set_ylabel("全天总购电费（元）", color=primary)
        ax1.set_title("购电上限灵敏度（R2 原网格 + M6′）；阈值 β 由相邻网格点夹逼")
        fig.tight_layout()
        fig.savefig(figure_dir / "robustness_buy_cap_curve.png")
        plt.close(fig)
        figures.append("robustness_buy_cap_curve.png")

    # 图 5 结构情景柱状
    scenario_labels: list[str] = []
    scenario_deltas: list[float] = []
    for family in ("ewin", "s_bound", "s_sell", "alpha_lt1", "eta_asym", "solver"):
        for item in groups.get(family, []):
            if item.get("feasible") and item["objective_yuan"] is not None and item["label"] != "baseline":
                scenario_labels.append(item["label"])
                scenario_deltas.append((item["objective_yuan"] - base_cost) / base_cost * 100)
    if scenario_labels:
        fig, ax = plt.subplots(figsize=(11, 4.4))
        colors = [primary if value >= 0 else secondary for value in scenario_deltas]
        ax.bar(range(len(scenario_labels)), scenario_deltas, color=colors)
        ax.set_xticks(range(len(scenario_labels)))
        ax.set_xticklabels(scenario_labels, rotation=60, ha="right", fontsize=8)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_ylabel("全天总购电费相对变化（%）")
        ax.set_title("结构情景与求解器设置对照（不改变交付口径）")
        fig.tight_layout()
        fig.savefig(figure_dir / "robustness_scenarios.png")
        plt.close(fig)
        figures.append("robustness_scenarios.png")

    # 图 6 spider（归一化 OAT 响应）
    fig, ax = plt.subplots(figsize=(7, 5))
    for name, (family, key) in (("η", ("eta", "eta_ch")), ("E_init", ("init", "e_init")),
                                ("α_em", ("alpha", "alpha_em")), ("P_max", ("pmax", "p_max")),
                                ("E_min", ("ewin", "e_min")), ("E_max", ("ewin", "e_max"))):
        items = sorted(
            [item for item in groups.get(family, []) if item.get("feasible")
             and item["params"][key] is not None and item["objective_yuan"] is not None],
            key=lambda item: item["params"][key],
        )
        if not items:
            continue
        xs = np.asarray([item["params"][key] for item in items], dtype=float)
        ys = np.asarray([(item["objective_yuan"] - base_cost) / base_cost for item in items], dtype=float)
        span = max(float(np.max(np.abs(xs - xs.mean()))), 1e-9)
        ax.plot((xs - xs.mean()) / span, ys, marker="o", label=name)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("归一化参数偏差")
    ax.set_ylabel("全天总购电费相对变化")
    ax.set_title("Spider 图：OAT 归一化响应")
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(figure_dir / "robustness_spider.png")
    plt.close(fig)
    figures.append("robustness_spider.png")
    return figures


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
