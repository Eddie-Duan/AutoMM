# -*- coding: utf-8 -*-
"""prob04 价格预测器、滚动回测与 ``4-3`` 调整层的滚动水平校正 ``κ_m``。

严格对应 ``formulations/formulation_v001`` §1.2–§1.5 与 ``assumption_v001`` 的 AS08/AS11/AS22，
以及团队 ``A8-(b)`` 派生 ①③⑤⑥：

```
(PF-PERSIST) \\hat p_{d,i} = p^{act}_{d−1,i}                       （主口径，两链共用）
(PF-HIST)    \\hat p_{d,i} = mean_{d' ∈ H_d} p^{act}_{d',i}         （强制基准）
(PF-DUAL)    s_i = mean_i(\\bar p)/mean(\\bar p)；μ_d = mean_{d' ∈ L_d} mean_i(p^{act}_{d',i})
             \\hat p_{d,i} = μ_d · s_i                              （强制基准）
(PF-AR)      \\hat p_{d,i} = a_i + φ_i · p^{act}_{d−1,i}            （ablation 对照）
(K-3)        κ_m = clip(A_m/B_m, 0.5, 2.0)，A_m/B_m 为当日/前一日 i ≤ 6m 均值；κ_0 ≡ 1
```

**信息集纪律（AS07/AS22）**：``H_d`` = ``{d' : d' < d}`` 是**显式入参**；本模块的任何函数都只能通过
``history``/``day_index`` 访问价格，不得隐式读取 ``d' ≥ d`` 的任何价格。禁止出现「全天电价已知」类表述。

**2025-01-01 回退（forced, formulation §1.3.4）**：``H_d = ∅`` 时 (PF-HIST) 的扩张窗均值无定义，
故该日决策价取常量中性价 ``\\hat p_{1,i} ≡ 1.0``（``fallback_constant_price``）：平坦价 ⇒ 无套利激励 ⇒
储能保持 6000 kWh，是最少信息的合法选择；该日**不参与回测**（`D_full` 计 364 天）。
"""
from __future__ import annotations

import numpy as np

DAYS_FULL = 365
PERIODS_PER_DAY = 144
D_REQ_START = 31                    # 0 基日索引：2025-02-01（1 月为预热期）
FALLBACK_CONSTANT_PRICE = 1.0       # 2025-01-01 的常量中性决策价（元/kWh）
DUAL_RECENT_DAYS = 7
AR_MIN_PAIRS = 3                    # PF-AR 逐时段 OLS 的最少配对样本数（见 pf_ar 的退化说明）
KAPPA_LOWER = 0.5
KAPPA_UPPER = 2.0
DECISION_HOURS: tuple[int, ...] = (0, 6, 12, 18)
PRIMARY_METHOD = "PF-PERSIST"
BASELINE_METHODS: tuple[str, ...] = ("PF-PERSIST", "PF-DUAL", "PF-HIST")
ABLATION_METHODS: tuple[str, ...] = ("PF-AR",)
ALL_METHODS: tuple[str, ...] = ("PF-PERSIST", "PF-DUAL", "PF-HIST", "PF-AR")
# 「更简者」判定用（选择规则 BT-5 的并列裁决）：数值越小越简。
SIMPLICITY_RANK: dict[str, int] = {"PF-PERSIST": 0, "PF-HIST": 1, "PF-DUAL": 2, "PF-AR": 3}
MAE_TIE_RELATIVE_TOL = 0.01         # MAE 相对差 < 1% 视为并列
METHOD_FORMULAS: dict[str, str] = {
    "PF-PERSIST": "hat p_{d,i} = p^{act}_{d-1,i}（主口径）",
    "PF-HIST": "hat p_{d,i} = mean_{d' in H_d} p^{act}_{d',i}（扩张窗历史同时段均值）",
    "PF-DUAL": "hat p_{d,i} = mu_d * s_i；s_i 为归一化历史形状（mean_i(s_i)=1），mu_d 为最近 7 个可用日的日内均价均值",
    "PF-AR": (
        "hat p_{d,i} = a_i + phi_i * p^{act}_{d-1,i}（逐时段 OLS，系数只用 H_d 估计；"
        f"配对样本 < {AR_MIN_PAIRS} 组时回退 PF-HIST；ablation 对照）"
    ),
}


