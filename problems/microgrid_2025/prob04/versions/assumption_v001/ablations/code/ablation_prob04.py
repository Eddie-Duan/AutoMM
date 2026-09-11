# -*- coding: utf-8 -*-
"""prob04 `ablation` 阶段的隔离计算脚本（**分链运行**：`--chain 4-2` / `--chain 4-3`）。
对应预注册方案 `ablations/plan.md`（跑数前冻结）。脚本只读 `data/`、只读导入 accepted
`code/`（`prob04_io` / `prob04_model` / `prob04_predict`），全部产物写入
`.../assumption_v001/ablations/results/<run>/`。
对照集合（plan.md §3）：
  * `BASE`                 —— 主口径基线复现（判据 C2）；
  * `C-ANCHOR-P03`         —— 实现正确性锚点（价格 ← 附件 1 单日曲线；判据 C1，强制闸门；仅 4-3）；
  * `S-RH-H{1,3,7,14}`     —— 滚动时域前瞻深度（判据 C3 基线闸门 / C4 单调性）
  * `S-VAR`                —— 24 场景两阶段随机（团队 R-1；含「必须的改写」：计划购电账单场景相关）
  * `S-VAR-RH-H3`          —— 组合项（团队 R-2 可选，本方案执行；仅 4-2）
  * `PF-AR`                —— 预测器选择敏感性（AS08；仅 4-2）
  * `S-ABL-SPILL`          —— 弃光界 D9-B → D9-A（AS05）
  * `S-ABL-KAPPA1`         —— κ_m ≡ 1（AS11 / D6 备选 C；仅 4-3）
  * `S-ABL-TIEBREAK`       —— 字面 ε 加权式 vs 字典序提交解（AS21；仅 4-2）
  * `S-ABL-ETA-PLACE`      —— η 作用位置四情景（AS04，固定上限；仅 4-2）
信息集纪律（`A8-(b)` / `AS07` / `AS11`）：决策层一律只用 `≤ d−1` 的历史实际价（`4-3` 的调整层额外可用当日已实现部分），结算一律用附件 4 实际价；**禁止**出现「全天电价已知」类表述。`C-ANCHOR-P03` 是唯一
使用附件 1 的对照，且**只替换价格**（退化情景复现锚点，团队勘误 `E-F4`），不进入任何交付值。
退出码：0 正常；2 求解未达最优；3 输入/路径非法；4 硬检查或强制闸门失败；5 墙钟预算耗尽。"""
# ruff: noqa: E501
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, csr_matrix

# ---------------------------------------------------------------------------
# 只读导入 accepted 主口径代码（不改动）
# ---------------------------------------------------------------------------
_THIS = Path(__file__).resolve()
for _candidate in (_THIS, *_THIS.parents):
    if (_candidate / "pyproject.toml").is_file() and (_candidate / "AGENTS.md").is_file():
        PROJECT_ROOT = _candidate
        break
else:  # pragma: no cover
    raise RuntimeError("无法定位项目根目录")

VERSION_DIR = PROJECT_ROOT / "problems/microgrid_2025/prob04/versions/assumption_v001"
ACCEPTED_CODE = VERSION_DIR / "code"
ABLATION_ROOT = VERSION_DIR / "ablations"
sys.path.insert(0, str(ACCEPTED_CODE))

import prob04_model as M  # noqa: E402
import prob04_predict as P  # noqa: E402
from prob04_io import (  # noqa: E402
    InputValidationError,
    read_attachment2,
    read_attachment3,
    read_attachment4_price,
    write_json,
)

CHAIN_42 = "4-2"
CHAIN_43 = "4-3"
EXIT_OK = 0
EXIT_SOLVER_NOT_OPTIMAL = 2
EXIT_INPUT_INVALID = 3
EXIT_HARD_CHECK_FAILED = 4
EXIT_BUDGET_EXCEEDED = 5

D_REQ_START = 31
N = M.PERIODS_PER_DAY
DAYS_FULL = M.DAYS_FULL
SEED = 20260911

SPEC_DATES = [
    ("2025-03-20", 78),
    ("2025-06-21", 171),
    ("2025-09-23", 265),
    ("2025-12-21", 354),
    ("2025-02-15", 45),
    ("2025-04-15", 104),
    ("2025-05-15", 134),
    ("2025-07-15", 195),
    ("2025-08-15", 226),
    ("2025-10-15", 287),
    ("2025-11-15", 318),
    ("2025-12-05", 338),
]
SPEC_DAY_INDEX = [item[1] for item in SPEC_DATES]
SPEC_DATE_BY_INDEX = {index: name for name, index in SPEC_DATES}

TOL_ANCHOR_REL = 1e-9
TOL_BASELINE_REL = 1e-9
TOL_RH_GATE_REL = 1e-9
TOL_STATE_ABS = 1e-6
TOL_SPILL_ABLATION_REL = 1e-6
SEASONAL_RECENT_DAYS = 7
SVAR_SCENARIOS = 24
SVAR_RH_HORIZON = 3

ANCHOR_P03 = {
    "D_full_C_total": 16179176.145228,
    "D_req_C_total": 14540616.335652,
    "D_full_C_plan": 13885669.475555,
    "D_full_C_adj": 563098.132533,
    "D_full_C_em": 1730408.537141,
    "D_req_sum_q_em": 391274.485914,
}

BASE_RUN002 = {
    CHAIN_42: {
        "D_full_C_total": 14755884.322036,
        "D_req_C_total": 13006411.041148,
        "D_req_sum_q_em": 0.0,
        "D_full_sum_q_em": 0.0,
    },
    CHAIN_43: {
        "D_full_C_total": 17181202.515506,
        "D_req_C_total": 15289050.714738,
        "D_req_sum_q_em": 394026.040750,
        "D_full_sum_q_em": 410453.995927,
    },
}

BLACKLIST_PHRASES = ("全天电价已知", "已知全天价格", "电价全天已知", "已知全天电价")


# ---------------------------------------------------------------------------
# 基础设施
# ---------------------------------------------------------------------------
def _resolve(text: str) -> Path:
    path = Path(text)
    return path if path.is_absolute() else (PROJECT_ROOT / path)


def _guard_output(output_dir: Path) -> None:
    """路径自证断言：任何模式都禁止写 `data/`、accepted `code/` 与交付结果目录。"""
    out = output_dir.resolve()
    for forbidden in (
        PROJECT_ROOT / "data",
        ACCEPTED_CODE,
        VERSION_DIR / "results",
    ):
        item = forbidden.resolve()
        if out == item or item in out.parents:
            raise SystemExit(f"[ablation] 输出路径越界（禁止写 {item}）：{out}")
    allowed = ABLATION_ROOT.resolve()
    if allowed not in out.parents and out != allowed:
        raise SystemExit(f"[ablation] 输出必须位于 {allowed} 之下：{out}")


def code_fingerprint(directory: Path) -> dict[str, str]:
    digest = hashlib.sha256()
    files: dict[str, str] = {}
    for path in sorted(directory.glob("*.py")):
        payload = path.read_bytes()
        files[path.name] = hashlib.sha256(payload).hexdigest()
        digest.update(path.name.encode("utf-8"))
        digest.update(payload)
    files["__code_dir__"] = digest.hexdigest()
    return files


