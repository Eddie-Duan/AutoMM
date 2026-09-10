# -*- coding: utf-8 -*-
"""prob01 消融与模型族对照实验（隔离 task 入口）。

实验设计与预注册判据见同版本 ``ablations/plan.md``（先于本代码运行写定，事后不得修改）。
本脚本只读 ``data/``（经 ``--input``）与 accepted 产物（``code/``、``results/.../run002/solution.json``），
向 ``--output`` 写：

- ``baseline_check.json``  accepted 基线复现闸门（C1，与 run002 逐项对比）
- ``solver_status.json``   求解器/环境/可行解标记（供 task_worker 判定 feasible_incumbent）
- ``comparison.json``      模型 × 指标对比表（A1 的 A–F 全条目 + A2 五维度）
- ``dp_granularity.json``  SOC 离散化 DP 的粒度-偏差曲线原始数据
- ``raw_cases.jsonl``      每个对照 case 一行（失败 case 保留、不删除）
- ``summary.json``         判据 C1–C7 判定 + 结论 K1–K3 + 技术债
- ``figures/*.png``        2–4 张图（费用对比、DP 粒度-偏差、消融瀑布、复杂度-费用）
- ``<case>/case.json``     每个对照独立子目录（原始样本与汇总分开，A3 输出隔离）
- ``run_manifest.json``    追踪信息（task_id、代码 sha256、输入 md5、seed、计数、耗时）

口径与 accepted 版本一致：``min Σ p_t·b_t``（元，不乘 Δt，D9）、``E_t=E_{t-1}+ηc_t−q_t/η``、
口径丙 ``c_t≤P_max·Δt``、``q_t≤P_max·Δt·η_dis``、``E_0=E_144=E_init``；团队勘误 E1–E3 遵循。
本脚本不修改任何原始数据与上游产物；全部对照数值只写入本阶段目录。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

HERE = Path(__file__).resolve()
VERSION_DIR = HERE.parents[2]                       # .../assumption_v003
ACCEPTED_CODE = VERSION_DIR / "code"
RUN002_DIR = VERSION_DIR / "results" / "prob01_v003_f001_run002"
ROOT = HERE.parents[7]
if str(ACCEPTED_CODE) not in sys.path:
    sys.path.insert(0, str(ACCEPTED_CODE))

from prob01_io import read_attachment1, write_json  # noqa: E402

DT = 1.0 / 6.0
ETA_CH = 0.9
ETA_DIS = 0.9
E_INIT = 6000.0
E_MIN = 1200.0
E_MAX = 10800.0
P_MAX = 5000.0
C_CAP = P_MAX * DT                    # 833.3333 kWh（并网点侧紧，accepted）
Q_CAP = P_MAX * DT * ETA_DIS          # 750.0000 kWh（电池侧紧，D10 口径丙 / E1）
TOL = 1e-6
SEED = 20260910
TRANSPORT_FLOOR = 1.0 - ETA_CH * ETA_DIS   # 0.19：db/dc

TABLE1_POSITIONS = (60, 72, 84, 96, 108, 120)   # 1-based，表 1 六个时段
BLOCK = 24                                        # 表 2 每段时段数
DP_STEPS = (400.0, 200.0, 100.0, 50.0)

CASE_FAMILIES = (
    "A_baseline_LP",
    "B_milp",
    "C_dp",
    "D_no_periodic",
    "E_no_spill",
    "F_eta_placement",
)


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #


def _finite(value: Any) -> Any:
    """把 NaN/Inf 转成 None，避免把非有限值伪装成合法结果。"""
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(item) for item in value]
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _blocks(values: np.ndarray, periods: int) -> list[float]:
    return [round(float(np.sum(values[k * BLOCK : (k + 1) * BLOCK])), 6) for k in range(periods // BLOCK)]


def _table1(series: np.ndarray) -> list[float]:
    return [round(float(series[position - 1]), 6) for position in TABLE1_POSITIONS]


# --------------------------------------------------------------------------- #
# 模型构造：通用 LP（A / D / E / F 共用）
# --------------------------------------------------------------------------- #


def build_model(
    *,
    price: np.ndarray,
    load_energy: np.ndarray,
    pv_energy: np.ndarray,
    eta_ch: float = ETA_CH,
    eta_dis: float = ETA_DIS,
    c_cap: float = C_CAP,
    q_cap: float = Q_CAP,
    e_init: float = E_INIT,
    e_min: float = E_MIN,
    e_max: float = E_MAX,
    free_final: bool = False,
    drop_spill: bool = False,
) -> dict[str, Any]:
    """构造与 accepted formulation_v001 §3.8 对应的 LP（可选 D/E 变体）。"""
    periods = int(price.shape[0])
    kinds = ("b", "c", "q", "E") if drop_spill else ("b", "c", "q", "s", "E")
    size = len(kinds) * periods
    index = lambda kind, t: kinds.index(kind) * periods + t  # noqa: E731

    objective = np.zeros(size)
    for t in range(periods):
        objective[index("b", t)] = price[t]

    rows: list[np.ndarray] = []
    rhs: list[float] = []
    for t in range(periods):                                  # (R2) SOC 动态
        row = np.zeros(size)
        row[index("E", t)] = 1.0
        if t > 0:
            row[index("E", t - 1)] = -1.0
        row[index("c", t)] = -eta_ch
        row[index("q", t)] = 1.0 / eta_dis
        rows.append(row)
        rhs.append(e_init if t == 0 else 0.0)
    a_eq = np.array(rows, dtype=float)
    b_eq = np.array(rhs, dtype=float)

    if not drop_spill:                                        # (R1) 等式平衡
        rows = []
        rhs = []
        for t in range(periods):
            row = np.zeros(size)
            row[index("b", t)] = 1.0
            row[index("q", t)] = 1.0
            row[index("c", t)] = -1.0
            row[index("s", t)] = -1.0
            rows.append(row)
            rhs.append(load_energy[t] - pv_energy[t])
        a_eq = np.vstack([np.array(rows, dtype=float), a_eq])
        b_eq = np.concatenate([np.array(rhs, dtype=float), b_eq])
        a_ub = None
        b_ub = None
    else:                                                     # (R1') 不等式平衡（无弃光变量）
        a_ub = np.zeros((periods, size))
        b_ub = np.zeros(periods)
        for t in range(periods):
            a_ub[t, index("c", t)] = 1.0
            a_ub[t, index("b", t)] = -1.0
            a_ub[t, index("q", t)] = -1.0
            b_ub[t] = -(load_energy[t] - pv_energy[t])

    lower: list[float] = []
    upper: list[float | None] = []
    for kind in kinds:
        for t in range(periods):
            if kind == "b":
                lower.append(0.0)
                upper.append(None)
            elif kind == "c":
                lower.append(0.0)
                upper.append(c_cap)
            elif kind == "q":
                lower.append(0.0)
                upper.append(q_cap)
            elif kind == "s":
                lower.append(0.0)
                upper.append(float(pv_energy[t]))
            else:
                if t == periods - 1 and not free_final:
                    lower.append(e_init)
                    upper.append(e_init)
                else:
                    lower.append(e_min)
                    upper.append(e_max)
    return {
        "kinds": kinds,
        "periods": periods,
        "size": size,
        "objective": objective,
        "a_eq": a_eq,
        "b_eq": b_eq,
        "a_ub": a_ub,
        "b_ub": b_ub,
        "lower": np.array(lower, dtype=float),
        "upper": np.array([np.inf if item is None else item for item in upper], dtype=float),
        "solution_lower": lower,
        "solution_upper": upper,
        "eta_ch": eta_ch,
        "eta_dis": eta_dis,
        "c_cap": c_cap,
        "q_cap": q_cap,
        "e_init": e_init,
        "e_min": e_min,
        "e_max": e_max,
        "free_final": free_final,
        "drop_spill": drop_spill,
        "n_equalities": int(a_eq.shape[0]),
        "n_inequalities": 0 if a_ub is None else int(a_ub.shape[0]),
    }


def solve_lp_model(model: dict[str, Any], *, time_limit: float = 60.0, method: str = "highs") -> dict[str, Any]:
    started = time.perf_counter()
    result = linprog(
        model["objective"],
        A_ub=model["a_ub"],
        b_ub=model["b_ub"],
        A_eq=model["a_eq"],
        b_eq=model["b_eq"],
        bounds=list(zip(model["solution_lower"], model["solution_upper"])),
        method=method,
        options={"time_limit": float(time_limit), "presolve": True},
    )
    elapsed = time.perf_counter() - started
    return {
        "x": None if result.x is None else np.asarray(result.x, dtype=float),
        "status": int(result.status),
        "message": str(result.message),
        "iterations": int(result.nit) if result.nit is not None else None,
        "objective": float(result.fun) if result.fun is not None else float("nan"),
        "seconds": elapsed,
        "mip_gap": None,
        "mip_nodes": None,
    }


def solve_milp_model(model: dict[str, Any], *, time_limit: float = 60.0, mip_rel_gap: float = 0.0) -> dict[str, Any]:
    """在 LP 上追加互补二元变量 u_t（B 对照）。"""
    periods = model["periods"]
    size = model["size"]
    total = size + periods
    kinds = model["kinds"]
    index = lambda kind, t: kinds.index(kind) * periods + t  # noqa: E731

    objective = np.zeros(total)
    objective[:size] = model["objective"]

    a_eq = np.zeros((model["a_eq"].shape[0], total))
    a_eq[:, :size] = model["a_eq"]

    c_cap = model["c_cap"]
    q_cap = model["q_cap"]
    a_ub = np.zeros((2 * periods, total))
    b_ub = np.zeros(2 * periods)
    for t in range(periods):
        a_ub[t, index("c", t)] = 1.0
        a_ub[t, size + t] = -c_cap
        a_ub[periods + t, index("q", t)] = 1.0
        a_ub[periods + t, size + t] = q_cap
        b_ub[periods + t] = q_cap

    lower = np.concatenate([model["lower"], np.zeros(periods)])
    upper = np.concatenate([model["upper"], np.ones(periods)])
    integrality = np.zeros(total)
    integrality[size:] = 1

    started = time.perf_counter()
    result = milp(
        objective,
        constraints=[
            LinearConstraint(a_eq, model["b_eq"], model["b_eq"]),
            LinearConstraint(a_ub, -np.inf, b_ub),
        ],
        integrality=integrality,
        bounds=Bounds(lower, upper),
        options={"time_limit": float(time_limit), "mip_rel_gap": float(mip_rel_gap), "presolve": True, "disp": False},
    )
    elapsed = time.perf_counter() - started
    x = None if result.x is None else np.asarray(result.x, dtype=float)
    return {
        "x": x,
        "status": int(result.status),
        "message": str(result.message),
        "iterations": int(result.mip_node_count) if getattr(result, "mip_node_count", None) is not None else None,
        "objective": float(result.fun) if result.fun is not None else float("nan"),
        "seconds": elapsed,
        "mip_gap": None if getattr(result, "mip_gap", None) is None else float(result.mip_gap),
        "mip_nodes": None if getattr(result, "mip_node_count", None) is None else int(result.mip_node_count),
    }


# --------------------------------------------------------------------------- #
# SOC 离散化 DP（C 对照）
# --------------------------------------------------------------------------- #


def transition_terms(
    *,
    net_energy: Any,
    pv_energy: Any,
    price: Any,
    delta_e: Any,
    eta_ch: float = ETA_CH,
    eta_dis: float = ETA_DIS,
    c_cap: float = C_CAP,
    q_cap: float = Q_CAP,
    tol: float = 1e-9,
) -> tuple[Any, Any, Any, Any, Any, Any]:
    """给定 (E_{t-1}→E_t) 的状态增量，解析求该转移的最小费用与最优 (c,q,b,s)。

    推导：R2 给 ``η_ch·c − q/η_dis = ΔE``，R1 给 ``b = net + c − q + s``。
    ``c − q`` 在 ``ΔE ≥ 0`` 时随 c 单调增（斜率 0.19），在 ``ΔE < 0`` 时随 c 单调增，
    故最小 b 取 ``c = max(0, ΔE/η_ch)``；若该 b < 0（光伏盈余），沿 c 增大方向把
    ``s = max(0, −b)`` 压到 ``s ≤ PV·Δt`` 之内（等价于允许同时充放电，与 LP 一致）。
    """
    c_lo = np.maximum(0.0, delta_e / eta_ch)
    q_lo = eta_dis * (eta_ch * c_lo - delta_e)
    b_lo = net_energy + c_lo - q_lo
    cap_ok = (c_lo <= c_cap + tol) & (q_lo <= q_cap + tol)

    c_hi = np.minimum(c_cap, (q_cap / eta_dis + delta_e) / eta_ch)
    c_hi = np.maximum(c_hi, c_lo)
    q_hi = eta_dis * (eta_ch * c_hi - delta_e)
    b_hi = net_energy + c_hi - q_hi
    feasible = cap_ok & (b_hi >= -pv_energy - tol)

    b_target = np.minimum(np.maximum(b_lo, -pv_energy), b_hi)
    c_best = c_lo + (b_target - b_lo) / TRANSPORT_FLOOR
    c_best = np.clip(c_best, c_lo, c_hi)
    q_best = eta_dis * (eta_ch * c_best - delta_e)
    b_min = net_energy + c_best - q_best          # R1 左端的净购电需求
    b_best = np.maximum(0.0, b_min)               # b >= 0
    s_best = np.maximum(0.0, -b_min)              # 余电经弃光变量丢弃
    cost = price * b_best
    return cost, feasible, c_best, q_best, b_best, s_best


def solve_dp(
    *,
    price: np.ndarray,
    load_energy: np.ndarray,
    pv_energy: np.ndarray,
    step: float,
    eta_ch: float = ETA_CH,
    eta_dis: float = ETA_DIS,
    c_cap: float = C_CAP,
    q_cap: float = Q_CAP,
    e_init: float = E_INIT,
    e_min: float = E_MIN,
    e_max: float = E_MAX,
) -> dict[str, Any]:
    """状态离散化 DP：状态 E_t 取 [e_min, e_max] 上步长 step 的等距网格。"""
    grid = np.arange(e_min, e_max + step * 0.5, step, dtype=float)
    grid = np.round(grid, 9)
    periods = int(price.shape[0])
    n_grid = int(grid.size)
    span = e_max - e_min
    if abs(grid[-1] - e_max) > 1e-6 or abs(grid[0] - e_min) > 1e-6:
        raise ValueError(f"DP 网格未覆盖 [{e_min}, {e_max}]：step={step}")
    if abs((e_init - e_min) / step - round((e_init - e_min) / step)) > 1e-9:
        raise ValueError(f"e_init={e_init} 不在 step={step} 的网格上")
    start_index = int(round((e_init - e_min) / step))

    net = load_energy - pv_energy
    inf = np.inf
    dp = np.full(n_grid, inf)
    dp[start_index] = 0.0
    choice = np.zeros((periods, n_grid), dtype=np.int32)
    transitions = 0
    started = time.perf_counter()
    for t in range(periods):
        delta_e = grid[None, :] - grid[:, None]                     # ΔE[i, j]
        cost, feasible, *_ = transition_terms(
            net_energy=net[t],
            pv_energy=pv_energy[t],
            price=price[t],
            delta_e=delta_e,
            eta_ch=eta_ch,
            eta_dis=eta_dis,
            c_cap=c_cap,
            q_cap=q_cap,
        )
        transitions += int(n_grid * n_grid)
        total = dp[:, None] + np.where(feasible, cost, inf)
        total = np.where(np.isfinite(total), total, inf)
        column_ok = np.any(np.isfinite(total), axis=0)
        best_index = np.argmin(np.where(np.isfinite(total), total, inf), axis=0)
        new_dp = np.where(column_ok, total[best_index, np.arange(n_grid)], inf)
        choice[t] = best_index
        dp = new_dp
        if not np.any(np.isfinite(dp)):
            break
    elapsed = time.perf_counter() - started

    objective = float(dp[start_index]) if np.isfinite(dp[start_index]) else float("nan")
    record: dict[str, Any] = {
        "status": 0 if np.isfinite(objective) else 2,
        "message": "DP optimal" if np.isfinite(objective) else "DP infeasible",
        "objective": objective,
        "seconds": elapsed,
        "iterations": None,
        "mip_gap": None,
        "mip_nodes": None,
        "dp_step_kwh": float(step),
        "dp_grid_points": n_grid,
        "dp_transitions": transitions,
        "dp_grid_span_kwh": float(span),
        "x": None,
    }
    if not np.isfinite(objective):
        record["arrays"] = None
        return record

    # 回溯路径
    states = np.zeros(periods + 1, dtype=np.int32)
    states[periods] = start_index
    for t in range(periods - 1, -1, -1):
        states[t] = choice[t, states[t + 1]]
    purchase = np.zeros(periods)
    charge = np.zeros(periods)
    discharge = np.zeros(periods)
    spill = np.zeros(periods)
    storage = np.zeros(periods)
    for t in range(periods):
        i, j = int(states[t]), int(states[t + 1])
        delta_e = float(grid[j] - grid[i])
        cost, feasible, c_best, q_best, b_best, s_best = transition_terms(
            net_energy=float(net[t]),
            pv_energy=float(pv_energy[t]),
            price=float(price[t]),
            delta_e=delta_e,
            eta_ch=eta_ch,
            eta_dis=eta_dis,
            c_cap=c_cap,
            q_cap=q_cap,
        )
        if not bool(np.all(feasible)):
            record["status"] = 2
            record["arrays"] = None
            return record
        charge[t] = float(c_best)
        discharge[t] = float(q_best)
        purchase[t] = float(max(0.0, b_best))
        spill[t] = float(s_best)
        storage[t] = float(grid[j])
    record["arrays"] = {
        "purchase": purchase,
        "charge": charge,
        "discharge": discharge,
        "spill": spill,
        "storage": storage,
        "states": states,
    }
    return record


# --------------------------------------------------------------------------- #
# 指标与检查
# --------------------------------------------------------------------------- #


def evaluate_case(
    *,
    label: str,
    family: str,
    kind: str,
    model_kind: str,
    price: np.ndarray,
    load_energy: np.ndarray,
    pv_energy: np.ndarray,
    purchase: np.ndarray,
    charge: np.ndarray,
    discharge: np.ndarray,
    spill: np.ndarray | None,
    storage: np.ndarray,
    eta_ch: float,
    eta_dis: float,
    c_cap: float,
    q_cap: float,
    e_init: float,
    e_min: float,
    e_max: float,
    free_final: bool,
    drop_spill: bool,
    solve: dict[str, Any],
    n_variables: int,
    n_equalities: int,
    n_inequalities: int,
    honors_identities: bool,
    note: str = "",
) -> dict[str, Any]:
    periods = int(price.shape[0])
    total_purchase = float(np.sum(purchase))
    total_charge = float(np.sum(charge))
    total_discharge = float(np.sum(discharge))
    total_spill = None if spill is None else float(np.sum(spill))
    cost = float(np.sum(price * purchase))
    net = float(np.sum(load_energy - pv_energy))

    # 约束残差（用原始等式/不等式逐项回代）
    r2 = np.zeros(periods)
    for t in range(periods):
        previous = e_init if t == 0 else storage[t - 1]
        r2[t] = storage[t] - previous - eta_ch * charge[t] + discharge[t] / eta_dis
    equality_residual = float(np.max(np.abs(r2))) if periods else 0.0
    inequality_violation = 0.0
    if drop_spill:
        residual = (load_energy - pv_energy) - (purchase + discharge - charge)
        inequality_violation = float(np.max(np.maximum(residual, 0.0)))
    else:
        balance = purchase + discharge - charge - spill - (load_energy - pv_energy)
        equality_residual = float(max(equality_residual, np.max(np.abs(balance))))

    # 界越界量按变量种类逐段计算（E 末时段由 free_final 决定）
    bound_violation = 0.0
    bound_violation = max(bound_violation, float(np.max(np.maximum(-purchase, 0.0))))
    bound_violation = max(bound_violation, float(np.max(np.maximum(charge - c_cap, 0.0))))
    bound_violation = max(bound_violation, float(np.max(np.maximum(-charge, 0.0))))
    bound_violation = max(bound_violation, float(np.max(np.maximum(discharge - q_cap, 0.0))))
    bound_violation = max(bound_violation, float(np.max(np.maximum(-discharge, 0.0))))
    bound_violation = max(bound_violation, float(np.max(np.maximum(storage - e_max, 0.0))))
    bound_violation = max(bound_violation, float(np.max(np.maximum(e_min - storage, 0.0))))
    if spill is not None:
        bound_violation = max(bound_violation, float(np.max(np.maximum(-spill, 0.0))))
        bound_violation = max(bound_violation, float(np.max(np.maximum(spill - pv_energy, 0.0))))
    if not free_final:
        bound_violation = max(bound_violation, abs(float(storage[-1]) - e_init))

    simultaneous = int(np.sum((charge > TOL) & (discharge > TOL)))
    complementarity = float(np.sum(charge * discharge))

    side_powers = [
        float(np.max(charge / DT)),
        float(np.max(eta_ch * charge / DT)),
        float(np.max(discharge / DT)),
        float(np.max(discharge / (eta_dis * DT))),
    ]
    max_side_power = float(max(side_powers))

    identity_i1 = total_discharge - eta_ch * eta_dis * total_charge
    identity_i2 = (
        total_purchase
        - net
        - (0.0 if total_spill is None else total_spill)
        - (1.0 - eta_ch * eta_dis) * total_charge
    )

    checks: dict[str, Any] = {
        "equality_residual": equality_residual <= TOL,
        "inequality_violation": inequality_violation <= TOL,
        "bound_violation": bound_violation <= TOL,
        "storage_upper": float(np.max(storage)) <= e_max + TOL,
        "storage_lower": float(np.min(storage)) >= e_min - TOL,
        "charge_cap": float(np.max(charge)) <= c_cap + TOL,
        "discharge_cap": float(np.max(discharge)) <= q_cap + TOL,
        "purchase_nonneg": float(np.min(purchase)) >= -TOL,
        "max_side_power": max_side_power <= P_MAX + 1e-3,
    }
    if not drop_spill:
        checks["spill_bound"] = bool(np.all(spill <= pv_energy + TOL))
        checks["periodic_endpoint"] = True if free_final else abs(float(storage[-1]) - e_init) <= TOL
    if honors_identities:
        checks["identity_I1"] = abs(identity_i1) <= 1e-6
        checks["identity_I2"] = abs(identity_i2) <= 1e-6

    feasible = bool(solve["status"] == 0 and all(checks.values()))
    no_storage_cost = float(np.sum(price * np.maximum(load_energy - pv_energy, 0.0)))

    record: dict[str, Any] = {
        "label": label,
        "family": family,
        "kind": kind,
        "model_kind": model_kind,
        "note": note,
        "feasible": feasible,
        "solver_status": int(solve["status"]),
        "solver_message": str(solve["message"]),
        "objective_yuan": round(cost, 6),
        "objective_solver_yuan": _finite(float(solve["objective"])),
        "solve_seconds": round(float(solve["seconds"]), 4),
        "iterations": solve["iterations"],
        "mip_gap": solve["mip_gap"],
        "mip_nodes": solve["mip_nodes"],
        "no_storage_cost_yuan": round(no_storage_cost, 6),
        "arbitrage_gain_yuan": round(no_storage_cost - cost, 6),
        "arbitrage_gain_ratio": round((no_storage_cost - cost) / no_storage_cost, 6),
        "complexity": {
            "variables": int(n_variables),
            "equalities": int(n_equalities),
            "inequalities": int(n_inequalities),
            "solve_seconds": round(float(solve["seconds"]), 4),
            "iterations": solve["iterations"],
            "mip_gap": solve["mip_gap"],
            "mip_nodes": solve["mip_nodes"],
            "dp_grid_points": solve.get("dp_grid_points"),
            "dp_transitions": solve.get("dp_transitions"),
        },
        "total_purchase_kwh": round(total_purchase, 6),
        "total_charge_kwh": round(total_charge, 6),
        "total_discharge_kwh": round(total_discharge, 6),
        "total_spill_kwh": None if total_spill is None else round(total_spill, 6),
        "net_load_kwh": round(net, 6),
        "storage_min_kwh": round(float(np.min(storage)), 6),
        "storage_max_kwh": round(float(np.max(storage)), 6),
        "storage_final_kwh": round(float(storage[-1]), 6),
        "equivalent_full_cycles": round(total_discharge / max(e_max - e_min, 1e-9), 6),
        "max_side_power_kw": round(max_side_power, 6),
        "simultaneous_periods": simultaneous,
        "complementarity_residual": complementarity,
        "equality_residual_max": _finite(equality_residual),
        "inequality_violation_max": _finite(inequality_violation),
        "bound_violation_max": _finite(bound_violation),
        "identity_I1_residual": _finite(identity_i1),
        "identity_I2_residual": _finite(identity_i2),
        "checks_failed": [name for name, ok in checks.items() if not ok],
        "table1_purchase_kwh": _table1(purchase),
        "table2_block_charge_kwh": _blocks(charge, periods),
        "table2_block_discharge_kwh": _blocks(discharge, periods),
        "table2_storage_0_00_kwh": e_init,
        "table2_storage_24_00_kwh": round(float(storage[-1]), 6),
        "mean_price_charge": _finite(float(np.mean(price[charge > TOL])) if np.any(charge > TOL) else None),
        "mean_price_discharge": _finite(float(np.mean(price[discharge > TOL])) if np.any(discharge > TOL) else None),
        "eta_ch": eta_ch,
        "eta_dis": eta_dis,
        "c_cap_kwh": round(c_cap, 6),
        "q_cap_kwh": round(q_cap, 6),
    }
    return _finite(record)


# --------------------------------------------------------------------------- #
# 单个对照的执行
# --------------------------------------------------------------------------- #


def run_lp_case(
    *,
    label: str,
    family: str,
    kind: str,
    data: Any,
    price: np.ndarray,
    load_energy: np.ndarray,
    pv_energy: np.ndarray,
    time_limit: float,
    eta_ch: float = ETA_CH,
    eta_dis: float = ETA_DIS,
    free_final: bool = False,
    drop_spill: bool = False,
    honors_identities: bool = True,
    note: str = "",
) -> dict[str, Any]:
    model = build_model(
        price=price,
        load_energy=load_energy,
        pv_energy=pv_energy,
        eta_ch=eta_ch,
        eta_dis=eta_dis,
        free_final=free_final,
        drop_spill=drop_spill,
    )
    solve = solve_lp_model(model, time_limit=time_limit)
    if solve["x"] is None:
        return _finite(
            {
                "label": label,
                "family": family,
                "kind": kind,
                "feasible": False,
                "solver_status": solve["status"],
                "solver_message": solve["message"],
                "objective_yuan": None,
                "checks_failed": ["no_solution"],
                "note": note,
                "complexity": {
                    "variables": model["size"],
                    "equalities": model["n_equalities"],
                    "inequalities": model["n_inequalities"],
                    "solve_seconds": round(float(solve["seconds"]), 4),
                },
            }
        )
    x = solve["x"]
    periods = model["periods"]
    kinds = model["kinds"]
    index = lambda k, t: kinds.index(k) * periods + t  # noqa: E731
    purchase = x[[index("b", t) for t in range(periods)]]
    charge = x[[index("c", t) for t in range(periods)]]
    discharge = x[[index("q", t) for t in range(periods)]]
    spill = None if drop_spill else x[[index("s", t) for t in range(periods)]]
    storage = x[[index("E", t) for t in range(periods)]]
    return evaluate_case(
        label=label,
        family=family,
        kind=kind,
        model_kind="lp",
        price=price,
        load_energy=load_energy,
        pv_energy=pv_energy,
        purchase=purchase,
        charge=charge,
        discharge=discharge,
        spill=spill,
        storage=storage,
        eta_ch=model["eta_ch"],
        eta_dis=model["eta_dis"],
        c_cap=model["c_cap"],
        q_cap=model["q_cap"],
        e_init=model["e_init"],
        e_min=model["e_min"],
        e_max=model["e_max"],
        free_final=free_final,
        drop_spill=drop_spill,
        solve=solve,
        n_variables=model["size"],
        n_equalities=model["n_equalities"],
        n_inequalities=model["n_inequalities"],
        honors_identities=honors_identities,
        note=note,
    )


def run_milp_case(
    *,
    label: str,
    data: Any,
    price: np.ndarray,
    load_energy: np.ndarray,
    pv_energy: np.ndarray,
    time_limit: float,
    mip_rel_gap: float = 0.0,
    note: str = "",
) -> dict[str, Any]:
    model = build_model(price=price, load_energy=load_energy, pv_energy=pv_energy)
    solve = solve_milp_model(model, time_limit=time_limit, mip_rel_gap=mip_rel_gap)
    if solve["x"] is None:
        return _finite(
            {
                "label": label,
                "family": "B_milp",
                "kind": "milp",
                "feasible": False,
                "solver_status": solve["status"],
                "solver_message": solve["message"],
                "objective_yuan": None,
                "checks_failed": ["no_solution"],
                "note": note,
                "complexity": {
                    "variables": model["size"] + model["periods"],
                    "equalities": model["n_equalities"],
                    "inequalities": 2 * model["periods"],
                    "solve_seconds": round(float(solve["seconds"]), 4),
                    "mip_gap": solve["mip_gap"],
                    "mip_nodes": solve["mip_nodes"],
                },
            }
        )
    x = solve["x"]
    periods = model["periods"]
    kinds = model["kinds"]
    index = lambda k, t: kinds.index(k) * periods + t  # noqa: E731
    purchase = x[[index("b", t) for t in range(periods)]]
    charge = x[[index("c", t) for t in range(periods)]]
    discharge = x[[index("q", t) for t in range(periods)]]
    spill = x[[index("s", t) for t in range(periods)]]
    storage = x[[index("E", t) for t in range(periods)]]
    return evaluate_case(
        label=label,
        family="B_milp",
        kind="milp",
        model_kind="milp",
        price=price,
        load_energy=load_energy,
        pv_energy=pv_energy,
        purchase=purchase,
        charge=charge,
        discharge=discharge,
        spill=spill,
        storage=storage,
        eta_ch=model["eta_ch"],
        eta_dis=model["eta_dis"],
        c_cap=model["c_cap"],
        q_cap=model["q_cap"],
        e_init=model["e_init"],
        e_min=model["e_min"],
        e_max=model["e_max"],
        free_final=False,
        drop_spill=False,
        solve=solve,
        n_variables=model["size"] + model["periods"],
        n_equalities=model["n_equalities"],
        n_inequalities=2 * model["periods"],
        honors_identities=True,
        note=note,
    )


def run_dp_case(
    *,
    label: str,
    step: float,
    price: np.ndarray,
    load_energy: np.ndarray,
    pv_energy: np.ndarray,
    note: str = "",
) -> dict[str, Any]:
    solve = solve_dp(price=price, load_energy=load_energy, pv_energy=pv_energy, step=step)
    arrays = solve.get("arrays")
    if arrays is None:
        return _finite(
            {
                "label": label,
                "family": "C_dp",
                "kind": "dp",
                "feasible": False,
                "solver_status": solve["status"],
                "solver_message": "DP 无可行状态轨迹",
                "objective_yuan": None,
                "checks_failed": ["dp_infeasible"],
                "note": note,
                "complexity": {
                    "variables": solve.get("dp_grid_points"),
                    "equalities": None,
                    "inequalities": None,
                    "solve_seconds": round(float(solve["seconds"]), 4),
                    "dp_grid_points": solve.get("dp_grid_points"),
                    "dp_transitions": solve.get("dp_transitions"),
                },
            }
        )
    return evaluate_case(
        label=label,
        family="C_dp",
        kind="dp",
        model_kind="dp",
        price=price,
        load_energy=load_energy,
        pv_energy=pv_energy,
        purchase=arrays["purchase"],
        charge=arrays["charge"],
        discharge=arrays["discharge"],
        spill=arrays["spill"],
        storage=arrays["storage"],
        eta_ch=ETA_CH,
        eta_dis=ETA_DIS,
        c_cap=C_CAP,
        q_cap=Q_CAP,
        e_init=E_INIT,
        e_min=E_MIN,
        e_max=E_MAX,
        free_final=False,
        drop_spill=False,
        solve=solve,
        n_variables=solve.get("dp_grid_points") or 0,
        n_equalities=0,
        n_inequalities=0,
        honors_identities=True,
        note=note,
    )


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #


def _parse_steps(text: str) -> list[float]:
    steps = []
    for item in text.split(","):
        item = item.strip()
        if item:
            steps.append(float(item))
    if not steps:
        raise ValueError("--dp-steps 不能为空")
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description="prob01 消融与模型族对照实验")
    parser.add_argument("--input", default="data/附件1.xlsx")
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--time-limit", type=float, default=60.0)
    parser.add_argument("--dp-steps", default=",".join(str(int(step)) for step in DP_STEPS))
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args()

    started = time.perf_counter()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    try:
        dp_steps = _parse_steps(args.dp_steps)
    except ValueError as exc:
        print(f"参数非法：{exc}", file=sys.stderr)
        return 3

    data = read_attachment1(Path(args.input), expected_rows=144)
    price = np.asarray(data.price, dtype=float)
    load_energy = np.asarray(data.load_kw, dtype=float) * DT
    pv_energy = np.asarray(data.pv_kw, dtype=float) * DT
    periods = int(price.shape[0])

    records: list[dict[str, Any]] = []

    def emit(record: dict[str, Any], subdir: str) -> None:
        records.append(record)
        write_json(output / subdir / "case.json", record)
        print(
            f"[case] {record['label']} feasible={record.get('feasible')} "
            f"C={record.get('objective_yuan')}",
            flush=True,
        )

    # ---------- A 基准 ----------
    baseline = run_lp_case(
        label="A_baseline_LP",
        family="A_baseline_LP",
        kind="lp",
        data=data,
        price=price,
        load_energy=load_energy,
        pv_energy=pv_energy,
        time_limit=args.time_limit,
        note="accepted formulation_v001 完整 LP（内部对照 + C1 复现闸门）",
    )
    emit(baseline, "A_baseline_LP")

    # ---------- B MILP ----------
    emit(
        run_milp_case(
            label="B_milp",
            data=data,
            price=price,
            load_energy=load_energy,
            pv_energy=pv_energy,
            time_limit=args.time_limit,
            note="互补二元变量 c_t<=C_CAP*u_t、q_t<=Q_CAP*(1-u_t)，显式强制 AS07",
        ),
        "B_milp",
    )

    # ---------- C DP 粒度族 ----------
    for step in dp_steps:
        emit(
            run_dp_case(
                label=f"C_dp_h{int(step):03d}",
                step=step,
                price=price,
                load_energy=load_energy,
                pv_energy=pv_energy,
                note=f"SOC 离散化 DP，状态步长 {step:g} kWh",
            ),
            f"C_dp_h{int(step):03d}",
        )

    # ---------- D 去日周期 ----------
    emit(
        run_lp_case(
            label="D_no_periodic",
            family="D_no_periodic",
            kind="lp_no_periodic",
            data=data,
            price=price,
            load_energy=load_energy,
            pv_energy=pv_energy,
            time_limit=args.time_limit,
            free_final=True,
            honors_identities=False,
            note="去掉日周期约束 E_0=E_144（E_144 自由 ∈[1200,10800]，E_0=6000 保留）",
        ),
        "D_no_periodic",
    )

    # ---------- E 去弃光变量 ----------
    emit(
        run_lp_case(
            label="E_no_spill",
            family="E_no_spill",
            kind="lp_no_spill",
            data=data,
            price=price,
            load_energy=load_energy,
            pv_energy=pv_energy,
            time_limit=args.time_limit,
            drop_spill=True,
            honors_identities=False,
            note="删除 s_t，R1 改为不等式 b+q-c >= 净负荷",
        ),
        "E_no_spill",
    )

    # ---------- F 效率作用位置（c/q 上限固定为 accepted）----------
    for eta_ch, eta_dis, tag, note in (
        (0.9, 0.9, "place_both", "两侧各 0.9（accepted）"),
        (0.9, 1.0, "place_charge_only", "仅充电侧 0.9"),
        (1.0, 0.9, "place_discharge_only", "仅放电侧 0.9"),
        (float(np.sqrt(0.9)), float(np.sqrt(0.9)), "place_round_trip", "往返整体 0.9（各侧 √0.9）"),
    ):
        emit(
            run_lp_case(
                label=f"F_{tag}",
                family="F_eta_placement",
                kind="lp_eta",
                data=data,
                price=price,
                load_energy=load_energy,
                pv_energy=pv_energy,
                time_limit=args.time_limit,
                eta_ch=eta_ch,
                eta_dis=eta_dis,
                honors_identities=False,
                note=f"效率作用位置：{note}；c/q 上限固定 833.3333/750.0000（与 robustness 族不同，见 plan.md §3.6）",
            ),
            f"F_{tag}",
        )

    with (output / "raw_cases.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(_finite(record), ensure_ascii=False, allow_nan=False) + "\n")

    # ---------- C1 基线复现闸门 ----------
    reference = json.loads((RUN002_DIR / "solution.json").read_text(encoding="utf-8"))
    ref_totals = reference["totals"]
    baseline_check: dict[str, Any] = {
        "reference": "results/prob01_v003_f001_run002/solution.json",
        "reference_sha256": _sha256(RUN002_DIR / "solution.json"),
        "compared": {},
        "passed": False,
    }
    if not baseline.get("feasible"):
        baseline_check["error"] = "baseline 不可行"
    else:
        pairs = {
            "objective_yuan": (baseline["objective_yuan"], reference["objective_yuan"]),
            "total_purchase_kwh": (baseline["total_purchase_kwh"], ref_totals["total_purchase_kwh"]),
            "total_charge_kwh": (baseline["total_charge_kwh"], ref_totals["total_charge_kwh"]),
            "total_discharge_kwh": (baseline["total_discharge_kwh"], ref_totals["total_discharge_kwh"]),
            "total_spill_kwh": (baseline["total_spill_kwh"], ref_totals["total_spill_kwh"]),
            "max_side_power_kw": (baseline["max_side_power_kw"], ref_totals["max_side_power_kw"]),
        }
        ok = True
        for name, (got, want) in pairs.items():
            scale = max(abs(want), 1.0)
            relative = abs(got - want) / scale
            entry = {"ours": got, "reference": want, "relative_diff": relative, "passed": relative <= 1e-6}
            baseline_check["compared"][name] = entry
            ok = ok and entry["passed"]
        baseline_check["passed"] = bool(ok)

    # ---------- 独立实现交叉检查（accepted prob01_model.py 只读复跑）----------
    cross_check: dict[str, Any] = {"ran": False}
    try:
        from prob01_model import LpData
        from prob01_model import evaluate as accepted_evaluate
        from prob01_model import solve_lp as accepted_solve

        accepted_solution = accepted_solve(
            LpData(
                price=price,
                load_kw=np.asarray(data.load_kw, dtype=float),
                pv_kw=np.asarray(data.pv_kw, dtype=float),
                periods=periods,
                time_labels=tuple(data.time_labels),
            ),
            time_limit_seconds=args.time_limit,
        )
        accepted_metrics = accepted_evaluate(accepted_solution)
        got = baseline.get("objective_yuan")
        want = float(accepted_metrics["objective_yuan"])
        relative = abs(got - want) / max(abs(want), 1.0)
        cross_check = {
            "ran": True,
            "accepted_objective_yuan": want,
            "generic_objective_yuan": got,
            "relative_diff": relative,
            "passed": bool(relative <= 1e-9),
            "accepted_checks_failed": accepted_metrics["checks_failed"],
        }
    except Exception as exc:  # noqa: BLE001 - 交叉检查失败不得掩盖主流程，但必须登记
        cross_check = {"ran": False, "error": f"{type(exc).__name__}: {exc}"}
    baseline_check["accepted_impl_cross_check"] = cross_check

    write_json(output / "baseline_check.json", baseline_check)
    write_json(
        output / "solver_status.json",
        {
            "solver_lp": "scipy.optimize.linprog(method='highs')",
            "solver_milp": "scipy.optimize.milp(HiGHS)",
            "solver_dp": "deterministic dynamic programming (no solver)",
            "device": "cpu",
            "gpu_required": False,
            "seed": args.seed,
            "time_limit_seconds": args.time_limit,
            "baseline_feasible": bool(baseline.get("feasible")),
            "feasible_incumbent": bool(baseline.get("feasible")),
            "baseline_check_passed": baseline_check["passed"],
            "cases_total": len(records),
            "cases_infeasible": sum(1 for item in records if not item.get("feasible")),
        },
    )
    if not baseline_check["passed"]:
        write_json(
            output / "run_manifest.json",
            {
                "outcome": "baseline_mismatch",
                "checks_failed": ["baseline_reproduction"],
                "cases_total": len(records),
                "baseline_check": baseline_check,
            },
        )
        print("基线复现失败，整批作废（exit 4）", file=sys.stderr)
        return 4

    by_label = {record["label"]: record for record in records}
    base_cost = float(baseline["objective_yuan"])

    def relative_diff(record: dict[str, Any]) -> float | None:
        if not record.get("feasible") or record.get("objective_yuan") is None:
            return None
        return (float(record["objective_yuan"]) - base_cost) / base_cost

    # ---------- DP 粒度曲线 ----------
    dp_records = [record for record in records if record["family"] == "C_dp"]
    dp_granularity = {
        "reference_objective_yuan": base_cost,
        "points": [
            {
                "step_kwh": None,
                "label": record["label"],
                "grid_points": record["complexity"].get("dp_grid_points"),
                "transitions": record["complexity"].get("dp_transitions"),
                "objective_yuan": record.get("objective_yuan"),
                "relative_diff": relative_diff(record),
                "solve_seconds": record["complexity"].get("solve_seconds"),
                "feasible": record.get("feasible"),
            }
            for record in dp_records
        ],
    }
    step_of = {f"C_dp_h{int(step):03d}": float(step) for step in dp_steps}
    for point in dp_granularity["points"]:
        point["step_kwh"] = step_of.get(point["label"])

    # ---------- 判据 C1–C7 ----------
    criteria: dict[str, Any] = {}
    criteria["C1_baseline_reproduction"] = {
        "value": max(
            (entry["relative_diff"] for entry in baseline_check["compared"].values()),
            default=float("nan"),
        ),
        "threshold": 1e-6,
        "passed": bool(baseline_check["passed"]),
    }
    milp = by_label.get("B_milp")
    if milp and milp.get("feasible"):
        rel = abs(float(milp["objective_yuan"]) - base_cost) / base_cost
        gap = milp.get("mip_gap")
        criteria["C2_milp_lossless"] = {
            "value": rel,
            "mip_gap": gap,
            "threshold": 1e-6,
            "passed": bool(rel <= 1e-6 and (gap is not None and gap <= 1e-6)),
            "direction_ok": bool(float(milp["objective_yuan"]) >= base_cost - 1e-6),
        }
    else:
        criteria["C2_milp_lossless"] = {"value": None, "threshold": 1e-6, "passed": False, "note": "MILP 不可行"}
    dp50 = by_label.get(f"C_dp_h{int(min(dp_steps)):03d}")
    dp_valid = [record for record in dp_records if record.get("feasible")]
    monotone = True
    ordered = sorted(dp_valid, key=lambda item: float(item["complexity"]["dp_grid_points"]))
    for previous, current in zip(ordered, ordered[1:]):
        if float(current["objective_yuan"]) > float(previous["objective_yuan"]) + 1e-6:
            monotone = False
    if dp50 and dp50.get("feasible"):
        rel_dp = (float(dp50["objective_yuan"]) - base_cost) / base_cost
        range_ok = bool(0.0 - 1e-6 <= rel_dp <= 0.01)
        criteria["C3_dp_route_consistency"] = {
            "value": rel_dp,
            "threshold": 0.01,
            "passed": bool(range_ok and monotone),
            "relative_range_ok": range_ok,
            "dp_not_better_than_lp": bool(float(dp50["objective_yuan"]) >= base_cost - 1e-6),
            "monotone_in_step": bool(monotone),
        }
    else:
        criteria["C3_dp_route_consistency"] = {"value": None, "threshold": 0.01, "passed": False}
    d_rec = by_label.get("D_no_periodic")
    e_rec = by_label.get("E_no_spill")
    c4a = bool(d_rec and d_rec.get("feasible") and float(d_rec["objective_yuan"]) <= base_cost + 1e-6)
    c4b = bool(e_rec and e_rec.get("feasible") and float(e_rec["objective_yuan"]) <= base_cost + 1e-6)
    criteria["C4_structural_direction"] = {
        "D_no_periodic_relative_diff": relative_diff(d_rec) if d_rec else None,
        "E_no_spill_relative_diff": relative_diff(e_rec) if e_rec else None,
        "threshold": 1e-6,
        "passed": bool(c4a and c4b),
        "D_direction_ok": c4a,
        "E_direction_ok": c4b,
    }
    f_records = [record for record in records if record["family"] == "F_eta_placement"]
    f_feasible = {record["label"]: float(record["objective_yuan"]) for record in f_records if record.get("feasible")}
    both = f_feasible.get("F_place_both")
    others = [value for key, value in f_feasible.items() if key != "F_place_both"]
    max_dev = max(
        (abs(value - base_cost) / base_cost for value in f_feasible.values()),
        default=None,
    )
    criteria["C5_eta_placement"] = {
        "costs": f_feasible,
        "accepted_is_most_conservative": bool(both is not None and all(both >= value - 1e-6 for value in others)),
        "max_abs_relative_diff": max_dev,
        "threshold": 0.10,
        "passed": bool(
            both is not None
            and all(both >= value - 1e-6 for value in others)
            and max_dev is not None
            and max_dev <= 0.10
        ),
        "relative_diff": {key: round((value - base_cost) / base_cost, 6) for key, value in f_feasible.items()},
    }
    constraint_failures = {
        record["label"]: record.get("checks_failed", [])
        for record in records
        if record.get("checks_failed")
    }
    milp_ok = bool(
        milp
        and milp.get("feasible")
        and milp.get("simultaneous_periods") == 0
        and float(milp.get("complementarity_residual") or 0.0) <= 1e-6
    )
    criteria["C6_constraint_satisfaction"] = {
        "failed_cases": constraint_failures,
        "milp_zero_simultaneous": milp_ok,
        "passed": bool(not constraint_failures and milp_ok),
    }
    arbitrage_ok = all(
        (record.get("mean_price_charge") is None)
        or (record.get("mean_price_discharge") is None)
        or float(record["mean_price_charge"]) < float(record["mean_price_discharge"])
        for record in records
        if record["family"] in {"A_baseline_LP", "B_milp", "C_dp"} and record.get("feasible")
    )
    criteria["C7_interpretability"] = {
        "arbitrage_direction_ok": bool(arbitrage_ok),
        "baseline_simultaneous_periods": baseline.get("simultaneous_periods"),
        "passed": bool(arbitrage_ok and baseline.get("simultaneous_periods") == 0),
    }

    # ---------- 对比表 ----------
    comparison: list[dict[str, Any]] = []
    for record in records:
        comparison.append(
            {
                "label": record["label"],
                "family": record["family"],
                "kind": record["kind"],
                "note": record.get("note", ""),
                "feasible": record.get("feasible"),
                "objective_yuan": record.get("objective_yuan"),
                "relative_diff_vs_A": relative_diff(record),
                "total_purchase_kwh": record.get("total_purchase_kwh"),
                "total_charge_kwh": record.get("total_charge_kwh"),
                "total_discharge_kwh": record.get("total_discharge_kwh"),
                "total_spill_kwh": record.get("total_spill_kwh"),
                "max_side_power_kw": record.get("max_side_power_kw"),
                "equivalent_full_cycles": record.get("equivalent_full_cycles"),
                "simultaneous_periods": record.get("simultaneous_periods"),
                "storage_final_kwh": record.get("storage_final_kwh"),
                "table1_purchase_kwh": record.get("table1_purchase_kwh"),
                "table2_block_charge_kwh": record.get("table2_block_charge_kwh"),
                "table2_block_discharge_kwh": record.get("table2_block_discharge_kwh"),
                "complexity": record.get("complexity"),
                "equality_residual_max": record.get("equality_residual_max"),
                "bound_violation_max": record.get("bound_violation_max"),
                "checks_failed": record.get("checks_failed"),
                "mean_price_charge": record.get("mean_price_charge"),
                "mean_price_discharge": record.get("mean_price_discharge"),
            }
        )
    write_json(
        output / "comparison.json",
        {
            "baseline_objective_yuan": base_cost,
            "no_storage_cost_yuan": baseline.get("no_storage_cost_yuan"),
            "rows": comparison,
            "unexecuted": [],
        },
    )
    write_json(output / "dp_granularity.json", dp_granularity)

    # ---------- 结论 K1–K3 ----------
    conclusions = {
        "K1_model_family_independent": {
            "milp_matches_lp": criteria["C2_milp_lossless"]["passed"],
            "dp50_relative_diff": criteria["C3_dp_route_consistency"].get("value"),
            "supported": bool(
                criteria["C2_milp_lossless"]["passed"]
                and criteria["C3_dp_route_consistency"].get("passed")
            ),
        },
        "K2_structural_contribution": {
            "periodic_constraint_value_yuan": (
                round(base_cost - float(d_rec["objective_yuan"]), 6) if d_rec and d_rec.get("feasible") else None
            ),
            "spill_variable_value_yuan": (
                round(base_cost - float(e_rec["objective_yuan"]), 6) if e_rec and e_rec.get("feasible") else None
            ),
            "D_relative_diff": relative_diff(d_rec) if d_rec else None,
            "E_relative_diff": relative_diff(e_rec) if e_rec else None,
            "supported": bool(c4a and c4b),
        },
        "K3_eta_placement": {
            "relative_diff": criteria["C5_eta_placement"]["relative_diff"],
            "accepted_is_most_conservative": criteria["C5_eta_placement"]["accepted_is_most_conservative"],
            "supported": bool(criteria["C5_eta_placement"]["passed"]),
        },
    }

    failed = [name for name, item in criteria.items() if not item.get("passed")]
    technical_debt = []
    if not criteria["C2_milp_lossless"]["passed"]:
        technical_debt.append(
            "C2 MILP 无损性未通过：AS07 显式二元约束对 LP 最优值有可测影响，按 allow_pass_with_warning 登记"
        )
    if not criteria["C3_dp_route_consistency"].get("monotone_in_step", True):
        technical_debt.append("C3 DP 粒度曲线非严格单调（数值抖动或网格取整效应），按技术债登记")
    for label, failed_checks in constraint_failures.items():
        technical_debt.append(f"C6 case {label} 约束检查未通过：{failed_checks}")
    technical_debt.append(
        "F 效率作用位置族固定 c/q 上限（833.3333/750.0000），与 robustness eta_placement 族按情景重算上限的口径不同，"
        "两者数值不可互换引用（plan.md §3.6/§3.9）"
    )

    summary = {
        "baseline_objective_yuan": base_cost,
        "criteria": criteria,
        "criteria_failed": failed,
        "technical_debt": technical_debt,
        "conclusions": conclusions,
        "dp_granularity": dp_granularity["points"],
        "cases_total": len(records),
        "cases_infeasible": sum(1 for item in records if not item.get("feasible")),
        "robustness_reference": {
            "source": "robustness/results/prob01_v003_robust_run001/summary.json（只读复用，未重跑）",
            "stability_grade": "稳定",
            "S1_S6_all_passed": True,
            "dominant_parameter": "eta（|ΔC|/C* ≤ 0.088885）",
        },
    }
    write_json(output / "summary.json", summary)

    # ---------- 图件 ----------
    figures: list[str] = []
    if not args.no_figures:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.rcParams.update(
            {
                "figure.dpi": 180,
                "font.size": 10,
                "axes.grid": True,
                "grid.alpha": 0.3,
                "font.sans-serif": ["Microsoft YaHei", "DejaVu Sans"],
                "axes.unicode_minus": False,
            }
        )
        figure_dir = output / "figures"
        figure_dir.mkdir(parents=True, exist_ok=True)

        feasible_records = [record for record in records if record.get("feasible")]
        labels = [record["label"] for record in feasible_records]
        costs = [float(record["objective_yuan"]) for record in feasible_records]
        deltas = [value - base_cost for value in costs]

        # 图 1：模型/对照费用对比 + 相对偏差
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
        colors = ["#1F4E79" if label == "A_baseline_LP" else "#70AD47" for label in labels]
        axes[0].bar(range(len(labels)), costs, color=colors)
        axes[0].axhline(base_cost, color="#C00000", linestyle="--", linewidth=1.0, label="accepted LP C*")
        axes[0].set_xticks(range(len(labels)))
        axes[0].set_xticklabels(labels, rotation=55, ha="right", fontsize=8)
        axes[0].set_ylabel("daily purchase cost C (CNY)")
        axes[0].set_title("Model / ablation comparison: objective")
        axes[0].legend(fontsize=8)
        axes[1].bar(
            range(len(labels)),
            [value * 100 for value in (delta / base_cost for delta in deltas)],
            color=colors,
        )
        axes[1].axhline(0, color="black", linewidth=0.8)
        axes[1].set_xticks(range(len(labels)))
        axes[1].set_xticklabels(labels, rotation=55, ha="right", fontsize=8)
        axes[1].set_ylabel("relative change vs C* (%)")
        axes[1].set_title("Relative deviation (negative = cheaper than accepted LP)")
        fig.tight_layout()
        fig.savefig(figure_dir / "ablation_model_cost.png")
        plt.close(fig)
        figures.append("ablation_model_cost.png")

        # 图 2：DP 粒度-偏差曲线
        points = [point for point in dp_granularity["points"] if point.get("objective_yuan")]
        fig, ax = plt.subplots(figsize=(7.5, 4.6))
        if points:
            xs = [float(point["step_kwh"]) for point in points]
            ys = [float(point["objective_yuan"]) for point in points]
            ax.plot(xs, ys, marker="o", color="#1F4E79", label="DP cost")
            for x, y in zip(xs, ys):
                ax.annotate(f"{(y - base_cost) / base_cost * 100:.3f}%", (x, y), textcoords="offset points",
                            xytext=(0, 8), ha="center", fontsize=8)
            ax.set_xscale("log")
            ax.set_xticks(xs)
            ax.set_xticklabels([f"{int(x)}" for x in xs])
        ax.axhline(base_cost, color="#C00000", linestyle="--", linewidth=1.0, label="accepted LP C*")
        ax.set_xlabel("SOC discretization step h (kWh, log scale)")
        ax.set_ylabel("DP objective (CNY)")
        ax.set_title("Discretized-DP granularity: cost bias vs grid step")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(figure_dir / "ablation_dp_granularity.png")
        plt.close(fig)
        figures.append("ablation_dp_granularity.png")

        # 图 3：消融瀑布（各对照相对基准的 ΔC）
        fig, ax = plt.subplots(figsize=(9.5, 4.4))
        ordered = sorted(feasible_records, key=lambda record: float(record["objective_yuan"]))
        names = [record["label"] for record in ordered]
        values = [float(record["objective_yuan"]) - base_cost for record in ordered]
        bar_colors = ["#1F4E79" if value >= 0 else "#C00000" for value in values]
        ax.barh(range(len(names)), values, color=bar_colors)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=8)
        ax.set_xlabel("ΔC vs accepted LP C* (CNY)")
        ax.set_title("Ablation waterfall: cost change relative to accepted LP")
        for index, value in enumerate(values):
            ax.annotate(f"{value:+.2f}", (value, index), textcoords="offset points",
                        xytext=(6 if value >= 0 else -6, 0), va="center",
                        ha="left" if value >= 0 else "right", fontsize=8)
        fig.tight_layout()
        fig.savefig(figure_dir / "ablation_waterfall.png")
        plt.close(fig)
        figures.append("ablation_waterfall.png")

        # 图 4：复杂度-费用权衡
        fig, ax = plt.subplots(figsize=(7.5, 4.8))
        for record in feasible_records:
            complexity = record.get("complexity") or {}
            seconds = float(complexity.get("solve_seconds") or 0.0)
            variables = complexity.get("variables")
            ax.scatter(max(seconds, 1e-4), float(record["objective_yuan"]), s=42)
            ax.annotate(
                f"{record['label']}\n(vars={variables})",
                (max(seconds, 1e-4), float(record["objective_yuan"])),
                textcoords="offset points",
                xytext=(5, 4),
                fontsize=7,
            )
        ax.axhline(base_cost, color="#C00000", linestyle="--", linewidth=1.0)
        ax.set_xscale("log")
        ax.set_xlabel("solve time (s, log scale)")
        ax.set_ylabel("objective C (CNY)")
        ax.set_title("Complexity vs objective trade-off")
        fig.tight_layout()
        fig.savefig(figure_dir / "ablation_complexity_tradeoff.png")
        plt.close(fig)
        figures.append("ablation_complexity_tradeoff.png")

    # ---------- 追踪 manifest ----------
    code_sha = {path.name: _sha256(path) for path in sorted(HERE.parent.glob("*.py"))}
    manifest = {
        "stage": "ablation",
        "question_id": "prob01",
        "assumption_version": "assumption_v003",
        "formulation_version": "formulation_v001",
        "task_id": os.environ.get("AUTOMM_TASK_ID"),
        "output_directory": str(output.as_posix()),
        "input_md5": data.md5,
        "reference_run002_sha256": baseline_check["reference_sha256"],
        "seed": args.seed,
        "dp_steps_kwh": dp_steps,
        "time_limit_seconds": args.time_limit,
        "families": list(CASE_FAMILIES),
        "cases_total": len(records),
        "cases_infeasible": sum(1 for item in records if not item.get("feasible")),
        "figures": figures,
        "code_sha256": code_sha,
        "accepted_code_sha256": {
            "prob01_model.py": _sha256(ACCEPTED_CODE / "prob01_model.py"),
            "prob01_io.py": _sha256(ACCEPTED_CODE / "prob01_io.py"),
        },
        "device": "cpu",
        "gpu_required": False,
        "baseline_check": baseline_check["passed"],
        "accepted_impl_cross_check": cross_check,
        "criteria_failed": failed,
        "checks_failed": ([] if baseline_check["passed"] else ["baseline_reproduction"]) + failed,
        "outcome": "completed" if not failed else "completed_with_findings",
        "wall_clock_seconds": round(time.perf_counter() - started, 3),
    }
    write_json(output / "run_manifest.json", manifest)
    print(
        json.dumps(
            {
                "outcome": manifest["outcome"],
                "cases": len(records),
                "failed_criteria": failed,
                "baseline_check": baseline_check["passed"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