def available_history(day_index: int, *, days: int = DAYS_FULL) -> list[int]:
    """``H_d = { d' : d' < d }``（显式入参，防止信息集越界；AS22 / (G-5)）。"""
    if day_index < 0:
        raise ValueError("day_index 必须非负")
    return list(range(min(day_index, days)))


def _history_rows(price: np.ndarray, history: list[int]) -> np.ndarray:
    if not history:
        raise ValueError("空历史集合在 (PF-HIST)/(PF-DUAL)/(PF-AR) 中无定义")
    return np.asarray(price, dtype=float)[np.asarray(history, dtype=int), :]


def fallback_price(periods: int = PERIODS_PER_DAY) -> np.ndarray:
    """``H_d = ∅``（仅 2025-01-01）时的常量中性决策价 ``\\hat p ≡ 1.0``。"""
    return np.full(periods, FALLBACK_CONSTANT_PRICE, dtype=float)


def pf_persist(price: np.ndarray, day_index: int, history: list[int]) -> np.ndarray:
    """(PF-PERSIST) 前一日同时段；``H_d = ∅`` 时返回常量中性价（回退规则）。"""
    if not history:
        return fallback_price(int(np.asarray(price).shape[1]))
    return np.array(price[day_index - 1], dtype=float, copy=True)


def pf_hist(price: np.ndarray, day_index: int, history: list[int]) -> np.ndarray:
    """(PF-HIST) 历史同时段扩张窗均值；``H_d = ∅`` 时返回常量中性价。"""
    del day_index
    if not history:
        return fallback_price(int(np.asarray(price).shape[1]))
    return _history_rows(price, history).mean(axis=0)


def pf_dual(price: np.ndarray, day_index: int, history: list[int]) -> np.ndarray:
    """(PF-DUAL) 水平 × 时段双因子；``H_d = ∅`` 时返回常量中性价。"""
    del day_index
    if not history:
        return fallback_price(int(np.asarray(price).shape[1]))
    rows = _history_rows(price, history)
    shape_mean = rows.mean(axis=0)
    level = float(shape_mean.mean())
    if level <= 0:
        return fallback_price(int(np.asarray(price).shape[1]))
    shape = shape_mean / level
    recent = history[-DUAL_RECENT_DAYS:]
    mu = float(np.asarray(price, dtype=float)[np.asarray(recent, dtype=int), :].mean())
    return mu * shape


def pf_ar(price: np.ndarray, day_index: int, history: list[int]) -> tuple[np.ndarray, bool]:
    """(PF-AR) 逐时段 AR(1)：``a_i + φ_i·p^{act}_{d−1,i}``，系数只用 ``H_d`` 估计。

    返回 ``(预测向量, 是否退化回退)``。当可用配对样本 ``(d'−1, d')`` 少于 ``AR_MIN_PAIRS`` 组时，
    逐时段 OLS 无定义（2 点样本下斜率由共线残差决定、可无界；实测 2025-01-03 会给出 134 元/kWh
    的病态预测），故回退为 (PF-HIST) 的扩张窗均值并标记 ``used_fallback=True``（ablation 口径，
    不影响主口径选择）。配对样本 ``(d'−1, d')`` 全部取自 ``H_d`` 内部（``d' < d``），
    回归自变量用 ``p^{act}_{d−1,i}``，**不使用** d 当日或未来的任何价格。
    """
    matrix = np.asarray(price, dtype=float)
    if not history:
        return fallback_price(matrix.shape[1]), True
    pairs = [d for d in history if d - 1 >= 0]
    if len(pairs) < AR_MIN_PAIRS:
        return _history_rows(price, history).mean(axis=0), True
    current = matrix[np.asarray(pairs, dtype=int), :]           # (n, 144)
    lagged = matrix[np.asarray([d - 1 for d in pairs], dtype=int), :]
    x_mean = lagged.mean(axis=0)
    y_mean = current.mean(axis=0)
    dx = lagged - x_mean
    dy = current - y_mean
    variance = (dx * dx).sum(axis=0)
    covariance = (dx * dy).sum(axis=0)
    positive = variance > 1e-12
    phi = np.where(positive, covariance / np.where(positive, variance, 1.0), 0.0)
    intercept = y_mean - phi * x_mean
    return intercept + phi * matrix[day_index - 1], False


