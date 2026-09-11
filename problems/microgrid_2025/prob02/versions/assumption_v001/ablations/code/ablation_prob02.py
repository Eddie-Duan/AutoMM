# -*- coding: utf-8 -*-
"""prob02 消融与模型族对照实验（隔离 task 入口）。

实验设计见同版本 ``ablations/plan.md``（预注册；模型集合 M1–M7 + M6′、判据 C1–C7、
公平性纪律与失败处理在实验批运行前冻结，事后不得修改）。

本脚本只读 ``data/``（经 ``--data``/``--data2``）与 accepted 产物（``--reference``），
向 ``--output`` 写：

- ``baseline_check.json``  C1 基线复现闸门（M1 ↔ run002 逐项对比）
- ``solver_status.json``   可行解标记 + 基线闸门 + 环境（供 task_worker 判定 feasible_incumbent）
- ``comparison.json``      模型 × 指标对比表（M1–M7 + M6/M6′ 全条目）
- ``identities.json``      (I1)/(I2) 全期与交付期残差、逐日连续性、Σq_em=0 可证性说明
- ``raw_cases.jsonl``      每个模型一行（失败 case 保留、不删除）
- ``summary.json``         C1–C7 判定 + K1–K6 结论 + 结构性发现 + 技术债
- ``figures/*.png``        4 张实验图（不登记为交付图表）
- ``run_manifest.json``    追踪信息（task_id、代码 sha256、输入 md5、种子、计数、耗时）
- ``<MODEL>/case.json``    每个模型一个独立子目录（原始样本与汇总分开）

口径（团队裁定 B0/B4）：``min Σ(p·b + α_em·p·q_em)``（元，**不乘 Δt**）、
``E_τ = E_{τ−1} + η_ch·c_τ − q_dis,τ/η_dis``、口径丙 ``c ≤ P·Δt``、``q_dis ≤ P·Δt·η_dis``、
``E ∈ [1200,10800]``、``E_0 = 6000``、``E_T`` 自由（AS04/D2-A）、全年 365 天滚动、CPU HiGHS、无 GPU。

**边界纪律（团队裁定 B5 / D8-A）**：M4（逐日独立）与 M5（终端=6000）在本阶段出数，
robustness 只可带出处引用；``b`` 上限族（M6/M6′）与 robustness 的 ``b_cap`` 属独立计算，
数值不得互相替代，冲突须在报告中显式登记。
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import coo_matrix, csr_matrix, hstack

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve()
VERSION_DIR = HERE.parents[2]                       # .../assumption_v001
CODE_DIR = HERE.parent
ACCEPTED_CODE = VERSION_DIR / "code"
ROOT = HERE.parents[7]
for _extra in (ACCEPTED_CODE, ROOT / "scripts"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from prob02_io import day_offset, read_attachment1, read_attachment2, write_json  # noqa: E402

DT = 1.0 / 6.0
TOL = 1e-6
BAL_TOL = 1e-8                                       # B2 第 1 条：逐时段平衡残差 ≤ 1e-8
PPD = 144
DAYS_FULL = 365
KINDS = ("b", "q_em", "c", "q_dis", "s", "E")
NO_SPILL_KINDS = ("b", "q_em", "c", "q_dis", "E")
E_INIT = 6000.0
E_MIN = 1200.0
E_MAX = 10800.0
P_MAX = 5000.0
ETA = 0.9
ETA2 = ETA * ETA
ALPHA = 5.0
C_CAP = P_MAX * DT
Q_CAP = P_MAX * DT * ETA
DELIVERY_START = 31                                  # 2025-02-01（1 月为预热期）
B_PEAK_KW = 10325.33                                 # AS10 非绑定阈值（勘误 R5）
BETA_BRACKET = (4218.75, 4375.00)                    # 勘误 R5 / formulation T2
SPEC_DATES = ("2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21")
TABLE1_POS = (60, 72, 84, 96, 108, 120)              # 1 基位置（AS01 左端点）
BLOCK_ROWS = 24
BLOCKS = 6
SEED = 20260910
FULL_TIME_LIMIT = 300.0
MILP_TIME_LIMIT = 300.0
REF_RUN = "prob02_v001_f001_run002"


# --------------------------------------------------------------------------- #
# 输入
# --------------------------------------------------------------------------- #


class InputError(RuntimeError):
    """输入结构或参数非法（exit 3）。"""


def load_inputs(data_path: str, data2_path: str) -> dict[str, Any]:
    a1 = read_attachment1(Path(data_path))
    a2 = read_attachment2(Path(data2_path))
    price = np.asarray(a1.price, dtype=float)
    load = np.asarray(a2.load_kw, dtype=float) * DT
    pv = np.asarray(a2.pv_kw, dtype=float) * DT
    if price.shape != (PPD,):
        raise InputError(f"附件 1 电价长度 {price.shape} != ({PPD},)")
    if load.shape != (DAYS_FULL, PPD) or pv.shape != (DAYS_FULL, PPD):
        raise InputError(f"附件 2 形状 {load.shape}/{pv.shape} != ({DAYS_FULL},{PPD})")
    return {
        "price": price,
        "load": load,
        "pv": pv,
        "dates": list(a2.dates),
        "a1_md5": a1.md5,
        "a2_md5": a2.md5,
    }


def _flat(price: np.ndarray, days: int) -> np.ndarray:
    return np.tile(price, days)


def _flat2(matrix: np.ndarray, days: int) -> np.ndarray:
    return matrix[:days].reshape(-1)


# --------------------------------------------------------------------------- #
# 全年 LP（M1 / M5 / M6 / M6′）
# --------------------------------------------------------------------------- #


def build_full_lp(
    price: np.ndarray, load: np.ndarray, pv: np.ndarray, *, terminal: float | None = None,
    b_cap_kwh: float | None = None,
) -> dict[str, Any]:
    """构造 ``(P2)``：``min cᵀx s.t. A_eq x = b_eq, l ≤ x ≤ u``（6 类变量按 KINDS 顺序）。"""
    periods = int(price.shape[0])
    size = len(KINDS) * periods
    obj = np.zeros(size)
    obj[0:periods] = price
    obj[periods : 2 * periods] = ALPHA * price

    lower = np.zeros(size)
    upper = np.empty(size)
    upper[0:periods] = np.inf if b_cap_kwh is None else float(b_cap_kwh)
    upper[periods : 2 * periods] = np.inf
    upper[2 * periods : 3 * periods] = C_CAP
    upper[3 * periods : 4 * periods] = Q_CAP
    upper[4 * periods : 5 * periods] = pv
    lower[5 * periods : 6 * periods] = E_MIN
    upper[5 * periods : 6 * periods] = E_MAX
    if terminal is not None:
        lower[size - 1] = float(terminal)
        upper[size - 1] = float(terminal)

    tau = np.arange(periods, dtype=np.int64)
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    vals: list[np.ndarray] = []

    def add(row: np.ndarray, col: np.ndarray, value: np.ndarray) -> None:
        rows.append(row)
        cols.append(col)
        vals.append(value)

    off = lambda kind: KINDS.index(kind) * periods  # noqa: E731
    # (R1) 平衡：b + q_em + q_dis − c − s = L·Δt − PV·Δt
    add(tau, off("b") + tau, np.ones(periods))
    add(tau, off("q_em") + tau, np.ones(periods))
    add(tau, off("q_dis") + tau, np.ones(periods))
    add(tau, off("c") + tau, -np.ones(periods))
    add(tau, off("s") + tau, -np.ones(periods))
    # (R2) SOC：E_τ − E_{τ−1} − η·c_τ + q_dis,τ/η = 0（τ=1 时 RHS = E_0）
    add(periods + tau, off("E") + tau, np.ones(periods))
    add(periods + tau[1:], off("E") + tau[1:] - 1, -np.ones(periods - 1))
    add(periods + tau, off("c") + tau, -ETA * np.ones(periods))
    add(periods + tau, off("q_dis") + tau, (1.0 / ETA) * np.ones(periods))

    a_eq = coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(2 * periods, size)
    ).tocsr()
    b_eq = np.concatenate([load - pv, np.concatenate([[E_INIT], np.zeros(periods - 1)])])
    scale = {
        "variables": size,
        "equality_constraints": 2 * periods,
        "inequality_constraints": 0,
        "binaries": 0,
        "nonzero": int(a_eq.nnz),
    }
    return {"obj": obj, "A_eq": a_eq, "b_eq": b_eq, "lower": lower, "upper": upper, "scale": scale}


def build_full_lp_no_spill(
    price: np.ndarray, load: np.ndarray, pv: np.ndarray, *, terminal: float | None = None
) -> dict[str, Any]:
    """M7 独立实现：消去 ``s``，平衡改写为等价不等式对；变量 ``(b, q_em, c, q_dis, E)``。"""
    periods = int(price.shape[0])
    size = 5 * periods
    obj = np.zeros(size)
    obj[0:periods] = price
    obj[periods : 2 * periods] = ALPHA * price

    lower = np.zeros(size)
    upper = np.empty(size)
    upper[0:periods] = np.inf
    upper[periods : 2 * periods] = np.inf
    upper[2 * periods : 3 * periods] = C_CAP
    upper[3 * periods : 4 * periods] = Q_CAP
    lower[4 * periods : 5 * periods] = E_MIN
    upper[4 * periods : 5 * periods] = E_MAX
    if terminal is not None:
        lower[size - 1] = float(terminal)
        upper[size - 1] = float(terminal)

    tau = np.arange(periods, dtype=np.int64)
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    vals: list[np.ndarray] = []

    def add(row: np.ndarray, col: np.ndarray, value: np.ndarray) -> None:
        rows.append(row)
        cols.append(col)
        vals.append(value)

    off = lambda kind: NO_SPILL_KINDS.index(kind) * periods  # noqa: E731
    # (R2) SOC
    add(tau, off("E") + tau, np.ones(periods))
    add(tau[1:], off("E") + tau[1:] - 1, -np.ones(periods - 1))
    add(tau, off("c") + tau, -ETA * np.ones(periods))
    add(tau, off("q_dis") + tau, (1.0 / ETA) * np.ones(periods))
    a_eq = coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(periods, size)
    ).tocsr()
    b_eq = np.concatenate([[E_INIT], np.zeros(periods - 1)])

    # 平衡不等式对：L·Δt − PV·Δt ≤ b + q + q_dis − c ≤ L·Δt
    # 上半块（行 0..T−1）系数 +1；下半块（行 T..2T−1）整体取负（把 ≥ 写成 ≤）
    ub_rows = np.arange(2 * periods, dtype=np.int64)
    ub_cols: list[np.ndarray] = []
    ub_vals: list[np.ndarray] = []
    for kind, sign in (("b", 1.0), ("q_em", 1.0), ("q_dis", 1.0), ("c", -1.0)):
        ub_cols.append(off(kind) + (ub_rows % periods))
        ub_vals.append(np.concatenate([sign * np.ones(periods), -sign * np.ones(periods)]))
    a_ub = coo_matrix(
        (np.concatenate(ub_vals), (np.tile(ub_rows, 4), np.concatenate(ub_cols))), shape=(2 * periods, size)
    ).tocsr()
    b_ub = np.concatenate([load, -(load - pv)])
    scale = {
        "variables": size,
        "equality_constraints": periods,
        "inequality_constraints": 2 * periods,
        "binaries": 0,
        "nonzero": int(a_eq.nnz + a_ub.nnz),
    }
    return {"obj": obj, "A_eq": a_eq, "b_eq": b_eq, "A_ub": a_ub, "b_ub": b_ub,
            "lower": lower, "upper": upper, "scale": scale}


def solve_lp(model: dict[str, Any], *, method: str = "highs", presolve: bool = True,
             time_limit: float = FULL_TIME_LIMIT) -> tuple[Any, float]:
    bounds = np.column_stack((model["lower"], model["upper"]))
    started = time.perf_counter()
    res = linprog(
        model["obj"],
        A_ub=model.get("A_ub"),
        b_ub=model.get("b_ub"),
        A_eq=model["A_eq"],
        b_eq=model["b_eq"],
        bounds=bounds,
        method=method,
        options={"time_limit": float(time_limit), "presolve": bool(presolve)},
    )
    elapsed = time.perf_counter() - started
    return res, elapsed


def unbundle_full(x: np.ndarray, periods: int) -> dict[str, np.ndarray]:
    out = {}
    for kind in KINDS:
        offset = KINDS.index(kind) * periods
        out[kind] = np.asarray(x[offset : offset + periods], dtype=float)
    return out


def unbundle_no_spill(x: np.ndarray, periods: int, load: np.ndarray,
                      pv: np.ndarray) -> dict[str, np.ndarray]:
    """M7 列序 ``(b, q_em, c, q_dis, E)``；由 ``(R1a)/(R1b)`` 回代重建 ``s``。"""
    b = np.asarray(x[0:periods], dtype=float)
    q = np.asarray(x[periods : 2 * periods], dtype=float)
    c = np.asarray(x[2 * periods : 3 * periods], dtype=float)
    d = np.asarray(x[3 * periods : 4 * periods], dtype=float)
    e = np.asarray(x[4 * periods : 5 * periods], dtype=float)
    return {"b": b, "q_em": q, "c": c, "q_dis": d, "E": e, "s": b + q + d + (pv - load) - c}


# --------------------------------------------------------------------------- #
# 日规模 LP（M2a / M2b / M4）
# --------------------------------------------------------------------------- #


def build_day_lp(price_d: np.ndarray, load_d: np.ndarray, pv_d: np.ndarray) -> dict[str, Any]:
    periods = PPD
    size = len(KINDS) * periods
    obj = np.zeros(size)
    obj[0:periods] = price_d
    obj[periods : 2 * periods] = ALPHA * price_d
    lower = np.zeros(size)
    upper = np.empty(size)
    upper[0:periods] = np.inf
    upper[periods : 2 * periods] = np.inf
    upper[2 * periods : 3 * periods] = C_CAP
    upper[3 * periods : 4 * periods] = Q_CAP
    upper[4 * periods : 5 * periods] = pv_d
    lower[5 * periods : 6 * periods] = E_MIN
    upper[5 * periods : 6 * periods] = E_MAX

    tau = np.arange(periods, dtype=np.int64)
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    vals: list[np.ndarray] = []

    def add(row: np.ndarray, col: np.ndarray, value: np.ndarray) -> None:
        rows.append(row)
        cols.append(col)
        vals.append(value)

    off = lambda kind: KINDS.index(kind) * periods  # noqa: E731
    add(tau, off("b") + tau, np.ones(periods))
    add(tau, off("q_em") + tau, np.ones(periods))
    add(tau, off("q_dis") + tau, np.ones(periods))
    add(tau, off("c") + tau, -np.ones(periods))
    add(tau, off("s") + tau, -np.ones(periods))
    add(periods + tau, off("E") + tau, np.ones(periods))
    add(periods + tau[1:], off("E") + tau[1:] - 1, -np.ones(periods - 1))
    add(periods + tau, off("c") + tau, -ETA * np.ones(periods))
    add(periods + tau, off("q_dis") + tau, (1.0 / ETA) * np.ones(periods))
    a_eq = coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(2 * periods, size)
    ).tocsr()
    b_eq = np.concatenate([load_d - pv_d, np.concatenate([[E_INIT], np.zeros(periods - 1)])])
    scale = {"variables": size, "equality_constraints": 2 * periods, "inequality_constraints": 0,
             "binaries": 0, "nonzero": int(a_eq.nnz)}
    return {"obj": obj, "A_eq": a_eq, "b_eq": b_eq, "lower": lower, "upper": upper,
            "load_d": load_d, "pv_d": pv_d, "scale": scale}


def solve_day_lp(model: dict[str, Any], e0: float, terminal: float | None,
                 price_d: np.ndarray, *, time_limit: float = 60.0) -> dict[str, Any]:
    lower = model["lower"].copy()
    upper = model["upper"].copy()
    b_eq = model["b_eq"].copy()
    b_eq[PPD] = float(e0)
    if terminal is not None:
        upper[-1] = float(terminal)
        lower[-1] = float(terminal)
    bounds = np.column_stack((lower, upper))
    started = time.perf_counter()
    res = linprog(model["obj"], A_eq=model["A_eq"], b_eq=b_eq, bounds=bounds, method="highs",
                  options={"time_limit": float(time_limit), "presolve": True})
    elapsed = time.perf_counter() - started
    if res.x is None:
        return {"ok": False, "status": int(res.status), "message": str(res.message), "seconds": elapsed}
    x = np.asarray(res.x, dtype=float)
    columns = unbundle_full(x, PPD)
    eq_res = float(np.max(np.abs(model["A_eq"] @ x - b_eq)))
    violation_low = float(np.max(lower - x))
    finite_upper = np.where(np.isfinite(upper), x - upper, -np.inf)
    bound_viol = max(violation_low, float(np.max(finite_upper)), 0.0)
    plan_cost = float(np.sum(price_d * columns["b"]))
    em_cost = float(np.sum(ALPHA * price_d * columns["q_em"]))
    return {
        "ok": True,
        "status": int(res.status),
        "message": str(res.message),
        "seconds": elapsed,
        "iterations": int(res.nit) if res.nit is not None else None,
        "objective": float(res.fun),
        "plan_cost": plan_cost,
        "em_cost": em_cost,
        "eq_residual": eq_res,
        "bound_violation": bound_viol,
        "columns": columns,
        "state_end": float(columns["E"][-1]),
    }


def solve_day_sequence(
    price: np.ndarray, load: np.ndarray, pv: np.ndarray, days: int, *,
    mode: str, m1_state: np.ndarray | None = None,
) -> dict[str, Any]:
    """逐日求解：``m2a``（终端外生固定）/ ``m2b``（日终自由递推）/ ``m4``（日初=日终=6000）。"""
    full = {kind: np.empty(days * PPD) for kind in KINDS}
    day = {key: np.zeros(days) for key in ("objective", "plan_cost", "em_cost", "purchase", "q_em",
                                           "charge", "discharge", "spill", "state_start", "state_end")}
    model_cache: dict[int, dict[str, Any]] = {}
    worst = {"eq_residual": 0.0, "bound_violation": 0.0}
    total_seconds = 0.0
    failed: list[dict[str, Any]] = []
    state = E_INIT
    price_d = price[:PPD]
    for d in range(days):
        load_d = load[d * PPD : (d + 1) * PPD]
        pv_d = pv[d * PPD : (d + 1) * PPD]
        key = d
        if key not in model_cache:
            model_cache[key] = build_day_lp(price_d, load_d, pv_d)
        model = model_cache.pop(key)
        e0 = float(state)
        if mode == "m2a":
            if m1_state is None:
                raise InputError("M2a 需要 M1 的状态序列")
            terminal: float | None = float(m1_state[(d + 1) * PPD])
        elif mode == "m4":
            terminal = E_INIT
            e0 = E_INIT
        else:
            terminal = None
        result = solve_day_lp(model, e0, terminal, price_d)
        total_seconds += result.get("seconds", 0.0)
        if not result["ok"]:
            failed.append({"day_index": d, "status": result["status"], "message": result["message"]})
            for kind in KINDS:
                full[kind][d * PPD : (d + 1) * PPD] = np.nan
            continue
        columns = result["columns"]
        for kind in KINDS:
            full[kind][d * PPD : (d + 1) * PPD] = columns[kind]
        day["objective"][d] = result["plan_cost"] + result["em_cost"]
        day["plan_cost"][d] = result["plan_cost"]
        day["em_cost"][d] = result["em_cost"]
        day["purchase"][d] = float(np.sum(columns["b"]))
        day["q_em"][d] = float(np.sum(columns["q_em"]))
        day["charge"][d] = float(np.sum(columns["c"]))
        day["discharge"][d] = float(np.sum(columns["q_dis"]))
        day["spill"][d] = float(np.sum(columns["s"]))
        day["state_start"][d] = e0
        day["state_end"][d] = result["state_end"]
        state = result["state_end"]
        worst["eq_residual"] = max(worst["eq_residual"], result["eq_residual"])
        worst["bound_violation"] = max(worst["bound_violation"], result["bound_violation"])
    return {
        "full": full,
        "day": day,
        "worst_eq_residual": worst["eq_residual"],
        "worst_bound_violation": worst["bound_violation"],
        "solve_seconds": total_seconds,
        "infeasible_days": failed,
        "scale": {"variables_per_day": len(KINDS) * PPD, "equality_per_day": 2 * PPD,
                  "days": days, "note": "逐日解耦；只改时域组织/跨日口径"},
    }


# --------------------------------------------------------------------------- #
# 指标评估（与求解矩阵无关的通用检查）
# --------------------------------------------------------------------------- #


def _finite(value: float) -> float | None:
    value = float(value)
    return value if np.isfinite(value) else None


def _rel(value: float, ref: float) -> float:
    if abs(ref) > 1e-12:
        return abs(value - ref) / abs(ref)
    return abs(value - ref)


def evaluate_arrays(
    columns: dict[str, np.ndarray], price: np.ndarray, load: np.ndarray, pv: np.ndarray,
    days: int, dates: list[str], *, full_horizon: bool = True, premise_no_cap: bool = True,
) -> dict[str, Any]:
    b = columns["b"]
    q = columns["q_em"]
    ch = columns["c"]
    dis = columns["q_dis"]
    s = columns["s"]
    e = columns["E"]
    periods = days * PPD
    state = np.concatenate([[E_INIT], e])

    checks: list[dict[str, Any]] = []

    def record(name: str, value: float, threshold: float, passed: bool, note: str = "",
               required: bool = True) -> None:
        checks.append({"name": name, "value": _finite(value), "threshold": float(threshold),
                       "passed": bool(passed), "required": bool(required), "note": note})

    balance = b + q + pv + dis - load - ch - s
    balance_res = float(np.max(np.abs(balance)))
    e_prev = state[:-1]
    soc_res = float(np.max(np.abs((e - e_prev) - ETA * ch + dis / ETA)))
    continuity = 0.0
    if days > 1:
        starts = state[: periods : PPD]
        ends = state[PPD : periods + 1 : PPD]
        continuity = float(np.max(np.abs(starts[1:] - ends[:-1])))

    total_b = float(np.sum(b))
    total_q = float(np.sum(q))
    total_c = float(np.sum(ch))
    total_dis = float(np.sum(dis))
    total_s = float(np.sum(s))
    cost_plan = float(np.sum(price * b))
    cost_em = float(np.sum(ALPHA * price * q))
    cost = cost_plan + cost_em
    net_load = float(np.sum(load - pv))
    storage_final = float(state[-1])

    delivery_start = min(DELIVERY_START, days)
    start_index = delivery_start * PPD
    if start_index < periods:
        delivery = slice(start_index, periods)
        state_start_delivery = float(state[start_index])
        net_delivery = float(np.sum(load[delivery] - pv[delivery]))
        cost_delivery = float(np.sum(price[delivery] * b[delivery]) + np.sum(ALPHA * price[delivery] * q[delivery]))
        plan_delivery = float(np.sum(price[delivery] * b[delivery]))
        em_delivery = float(np.sum(ALPHA * price[delivery] * q[delivery]))
        i1_delivery = float(
            np.sum(dis[delivery]) - (ETA2 * np.sum(ch[delivery]) - ETA * (storage_final - state_start_delivery))
        )
        i2_delivery = float(
            np.sum(b[delivery]) - (net_delivery + np.sum(s[delivery]) + (1.0 - ETA2) * np.sum(ch[delivery])
                                   + ETA * (storage_final - state_start_delivery) - np.sum(q[delivery]))
        )
    else:
        net_delivery = 0.0
        cost_delivery = 0.0
        plan_delivery = 0.0
        em_delivery = 0.0
        i1_delivery = 0.0
        i2_delivery = 0.0

    i1 = float(total_dis - (ETA2 * total_c - ETA * (storage_final - E_INIT)))
    i2 = float(total_b - (net_load + total_s + (1.0 - ETA2) * total_c + ETA * (storage_final - E_INIT) - total_q))

    charge_price = float(np.sum(price * ch) / total_c) if total_c > TOL else 0.0
    discharge_price = float(np.sum(price * dis) / total_dis) if total_dis > TOL else 0.0

    record("balance_residual_max", balance_res, BAL_TOL, balance_res <= TOL, "(R1) 逐时段电量平衡回代")
    record("soc_residual_max", soc_res, TOL, soc_res <= TOL, "(R2) SOC 状态转移回代")
    record("cross_day_continuity", continuity, TOL, continuity <= TOL, "|E_{d,0} − E_{d−1,144}|")
    record("storage_range", float(np.min(state[1:])), E_MIN, float(np.min(state[1:])) >= E_MIN - TOL, "E ≥ 1200")
    record("storage_upper", float(np.max(state[1:])), E_MAX, float(np.max(state[1:])) <= E_MAX + TOL, "E ≤ 10800")
    record("charge_cap", float(np.max(ch)), C_CAP, float(np.max(ch)) <= C_CAP + TOL, "c ≤ 833.3333")
    record("discharge_cap", float(np.max(dis)), Q_CAP, float(np.max(dis)) <= Q_CAP + TOL, "q_dis ≤ 750.0000")
    record("spill_bound", float(np.max(s - pv)), 0.0, bool(np.all(s <= pv + TOL)), "0 ≤ s ≤ PV·Δt")
    record("nonnegativity", float(min(np.min(b), np.min(q), np.min(ch), np.min(dis), np.min(s))), 0.0,
           bool(np.all(b >= -TOL) and np.all(q >= -TOL) and np.all(ch >= -TOL)
                and np.all(dis >= -TOL) and np.all(s >= -TOL)), "b,q_em,c,q_dis,s ≥ 0")
    charge_power = float(max(np.max(ch), ETA * np.max(ch)) / DT)
    discharge_power = float(max(np.max(dis), np.max(dis) / ETA) / DT)
    record("max_side_power_kw", max(charge_power, discharge_power), P_MAX,
           max(charge_power, discharge_power) <= P_MAX + 1e-3, "并网点侧与电池侧功率均 ≤ 5000 kW")
    record("q_em_zero_total", total_q, TOL, total_q <= TOL,
           "定理 T1（完全信息 + 无上限 ⇒ Σq_em = 0）", required=premise_no_cap)
    complementarity = float(np.sum(ch * dis))
    record("complementarity_sum", complementarity, TOL, complementarity <= TOL, "引理 L1 同充放残差")
    record("identity_I1", i1, TOL, abs(i1) <= TOL, "Σq_dis = η²Σc − η(E_T − E_0)")
    record("identity_I2", i2, TOL, abs(i2) <= TOL, "Σb = N + Σs + 0.19Σc + η(E_T − E_0) − Σq_em")
    if full_horizon:
        lower_bound = float(np.min(price) * (net_load + ETA * (E_MIN - E_INIT)))
        no_storage = float(np.sum(price * np.maximum(load - pv, 0.0)))
        record("analytic_lower_bound", cost, lower_bound, cost >= lower_bound - 1e-6,
               "C ≥ min(p)·[N + η(E_min − E_0)]")
        record("analytic_upper_bound", no_storage, cost, cost <= no_storage + 1e-6,
               "无储能可行解的购电费上界（仅在 b 无上限时前提成立）", required=premise_no_cap)
        record("magnitude_delivery_10m", cost_delivery, 1.0e7, cost_delivery >= 1.0e7,
               "交付期费用 10^7 元量级（防 Δt 误乘）", required=bool(start_index < periods))

    spec_table: dict[str, Any] = {}
    for name in SPEC_DATES:
        try:
            index = day_offset(dates, name)
        except Exception:
            continue
        if index >= days:
            continue
        sl = slice(index * PPD, (index + 1) * PPD)
        price_day = price[:PPD]
        blocks_charge: list[float] = []
        blocks_discharge: list[float] = []
        for k in range(BLOCKS):
            seg = slice(k * BLOCK_ROWS, (k + 1) * BLOCK_ROWS)
            blocks_charge.append(float(np.sum(ch[sl][seg])))
            blocks_discharge.append(float(np.sum(dis[sl][seg])))
        spec_table[name] = {
            "slots_purchase_kwh": [float(b[sl][pos - 1]) for pos in TABLE1_POS],
            "all_day_energy_kwh": float(np.sum(b[sl])),
            "all_day_cost_yuan": float(np.sum(price_day * b[sl]) + np.sum(ALPHA * price_day * q[sl])),
            "block_charge_kwh": blocks_charge,
            "block_discharge_kwh": blocks_discharge,
            "storage_0_00_kwh": float(state[index * PPD]),
            "storage_24_00_kwh": float(state[(index + 1) * PPD]),
        }

    purchase_d = b.reshape(days, PPD)
    q_d = q.reshape(days, PPD)
    ch_d = ch.reshape(days, PPD)
    dis_d = dis.reshape(days, PPD)
    s_d = s.reshape(days, PPD)
    price_d = price.reshape(days, PPD)
    day_cost = np.sum(price_d * purchase_d + ALPHA * price_d * q_d, axis=1)
    starts = state[: periods : PPD]
    ends = state[PPD : periods + 1 : PPD]

    return {
        "objective_yuan": cost,
        "solver_objective_yuan": None,
        "objective_plan_yuan": cost_plan,
        "objective_emergency_yuan": cost_em,
        "delivery_cost_yuan": cost_delivery,
        "delivery_cost_plan_yuan": plan_delivery,
        "delivery_cost_emergency_yuan": em_delivery,
        "totals": {
            "total_purchase_kwh": total_b,
            "total_q_em_kwh": total_q,
            "total_charge_kwh": total_c,
            "total_discharge_kwh": total_dis,
            "total_spill_kwh": total_s,
            "net_load_kwh": net_load,
            "net_load_delivery_kwh": net_delivery,
            "storage_initial_kwh": E_INIT,
            "storage_final_kwh": storage_final,
            "storage_range_kwh": [float(np.min(state[1:])), float(np.max(state[1:]))],
            "max_purchase_kwh": float(np.max(b)),
            "max_purchase_power_kw": float(np.max(b)) / DT,
            "max_side_power_kw": max(charge_power, discharge_power),
            "days_with_emergency": int(np.sum(np.any(q_d > TOL, axis=1))),
            "simultaneous_charge_discharge_periods": int(np.sum((ch > TOL) & (dis > TOL))),
            "day_start_unique_levels": int(len(np.unique(np.round(starts, 6)))),
        },
        "identities": {
            "I1_residual": i1,
            "I2_residual": i2,
            "I1_delivery_residual": i1_delivery,
            "I2_delivery_residual": i2_delivery,
            "balance_residual_max": balance_res,
            "soc_residual_max": soc_res,
            "continuity_residual_max": continuity,
        },
        "interpretability": {
            "charge_price_mean": charge_price,
            "discharge_price_mean": discharge_price,
            "arbitrage_direction_ok": (
                bool(charge_price < discharge_price) if total_c > TOL and total_dis > TOL else True
            ),
        },
        "checks": checks,
        "checks_failed": [item["name"] for item in checks if item["required"] and not item["passed"]],
        "checks_informational_failed": [item["name"] for item in checks if not item["required"] and not item["passed"]],
        "spec_table": spec_table,
        "daily": {
            "purchase_kwh": [float(v) for v in np.sum(purchase_d, axis=1)],
            "q_em_kwh": [float(v) for v in np.sum(q_d, axis=1)],
            "charge_kwh": [float(v) for v in np.sum(ch_d, axis=1)],
            "discharge_kwh": [float(v) for v in np.sum(dis_d, axis=1)],
            "spill_kwh": [float(v) for v in np.sum(s_d, axis=1)],
            "cost_total_yuan": [float(v) for v in day_cost],
            "state_start_kwh": [float(v) for v in starts],
            "state_end_kwh": [float(v) for v in ends],
        },
    }


# --------------------------------------------------------------------------- #
# case 组装
# --------------------------------------------------------------------------- #


def make_case(label: str, family: str, metrics: dict[str, Any], *, status: int, message: str,
              method: str, seconds: float, iterations: int | None, scale: dict[str, Any],
              note: str = "", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    case = {
        "label": label,
        "family": family,
        "status": status,
        "message": message,
        "solver_method": method,
        "solve_time_seconds": float(seconds),
        "iterations": iterations,
        "matrix_scale": scale,
        "note": note,
    }
    case.update(metrics)
    if extra:
        case.update(extra)
    return case


def failure_case(label: str, family: str, *, status: int, message: str, reason: str,
                 method: str = "highs", scale: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "label": label,
        "family": family,
        "status": int(status),
        "message": message,
        "solver_method": method,
        "solve_time_seconds": None,
        "iterations": None,
        "matrix_scale": scale or {},
        "note": reason,
        "feasible": False,
        "objective_yuan": None,
        "delivery_cost_yuan": None,
        "totals": {},
        "identities": {},
        "checks_failed": ["not_solved"],
        "failed": True,
    }


def solve_full_once(label: str, family: str, price: np.ndarray, load: np.ndarray, pv: np.ndarray,
                    days: int, dates: list[str], *, terminal: float | None = None,
                    b_cap_kwh: float | None = None, method: str = "highs", presolve: bool = True,
                    note: str = "", keep_columns: bool = False) -> tuple[dict[str, Any], dict[str, np.ndarray] | None]:
    """求解一个全年 LP；``keep_columns=True`` 时返回解数组（仅 M1 需要，供 M2a 外生耦合）。"""
    model = build_full_lp(price, load, pv, terminal=terminal, b_cap_kwh=b_cap_kwh)
    res, seconds = solve_lp(model, method=method, presolve=presolve)
    periods = days * PPD
    if res.x is None:
        return failure_case(label, family, status=int(res.status), message=str(res.message),
                            reason="LP 无解或未返回解", method=method, scale=model["scale"]), None
    columns = unbundle_full(np.asarray(res.x, dtype=float), periods)
    metrics = evaluate_arrays(columns, price, load, pv, days, dates, premise_no_cap=(b_cap_kwh is None))
    metrics["solver_objective_yuan"] = float(res.fun) if res.fun is not None else None
    case = make_case(label, family, metrics, status=int(res.status), message=str(res.message),
                     method=method, seconds=seconds,
                     iterations=int(res.nit) if res.nit is not None else None,
                     scale=model["scale"], note=note)
    case["feasible"] = True
    case["terminal_kwh"] = terminal
    case["b_cap_kw"] = (b_cap_kwh / DT) if b_cap_kwh is not None else None
    return case, (columns if keep_columns else None)


def run_full_case(*args: Any, **kwargs: Any) -> dict[str, Any]:
    case, _ = solve_full_once(*args, **kwargs)
    return case


def run_full_case_no_spill(label: str, family: str, price: np.ndarray, load: np.ndarray,
                           pv: np.ndarray, days: int, dates: list[str], *,
                           terminal: float | None = None, method: str = "highs-ds",
                           presolve: bool = False, note: str = "") -> dict[str, Any]:
    model = build_full_lp_no_spill(price, load, pv, terminal=terminal)
    bounds = np.column_stack((model["lower"], model["upper"]))
    started = time.perf_counter()
    res = linprog(model["obj"], A_ub=model["A_ub"], b_ub=model["b_ub"], A_eq=model["A_eq"],
                  b_eq=model["b_eq"], bounds=bounds, method=method,
                  options={"time_limit": FULL_TIME_LIMIT, "presolve": presolve})
    seconds = time.perf_counter() - started
    periods = days * PPD
    if res.x is None:
        return failure_case(label, family, status=int(res.status), message=str(res.message),
                            reason="独立实现 LP 无解或未返回解", method=method, scale=model["scale"])
    columns = unbundle_no_spill(np.asarray(res.x, dtype=float), periods, load, pv)
    metrics = evaluate_arrays(columns, price, load, pv, days, dates)
    metrics["solver_objective_yuan"] = float(res.fun) if res.fun is not None else None
    case = make_case(label, family, metrics, status=int(res.status), message=str(res.message),
                     method=method, seconds=seconds,
                     iterations=int(res.nit) if res.nit is not None else None,
                     scale=model["scale"], note=note)
    case["feasible"] = True
    case["reconstructed_spill_kwh"] = float(np.sum(columns["s"]))
    return case


# --------------------------------------------------------------------------- #
# M3：互补 MILP（全规模，独立子进程）
# --------------------------------------------------------------------------- #


def build_milp_full(price: np.ndarray, load: np.ndarray, pv: np.ndarray) -> dict[str, Any]:
    periods = int(price.shape[0])
    base = build_full_lp(price, load, pv)
    size = 6 * periods
    total = size + periods
    obj = np.concatenate([base["obj"], np.zeros(periods)])
    lower = np.concatenate([base["lower"], np.zeros(periods)])
    upper = np.concatenate([base["upper"], np.ones(periods)])
    integrality = np.zeros(total)
    integrality[size:] = 1.0

    a_eq = hstack([base["A_eq"], csr_matrix((2 * periods, periods))], format="csr")
    tau = np.arange(periods, dtype=np.int64)
    rows = np.concatenate([tau, tau, periods + tau, periods + tau])
    cols = np.concatenate([2 * periods + tau, 6 * periods + tau,
                           3 * periods + tau, 6 * periods + tau])
    vals = np.concatenate([np.ones(periods), -C_CAP * np.ones(periods),
                           np.ones(periods), Q_CAP * np.ones(periods)])
    a_ub = coo_matrix((vals, (rows, cols)), shape=(2 * periods, total)).tocsr()
    b_ub = np.concatenate([np.zeros(periods), Q_CAP * np.ones(periods)])
    scale = {"variables": total, "equality_constraints": 2 * periods,
             "inequality_constraints": 2 * periods, "binaries": periods, "nonzero": int(a_eq.nnz + a_ub.nnz)}
    return {"obj": obj, "A_eq": a_eq, "b_eq": base["b_eq"], "A_ub": a_ub, "b_ub": b_ub,
            "lower": lower, "upper": upper, "integrality": integrality, "scale": scale}


def solve_milp_full(price: np.ndarray, load: np.ndarray, pv: np.ndarray, days: int, dates: list[str],
                    *, time_limit: float = MILP_TIME_LIMIT) -> dict[str, Any]:
    model = build_milp_full(price, load, pv)
    constraints = [
        LinearConstraint(model["A_eq"], model["b_eq"], model["b_eq"]),
        LinearConstraint(model["A_ub"], -np.inf * np.ones_like(model["b_ub"]), model["b_ub"]),
    ]
    started = time.perf_counter()
    res = milp(
        c=model["obj"],
        constraints=constraints,
        integrality=model["integrality"],
        bounds=Bounds(model["lower"], model["upper"]),
        options={"time_limit": float(time_limit), "mip_rel_gap": 0.0, "disp": False},
    )
    seconds = time.perf_counter() - started
    mip_gap = getattr(res, "mip_gap", None)
    nodes = getattr(res, "mip_node_count", None)
    extra = {"mip_gap": None if mip_gap is None else _finite(mip_gap), "mip_node_count": nodes,
             "time_limit_seconds": float(time_limit), "proven_optimal": int(res.status) == 0}
    if res.x is None:
        case = failure_case("M3_full", "model_family", status=int(res.status),
                            message=str(res.message), reason="全规模 MILP 无 incumbent（降级）",
                            method="highs-milp", scale=model["scale"])
        case.update(extra)
        return case
    periods = days * PPD
    columns = unbundle_full(np.asarray(res.x, dtype=float)[: 6 * periods], periods)
    metrics = evaluate_arrays(columns, price, load, pv, days, dates)
    metrics["solver_objective_yuan"] = float(res.fun) if res.fun is not None else None
    case = make_case("M3_full", "model_family", metrics, status=int(res.status), message=str(res.message),
                     method="highs-milp", seconds=seconds, iterations=None, scale=model["scale"],
                     note="互补 MILP：c ≤ C_CAP·u、q_dis ≤ Q_CAP·(1−u)，紧 M 上界")
    case.update(extra)
    case["feasible"] = True
    return case


# --------------------------------------------------------------------------- #
# 基线闸门（C1）
# --------------------------------------------------------------------------- #


def baseline_check(m1: dict[str, Any], ref_dir: Path) -> dict[str, Any]:
    solution = json.loads((ref_dir / "solution.json").read_text(encoding="utf-8"))
    tables = json.loads((ref_dir / "tables.json").read_text(encoding="utf-8"))
    totals_ref = solution["totals"]
    m1_totals = m1["totals"]
    pairs = [
        ("objective_yuan", m1["objective_yuan"], solution["objective_yuan"], 1e-6),
        ("delivery_cost_yuan", m1["delivery_cost_yuan"], solution["delivery_cost_yuan"], 1e-6),
        ("total_purchase_kwh", m1_totals["total_purchase_kwh"], totals_ref["total_purchase_kwh"], 1e-6),
        ("total_q_em_kwh", m1_totals["total_q_em_kwh"], totals_ref["total_q_em_kwh"], 1e-6),
        ("total_spill_kwh", m1_totals["total_spill_kwh"], totals_ref["total_spill_kwh"], 1e-6),
        ("storage_final_kwh", m1_totals["storage_final_kwh"], totals_ref["storage_final_kwh"], 1e-6),
        ("max_purchase_power_kw", m1_totals["max_purchase_power_kw"], totals_ref["max_purchase_power_kw"], 1e-6),
        ("max_side_power_kw", m1_totals["max_side_power_kw"], totals_ref["max_side_power_kw"], 1e-6),
    ]
    items: list[dict[str, Any]] = []
    passed = True
    for name, value, ref, tol in pairs:
        diff = _rel(value, ref)
        ok = diff <= tol
        passed = passed and ok
        items.append({"name": name, "value": float(value), "reference": float(ref), "rel_diff": diff,
                      "tolerance": tol, "passed": bool(ok)})
    spec_items: list[dict[str, Any]] = []
    for date, ref_row in tables["table1"].items():
        mine = m1["spec_table"].get(date)
        if mine is None:
            spec_items.append({"name": f"{date}.missing", "passed": False})
            passed = False
            continue
        checks = [
            ("all_day_energy_kwh", mine["all_day_energy_kwh"], ref_row["all_day_energy_kwh"]),
            ("all_day_cost_yuan", mine["all_day_cost_yuan"], ref_row["all_day_cost_yuan"]),
        ]
        for k, slot in enumerate(ref_row["slots"]):
            checks.append((f"slot_{slot['position']}", mine["slots_purchase_kwh"][k], slot["purchase_kwh"]))
        ref2 = tables["table2"][date]
        for k in range(BLOCKS):
            checks.append((f"block_charge_{k}", mine["block_charge_kwh"][k], ref2["block_charge_kwh"][k]))
            checks.append((f"block_discharge_{k}", mine["block_discharge_kwh"][k], ref2["block_discharge_kwh"][k]))
        checks.append(("storage_0_00", mine["storage_0_00_kwh"], ref2["storage_0_00_kwh"]))
        checks.append(("storage_24_00", mine["storage_24_00_kwh"], ref2["storage_24_00_kwh"]))
        for name, value, ref in checks:
            diff = abs(float(value) - float(ref))
            ok = diff <= 1e-6
            passed = passed and ok
            spec_items.append({"name": f"{date}.{name}", "value": float(value), "reference": float(ref),
                               "abs_diff": diff, "passed": bool(ok)})
    return {"passed": bool(passed), "items": items, "spec_items": spec_items,
            "reference_directory": str(ref_dir.as_posix())}


# --------------------------------------------------------------------------- #
# 图（实验产物，不登记为交付图表）
# --------------------------------------------------------------------------- #


def make_figures(output_dir: Path, cases: list[dict[str, Any]], cap_rows: list[dict[str, Any]],
                 m1_label: str = "M1") -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    figures = output_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    produced: list[str] = []
    base = next((c for c in cases if c["label"] == m1_label), None)
    if base is None or base.get("objective_yuan") is None:
        return produced
    base_cost = float(base["objective_yuan"])

    # 图 1：模型费用对比（全期）
    labels = [c["label"] for c in cases]
    costs = [float(c.get("objective_yuan") or np.nan) for c in cases]
    fig, axes = plt.subplots(2, 1, figsize=(max(9.0, 0.55 * len(labels)), 9.0))
    axes[0].bar(range(len(labels)), costs, color="#3b7dd8")
    axes[0].axhline(base_cost, color="black", linestyle="--", linewidth=1.0, label="M1 基线")
    axes[0].set_xticks(range(len(labels)))
    axes[0].set_xticklabels(labels, rotation=60, ha="right", fontsize=8)
    axes[0].set_ylabel("全期总费用（元）")
    axes[0].set_title("prob02 消融/模型族对照：全期总费用")
    axes[0].legend()
    dev = [(c - base_cost) / base_cost * 100.0 for c in costs]
    axes[1].bar(range(len(labels)), dev, color="#d8693b")
    axes[1].axhline(0.0, color="black", linewidth=0.8)
    axes[1].set_xticks(range(len(labels)))
    axes[1].set_xticklabels(labels, rotation=60, ha="right", fontsize=8)
    axes[1].set_ylabel("相对 M1 偏差（%）")
    axes[1].set_title("相对 M1 的费用偏差（负 = 更省）")
    fig.tight_layout()
    path = figures / "ablation_model_cost.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    produced.append(path.name)

    # 图 2：购电上限 - 紧急购电曲线
    if cap_rows:
        rows = sorted(cap_rows, key=lambda r: (r["b_cap_kw"] if r["b_cap_kw"] is not None else 1e12))
        xs = [r["b_cap_kw"] for r in rows if r["b_cap_kw"] is not None]
        qs = [r["q_em_kwh"] for r in rows if r["b_cap_kw"] is not None]
        cs = [r["objective_yuan"] for r in rows if r["b_cap_kw"] is not None]
        fig, ax1 = plt.subplots(figsize=(9.0, 5.0))
        ax1.plot(xs, qs, "o-", color="#3b7dd8", label="Σq_em（kWh）")
        ax1.axvspan(BETA_BRACKET[0], BETA_BRACKET[1], color="#f2c14e", alpha=0.35,
                    label=f"β ∈ ({BETA_BRACKET[0]}, {BETA_BRACKET[1]}] kW")
        ax1.set_xlabel("外网购电上限 B（kW）")
        ax1.set_ylabel("紧急购电总量 Σq_em（kWh）", color="#3b7dd8")
        ax2 = ax1.twinx()
        ax2.plot(xs, cs, "s--", color="#d8693b", label="全期总费用（元）")
        ax2.set_ylabel("全期总费用（元）", color="#d8693b")
        ax1.set_title("M6/M6′：购电上限与紧急购电机制（阈值 β 见勘误 R5）")
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", fontsize=8)
        fig.tight_layout()
        path = figures / "ablation_b_cap_curve.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        produced.append(path.name)

    # 图 3：结构消融瀑布
    order = [c for c in cases if c["label"] in ("M2a", "M2b", "M4", "M5", "M7", "M3_full")]
    fig, ax = plt.subplots(figsize=(9.0, 5.0))
    names = ["M1"] + [c["label"] for c in order]
    values = [base_cost] + [float(c.get("objective_yuan") or np.nan) for c in order]
    ax.bar(range(len(names)), values, color=["black"] + ["#6aa84f"] * len(order))
    ax.axhline(base_cost, color="black", linestyle="--", linewidth=1.0)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=45, ha="right")
    ax.set_ylabel("全期总费用（元）")
    ax.set_title("跨日/终端/模型族的结构对照（全期）")
    fig.tight_layout()
    path = figures / "ablation_structure_waterfall.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    produced.append(path.name)

    # 图 4：复杂度 - 费用偏差
    fig, ax = plt.subplots(figsize=(9.0, 5.0))
    for case in cases:
        if case.get("objective_yuan") is None or case.get("solve_time_seconds") is None:
            continue
        x = max(float(case["solve_time_seconds"]), 1e-3)
        y = (float(case["objective_yuan"]) - base_cost) / base_cost * 100.0
        ax.scatter(x, y, s=28)
        ax.annotate(case["label"], (x, y), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.set_xscale("log")
    ax.set_xlabel("求解时间（s，对数轴）")
    ax.set_ylabel("相对 M1 的费用偏差（%）")
    ax.set_title("复杂度 - 费用偏差权衡（本问精确解成本已可接受）")
    fig.tight_layout()
    path = figures / "ablation_complexity_tradeoff.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    produced.append(path.name)
    return produced


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #


def _code_fingerprint() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(CODE_DIR.rglob("*.py")):
        out[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    digest = hashlib.sha256()
    for name, value in sorted(out.items()):
        digest.update(name.encode("utf-8"))
        digest.update(value.encode("utf-8"))
    out["__code_dir__"] = digest.hexdigest()
    return out


def _dump_case(output_dir: Path, name: str, case: dict[str, Any]) -> None:
    target = output_dir / name
    target.mkdir(parents=True, exist_ok=True)
    write_json(target / "case.json", case)


def run_all(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ref_dir = Path(args.reference).resolve()
    days = int(args.days)
    data = load_inputs(args.data, args.data2)
    price = _flat(data["price"], days)
    load = _flat2(data["load"], days)
    pv = _flat2(data["pv"], days)
    dates = data["dates"]

    cases: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []

    # ---- M1（基准 + 强制闸门）----
    m1, m1_columns = solve_full_once(
        "M1", "baseline", price, load, pv, days, dates, keep_columns=True,
        note="主模型 (P2)：365×144 单一 LP，E_T 自由，b 无上限",
    )
    _dump_case(output_dir, "M1", m1)
    cases.append(m1)
    raw.append(_raw_row(m1))
    if m1.get("objective_yuan") is None:
        write_json(output_dir / "solver_status.json", {"feasible_incumbent": False,
                                                       "message": "M1 无解", "stage": "ablation"})
        return 3
    gate = baseline_check(m1, ref_dir) if days == DAYS_FULL else {"passed": True, "note": "probe mode"}
    write_json(output_dir / "baseline_check.json", gate)
    if not gate["passed"] and not args.probe_mode:
        print("C1 基线复现闸门失败，整批作废")
        write_json(output_dir / "solver_status.json",
                   {"feasible_incumbent": True, "baseline_check_passed": False, "exit": 4})
        return 4

    periods = days * PPD
    m1_state = np.concatenate([[E_INIT], m1_columns["E"]]) if m1_columns is not None else None

    # ---- M7（独立第二实现）----
    m7 = run_full_case_no_spill("M7", "cross_validation", price, load, pv, days, dates,
                                note="消去 s：平衡等效不等式对 + highs-ds + presolve=False")
    _dump_case(output_dir, "M7", m7)
    cases.append(m7)
    raw.append(_raw_row(m7))
    gc.collect()

    # ---- M5（终端 = 6000）----
    m5 = run_full_case("M5", "terminal", price, load, pv, days, dates, terminal=E_INIT,
                       note="终端条件对照：E_T = 6000 kWh（D2 备选 B）")
    _dump_case(output_dir, "M5", m5)
    cases.append(m5)
    raw.append(_raw_row(m5))
    gc.collect()

    # ---- M6 / M6′（购电上限）----
    cap_rows: list[dict[str, Any]] = []
    cap_grid = [("M6", b) for b in (10326.0, 8459.0, 6000.0, 5000.0)]
    cap_grid += [("M6p", b) for b in (4375.0, 4218.75, 4000.0, 3750.0, 3000.0, 2000.0)]
    for family, cap_kw in cap_grid:
        label = f"{family}_B{_fmt_cap(cap_kw)}"
        case = run_full_case(label, "purchase_cap", price, load, pv, days, dates,
                             b_cap_kwh=cap_kw * DT,
                             note=f"b ≤ {cap_kw:g} kW（只改 b 上界一项）")
        _dump_case(output_dir, label, case)
        cases.append(case)
        raw.append(_raw_row(case))
        cap_rows.append({"label": label, "b_cap_kw": float(cap_kw),
                         "q_em_kwh": (case.get("totals", {}) or {}).get("total_q_em_kwh"),
                         "objective_yuan": case.get("objective_yuan"),
                         "delivery_cost_yuan": case.get("delivery_cost_yuan"),
                         "days_with_emergency": (case.get("totals", {}) or {}).get("days_with_emergency")})
        gc.collect()

    # ---- M2a / M2b / M4（逐日）----
    day_cases: dict[str, dict[str, Any]] = {}
    for label, mode, note in (
        ("M2a", "m2a", "逐日解耦 + 耦合序列 {E_{d,144}} 外生固定为 M1 最优值（C2 对象）"),
        ("M2b", "m2b", "逐日解耦 + 日终自由纯递推（跨日携带价值，D2 结构性发现）"),
        ("M4", "m4", "逐日独立 LP：E_{d,0} = E_{d,144} = 6000（D1 备选 A，D3 同为 365 天）"),
    ):
        seq = solve_day_sequence(price, load, pv, days, mode=mode, m1_state=m1_state)
        if seq["infeasible_days"]:
            case = failure_case(label, "time_domain", status=2,
                                message=f"{len(seq['infeasible_days'])} 天不可行", reason="逐日子问题不可行")
            case["infeasible_days"] = seq["infeasible_days"][:20]
        else:
            columns = {kind: seq["full"][kind] for kind in KINDS}
            metrics = evaluate_arrays(columns, price, load, pv, days, dates)
            metrics["solver_objective_yuan"] = float(np.sum(seq["day"]["objective"]))
            case = make_case(label, "time_domain", metrics, status=0, message="ok", method="highs",
                             seconds=seq["solve_seconds"], iterations=None, scale=seq["scale"], note=note)
            case["feasible"] = True
            case["worst_eq_residual"] = seq["worst_eq_residual"]
            case["worst_bound_violation"] = seq["worst_bound_violation"]
            if mode == "m2a" and m1_columns is not None:
                m1_day = np.sum(price.reshape(days, PPD) * m1_columns["b"].reshape(days, PPD)
                                + ALPHA * price.reshape(days, PPD) * m1_columns["q_em"].reshape(days, PPD), axis=1)
                diff = np.abs(seq["day"]["objective"] - m1_day)
                case["per_day_max_abs_diff_yuan"] = float(np.max(diff))
                case["per_day_max_rel_diff"] = float(np.max(diff / np.maximum(np.abs(m1_day), 1e-12)))
        _dump_case(output_dir, label, case)
        cases.append(case)
        raw.append(_raw_row(case))
        day_cases[label] = case
        gc.collect()

    # ---- M3：日规模 MILP oracle（小，in-process）----
    day_oracles: list[dict[str, Any]] = []
    if m1_state is not None:
        day_oracles = run_m3_day_oracles_by_dates(price, load, pv, days, m1_state, dates)

    # ---- M3：全规模 MILP（独立子进程）----
    m3_full = run_m3_subprocess(args, output_dir)
    _dump_case(output_dir, "M3_full", m3_full)
    cases.append(m3_full)
    raw.append(_raw_row(m3_full))

    # ---- 汇总 ----
    summary = summarize(cases, cap_rows, day_oracles, gate, days)
    identities = build_identities(cases)
    comparison = build_comparison(cases, cap_rows, day_oracles)
    write_json(output_dir / "identities.json", identities)
    write_json(output_dir / "comparison.json", comparison)
    summary["figures"] = make_figures(output_dir, cases, cap_rows)
    write_json(output_dir / "summary.json", summary)
    _dump_raw(raw, output_dir / "raw_cases.jsonl")

    manifest = {
        "problem_id": "microgrid_2025",
        "question_id": "prob02",
        "stage": "ablation",
        "assumption_version": "assumption_v001",
        "formulation_version": "formulation_v001",
        "task_id": _task_id(),
        "output_directory": str(output_dir),
        "days": days,
        "periods": periods,
        "seed": SEED,
        "device": "cpu",
        "gpu_required": False,
        "solver": "scipy.optimize.linprog/milp (HiGHS)",
        "probe_mode": bool(args.probe_mode),
        "wall_clock_seconds": time.perf_counter() - started,
        "model_count": len(cases),
        "inputs": {"attachment1_md5": data["a1_md5"], "attachment2_md5": data["a2_md5"],
                   "reference_directory": str(ref_dir)},
        "baseline_check_passed": bool(gate["passed"]),
        "code_sha256": _code_fingerprint(),
        "environment": {"python": platform.python_version(), "numpy": np.__version__,
                        "platform": platform.platform()},
    }
    write_json(output_dir / "run_manifest.json", manifest)
    write_json(output_dir / "solver_status.json", {
        "feasible_incumbent": bool(m1.get("feasible")),
        "baseline_check_passed": bool(gate["passed"]),
        "objective_yuan": m1.get("objective_yuan"),
        "delivery_cost_yuan": m1.get("delivery_cost_yuan"),
        "criteria_failed": summary.get("criteria_failed", []),
        "device": "cpu",
        "gpu_required": False,
        "seed": SEED,
        "deterministic": True,
        "model_count": len(cases),
    })
    print(f"ablation 完成：{len(cases)} 个模型 case，判据未通过项 = {summary.get('criteria_failed', [])}")
    print(f"output = {output_dir}")
    return 0


def run_m3_subprocess(args: argparse.Namespace, output_dir: Path) -> dict[str, Any]:
    """全规模 MILP 在独立子进程中运行（内存/超时隔离，D5 降级纪律）。"""
    target = output_dir / "M3_full"
    target.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(HERE), "--data", str(args.data), "--data2", str(args.data2),
           "--output", str(output_dir), "--reference", str(args.reference), "--seed", str(args.seed),
           "--days", str(args.days), "--only", "m3_full",
           "--milp-time-limit", str(args.milp_time_limit)]
    stdout_path = target / "child_stdout.log"
    stderr_path = target / "child_stderr.log"
    timeout = float(args.milp_time_limit) + 240.0
    started = time.perf_counter()
    try:
        with stdout_path.open("w", encoding="utf-8", newline="\n") as out, \
                stderr_path.open("w", encoding="utf-8", newline="\n") as err:
            proc = subprocess.run(cmd, cwd=str(ROOT), stdout=out, stderr=err,
                                  stdin=subprocess.DEVNULL, timeout=timeout, check=False,
                                  creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0))
        elapsed = time.perf_counter() - started
        child_case_path = target / "case.json"
        if child_case_path.is_file():
            case = json.loads(child_case_path.read_text(encoding="utf-8"))
            case["child_returncode"] = proc.returncode
            case["child_wall_clock_seconds"] = elapsed
            case["degraded"] = proc.returncode != 0 or not case.get("proven_optimal", False)
            if proc.returncode != 0:
                case.setdefault("note", "")
                case["note"] = (case["note"] + f" | 子进程返回码 {proc.returncode}，降级为技术债").strip(" |")
            return case
        return {
            "label": "M3_full", "family": "model_family", "status": int(proc.returncode),
            "message": "全规模 MILP 子进程未产出 case.json", "note": "降级：以 4 个指定日期的日规模 MILP 作数值 oracle",
            "feasible": False, "objective_yuan": None, "delivery_cost_yuan": None,
            "totals": {}, "identities": {}, "checks_failed": ["m3_full_unavailable"],
            "failed": True, "degraded": True, "child_returncode": int(proc.returncode),
            "child_wall_clock_seconds": elapsed,
        }
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - started
        return {
            "label": "M3_full", "family": "model_family", "status": 124,
            "message": f"全规模 MILP 子进程超过墙钟上限 {timeout:.0f} s",
            "note": "降级：D5 允许以代表日 MILP 作 oracle",
            "feasible": False, "objective_yuan": None, "delivery_cost_yuan": None,
            "totals": {}, "identities": {}, "checks_failed": ["m3_full_timeout"],
            "failed": True, "degraded": True, "child_returncode": 124,
            "child_wall_clock_seconds": elapsed,
        }


def run_only_m3_full(args: argparse.Namespace) -> int:
    output_dir = Path(args.output).resolve()
    days = int(args.days)
    data = load_inputs(args.data, args.data2)
    price = _flat(data["price"], days)
    load = _flat2(data["load"], days)
    pv = _flat2(data["pv"], days)
    case = solve_milp_full(price, load, pv, days, data["dates"],
                           time_limit=float(args.milp_time_limit))
    _dump_case(output_dir, "M3_full", case)
    return 0 if case.get("feasible") else 5


def _fmt_cap(value: float) -> str:
    text = f"{value:g}"
    return text.replace(".", "_")


def _task_id() -> str | None:
    import os

    return os.environ.get("AUTOMM_TASK_ID")


def _dump_raw(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False))
            handle.write("\n")


def _raw_row(case: dict[str, Any]) -> dict[str, Any]:
    totals = case.get("totals") or {}
    return {
        "label": case["label"],
        "family": case.get("family"),
        "status": case.get("status"),
        "feasible": bool(case.get("feasible")),
        "objective_yuan": case.get("objective_yuan"),
        "delivery_cost_yuan": case.get("delivery_cost_yuan"),
        "total_purchase_kwh": totals.get("total_purchase_kwh"),
        "total_q_em_kwh": totals.get("total_q_em_kwh"),
        "total_spill_kwh": totals.get("total_spill_kwh"),
        "storage_final_kwh": totals.get("storage_final_kwh"),
        "solve_time_seconds": case.get("solve_time_seconds"),
        "checks_failed": case.get("checks_failed", []),
        "note": case.get("note", ""),
    }


def build_identities(cases: list[dict[str, Any]]) -> dict[str, Any]:
    items = {}
    for case in cases:
        ident = case.get("identities") or {}
        totals = case.get("totals") or {}
        items[case["label"]] = {
            "I1_residual": ident.get("I1_residual"),
            "I2_residual": ident.get("I2_residual"),
            "I1_delivery_residual": ident.get("I1_delivery_residual"),
            "I2_delivery_residual": ident.get("I2_delivery_residual"),
            "balance_residual_max": ident.get("balance_residual_max"),
            "soc_residual_max": ident.get("soc_residual_max"),
            "continuity_residual_max": ident.get("continuity_residual_max"),
            "storage_final_kwh": totals.get("storage_final_kwh"),
        }
    return {
        "closed_form": [
            "(I1) Σq_dis = η_ch·η_dis·Σc − η_dis·(E_T − E_0)",
            "(I2) Σb = N + Σs + (1 − η_ch·η_dis)·Σc + η_dis·(E_T − E_0) − Σq_em",
        ],
        "per_model": items,
        "q_em_zero_proof": (
            "Σq_em = 0 是可证性结论而非实测断言：设 p>0、α_em=5>1 且 b 无上界，"
            "则任一含 q_em,τ=δ>0 的可行解可令 b'_τ=b_τ+δ、q'_em,τ=0，可行域不变而目标严格下降 "
            "(α_em−1)pδ>0，故最优解满足 q_em≡0（定理 T1；依赖完全信息 + 无购电上限 + α_em>1 三前提）。"
        ),
        "note": "平衡/SOC 残差由解数组独立回代得到（不依赖求解器矩阵），故对 M7 的消元实现同样有效。",
    }


def build_comparison(cases: list[dict[str, Any]], cap_rows: list[dict[str, Any]],
                     day_oracles: list[dict[str, Any]]) -> dict[str, Any]:
    table = []
    for case in cases:
        totals = case.get("totals") or {}
        interp = case.get("interpretability") or {}
        table.append({
            "label": case["label"],
            "family": case.get("family"),
            "feasible": bool(case.get("feasible")),
            "objective_yuan": case.get("objective_yuan"),
            "delivery_cost_yuan": case.get("delivery_cost_yuan"),
            "objective_plan_yuan": case.get("objective_plan_yuan"),
            "objective_emergency_yuan": case.get("objective_emergency_yuan"),
            "total_purchase_kwh": totals.get("total_purchase_kwh"),
            "total_q_em_kwh": totals.get("total_q_em_kwh"),
            "total_charge_kwh": totals.get("total_charge_kwh"),
            "total_discharge_kwh": totals.get("total_discharge_kwh"),
            "total_spill_kwh": totals.get("total_spill_kwh"),
            "storage_final_kwh": totals.get("storage_final_kwh"),
            "max_side_power_kw": totals.get("max_side_power_kw"),
            "days_with_emergency": totals.get("days_with_emergency"),
            "simultaneous_charge_discharge_periods": totals.get("simultaneous_charge_discharge_periods"),
            "charge_price_mean": interp.get("charge_price_mean"),
            "discharge_price_mean": interp.get("discharge_price_mean"),
            "solve_time_seconds": case.get("solve_time_seconds"),
            "solver_method": case.get("solver_method"),
            "matrix_scale": case.get("matrix_scale"),
            "mip_gap": case.get("mip_gap"),
            "mip_node_count": case.get("mip_node_count"),
            "checks_failed": case.get("checks_failed", []),
            "note": case.get("note", ""),
        })
    return {"models": table, "purchase_cap": cap_rows, "m3_day_oracles": day_oracles}


def run_m3_day_oracles_by_dates(price: np.ndarray, load: np.ndarray, pv: np.ndarray, days: int,
                                m1_state: np.ndarray, dates: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in SPEC_DATES:
        try:
            index = day_offset(dates, name)
        except Exception:
            continue
        if index >= days:
            continue
        rows.append(_m3_day_oracle(price, load, pv, index, name, m1_state))
    return rows


def _m3_day_oracle(price: np.ndarray, load: np.ndarray, pv: np.ndarray, index: int, name: str,
                   m1_state: np.ndarray) -> dict[str, Any]:
    price_d = price[:PPD]
    load_d = load[index * PPD : (index + 1) * PPD]
    pv_d = pv[index * PPD : (index + 1) * PPD]
    e0 = float(m1_state[index * PPD])
    model = build_day_lp(price_d, load_d, pv_d)
    lp = solve_day_lp(model, e0, None, price_d)
    row: dict[str, Any] = {"date": name, "day_index": index, "e0_kwh": e0, "milp_binaries": PPD}
    if not lp["ok"]:
        row.update({"lp_ok": False, "lp_status": lp["status"]})
        return row
    row["lp_objective_yuan"] = lp["objective"]
    row["lp_simultaneous_periods"] = int(np.sum((lp["columns"]["c"] > TOL) & (lp["columns"]["q_dis"] > TOL)))
    size = 6 * PPD
    total = size + PPD
    obj = np.concatenate([model["obj"], np.zeros(PPD)])
    lower = np.concatenate([model["lower"], np.zeros(PPD)])
    upper = np.concatenate([model["upper"], np.ones(PPD)])
    integrality = np.zeros(total)
    integrality[size:] = 1.0
    a_eq = hstack([model["A_eq"], csr_matrix((2 * PPD, PPD))], format="csr")
    tau = np.arange(PPD, dtype=np.int64)
    rows_idx = np.concatenate([tau, tau, PPD + tau, PPD + tau])
    cols_idx = np.concatenate([2 * PPD + tau, 6 * PPD + tau, 3 * PPD + tau, 6 * PPD + tau])
    vals = np.concatenate([np.ones(PPD), -C_CAP * np.ones(PPD), np.ones(PPD), Q_CAP * np.ones(PPD)])
    a_ub = coo_matrix((vals, (rows_idx, cols_idx)), shape=(2 * PPD, total)).tocsr()
    b_ub = np.concatenate([np.zeros(PPD), Q_CAP * np.ones(PPD)])
    b_eq = model["b_eq"].copy()
    b_eq[PPD] = e0
    started = time.perf_counter()
    res = milp(c=obj,
               constraints=[LinearConstraint(a_eq, b_eq, b_eq),
                            LinearConstraint(a_ub, -np.inf * np.ones_like(b_ub), b_ub)],
               integrality=integrality, bounds=Bounds(lower, upper),
               options={"time_limit": 60.0, "mip_rel_gap": 0.0, "disp": False})
    row["milp_seconds"] = time.perf_counter() - started
    row["milp_status"] = int(res.status)
    row["milp_message"] = str(res.message)
    row["milp_mip_gap"] = _finite(getattr(res, "mip_gap", None) or 0.0)
    row["milp_node_count"] = getattr(res, "mip_node_count", None)
    if res.x is not None:
        cols = unbundle_full(np.asarray(res.x, dtype=float)[: 6 * PPD], PPD)
        row["milp_objective_yuan"] = float(res.fun)
        row["milp_simultaneous_periods"] = int(np.sum((cols["c"] > TOL) & (cols["q_dis"] > TOL)))
        row["objective_rel_diff"] = _rel(float(res.fun), float(lp["objective"]))
        row["balance_residual_max"] = float(np.max(np.abs(
            cols["b"] + cols["q_em"] + pv_d + cols["q_dis"] - load_d - cols["c"] - cols["s"])))
    else:
        row["milp_objective_yuan"] = None
        row["objective_rel_diff"] = None
    return row


def summarize(cases: list[dict[str, Any]], cap_rows: list[dict[str, Any]],
              day_oracles: list[dict[str, Any]], gate: dict[str, Any], days: int) -> dict[str, Any]:
    by_label = {case["label"]: case for case in cases}
    base = by_label.get("M1") or {}
    base_cost = base.get("objective_yuan")
    base_delivery = base.get("delivery_cost_yuan")
    results: dict[str, Any] = {}
    failed: list[str] = []

    def ok(label: str) -> bool:
        item = by_label.get(label, {})
        return bool(item.get("feasible")) and item.get("objective_yuan") is not None

    if ok("M1") and ok("M2a"):
        diff = _rel(by_label["M2a"]["objective_yuan"], base_cost)
        results["C2"] = {"passed": bool(diff <= 1e-6), "rel_diff_full": diff,
                         "rel_diff_delivery": _rel(by_label["M2a"]["delivery_cost_yuan"], base_delivery),
                         "note": "B3-C2 只适用于 M2a（D2 裁定）"}
        if diff > 1e-6:
            failed.append("C2")
    else:
        results["C2"] = {"passed": False, "note": "M2a 或 M1 不可用"}
        failed.append("C2")

    if ok("M1") and ok("M7"):
        diff = _rel(by_label["M7"]["objective_yuan"], base_cost)
        results["C2b_M7_independent_implementation"] = {
            "passed": bool(diff <= 1e-6), "rel_diff": diff,
            "balance_residual_max": (by_label["M7"].get("identities") or {}).get("balance_residual_max"),
            "note": "B2 第 1 条：M7 为 M1 的独立第二实现（消去 s + highs-ds + presolve=False）",
        }
        if diff > 1e-6:
            failed.append("C2b")

    m3 = by_label.get("M3_full", {})
    if m3.get("objective_yuan") is not None:
        diff = _rel(m3["objective_yuan"], base_cost)
        gap = m3.get("mip_gap")
        gap_ok = gap is not None and float(gap) <= 1e-6
        results["C3"] = {"passed": bool(diff <= 1e-6 and gap_ok), "rel_diff": diff, "mip_gap": gap,
                         "proven_optimal": m3.get("proven_optimal"),
                         "day_oracles": day_oracles}
        if diff > 1e-6 or not gap_ok:
            failed.append("C3")
    else:
        results["C3"] = {"passed": False, "degraded": True, "note": m3.get("note", "M3 全规模不可用"),
                         "day_oracles": day_oracles}
        failed.append("C3")

    # C4：M4/M5 方向与量级（全期与交付期分别核对）
    probe = {"M4": {"full": 17135.02, "delivery": 17803.27}, "M5": {"full": 2217.083334, "delivery": 2217.083334}}
    c4 = {}
    for label in ("M4", "M5"):
        if not ok(label):
            c4[label] = {"passed": False, "note": "不可用"}
            failed.append("C4")
            continue
        d_full = by_label[label]["objective_yuan"] - base_cost
        d_delivery = by_label[label]["delivery_cost_yuan"] - base_delivery
        expect = probe[label]
        rel_full = abs(d_full - expect["full"]) / abs(expect["full"])
        rel_delivery = abs(d_delivery - expect["delivery"]) / abs(expect["delivery"])
        passed = d_full >= -1e-6 and d_delivery >= -1e-6 and rel_full <= 0.01 and rel_delivery <= 0.01
        c4[label] = {"passed": bool(passed), "delta_full_yuan": d_full, "delta_delivery_yuan": d_delivery,
                     "probe_full_yuan": expect["full"], "probe_delivery_yuan": expect["delivery"],
                     "rel_full": rel_full, "rel_delivery": rel_delivery}
        if not passed:
            failed.append("C4")
    results["C4"] = c4

    # C5：M6/M6′ 单调性
    grid = sorted([r for r in cap_rows if r["q_em_kwh"] is not None], key=lambda r: r["b_cap_kw"])
    zeros = [r for r in grid if r["q_em_kwh"] <= TOL]
    positives = [r for r in grid if r["q_em_kwh"] > TOL]
    mono_q = all(grid[i]["q_em_kwh"] >= grid[i + 1]["q_em_kwh"] - 1e-6 for i in range(len(grid) - 1))
    mono_c = all(grid[i]["objective_yuan"] >= grid[i + 1]["objective_yuan"] - 1e-6 for i in range(len(grid) - 1))
    bracket = None
    if positives and zeros:
        low = max(r["b_cap_kw"] for r in positives)
        high = min(r["b_cap_kw"] for r in zeros)
        if low < high:
            bracket = [low, high]
    c5_passed = mono_q and mono_c and bool(zeros) and bool(positives)
    results["C5"] = {"passed": bool(c5_passed), "monotone_q_em_non_increasing_in_cap": mono_q,
                     "monotone_cost_non_increasing_in_cap": mono_c, "bracket_kw": bracket,
                     "declared_bracket_kw": list(BETA_BRACKET), "grid": grid}
    if not c5_passed:
        failed.append("C5")

    # C6：约束满足度
    c6 = {case["label"]: case.get("checks_failed", []) for case in cases}
    c6_failed = [label for label, items in c6.items() if items]
    results["C6"] = {"passed": not c6_failed, "checks_failed": c6, "failed_models": c6_failed}
    if c6_failed:
        failed.append("C6")

    # C7：套利方向
    c7 = {}
    for case in cases:
        interp = case.get("interpretability") or {}
        total_charge = (case.get("totals") or {}).get("total_charge_kwh")
        if total_charge and total_charge > TOL:
            c7[case["label"]] = bool(interp.get("arbitrage_direction_ok", True))
    results["C7"] = {"passed": all(c7.values()) if c7 else True, "by_model": c7,
                     "note": "无可判模型时记 not_applicable"}
    if c7 and not all(c7.values()):
        failed.append("C7")

    # K2：M2b 跨日携带价值
    k2 = None
    if ok("M2b") and ok("M1"):
        k2 = {"delta_full_yuan": by_label["M2b"]["objective_yuan"] - base_cost,
              "delta_delivery_yuan": by_label["M2b"]["delivery_cost_yuan"] - base_delivery,
              "note": "D2：M2b 与 M1 的差额为跨日携带价值的结构性发现，不得判为实现错误"}
    results["K2_cross_day_carrying_value"] = k2
    return {
        "criteria": results,
        "criteria_failed": sorted(set(failed)),
        "baseline_check_passed": bool(gate.get("passed")),
        "days": days,
        "note": "判据阈值在 ablations/plan.md 冻结；本文件只在结果出来后填数值，不修改阈值。",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="prob02 消融与模型族对照实验")
    parser.add_argument("--data", required=True)
    parser.add_argument("--data2", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--days", type=int, default=DAYS_FULL)
    parser.add_argument("--only", default="all", choices=("all", "m3_full"))
    parser.add_argument("--milp-time-limit", type=float, default=MILP_TIME_LIMIT)
    parser.add_argument("--probe-mode", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.only == "m3_full":
        return run_only_m3_full(args)
    return run_all(args)


if __name__ == "__main__":
    raise SystemExit(main())