def md5_of(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


class Budget:
    def __init__(self, max_wall_seconds: float) -> None:
        self.started = time.perf_counter()
        self.max_wall = float(max_wall_seconds)
        self.records: list[dict[str, Any]] = []

    def record(self, label: str, seconds: float) -> None:
        self.records.append({"label": label, "seconds": round(float(seconds), 6)})

    def check(self, message: str) -> None:
        if time.perf_counter() - self.started > self.max_wall:
            raise M.BudgetExceeded(message)

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.started


# ---------------------------------------------------------------------------
# 费用与指标
# ---------------------------------------------------------------------------
def cost_breakdown(result: M.ChainResult, *, actual: bool) -> dict[str, np.ndarray]:
    price = result.price_act if actual else result.price_fc
    b = result.plan_b
    q = result.q
    plan = np.sum(price * b, axis=1)
    if result.chain == CHAIN_43:
        dev_plus = np.maximum(b - q, 0.0)
        dev_minus = np.maximum(q - b, 0.0)
        adj = np.sum(price * (M.BETA_DEF * dev_plus + M.BETA_OVER * dev_minus), axis=1)
    else:
        adj = np.zeros(result.days)
    em = np.sum(M.ALPHA_EM * price * result.q_em, axis=1)
    return {"plan": plan, "adjustment": adj, "emergency": em, "total": plan + adj + em}


def summarize(result: M.ChainResult) -> dict[str, Any]:
    act = cost_breakdown(result, actual=True)
    fc = cost_breakdown(result, actual=False)
    days = result.days
    out: dict[str, Any] = {"days": days, "chain": result.chain}
    for label, sl in (("D_full", slice(0, days)), ("D_req", slice(min(D_REQ_START, days), days))):
        out[label] = {
            "days": int(len(range(*sl.indices(days)))),
            "cost_total_yuan": float(np.sum(act["total"][sl])),
            "cost_plan_yuan": float(np.sum(act["plan"][sl])),
            "cost_adj_yuan": float(np.sum(act["adjustment"][sl])),
            "cost_em_yuan": float(np.sum(act["emergency"][sl])),
            "cost_total_fc_yuan": float(np.sum(fc["total"][sl])),
            "delta_c_price_yuan": float(np.sum((act["total"] - fc["total"])[sl])),
            "delta_c_plan_yuan": float(np.sum((act["plan"] - fc["plan"])[sl])),
            "delta_c_adj_yuan": float(np.sum((act["adjustment"] - fc["adjustment"])[sl])),
            "delta_c_em_yuan": float(np.sum((act["emergency"] - fc["emergency"])[sl])),
            "total_plan_kwh": float(np.sum(result.plan_b[sl])),
            "total_purchase_kwh": float(np.sum(result.q[sl])),
            "total_q_em_kwh": float(np.sum(result.q_em[sl])),
            "total_charge_kwh": float(np.sum(result.c[sl])),
            "total_discharge_kwh": float(np.sum(result.q_dis[sl])),
            "total_spill_kwh": float(np.sum(result.s_settle[sl])),
            "days_with_q_em": int(np.sum(np.sum(result.q_em[sl] > M.TOL, axis=1) > 0)),
            "periods_with_q_em": int(np.count_nonzero(result.q_em[sl] > M.TOL)),
        }
    ends = result.E[:, -1]
    out["state_end_kwh"] = {
        "mean": float(np.mean(ends)),
        "min": float(np.min(ends)),
        "max": float(np.max(ends)),
        "unique": int(np.unique(np.round(ends, 6)).size),
        "days_at_lower_bound": int(np.sum(ends <= M.E_MIN + 1e-6)),
        "sum_abs_span_from_lower_bound_kwh": float(np.sum(np.abs(ends - M.E_MIN))),
    }
    out["bounds"] = {
        "max_charge_kwh": float(np.max(result.c)),
        "max_discharge_kwh": float(np.max(result.q_dis)),
        "max_side_power_kw": float(
            np.max(
                np.maximum.reduce(
                    [
                        result.c / M.DELTA_T,
                        M.ETA_CH * result.c / M.DELTA_T,
                        result.q_dis / M.DELTA_T,
                        result.q_dis / (M.ETA_DIS * M.DELTA_T),
                    ]
                )
            )
        ),
        "storage_min_kwh": float(np.min(result.E)),
        "storage_max_kwh": float(np.max(result.E)),
        "storage_initial_kwh": float(M.state_starts(result)[0]),
    }
    durations: dict[str, float] = {}
    for item in result.layer_records:
        durations[item.layer] = durations.get(item.layer, 0.0) + float(item.seconds)
    out["layer_seconds"] = {key: round(value, 6) for key, value in sorted(durations.items())}
    out["lp_layer_solves"] = len(result.layer_records)
    out["lp_layer_status_max"] = int(max((item.status for item in result.layer_records), default=0))
    out["t7"] = {
        "max_primary_relative_change": float(
            max((item.primary_relative_change for item in result.tiebreak_records), default=0.0)
        ),
        "degenerate_layers": int(sum(1 for item in result.tiebreak_records if item.degeneracy_degree > 0)),
        "layers": len(result.tiebreak_records),
    }
    return out


def cross_checks(result: M.ChainResult) -> dict[str, Any]:
    days = result.days
    starts = M.state_starts(result)
    ends = result.E[:, -1]
    transition = np.abs(
        np.diff(np.concatenate([starts[:, None], result.E], axis=1), axis=1)
        - M.ETA_CH * result.c
        + result.q_dis / M.ETA_DIS
    )
    settlement = np.abs(
        result.q + result.q_em + result.pv_act_energy + result.q_dis - result.load_energy - result.c - result.s_settle
    )
    continuity = np.abs(starts[1:] - ends[:-1]) if days > 1 else np.zeros(0)
    eq_max = max((item.equality_residual_max for item in result.layer_records), default=0.0)
    eq_rel = max((item.equality_residual_relative_max for item in result.layer_records), default=0.0)
    bound_max = max((item.bound_violation_max for item in result.layer_records), default=0.0)
    values = {
        "state_transition_residual_max": float(np.max(transition)) if transition.size else 0.0,
        "settlement_balance_residual_max": float(np.max(settlement)) if settlement.size else 0.0,
        "cross_day_continuity_max": float(np.max(continuity)) if continuity.size else 0.0,
        "layer_equality_residual_max": float(eq_max),
        "layer_equality_residual_relative_max": float(eq_rel),
        "layer_bound_violation_max": float(bound_max),
        "storage_min_kwh": float(np.min(result.E)),
        "storage_max_kwh": float(np.max(result.E)),
        "max_charge_kwh": float(np.max(result.c)),
        "max_discharge_kwh": float(np.max(result.q_dis)),
        "sum_q_em_kwh": float(np.sum(result.q_em)),
        "min_plan_purchase_kwh": float(np.min(result.plan_b)),
        "simultaneous_charge_discharge_periods": int(np.count_nonzero((result.c > M.TOL) & (result.q_dis > M.TOL))),
    }
    thresholds = {
        "state_transition_residual_max": M.TOL,
        "settlement_balance_residual_max": M.TOL,
        "cross_day_continuity_max": M.TOL,
        "layer_equality_residual_max": M.TOL,
        "layer_equality_residual_relative_max": M.LAYER_TOL_RELATIVE,
        "layer_bound_violation_max": M.TOL,
    }
    failed = [
        name
        for name, tol in thresholds.items()
        if (not np.isfinite(values[name])) or values[name] > tol
    ]
    values["checks_failed"] = failed
    values["thresholds"] = thresholds
    return values


# ---------------------------------------------------------------------------
# 输入装载
# ---------------------------------------------------------------------------
def load_inputs(args: argparse.Namespace) -> dict[str, Any]:
    att2 = read_attachment2(_resolve(args.data2), expected_days=DAYS_FULL)
    att4 = read_attachment4_price(_resolve(args.data4), expected_days=DAYS_FULL)
    if att4.time_labels != att2.time_labels:
        raise InputValidationError("附件 4 与附件 2 的 144 个时间列标签不一致（相位不同）")
    if att4.dates != att2.dates:
        raise InputValidationError("附件 4 与附件 2 的日期序列不一致")
    att3 = read_attachment3(_resolve(args.data3), expected_days=DAYS_FULL) if args.data3 else None
    if att3 is not None and att3.dates != att2.dates:
        raise InputValidationError("附件 3 与附件 2 的日期序列不一致")
    return {"att2": att2, "att3": att3, "att4": att4}


def read_attachment1_price(path: Path) -> np.ndarray:
    """读取附件 1 的 144 点单日电价曲线（`C-ANCHOR-P03` 专用；只替换价格）。"""
    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook[workbook.sheetnames[0]]
        rows = [row for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()
    if len(rows) != N + 1:
        raise InputValidationError(f"附件 1 行数 {len(rows)} != 1 + {N}")
    header = ["" if item is None else str(item).strip() for item in rows[0]]
    if header[1] != "电价":
        raise InputValidationError(f"附件 1 第 2 列表头不是「电价」：{header[1]!r}")
    price = np.array([float(row[1]) for row in rows[1:]], dtype=float)
    if price.shape != (N,) or not np.all(np.isfinite(price)) or np.any(price < 0):
        raise InputValidationError("附件 1 电价列形状或取值非法")
    return price


def build_decision_prices(price_act: np.ndarray, days: int, method: str = P.PRIMARY_METHOD):
    matrix = np.empty((days, N))
    fallbacks: list[dict[str, Any]] = []
    for day in range(days):
        item = P.predict(price_act, day, method)
        matrix[day] = np.asarray(item["price"], dtype=float)
        if item["fallback"]:
            fallbacks.append(
                {"day_index": day, "method": method, "marker": str(item["fallback"]),
                 "history_size": int(item["history_size"])}
            )
    return matrix, fallbacks


def seasonal_baselines(att2, days: int) -> dict[str, np.ndarray]:
    """未来日负荷/光伏的两个历史口径（都只用 `≤ d−1` 的信息）。"""
    dates = att2.dates
    months = np.array([int(text[5:7]) for text in dates])
    load = att2.load_kw[:days] * M.DELTA_T
    pv = att2.pv_kw[:days] * M.DELTA_T
    out = {key: np.zeros_like(load) for key in ("month_load", "month_pv", "recent_load", "recent_pv")}
    for day in range(days):
        same = np.where(months[:day] == months[day])[0]
        if same.size == 0:
            same = np.arange(day) if day > 0 else np.array([day])
        out["month_load"][day] = load[same].mean(axis=0)
        out["month_pv"][day] = pv[same].mean(axis=0)
        window = np.arange(max(0, day - SEASONAL_RECENT_DAYS), day)
        if window.size == 0:
            window = np.arange(day) if day > 0 else np.array([day])
        out["recent_load"][day] = load[window].mean(axis=0)
        out["recent_pv"][day] = pv[window].mean(axis=0)
    out["months"] = months
    return out


def make_chain_inputs(chain: str, att2, att3, att4, *, price_act: np.ndarray | None = None,
                      days: int = DAYS_FULL, decision_method: str = P.PRIMARY_METHOD,
                      forecast_basis: str = "month_mean",
                      decision_price: np.ndarray | None = None,
                      reference_seed: bool = False) -> dict[str, Any]:
    if price_act is None:
        price = np.asarray(att4.price[:days], dtype=float)
    else:
        price = np.asarray(price_act[:days], dtype=float)
    fallbacks: list[dict[str, Any]] = []
    if decision_price is not None:
        matrix = np.asarray(decision_price[:days], dtype=float)
    elif reference_seed:
        # `C-ANCHOR-P03` 专用：为 `d = 2025-01-01` 提供「参考日」（价格 = 当天曲线）作为 `H_1`；
        # 使 `PF-PERSIST` 在该日也可用（否则回退为常量中性价 1.0，与 `M1` 的价格口径不同）。
        matrix = np.empty((days, N))
        for day in range(days):
            history = np.vstack([price[day], price[: day + 1]])
            item = P.predict(history, day + 1, P.PRIMARY_METHOD)
            matrix[day] = np.asarray(item["price"], dtype=float)
            if item["fallback"]:
                fallbacks.append({"day_index": day, "method": P.PRIMARY_METHOD,
                                  "marker": str(item["fallback"]), "history_size": int(item["history_size"])})
    else:
        matrix, fallbacks = build_decision_prices(price, days, decision_method)
    inputs: dict[str, Any] = {
        "chain": chain,
        "days": days,
        "price_act": price,
        "decision_price": matrix,
        "fallbacks": fallbacks,
        "load_energy": att2.load_kw[:days] * M.DELTA_T,
        "pv_act_energy": att2.pv_kw[:days] * M.DELTA_T,
        "forecast_kw": {},
        "forecast_energy": {},
        "seasonal": seasonal_baselines(att2, days),
        "forecast_basis": forecast_basis,
    }
    if chain == CHAIN_43:
        raw = {hour: np.vstack([M.downscale(att3.row(day, hour), hour) for day in range(days)])
               for hour in P.DECISION_HOURS}
        inputs["forecast_kw"] = raw
        inputs["forecast_energy"] = {hour: raw[hour] * M.DELTA_T for hour in P.DECISION_HOURS}
    return inputs


def _future_load_pv(inputs: dict[str, Any], day: int, basis: str,
                    horizon_days: int) -> tuple[np.ndarray, np.ndarray]:
    """返回未来 `H−1` 天的日负荷/光伏矩阵（`(H−1, 144)`），口径由 `basis` 决定。"""
    seasonal = inputs["seasonal"]
    key_load = "recent_load" if basis == "recent7" else "month_load"
    key_pv = "recent_pv" if basis == "recent7" else "month_pv"
    future = np.arange(day + 1, min(inputs["days"], day + max(horizon_days, 1)))
    if future.size == 0:
        return np.zeros((0, N)), np.zeros((0, N))
    return seasonal[key_load][future], seasonal[key_pv][future]


# ---------------------------------------------------------------------------
# S-RH：窗口 LP（当天细粒度 + 未来日 1 小时块粒度）
# ---------------------------------------------------------------------------
def window_plan(
    *,
    day: int,
    t0: int,
    horizon_days: int,
    state_before: float,
    fine_price: np.ndarray,
    fine_pv: np.ndarray,
    fine_load: np.ndarray,
    committed_c: np.ndarray,
    committed_q: np.ndarray,
    committed_s: np.ndarray,
    committed_E: np.ndarray,
    future_load: np.ndarray,
    future_pv: np.ndarray,
    price_forward: np.ndarray,
    basis: str,
    time_limit_seconds: float,
    include_q_em: bool = False,
) -> dict[str, Any]:
    """在 `[t0, +H)` 上求解计划层 LP。
    变量序：`b | c | q_dis | s | E`（当天剩余 `n_fine = 144 − t0` 个时段；`include_q_em=True`
    时在该块末尾追加 `q_em`，使 `4-2` 在 `t0 = 0, H = 1` 时与 accepted `solve_day_plan_42`
    的矩阵**逐元素相同**）后接未来日的 1 小时块变量 `b_f | c_f | q_dis_f | s_f | E_f`
    （`n_future_hours = 24(H−1)`）。`t0` 之前的时段以**等式固定**为已提交值。

    **run003 口径修正（plan_v003.md §2）**：两条链的 S-RH 计划窗口一律 `t0 = 0`（`4-3` 的
    计划层同样是 0:00 对全天决策、只提交前 `COMMIT_BLOCK` 个时段）；旧版对 `4-3` 传
    `t0 = COMMIT_BLOCK = 36` 却把「已提交前缀」填为零向量，与 `E ≥ 1200` 的下界直接冲突，
    导致 `H = 1` 的窗口 LP 恒为 infeasible（`status = 2`）。
    """
    n_fine = N - t0
    n_future = int(future_load.shape[0]) * 24
    horizon_effective = 1 + n_future // 24
    has_future = n_future > 0
    fine_block = 6 if include_q_em else 5
    size = fine_block * n_fine + (5 * n_future if has_future else 0)

    b_off = 0
    c_off = n_fine
    q_off = 2 * n_fine
    s_off = 3 * n_fine
    e_off = 4 * n_fine
    qe_off = 5 * n_fine if include_q_em else 0
    if has_future:
        fb_off = fine_block * n_fine
        fc_off = fb_off + n_future
        fq_off = fb_off + 2 * n_future
        fs_off = fb_off + 3 * n_future
        fe_off = fb_off + 4 * n_future
    else:
        fb_off = fc_off = fq_off = fs_off = fe_off = 0

    objective = np.zeros(size)
    objective[b_off : b_off + n_fine] = fine_price[t0:]
    if include_q_em:
        # 与 accepted `solve_day_plan_42` 的 `ALPHA_EM·price` 项逐字对齐（`q_em` 变量必须保留）
        objective[qe_off : qe_off + n_fine] = M.ALPHA_EM * fine_price[t0:]
    if has_future:
        objective[fb_off : fb_off + n_future] = price_forward

    lb = np.zeros(size)
    ub = np.full(size, np.inf)
    ub[c_off : c_off + n_fine] = M.C_CAP
    ub[q_off : q_off + n_fine] = M.Q_CAP
    ub[s_off : s_off + n_fine] = np.maximum(0.0, fine_pv[t0:] - fine_load[t0:])
    lb[e_off : e_off + n_fine] = M.E_MIN
    ub[e_off : e_off + n_fine] = M.E_MAX
    if include_q_em:
        lb[qe_off : qe_off + n_fine] = 0.0  # ub 已为 +inf
    if t0 > 0:
        lb[b_off : b_off + t0] = 0.0
        ub[b_off : b_off + t0] = 0.0
        # 固定前 t0 个时段为已提交值（用等式行，见下）
    if has_future:
        hours = np.arange(n_future)
        d_idx = hours // 24
        h_idx = hours % 24
        block_load = future_load.reshape(future_load.shape[0], 24, 6).sum(axis=2)[d_idx, h_idx]
        block_pv = future_pv.reshape(future_pv.shape[0], 24, 6).sum(axis=2)[d_idx, h_idx]
        ub[fc_off : fc_off + n_future] = M.C_CAP * 6.0
        ub[fq_off : fq_off + n_future] = M.Q_CAP * 6.0
        ub[fs_off : fs_off + n_future] = np.maximum(0.0, block_pv - block_load)
        lb[fe_off : fe_off + n_future] = M.E_MIN
        ub[fe_off : fe_off + n_future] = M.E_MAX

    # 等式：前 t0 行固定提交值；随后为当天的层内平衡 + 状态转移（含未来块）
    eq_rows: list[np.ndarray] = []
    eq_cols: list[np.ndarray] = []
    eq_vals: list[np.ndarray] = []
    rhs: list[float] = []

    # (1) 固定已提交时段（b/c/s/E）为已提交值（用等式行，保证状态链一致）
    if t0 > 0:
        rows_t0 = np.arange(t0)
        for offset, values in (
            (b_off, committed_q[:t0]),
            (c_off, committed_c[:t0]),
            (s_off, committed_s[:t0]),
            (e_off, committed_E[:t0]),
        ):
            eq_rows.append(rows_t0)
            eq_cols.append(offset + rows_t0)
            eq_vals.append(np.ones(t0))
            rhs.extend(float(v) for v in values)
        # q_dis 用 0 界固定（4-3 的 q_dis 由调整层给出，窗口不重优化已提交时段）
        ub[q_off : q_off + t0] = 0.0

    base_row = len(rhs)
    tau = np.arange(n_fine, dtype=np.int64)
    # (2) 当天层内平衡（t0..143）
    eq_rows.append(base_row + tau)
    eq_cols.append(b_off + tau)
    eq_vals.append(np.ones(n_fine))
    eq_rows.append(base_row + tau)
    eq_cols.append(q_off + tau)
    eq_vals.append(np.ones(n_fine))
    eq_rows.append(base_row + tau)
    eq_cols.append(c_off + tau)
    eq_vals.append(-np.ones(n_fine))
    eq_rows.append(base_row + tau)
    eq_cols.append(s_off + tau)
    eq_vals.append(-np.ones(n_fine))
    if include_q_em:
        eq_rows.append(base_row + tau)
        eq_cols.append(qe_off + tau)
        eq_vals.append(np.ones(n_fine))
    rhs.extend(float(v) for v in (fine_load - fine_pv)[t0:])
    # (3) 状态转移：E_j − η c_j + q_dis_j/η − E_{j−1} = 0（j = 0 的 E_{j−1} 换为 state_before）
    t_rows = base_row + n_fine + tau
    eq_rows.append(t_rows)
    eq_cols.append(e_off + tau)
    eq_vals.append(np.ones(n_fine))
    eq_rows.append(t_rows)
    eq_cols.append(c_off + tau)
    eq_vals.append(-M.ETA_CH * np.ones(n_fine))
    eq_rows.append(t_rows)
    eq_cols.append(q_off + tau)
    eq_vals.append((1.0 / M.ETA_DIS) * np.ones(n_fine))
    if n_fine > 1:
        eq_rows.append(t_rows[1:])
        eq_cols.append(e_off + tau[:-1])
        eq_vals.append(-np.ones(n_fine - 1))
    rhs.append(float(state_before))
    rhs.extend([0.0] * (n_fine - 1))
    if has_future:
        hours = np.arange(n_future, dtype=np.int64)
        f_bal_rows = base_row + 2 * n_fine + hours
        # 未来块平衡：
        eq_rows.append(f_bal_rows)
        eq_cols.append(fb_off + hours)
        eq_vals.append(np.ones(n_future))
        eq_rows.append(f_bal_rows)
        eq_cols.append(fq_off + hours)
        eq_vals.append(np.ones(n_future))
        eq_rows.append(f_bal_rows)
        eq_cols.append(fc_off + hours)
        eq_vals.append(-np.ones(n_future))
        eq_rows.append(f_bal_rows)
        eq_cols.append(fs_off + hours)
        eq_vals.append(-np.ones(n_future))
        d_idx = hours // 24
        h_idx = hours % 24
        block_load = future_load.reshape(future_load.shape[0], 24, 6).sum(axis=2)[d_idx, h_idx]
        block_pv = future_pv.reshape(future_pv.shape[0], 24, 6).sum(axis=2)[d_idx, h_idx]
        rhs.extend(float(v) for v in (block_load - block_pv))
        # 未来块状态转移（1 小时步；块内 c 为 6 个 10 分钟之和）
        ft_rows = base_row + 2 * n_fine + n_future + hours
        eq_rows.append(ft_rows)
        eq_cols.append(fe_off + hours)
        eq_vals.append(np.ones(n_future))
        eq_rows.append(ft_rows)
        eq_cols.append(fc_off + hours)
        eq_vals.append(-M.ETA_CH * np.ones(n_future))
        eq_rows.append(ft_rows)
        eq_cols.append(fq_off + hours)
        eq_vals.append((1.0 / M.ETA_DIS) * np.ones(n_future))
        if n_future > 1:
            eq_rows.append(ft_rows[1:])
            eq_cols.append(fe_off + hours[:-1])
            eq_vals.append(-np.ones(n_future - 1))
        if n_fine > 0:
            eq_rows.append(ft_rows[:1])
            eq_cols.append(np.array([e_off + n_fine - 1]))
            eq_vals.append(np.array([-1.0]))
        rhs.extend([0.0] * n_future)

    n_rows = len(rhs)
    a_eq = coo_matrix(
        (np.concatenate(eq_vals), (np.concatenate(eq_rows), np.concatenate(eq_cols))), shape=(n_rows, size)
    ).tocsr()
    bounds = np.stack([lb, ub], axis=1)
    # **必须复用 AS21 的共享求解器**（`T7-5`）：否则同一最优面上的不同解会使 `H = 1` 无法
    # 逐位复现主口径（`C3` 闸门），且会污染 `H` 的单调性判据。
    # 次目标与 ε 尺度**逐字对齐主口径的层定义**（`Σ(c+q_dis)`、`throughput_scale(144)`）。
    throughput = np.zeros(size)
    throughput[c_off : c_off + n_fine] = 1.0
    throughput[q_off : q_off + n_fine] = 1.0
    if has_future:
        throughput[fc_off : fc_off + n_future] = 1.0 / 6.0
        throughput[fq_off : fq_off + n_future] = 1.0 / 6.0
    result, record, tiebreak = M._solve_with_tiebreak(
        primary_objective=objective,
        throughput_objective=throughput,
        scale=M.throughput_scale(N),
        a_eq=a_eq,
        b_eq=np.asarray(rhs, dtype=float),
        a_ub=None,
        b_ub=None,
        bounds=bounds,
        layer="srh_window",
        day=day,
        hour=0,
        boundary_index=5 * n_fine - 1,
        time_limit_seconds=time_limit_seconds,
    )
    seconds = float(record.seconds)
    if result.x is None or int(record.status) != 0:
        raise M.LayerFailure(
            f"S-RH 窗口 LP 未达最优（day={day}, t0={t0}, H={horizon_days}, status={record.status}）",
            day=day, hour=0, status=int(record.status),
        )
    x = np.asarray(result.x, dtype=float)
    return {
        "b": x[b_off : b_off + n_fine],
        "c": x[c_off : c_off + n_fine],
        "q_dis": x[q_off : q_off + n_fine],
        "s": x[s_off : s_off + n_fine],
        "E": x[e_off : e_off + n_fine],
        "q_em": (x[qe_off : qe_off + n_fine] if include_q_em else None),
        "objective": float(np.dot(objective, x)),
        "seconds": seconds,
        "variables": int(size),
        "equality_rows": int(n_rows),
        "future_days": int(max(horizon_effective - 1, 0)),
        "horizon_requested_days": int(horizon_days),
        "horizon_effective_days": int(horizon_effective),
        "terminal_window_truncated": bool(horizon_effective < horizon_days),
        "granularity": "current_day_10min + future_days_1hour_block",
        "future_load_pv_basis": basis,
        "price_forward_basis": "PF-PERSIST（p^{act}_{d−1,·}，只用 ≤ d−1 的历史）",
        "future_price_used_in_commitment": False,
        "tiebreak": {
            "committed_solution": tiebreak.committed_solution,
            "primary_relative_change": float(tiebreak.primary_relative_change),
            "throughput_kwh": float(tiebreak.throughput_kwh),
            "degeneracy_degree": int(tiebreak.degeneracy_degree),
        },
    }


def run_rh(chain: str, inputs: dict[str, Any], horizon_days: int, *, time_limit_seconds: float,
           budget: Budget) -> dict[str, Any]:
    days = inputs["days"]
    price_act = inputs["price_act"]
    decision_price = inputs["decision_price"]
    load = inputs["load_energy"]
    pv_act = inputs["pv_act_energy"]
    basis = inputs["forecast_basis"]
    shape = (days, N)
    plan_b = np.zeros(shape)
    plan_c = np.zeros(shape)
    plan_q_dis = np.zeros(shape)
    plan_s = np.zeros(shape)
    plan_E = np.zeros(shape)
    plan_q_em = np.zeros(shape)
    q = np.zeros(shape)
    c = np.zeros(shape)
    q_dis = np.zeros(shape)
    state = np.zeros(shape)
    price_fc = np.zeros(shape)
    kappa_records: list[dict[str, Any]] = []
    windows: list[dict[str, Any]] = []
    layer_seconds: dict[str, float] = {"plan": 0.0, "adjustment6": 0.0, "adjustment12": 0.0, "adjustment18": 0.0}
    lp_solves = 0
    e_prev = M.E_INIT

    for day in range(days):
        budget.check(f"S-RH({chain}) 墙钟预算耗尽：已完成 {day}/{days} 天")
        t0 = 0
        include_q_em = chain == CHAIN_42
        fine_pv = pv_act[day] if chain == CHAIN_42 else inputs["forecast_energy"][0][day]
        future_load, future_pv = _future_load_pv(inputs, day, basis, horizon_days)
        lag_price = price_act[day - 1] if day - 1 >= 0 else P.fallback_price()
        n_future = 24 * len(future_load)
        price_forward = (np.tile(lag_price.reshape(-1, 24, 6).mean(axis=2), len(future_load))
                         if n_future else np.zeros(0))
        window = window_plan(
            day=day, t0=t0, horizon_days=horizon_days, state_before=e_prev,
            fine_price=decision_price[day], fine_pv=fine_pv, fine_load=load[day],
            committed_c=plan_c[day], committed_q=q[day], committed_s=plan_s[day], committed_E=plan_E[day],
            future_load=future_load, future_pv=future_pv, price_forward=price_forward,
            basis=basis, time_limit_seconds=time_limit_seconds, include_q_em=include_q_em,
        )
        budget.record(f"rh_{chain}_H{horizon_days}_plan_day{day}", window["seconds"])
        layer_seconds["plan"] += window["seconds"]
        lp_solves += 1
        # 计划层变量**全量**落盘（与 accepted 主口径一致：`plan_*` 记录整日计划，
        # 只有 `4-3` 的前 `COMMIT_BLOCK` 个时段进入提交量 `q/c/q_dis/state`；
        # 调整层的偏差结算以整日 `plan_b` 为基准，故 `plan_b` 的尾部**不得**留零）。
        plan_b[day] = window["b"]
        plan_c[day] = window["c"]
        plan_q_dis[day] = window["q_dis"]
        plan_s[day] = window["s"]
        plan_E[day] = window["E"]
        if window.get("q_em") is not None:
            plan_q_em[day] = window["q_em"]
        commit = slice(0, M.COMMIT_BLOCK) if chain == CHAIN_43 else slice(0, N)
        q[day, commit] = plan_b[day, commit]
        c[day, commit] = plan_c[day, commit]
        q_dis[day, commit] = plan_q_dis[day, commit]
        state[day, commit] = plan_E[day, commit]
        windows.append(
            {k: window[k] for k in ("objective", "seconds", "variables", "equality_rows", "future_days",
                                    "horizon_requested_days", "horizon_effective_days",
                                    "terminal_window_truncated", "granularity", "future_load_pv_basis",
                                    "price_forward_basis")}
        )
        if chain == CHAIN_43:
            schedule = P.kappa_schedule(price_act, day)
            kappas = {int(key): float(value) for key, value in schedule["kappa"].items()}
            kappa_records.extend(schedule["records"])
            price_fc[day] = P.belief_price(price_act, day, kappas)
            for hour in (6, 12, 18):
                budget.check(f"S-RH(4-3) 墙钟预算耗尽：day={day}, hour={hour}")
                layer_price = P.layer_price(price_act, day, hour, float(kappas[hour]))
                layer, record, _ = M.solve_adjustment_layer_43(
                    hour=hour, price=layer_price, load_energy=load[day],
                    pv_fc_energy=inputs["forecast_energy"][hour][day], plan_b=plan_b[day],
                    e_start=float(state[day, 6 * hour - 1]), time_limit_seconds=time_limit_seconds, day=day,
                )
                if record.status != 0 or not layer:
                    raise M.LayerFailure(
                        f"S-RH(4-3) 调整层未达最优（day={day}, hour={hour}, status={record.status}）",
                        day=day, hour=hour, status=int(record.status),
                    )
                layer_seconds[f"adjustment{hour}"] += float(record.seconds)
                lp_solves += 1
                slot = slice(6 * hour, 6 * hour + M.COMMIT_BLOCK)
                q[day, slot] = layer["q"][0:M.COMMIT_BLOCK]
                c[day, slot] = layer["c"][0:M.COMMIT_BLOCK]
                q_dis[day, slot] = layer["q_dis"][0:M.COMMIT_BLOCK]
                state[day, slot] = layer["E"][0:M.COMMIT_BLOCK]
        else:
            price_fc[day] = decision_price[day]
        e_prev = float(state[day, -1])

    residual_all = q + q_dis + pv_act - load - c
    result = M.ChainResult(
        chain=chain, days=days, price_act=price_act, price_fc=price_fc, decision_price=decision_price,
        load_energy=load, pv_act_energy=pv_act, plan_b=plan_b, q=q, c=c, q_dis=q_dis, E=state,
        q_em=np.maximum(-residual_all, 0.0), s_settle=np.maximum(residual_all, 0.0),
        plan_c=plan_c, plan_q_dis=plan_q_dis, plan_s=plan_s, plan_E=plan_E, plan_q_em=plan_q_em,
        layer_records=[], tiebreak_records=[], kappa_records=kappa_records,
        layer_pv_energy=({hour: inputs["forecast_energy"][hour] for hour in P.DECISION_HOURS}
                         if chain == CHAIN_43 else {0: pv_act}),
    )
    return {
        "result": result,
        "windows": windows,
        "solver_seconds": float(sum(item["seconds"] for item in windows) + sum(layer_seconds.values())),
        "layer_seconds": {key: round(value, 6) for key, value in layer_seconds.items()},
        "lp_solves": lp_solves,
        "max_variables": int(max(item["variables"] for item in windows)),
    }


# ---------------------------------------------------------------------------
# S-VAR：两阶段随机（24 场景，确定性等价）
# ---------------------------------------------------------------------------
def build_scenarios(price_act: np.ndarray, day: int, count: int = SVAR_SCENARIOS) -> dict[str, Any]:
    available = int(np.asarray(price_act).shape[0])
    pool = np.array([d for d in range(min(day, available)) if d % 7 == day % 7], dtype=int)
    pool_kind = "same_weekday_type"
    if pool.size == 0 or pool.size < count:
        pool = np.arange(min(day, available), dtype=int)
        pool_kind = "all_prior_days" if pool.size >= count else "short_history_reused"
    with_replacement = bool(pool.size < count)
    idx = pool[np.floor(np.arange(count) * pool.size / count).astype(int)] if pool.size else np.zeros(count, dtype=int)
    return {
        "day_index": int(day),
        "count": int(count),
        "pool_kind": pool_kind,
        "pool_size": int(pool.size),
        "with_replacement": with_replacement,
        "source_day_indices": [int(item) for item in idx],
        "lookahead_free": bool(np.all(idx < day)),
        "prices": price_act[idx] if pool.size else np.zeros((count, N)),
    }


def _svar_common_equalities(s_count: int, offsets: list[tuple[int, ...]], load: np.ndarray, pv_act: np.ndarray,
                            e_start: float, size: int) -> tuple[csr_matrix, np.ndarray]:
    """逐场景构造 `2 × N` 条等式（每个场景占**独立**的行块 `[2Ns, 2Ns + 2N)`）。

    **run003 修正（plan_v003.md §2）**：旧版对每个场景都复用行号 `0..2N-1`，`coo_matrix` 把
    不同场景的系数**求和**到同一行，而 `b_eq` 仍是 `2N·s_count` 长度 ⇒ 第 `2N` 行之后全为零行
    配非零右端，`4-3` 的 S-VAR 确定性等价 LP **恒 infeasible**（`status = 2`）。
    """
    tau = np.arange(N, dtype=np.int64)
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    vals: list[np.ndarray] = []
    rhs: list[np.ndarray] = []
    for s, offset in enumerate(offsets):
        q_off, c_off, qd_off, sp_off, e_off = offset[:5]
        row0 = 2 * N * s
        rows += [row0 + tau, row0 + tau, row0 + tau, row0 + tau]
        cols += [q_off + tau, qd_off + tau, c_off + tau, sp_off + tau]
        vals += [np.ones(N), np.ones(N), -np.ones(N), -np.ones(N)]
        rows += [row0 + N + tau, row0 + N + tau, row0 + N + tau[1:], row0 + N + tau]
        cols += [e_off + tau, c_off + tau, e_off + tau[1:] - 1, qd_off + tau]
        vals += [np.ones(N), -M.ETA_CH * np.ones(N), -np.ones(N - 1), (1.0 / M.ETA_DIS) * np.ones(N)]
        rhs.append(np.concatenate([load - pv_act, np.concatenate([[e_start], np.zeros(N - 1)])]))
    a_eq = coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(2 * N * s_count, size)
    ).tocsr()
    return a_eq, np.concatenate(rhs)


def _svar42_equivalent(scenario: dict[str, Any], *, load: np.ndarray, pv_act: np.ndarray, e_start: float,
                       time_limit_seconds: float) -> dict[str, Any]:
    """链 4-2 的 S-VAR 确定性等价：第一阶段 `b` 共用；第二阶段 `c/q_dis/s/q_em/E`。
    变量序：`b(144) | [每场景 c, q_dis, s, q_em, E]`（每场景 `5 × 144`）。
    平衡式 `b + q_dis + q_em − c − s = L·Δt − PV·Δt`；状态转移 `E_j − E_{j−1} − η c_j + q_dis_j/η = 0`。
    """
    s_count = scenario["count"]
    prices = scenario["prices"]
    per_scenario_block = 5 * N
    size = N + per_scenario_block * s_count
    objective = np.zeros(size)
    objective[0:N] = prices.mean(axis=0)
    lb = np.zeros(size)
    ub = np.full(size, np.inf)
    lb[0:N] = 0.0
    ub[0:N] = np.inf
    offsets: list[tuple[int, int, int, int, int, int]] = []
    for s in range(s_count):
        base = N + s * per_scenario_block
        c_off = base
        qd_off = base + N
        sp_off = base + 2 * N
        qe_off = base + 3 * N
        e_off = base + 4 * N
        offsets.append((c_off, qd_off, sp_off, qe_off, e_off))
        ub[c_off : c_off + N] = M.C_CAP
        ub[qd_off : qd_off + N] = M.Q_CAP
        ub[sp_off : sp_off + N] = np.maximum(0.0, pv_act - load)
        ub[qe_off : qe_off + N] = np.inf
        lb[e_off : e_off + N] = M.E_MIN
        ub[e_off : e_off + N] = M.E_MAX
        objective[qe_off : qe_off + N] = M.ALPHA_EM * prices[s] / s_count
    tau = np.arange(N, dtype=np.int64)
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    vals: list[np.ndarray] = []
    rhs: list[np.ndarray] = []
    for s in range(s_count):
        c_off, qd_off, sp_off, qe_off, e_off = offsets[s]
        row0 = 2 * N * s
        # 平衡：b + q_dis + q_em − c − s = L·Δt − PV·Δt
        rows += [row0 + tau, row0 + tau, row0 + tau, row0 + tau, row0 + tau]
        cols += [tau, qd_off + tau, qe_off + tau, c_off + tau, sp_off + tau]
        vals += [np.ones(N), np.ones(N), np.ones(N), -np.ones(N), -np.ones(N)]
        # 状态转移（行号 `row0 + N + tau`；同一行承载 E_{j−1} 与 E_j）
        rows += [row0 + N + tau, row0 + N + tau, row0 + N + tau[1:], row0 + N + tau]
        cols += [e_off + tau, c_off + tau, e_off + tau[1:] - 1, qd_off + tau]
        vals += [np.ones(N), -M.ETA_CH * np.ones(N), -np.ones(N - 1), (1.0 / M.ETA_DIS) * np.ones(N)]
        rhs.append(np.concatenate([load - pv_act, np.concatenate([[e_start], np.zeros(N - 1)])]))
    a_eq = coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(2 * N * s_count, size)
    ).tocsr()
    bounds = np.stack([lb, ub], axis=1)
    b_eq_vec = np.concatenate(rhs)
    started = time.perf_counter()
    res = linprog(objective, A_eq=a_eq, b_eq=b_eq_vec, bounds=bounds, method="highs",
                  options={"time_limit": float(time_limit_seconds), "presolve": True})
    seconds = time.perf_counter() - started
    if res.x is None:
        raise M.LayerFailure(f"S-VAR(4-2) 确定性等价 LP 未达最优（status={res.status}）",
                             day=-1, hour=-1, status=int(res.status))
    x = np.asarray(res.x, dtype=float)
    b = x[0:N]
    per_scenario = []
    for s in range(s_count):
        c_off, qd_off, sp_off, qe_off, e_off = offsets[s]
        c_s = x[c_off : c_off + N]
        qd_s = x[qd_off : qd_off + N]
        qe_s = x[qe_off : qe_off + N]
        e_s = x[e_off : e_off + N]
        plan = float(np.sum(prices[s] * b))
        em = float(np.sum(M.ALPHA_EM * prices[s] * qe_s))
        per_scenario.append(
            {
                "scenario": s,
                "source_day_index": int(scenario["source_day_indices"][s]),
                "cost_plan_yuan": plan,
                "cost_adj_yuan": 0.0,
                "cost_em_yuan": em,
                "cost_total_yuan": plan + em,
                "sum_q_em_kwh": float(np.sum(qe_s)),
                "sum_charge_kwh": float(np.sum(c_s)),
                "sum_discharge_kwh": float(np.sum(qd_s)),
                "state_end_kwh": float(e_s[-1]),
            }
        )
    packed = _pack_svar(b, per_scenario, res, seconds, size, int(a_eq.shape[0]), 0)
    packed["residuals"] = _lp_residuals(x=x, a_eq=a_eq, b_eq=b_eq_vec, bounds=bounds)
    return packed