def predict(price: np.ndarray, day_index: int, method: str = PRIMARY_METHOD) -> dict[str, object]:
    """按显式历史集合预测第 ``day_index`` 天的 144 点决策价。

    返回 ``{"price": ndarray, "history_size": int, "fallback": str|None, "method": str}``。
    ``fallback`` 取值：``None`` / ``"fallback_constant_price"``（``H_d = ∅``）/
    ``"pf_ar_regression_undefined"``（配对样本 < 2，退化为 PF-HIST）。
    """
    history = available_history(day_index)
    fallback: str | None = None
    used_fallback = False
    if method == "PF-PERSIST":
        value = pf_persist(price, day_index, history)
    elif method == "PF-HIST":
        value = pf_hist(price, day_index, history)
    elif method == "PF-DUAL":
        value = pf_dual(price, day_index, history)
    elif method == "PF-AR":
        value, used_fallback = pf_ar(price, day_index, history)
        if used_fallback:
            fallback = "pf_ar_regression_undefined"
    else:
        raise ValueError(f"未知预测器：{method}")
    if not history:
        fallback = "fallback_constant_price"
    return {
        "method": method,
        "price": value,
        "history_size": len(history),
        "fallback": fallback,
    }


def predict_day(price: np.ndarray, day_index: int, *, method: str = PRIMARY_METHOD) -> np.ndarray:
    """便捷包装：只取预测价向量（调用方已承诺 ``day_index`` 与信息集口径）。"""
    return np.asarray(predict(price, day_index, method)["price"], dtype=float)


def _metrics(actual: np.ndarray, forecast: np.ndarray) -> dict[str, float]:
    error = np.abs(actual - forecast)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(actual > 0, error / np.where(actual > 0, actual, 1.0), 0.0)
    return {
        "mae": float(error.mean()),
        "mape": float(ratio.mean()),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "bias": float((forecast - actual).mean()),
        "p50": float(np.percentile(error, 50)),
        "p90": float(np.percentile(error, 90)),
        "p99": float(np.percentile(error, 99)),
        "max": float(error.max()),
    }


