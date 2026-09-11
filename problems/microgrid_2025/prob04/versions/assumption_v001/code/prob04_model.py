# -*- coding: utf-8 -*-
"""prob04 两条链（``4-2`` 逐日 LP / ``4-3`` 三层顺序向前递推 LP）的建模、求解与结构自检。

严格对应 ``problems/microgrid_2025/prob04/versions/assumption_v001``（AS01–AS23 + 团队 ``A8-(b)`` 六条派生）
与 ``formulations/formulation_v001``（§1.4 降尺度、§2.2–§2.6 链 ``4-2``、§3.2–§3.7 链 ``4-3``、§4.2 ``A2-PRE``）：

```
链 4-2（M4-2，逐日向前递推）
  for d in D_full:
      计划层 (PL2_d): min Σ \\hat p_{d,i}·b_i + Σ α_em·\\hat p_{d,i}·q_em_i   （q_em 变量**必须保留**）
      提交全天 (b, c, q_dis, s) 与 E 轨迹；q := b（4-2 无独立 q 变量，F-3）
      结算层 (ST2_d): 闭式 r = b + q_dis + PV^act·Δt − L·Δt − c；s' = max(0,r)；q_em = max(0,−r)

链 4-3（M4-3，三层顺序向前递推）
  for d in D_full:
      计划层 (PL_d)  : m=0，用 Π_0[PV] 与 \\hat p^{(0)}，min Σ \\hat p^{(0)}·b；**不含 q_em**；提交 D_0 = i = 1..36
      调整层 (AD_{d,m}): m ∈ {6,12,18}，用 Π_m[PV] 与 \\hat p^{(m)} = κ_m·p^{act}_{d−1}（i > 6m），
                        b 为参数，顺序重优化 R_m，只提交 D_m = {i : 6m < i ≤ 6m+36}
      结算层 (ST_d)  : 与 4-2 逐项相同的闭式（PV^act 与 p^{act} 的唯一入口）
```

口径（两链不得逐问更改）：``Δt = 1/6``、``η_ch = η_dis = 0.9``、``c ≤ 833.3333``、``q_dis ≤ 750.0000``、
``E ∈ [1200, 10800]``、``E_{1/1,0} = 6000``、终端自由、``α_em = 5``（两链）、``β_def = 0.5`` / ``β_over = 1.5``
（仅 ``4-3``）；费用以**元**计且**不乘** ``Δt``。

求解器：CPU HiGHS（``scipy.optimize.linprog(method="highs")``）；两条链**都不使用 GPU**、不依赖随机源。

统一 tie-break（AS21，承 prob03 团队裁定 T7-1/T9）：所有层、所有模型一律「先 ``min`` 该层主目标、
再在主目标最优面上 ``min Σ_t (c_t + q_dis_t)``」；字面 ε 加权式只作**逐层诊断**，不作提交解。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from prob04_predict import D_REQ_START, DECISION_HOURS
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, csr_matrix, vstack

DELTA_T = 1.0 / 6.0
ETA_CH = 0.9
ETA_DIS = 0.9
ETA_ROUND_TRIP = ETA_CH * ETA_DIS
E_INIT = 6000.0
E_MIN = 1200.0
E_MAX = 10800.0
P_MAX = 5000.0
C_CAP = P_MAX * DELTA_T                 # 833.3333 kWh（并网点侧为紧侧）
Q_CAP = P_MAX * DELTA_T * ETA_DIS       # 750.0000 kWh（电池侧为紧侧）
ALPHA_EM = 5.0
BETA_DEF = 0.5
BETA_OVER = 1.5
PERIODS_PER_DAY = 144
DAYS_FULL = 365
TOL = 1e-6
LAYER_TOL = 1e-6
LAYER_TOL_RELATIVE = 1e-8
BALANCE_TOL = 1e-8
BLOCK_ROWS = 24
BLOCKS_PER_DAY = 6
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
CROSS_YEAR_DROPPED: dict[int, tuple[int, int]] = {6: (19, 24), 12: (13, 24), 18: (7, 24)}
COMMIT_BLOCK = 36
DELIVERY_MAGNITUDE_BAND_YUAN = (3.0e6, 5.0e7)
DAILY_MAGNITUDE_BAND_YUAN = (5.0e3, 2.0e5)

# --- AS21（承 prob03 T7-1/T7-2/T7-3/T7-5）：统一冻结 tie-breaking --------------------------
T7_EPS_RELATIVE = 1e-6
T7_INVARIANCE_TOL = 1e-9
T7_SHRINK_FACTOR = 0.1
T7_MAX_SHRINKS = 8
T7_FACE_TOL_RELATIVE = 1e-9
T7_FACE_TOL_ABSOLUTE = 1e-9
T7_FACE_PRIMARY_TOL_FRACTION = 0.5
T7_TIEBREAK_RULE = (
    "min [该层主目标] + ε·Σ_t(c_{d,t}+q_dis_{d,t})，"
    "ε = 1e-6·max(|该层主目标最优值|,1)/[n·(c_cap+q_dis_cap)]；"
    "所有层、所有模型（4-2/4-3/A2-PRE/ablation 对照）必须完全一致（AS21 承 prob03 T7-1/T7-5）"
)


class LayerFailure(RuntimeError):
    """某个决策层 LP 未达最优：由调用方按 ``solver_not_optimal`` 路由（不得伪报最优）。"""

    def __init__(self, message: str, *, day: int, hour: int, status: int) -> None:
        super().__init__(message)
        self.day = day
        self.hour = hour
        self.status = status


class BudgetExceeded(RuntimeError):
    """墙钟预算耗尽：按 ``solver_not_optimal`` 路由并保留已完成层的证据，不得伪报完成。"""


@dataclass(frozen=True)
class ChainInputs:
    """一条链的输入（按天展开）。

    ``price_act``：附件 4 的实际价（结算用，两链唯一价格入口）；
    ``decision_price``：计划层的决策价 ``\\hat p``（``4-2`` = (PF-PERSIST)；``4-3`` = ``\\hat p^{(0)}``）；
    ``forecast_kw``：``4-3`` 的 ``hour → (days, 144)`` 降尺度预报（未支配时段为 NaN）；``4-2`` 为空字典。
    """

    days: int
    price_act: np.ndarray
    decision_price: np.ndarray
    load_energy: np.ndarray
    pv_act_energy: np.ndarray
    forecast_kw: dict[int, np.ndarray] = field(default_factory=dict)

    @property
    def periods(self) -> int:
        return int(self.days * PERIODS_PER_DAY)

    def forecast_energy(self, hour: int) -> np.ndarray:
        return self.forecast_kw[hour] * DELTA_T


@dataclass
class LayerRecord:
    day: int
    hour: int
    layer: str
    status: int
    message: str
    iterations: int | None
    objective: float
    equality_residual_max: float
    equality_residual_relative_max: float
    inequality_residual_max: float
    inequality_residual_relative_max: float
    bound_violation_max: float
    seconds: float
    variables: int
    equality_rows: int
    inequality_rows: int
    nonzero: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "day_index": self.day,
            "hour": self.hour,
            "layer": self.layer,
            "status": self.status,
            "message": self.message,
            "iterations": self.iterations,
            "objective_yuan": self.objective,
            "equality_residual_max": self.equality_residual_max,
            "equality_residual_relative_max": self.equality_residual_relative_max,
            "inequality_residual_max": self.inequality_residual_max,
            "inequality_residual_relative_max": self.inequality_residual_relative_max,
            "bound_violation_max": self.bound_violation_max,
            "seconds": self.seconds,
            "variables": self.variables,
            "equality_rows": self.equality_rows,
            "inequality_rows": self.inequality_rows,
            "nonzero": self.nonzero,
        }


@dataclass
class TiebreakRecord:
    """AS21 的逐层审计记录（主目标不变性 / 吞吐量 / 退化维度 / 边界状态 / 提交解来源）。"""

    layer: str
    day: int
    hour: int
    primary_before_yuan: float
    primary_after_yuan: float
    primary_relative_change: float
    epsilon: float
    shrinks: int
    invariance_passed: bool
    throughput_kwh: float
    throughput_before_kwh: float
    throughput_reduced_kwh: float
    baseline_state_change_max_kwh: float
    degeneracy_degree: int
    active_constraints: int
    variables: int
    weighted_primary_relative_change: float
    weighted_throughput_kwh: float
    weighted_sum_effective: bool
    committed_solution: str
    throughput_upper_on_optimal_face_kwh: float | None
    throughput_unique: bool | None
    probe_status: int | None
    boundary_state_kwh: float
    baseline_seconds: float
    solver_seconds: float
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "day_index": int(self.day),
            "hour": int(self.hour),
            "primary_before_yuan": _finite_or(self.primary_before_yuan),
            "primary_after_yuan": _finite_or(self.primary_after_yuan),
            "primary_relative_change": _finite_or(self.primary_relative_change),
            "epsilon": _finite_or(self.epsilon),
            "shrinks": int(self.shrinks),
            "invariance_passed": bool(self.invariance_passed),
            "throughput_kwh": _finite_or(self.throughput_kwh),
            "throughput_before_kwh": _finite_or(self.throughput_before_kwh),
            "throughput_reduced_kwh": _finite_or(self.throughput_reduced_kwh),
            "baseline_state_change_max_kwh": _finite_or(self.baseline_state_change_max_kwh),
            "degeneracy_degree": int(self.degeneracy_degree),
            "active_constraints": int(self.active_constraints),
            "variables": int(self.variables),
            "weighted_primary_relative_change": _finite_or(self.weighted_primary_relative_change),
            "weighted_throughput_kwh": _finite_or(self.weighted_throughput_kwh),
            "weighted_sum_effective": bool(self.weighted_sum_effective),
            "committed_solution": self.committed_solution,
            "throughput_upper_on_optimal_face_kwh": (
                None if self.throughput_upper_on_optimal_face_kwh is None
                else _finite_or(self.throughput_upper_on_optimal_face_kwh)
            ),
            "throughput_unique": (
                None if self.throughput_unique is None else bool(self.throughput_unique)
            ),
            "probe_status": None if self.probe_status is None else int(self.probe_status),
            "boundary_state_kwh": _finite_or(self.boundary_state_kwh),
            "baseline_seconds": _finite_or(self.baseline_seconds),
            "solver_seconds": _finite_or(self.solver_seconds),
            "note": self.note,
        }


@dataclass
class ChainResult:
    """一条链的完整解（提交链 + 计划轨迹 + 审计记录；两链共用同一容器）。"""

    chain: str
    days: int
    price_act: np.ndarray          # (days, 144) 附件 4 实际价
    price_fc: np.ndarray           # (days, 144) 决策层信念价 \hat p^{fc}
    decision_price: np.ndarray     # (days, 144) 计划层决策价 \hat p（4-2 与 4-3 同式）
    load_energy: np.ndarray        # (days, 144) kWh = L·Δt（附件 2 实际）
    pv_act_energy: np.ndarray      # (days, 144) kWh = PV^act·Δt（附件 2 实际）
    plan_b: np.ndarray
    q: np.ndarray                  # 最终量（4-2 中 q := b）
    c: np.ndarray
    q_dis: np.ndarray
    E: np.ndarray
    q_em: np.ndarray
    s_settle: np.ndarray
    plan_c: np.ndarray
    plan_q_dis: np.ndarray
    plan_s: np.ndarray
    plan_E: np.ndarray
    plan_q_em: np.ndarray          # 计划层解中的 q_em 变量（4-2 保留变量；4-3 无该变量，恒 0）
    layer_records: list[LayerRecord] = field(default_factory=list)
    tiebreak_records: list[TiebreakRecord] = field(default_factory=list)
    kappa_records: list[dict[str, Any]] = field(default_factory=list)
    fallback_records: list[dict[str, Any]] = field(default_factory=list)
    # 支配层光伏电量矩阵（4-2：{0: PV^act·Δt}；4-3：{m: Π_m[PV]·Δt}），供层内余额核对使用
    layer_pv_energy: dict[int, np.ndarray] = field(default_factory=dict)

    @property
    def periods(self) -> int:
        return int(self.days * PERIODS_PER_DAY)


def _finite_or(value: float, fallback: float = 1e30) -> float:
    """把非有限值替换为有限哨兵，保证 ``allow_nan=False`` 的 JSON 落盘不失败。"""
    number = float(value)
    return number if np.isfinite(number) else float(fallback)


def dominance_map(periods: int = PERIODS_PER_DAY) -> np.ndarray:
    """支配时刻 ``ν(i)``：``i = 1..144`` → ``0/6/12/18``（每层 36 个时段）。"""
    index = np.arange(1, periods + 1)
    return 6 * ((index - 1) // COMMIT_BLOCK)


def downscale(pv_row: np.ndarray, hour: int, *, periods: int = PERIODS_PER_DAY) -> np.ndarray:
    """AS19/formulation §1.4 的降尺度算子 ``Π_m``（整点点值 + 整点锚定线性插值）。

    ``pv_row[k−1] = A_{m,k}``（``(m+k):00`` 的功率点值，``k = 1..24``）。时段 ``i`` 的块
    ``b = ⌈i/6⌉``、块内位置 ``j = i − 6(b−1)``，时效 ``k = b − m``：

    * ``k = 1``：前向保持 ``A_{m,1}``（发布后第一小时无 ``P(m)``）；
    * ``2 ≤ k ≤ 24``：``(1 − j/6)·A_{m,k−1} + (j/6)·A_{m,k}``；
    * ``k < 1``（早于发布时刻）：**未定义（NaN）**，不消费。

    跨年项（``m + k > 24``，即 ``k > 24 − m``）在本函数中**不产生任何输出**（该时段落在次日、
    不在当日 144 时段内），其个数由 :func:`cross_year_dropped_count` 登记。
    """
    row = np.asarray(pv_row, dtype=float).reshape(-1)
    if row.shape[0] != 24:
        raise ValueError(f"预报向量长度 {row.shape[0]} != 24")
    if hour not in DECISION_HOURS:
        raise ValueError(f"未知发布时刻：{hour}")
    out = np.full(periods, np.nan, dtype=float)
    for index in range(1, periods + 1):
        block = (index - 1) // 6 + 1
        position = index - 6 * (block - 1)
        lead = block - hour
        if lead < 1:
            continue
        if lead == 1:
            out[index - 1] = row[0]
        else:
            out[index - 1] = (1.0 - position / 6.0) * row[lead - 2] + (position / 6.0) * row[lead - 1]
    return out


def cross_year_dropped_count(hour: int) -> int:
    """跨年项个数：``m = 6/12/18`` 分别丢弃 6/12/18 项（合计 36，§1.4 / §8.4）。"""
    if hour == 0:
        return 0
    low, high = CROSS_YEAR_DROPPED[hour]
    return int(high - low + 1)


def block_energy_bias(pv_row: np.ndarray, hour: int) -> dict[str, float]:
    """块内能量偏差统计（**强制披露**，§1.4）：插值 vs 分段常数。

    块 ``b`` 的 6 个时段之和 ``= (2.5·A_{k−1} + 3.5·A_k)/6``（``k ≥ 2``），分段常数口径为 ``A_k``；
    逐块给出二者之差与绝对差之和（``k = 1`` 的块两口径相同，差为 0）。
    """
    row = np.asarray(pv_row, dtype=float).reshape(-1)
    total_interp = 0.0
    total_piecewise = 0.0
    biases: list[float] = []
    for block in range(hour + 1, 25):
        lead = block - hour
        if lead == 1:
            interp = row[0]
        else:
            interp = (2.5 * row[lead - 2] + 3.5 * row[lead - 1]) / 6.0
        piecewise = row[lead - 1]
        biases.append(float(interp - piecewise))
        total_interp += float(interp)
        total_piecewise += float(piecewise)
    return {
        "blocks": float(len(biases)),
        "sum_interpolated_kwh": total_interp,
        "sum_piecewise_constant_kwh": total_piecewise,
        "net_bias_kwh": total_interp - total_piecewise,
        "max_abs_block_bias_kwh": max((abs(item) for item in biases), default=0.0),
        "sum_abs_block_bias_kwh": float(np.sum(np.abs(biases))) if biases else 0.0,
    }


def _solve(
    objective: np.ndarray,
    a_eq: csr_matrix,
    b_eq: np.ndarray,
    a_ub: csr_matrix | None,
    b_ub: np.ndarray | None,
    bounds: np.ndarray,
    *,
    time_limit_seconds: float,
) -> tuple[Any, float]:
    started = time.perf_counter()
    result = linprog(
        objective,
        A_eq=a_eq,
        b_eq=b_eq,
        A_ub=a_ub,
        b_ub=b_ub,
        bounds=bounds,
        method="highs",
        options={"time_limit": float(time_limit_seconds), "presolve": True},
    )
    return result, time.perf_counter() - started


def _inf_norm(matrix: csr_matrix) -> float:
    """稀疏矩阵的 ∞-范数（最大绝对行和），用于尺度感知的相对残差分母。"""
    if matrix.shape[0] == 0:
        return 0.0
    return float(np.max(np.abs(matrix).sum(axis=1)))


def _relative_residual(residual: float, matrix: csr_matrix, rhs: np.ndarray, x: np.ndarray) -> float:
    """标准尺度感知相对残差：``residual / max(1, ‖A‖∞·‖x‖∞ + ‖b‖∞)``。"""
    denominator = max(
        1.0,
        _inf_norm(matrix) * float(np.max(np.abs(x))) + float(np.max(np.abs(rhs))),
    )
    return max(float(residual), 0.0) / denominator


def _residuals(
    result: Any,
    a_eq: csr_matrix,
    b_eq: np.ndarray,
    a_ub: csr_matrix | None,
    b_ub: np.ndarray | None,
    bounds: np.ndarray,
) -> tuple[float, float, float, float, float]:
    """返回 ``(等式残差, 不等式残差, 界越界量, 等式相对残差, 不等式相对残差)``。"""
    if result.x is None:
        return float("nan"), float("nan"), float("nan"), float("nan"), float("nan")
    x = np.asarray(result.x, dtype=float)
    equality = float(np.max(np.abs(a_eq @ x - b_eq)))
    equality_relative = _relative_residual(equality, a_eq, b_eq, x)
    if a_ub is None or a_ub.shape[0] == 0:
        inequality, inequality_relative = 0.0, 0.0
    else:
        inequality = float(np.max(a_ub @ x - b_ub))
        inequality_relative = _relative_residual(inequality, a_ub, b_ub, x)
    lower = bounds[:, 0]
    upper = bounds[:, 1]
    violation_low = float(np.max(lower - x))
    finite = np.isfinite(upper)
    violation_up = float(np.max((x - upper)[finite])) if finite.any() else -np.inf
    bound = max(violation_low, violation_up, 0.0)
    return equality, inequality, bound, equality_relative, inequality_relative


def throughput_scale(periods: int) -> float:
    """该层吞吐量 ``Σ_t(c_{d,t}+q_dis_{d,t})`` 的紧上界（AS21 的 ε 相对化分母）。"""
    return float(periods) * (C_CAP + Q_CAP)


def throughput_coefficients(size: int, c_offset: int, q_dis_offset: int, periods: int) -> np.ndarray:
    """AS21 的次目标系数向量：``c`` 与 ``q_dis`` 位置为 1，其余为 0（共享算子，所有链/模型一致）。"""
    coefficients = np.zeros(size)
    coefficients[c_offset : c_offset + periods] = 1.0
    coefficients[q_dis_offset : q_dis_offset + periods] = 1.0
    return coefficients


def tiebreak_epsilon(primary_reference: float, scale: float) -> float:
    """AS21 的 ``ε``：``1e-6 × max(|主目标尺度|,1) / 吞吐量尺度``（无量纲、确定性）。"""
    return T7_EPS_RELATIVE * max(abs(float(primary_reference)), 1.0) / max(float(scale), 1.0)


def _degeneracy_proxy(
    x: np.ndarray,
    n_variables: int,
    a_eq: csr_matrix,
    a_ub: csr_matrix | None,
    b_ub: np.ndarray | None,
    bounds: np.ndarray,
    *,
    tol: float,
) -> tuple[int, int]:
    """退化维度代理 = 活跃约束数（等式 + 紧不等式 + 贴界变量） − 变量数。"""
    active = int(a_eq.shape[0])
    if a_ub is not None and a_ub.shape[0]:
        slack = np.asarray(a_ub @ x - b_ub, dtype=float).reshape(-1)
        active += int(np.sum(slack >= -tol))
    lower = bounds[:, 0]
    upper = bounds[:, 1]
    at_lower = x <= lower + tol
    at_upper = np.isfinite(upper) & (x >= upper - tol)
    active += int(np.sum(at_lower | at_upper))
    return active - int(n_variables), active


def _layer_record(
    result: Any,
    seconds: float,
    *,
    day: int,
    hour: int,
    layer: str,
    a_eq: csr_matrix,
    b_eq: np.ndarray,
    a_ub: csr_matrix | None,
    b_ub: np.ndarray | None,
    bounds: np.ndarray,
    objective: float | None = None,
) -> LayerRecord:
    equality, inequality, bound, equality_relative, inequality_relative = _residuals(
        result, a_eq, b_eq, a_ub, b_ub, bounds
    )
    return LayerRecord(
        day=day,
        hour=hour,
        layer=layer,
        status=int(result.status),
        message=str(result.message),
        iterations=int(result.nit) if result.nit is not None else None,
        objective=float(objective) if objective is not None else (
            float(result.fun) if result.fun is not None else float("nan")
        ),
        equality_residual_max=equality,
        equality_residual_relative_max=equality_relative,
        inequality_residual_max=inequality,
        inequality_residual_relative_max=inequality_relative,
        bound_violation_max=bound,
        seconds=seconds,
        variables=int(a_eq.shape[1]),
        equality_rows=int(a_eq.shape[0]),
        inequality_rows=int(a_ub.shape[0]) if a_ub is not None else 0,
        nonzero=int(a_eq.nnz + (a_ub.nnz if a_ub is not None else 0)),
    )


def _solve_with_tiebreak(
    *,
    primary_objective: np.ndarray,
    throughput_objective: np.ndarray,
    scale: float,
    a_eq: csr_matrix,
    b_eq: np.ndarray,
    a_ub: csr_matrix | None,
    b_ub: np.ndarray | None,
    bounds: np.ndarray,
    layer: str,
    day: int,
    hour: int,
    boundary_index: int,
    time_limit_seconds: float,
) -> tuple[Any, LayerRecord, TiebreakRecord]:
    """AS21 的共享求解器（承 prob03 团队 T7 的四段式；两链所有层与所有对照模型必须复用）。

    ① **基线**：纯主目标 LP → ``P*``（不变性判定的「加入次目标前」）；
    ② **字面加权式**：``min [主目标] + ε·Σ(c+q_dis)``；ε 按逐层验证，不满足则按
       ``T7_SHRINK_FACTOR`` 缩小后重跑（有界）；该式只作**诊断**，不作提交解；
    ③ **字典序提交解**（AS21 优先序在 ``ε→0⁺`` 的精确实现）：在主目标最优面
       ``{primary ≤ P* + 1e-9·max(|P*|,1)}`` 上**最小化**吞吐量；
    ④ **退化探测**：在同一主目标最优面上**最大化**吞吐量，判定是否仍存在多重最优。
    """
    n_variables = int(primary_objective.shape[0])
    total_seconds = 0.0
    primary_row = np.asarray(primary_objective, dtype=float).reshape(1, -1)

    baseline_result, baseline_seconds = _solve(
        primary_objective, a_eq, b_eq, a_ub, b_ub, bounds, time_limit_seconds=time_limit_seconds
    )
    total_seconds += baseline_seconds
    if baseline_result.x is None:
        record = _layer_record(
            baseline_result, baseline_seconds, day=day, hour=hour, layer=layer,
            a_eq=a_eq, b_eq=b_eq, a_ub=a_ub, b_ub=b_ub, bounds=bounds,
        )
        return baseline_result, record, TiebreakRecord(
            layer=layer, day=day, hour=hour,
            primary_before_yuan=float("nan"), primary_after_yuan=float("nan"),
            primary_relative_change=float("inf"), epsilon=float("nan"), shrinks=0,
            invariance_passed=False, throughput_kwh=float("nan"),
            throughput_before_kwh=float("nan"), throughput_reduced_kwh=float("nan"),
            baseline_state_change_max_kwh=float("nan"), degeneracy_degree=-1,
            active_constraints=-1, variables=n_variables,
            weighted_primary_relative_change=float("inf"), weighted_throughput_kwh=float("nan"),
            weighted_sum_effective=False, committed_solution="none",
            throughput_upper_on_optimal_face_kwh=None, throughput_unique=None,
            probe_status=None, boundary_state_kwh=float("nan"),
            baseline_seconds=baseline_seconds, solver_seconds=total_seconds,
            note="baseline_not_optimal",
        )

    x_baseline = np.asarray(baseline_result.x, dtype=float)
    primary_before = float(np.dot(primary_objective, x_baseline))
    throughput_before = float(np.dot(throughput_objective, x_baseline))
    tol_primary = T7_FACE_PRIMARY_TOL_FRACTION * T7_INVARIANCE_TOL * max(abs(primary_before), 1.0)

    epsilon = tiebreak_epsilon(primary_before, scale)
    shrinks = 0
    weighted_result = baseline_result
    weighted_seconds = baseline_seconds
    weighted_primary = primary_before
    weighted_relative = 0.0
    for attempt in range(T7_MAX_SHRINKS + 1):
        combined = primary_objective + epsilon * throughput_objective
        weighted_result, weighted_seconds = _solve(
            combined, a_eq, b_eq, a_ub, b_ub, bounds, time_limit_seconds=time_limit_seconds
        )
        total_seconds += weighted_seconds
        if weighted_result.x is None:
            break
        x_weighted = np.asarray(weighted_result.x, dtype=float)
        weighted_primary = float(np.dot(primary_objective, x_weighted))
        weighted_relative = abs(weighted_primary - primary_before) / max(abs(primary_before), 1.0)
        if weighted_relative <= T7_INVARIANCE_TOL or attempt >= T7_MAX_SHRINKS:
            break
        epsilon *= T7_SHRINK_FACTOR
        shrinks += 1
    weighted_ok = weighted_result.x is not None
    weighted_throughput = (
        float(np.dot(throughput_objective, np.asarray(weighted_result.x, dtype=float))) if weighted_ok
        else float("nan")
    )

    if a_ub is not None and a_ub.shape[0]:
        face_a_ub = vstack([a_ub, csr_matrix(primary_row)]).tocsr()
        face_b_ub = np.concatenate([np.asarray(b_ub, dtype=float), [primary_before + tol_primary]])
    else:
        face_a_ub = csr_matrix(primary_row)
        face_b_ub = np.array([primary_before + tol_primary])
    lex_result, lex_seconds = _solve(
        throughput_objective, a_eq, b_eq, face_a_ub, face_b_ub, bounds,
        time_limit_seconds=time_limit_seconds,
    )
    total_seconds += lex_seconds
    committed_solution = "lexicographic"
    if lex_result.x is not None and int(lex_result.status) == 0:
        result = lex_result
    elif weighted_ok:
        result = weighted_result
        committed_solution = "weighted_sum_fallback"
    else:
        result = baseline_result
        committed_solution = "baseline_fallback"
    x = np.asarray(result.x, dtype=float)
    primary_after = float(np.dot(primary_objective, x))
    relative = abs(primary_after - primary_before) / max(abs(primary_before), 1.0)
    throughput = float(np.dot(throughput_objective, x))
    invariance_passed = bool(relative <= T7_INVARIANCE_TOL)
    weighted_sum_effective = bool(
        weighted_ok
        and weighted_relative <= T7_INVARIANCE_TOL
        and (weighted_throughput - throughput) <= max(T7_FACE_TOL_ABSOLUTE, T7_FACE_TOL_RELATIVE * abs(throughput))
    )
    boundary_state = float(x[boundary_index])
    state_change = float(np.max(np.abs(x - x_baseline)))
    degeneracy_degree, active_constraints = _degeneracy_proxy(
        x, n_variables, a_eq, a_ub, b_ub, bounds, tol=TOL
    )

    probe_result, probe_seconds = _solve(
        -throughput_objective, a_eq, b_eq, face_a_ub, face_b_ub, bounds,
        time_limit_seconds=time_limit_seconds,
    )
    total_seconds += probe_seconds
    if probe_result.x is not None and int(probe_result.status) == 0:
        throughput_upper = -float(probe_result.fun)
        throughput_unique = bool(
            (throughput_upper - throughput) <= max(T7_FACE_TOL_ABSOLUTE, T7_FACE_TOL_RELATIVE * abs(throughput))
        )
        probe_status: int | None = int(probe_result.status)
    else:
        throughput_upper = None
        throughput_unique = None
        probe_status = int(probe_result.status)

    note = ""
    if not invariance_passed:
        note = "primary_invariance_violated"
    elif not weighted_sum_effective:
        note = "weighted_sum_below_solver_resolution_lexicographic_committed"
    if committed_solution != "lexicographic":
        note = (note + ";" if note else "") + f"committed={committed_solution}"

    if committed_solution == "lexicographic":
        committed_seconds = lex_seconds
    elif committed_solution == "weighted_sum_fallback":
        committed_seconds = weighted_seconds
    else:
        committed_seconds = baseline_seconds
    record = _layer_record(
        result, committed_seconds, day=day, hour=hour, layer=layer,
        a_eq=a_eq, b_eq=b_eq, a_ub=a_ub, b_ub=b_ub, bounds=bounds,
        objective=primary_after,
    )
    tiebreak = TiebreakRecord(
        layer=layer,
        day=day,
        hour=hour,
        primary_before_yuan=primary_before,
        primary_after_yuan=primary_after,
        primary_relative_change=relative,
        epsilon=epsilon,
        shrinks=shrinks,
        invariance_passed=invariance_passed,
        throughput_kwh=throughput,
        throughput_before_kwh=throughput_before,
        throughput_reduced_kwh=throughput_before - throughput,
        baseline_state_change_max_kwh=state_change,
        degeneracy_degree=degeneracy_degree,
        active_constraints=active_constraints,
        variables=n_variables,
        weighted_primary_relative_change=weighted_relative,
        weighted_throughput_kwh=weighted_throughput,
        weighted_sum_effective=weighted_sum_effective,
        committed_solution=committed_solution,
        throughput_upper_on_optimal_face_kwh=throughput_upper,
        throughput_unique=throughput_unique,
        probe_status=probe_status,
        boundary_state_kwh=boundary_state,
        baseline_seconds=baseline_seconds,
        solver_seconds=total_seconds,
        note=note,
    )
    return result, record, tiebreak


def _balance_and_state_rows(
    n: int,
    *,
    size: int,
    pv_energy: np.ndarray,
    load_energy: np.ndarray,
    e_start: float,
    balance_offsets: tuple[int, int, int, int],
    energy_offset: int,
) -> tuple[csr_matrix, np.ndarray]:
    """构造「层内平衡 + 状态转移」两组等式（``4-2``/``4-3`` 计划层/调整层共用骨架）。

    ``balance_offsets = (purchase_offset, charge_offset, discharge_offset, spill_offset)``：
    平衡式为 ``purchase + discharge − charge − spill = L·Δt − PV^{层}·Δt``。
    """
    purchase_off, charge_off, discharge_off, spill_off = balance_offsets
    tau = np.arange(n, dtype=np.int64)
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    vals: list[np.ndarray] = []
    rows += [tau, tau, tau, tau]
    cols += [purchase_off + tau, discharge_off + tau, charge_off + tau, spill_off + tau]
    vals += [np.ones(n), np.ones(n), -np.ones(n), -np.ones(n)]
    rows += [n + tau, n + tau, n + tau[1:], n + tau]
    cols += [energy_offset + tau, charge_off + tau, energy_offset + tau[1:] - 1, discharge_off + tau]
    vals += [np.ones(n), -ETA_CH * np.ones(n), -np.ones(n - 1), (1.0 / ETA_DIS) * np.ones(n)]
    a_eq = coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(2 * n, size),
    ).tocsr()
    b_eq = np.concatenate([load_energy - pv_energy, np.concatenate([[e_start], np.zeros(n - 1)])])
    return a_eq, b_eq


def solve_day_plan_42(
    *,
    price: np.ndarray,
    load_energy: np.ndarray,
    pv_act_energy: np.ndarray,
    e_start: float,
    time_limit_seconds: float,
    day: int = -1,
) -> tuple[dict[str, np.ndarray], LayerRecord, TiebreakRecord]:
    """链 ``4-2`` 的单日计划层 ``(PL2_d)``：``min Σ\\hat p·b + Σ α_em·\\hat p·q_em``。

    变量序：``b | c | q_dis | s | E | q_em``（``6 × 144 = 864`` 变量 / ``288`` 等式）。
    ``q_em`` 变量与目标项**必须保留**（AS15/PL2-7），不得因预期恒零而删除。
    """
    n = PERIODS_PER_DAY
    size = 6 * n
    objective = np.zeros(size)
    objective[0:n] = price
    objective[5 * n : 6 * n] = ALPHA_EM * price

    spill_upper = np.maximum(0.0, pv_act_energy - load_energy)
    bounds = np.empty((size, 2), dtype=float)
    bounds[0:n, 0] = 0.0
    bounds[0:n, 1] = np.inf
    bounds[n : 2 * n, 0] = 0.0
    bounds[n : 2 * n, 1] = C_CAP
    bounds[2 * n : 3 * n, 0] = 0.0
    bounds[2 * n : 3 * n, 1] = Q_CAP
    bounds[3 * n : 4 * n, 0] = 0.0
    bounds[3 * n : 4 * n, 1] = spill_upper
    bounds[4 * n : 5 * n, 0] = E_MIN
    bounds[4 * n : 5 * n, 1] = E_MAX
    bounds[5 * n : 6 * n, 0] = 0.0
    bounds[5 * n : 6 * n, 1] = np.inf

    a_eq, b_eq = _balance_and_state_rows(
        n,
        size=size,
        pv_energy=pv_act_energy,
        load_energy=load_energy,
        e_start=e_start,
        balance_offsets=(0, n, 2 * n, 3 * n),
        energy_offset=4 * n,
    )
    # ``q_em`` 只出现在平衡式（与 b 同位）：把其系数补进前 n 行
    extra = coo_matrix(
        (np.ones(n), (np.arange(n), 5 * n + np.arange(n))), shape=(2 * n, size)
    ).tocsr()
    a_eq = (a_eq + extra).tocsr()

    throughput = throughput_coefficients(size, n, 2 * n, n)
    result, record, tiebreak = _solve_with_tiebreak(
        primary_objective=objective,
        throughput_objective=throughput,
        scale=throughput_scale(n),
        a_eq=a_eq,
        b_eq=b_eq,
        a_ub=None,
        b_ub=None,
        bounds=bounds,
        layer="plan42",
        day=day,
        hour=0,
        boundary_index=size - n - 1,
        time_limit_seconds=time_limit_seconds,
    )
    if result.x is None:
        return {}, record, tiebreak
    x = np.asarray(result.x, dtype=float)
    return (
        {
            "b": x[0:n],
            "c": x[n : 2 * n],
            "q_dis": x[2 * n : 3 * n],
            "s": x[3 * n : 4 * n],
            "E": x[4 * n : 5 * n],
            "q_em": x[5 * n : 6 * n],
        },
        record,
        tiebreak,
    )


def solve_plan_layer_43(
    *,
    price: np.ndarray,
    load_energy: np.ndarray,
    pv_fc_energy: np.ndarray,
    e_start: float,
    time_limit_seconds: float,
    day: int = -1,
) -> tuple[dict[str, np.ndarray], LayerRecord, TiebreakRecord]:
    """链 ``4-3`` 的计划层 ``(PL_d)``：``min Σ \\hat p^{(0)}·b``（``5 × 144 = 720`` 变量 / ``288`` 等式）。

    **本层不含 ``q_em`` 变量**（承 prob03 ``(PL-1)`` / formulation E-F2）。
    """
    n = PERIODS_PER_DAY
    size = 5 * n
    objective = np.zeros(size)
    objective[0:n] = price

    spill_upper = np.maximum(0.0, pv_fc_energy - load_energy)
    bounds = np.empty((size, 2), dtype=float)
    bounds[0:n, 0] = 0.0
    bounds[0:n, 1] = np.inf
    bounds[n : 2 * n, 0] = 0.0
    bounds[n : 2 * n, 1] = C_CAP
    bounds[2 * n : 3 * n, 0] = 0.0
    bounds[2 * n : 3 * n, 1] = Q_CAP
    bounds[3 * n : 4 * n, 0] = 0.0
    bounds[3 * n : 4 * n, 1] = spill_upper
    bounds[4 * n : 5 * n, 0] = E_MIN
    bounds[4 * n : 5 * n, 1] = E_MAX

    a_eq, b_eq = _balance_and_state_rows(
        n,
        size=size,
        pv_energy=pv_fc_energy,
        load_energy=load_energy,
        e_start=e_start,
        balance_offsets=(0, n, 2 * n, 3 * n),
        energy_offset=4 * n,
    )
    throughput = throughput_coefficients(size, n, 2 * n, n)
    result, record, tiebreak = _solve_with_tiebreak(
        primary_objective=objective,
        throughput_objective=throughput,
        scale=throughput_scale(n),
        a_eq=a_eq,
        b_eq=b_eq,
        a_ub=None,
        b_ub=None,
        bounds=bounds,
        layer="plan43",
        day=day,
        hour=0,
        boundary_index=size - 1,
        time_limit_seconds=time_limit_seconds,
    )
    if result.x is None:
        return {}, record, tiebreak
    x = np.asarray(result.x, dtype=float)
    return (
        {
            "b": x[0:n],
            "c": x[n : 2 * n],
            "q_dis": x[2 * n : 3 * n],
            "s": x[3 * n : 4 * n],
            "E": x[4 * n : 5 * n],
        },
        record,
        tiebreak,
    )


def solve_adjustment_layer_43(
    *,
    hour: int,
    price: np.ndarray,
    load_energy: np.ndarray,
    pv_fc_energy: np.ndarray,
    plan_b: np.ndarray,
    e_start: float,
    time_limit_seconds: float,
    day: int = -1,
) -> tuple[dict[str, np.ndarray], LayerRecord, TiebreakRecord]:
    """链 ``4-3`` 的调整层 ``(AD_{d,m})``，``m ∈ {6,12,18}``。

    变量定义在 ``R_m = {i : 6m < i ≤ 144}``（``n = 144 − 6m``）：``q | c | q_dis | s | E | u⁺ | u⁻``；
    主目标 ``min Σ_{R_m}[β_def·\\hat p^{(m)}·u⁺ + β_over·\\hat p^{(m)}·u⁻]``；``b`` 为**参数**；
    分段线性化 ``u⁺ ≥ b − q``、``u⁻ ≥ q − b``、``u^± ≥ 0``（LP 无损，§5-L5）。
    调用方只提交 ``D_m``（前 36 个时段），``R_m`` 的尾部为前瞻。
    """
    global_index = np.arange(6 * hour + 1, PERIODS_PER_DAY + 1)
    n = int(global_index.shape[0])
    size = 7 * n
    objective = np.zeros(size)
    objective[5 * n : 6 * n] = BETA_DEF * price[global_index - 1]
    objective[6 * n : 7 * n] = BETA_OVER * price[global_index - 1]

    pv_slice = pv_fc_energy[global_index - 1]
    load_slice = load_energy[global_index - 1]
    spill_upper = np.maximum(0.0, pv_slice - load_slice)
    bounds = np.empty((size, 2), dtype=float)
    bounds[0:n, 0] = 0.0
    bounds[0:n, 1] = np.inf
    bounds[n : 2 * n, 0] = 0.0
    bounds[n : 2 * n, 1] = C_CAP
    bounds[2 * n : 3 * n, 0] = 0.0
    bounds[2 * n : 3 * n, 1] = Q_CAP
    bounds[3 * n : 4 * n, 0] = 0.0
    bounds[3 * n : 4 * n, 1] = spill_upper
    bounds[4 * n : 5 * n, 0] = E_MIN
    bounds[4 * n : 5 * n, 1] = E_MAX
    bounds[5 * n : 7 * n, 0] = 0.0
    bounds[5 * n : 7 * n, 1] = np.inf

    a_eq, b_eq = _balance_and_state_rows(
        n,
        size=size,
        pv_energy=pv_slice,
        load_energy=load_slice,
        e_start=e_start,
        balance_offsets=(0, n, 2 * n, 3 * n),
        energy_offset=4 * n,
    )
    tau = np.arange(n, dtype=np.int64)
    plan_slice = plan_b[global_index - 1]
    ub_rows = [tau, tau, n + tau, n + tau]
    ub_cols = [tau, 5 * n + tau, tau, 6 * n + tau]
    ub_vals = [-np.ones(n), -np.ones(n), np.ones(n), -np.ones(n)]
    a_ub = coo_matrix(
        (np.concatenate(ub_vals), (np.concatenate(ub_rows), np.concatenate(ub_cols))),
        shape=(2 * n, size),
    ).tocsr()
    b_ub = np.concatenate([-plan_slice, plan_slice])

    throughput = throughput_coefficients(size, n, 2 * n, n)
    result, record, tiebreak = _solve_with_tiebreak(
        primary_objective=objective,
        throughput_objective=throughput,
        scale=throughput_scale(n),
        a_eq=a_eq,
        b_eq=b_eq,
        a_ub=a_ub,
        b_ub=b_ub,
        bounds=bounds,
        layer=f"adjustment{hour}",
        day=day,
        hour=hour,
        boundary_index=5 * n - 1,
        time_limit_seconds=time_limit_seconds,
    )
    if result.x is None:
        return {}, record, tiebreak
    x = np.asarray(result.x, dtype=float)
    return (
        {
            "q": x[0:n],
            "c": x[n : 2 * n],
            "q_dis": x[2 * n : 3 * n],
            "s": x[3 * n : 4 * n],
            "E": x[4 * n : 5 * n],
            "u_plus": x[5 * n : 6 * n],
            "u_minus": x[6 * n : 7 * n],
        },
        record,
        tiebreak,
    )


def _deadline_hit(deadline: float | None, message: str) -> None:
    if deadline is not None and time.perf_counter() > deadline:
        raise BudgetExceeded(message)


def run_chain_42(
    data: ChainInputs, *, time_limit_seconds: float = 60.0, deadline: float | None = None
) -> ChainResult:
    """按 formulation §2.5 执行链 ``4-2``（``M4-2``）：逐日 1 次 LP + 闭式结算。"""
    days = data.days
    shape = (days, PERIODS_PER_DAY)
    plan_b = np.zeros(shape)
    plan_c = np.zeros(shape)
    plan_q_dis = np.zeros(shape)
    plan_s = np.zeros(shape)
    plan_E = np.zeros(shape)
    plan_q_em = np.zeros(shape)
    q_em_settle = np.zeros(shape)
    s_settle = np.zeros(shape)
    records: list[LayerRecord] = []
    tiebreaks: list[TiebreakRecord] = []

    e_prev = E_INIT
    for day in range(days):
        _deadline_hit(deadline, f"墙钟预算耗尽：已完成 {day}/{days} 天（4-2）")
        plan, record, tiebreak = solve_day_plan_42(
            price=data.decision_price[day],
            load_energy=data.load_energy[day],
            pv_act_energy=data.pv_act_energy[day],
            e_start=e_prev,
            time_limit_seconds=time_limit_seconds,
            day=day,
        )
        records.append(record)
        tiebreaks.append(tiebreak)
        if record.status != 0 or not plan:
            raise LayerFailure(
                f"4-2 计划层 LP 未达最优（day={day}, status={record.status}）：{record.message}",
                day=day,
                hour=0,
                status=record.status,
            )
        plan_b[day] = plan["b"]
        plan_c[day] = plan["c"]
        plan_q_dis[day] = plan["q_dis"]
        plan_s[day] = plan["s"]
        plan_E[day] = plan["E"]
        plan_q_em[day] = plan["q_em"]
        residual = plan["b"] + plan["q_dis"] + data.pv_act_energy[day] - data.load_energy[day] - plan["c"]
        s_settle[day] = np.maximum(residual, 0.0)
        q_em_settle[day] = np.maximum(-residual, 0.0)
        e_prev = float(plan["E"][-1])

    return ChainResult(
        chain="4-2",
        days=days,
        price_act=data.price_act,
        price_fc=data.decision_price,
        decision_price=data.decision_price,
        load_energy=data.load_energy,
        pv_act_energy=data.pv_act_energy,
        plan_b=plan_b,
        q=plan_b.copy(),
        c=plan_c.copy(),
        q_dis=plan_q_dis.copy(),
        E=plan_E.copy(),
        q_em=q_em_settle,
        s_settle=s_settle,
        plan_c=plan_c,
        plan_q_dis=plan_q_dis,
        plan_s=plan_s,
        plan_E=plan_E,
        plan_q_em=plan_q_em,
        layer_records=records,
        tiebreak_records=tiebreaks,
        layer_pv_energy={0: data.pv_act_energy},
    )


def run_chain_43(
    data: ChainInputs, *, time_limit_seconds: float = 60.0, deadline: float | None = None
) -> ChainResult:
    """按 formulation §3.6 执行链 ``4-3``（``M4-3``）：逐日 4 次 LP + 闭式结算。"""
    from prob04_predict import belief_price, kappa_schedule, layer_price

    days = data.days
    shape = (days, PERIODS_PER_DAY)
    plan_b = np.zeros(shape)
    plan_c = np.zeros(shape)
    plan_q_dis = np.zeros(shape)
    plan_s = np.zeros(shape)
    plan_E = np.zeros(shape)
    q = np.zeros(shape)
    c = np.zeros(shape)
    q_dis = np.zeros(shape)
    state = np.zeros(shape)
    q_em_settle = np.zeros(shape)
    s_settle = np.zeros(shape)
    price_fc = np.zeros(shape)
    records: list[LayerRecord] = []
    tiebreaks: list[TiebreakRecord] = []
    kappa_records: list[dict[str, Any]] = []
    fallback_records: list[dict[str, Any]] = []

    pv0 = data.forecast_energy(0)
    e_prev = E_INIT
    for day in range(days):
        _deadline_hit(deadline, f"墙钟预算耗尽：已完成 {day}/{days} 天（4-3）")
        schedule = kappa_schedule(data.price_act, day)
        kappas = {int(key): float(value) for key, value in schedule["kappa"].items()}
        kappa_records.extend(schedule["records"])
        price_fc[day] = belief_price(data.price_act, day, kappas)
        if day == 0:
            fallback_records.append(
                {
                    "day_index": 0,
                    "date": "2025-01-01",
                    "marker": "fallback_constant_price",
                    "scope": "plan_layer_and_adjustment_unrealized_part",
                    "value": 1.0,
                    "reason": (
                        "H_d = 空集（无前一日），(PF-HIST) 扩张窗均值无定义；取常量中性价 1.0："
                        "平坦价 ⇒ 无套利激励 ⇒ 储能保持 6000 kWh，是最少信息的合法选择；"
                        "不使用当日未实现实际价、不使用未来价格、不使用全量均值"
                    ),
                }
            )
        plan, record, tiebreak = solve_plan_layer_43(
            price=data.decision_price[day],
            load_energy=data.load_energy[day],
            pv_fc_energy=pv0[day],
            e_start=e_prev,
            time_limit_seconds=time_limit_seconds,
            day=day,
        )
        records.append(record)
        tiebreaks.append(tiebreak)
        if record.status != 0 or not plan:
            raise LayerFailure(
                f"4-3 计划层 LP 未达最优（day={day}, status={record.status}）：{record.message}",
                day=day,
                hour=0,
                status=record.status,
            )
        plan_b[day] = plan["b"]
        plan_c[day] = plan["c"]
        plan_q_dis[day] = plan["q_dis"]
        plan_s[day] = plan["s"]
        plan_E[day] = plan["E"]
        q[day, 0:COMMIT_BLOCK] = plan["b"][0:COMMIT_BLOCK]
        c[day, 0:COMMIT_BLOCK] = plan["c"][0:COMMIT_BLOCK]
        q_dis[day, 0:COMMIT_BLOCK] = plan["q_dis"][0:COMMIT_BLOCK]
        state[day, 0:COMMIT_BLOCK] = plan["E"][0:COMMIT_BLOCK]

        for hour in (6, 12, 18):
            _deadline_hit(deadline, f"墙钟预算耗尽：day={day}, hour={hour}（4-3）")
            layer_price_vector = layer_price(data.price_act, day, hour, float(kappas[hour]))
            pv_m = data.forecast_energy(hour)[day]
            layer, record, tiebreak = solve_adjustment_layer_43(
                hour=hour,
                price=layer_price_vector,
                load_energy=data.load_energy[day],
                pv_fc_energy=pv_m,
                plan_b=plan_b[day],
                e_start=float(state[day, 6 * hour - 1]),
                time_limit_seconds=time_limit_seconds,
                day=day,
            )
            records.append(record)
            tiebreaks.append(tiebreak)
            if record.status != 0 or not layer:
                raise LayerFailure(
                    f"4-3 调整层 LP 未达最优（day={day}, hour={hour}, status={record.status}）：{record.message}",
                    day=day,
                    hour=hour,
                    status=record.status,
                )
            commit = slice(6 * hour, 6 * hour + COMMIT_BLOCK)
            q[day, commit] = layer["q"][0:COMMIT_BLOCK]
            c[day, commit] = layer["c"][0:COMMIT_BLOCK]
            q_dis[day, commit] = layer["q_dis"][0:COMMIT_BLOCK]
            state[day, commit] = layer["E"][0:COMMIT_BLOCK]

        residual = q[day] + q_dis[day] + data.pv_act_energy[day] - data.load_energy[day] - c[day]
        s_settle[day] = np.maximum(residual, 0.0)
        q_em_settle[day] = np.maximum(-residual, 0.0)
        e_prev = float(state[day, -1])

    return ChainResult(
        chain="4-3",
        days=days,
        price_act=data.price_act,
        price_fc=price_fc,
        decision_price=data.decision_price,
        load_energy=data.load_energy,
        pv_act_energy=data.pv_act_energy,
        plan_b=plan_b,
        q=q,
        c=c,
        q_dis=q_dis,
        E=state,
        q_em=q_em_settle,
        s_settle=s_settle,
        plan_c=plan_c,
        plan_q_dis=plan_q_dis,
        plan_s=plan_s,
        plan_E=plan_E,
        plan_q_em=np.zeros(shape),
        layer_records=records,
        tiebreak_records=tiebreaks,
        kappa_records=kappa_records,
        fallback_records=fallback_records,
        layer_pv_energy={hour: data.forecast_energy(hour) for hour in DECISION_HOURS},
    )


def solve_a2_pre(
    data: ChainInputs, *, time_limit_seconds: float = 60.0
) -> tuple[ChainResult, list[LayerRecord], list[TiebreakRecord]]:
    """``A2-PRE``（formulation §4.2 / 决策点 D8-A）：价格完全预知 + 附件 2 实际光伏的单一长时域 LP。

    仅用于 ``4-2`` 的**成本下界锚点**与 ``ablation`` 对照（``C^{act}(4-2) ≥ C^{pre}``，§5-L6）；
    **不进入主结果**。变量序：``b | c | q_dis | s | E``（``5 × days × 144``），无 ``q_em``、无调整层。
    """
    days = data.days
    n = days * PERIODS_PER_DAY
    size = 5 * n
    price_flat = data.price_act.reshape(-1)
    load_flat = data.load_energy.reshape(-1)
    pv_flat = data.pv_act_energy.reshape(-1)
    objective = np.zeros(size)
    objective[0:n] = price_flat

    spill_upper = np.maximum(0.0, pv_flat - load_flat)
    bounds = np.empty((size, 2), dtype=float)
    bounds[0:n, 0] = 0.0
    bounds[0:n, 1] = np.inf
    bounds[n : 2 * n, 0] = 0.0
    bounds[n : 2 * n, 1] = C_CAP
    bounds[2 * n : 3 * n, 0] = 0.0
    bounds[2 * n : 3 * n, 1] = Q_CAP
    bounds[3 * n : 4 * n, 0] = 0.0
    bounds[3 * n : 4 * n, 1] = spill_upper
    bounds[4 * n : 5 * n, 0] = E_MIN
    bounds[4 * n : 5 * n, 1] = E_MAX

    a_eq, b_eq = _balance_and_state_rows(
        n,
        size=size,
        pv_energy=pv_flat,
        load_energy=load_flat,
        e_start=E_INIT,
        balance_offsets=(0, n, 2 * n, 3 * n),
        energy_offset=4 * n,
    )
    throughput = throughput_coefficients(size, n, 2 * n, n)
    result, record, tiebreak = _solve_with_tiebreak(
        primary_objective=objective,
        throughput_objective=throughput,
        scale=throughput_scale(n),
        a_eq=a_eq,
        b_eq=b_eq,
        a_ub=None,
        b_ub=None,
        bounds=bounds,
        layer="a2_pre",
        day=-1,
        hour=-1,
        boundary_index=size - 1,
        time_limit_seconds=time_limit_seconds,
    )
    if result.x is None:
        raise LayerFailure(
            f"A2-PRE 长时域 LP 未达最优（status={record.status}）：{record.message}",
            day=-1,
            hour=-1,
            status=record.status,
        )
    x = np.asarray(result.x, dtype=float)
    b = x[0:n].reshape(days, PERIODS_PER_DAY)
    c = x[n : 2 * n].reshape(days, PERIODS_PER_DAY)
    q_dis = x[2 * n : 3 * n].reshape(days, PERIODS_PER_DAY)
    s = x[3 * n : 4 * n].reshape(days, PERIODS_PER_DAY)
    state = x[4 * n : 5 * n].reshape(days, PERIODS_PER_DAY)
    residual = b + q_dis + data.pv_act_energy - data.load_energy - c
    chain = ChainResult(
        chain="4-2",
        days=days,
        price_act=data.price_act,
        price_fc=data.decision_price,
        decision_price=data.decision_price,
        load_energy=data.load_energy,
        pv_act_energy=data.pv_act_energy,
        plan_b=b,
        q=b.copy(),
        c=c,
        q_dis=q_dis,
        E=state,
        q_em=np.maximum(-residual, 0.0),
        s_settle=np.maximum(residual, 0.0),
        plan_c=c,
        plan_q_dis=q_dis,
        plan_s=s,
        plan_E=state,
        plan_q_em=np.zeros_like(b),
        layer_records=[record],
        tiebreak_records=[tiebreak],
        layer_pv_energy={0: data.pv_act_energy},
    )
    return chain, [record], [tiebreak]


def state_starts(result: ChainResult) -> np.ndarray:
    """每日 0:00 储电量（``E_{d,0}``；``E_{1/1,0} = E_INIT``）。"""
    out = np.empty(result.days)
    out[0] = E_INIT
    if result.days > 1:
        out[1:] = result.E[:-1, -1]
    return out


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


def emergency_intervals(q_em_day: np.ndarray, *, tol: float = TOL) -> list[dict[str, Any]]:
    """逐日紧急购电区间（连续 ``q_em > 0`` 时段合并 + 左端点标签 ``[τ_i, τ_j+10min)``）。"""
    from prob04_io import interval_label

    mask = np.asarray(q_em_day, dtype=float) > tol
    out: list[dict[str, Any]] = []
    for start, stop in merge_interval_labels(mask):
        out.append(
            {
                "slot": interval_label(start, stop),
                "start_period": int(start + 1),
                "stop_period": int(stop),
                "energy_kwh": round(float(np.sum(q_em_day[start:stop])), 6),
            }
        )
    return out


def _round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def cost_breakdown(result: ChainResult, *, use_actual_price: bool) -> dict[str, np.ndarray]:
    """按「实际价」或「决策层信念价」逐日计算 ``C_plan``/``C_adj``/``C_em``（同一组决策量，只换价格）。"""
    price = result.price_act if use_actual_price else result.price_fc
    b = result.plan_b
    q = result.q
    plan = np.sum(price * b, axis=1)
    if result.chain == "4-3":
        deviation_plus = np.maximum(b - q, 0.0)
        deviation_minus = np.maximum(q - b, 0.0)
        adjustment = np.sum(price * (BETA_DEF * deviation_plus + BETA_OVER * deviation_minus), axis=1)
    else:
        adjustment = np.zeros(result.days)
    emergency = np.sum(ALPHA_EM * price * result.q_em, axis=1)
    return {
        "plan": plan,
        "adjustment": adjustment,
        "emergency": emergency,
        "total": plan + adjustment + emergency,
    }


def _layer_pv_and_cap(result: ChainResult) -> tuple[np.ndarray, np.ndarray]:
    """提交链的「支配层光伏电量」与「弃光物理上界」矩阵（逐时段）。

    ``4-2``：只有一个决策层（全天 144 时段均由 0:00 计划支配），PV 用附件 2 实际；
    ``4-3``：``ν(i)`` 支配 ``Π_{ν(i)}[PV]·Δt``（计划层 ``Π_0``；调整层 ``Π_6/Π_12/Π_18``）。
    """
    days = result.days
    nu = dominance_map() if result.chain == "4-3" else np.zeros(PERIODS_PER_DAY, dtype=int)
    layer_pv = np.full((days, PERIODS_PER_DAY), np.nan)
    for hour, matrix in result.layer_pv_energy.items():
        cols = np.where(nu == hour)[0]
        layer_pv[:, cols] = matrix[:, cols]
    if np.any(~np.isfinite(layer_pv)):
        raise ValueError("提交链的支配层光伏在存在 NaN：降尺度覆盖域异常")
    cap = np.maximum(0.0, layer_pv - result.load_energy)
    return layer_pv, cap


def evaluate(result: ChainResult, *, probe_mode: bool, full_horizon: bool = True) -> dict[str, Any]:
    """计算指标、结构恒等式 ``(I2-*)``/``(I3-*)``（逐日 + 交付期切片 + 全期）与全部硬约束检查。

    ``probe_mode=True`` 时**跳过**四项「解析界/量级带」硬检查（探针不构成交付证据），
    但仍在 stdout 打印诊断值；其余结构恒等式与边界检查一律执行。
    """
    chain = result.chain
    days = result.days
    b = result.plan_b
    q = result.q
    c = result.c
    q_dis = result.q_dis
    q_em = result.q_em
    s_settle = result.s_settle
    price = result.price_act
    load = result.load_energy
    pv_act = result.pv_act_energy
    starts = state_starts(result)
    ends = result.E[:, -1]

    act = cost_breakdown(result, use_actual_price=True)
    fc = cost_breakdown(result, use_actual_price=False)
    cost_plan_d, cost_adj_d = act["plan"], act["adjustment"]
    cost_em_d, cost_total_d = act["emergency"], act["total"]

    checks: list[dict[str, Any]] = []

    def record(name: str, value: float, threshold: float, passed: bool, note: str = "") -> None:
        checks.append(
            {"name": name, "value": float(value), "threshold": float(threshold), "passed": bool(passed), "note": note}
        )

    # ---- 逐日恒等式（两链同式；4-2 中 q := b） ----
    net_day = np.sum(load - pv_act, axis=1)
    i1_day = np.sum(q_dis, axis=1) - (ETA_ROUND_TRIP * np.sum(c, axis=1) - ETA_DIS * (ends - starts))
    i2_day = np.sum(q, axis=1) - (
        net_day
        + np.sum(s_settle, axis=1)
        + (1.0 - ETA_ROUND_TRIP) * np.sum(c, axis=1)
        + ETA_DIS * (ends - starts)
        - np.sum(q_em, axis=1)
    )
    transition = np.abs(
        np.diff(np.concatenate([starts[:, None], result.E], axis=1), axis=1)
        - ETA_CH * c
        + q_dis / ETA_DIS
    )
    settlement = np.abs(q + q_em + pv_act + q_dis - load - c - s_settle)
    continuity = np.abs(starts[1:] - ends[:-1]) if days > 1 else np.zeros(0)

    # ---- 层内余额（提交链 vs 支配层预报，§5-L3/L4）：s^{[ν(i)]} = q + Π Δt + q_dis − LΔt − c ----
    layer_pv, spill_cap = _layer_pv_and_cap(result)
    layer_spill = q + layer_pv + q_dis - load - c
    spill_upper_violation = float(np.max(layer_spill - spill_cap))
    spill_lower_violation = float(np.max(-layer_spill))

    if result.layer_records:
        eq_max = max(item.equality_residual_max for item in result.layer_records)
        eq_rel_max = max(item.equality_residual_relative_max for item in result.layer_records)
        ineq_max = max(item.inequality_residual_max for item in result.layer_records)
        ineq_rel_max = max(item.inequality_residual_relative_max for item in result.layer_records)
        bound_max = max(item.bound_violation_max for item in result.layer_records)
        worst_layer = max(item.status for item in result.layer_records)
    else:
        eq_max = eq_rel_max = ineq_max = ineq_rel_max = bound_max = 0.0
        worst_layer = 0

    charge_power = np.maximum.reduce(
        [c / DELTA_T, ETA_CH * c / DELTA_T, q_dis / DELTA_T, q_dis / (ETA_DIS * DELTA_T)]
    )
    same_period = int(np.sum((c > TOL) & (q_dis > TOL)))
    q_em_with_charge = int(np.sum((q_em > TOL) & (c > TOL)))

    record("layer_status_max", float(worst_layer), 0.0, worst_layer == 0, "所有层 HiGHS status = 0 (Optimal)")
    record("layer_equality_residual_max", eq_max, LAYER_TOL, eq_max <= LAYER_TOL,
           "各层等式残差（求解器内部绝对；『等式残差 ≤1e-6』，HiGHS 可行性容差 1e-7）")
    record("layer_equality_residual_relative_max", eq_rel_max, LAYER_TOL_RELATIVE, eq_rel_max <= LAYER_TOL_RELATIVE,
           "各层等式残差（尺度感知相对：‖A_eq x−b_eq‖∞/(‖A_eq‖∞‖x‖∞+‖b_eq‖∞)）")
    record("layer_inequality_residual_max", ineq_max, LAYER_TOL, ineq_max <= LAYER_TOL,
           "各层不等式残差（求解器内部绝对）")
    record("layer_inequality_residual_relative_max", ineq_rel_max, LAYER_TOL_RELATIVE,
           ineq_rel_max <= LAYER_TOL_RELATIVE, "各层不等式残差（尺度感知相对）")
    record("layer_bound_violation_max", bound_max, TOL, bound_max <= TOL, "各层变量界越界量")
    record("cross_day_continuity", float(np.max(continuity)) if continuity.size else 0.0, TOL,
           (not continuity.size) or float(np.max(continuity)) <= TOL, "|E_{d,0} − E_{d−1,144}|（跨日状态闭合）")
    record("state_transition_residual", float(np.max(transition)), TOL, float(np.max(transition)) <= TOL,
           "|E_i − E_{i−1} − 0.9c_i + q_dis_i/0.9|（状态转移闭合）")
    record("settlement_balance_residual", float(np.max(settlement)), TOL, float(np.max(settlement)) <= TOL,
           "结算层等式平衡 |q + q_em + PV^act·Δt + q_dis − L·Δt − c − s'| ≤ 1e-6")
    record("layer_spill_upper_violation", spill_upper_violation, BALANCE_TOL, spill_upper_violation <= BALANCE_TOL,
           "提交链层内弃光 s^{[ν(i)]} ≤ max(0, Π_{ν(i)}·Δt − L·Δt)（层内余额上界）")
    record("layer_spill_lower_violation", spill_lower_violation, BALANCE_TOL, spill_lower_violation <= BALANCE_TOL,
           "提交链层内弃光 s^{[ν(i)]} ≥ 0（层内余额下界）")
    record("storage_upper_violation", max(float(np.max(result.E)) - E_MAX, 0.0), TOL,
           float(np.max(result.E)) <= E_MAX + TOL, "E ≤ 10800")
    record("storage_lower_violation", max(E_MIN - float(np.min(result.E)), 0.0), TOL,
           float(np.min(result.E)) >= E_MIN - TOL, "E ≥ 1200")
    record("storage_initial_exact", abs(starts[0] - E_INIT), TOL, abs(starts[0] - E_INIT) <= TOL,
           "E_{1/1,0} = 6000")
    record("charge_cap_violation", max(float(np.max(c)) - C_CAP, 0.0), TOL, float(np.max(c)) <= C_CAP + TOL,
           "c ≤ 833.3333（并网点侧紧）")
    record("discharge_cap_violation", max(float(np.max(q_dis)) - Q_CAP, 0.0), TOL,
           float(np.max(q_dis)) <= Q_CAP + TOL, "q_dis ≤ 750.0000（电池侧紧）")
    record("settle_spill_bound_violation", max(float(np.max(s_settle - pv_act)), 0.0), TOL,
           bool(np.all(s_settle <= pv_act + TOL)), "0 ≤ s' ≤ PV^act·Δt")
    record("plan_nonneg_violation", max(-float(np.min(b)), 0.0), TOL, float(np.min(b)) >= -TOL, "b ≥ 0")
    record("purchase_nonneg_violation", max(-float(np.min(q)), 0.0), TOL, float(np.min(q)) >= -TOL, "q ≥ 0")
    record("q_em_nonneg_violation", max(-float(np.min(q_em)), 0.0), TOL, float(np.min(q_em)) >= -TOL, "q_em ≥ 0")
    record("max_side_power_kw", float(np.max(charge_power)), P_MAX, float(np.max(charge_power)) <= P_MAX + 1e-3,
           "并网点侧与电池侧换算功率（四路）均 ≤ 5000 kW")
    record("identity_I1_residual", float(np.max(np.abs(i1_day))), TOL, float(np.max(np.abs(i1_day))) <= TOL,
           "Σq_dis = η²Σc − η(E_T − E_0)（逐日最大残差）")
    record("identity_I2_residual", float(np.max(np.abs(i2_day))), TOL, float(np.max(np.abs(i2_day))) <= TOL,
           "Σq = N + Σs' + 0.19Σc + ηΔE − Σq_em（逐日最大残差）")

    if chain == "4-3":
        record("q_eq_b_first_block", float(np.max(np.abs(q[:, 0:COMMIT_BLOCK] - b[:, 0:COMMIT_BLOCK]))), TOL,
               float(np.max(np.abs(q[:, 0:COMMIT_BLOCK] - b[:, 0:COMMIT_BLOCK]))) <= TOL,
               "i ≤ 36 时 q = b（计划层提交口径 AD-1）")
        covered = np.zeros((days, PERIODS_PER_DAY), dtype=int)
        for hour in (6, 12, 18):
            covered[:, 6 * hour : 6 * hour + COMMIT_BLOCK] += 1
        covered[:, 0:COMMIT_BLOCK] += 1
        record("commit_partition_exact", float(int(np.sum(covered != 1))), 0.0, bool(np.all(covered == 1)),
               "提交时段划分 D_0 ∪ D_6 ∪ D_12 ∪ D_18 恰为 144 个时段且互不重叠 ⇒ i ≤ 6m 只被写入一次、"
               "不回溯（AS18/(AD-1)）由提交链构造保证")
    else:
        record("chain42_q_em_expected_zero", float(np.max(result.plan_q_em)), TOL,
               float(np.max(result.plan_q_em)) <= TOL,
               "4-2 计划层 q_em ≡ 0（§2.3 定理：α_em = 5 > 1，任一最优解把 q_em 换成 b 严格改进）")
        record("chain42_settle_q_em_expected_zero", float(np.max(q_em)), TOL, float(np.max(q_em)) <= TOL,
               "4-2 结算层 q_em = max(0, −r) ≡ 0（计划层等式平衡精确闭合 ⇒ r = s ≥ 0）")

    total_act = float(np.sum(cost_total_d))
    plan_act = float(np.sum(cost_plan_d))
    adj_act = float(np.sum(cost_adj_d))
    em_act = float(np.sum(cost_em_d))
    record("cost_decomposition_identity", total_act - (plan_act + adj_act + em_act), 1e-6,
           abs(total_act - (plan_act + adj_act + em_act)) <= 1e-6,
           "C_total^act = C_plan^act + C_adj^act + C_em^act（4-2 的 C_adj 恒 0）")
    fc_total = float(np.sum(fc["total"]))
    fc_plan = float(np.sum(fc["plan"]))
    fc_adj = float(np.sum(fc["adjustment"]))
    fc_em = float(np.sum(fc["emergency"]))
    record("cost_decomposition_identity_fc", fc_total - (fc_plan + fc_adj + fc_em), 1e-6,
           abs(fc_total - (fc_plan + fc_adj + fc_em)) <= 1e-6,
           "C_total^fc = C_plan^fc + C_adj^fc + C_em^fc（决策层信念价口径，同一组决策量）")
    delta_price = price - result.price_fc
    delta_plan = float(np.sum(delta_price * b))
    delta_em = float(np.sum(ALPHA_EM * delta_price * q_em))
    delta_adj = (
        float(np.sum(delta_price * (BETA_DEF * np.maximum(b - q, 0.0) + BETA_OVER * np.maximum(q - b, 0.0))))
        if chain == "4-3" else 0.0
    )
    record("delta_c_price_identity", (total_act - fc_total) - (delta_plan + delta_adj + delta_em), 1e-6,
           abs((total_act - fc_total) - (delta_plan + delta_adj + delta_em)) <= 1e-6,
           "ΔC_price = ΔC_plan + ΔC_adj + ΔC_em，其中 ΔC_· = Σ(p^act − \\hat p^{fc})·对应量（同一组决策量）")

    # ---- AS21 逐层不变性与退化审计 ----
    t7 = result.tiebreak_records
    if t7:
        t7_rel_max = _finite_or(max(item.primary_relative_change for item in t7))
        t7_all_passed = bool(all(item.invariance_passed for item in t7))
        t7_shrinks = int(sum(item.shrinks for item in t7))
        t7_degenerate_layers = int(sum(1 for item in t7 if item.degeneracy_degree > 0))
        t7_remaining = int(sum(1 for item in t7 if item.throughput_unique is False))
        t7_unknown = int(sum(1 for item in t7 if item.throughput_unique is None))
        t7_throughput = _finite_or(float(np.sum([item.throughput_kwh for item in t7])))
        t7_throughput_before = _finite_or(float(np.sum([item.throughput_before_kwh for item in t7])))
        t7_state_change = _finite_or(float(np.max([item.baseline_state_change_max_kwh for item in t7])))
        t7_eps_min = _finite_or(float(np.min([item.epsilon for item in t7])))
        t7_eps_max = _finite_or(float(np.max([item.epsilon for item in t7])))
        t7_max_degeneracy = int(max(item.degeneracy_degree for item in t7))
        t7_weighted_rel_max = _finite_or(max(item.weighted_primary_relative_change for item in t7))
        t7_weighted_effective = int(sum(1 for item in t7 if item.weighted_sum_effective))
        t7_lexicographic = int(sum(1 for item in t7 if item.committed_solution == "lexicographic"))
        t7_fallbacks = int(sum(1 for item in t7 if item.committed_solution != "lexicographic"))
    else:
        t7_rel_max, t7_all_passed, t7_shrinks = 0.0, True, 0
        t7_degenerate_layers = t7_remaining = t7_unknown = 0
        t7_throughput = t7_throughput_before = t7_state_change = 0.0
        t7_eps_min = t7_eps_max = 0.0
        t7_max_degeneracy = t7_weighted_effective = t7_lexicographic = t7_fallbacks = 0
        t7_weighted_rel_max = 0.0
    record("t7_primary_invariance_max_relative_change", t7_rel_max, T7_INVARIANCE_TOL, t7_rel_max <= T7_INVARIANCE_TOL,
           "AS21/T7-2：加入次目标前后主目标相对变化（逐层最大值，须 ≤ 1e-9）")
    record("t7_invariance_all_layers_passed", float(int(not t7_all_passed)), 0.0, t7_all_passed,
           "AS21/T7-2：全部逐层记录 invariance_passed=true")
    record("t7_epsilon_below_primary_scale", t7_eps_max, 1.0, t7_eps_max < 1.0,
           "AS21/T7-1：ε 为无量纲相对权重（ε ≪ 1）；次目标总量 ≤ 1e-6·主目标尺度")

    # ---- 交付期切片 ----
    delivery = np.zeros(days, dtype=bool)
    delivery_start = min(D_REQ_START, days)
    delivery[delivery_start:] = True
    if delivery.any():
        d_start_state = float(starts[delivery_start])
        d_end_state = float(ends[-1])
        net_d = float(np.sum((load - pv_act)[delivery]))
        i1_delivery = float(
            np.sum(q_dis[delivery]) - (ETA_ROUND_TRIP * np.sum(c[delivery]) - ETA_DIS * (d_end_state - d_start_state))
        )
        i2_delivery = float(
            np.sum(q[delivery])
            - (
                net_d
                + float(np.sum(s_settle[delivery]))
                + (1.0 - ETA_ROUND_TRIP) * float(np.sum(c[delivery]))
                + ETA_DIS * (d_end_state - d_start_state)
                - float(np.sum(q_em[delivery]))
            )
        )
        record("identity_I1_delivery_residual", i1_delivery, TOL, abs(i1_delivery) <= TOL, "交付期切片 (I1)/(I3-1)")
        record("identity_I2_delivery_residual", i2_delivery, TOL, abs(i2_delivery) <= TOL,
               "交付期切片 (I2)/(I3-8)：Σq = N_req + Σs' + 0.19Σc + η(E_T − E_{2/1,0}) − Σq^em")
    else:
        net_d = i1_delivery = i2_delivery = 0.0
        d_start_state = d_end_state = 0.0

    # ---- 解析界与量级带（正式模式硬检查；探针模式只打印诊断，但**仍然计算**这些参考值） ----
    bounds: dict[str, Any] = {}
    if delivery.any():
        p_min = float(np.min(price))
        lower = p_min * float(np.sum(b[delivery]))
        policy_b = np.maximum(load - pv_act, 0.0)
        policy_q = np.empty_like(q)
        if chain == "4-3":
            nu = dominance_map()
            for hour, matrix in result.layer_pv_energy.items():
                cols = np.where(nu == hour)[0]
                policy_q[:, cols] = np.maximum(load[:, cols] - matrix[:, cols], 0.0)
        else:
            policy_q = policy_b.copy()
        policy_plus = np.maximum(policy_b - policy_q, 0.0)
        policy_minus = np.maximum(policy_q - policy_b, 0.0)
        policy_em = np.maximum(load - policy_q - pv_act, 0.0)
        policy_plan = float(np.sum(price[delivery] * policy_b[delivery]))
        policy_adj = float(
            np.sum(price[delivery] * (BETA_DEF * policy_plus[delivery] + BETA_OVER * policy_minus[delivery]))
        ) if chain == "4-3" else 0.0
        policy_emc = float(np.sum(ALPHA_EM * price[delivery] * policy_em[delivery]))
        upper = policy_plan + policy_adj + policy_emc
        total_act_delivery = float(np.sum(cost_total_d[delivery]))
        mean_daily = total_act_delivery / max(int(delivery.sum()), 1)
        bounds = {
            "delivery_plan_lower_bound_yuan": _round(lower),
            "delivery_plan_lower_bound_formula": "p^act_min · Σ_{D_req} b（C_total^act ≥ C_plan^act ≥ p_min·Σb）",
            "delivery_constructed_upper_bound_yuan": _round(upper),
            "delivery_upper_bound_parts_yuan": {
                "plan": _round(policy_plan),
                "adjustment": _round(policy_adj),
                "emergency": _round(policy_emc),
            },
            "delivery_upper_bound_formula": (
                "无储能可行策略（c = q_dis = 0、各层 q/b 取该层预报净负荷、s 取该层物理盈余）："
                "Σp^act·b_policy + Σ[0.5p^act(b−q)^+ + 1.5p^act(q−b)^+] + Σ5p^act·q^em_policy"
                "（4-2 无 C_adj 项）"
            ),
            "mean_daily_delivery_cost_yuan": _round(mean_daily),
            "magnitude_band_delivery_yuan": list(DELIVERY_MAGNITUDE_BAND_YUAN),
            "magnitude_band_daily_yuan": list(DAILY_MAGNITUDE_BAND_YUAN),
            "magnitude_band_delivery_ok": bool(
                DELIVERY_MAGNITUDE_BAND_YUAN[0] <= total_act_delivery <= DELIVERY_MAGNITUDE_BAND_YUAN[1]
            ),
            "magnitude_band_daily_ok": bool(
                DAILY_MAGNITUDE_BAND_YUAN[0] <= mean_daily <= DAILY_MAGNITUDE_BAND_YUAN[1]
            ),
            "delivery_cost_total_act_yuan": _round(total_act_delivery),
            "hard_checks_applied": bool(full_horizon and not probe_mode),
        }
        if not probe_mode:
            record("analytic_lower_bound", total_act_delivery, lower, total_act_delivery >= lower - 1e-6,
                   "交付期 C_total^act ≥ p^act_min·Σb（构造性下界）")
            record("analytic_upper_bound", total_act_delivery, upper, total_act_delivery <= upper + 1e-6,
                   "交付期 C_total^act ≤ 无储能可行策略的构造上界")
            record("magnitude_delivery_band", total_act_delivery, DELIVERY_MAGNITUDE_BAND_YUAN[1],
                   DELIVERY_MAGNITUDE_BAND_YUAN[0] <= total_act_delivery <= DELIVERY_MAGNITUDE_BAND_YUAN[1],
                   "交付期费用须落在 [3e6, 5e7] 元（10^7 量级），防 Δt 误乘")
            record("magnitude_daily_band", mean_daily, DAILY_MAGNITUDE_BAND_YUAN[1],
                   DAILY_MAGNITUDE_BAND_YUAN[0] <= mean_daily <= DAILY_MAGNITUDE_BAND_YUAN[1],
                   "日均费用须落在 [5e3, 2e5] 元；落入 10^3 元即 Δt 硬错误")

    # ---- 统计量（不作硬失败） ----
    clip_events = [item for item in result.kappa_records if item.get("clipped")]
    statistics = {
        "simultaneous_charge_discharge_periods": same_period,
        "periods_with_q_em_and_charge": q_em_with_charge,
        "periods_with_spill": int(np.sum(s_settle > TOL)),
        "days_with_emergency": int(np.sum(np.any(q_em > TOL, axis=1))),
        "periods_with_emergency": int(np.sum(q_em > TOL)),
        "max_purchase_kwh": _round(float(np.max(q))),
        "max_purchase_day_kwh": _round(float(np.max(np.sum(q, axis=1)))),
        "kappa_clip_events": len(clip_events),
        "kappa_clip_records": clip_events,
        "kappa0_identity_holds": bool(
            all(item["kappa"] == 1.0 for item in result.kappa_records if int(item["m"]) == 0)
        ),
        "kappa_records": len(result.kappa_records),
        "degenerate_layers": t7_degenerate_layers,
        "layers_with_remaining_multiplicity": t7_remaining,
        "note": (
            "同充放时段数与 q_em>0 且 c>0 时段数属 LP 退化的记录量，不作硬失败；"
            "4-2 的 Σq_em 预期恒 0（§2.3 定理），4-3 的 Σq^em 预期 > 0（预报—实际光伏缺口）。"
        ),
    }

    delivery_slice = delivery if delivery.any() else np.zeros(days, dtype=bool)

    def _sum(array: np.ndarray) -> float:
        return _round(float(np.sum(array[delivery_slice]))) if delivery_slice.any() else 0.0

    belief = {
        "price_basis": (
            "决策层信念价 \\hat p^{fc}_{d,i} = \\hat p^{(ν(i))}_{d,i}"
            "（4-2：\\hat p = PF-PERSIST；4-3：κ_0 ≡ 1 与 κ_6/κ_12/κ_18 分段）"
        ),
        "cost_plan_fc_yuan": _round(fc_plan),
        "cost_adj_fc_yuan": _round(fc_adj),
        "cost_em_fc_yuan": _round(fc_em),
        "cost_total_fc_yuan": _round(fc_total),
        "delta_c_price_yuan": _round(total_act - fc_total),
        "delta_c_plan_yuan": _round(plan_act - fc_plan),
        "delta_c_adj_yuan": _round(adj_act - fc_adj),
        "delta_c_em_yuan": _round(em_act - fc_em),
        "same_decisions": True,
        "note": "同一组已提交决策量，仅替换计价价格（不重解模型）；ΔC_price 的符号按实测（P3），不得预设为正。",
    }

    series = {
        "period_index": list(range(1, days * PERIODS_PER_DAY + 1)),
        "day_index": [int(v) for v in np.repeat(np.arange(days), PERIODS_PER_DAY)],
        "price_actual_yuan_per_kwh": [float(v) for v in price.reshape(-1)],
        "price_belief_yuan_per_kwh": [float(v) for v in result.price_fc.reshape(-1)],
        "load_energy_kwh": [float(v) for v in load.reshape(-1)],
        "pv_actual_energy_kwh": [float(v) for v in pv_act.reshape(-1)],
        "plan_purchase_kwh": [float(v) for v in b.reshape(-1)],
        "final_purchase_kwh": [float(v) for v in q.reshape(-1)],
        "q_em_kwh": [float(v) for v in q_em.reshape(-1)],
        "charge_kwh": [float(v) for v in c.reshape(-1)],
        "discharge_kwh": [float(v) for v in q_dis.reshape(-1)],
        "spill_settlement_kwh": [float(v) for v in s_settle.reshape(-1)],
        "storage_kwh": [float(v) for v in result.E.reshape(-1)],
    }

    return {
        "chain": chain,
        "probe_mode": bool(probe_mode),
        "objective_yuan": _round(total_act),
        "cost_plan_yuan": _round(plan_act),
        "cost_adj_yuan": _round(adj_act),
        "cost_em_yuan": _round(em_act),
        "belief": belief,
        "delivery": {
            "cost_total_yuan": _round(float(np.sum(cost_total_d[delivery_slice]))) if delivery_slice.any() else 0.0,
            "cost_plan_yuan": _round(float(np.sum(cost_plan_d[delivery_slice]))) if delivery_slice.any() else 0.0,
            "cost_adj_yuan": _round(float(np.sum(cost_adj_d[delivery_slice]))) if delivery_slice.any() else 0.0,
            "cost_em_yuan": _round(float(np.sum(cost_em_d[delivery_slice]))) if delivery_slice.any() else 0.0,
            "cost_total_fc_yuan": _round(float(np.sum(fc["total"][delivery_slice]))) if delivery_slice.any() else 0.0,
            "delta_c_price_yuan": (
                _round(float(np.sum((cost_total_d - fc["total"])[delivery_slice]))) if delivery_slice.any() else 0.0
            ),
            "total_plan_kwh": _sum(b),
            "total_purchase_kwh": _sum(q),
            "total_q_em_kwh": _sum(q_em),
            "total_charge_kwh": _sum(c),
            "total_discharge_kwh": _sum(q_dis),
            "total_spill_kwh": _sum(s_settle),
            "net_load_kwh": _round(net_d),
            "storage_start_kwh": _round(d_start_state),
            "storage_final_kwh": _round(d_end_state),
            "days": int(delivery_slice.sum()),
            "first_date_index": int(delivery_start),
            "last_date_index": days - 1,
        },
        "totals": {
            "total_plan_kwh": _round(float(np.sum(b))),
            "total_purchase_kwh": _round(float(np.sum(q))),
            "total_q_em_kwh": _round(float(np.sum(q_em))),
            "total_charge_kwh": _round(float(np.sum(c))),
            "total_discharge_kwh": _round(float(np.sum(q_dis))),
            "total_spill_kwh": _round(float(np.sum(s_settle))),
            "net_load_kwh": _round(float(np.sum(net_day))),
            "max_charge_kwh": _round(float(np.max(c))),
            "max_discharge_kwh": _round(float(np.max(q_dis))),
            "max_plan_purchase_kwh": _round(float(np.max(b))),
            "max_final_purchase_kwh": _round(float(np.max(q))),
            "max_side_power_kw": _round(float(np.max(charge_power))),
            "storage_initial_kwh": _round(E_INIT),
            "storage_final_kwh": _round(float(ends[-1])),
            "storage_range_kwh": [_round(float(np.min(result.E))), _round(float(np.max(result.E)))],
            "days_with_emergency": int(np.sum(np.any(q_em > TOL, axis=1))),
            "periods_with_emergency": int(np.sum(q_em > TOL)),
            "simultaneous_charge_discharge_periods": same_period,
            "periods_with_q_em_and_charge": q_em_with_charge,
        },
        "identities": {
            "I1_daily_max_abs": float(np.max(np.abs(i1_day))),
            "I2_daily_max_abs": float(np.max(np.abs(i2_day))),
            "I1_delivery_residual": float(i1_delivery),
            "I2_delivery_residual": float(i2_delivery),
            "continuity_residual_max": float(np.max(continuity)) if continuity.size else 0.0,
            "transition_residual_max": float(np.max(transition)),
            "settlement_residual_max": float(np.max(settlement)),
            "layer_spill_upper_violation": spill_upper_violation,
            "layer_spill_lower_violation": spill_lower_violation,
        },
        "bounds": bounds,
        "statistics": statistics,
        "t7_tiebreak": {
            "rule": T7_TIEBREAK_RULE,
            "eps_relative": T7_EPS_RELATIVE,
            "invariance_tol": T7_INVARIANCE_TOL,
            "shrink_factor": T7_SHRINK_FACTOR,
            "max_shrinks": T7_MAX_SHRINKS,
            "layers": len(t7),
            "max_primary_relative_change": t7_rel_max,
            "all_layers_invariance_passed": t7_all_passed,
            "total_shrinks": t7_shrinks,
            "epsilon_min": t7_eps_min,
            "epsilon_max": t7_eps_max,
            "weighted_sum_max_primary_relative_change": t7_weighted_rel_max,
            "weighted_sum_effective_layers": t7_weighted_effective,
            "lexicographic_committed_layers": t7_lexicographic,
            "fallback_committed_layers": t7_fallbacks,
            "throughput_primary_only_kwh": t7_throughput_before,
            "throughput_tiebreak_kwh": t7_throughput,
            "throughput_reduced_kwh": t7_throughput_before - t7_throughput,
            "max_baseline_trajectory_change_kwh": t7_state_change,
            "degenerate_layers": t7_degenerate_layers,
            "max_degeneracy_degree": t7_max_degeneracy,
            "layers_with_remaining_multiplicity": t7_remaining,
            "layers_with_unknown_multiplicity": t7_unknown,
            "note": (
                "AS21：提交解为主目标最优面上吞吐量最小的字典序解（T7-1 优先序在 ε→0⁺ 的精确实现），"
                "字面 ε 加权式只作逐层诊断；degeneracy_degree = 活跃约束数 − 变量数。"
            ),
        },
        "daily": {
            "dates_index": list(range(days)),
            "plan_kwh": [_round(v) for v in np.sum(b, axis=1)],
            "purchase_kwh": [_round(v) for v in np.sum(q, axis=1)],
            "q_em_kwh": [_round(v) for v in np.sum(q_em, axis=1)],
            "charge_kwh": [_round(v) for v in np.sum(c, axis=1)],
            "discharge_kwh": [_round(v) for v in np.sum(q_dis, axis=1)],
            "spill_kwh": [_round(v) for v in np.sum(s_settle, axis=1)],
            "cost_plan_yuan": [_round(v) for v in cost_plan_d],
            "cost_adj_yuan": [_round(v) for v in cost_adj_d],
            "cost_em_yuan": [_round(v) for v in cost_em_d],
            "cost_total_yuan": [_round(v) for v in cost_total_d],
            "cost_total_fc_yuan": [_round(v) for v in fc["total"]],
            "delta_c_price_yuan": [_round(v) for v in (cost_total_d - fc["total"])],
            "state_start_kwh": [_round(v) for v in starts],
            "state_end_kwh": [_round(v) for v in ends],
            "I1_residual": [_round(v) for v in i1_day],
            "I2_residual": [_round(v) for v in i2_day],
        },
        "checks": checks,
        "checks_failed": [item["name"] for item in checks if not item["passed"]],
        "series": series,
    }


__all__ = [
    "ALPHA_EM",
    "BALANCE_TOL",
    "BETA_DEF",
    "BETA_OVER",
    "BLOCKS_PER_DAY",
    "BLOCK_ROWS",
    "BudgetExceeded",
    "C_CAP",
    "COMMIT_BLOCK",
    "CROSS_YEAR_DROPPED",
    "ChainInputs",
    "ChainResult",
    "DAILY_MAGNITUDE_BAND_YUAN",
    "DAYS_FULL",
    "DECISION_HOURS",
    "DELIVERY_MAGNITUDE_BAND_YUAN",
    "DELTA_T",
    "D_REQ_START",
    "E_INIT",
    "E_MAX",
    "E_MIN",
    "ETA_CH",
    "ETA_DIS",
    "ETA_ROUND_TRIP",
    "LAYER_TOL",
    "LAYER_TOL_RELATIVE",
    "LayerFailure",
    "LayerRecord",
    "P_MAX",
    "PERIODS_PER_DAY",
    "Q_CAP",
    "SPEC_DATES",
    "TABLE1_SLOTS",
    "TOL",
    "T7_EPS_RELATIVE",
    "T7_INVARIANCE_TOL",
    "T7_MAX_SHRINKS",
    "T7_SHRINK_FACTOR",
    "T7_TIEBREAK_RULE",
    "TiebreakRecord",
    "block_energy_bias",
    "cost_breakdown",
    "cross_year_dropped_count",
    "dominance_map",
    "downscale",
    "emergency_intervals",
    "evaluate",
    "merge_interval_labels",
    "run_chain_42",
    "run_chain_43",
    "solve_a2_pre",
    "solve_adjustment_layer_43",
    "solve_day_plan_42",
    "solve_plan_layer_43",
    "state_starts",
    "throughput_coefficients",
    "throughput_scale",
    "tiebreak_epsilon",
]