def _svar43_equivalent(scenario: dict[str, Any], *, load: np.ndarray, pv_act: np.ndarray, e_start: float,
                       time_limit_seconds: float) -> dict[str, Any]:
    """链 4-3 的 S-VAR 确定性等价：`b` 共用；`q`（最终量）、`u⁺/u⁻`、`c/q_dis/s/E/q_em` 按场景。"""
    s_count = scenario["count"]
    prices = scenario["prices"]
    n_core = 5 * N * s_count
    n_extra = 3 * N * s_count
    total = N + n_core + n_extra
    objective = np.zeros(total)
    objective[0:N] = prices.mean(axis=0)
    lb = np.zeros(total)
    ub = np.full(total, np.inf)
    offsets: list[tuple[int, ...]] = []
    for s in range(s_count):
        base = N + s * 5 * N
        q_off, c_off, qd_off, sp_off, e_off = base, base + N, base + 2 * N, base + 3 * N, base + 4 * N
        offsets.append((q_off, c_off, qd_off, sp_off, e_off))
        ub[c_off : c_off + N] = M.C_CAP
        ub[qd_off : qd_off + N] = M.Q_CAP
        ub[sp_off : sp_off + N] = np.maximum(0.0, pv_act - load)
        lb[e_off : e_off + N] = M.E_MIN
        ub[e_off : e_off + N] = M.E_MAX
    up_base = N + n_core
    um_base = up_base + N * s_count
    qe_base = um_base + N * s_count
    for s in range(s_count):
        objective[up_base + s * N : up_base + (s + 1) * N] = prices[s] * M.BETA_DEF / s_count
        objective[um_base + s * N : um_base + (s + 1) * N] = prices[s] * M.BETA_OVER / s_count
        objective[qe_base + s * N : qe_base + (s + 1) * N] = M.ALPHA_EM * prices[s] / s_count
    a_eq, b_eq = _svar_common_equalities(s_count, offsets, load, pv_act, e_start, total)
    # 追加 `q_em` 到层内平衡：q + q_dis − c − s + q_em = L·Δt − PV·Δt
    tau = np.arange(N, dtype=np.int64)
    extra_rows: list[np.ndarray] = []
    extra_cols: list[np.ndarray] = []
    extra_vals: list[np.ndarray] = []
    for s in range(s_count):
        row0 = 2 * N * s
        extra_rows.append(row0 + tau)
        extra_cols.append(qe_base + s * N + tau)
        extra_vals.append(np.ones(N))
    a_eq = (a_eq + coo_matrix((np.concatenate(extra_vals),
                               (np.concatenate(extra_rows), np.concatenate(extra_cols))),
                              shape=(2 * N * s_count, total))).tocsr()
    # 不等式（**run003 修正，plan_v003.md §2**）：必须与 accepted
    # `solve_adjustment_layer_43` / formulation `(AD-3)` 的方向**逐字一致**，且**逐时段一行**：
    #   u⁺ ≥ b − q（计划缺额，系数 `β_def = 0.5`）；u⁻ ≥ q − b（超计划购电，系数 `β_over = 1.5`）。
    # 旧版两处都错：(i) 把两者写反（`u⁺ ≥ q − b`、`u⁻ ≥ b − q`）⇒ `0.5×`/`1.5×` 两段互换；
    # (ii) 每个场景的 N 个时段共用**同一行**（整数行号），把逐时段约束聚合成一条和式约束，
    # 且行数与 `b_ub` 长度不一致（`linprog` 直接报 `b_ub must be a 1-D array`）。
    ub_rows: list[np.ndarray] = []
    ub_cols: list[np.ndarray] = []
    ub_vals: list[np.ndarray] = []
    for s in range(s_count):
        q_off = offsets[s][0]
        up = up_base + s * N
        um = um_base + s * N
        row0 = 2 * N * s
        # b − q − u⁺ ≤ 0  ⇔  u⁺ ≥ b − q（计划缺额，β_def）
        ub_rows += [row0 + tau, row0 + tau, row0 + tau]
        ub_cols += [tau, q_off + tau, up + tau]
        ub_vals += [np.ones(N), -np.ones(N), -np.ones(N)]
        # q − b − u⁻ ≤ 0  ⇔  u⁻ ≥ q − b（超计划，β_over）
        ub_rows += [row0 + N + tau, row0 + N + tau, row0 + N + tau]
        ub_cols += [q_off + tau, tau, um + tau]
        ub_vals += [np.ones(N), -np.ones(N), -np.ones(N)]
    ub_rhs = np.zeros(2 * N * s_count)
    a_ub = coo_matrix((np.concatenate(ub_vals), (np.concatenate(ub_rows), np.concatenate(ub_cols))),
                      shape=(2 * N * s_count, total)).tocsr()
    bounds = np.stack([lb, ub], axis=1)
    started = time.perf_counter()
    res = linprog(objective, A_eq=a_eq, b_eq=b_eq, A_ub=a_ub, b_ub=ub_rhs, bounds=bounds,
                  method="highs", options={"time_limit": float(time_limit_seconds), "presolve": True})
    seconds = time.perf_counter() - started
    if res.x is None:
        raise M.LayerFailure(f"S-VAR(4-3) 确定性等价 LP 未达最优（status={res.status}）",
                             day=-1, hour=-1, status=int(res.status))
    x = np.asarray(res.x, dtype=float)
    b = x[0:N]
    per_scenario = []
    for s in range(s_count):
        q_off = offsets[s][0]
        q_s = x[q_off : q_off + N]
        up_s = x[up_base + s * N : up_base + (s + 1) * N]
        um_s = x[um_base + s * N : um_base + (s + 1) * N]
        qe_s = x[qe_base + s * N : qe_base + (s + 1) * N]
        plan = float(np.sum(prices[s] * b))
        adj = float(np.sum(prices[s] * (M.BETA_DEF * up_s + M.BETA_OVER * um_s)))
        em = float(np.sum(M.ALPHA_EM * prices[s] * qe_s))
        per_scenario.append(
            {
                "scenario": s,
                "source_day_index": int(scenario["source_day_indices"][s]),
                "cost_plan_yuan": plan,
                "cost_adj_yuan": adj,
                "cost_em_yuan": em,
                "cost_total_yuan": plan + adj + em,
                "sum_q_em_kwh": float(np.sum(qe_s)),
                "sum_purchase_kwh": float(np.sum(q_s)),
            }
        )
    packed = _pack_svar(b, per_scenario, res, seconds, total, int(a_eq.shape[0]), int(a_ub.shape[0]))
    packed["residuals"] = _lp_residuals(x=x, a_eq=a_eq, b_eq=b_eq, a_ub=a_ub,
                                        b_ub=ub_rhs, bounds=bounds)
    return packed