def roll_backtest(
    price: np.ndarray,
    *,
    days: int = DAYS_FULL,
    methods: tuple[str, ...] = ALL_METHODS,
    selection_methods: tuple[str, ...] = BASELINE_METHODS,
) -> dict[str, object]:
    """滚动回测（BT-1…BT-6）：只用 ``t`` 日之前的信息，主判据窗口 ``D_req``（334 天）。

    ``D_full`` = 剔除 2025-01-01 的 364 天（诊断窗口）；``D_req`` = 2025-02-01…12-31（334 天，主判据）。
    ``selection_methods`` 为**参与主口径选择**的预测器集合（默认三个强制基准；
    ``PF-AR`` 按 AS08 登记为 ``ablation`` 强制对照，**不参与主口径选择**，其指标仍全量落盘）。
    """
    matrix = np.asarray(price, dtype=float)
    day_rows = list(range(1, min(days, matrix.shape[0])))
    windows = {
        "D_req": [d for d in day_rows if d >= D_REQ_START],
        "D_full": day_rows,
    }
    forecasts: dict[str, np.ndarray] = {}
    fallback_counts: dict[str, dict[str, int]] = {}
    for method in methods:
        stack = np.empty((len(day_rows), matrix.shape[1]), dtype=float)
        counters = {"fallback_constant_price": 0, "pf_ar_regression_undefined": 0}
        for offset, day in enumerate(day_rows):
            item = predict(matrix, day, method)
            stack[offset] = np.asarray(item["price"], dtype=float)
            if item["fallback"]:
                counters[str(item["fallback"])] += 1
        forecasts[method] = stack
        fallback_counts[method] = counters

    report: dict[str, object] = {
        "protocol": {
            "information_set": "H_d = {d' : d' < d}（显式入参；禁止使用 d 当日与未来信息）",
            "windows": {
                "D_req": "2025-02-01…2025-12-31（334 天，主判据）",
                "D_full": "2025-01-02…2025-12-31（364 天，诊断）",
            },
            "metrics": "MAE（主判据）、MAPE、RMSE、bias、绝对误差 P50/P90/P99、逐日 MAE 夺冠计数",
            "selection_rule": "D_req MAE 最小；MAE 相对差 < 1% 视为并列，取更简者（BT-5）",
            "frozen": True,
        },
        "formulas": METHOD_FORMULAS,
        "days_available": len(day_rows),
        "fallbacks": fallback_counts,
        "windows": {},
        "method_metrics": {},
    }
    for window_name, window_days in windows.items():
        offsets = [day - 1 for day in window_days]
        actual = matrix[np.asarray(window_days, dtype=int), :]
        entry: dict[str, object] = {"days": len(window_days), "first_day": window_days[0], "last_day": window_days[-1]}
        per_method: dict[str, dict[str, float]] = {}
        daily_mae: dict[str, np.ndarray] = {}
        for method in methods:
            stack = forecasts[method][np.asarray(offsets, dtype=int), :]
            per_method[method] = _metrics(actual, stack)
            daily_mae[method] = np.abs(actual - stack).mean(axis=1)
        wins = {method: 0 for method in methods}
        ties = 0
        for index in range(len(window_days)):
            values = np.array([daily_mae[method][index] for method in methods])
            best = float(values.min())
            winners = [method for method in methods if daily_mae[method][index] <= best + 1e-12]
            if len(winners) > 1:
                ties += 1
            for method in winners:
                wins[method] += 1
        for method in methods:
            per_method[method]["daily_mae_win_days"] = float(wins[method])
            per_method[method]["daily_mae_win_fraction"] = float(wins[method] / max(len(window_days), 1))
        entry["metrics"] = per_method
        entry["tie_days"] = ties
        report["windows"][window_name] = entry  # type: ignore[index]

    main_window = report["windows"]["D_req"]  # type: ignore[index]
    mae_table = {
        method: float(main_window["metrics"][method]["mae"])  # type: ignore[index]
        for method in selection_methods
    }
    ordered = sorted(mae_table.items(), key=lambda item: (item[1], SIMPLICITY_RANK.get(item[0], 99)))
    best_mae = ordered[0][1]
    tied = [
        name for name, value in mae_table.items()
        if best_mae > 0 and (value - best_mae) / best_mae < MAE_TIE_RELATIVE_TOL
    ]
    selected = sorted(tied, key=lambda name: SIMPLICITY_RANK.get(name, 99))[0] if tied else ordered[0][0]
    report["selection"] = {
        "window": "D_req",
        "selection_methods": list(selection_methods),
        "mae_by_method": mae_table,
        "relative_difference_vs_best": {
            name: (0.0 if best_mae == 0 else (value - best_mae) / best_mae) for name, value in mae_table.items()
        },
        "tie_tolerance": MAE_TIE_RELATIVE_TOL,
        "tied_methods": tied,
        "selected": selected,
        "simplicity_rank": SIMPLICITY_RANK,
        "baseline_methods": list(BASELINE_METHODS),
        "ablation_methods": list(ABLATION_METHODS),
        "note": (
            "PF-AR 只作 ablation 强制对照，按 AS08 不参与主口径选择；"
            "所有预测器的指标（含 PF-AR）仍全量落盘于 windows 中。"
        ),
    }
    return report


def kappa_m(price: np.ndarray, day_index: int, m: int) -> dict[str, object]:
    """``4-3`` 调整层的水平校正因子 ``κ_m``（(K-3)/(K-4)）。

    ``A_m`` = 当日 ``i ≤ 6m`` 实际均价；``B_m`` = **前一日同段** ``i ≤ 6m`` 均价；
    ``κ_m = clip(A_m/B_m, 0.5, 2.0)``；``κ_0 ≡ 1``。每次截断（或缺失前一日）**逐个登记**，禁止静默截断。
    """
    matrix = np.asarray(price, dtype=float)
    if m == 0:
        return {
            "day_index": int(day_index),
            "m": 0,
            "a_m": None,
            "b_m": None,
            "raw": None,
            "kappa": 1.0,
            "clipped": False,
            "reason": "kappa_0_identity",
        }
    if m not in (6, 12, 18):
        raise ValueError(f"m 必须属于 {{0,6,12,18}}，收到 {m}")
    cutoff = 6 * m
    a_m = float(matrix[day_index, :cutoff].mean())
    if day_index - 1 < 0:
        return {
            "day_index": int(day_index),
            "m": int(m),
            "a_m": a_m,
            "b_m": None,
            "raw": None,
            "kappa": 1.0,
            "clipped": False,
            "reason": "no_previous_day_kappa_neutral",
        }
    b_m = float(matrix[day_index - 1, :cutoff].mean())
    if b_m <= 0:
        return {
            "day_index": int(day_index),
            "m": int(m),
            "a_m": a_m,
            "b_m": b_m,
            "raw": None,
            "kappa": 1.0,
            "clipped": False,
            "reason": "zero_denominator_kappa_neutral",
        }
    raw = a_m / b_m
    clipped_value = min(KAPPA_UPPER, max(KAPPA_LOWER, raw))
    return {
        "day_index": int(day_index),
        "m": int(m),
        "a_m": a_m,
        "b_m": b_m,
        "raw": raw,
        "kappa": float(clipped_value),
        "clipped": bool(clipped_value != raw),
        "reason": "clip_to_bounds" if clipped_value != raw else "ok",
    }