def _pack_svar(b, per_scenario, res, seconds, variables, equality_rows, inequality_rows) -> dict[str, Any]:
    totals = [item["cost_total_yuan"] for item in per_scenario]
    return {
        "b": b,
        "per_scenario": per_scenario,
        "expected_cost_total_yuan": float(np.mean(totals)),
        "expected_cost_plan_yuan": float(np.mean([item["cost_plan_yuan"] for item in per_scenario])),
        "expected_cost_adj_yuan": float(np.mean([item["cost_adj_yuan"] for item in per_scenario])),
        "expected_cost_em_yuan": float(np.mean([item["cost_em_yuan"] for item in per_scenario])),
        "scenario_cost_std_yuan": float(np.std(totals)),
        "scenario_cost_min_yuan": float(np.min(totals)),
        "scenario_cost_max_yuan": float(np.max(totals)),
        "objective_yuan": float(res.fun),
        "seconds": float(seconds),
        "variables": int(variables),
        "equality_rows": int(equality_rows),
        "inequality_rows": int(inequality_rows),
        "lp_solves": 1,
    }


def _lp_residuals(*, x: np.ndarray, a_eq, b_eq: np.ndarray, a_ub=None, b_ub=None,
                  bounds: np.ndarray | None = None) -> dict[str, float]:
    """S-VAR 确定性等价的**约束满足度证据**（预注册判据 `C8` 的逐 case 残差）。

    旧版只把 S-VAR 的求解状态写进 `solver_status`，未给层等式/不等式/边界残差，使 `C8`
    对这两个对照无法评估；本轮补齐（run003，plan_v003.md §2）。
    """
    eq = float(np.max(np.abs(np.asarray(a_eq @ x).ravel() - np.asarray(b_eq).ravel()))) if a_eq.shape[0] else 0.0
    if a_ub is not None and a_ub.shape[0]:
        iq = float(np.max(np.maximum(np.asarray(a_ub @ x).ravel() - np.asarray(b_ub).ravel(), 0.0)))
    else:
        iq = 0.0
    if bounds is None:
        lo = hi = 0.0
    else:
        lo = float(np.max(np.maximum(bounds[:, 0] - x, 0.0)))
        hi = float(np.max(np.maximum(x - bounds[:, 1], 0.0)))
    worst = max(eq, iq, lo, hi)
    return {
        "equality_residual_max": eq,
        "inequality_residual_max": iq,
        "bound_lower_violation_max": lo,
        "bound_upper_violation_max": hi,
        "worst_residual": float(worst),
        "pass": bool(np.isfinite(worst) and worst <= TOL_STATE_ABS),
    }