def kappa_schedule(price: np.ndarray, day_index: int) -> dict[str, object]:
    """一日的 ``κ_m`` 全表（``m = 0/6/12/18``）与截断登记。"""
    records = [kappa_m(price, day_index, m) for m in DECISION_HOURS]
    clipped = [item for item in records if item["clipped"]]
    return {
        "day_index": int(day_index),
        "records": records,
        "kappa": {int(item["m"]): float(item["kappa"]) for item in records},
        "clip_events": clipped,
    }


def layer_price(
    price: np.ndarray,
    day_index: int,
    m: int,
    kappa: float,
    *,
    periods: int = PERIODS_PER_DAY,
) -> np.ndarray:
    """按 (K-2) 构造第 ``m`` 层的决策价 ``\\hat p^{(m)}_{d,i}``。

    ``i ≤ 6m`` 用当日**已实现**实际价；``i > 6m`` 用 ``κ_m · p^{act}_{d−1,i}``；
    ``m = 0`` 时全天为 ``p^{act}_{d−1,i}``（``κ_0 ≡ 1``，与 (PF-PERSIST) 逐项相同）。
    无前一日（``d = 2025-01-01`）时未实现部分的基项取常量中性价 ``1.0``（回退登记在调用方）。
    """
    matrix = np.asarray(price, dtype=float)
    out = np.empty(periods, dtype=float)
    cutoff = 6 * m
    base = matrix[day_index - 1] if day_index - 1 >= 0 else fallback_price(periods)
    out[cutoff:] = kappa * base[cutoff:]
    if m > 0:
        out[:cutoff] = matrix[day_index, :cutoff]
    return out


def belief_price(
    price: np.ndarray, day_index: int, kappas: dict[int, float], *, periods: int = PERIODS_PER_DAY
) -> np.ndarray:
    """(G-4) 决策层信念价 ``\\hat p^{fc}_{d,i} = \\hat p^{(ν(i))}_{d,i}``，``ν(i)=6·⌊(i−1)/36⌋``。

    由于 ``i ∈ D_m`` 必有 ``i > 6m``，本式逐段等价于 ``κ_{ν(i)} · p^{act}_{d−1,i}``（``κ_0 ≡ 1``）。
    """
    matrix = np.asarray(price, dtype=float)
    index = np.arange(1, periods + 1)
    nu = 6 * ((index - 1) // 36)
    base = matrix[day_index - 1] if day_index - 1 >= 0 else fallback_price(periods)
    factors = np.array([float(kappas.get(int(hour), 1.0)) for hour in nu], dtype=float)
    return factors * base


__all__ = [
    "ABLATION_METHODS",
    "ALL_METHODS",
    "AR_MIN_PAIRS",
    "BASELINE_METHODS",
    "DAYS_FULL",
    "D_REQ_START",
    "DECISION_HOURS",
    "DUAL_RECENT_DAYS",
    "FALLBACK_CONSTANT_PRICE",
    "KAPPA_LOWER",
    "KAPPA_UPPER",
    "MAE_TIE_RELATIVE_TOL",
    "METHOD_FORMULAS",
    "PERIODS_PER_DAY",
    "PRIMARY_METHOD",
    "SIMPLICITY_RANK",
    "available_history",
    "belief_price",
    "fallback_price",
    "kappa_m",
    "kappa_schedule",
    "layer_price",
    "pf_ar",
    "pf_dual",
    "pf_hist",
    "pf_persist",
    "predict",
    "predict_day",
    "roll_backtest",
]