def _svar_checks(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """把逐代表日/逐场景的残差聚合成 case 级 `checks`（供 `_walk` 汇总进 `checks_failed`）。"""
    worst = {
        key: max((float(item["residuals"][key]) for item in cases if "residuals" in item), default=0.0)
        for key in ("equality_residual_max", "inequality_residual_max",
                    "bound_lower_violation_max", "bound_upper_violation_max")
    }
    failed = [key for key, value in worst.items() if value > TOL_STATE_ABS]
    return {**worst, "threshold": TOL_STATE_ABS, "checks_failed": failed}


def svar_rh_case(inputs: dict[str, Any], scenario: dict[str, Any], day_index: int, horizon_days: int,
                 e_start: float, time_limit_seconds: float) -> dict[str, Any]:
    """`S-VAR-RH`（仅 `4-2`）：第一阶段 `b` 由「场景均值价 + 窗口前瞻」确定，再逐场景结算。"""
    s_count = scenario["count"]
    prices = scenario["prices"]
    load = inputs["load_energy"][day_index]
    pv_act = inputs["pv_act_energy"][day_index]
    future_load, future_pv = _future_load_pv(inputs, day_index, inputs["forecast_basis"], horizon_days)
    lag_price = inputs["price_act"][day_index - 1] if day_index - 1 >= 0 else P.fallback_price()
    started = time.perf_counter()
    window = window_plan(
        day=day_index, t0=0, horizon_days=horizon_days, state_before=e_start,
        fine_price=prices.mean(axis=0), fine_pv=pv_act, fine_load=load,
        committed_c=np.zeros(N), committed_q=np.zeros(N), committed_s=np.zeros(N), committed_E=np.zeros(N),
        future_load=future_load, future_pv=future_pv,
        price_forward=np.tile(lag_price.reshape(-1, 24, 6).mean(axis=2), max(len(future_load), 0)),
        basis=inputs["forecast_basis"], time_limit_seconds=time_limit_seconds,
    )
    b = window["b"]
    c_s = window["c"]
    qd_s = window["q_dis"]
    residual = b + qd_s + pv_act - load - c_s
    q_em = np.maximum(-residual, 0.0)
    per_scenario = []
    for s in range(s_count):
        plan = float(np.sum(prices[s] * b))
        em = float(np.sum(M.ALPHA_EM * prices[s] * q_em))
        per_scenario.append(
            {
                "scenario": s,
                "source_day_index": int(scenario["source_day_indices"][s]),
                "cost_plan_yuan": plan,
                "cost_adj_yuan": 0.0,
                "cost_em_yuan": em,
                "cost_total_yuan": plan + em,
                "sum_q_em_kwh": float(np.sum(q_em)),
            }
        )
    seconds = time.perf_counter() - started
    packed = _pack_svar(np.asarray(b, dtype=float), per_scenario, type("R", (), {"fun": window["objective"]})(),
                        seconds, window["variables"], window["equality_rows"], 0)
    packed["window_granularity"] = window["granularity"]
    packed["first_stage_objective_note"] = (
        "第一阶段 `b` 由「场景均值价 + 窗口前瞻」确定（`H = 3`），再逐场景按场景价结算（R-1 的「费用进场景」）"
    )
    # C8 残差证据：由窗口返回量直接复算（层内平衡 + 储能界限 + 单步容量界）
    s_win = np.asarray(window["s"], dtype=float)
    e_win = np.asarray(window["E"], dtype=float)
    e_prev_vec = np.concatenate([[e_start], e_win[:-1]])
    packed["residuals"] = {
        "equality_residual_max": float(np.max(np.abs(residual - s_win + q_em))),
        "inequality_residual_max": float(np.max(np.abs(e_win - M.ETA_CH * c_s + qd_s / M.ETA_DIS - e_prev_vec))),
        "bound_lower_violation_max": float(max(np.max(M.E_MIN - e_win), np.max(-c_s), np.max(-qd_s), np.max(-s_win))),
        "bound_upper_violation_max": float(max(np.max(e_win - M.E_MAX),
                                               np.max(c_s - M.C_CAP), np.max(qd_s - M.Q_CAP))),
    }
    packed["residuals"]["pass"] = bool(
        max(packed["residuals"][key] for key in ("equality_residual_max", "inequality_residual_max",
                                                 "bound_lower_violation_max", "bound_upper_violation_max")) <= TOL_STATE_ABS
    )
    return packed


def run_svar(chain: str, inputs: dict[str, Any], *, horizon_days: int, time_limit_seconds: float,
             budget: Budget, variant: str) -> dict[str, Any]:
    load = inputs["load_energy"]
    pv_act = inputs["pv_act_energy"]
    price_act = inputs["price_act"]
    state_reference = inputs.get("state_end")
    cases: list[dict[str, Any]] = []
    started = time.perf_counter()
    day_indices = [index for index in SPEC_DAY_INDEX if index < inputs["days"]]
    for day_index in day_indices:
        budget.check(f"S-VAR 墙钟预算耗尽：已完成 {len(cases)}/12 代表日")
        scenario = build_scenarios(price_act, day_index)
        e_start = float(state_reference[day_index - 1]) if (state_reference is not None and day_index > 0) else M.E_INIT
        if variant == "daily":
            if chain == CHAIN_42:
                outcome = _svar42_equivalent(scenario, load=load[day_index], pv_act=pv_act[day_index],
                                             e_start=e_start, time_limit_seconds=time_limit_seconds)
            else:
                outcome = _svar43_equivalent(scenario, load=load[day_index], pv_act=pv_act[day_index],
                                             e_start=e_start, time_limit_seconds=time_limit_seconds)
        else:
            outcome = svar_rh_case(inputs, scenario, day_index, horizon_days, e_start, time_limit_seconds)
        budget.record(f"svar_{chain}_{variant}_day{day_index}", float(outcome["seconds"]))
        baseline_day = float(inputs["base_day_cost"][day_index])
        base_b = inputs["base_day_plan_b"][day_index]
        diff = np.asarray(outcome["b"], dtype=float) - base_b
        outcome.update(
            {
                "day_index": int(day_index),
                "date": SPEC_DATE_BY_INDEX[day_index],
                "scenario_pool": {
                    "pool_kind": scenario["pool_kind"],
                    "pool_size": scenario["pool_size"],
                    "with_replacement": scenario["with_replacement"],
                    "lookahead_free": scenario["lookahead_free"],
                    "source_day_indices": scenario["source_day_indices"],
                },
                "baseline_point_forecast_cost_yuan": baseline_day,
                "expected_minus_baseline_yuan": float(outcome["expected_cost_total_yuan"] - baseline_day),
                "expected_minus_baseline_pct": float(
                    0.0 if baseline_day == 0 else 100.0 * (outcome["expected_cost_total_yuan"] - baseline_day) / baseline_day
                ),
                "first_stage_plan_kwh": float(np.sum(outcome["b"])),
                "baseline_plan_kwh": float(np.sum(base_b)),
                "plan_shape": {
                    "mean_abs_diff_kwh": float(np.mean(np.abs(diff))),
                    "sum_abs_diff_kwh": float(np.sum(np.abs(diff))),
                    "max_abs_diff_kwh": float(np.max(np.abs(diff))),
                    "block_mean_diff_kwh": [float(np.mean(diff[k * 24 : (k + 1) * 24])) for k in range(6)],
                    "diff": [float(v) for v in diff],
                },
            }
        )
        cases.append(outcome)
    for item in cases:
        item["b"] = [float(value) for value in np.asarray(item["b"]).reshape(-1)]
    total_seconds = time.perf_counter() - started
    expected = float(np.sum([item["expected_cost_total_yuan"] for item in cases]))
    baseline = float(np.sum([item["baseline_point_forecast_cost_yuan"] for item in cases]))
    if not cases:
        return {
            "chain": chain, "variant": variant, "horizon_days": int(horizon_days),
            "representative_days": [], "representative_day_indices": [],
            "scenario_count": SVAR_SCENARIOS, "cases": [],
            "expected_cost_total_yuan": 0.0, "baseline_point_forecast_cost_yuan": 0.0,
            "expected_minus_baseline_yuan": 0.0, "expected_minus_baseline_pct": 0.0,
            "cost_reduction_pct": 0.0,
            "first_stage_shape": {}, "compute": {"lp_solves": 0, "solver_seconds": 0.0,
                                                 "wall_seconds_including_scenario_build": total_seconds,
                                                 "max_variables_case": 0, "max_equality_rows_case": 0},
            "note": "窗口内无代表日（--days 小于首个代表日），本对照跳过",
            "checks": _svar_checks([]),
            "checks_failed": [],
        }
    mean_diff = np.mean(np.stack([np.asarray(item["plan_shape"]["diff"]) for item in cases]), axis=0)
    top = np.argsort(-np.abs(mean_diff))[:12]
    return {
        "chain": chain,
        "variant": variant,
        "horizon_days": int(horizon_days),
        "representative_days": [item["date"] for item in cases],
        "representative_day_indices": day_indices,
        "scenario_count": SVAR_SCENARIOS,
        "scenario_pool_scope_note": (
            "场景池 = 代表日 d 之前（≤ d−1）的同型日（d' mod 7 == d mod 7），确定性等距抽 24 个；池内不足 24 时"
            "退化为全部先前日并允许有放回。该经验分布**只是对照口径**，不是对真实价格分布的估计，也不作为"
            "预测精度的证据（主口径预测器证据见 forecast_backtest.json 与 E-F5 的 MAE/MAPE/P90 报告纪律）。"
        ),
        "mandatory_rewrite_note": (
            "计划购电账单本身场景相关：C_plan^(s) = Σ p^(s)·b（数量共用、费用进场景）；"
            "本实现**不含** c^base·P_plan 项（团队 R-1「必须的改写」）。"
        ),
        "cases": cases,
        "expected_cost_total_yuan": expected,
        "baseline_point_forecast_cost_yuan": baseline,
        "expected_minus_baseline_yuan": expected - baseline,
        "expected_minus_baseline_pct": 0.0 if baseline == 0 else 100.0 * (expected - baseline) / baseline,
        "cost_reduction_pct": 0.0 if baseline == 0 else 100.0 * (baseline - expected) / baseline,
        "first_stage_shape": {
            "mean_abs_diff_kwh": float(np.mean(np.abs(mean_diff))),
            "sum_abs_diff_kwh": float(np.sum(np.abs(mean_diff))),
            "max_abs_diff_kwh": float(np.max(np.abs(mean_diff))),
            "top_periods": [{"period": int(index + 1), "mean_diff_kwh": float(mean_diff[index])} for index in top],
            "block_mean_diff_kwh": [float(np.mean(mean_diff[k * 24 : (k + 1) * 24])) for k in range(6)],
        },
        "compute": {
            "lp_solves": int(sum(item["lp_solves"] for item in cases)),
            "solver_seconds": float(sum(item["seconds"] for item in cases)),
            "wall_seconds_including_scenario_build": float(total_seconds),
            "max_variables_case": int(max(item["variables"] for item in cases)),
            "max_equality_rows_case": int(max(item["equality_rows"] for item in cases)),
        },
        "price_forecast_error_cost_reference": "见 BASE 的 D_req.delta_c_price_yuan（并置披露）",
        "checks": _svar_checks(cases),
        "checks_failed": _svar_checks(cases)["checks_failed"],
    }


# ---------------------------------------------------------------------------
# 结构消融：显式求解包装（不改 accepted 模块）
# ---------------------------------------------------------------------------
def _spill_upper_d9a(pv_slice: np.ndarray, load_slice: np.ndarray) -> np.ndarray:
    del load_slice
    return np.asarray(pv_slice, dtype=float)


def solve_day_plan_42_variant(*, price, load_energy, pv_act_energy, e_start, day, time_limit_seconds,
                              spill_mode: str):
    n = N
    size = 6 * n
    objective = np.zeros(size)
    objective[0:n] = price
    objective[5 * n : 6 * n] = M.ALPHA_EM * price
    spill_upper = (np.maximum(0.0, pv_act_energy - load_energy) if spill_mode == "d9b"
                   else _spill_upper_d9a(pv_act_energy, load_energy))
    bounds = np.empty((size, 2), dtype=float)
    bounds[0:n, 0], bounds[0:n, 1] = 0.0, np.inf
    bounds[n : 2 * n, 0], bounds[n : 2 * n, 1] = 0.0, M.C_CAP
    bounds[2 * n : 3 * n, 0], bounds[2 * n : 3 * n, 1] = 0.0, M.Q_CAP
    bounds[3 * n : 4 * n, 0], bounds[3 * n : 4 * n, 1] = 0.0, spill_upper
    bounds[4 * n : 5 * n, 0], bounds[4 * n : 5 * n, 1] = M.E_MIN, M.E_MAX
    bounds[5 * n : 6 * n, 0], bounds[5 * n : 6 * n, 1] = 0.0, np.inf
    a_eq, b_eq = M._balance_and_state_rows(
        n, size=size, pv_energy=pv_act_energy, load_energy=load_energy, e_start=e_start,
        balance_offsets=(0, n, 2 * n, 3 * n), energy_offset=4 * n,
    )
    extra = coo_matrix((np.ones(n), (np.arange(n), 5 * n + np.arange(n))), shape=(2 * n, size)).tocsr()
    a_eq = (a_eq + extra).tocsr()
    throughput = M.throughput_coefficients(size, n, 2 * n, n)
    result, record, tiebreak = M._solve_with_tiebreak(
        primary_objective=objective, throughput_objective=throughput, scale=M.throughput_scale(n),
        a_eq=a_eq, b_eq=b_eq, a_ub=None, b_ub=None, bounds=bounds, layer="plan42", day=day, hour=0,
        boundary_index=size - n - 1, time_limit_seconds=time_limit_seconds,
    )
    if result.x is None:
        return {}, record, tiebreak
    x = np.asarray(result.x, dtype=float)
    return ({"b": x[0:n], "c": x[n : 2 * n], "q_dis": x[2 * n : 3 * n], "s": x[3 * n : 4 * n],
             "E": x[4 * n : 5 * n], "q_em": x[5 * n : 6 * n]}, record, tiebreak)


def solve_plan_layer_43_variant(*, price, load_energy, pv_fc_energy, e_start, day, time_limit_seconds,
                                spill_mode: str):
    n = N
    size = 5 * n
    objective = np.zeros(size)
    objective[0:n] = price
    spill_upper = (np.maximum(0.0, pv_fc_energy - load_energy) if spill_mode == "d9b"
                   else _spill_upper_d9a(pv_fc_energy, load_energy))
    bounds = np.empty((size, 2), dtype=float)
    bounds[0:n, 0], bounds[0:n, 1] = 0.0, np.inf
    bounds[n : 2 * n, 0], bounds[n : 2 * n, 1] = 0.0, M.C_CAP
    bounds[2 * n : 3 * n, 0], bounds[2 * n : 3 * n, 1] = 0.0, M.Q_CAP
    bounds[3 * n : 4 * n, 0], bounds[3 * n : 4 * n, 1] = 0.0, spill_upper
    bounds[4 * n : 5 * n, 0], bounds[4 * n : 5 * n, 1] = M.E_MIN, M.E_MAX
    a_eq, b_eq = M._balance_and_state_rows(
        n, size=size, pv_energy=pv_fc_energy, load_energy=load_energy, e_start=e_start,
        balance_offsets=(0, n, 2 * n, 3 * n), energy_offset=4 * n,
    )
    throughput = M.throughput_coefficients(size, n, 2 * n, n)
    result, record, tiebreak = M._solve_with_tiebreak(
        primary_objective=objective, throughput_objective=throughput, scale=M.throughput_scale(n),
        a_eq=a_eq, b_eq=b_eq, a_ub=None, b_ub=None, bounds=bounds, layer="plan43", day=day, hour=0,
        boundary_index=size - 1, time_limit_seconds=time_limit_seconds,
    )
    if result.x is None:
        return {}, record, tiebreak
    x = np.asarray(result.x, dtype=float)
    return ({"b": x[0:n], "c": x[n : 2 * n], "q_dis": x[2 * n : 3 * n], "s": x[3 * n : 4 * n],
             "E": x[4 * n : 5 * n]}, record, tiebreak)


def solve_adjustment_layer_43_variant(*, hour, price, load_energy, pv_fc_energy, plan_b, e_start, day,
                                      time_limit_seconds, spill_mode):
    global_index = np.arange(6 * hour + 1, N + 1)
    n = int(global_index.shape[0])
    size = 7 * n
    objective = np.zeros(size)
    objective[5 * n : 6 * n] = M.BETA_DEF * price[global_index - 1]
    objective[6 * n : 7 * n] = M.BETA_OVER * price[global_index - 1]
    pv_slice = pv_fc_energy[global_index - 1]
    load_slice = load_energy[global_index - 1]
    spill_upper = (np.maximum(0.0, pv_slice - load_slice) if spill_mode == "d9b"
                   else _spill_upper_d9a(pv_slice, load_slice))
    bounds = np.empty((size, 2), dtype=float)
    bounds[0:n, 0], bounds[0:n, 1] = 0.0, np.inf
    bounds[n : 2 * n, 0], bounds[n : 2 * n, 1] = 0.0, M.C_CAP
    bounds[2 * n : 3 * n, 0], bounds[2 * n : 3 * n, 1] = 0.0, M.Q_CAP
    bounds[3 * n : 4 * n, 0], bounds[3 * n : 4 * n, 1] = 0.0, spill_upper
    bounds[4 * n : 5 * n, 0], bounds[4 * n : 5 * n, 1] = M.E_MIN, M.E_MAX
    bounds[5 * n : 7 * n, 0], bounds[5 * n : 7 * n, 1] = 0.0, np.inf
    a_eq, b_eq = M._balance_and_state_rows(
        n, size=size, pv_energy=pv_slice, load_energy=load_slice, e_start=e_start,
        balance_offsets=(0, n, 2 * n, 3 * n), energy_offset=4 * n,
    )
    tau = np.arange(n, dtype=np.int64)
    plan_slice = plan_b[global_index - 1]
    a_ub = coo_matrix(
        (np.concatenate([-np.ones(n), -np.ones(n), np.ones(n), -np.ones(n)]),
         (np.concatenate([tau, tau, n + tau, n + tau]),
          np.concatenate([tau, 5 * n + tau, tau, 6 * n + tau]))),
        shape=(2 * n, size),
    ).tocsr()
    b_ub = np.concatenate([-plan_slice, plan_slice])
    throughput = M.throughput_coefficients(size, n, 2 * n, n)
    result, record, tiebreak = M._solve_with_tiebreak(
        primary_objective=objective, throughput_objective=throughput, scale=M.throughput_scale(n),
        a_eq=a_eq, b_eq=b_eq, a_ub=a_ub, b_ub=b_ub, bounds=bounds, layer=f"adjustment{hour}", day=day,
        hour=hour, boundary_index=5 * n - 1, time_limit_seconds=time_limit_seconds,
    )
    if result.x is None:
        return {}, record, tiebreak
    x = np.asarray(result.x, dtype=float)
    return ({"q": x[0:n], "c": x[n : 2 * n], "q_dis": x[2 * n : 3 * n], "s": x[3 * n : 4 * n],
             "E": x[4 * n : 5 * n], "u_plus": x[5 * n : 6 * n], "u_minus": x[6 * n : 7 * n]}, record, tiebreak)


def make_kappa_schedule_identity():
    def schedule(price, day_index):  # noqa: ARG001
        return {
            "day_index": int(day_index),
            "records": [
                {"day_index": int(day_index), "m": int(hour), "a_m": None, "b_m": None, "raw": None,
                 "kappa": 1.0, "clipped": False, "reason": "ablation_kappa_identity"}
                for hour in P.DECISION_HOURS
            ],
            "kappa": {int(hour): 1.0 for hour in P.DECISION_HOURS},
            "clip_events": [],
        }

    return schedule


def run_chain_variant(chain: str, inputs: dict[str, Any], *, spill_mode: str, kappa_identity: bool,
                      eta: tuple[float, float] | None, tiebreak_literal: bool, time_limit_seconds: float,
                      deadline: float, fallback_seed: np.ndarray | None = None) -> M.ChainResult:
    """按变体重新实现两链的前向递推（求解器复用 accepted 的 `_solve_with_tiebreak`）。

    `fallback_seed` 只服务 `C-ANCHOR-P03`：锚点价格序列是同一单日曲线 × 365 天，
    故 `d = 2025-01-01` 的前一日（`2024-12-31`）价格按构造等于该曲线。accepted 模块对
    「无前一日」取常量中性价 1.0，会让 `d = 0` 的调整层未实现部分偏离 `M1`；此处补上
    这条**数据**（不改任何模型方程），且只在锚点运行期间生效，`finally` 中恢复。
    """
    eta_ch, eta_dis = (M.ETA_CH, M.ETA_DIS) if eta is None else eta
    original = (M.ETA_CH, M.ETA_DIS, P.kappa_schedule)
    fallback_original = P.fallback_price
    M.ETA_CH, M.ETA_DIS = eta_ch, eta_dis
    if kappa_identity:
        P.kappa_schedule = make_kappa_schedule_identity()
    if fallback_seed is not None:
        seeded = np.asarray(fallback_seed, dtype=float)

        def _seeded_fallback(periods: int = P.PERIODS_PER_DAY,
                             _seeded: np.ndarray = seeded) -> np.ndarray:
            return np.asarray(_seeded[:periods], dtype=float)

        P.fallback_price = _seeded_fallback
    try:
        if tiebreak_literal:
            return _run_literal_tiebreak_42(inputs, spill_mode=spill_mode, time_limit_seconds=time_limit_seconds,
                                            deadline=deadline)
        return _run_chain_variant_inner(chain, inputs, spill_mode=spill_mode, time_limit_seconds=time_limit_seconds,
                                        deadline=deadline)
    finally:
        M.ETA_CH, M.ETA_DIS, P.kappa_schedule = original
        P.fallback_price = fallback_original


def _run_literal_tiebreak_42(inputs: dict[str, Any], *, spill_mode: str, time_limit_seconds: float,
                             deadline: float) -> M.ChainResult:
    """字面 ε 加权式：`min 主目标 + ε·Σ(c+q_dis)`（ε 按 AS21 定义），直接取其解为提交解。"""
    days = inputs["days"]
    shape = (days, N)
    fields = {key: np.zeros(shape) for key in ("b", "c", "q_dis", "s", "E", "q_em")}
    e_prev = M.E_INIT
    for day in range(days):
        if time.perf_counter() > deadline:
            raise M.BudgetExceeded(f"墙控预算耗尽：已完成 {day}/{days} 天")
        price = inputs["decision_price"][day]
        load = inputs["load_energy"][day]
        pv_act = inputs["pv_act_energy"][day]
        n = N
        size = 6 * n
        objective = np.zeros(size)
        objective[0:n] = price
        objective[5 * n : 6 * n] = M.ALPHA_EM * price
        spill_upper = (np.maximum(0.0, pv_act - load) if spill_mode == "d9b" else np.asarray(pv_act, dtype=float))
        bounds = np.empty((size, 2), dtype=float)
        bounds[0:n, 0], bounds[0:n, 1] = 0.0, np.inf
        bounds[n : 2 * n, 0], bounds[n : 2 * n, 1] = 0.0, M.C_CAP
        bounds[2 * n : 3 * n, 0], bounds[2 * n : 3 * n, 1] = 0.0, M.Q_CAP
        bounds[3 * n : 4 * n, 0], bounds[3 * n : 4 * n, 1] = 0.0, spill_upper
        bounds[4 * n : 5 * n, 0], bounds[4 * n : 5 * n, 1] = M.E_MIN, M.E_MAX
        bounds[5 * n : 6 * n, 0], bounds[5 * n : 6 * n, 1] = 0.0, np.inf
        a_eq, b_eq = M._balance_and_state_rows(
            n, size=size, pv_energy=pv_act, load_energy=load, e_start=e_prev,
            balance_offsets=(0, n, 2 * n, 3 * n), energy_offset=4 * n,
        )
        a_eq = (a_eq + coo_matrix((np.ones(n), (np.arange(n), 5 * n + np.arange(n))),
                                  shape=(2 * n, size)).tocsr()).tocsr()
        baseline = linprog(objective, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs",
                           options={"time_limit": float(time_limit_seconds), "presolve": True})
        if baseline.x is None:
            raise M.LayerFailure(f"字面 ε 加权式基线 LP 未达最优（day={day}, status={baseline.status}）",
                                 day=day, hour=0, status=int(baseline.status))
        eps = M.tiebreak_epsilon(float(baseline.fun), M.throughput_scale(n))
        weighted = objective.copy()
        weighted[n : 2 * n] += eps
        weighted[2 * n : 3 * n] += eps
        res = linprog(weighted, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs",
                      options={"time_limit": float(time_limit_seconds), "presolve": True})
        if res.x is None:
            raise M.LayerFailure(f"字面 ε 加权式 LP 未达最优（day={day}, status={res.status}）",
                                 day=day, hour=0, status=int(res.status))
        x = np.asarray(res.x, dtype=float)
        fields["b"][day] = x[0:n]
        fields["c"][day] = x[n : 2 * n]
        fields["q_dis"][day] = x[2 * n : 3 * n]
        fields["s"][day] = x[3 * n : 4 * n]
        fields["E"][day] = x[4 * n : 5 * n]
        fields["q_em"][day] = x[5 * n : 6 * n]
        e_prev = float(fields["E"][day][-1])
    residual = fields["b"] + fields["q_dis"] + inputs["pv_act_energy"] - inputs["load_energy"] - fields["c"]
    return M.ChainResult(
        chain=CHAIN_42, days=days, price_act=inputs["price_act"], price_fc=inputs["decision_price"],
        decision_price=inputs["decision_price"], load_energy=inputs["load_energy"],
        pv_act_energy=inputs["pv_act_energy"], plan_b=fields["b"], q=fields["b"].copy(), c=fields["c"],
        q_dis=fields["q_dis"], E=fields["E"], q_em=np.maximum(-residual, 0.0), s_settle=np.maximum(residual, 0.0),
        plan_c=fields["c"], plan_q_dis=fields["q_dis"], plan_s=fields["s"], plan_E=fields["E"],
        plan_q_em=fields["q_em"], layer_records=[], tiebreak_records=[], layer_pv_energy={0: inputs["pv_act_energy"]},
    )


def _run_chain_variant_inner(chain: str, inputs: dict[str, Any], *, spill_mode: str,
                             time_limit_seconds: float, deadline: float) -> M.ChainResult:
    days = inputs["days"]
    price_act = inputs["price_act"]
    load = inputs["load_energy"]
    pv_act = inputs["pv_act_energy"]
    shape = (days, N)
    plan_b = np.zeros(shape)
    plan_c = np.zeros(shape)
    plan_q_dis = np.zeros(shape)
    plan_s = np.zeros(shape)
    plan_E = np.zeros(shape)
    q = np.zeros(shape)
    c = np.zeros(shape)
    q_dis = np.zeros(shape)
    state = np.zeros(shape)
    price_fc = np.zeros(shape)
    kappa_records: list[dict[str, Any]] = []
    e_prev = M.E_INIT
    for day in range(days):
        if time.perf_counter() > deadline:
            raise M.BudgetExceeded(f"墙钟预算耗尽：已完成 {day}/{days} 天")
        if chain == CHAIN_42:
            plan, record, _ = solve_day_plan_42_variant(
                price=inputs["decision_price"][day], load_energy=load[day], pv_act_energy=pv_act[day],
                e_start=e_prev, day=day, time_limit_seconds=time_limit_seconds, spill_mode=spill_mode,
            )
            if record.status != 0 or not plan:
                raise M.LayerFailure(f"变体 4-2 计划层未达最优（day={day}, status={record.status}）",
                                     day=day, hour=0, status=int(record.status))
            plan_b[day], plan_c[day], plan_q_dis[day], plan_s[day] = plan["b"], plan["c"], plan["q_dis"], plan["s"]
            plan_E[day] = plan["E"]
            q[day] = plan["b"]
            c[day] = plan["c"]
            q_dis[day] = plan["q_dis"]
            state[day] = plan["E"]
            price_fc[day] = inputs["decision_price"][day]
        else:
            schedule = P.kappa_schedule(price_act, day)
            kappas = {int(key): float(value) for key, value in schedule["kappa"].items()}
            kappa_records.extend(schedule["records"])
            price_fc[day] = P.belief_price(price_act, day, kappas)
            plan, record, _ = solve_plan_layer_43_variant(
                price=inputs["decision_price"][day], load_energy=load[day],
                pv_fc_energy=inputs["forecast_energy"][0][day], e_start=e_prev, day=day,
                time_limit_seconds=time_limit_seconds, spill_mode=spill_mode,
            )
            if record.status != 0 or not plan:
                raise M.LayerFailure(f"变体 4-3 计划层未达最优（day={day}, status={record.status}）",
                                     day=day, hour=0, status=int(record.status))
            plan_b[day], plan_c[day], plan_q_dis[day], plan_s[day] = plan["b"], plan["c"], plan["q_dis"], plan["s"]
            plan_E[day] = plan["E"]
            q[day, 0:M.COMMIT_BLOCK] = plan["b"][0:M.COMMIT_BLOCK]
            c[day, 0:M.COMMIT_BLOCK] = plan["c"][0:M.COMMIT_BLOCK]
            q_dis[day, 0:M.COMMIT_BLOCK] = plan["q_dis"][0:M.COMMIT_BLOCK]
            state[day, 0:M.COMMIT_BLOCK] = plan["E"][0:M.COMMIT_BLOCK]
            for hour in (6, 12, 18):
                layer_price = P.layer_price(price_act, day, hour, float(kappas[hour]))
                layer, record, _ = solve_adjustment_layer_43_variant(
                    hour=hour, price=layer_price, load_energy=load[day],
                    pv_fc_energy=inputs["forecast_energy"][hour][day], plan_b=plan_b[day],
                    e_start=float(state[day, 6 * hour - 1]), day=day,
                    time_limit_seconds=time_limit_seconds, spill_mode=spill_mode,
                )
                if record.status != 0 or not layer:
                    raise M.LayerFailure(f"变体 4-3 调整层未达最优（day={day}, hour={hour}）",
                                         day=day, hour=hour, status=int(record.status))
                commit = slice(6 * hour, 6 * hour + M.COMMIT_BLOCK)
                q[day, commit] = layer["q"][0:M.COMMIT_BLOCK]
                c[day, commit] = layer["c"][0:M.COMMIT_BLOCK]
                q_dis[day, commit] = layer["q_dis"][0:M.COMMIT_BLOCK]
                state[day, commit] = layer["E"][0:M.COMMIT_BLOCK]
        e_prev = float(state[day, -1])
    residual_all = q + q_dis + pv_act - load - c
    return M.ChainResult(
        chain=chain, days=days, price_act=price_act, price_fc=price_fc, decision_price=inputs["decision_price"],
        load_energy=load, pv_act_energy=pv_act, plan_b=plan_b, q=q, c=c, q_dis=q_dis, E=state,
        q_em=np.maximum(-residual_all, 0.0), s_settle=np.maximum(residual_all, 0.0),
        plan_c=plan_c, plan_q_dis=plan_q_dis, plan_s=plan_s, plan_E=plan_E, plan_q_em=np.zeros(shape),
        layer_records=[], tiebreak_records=[], kappa_records=kappa_records,
        layer_pv_energy=({hour: inputs["forecast_energy"][hour] for hour in P.DECISION_HOURS}
                         if chain == CHAIN_43 else {0: pv_act}),
    )


# ---------------------------------------------------------------------------
# 主口径（复用 accepted 求解器）
# ---------------------------------------------------------------------------
def run_main_chain(chain: str, inputs: dict[str, Any], *, time_limit_seconds: float,
                   deadline: float) -> M.ChainResult:
    forecast_kw = ({hour: inputs["forecast_energy"][hour] / M.DELTA_T for hour in P.DECISION_HOURS}
                   if chain == CHAIN_43 else {})
    data = M.ChainInputs(
        days=inputs["days"], price_act=inputs["price_act"], decision_price=inputs["decision_price"],
        load_energy=inputs["load_energy"], pv_act_energy=inputs["pv_act_energy"], forecast_kw=forecast_kw,
    )
    if chain == CHAIN_42:
        return M.run_chain_42(data, time_limit_seconds=time_limit_seconds, deadline=deadline)
    return M.run_chain_43(data, time_limit_seconds=time_limit_seconds, deadline=deadline)


def attach_reference_state(inputs: dict[str, Any], reference: M.ChainResult) -> None:
    inputs["state_end"] = reference.E[:, -1].copy()
    inputs["base_day_cost"] = cost_breakdown(reference, actual=True)["total"].copy()
    inputs["base_day_plan_b"] = reference.plan_b.copy()


# ---------------------------------------------------------------------------
# 汇总与主流程
# ---------------------------------------------------------------------------
def _rel(observed: float, expected: float) -> float:
    if expected == 0:
        return float(abs(observed))
    return float(abs(observed - expected) / abs(expected))


def _pct(delta: float, base: float) -> float:
    return 0.0 if base == 0 else float(100.0 * delta / base)


def emit(out_dir: Path, case: str, summary: dict[str, Any], raw: dict[str, Any] | None = None) -> dict[str, Any]:
    case_dir = out_dir / case
    case_dir.mkdir(parents=True, exist_ok=True)
    write_json(case_dir / "summary.json", summary)
    if raw is not None and raw is not summary:
        write_json(case_dir / "raw.json", raw)
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="prob04 ablation 隔离计算（分链）")
    parser.add_argument("--chain", choices=(CHAIN_42, CHAIN_43), required=True)
    parser.add_argument("--data1", default="data/附件1.xlsx", help="附件 1（**只** C-ANCHOR-P03 的价格来源）")
    parser.add_argument("--data2", default="data/附件2.xlsx")
    parser.add_argument("--data3", default="data/附件3.xlsx")
    parser.add_argument("--data4", default="data/附件4.xlsx")
    parser.add_argument("--output", required=True)
    parser.add_argument("--days", type=int, default=DAYS_FULL)
    parser.add_argument("--time-limit", type=float, default=60.0)
    parser.add_argument("--max-wall-seconds", type=float, default=1400.0)
    parser.add_argument("--cases", default="all")
    parser.add_argument("--anchor-probe-days", type=int, default=0, help=">0 时锚点只跑前 N 天（自检）")
    parser.add_argument("--anchors-only", action="store_true", help="只跑 BASE + C-ANCHOR-P03（自检）")
    parser.add_argument("--forecast-basis", choices=("month_mean", "recent7"), default="month_mean")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = _resolve(args.output)
    _guard_output(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    chain = args.chain
    days = args.days
    budget = Budget(args.max_wall_seconds)
    if args.anchors_only:
        selected = {"BASE", "ANCHOR"}
    elif args.cases.strip() == "all":
        selected = None
    else:
        selected = {item.strip().upper() for item in args.cases.split(",") if item.strip()}
    def want(name: str) -> bool:
        return selected is None or name in selected


    try:
        loaded = load_inputs(args)
    except InputValidationError as exc:
        print(f"[ablation] 输入校验失败：{exc}", file=sys.stderr)
        return EXIT_INPUT_INVALID

    att2, att3, att4 = loaded["att2"], loaded["att3"], loaded["att4"]
    if chain == CHAIN_43 and att3 is None:
        print("[ablation] 链 4-3 需要附件 3", file=sys.stderr)
        return EXIT_INPUT_INVALID

    results: dict[str, Any] = {}
    criteria: dict[str, Any] = {}
    baseline_check: dict[str, Any] = {}

    # ---- 参考解重放（取代表日的日初状态与单日基线费用；不写盘、不覆盖）----
    reference: M.ChainResult | None = None
    try:
        reference = run_main_chain(
            chain, make_chain_inputs(chain, att2, att3, att4, days=days, forecast_basis=args.forecast_basis),
            time_limit_seconds=args.time_limit, deadline=budget.started + args.max_wall_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ablation] 参考解重放失败（不阻塞，仅影响代表日初状态）：{exc}")

    inputs = make_chain_inputs(chain, att2, att3, att4, days=days, forecast_basis=args.forecast_basis)
    if reference is not None:
        attach_reference_state(inputs, reference)
    else:
        inputs["state_end"] = None
        inputs["base_day_cost"] = np.zeros(days)
        inputs["base_day_plan_b"] = np.zeros((days, N))

    # ---- BASE（判据 C2）----
    if want("BASE"):
        res = reference if reference is not None else run_main_chain(
            chain, inputs, time_limit_seconds=args.time_limit, deadline=budget.started + args.max_wall_seconds)
        summary = summarize(res)
        summary["checks"] = cross_checks(res)
        summary["decision_prices"] = {"method": P.PRIMARY_METHOD, "future_price_used_in_decision": False}
        results["BASE"] = emit(output_dir, f"BASE-{chain.replace('-', '')}", summary, summary)
        expected = BASE_RUN002[chain]
        rel = {
            "D_full_C_total": _rel(summary["D_full"]["cost_total_yuan"], expected["D_full_C_total"]),
            "D_req_C_total": _rel(summary["D_req"]["cost_total_yuan"], expected["D_req_C_total"]),
            "D_req_sum_q_em": (_rel(summary["D_req"]["total_q_em_kwh"], expected["D_req_sum_q_em"])
                               if expected["D_req_sum_q_em"] != 0 else float(abs(summary["D_req"]["total_q_em_kwh"]))),
            "D_full_sum_q_em": (_rel(summary["D_full"]["total_q_em_kwh"], expected["D_full_sum_q_em"])
                                if expected["D_full_sum_q_em"] != 0 else float(abs(summary["D_full"]["total_q_em_kwh"]))),
        }
        baseline_check["BASE"] = {
            "pass": bool(all(value <= TOL_BASELINE_REL for value in rel.values())),
            "relative_differences": rel,
            "threshold": TOL_BASELINE_REL,
            "expected": expected,
            "observed": {
                "D_full_C_total": summary["D_full"]["cost_total_yuan"],
                "D_req_C_total": summary["D_req"]["cost_total_yuan"],
                "D_req_sum_q_em": summary["D_req"]["total_q_em_kwh"],
                "D_full_sum_q_em": summary["D_full"]["total_q_em_kwh"],
            },
        }
        criteria["C2"] = baseline_check["BASE"]

    # ---- C-ANCHOR-P03（判据 C1，仅 4-3）----
    if chain == CHAIN_43 and want("ANCHOR"):
        anchor_days = int(args.anchor_probe_days) or days
        one_day = read_attachment1_price(_resolve(args.data1))
        price_anchor = np.tile(one_day, (days, 1))
        anchor_inputs = make_chain_inputs(chain, att2, att3, att4, price_act=price_anchor, days=days,
                                          forecast_basis=args.forecast_basis, reference_seed=True)
        # 锚点必须用与 prob03 `M1` 一致的层内弃光界（`s ≤ Π_m[PV]·Δt`）；prob04 主口径的
        # `D9-B` 物理盈余界会收紧可行域并改变最优值（见 `S-ABL-SPILL`），故**不用于**锚点。
        res = run_chain_variant(chain, anchor_inputs, spill_mode="d9a", kappa_identity=False, eta=None,
                                tiebreak_literal=False, time_limit_seconds=args.time_limit,
                                deadline=budget.started + args.max_wall_seconds, fallback_seed=one_day)
        summary = summarize(res)
        summary["checks"] = cross_checks(res)
        summary["anchor_construction"] = {
            "price_source": "data/附件1.xlsx（144 点单日曲线 × 365 天；只替换价格，团队勘误 E-F4）",
            "attachment1_md5": md5_of(_resolve(args.data1)),
            "pf_persist_exact": True,
            "kappa_identity": True,
            "spill_bound": "D9-A（s ≤ Π_m[PV]·Δt），与 prob03 M1 一致",
            "reference_day_seed": (
                "为 d = 2025-01-01 提供「参考日」（价格 = 当天附件 1 曲线）作为 H_1，使 PF-PERSIST 在该日"
                "也可用；否则该日回退为常量中性价 1.0，与 M1 的价格口径不同（此为信息集允许的合法回退）。"
            ),
            "fallback_seed": (
                "锚点价格序列为同一单日曲线 × 365 天 ⇒ `2025-01-01` 的前一日（`2024-12-31`）"
                "按构造同取该曲线；锚点运行期间以该曲线替换 accepted 模块「无前一日」的常量中性价 1.0"
                "（只补数据、不改模型方程），`finally` 中恢复。未补此项时 `D_full` 的 `C_adj` 残差 "
                "+1777.290337 元、`ΔC_price(D_full)` = −30558.377455 元，六项中两项超 1e-9。"
            ),
            "probe_days": int(anchor_days),
            "note": "退化情景复现锚点：不进入交付值、不写回 prob03（换数据、不换模型）",
        }
        summary["anchor_reference"] = ANCHOR_P03
        rel = {
            "D_full_C_total": _rel(summary["D_full"]["cost_total_yuan"], ANCHOR_P03["D_full_C_total"]),
            "D_req_C_total": _rel(summary["D_req"]["cost_total_yuan"], ANCHOR_P03["D_req_C_total"]),
            "D_full_C_plan": _rel(summary["D_full"]["cost_plan_yuan"], ANCHOR_P03["D_full_C_plan"]),
            "D_full_C_adj": _rel(summary["D_full"]["cost_adj_yuan"], ANCHOR_P03["D_full_C_adj"]),
            "D_full_C_em": _rel(summary["D_full"]["cost_em_yuan"], ANCHOR_P03["D_full_C_em"]),
            "D_req_sum_q_em": _rel(summary["D_req"]["total_q_em_kwh"], ANCHOR_P03["D_req_sum_q_em"]),
        }
        passed = bool(anchor_days == days and all(value <= TOL_ANCHOR_REL for value in rel.values()))
        baseline_check["C-ANCHOR-P03"] = {
            "pass": passed,
            "relative_differences": rel,
            "threshold": TOL_ANCHOR_REL,
            "reference": ANCHOR_P03,
            "observed": {
                "D_full_C_total": summary["D_full"]["cost_total_yuan"],
                "D_req_C_total": summary["D_req"]["cost_total_yuan"],
                "D_full_C_plan": summary["D_full"]["cost_plan_yuan"],
                "D_full_C_adj": summary["D_full"]["cost_adj_yuan"],
                "D_full_C_em": summary["D_full"]["cost_em_yuan"],
                "D_req_sum_q_em": summary["D_req"]["total_q_em_kwh"],
            },
            "probe_days": int(anchor_days),
            "note": "probe_days < 365 时 pass 预期为 False（仅自检）",
        }
        criteria["C1"] = baseline_check["C-ANCHOR-P03"]
        results["C-ANCHOR-P03"] = emit(output_dir, "C-ANCHOR-P03", summary, summary)

    # ---- S-RH ----
    if want("SRH"):
        rh_results: dict[str, Any] = {}
        rh_outcomes: dict[int, dict[str, Any]] = {}
        for horizon in (1, 3, 7, 14):
            budget.check(f"S-RH(H={horizon}) 墙钟预算耗尽")
            outcome = run_rh(chain, inputs, horizon, time_limit_seconds=args.time_limit, budget=budget)
            rh_outcomes[horizon] = outcome
            summary = summarize(outcome["result"])
            summary["checks"] = cross_checks(outcome["result"])
            summary.update(
                {
                    "horizon_days": horizon,
                    "window": {
                        "granularity": "current_day_10min + future_days_1hour_block",
                        "future_load_pv_basis": args.forecast_basis,
                        "price_forward_basis": "PF-PERSIST（p^{act}_{d−1,·}）",
                        "terminal_rule": "末窗（越过 12-31）按终端自由截断并登记",
                        "non_anticipativity": "窗口内未来变量只用于优化、不进入承诺",
                    },
                    "solver_seconds": outcome["solver_seconds"],
                    "lp_solves": outcome["lp_solves"],
                    "max_window_variables": outcome["max_variables"],
                    "layer_seconds": outcome["layer_seconds"],
                }
            )
            label = f"S-RH-H{horizon}"
            rh_results[label] = emit(output_dir, f"S-RH-{chain.replace('-', '')}-H{horizon}", summary, summary)
        results["S-RH"] = rh_results
        base_full = rh_results["S-RH-H1"]["D_full"]["cost_total_yuan"]
        base_del = rh_results["S-RH-H1"]["D_req"]["cost_total_yuan"]
        if "BASE" in results:
            rel_full = _rel(base_full, results["BASE"]["D_full"]["cost_total_yuan"])
            rel_del = _rel(base_del, results["BASE"]["D_req"]["cost_total_yuan"])
        else:
            rel_full = _rel(base_full, BASE_RUN002[chain]["D_full_C_total"])
            rel_del = _rel(base_del, BASE_RUN002[chain]["D_req_C_total"])
        state_gap = None
        # **run003 修正（plan_v003.md §2）**：`C3` 是 `H = 1` 的基线闸门，轨迹比对必须取
        # `H = 1` 的结果；旧版沿用循环结束后的 `outcome`（= `H = 14`），把 14 天窗口的储能轨迹
        # 与主口径比对 ⇒ 4-2 的 `state_gap` 被误报为 `9600 kWh`（满量程差），实际是比错了对象。
        rh_h1 = rh_outcomes[1]["result"]
        if reference is not None and reference.E.shape == rh_h1.E.shape:
            state_gap = float(np.max(np.abs(rh_h1.E - reference.E)))
        criteria["C3"] = {
            "pass": bool(rel_full <= TOL_RH_GATE_REL and rel_del <= TOL_RH_GATE_REL
                         and (state_gap is None or state_gap <= TOL_STATE_ABS)),
            "D_full_relative_difference": rel_full,
            "D_req_relative_difference": rel_del,
            "state_trajectory_max_abs_difference_kwh": state_gap,
            "threshold": TOL_RH_GATE_REL,
            "note": "H = 1 必须逐位复现主口径基准（团队 R-2 预注册判据①）；轨迹比对对象为 H = 1",
        }
        ordering = [rh_results[f"S-RH-H{h}"]["D_full"]["cost_total_yuan"] for h in (1, 3, 7, 14)]
        # **run003 修正（plan_v003.md §2）**：预注册期望是「`H` 增大 ⇒ 费用**不增**」（更多前瞻 ⇒ 不劣），
        # 即 `H` 序列上费用应为**非增**。旧版误写为非减，把 4-2 实测的非增序列（1.4756e7 → 1.4726e7）
        # 反判成反例。判据阈值与口径未改，仅纠正实现方向。
        nonincreasing = all(
            ordering[i] >= ordering[i + 1] - 1e-6 * max(abs(ordering[i + 1]), 1.0)
            for i in range(len(ordering) - 1)
        )
        criteria["C4"] = {
            "chain": chain,
            "D_full_cost_by_horizon": {f"H{h}": value for h, value in zip((1, 3, 7, 14), ordering)},
            "expectation_nonincreasing_cost": bool(nonincreasing),
            "monotone_nonincreasing_cost": bool(nonincreasing),
            "applies": chain == CHAIN_42,
            "counterexample_registered": bool(chain == CHAIN_42 and not nonincreasing),
            "note": ("预注册期望：4-2 的 H 增大 ⇒ 费用不增（非增）；4-3 因 §3.3.4 的边界（深度只作用于计划层）"
                     "不作单调性要求，仅报数值；出现**增**则按 T7-4 如实登记反例，禁止强凑单调性"),
        }
        criteria["C_RH_BOUNDARY"] = {
            "state_end_statistics": {label: rh_results[label]["state_end_kwh"] for label in rh_results},
            "note": "日边界储电量行为（团队 R-2 报告项 b，直接回应 prob03 E8/R18）",
        }

    # ---- S-VAR / S-VAR-RH ----
    if want("SVAR"):
        svar = run_svar(chain, inputs, horizon_days=1, time_limit_seconds=args.time_limit, budget=budget,
                        variant="daily")
        results["S-VAR"] = emit(output_dir, f"S-VAR-{chain.replace('-', '')}", svar, svar)
    if chain == CHAIN_42 and want("SVAR-RH"):
        svar_rh = run_svar(chain, inputs, horizon_days=SVAR_RH_HORIZON, time_limit_seconds=args.time_limit,
                           budget=budget, variant="rh")
        results["S-VAR-RH"] = emit(output_dir, f"S-VAR-RH-{chain.replace('-', '')}-H{SVAR_RH_HORIZON}", svar_rh, svar_rh)

    # ---- PF-AR ----
    if chain == CHAIN_42 and want("PFAR"):
        ar_inputs = make_chain_inputs(chain, att2, att3, att4, days=days, decision_method="PF-AR",
                                      forecast_basis=args.forecast_basis)
        res = run_main_chain(chain, ar_inputs, time_limit_seconds=args.time_limit,
                             deadline=budget.started + args.max_wall_seconds)
        summary = summarize(res)
        summary["checks"] = cross_checks(res)
        summary["decision_prices"] = {"method": "PF-AR", "future_price_used_in_decision": False}
        summary["fallback_days"] = len(ar_inputs["fallbacks"])
        results["PF-AR"] = emit(output_dir, "PF-AR-42", summary, summary)

    # ---- 结构消融 ----
    if want("SPILL"):
        res = run_chain_variant(chain, inputs, spill_mode="d9a", kappa_identity=False, eta=None,
                                tiebreak_literal=False, time_limit_seconds=args.time_limit,
                                deadline=budget.started + args.max_wall_seconds)
        summary = summarize(res)
        summary["checks"] = cross_checks(res)
        summary["ablation"] = {"item": "AS05 / D9-B → D9-A",
                               "change": "层内弃光上界 s ≤ PV^{层}·Δt（替代物理盈余界 max(0, PV^{层}·Δt − L·Δt)）"}
        results["S-ABL-SPILL"] = emit(output_dir, f"S-ABL-SPILL-{chain.replace('-', '')}", summary, summary)

    if chain == CHAIN_43 and want("KAPPA1"):
        res = run_chain_variant(chain, inputs, spill_mode="d9b", kappa_identity=True, eta=None,
                                tiebreak_literal=False, time_limit_seconds=args.time_limit,
                                deadline=budget.started + args.max_wall_seconds)
        summary = summarize(res)
        summary["checks"] = cross_checks(res)
        summary["ablation"] = {"item": "AS11 / D6-C", "change": "κ_m ≡ 1（调整层不更新价格预测）"}
        results["S-ABL-KAPPA1"] = emit(output_dir, "S-ABL-KAPPA1-43", summary, summary)

    if chain == CHAIN_42 and want("TIEBREAK"):
        res = run_chain_variant(chain, inputs, spill_mode="d9b", kappa_identity=False, eta=None,
                                tiebreak_literal=True, time_limit_seconds=args.time_limit,
                                deadline=budget.started + args.max_wall_seconds)
        summary = summarize(res)
        summary["checks"] = cross_checks(res)
        summary["ablation"] = {"item": "AS21",
                               "change": "字面 ε 加权式（min 主目标 + ε·Σ(c+q_dis)）替代字典序提交解"}
        results["S-ABL-TIEBREAK"] = emit(output_dir, "S-ABL-TIEBREAK-42", summary, summary)

    if chain == CHAIN_42 and want("ETA"):
        eta_results: dict[str, Any] = {}
        for label, eta_ch, eta_dis in (
            ("both", 0.9, 0.9),
            ("charge_only", 0.9, 1.0),
            ("discharge_only", 1.0, 0.9),
            ("round_trip", float(np.sqrt(0.9)), float(np.sqrt(0.9))),
        ):
            res = run_chain_variant(chain, inputs, spill_mode="d9b", kappa_identity=False,
                                    eta=(eta_ch, eta_dis), tiebreak_literal=False,
                                    time_limit_seconds=args.time_limit,
                                    deadline=budget.started + args.max_wall_seconds)
            summary = summarize(res)
            summary["checks"] = cross_checks(res)
            summary["ablation"] = {
                "item": "AS04（η 作用位置）",
                "eta_ch": eta_ch,
                "eta_dis": eta_dis,
                "cap_discipline": ("固定 c ≤ 833.3333、q_dis ≤ 750.0000；与 robustness 的 eta_placement 族"
                                   "（按情景重算上限）口径不同，不得互换引用"),
            }
            eta_results[label] = emit(output_dir, f"S-ABL-ETA-{label}", summary, summary)
        results["S-ABL-ETA-PLACE"] = eta_results

    # ---- 汇总 ----
    comparison = build_comparison(chain, results, criteria)
    write_json(output_dir / "comparison.json", comparison)
    write_json(output_dir / "baseline_check.json", baseline_check)
    write_json(output_dir / "criteria.json", {
        "chain": chain,
        "criteria": criteria,
        "criteria_failed": [key for key, value in criteria.items()
                            if isinstance(value, dict) and value.get("pass") is False],
    })
    write_json(output_dir / "results.json", results)
    write_json(output_dir / "forecast_backtest.json",
               P.roll_backtest(att4.price, days=DAYS_FULL, methods=P.ALL_METHODS))

    failed_checks = sorted({item for case in _walk(results) for item in case.get("checks_failed", [])})
    manifest = {
        "problem_id": "microgrid_2025",
        "question_id": "prob04",
        "assumption_version": "assumption_v001",
        "formulation_version": "formulation_v001",
        "stage": "ablation",
        "chain": chain,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task_id": os.environ.get("AUTOMM_TASK_ID") or None,
        "output_directory": str(output_dir),
        "seed": SEED,
        "deterministic_scenarios": True,
        "device": "cpu",
        "gpu_required": False,
        "solver": "scipy.optimize.linprog(method='highs')（S-VAR 的确定性等价同样用 HiGHS）",
        "days": days,
        "layer_time_limit_seconds": args.time_limit,
        "max_wall_seconds": args.max_wall_seconds,
        "wall_seconds": budget.elapsed,
        "forecast_basis": args.forecast_basis,
        "information_set": {
            "future_price_used_in_decision": False,
            "decision_price_rule": "PF-PERSIST（4-2）；PF-PERSIST + κ_m 滚动更新（4-3）",
            "settlement_price_rule": "附件 4 实际价（唯一结算入口）",
            "anchor_exception": "C-ANCHOR-P03 只替换价格为附件 1 单日曲线（退化情景复现锚点）",
        },
        "input": {
            "attachment1": str(_resolve(args.data1)),
            "attachment1_md5": md5_of(_resolve(args.data1)),
            "attachment1_used_only_for": "C-ANCHOR-P03（只替换价格；团队勘误 E-F4）",
            "attachment2_md5": att2.md5,
            "attachment3_md5": att3.md5 if att3 is not None else None,
            "attachment4_md5": att4.md5,
        },
        "code_sha256": {
            "ablation": code_fingerprint(Path(__file__).resolve().parent),
            "accepted": code_fingerprint(ACCEPTED_CODE),
        },
        "case_counts": _count_cases(results),
        "checks_failed": failed_checks,
        "environment": {"python": sys.version.split()[0], "numpy": np.__version__,
                        "platform": platform.platform()},
    }
    write_json(output_dir / "run_manifest.json", manifest)
    write_json(output_dir / "solver_status.json", {
        "status": 0 if not failed_checks else 4,
        "feasible_incumbent": True,
        "chain": chain,
        "cases": _count_cases(results),
        "baseline_check": {key: value["pass"] for key, value in baseline_check.items()},
        "criteria_failed": [key for key, value in criteria.items()
                            if isinstance(value, dict) and value.get("pass") is False],
        "checks_failed": failed_checks,
        "wall_seconds": budget.elapsed,
        "device": "cpu",
        "gpu_required": False,
        "seed": SEED,
    })
    write_json(output_dir / "budget_history.json", {"records": budget.records})

    print(f"[ablation] 链 {chain} 完成：cases={_count_cases(results)}，墙钟 {budget.elapsed:.2f} s")
    for key, value in comparison["table"].items():
        if "D_req_delta_pct" in value:
            print(f"[ablation] {key}: D_req={value['D_req_cost_total_yuan']:.4f} 元"
                  f"(Δ={value['D_req_delta_pct']:+.6f}% vs BASE)")
        else:
            print(f"[ablation] {key}: {value}")
    if failed_checks:
        print(f"[ablation] 硬检查未通过：{failed_checks}", file=sys.stderr)
        return EXIT_HARD_CHECK_FAILED
    return EXIT_OK


def _walk(value: Any):
    if isinstance(value, dict):
        # 逐 case 摘要：带 `D_full`/`D_req` 的费用型对照，或带 `checks_failed` 的 S-VAR 型对照
        # （run003 修正：旧版只认 `D_full`/`D_req`，S-VAR/S-VAR-RH 的约束残差因此不进
        # `checks_failed`，且 `case_counts` 少计 2 个对照 ⇒ pre-registered `C8` 无法评估）。
        if ("D_full" in value and "D_req" in value) or "checks_failed" in value:
            yield value
        else:
            for item in value.values():
                yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _count_cases(value: Any) -> int:
    return sum(1 for _ in _walk(value))


def build_comparison(chain: str, results: dict[str, Any], criteria: dict[str, Any]) -> dict[str, Any]:
    table: dict[str, Any] = {}
    base_entry = results.get("BASE")
    base_full = base_entry["D_full"]["cost_total_yuan"] if base_entry else BASE_RUN002[chain]["D_full_C_total"]
    base_del = base_entry["D_req"]["cost_total_yuan"] if base_entry else BASE_RUN002[chain]["D_req_C_total"]

    def add(label: str, summary: dict[str, Any], extra: dict[str, Any] | None = None) -> None:
        entry = {
            "D_full_cost_total_yuan": summary["D_full"]["cost_total_yuan"],
            "D_req_cost_total_yuan": summary["D_req"]["cost_total_yuan"],
            "D_full_delta_vs_base_yuan": summary["D_full"]["cost_total_yuan"] - base_full,
            "D_req_delta_vs_base_yuan": summary["D_req"]["cost_total_yuan"] - base_del,
            "D_full_delta_pct": _pct(summary["D_full"]["cost_total_yuan"] - base_full, base_full),
            "D_req_delta_pct": _pct(summary["D_req"]["cost_total_yuan"] - base_del, base_del),
            "D_req_delta_c_price_yuan": summary["D_req"]["delta_c_price_yuan"],
            "D_req_sum_q_em_kwh": summary["D_req"]["total_q_em_kwh"],
            "state_end_mean_kwh": summary["state_end_kwh"]["mean"],
            "state_end_days_at_lower_bound": summary["state_end_kwh"]["days_at_lower_bound"],
            "sum_abs_state_span_from_lower_bound_kwh": summary["state_end_kwh"]["sum_abs_span_from_lower_bound_kwh"],
            "lp_layer_solves": summary.get("lp_layer_solves"),
            "checks_failed": summary.get("checks", {}).get("checks_failed", []),
        }
        if extra:
            entry.update(extra)
        table[label] = entry

    for key, value in results.items():
        if key == "BASE":
            add("BASE", value)
        elif key == "C-ANCHOR-P03":
            add("C-ANCHOR-P03", value, {"anchor_pass": criteria.get("C1", {}).get("pass")})
        elif key == "S-RH":
            for label, item in value.items():
                add(label, item, {"horizon_days": item["horizon_days"], "lp_solves": item["lp_solves"],
                                  "solver_seconds": item["solver_seconds"],
                                  "max_window_variables": item["max_window_variables"]})
        elif key == "S-VAR":
            table["S-VAR"] = {
                "representative_days": value["representative_days"],
                "expected_cost_total_yuan": value["expected_cost_total_yuan"],
                "baseline_point_forecast_cost_yuan": value["baseline_point_forecast_cost_yuan"],
                "delta_yuan": value["expected_minus_baseline_yuan"],
                "delta_pct": value["expected_minus_baseline_pct"],
                "cost_reduction_pct": value["cost_reduction_pct"],
                "first_stage_shape": value["first_stage_shape"],
                "compute": value["compute"],
            }
        elif key == "S-VAR-RH":
            table["S-VAR-RH"] = {
                "representative_days": value["representative_days"],
                "horizon_days": value["horizon_days"],
                "expected_cost_total_yuan": value["expected_cost_total_yuan"],
                "baseline_point_forecast_cost_yuan": value["baseline_point_forecast_cost_yuan"],
                "delta_yuan": value["expected_minus_baseline_yuan"],
                "delta_pct": value["expected_minus_baseline_pct"],
                "cost_reduction_pct": value["cost_reduction_pct"],
                "compute": value["compute"],
            }
        elif key == "PF-AR":
            add("PF-AR", value, {"decision_price_method": "PF-AR"})
        elif key in ("S-ABL-SPILL", "S-ABL-KAPPA1", "S-ABL-TIEBREAK"):
            add(key, value)
        elif key == "S-ABL-ETA-PLACE":
            for label, item in value.items():
                add(f"S-ABL-ETA-{label}", item,
                    {"eta_ch": item["ablation"]["eta_ch"], "eta_dis": item["ablation"]["eta_dis"]})

    spill_rel = None
    if "S-ABL-SPILL" in results:
        spill_rel = _rel(results["S-ABL-SPILL"]["D_full"]["cost_total_yuan"], base_full)
    kappa1_delta = None
    if "S-ABL-KAPPA1" in results:
        kappa1_delta = results["S-ABL-KAPPA1"]["D_full"]["cost_total_yuan"] - base_full
    tiebreak_delta = None
    if "S-ABL-TIEBREAK" in results:
        tiebreak_delta = results["S-ABL-TIEBREAK"]["D_full"]["cost_total_yuan"] - base_full
    criteria.setdefault("C6", {})
    criteria["C6"].update({
        "spill_bound_D9A_vs_D9B_relative_difference": spill_rel,
        "spill_bound_pass": None if spill_rel is None else bool(spill_rel <= TOL_SPILL_ABLATION_REL),
        "threshold": TOL_SPILL_ABLATION_REL,
        "kappa1_delta_yuan": kappa1_delta,
        "tiebreak_literal_delta_yuan": tiebreak_delta,
    })
    return {
        "chain": chain,
        "base_reference": {
            "D_full_cost_total_yuan": base_full,
            "D_req_cost_total_yuan": base_del,
            "source": "BASE（本实验独立重跑主口径）" if base_entry else "run002（登记值）",
        },
        "table": table,
        "criteria": criteria,
        "note": ("ΔC = 对照费用 − 主口径费用（负数 = 更省）；一律分链报告；S-VAR 的期望费用只在 12 个代表日"
                 "窗口内与主口径同窗口可比，不可与全年费用直接相加"),
    }


if __name__ == "__main__":
    raise SystemExit(main())

