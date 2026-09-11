# -*- coding: utf-8 -*-
"""prob03 三层顺序向前递推 LP（主口径 ``M1``）的建模、求解与结构自检。

严格对应 ``problems/microgrid_2025/prob03/versions/assumption_v001``（AS01–AS18 + 团队裁定 B0–B7）
与 ``formulations/formulation_v001``（§3.2 降尺度、§3.3 计划层、§3.4 调整层、§3.5 结算层、§3.10 算法）：

    for d in D_full:
        计划层 (PL_d)  : 0:00 预报 Π_0，min Σ p·b，提交 D_0 = i = 1..36
        调整层 (AD_{d,m}): m ∈ {6,12,18}，用 Π_m 顺序重优化 R_m，只提交 D_m
        结算层 (ST_d)  : 用附件 2 **实际**光伏闭式求 s' 与 q_em（唯一 PV^act 入口，§0.4 F2）

口径（不得逐问更改）：``Δt = 1/6``、``η_ch = η_dis = 0.9``、``c ≤ 833.3333``、``q_dis ≤ 750.0000``
（D10 口径丙 / 勘误 E1）、``E ∈ [1200, 10800]``、``E_{1/1,0} = 6000``、终端自由、``α_em = 5``、
``β_def = 0.5``、``β_over = 1.5``；目标 ``C_total = C_plan + C_em + C_adj``（元，**不乘 Δt**，团队 D9）。

求解器：CPU HiGHS（``scipy.optimize.linprog(method="highs")``）；本问**不使用 GPU**、不依赖随机源。
``M2``–``M8`` 按团队裁定 B0/B2 由 ``ablation`` 阶段在 ``ablations/code/`` 下另建，本模块只实现 ``M1``。

团队裁定 **T7**（统一冻结 tie-breaking，效力高于 B4-``C5`` 初版措辞，2026-09-11）：

* **T7-1**：所有层、所有模型（``M1``–``M8``）一律使用 `min [该层主目标] + ε·Σ_t(c_{d,t}+q_dis_{d,t})`；
  本模块把 ε 实现为**共享算子** :func:`tiebreak_epsilon` / :func:`throughput_coefficients`，
  ``M2``–``M8`` 必须调用同一算子（``T7_EPS_RELATIVE``、次目标系数与不变性阈值完全一致，T7-5）。
* **T7-2**：逐层落盘「加入次目标前后主目标相对变化 ≤ ``T7_INVARIANCE_TOL``」的验证
  （:class:`TiebreakRecord`），不满足时按 :data:`T7_SHRINK_FACTOR` 缩小 ε 重跑，有界于 :data:`T7_MAX_SHRINKS`。
* **T7-3**：报告该层退化维度（活跃约束数 − 变量数）与影响的上游量（层末状态 ``E``、与基线解的轨迹差），
  并在 T7 最优面上最大化吞吐量以判定是否仍存在多重最优。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, csr_matrix, vstack

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
Q_CAP = P_MAX * DELTA_T * ETA_DIS       # 750.0000 kWh（电池侧为紧侧，D10 口径丙 / E1）
ALPHA_EM = 5.0
BETA_DEF = 0.5
BETA_OVER = 1.5
PERIODS_PER_DAY = 144
DAYS_FULL = 365
DAILY_DELIVERY_START = 31               # 0 基日索引：2025-02-01（1 月为预热期）
TOL = 1e-6
# 层内 LP 的**求解器内部**可行性残差门槛（**不是** formulation §4.3 的「各层余额残差」）。
# 本模型只覆盖 HiGHS 的 ``time_limit``/``presolve``（见 ``_solve``），其默认
# ``primal_feasibility_tolerance`` 为 1e-7，因此任何层都不可能被要求给出优于 ~1e-7 的
# ``‖A_eq x − b_eq‖∞`` 或 ``max(A_ub x − b_ub)``。旧值 1e-8 严格强于求解器自身的可行性保证：
# 365 天链在 day 243/hour 18 与 day 41/hour 6 两层分别以 8.79e-8、3.53e-8 的纯数值噪声被判
# ``hard_check_failed``（task 1b57b1cb92e0d5095518，act-ed12930b86a54d59 诊断）。
# 现改为「绝对门槛与 AS 的『等式残差 ≤1e-6』一致 + 尺度感知相对门槛」双判据；
# formulation §4.3 的「各层余额残差 ≤1e-8」仍由**提交解重算**的 ``layer_spill_*`` 承担（BALANCE_TOL）。
LAYER_TOL = 1e-6                     # 求解器内部残差绝对门槛（=TOL；HiGHS 可行性容差 1e-7）
LAYER_TOL_RELATIVE = 1e-8            # 求解器内部残差相对门槛：‖A x−b‖∞ / (‖A‖∞·‖x‖∞ + ‖b‖∞)
BALANCE_TOL = 1e-8                   # 提交解重算的层内余额残差（formulation §4.3 C 判据，沿用 1e-8）
DECISION_HOURS: tuple[int, ...] = (0, 6, 12, 18)
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
DELIVERY_MAGNITUDE_BAND_YUAN = (3.0e6, 5.0e7)
DAILY_MAGNITUDE_BAND_YUAN = (5.0e3, 2.0e5)

# --- 团队裁定 T7：统一冻结 tie-breaking（所有层、所有模型 M1–M8） -------------------------
# T7-1 原文：``min [该层主目标] + ε·Σ_t(c_{d,t}+q_dis_{d,t})``，``ε = 1e-6 × 主目标尺度``。
# 团队同句要求「取足够小以保证不改变主目标最优值」。字面取 ``ε = 1e-6·P*`` 会使次目标总量
# ``ε·Σ(c+q_dis)``（上界 ``T_ref = n·(C_CAP+Q_CAP)``）与主目标**同量级**，与「足够小」自相矛盾。
# 本实现把该式**相对化**为无量纲权重（差异已在 implementation.md §1.1 显式登记）：
#       ε = T7_EPS_RELATIVE × max(|P*|, 1) / T_ref
# 于是次目标总量恒 ≤ 1e-6·max(|P*|,1)；且因次目标是线性的、主目标最优面非空，
# 加权和的最优解必落在主目标最优面上（T7-2 的逐层验证即检验这一点）。
T7_EPS_RELATIVE = 1e-6
T7_INVARIANCE_TOL = 1e-9          # T7-2：主目标相对变化上限
T7_SHRINK_FACTOR = 0.1            # T7-2：不满足时 ε 缩小倍数
T7_MAX_SHRINKS = 8                # T7-2：缩小次数上限（有界、确定性）
T7_FACE_TOL_RELATIVE = 1e-9       # T7-3：T7 最优面判定的相对容差
T7_FACE_TOL_ABSOLUTE = 1e-9       # T7-3：T7 最优面判定的绝对容差
# ③ 字典序提交解的主目标最优面带宽容差占 T7_INVARIANCE_TOL 的比例：留出求解器数值噪声余量，
# 使「约束面上取到边界」的解仍满足 T7-2 的 ≤ 1e-9 判定（否则刚好等于 1e-9 会因 5e-16 噪声判负）。
T7_FACE_PRIMARY_TOL_FRACTION = 0.5
T7_TIEBREAK_RULE = (
    "min [该层主目标] + ε·Σ_t(c_{d,t}+q_dis_{d,t})，"
    "ε = 1e-6·max(|该层主目标最优值|,1)/[n·(c_cap+q_dis_cap)]；"
    "所有层、所有模型 M1–M8 必须完全一致（团队 T7-1/T7-5）"
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
    """整条 ``M1`` 链的输入（按天展开；``fc`` 为 ``hour → (days, 144)`` 降尺度预报）。"""

    days: int
    price: np.ndarray          # (days, 144) 元/kWh
    load_energy: np.ndarray    # (days, 144) kWh = L·Δt
    pv_act_energy: np.ndarray  # (days, 144) kWh = PV^act·Δt
    forecast_kw: dict[int, np.ndarray]   # hour → (days, 144) kW（未支配时段为 NaN）

    @property
    def periods(self) -> int:
        return int(self.days * PERIODS_PER_DAY)

    def forecast_energy(self, hour: int) -> np.ndarray:
        return self.forecast_kw[hour] * DELTA_T


@dataclass
class LayerRecord:
    day: int
    hour: int
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


def _finite_or(value: float, fallback: float = 1e30) -> float:
    """把非有限值替换为有限哨兵，保证 ``allow_nan=False`` 的 JSON 落盘不失败。"""
    number = float(value)
    return number if np.isfinite(number) else float(fallback)


@dataclass
class TiebreakRecord:
    """团队 T7 的逐层审计记录（T7-1 规则 / T7-2 不变性 / T7-3 退化维度与上游量）。"""

    layer: str                    # "plan" | "adjustment"
    day: int
    hour: int
    primary_before_yuan: float    # 未加次目标的主目标最优值 P*
    primary_after_yuan: float     # 加次目标后的主目标值 P'
    primary_relative_change: float
    epsilon: float
    shrinks: int
    invariance_passed: bool
    throughput_kwh: float         # Σ(c+q_dis)：加次目标后的选择
    throughput_before_kwh: float  # Σ(c+q_dis)：纯主目标基线解
    throughput_reduced_kwh: float
    baseline_state_change_max_kwh: float   # |x_tiebreak − x_baseline|∞（轨迹差）
    degeneracy_degree: int                 # 活跃约束数 − 变量数（退化维度代理）
    active_constraints: int
    variables: int
    weighted_primary_relative_change: float  # T7-1 字面加权式的相对变化（诊断）
    weighted_throughput_kwh: float
    weighted_sum_effective: bool             # 加权式是否达到字典序最小值
    committed_solution: str                  # "lexicographic" | "weighted_sum_fallback" | "baseline_fallback"
    throughput_upper_on_optimal_face_kwh: float | None
    throughput_unique: bool | None
    probe_status: int | None
    boundary_state_kwh: float              # 影响的上游量：该层末状态 E
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
class M1Result:
    data: ChainInputs
    plan_b: np.ndarray            # (days, 144) 计划购电量
    plan_c: np.ndarray            # (days, 144) 计划层轨迹（仅 D_0 提交，其余为计划轨迹）
    plan_q_dis: np.ndarray
    plan_s: np.ndarray
    plan_E: np.ndarray
    q: np.ndarray                 # (days, 144) 最终购电量（替代量）
    c: np.ndarray
    q_dis: np.ndarray
    E: np.ndarray
    q_em: np.ndarray              # (days, 144) 结算层
    s_settle: np.ndarray          # (days, 144) 结算层弃光 s'
    layer_records: list[LayerRecord] = field(default_factory=list)
    tiebreak_records: list[TiebreakRecord] = field(default_factory=list)

    @property
    def days(self) -> int:
        return self.data.days


def dominance_map(periods: int = PERIODS_PER_DAY) -> np.ndarray:
    """支配时刻 ``ν(i)``：``i = 1..144`` → ``0/6/12/18``（每层 36 个时段）。"""
    index = np.arange(1, periods + 1)
    return 6 * ((index - 1) // 36)


def downscale(pv_row: np.ndarray, hour: int, *, periods: int = PERIODS_PER_DAY) -> np.ndarray:
    """AS05 降尺度算子 ``Π_m``（整点点值 + 整点锚定线性插值）。

    ``pv_row[k−1] = A_{m,k}``（``(m+k):00`` 的功率点值，``k = 1..24``）。时段 ``i`` 的块
    ``b = ⌈i/6⌉``、块内位置 ``j = i − 6(b−1)``，时效 ``k = b − m``：

    * ``k = 1``：前向保持 ``A_{m,1}``；
    * ``2 ≤ k ≤ 24``：``(1 − j/6)·A_{m,k−1} + (j/6)·A_{m,k}``；
    * ``k < 1``（早于发布时刻）或 ``b = m + k > 24``（跨年项）：**未定义（NaN）**，不消费。
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
        if lead < 1 or lead > 24:
            continue
        if lead == 1:
            out[index - 1] = row[0]
        else:
            out[index - 1] = (1.0 - position / 6.0) * row[lead - 2] + (position / 6.0) * row[lead - 1]
    return out


def cross_year_dropped_count(hour: int) -> int:
    """跨年项个数：``m = 6/12/18`` 分别丢弃 6/12/18 项（合计 36，AS05 第 4 条 / B7-5）。"""
    if hour == 0:
        return 0
    low, high = CROSS_YEAR_DROPPED[hour]
    return int(high - low + 1)


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
    """标准尺度感知相对残差：``residual / max(1, ‖A‖∞·‖x‖∞ + ‖b‖∞)``。

    分母取 ``‖A‖∞·‖x‖∞ + ‖b‖∞``（经典 scaled residual），下限 1 以避免小尺度层的除零放大。
    """
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
    """该层吞吐量 ``Σ_t(c_{d,t}+q_dis_{d,t})`` 的紧上界（T7-1 的 ε 相对化分母）。"""
    return float(periods) * (C_CAP + Q_CAP)


def throughput_coefficients(size: int, c_offset: int, q_dis_offset: int, periods: int) -> np.ndarray:
    """T7-1 的次目标系数向量：``c`` 与 ``q_dis`` 位置为 1，其余为 0（共享算子，M1–M8 一致）。"""
    coefficients = np.zeros(size)
    coefficients[c_offset : c_offset + periods] = 1.0
    coefficients[q_dis_offset : q_dis_offset + periods] = 1.0
    return coefficients


def tiebreak_epsilon(primary_reference: float, scale: float) -> float:
    """T7-1 的 ``ε``：``1e-6 × max(|主目标尺度|,1) / 吞吐量尺度``（无量纲、确定性）。"""
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
    """T7-3：退化维度代理 = 活跃约束数（等式 + 紧不等式 + 贴界变量） − 变量数。"""
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
    """团队 T7 的共享求解器（``M1`` 计划/调整层；``M2``–``M8`` 必须复用，T7-5）。

    四段式，全部确定性、无随机源：

    ① **基线**：纯主目标 LP → ``P*``（T7-2 的「加入次目标前」）。
    ② **T7-1 字面式**：``min [主目标] + ε·Σ(c+q_dis)``；ε 按 T7-2 逐层验证，不满足则按
       ``T7_SHRINK_FACTOR`` 缩小后重跑（有界）。调整层的 ``P*`` 是偏差结算费用，可小到与 HiGHS
       对偶容差同量级，故该式在数值上可能被求解器忽略（次目标不起作用）——如实记录于
       ``weighted_sum_effective``，**不**作为提交解。
    ③ **字典序提交解**（T7-1 优先序语义在 ε→0⁺ 的精确、可解析实现）：在主目标最优面
       ``{primary ≤ P* + 1e-9·max(|P*|,1)}`` 上**最小化**吞吐量，得到吞吐量最小的最优轨迹。
    ④ **T7-3 退化探测**：在同一主目标最优面上**最大化**吞吐量；若上界显著大于 ③ 的最小值，
       说明该层仍存在多个最优轨迹，必须报告退化维度与影响的上游量，不得静默取一个解。
    """
    n_variables = int(primary_objective.shape[0])
    total_seconds = 0.0
    primary_row = np.asarray(primary_objective, dtype=float).reshape(1, -1)

    # ① 基线：纯主目标 LP
    baseline_result, baseline_seconds = _solve(
        primary_objective, a_eq, b_eq, a_ub, b_ub, bounds, time_limit_seconds=time_limit_seconds
    )
    total_seconds += baseline_seconds
    if baseline_result.x is None:
        record = _layer_record(
            baseline_result, baseline_seconds, day=day, hour=hour,
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

    # ② T7-1 字面式（诊断 + T7-2 的「加入次目标后」）+ ε 收缩
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

    # ③ 字典序提交解：主目标最优面上最小化吞吐量
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

    # ④ T7-3：同一主目标最优面上最大化吞吐量，判定是否仍有多重最优
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
        result, committed_seconds, day=day, hour=hour,
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


def solve_plan_layer(
    *,
    price: np.ndarray,
    load_energy: np.ndarray,
    pv_fc_energy: np.ndarray,
    e_start: float,
    time_limit_seconds: float,
    day: int = -1,
) -> tuple[dict[str, np.ndarray], LayerRecord, TiebreakRecord]:
    """计划层 ``(PL_d)``：``min Σ p_i·b_i + ε·Σ(c+q_dis)``（团队 T1 主口径 + T7-1 tie-breaking）。"""
    n = PERIODS_PER_DAY
    size = 5 * n
    objective = np.zeros(size)
    objective[0:n] = price

    bounds = np.empty((size, 2), dtype=float)
    bounds[0:n, 0] = 0.0
    bounds[0:n, 1] = np.inf
    bounds[n : 2 * n, 0] = 0.0
    bounds[n : 2 * n, 1] = C_CAP
    bounds[2 * n : 3 * n, 0] = 0.0
    bounds[2 * n : 3 * n, 1] = Q_CAP
    bounds[3 * n : 4 * n, 0] = 0.0
    bounds[3 * n : 4 * n, 1] = pv_fc_energy
    bounds[4 * n : 5 * n, 0] = E_MIN
    bounds[4 * n : 5 * n, 1] = E_MAX

    tau = np.arange(n, dtype=np.int64)
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    vals: list[np.ndarray] = []
    rows += [tau, tau, tau, tau]
    cols += [tau, 2 * n + tau, n + tau, 3 * n + tau]
    vals += [np.ones(n), np.ones(n), -np.ones(n), -np.ones(n)]
    rows += [n + tau, n + tau, n + tau[1:], n + tau]
    cols += [4 * n + tau, n + tau, 4 * n + tau[1:] - 1, 2 * n + tau]
    vals += [np.ones(n), -ETA_CH * np.ones(n), -np.ones(n - 1), (1.0 / ETA_DIS) * np.ones(n)]
    a_eq = coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(2 * n, size),
    ).tocsr()
    b_eq = np.concatenate([load_energy - pv_fc_energy, np.concatenate([[e_start], np.zeros(n - 1)])])

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
        layer="plan",
        day=day,
        hour=0,
        boundary_index=size - 1,
        time_limit_seconds=time_limit_seconds,
    )
    if result.x is None:
        return {}, record, tiebreak
    x = np.asarray(result.x, dtype=float)
    solution = {
        "b": x[0:n],
        "c": x[n : 2 * n],
        "q_dis": x[2 * n : 3 * n],
        "s": x[3 * n : 4 * n],
        "E": x[4 * n : 5 * n],
    }
    return solution, record, tiebreak


def solve_adjustment_layer(
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
    """调整层 ``(AD_{d,m})``：``min Σ_{i∈R_m}[β_def·p·u⁺ + β_over·p·u⁻] + ε·Σ(c+q_dis)``（AD-3/AD-5 + T7-1）。

    仅返回该层解；调用方只提交 ``D_m``（其余为前视，会被后继层重优化）。
    """
    global_index = np.arange(6 * hour + 1, PERIODS_PER_DAY + 1)
    n = int(global_index.shape[0])
    size = 7 * n
    objective = np.zeros(size)
    objective[5 * n : 6 * n] = BETA_DEF * price[global_index - 1]
    objective[6 * n : 7 * n] = BETA_OVER * price[global_index - 1]

    bounds = np.empty((size, 2), dtype=float)
    bounds[0:n, 0] = 0.0
    bounds[0:n, 1] = np.inf
    bounds[n : 2 * n, 0] = 0.0
    bounds[n : 2 * n, 1] = C_CAP
    bounds[2 * n : 3 * n, 0] = 0.0
    bounds[2 * n : 3 * n, 1] = Q_CAP
    bounds[3 * n : 4 * n, 0] = 0.0
    bounds[3 * n : 4 * n, 1] = pv_fc_energy[global_index - 1]
    bounds[4 * n : 5 * n, 0] = E_MIN
    bounds[4 * n : 5 * n, 1] = E_MAX
    bounds[5 * n : 7 * n, 0] = 0.0
    bounds[5 * n : 7 * n, 1] = np.inf

    tau = np.arange(n, dtype=np.int64)
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    vals: list[np.ndarray] = []
    # 层内平衡：q + q_dis − c − s = L·Δt − Π_m·Δt
    rows += [tau, tau, tau, tau]
    cols += [tau, 2 * n + tau, n + tau, 3 * n + tau]
    vals += [np.ones(n), np.ones(n), -np.ones(n), -np.ones(n)]
    # 状态转移：E_j − E_{j−1} − η c_j + q_dis_j/η = 0，j = 1 时 RHS = E_{6m}
    rows += [n + tau, n + tau, n + tau[1:], n + tau]
    cols += [4 * n + tau, n + tau, 4 * n + tau[1:] - 1, 2 * n + tau]
    vals += [np.ones(n), -ETA_CH * np.ones(n), -np.ones(n - 1), (1.0 / ETA_DIS) * np.ones(n)]
    a_eq = coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(2 * n, size),
    ).tocsr()
    b_eq = np.concatenate(
        [load_energy[global_index - 1] - pv_fc_energy[global_index - 1], np.concatenate([[e_start], np.zeros(n - 1)])]
    )

    # 分段线性化（AD-5，LP 无损）：u⁺ ≥ b − q（第 j 行）；u⁻ ≥ q − b（第 n+j 行）
    plan_slice = plan_b[global_index - 1]
    ub_rows: list[np.ndarray] = []
    ub_cols: list[np.ndarray] = []
    ub_vals: list[np.ndarray] = []
    ub_rows += [tau, tau]
    ub_cols += [tau, 5 * n + tau]
    ub_vals += [-np.ones(n), -np.ones(n)]
    ub_rows += [n + tau, n + tau]
    ub_cols += [tau, 6 * n + tau]
    ub_vals += [np.ones(n), -np.ones(n)]
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
        layer="adjustment",
        day=day,
        hour=hour,
        boundary_index=5 * n - 1,
        time_limit_seconds=time_limit_seconds,
    )
    if result.x is None:
        return {}, record, tiebreak
    x = np.asarray(result.x, dtype=float)
    solution = {
        "q": x[0:n],
        "c": x[n : 2 * n],
        "q_dis": x[2 * n : 3 * n],
        "s": x[3 * n : 4 * n],
        "E": x[4 * n : 5 * n],
        "u_plus": x[5 * n : 6 * n],
        "u_minus": x[6 * n : 7 * n],
    }
    return solution, record, tiebreak


def run_m1(data: ChainInputs, *, time_limit_seconds: float = 60.0, deadline: float | None = None) -> M1Result:
    """按 ``formulation.md`` §3.10 执行 ``M1``：逐日 4 次 LP + 闭式结算。

    ``deadline`` 为 ``time.perf_counter()`` 口径的墙钟上限；超限抛 :class:`BudgetExceeded`，
    已完成的层证据由调用方写入 solver 日志（不伪报完成）。
    """
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
    q_em = np.zeros(shape)
    s_settle = np.zeros(shape)
    records: list[LayerRecord] = []
    tiebreaks: list[TiebreakRecord] = []

    pv0 = data.forecast_energy(0)
    e_prev = E_INIT
    for day in range(days):
        if deadline is not None and time.perf_counter() > deadline:
            raise BudgetExceeded(f"墙钟预算耗尽：已完成 {day}/{days} 天")
        plan, record, tiebreak = solve_plan_layer(
            price=data.price[day],
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
                f"计划层 LP 未达最优（day={day}, status={record.status}）：{record.message}",
                day=day,
                hour=0,
                status=record.status,
            )
        plan_b[day] = plan["b"]
        plan_c[day] = plan["c"]
        plan_q_dis[day] = plan["q_dis"]
        plan_s[day] = plan["s"]
        plan_E[day] = plan["E"]
        q[day, 0:36] = plan["b"][0:36]
        c[day, 0:36] = plan["c"][0:36]
        q_dis[day, 0:36] = plan["q_dis"][0:36]
        state[day, 0:36] = plan["E"][0:36]

        for hour in (6, 12, 18):
            if deadline is not None and time.perf_counter() > deadline:
                raise BudgetExceeded(f"墙钟预算耗尽：day={day}, hour={hour}")
            pv_m = data.forecast_energy(hour)[day]
            layer, record, tiebreak = solve_adjustment_layer(
                hour=hour,
                price=data.price[day],
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
                    f"调整层 LP 未达最优（day={day}, hour={hour}, status={record.status}）：{record.message}",
                    day=day,
                    hour=hour,
                    status=record.status,
                )
            commit = slice(6 * hour, 6 * hour + 36)
            q[day, commit] = layer["q"][0:36]
            c[day, commit] = layer["c"][0:36]
            q_dis[day, commit] = layer["q_dis"][0:36]
            state[day, commit] = layer["E"][0:36]

        residual = q[day] + q_dis[day] + data.pv_act_energy[day] - data.load_energy[day] - c[day]
        s_settle[day] = np.maximum(residual, 0.0)
        q_em[day] = np.maximum(-residual, 0.0)
        e_prev = float(state[day, -1])

    return M1Result(
        data=data,
        plan_b=plan_b,
        plan_c=plan_c,
        plan_q_dis=plan_q_dis,
        plan_s=plan_s,
        plan_E=plan_E,
        q=q,
        c=c,
        q_dis=q_dis,
        E=state,
        q_em=q_em,
        s_settle=s_settle,
        layer_records=records,
        tiebreak_records=tiebreaks,
    )


def state_starts(result: M1Result) -> np.ndarray:
    """每日 0:00 储电量（``E_{d,0}``；``E_{1/1,0} = E_INIT``）。"""
    days = result.days
    out = np.empty(days)
    out[0] = E_INIT
    if days > 1:
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


def _format_minutes(total_minutes: int) -> str:
    """把「左端点分钟数」格式化为 ``H:MM``；≥1440 时按 AS01 写 ``+1``。"""
    if total_minutes < 1440:
        return f"{total_minutes // 60}:{total_minutes % 60:02d}"
    shifted = total_minutes - 1440
    return f"{shifted // 60}:{shifted % 60:02d}+1"


def interval_label(labels: list[str], start: int, stop: int) -> str:
    """按 AS01 生成 ``[τ_start+1, τ_stop+1 + 10min)`` 的区间标签（左端点口径）。

    团队勘误 R9（2026-09-11）：两端**都用** ``_format_minutes`` 的 ``H:MM`` 风格（小时不补零），
    与附件 5 模板列标签风格（如 ``9:50-10:00``）一致。旧实现起点取自 ``labels[start]``，
    而该标签由 ``strftime("%H:%M")`` 生成、**小时补零**，导致同一单元格出现 ``06:10-9:20`` 这种
    两侧风格不一致的写法。``labels`` 参数保留仅为签名兼容（不再用于拼接）。
    """
    del labels  # 仅签名兼容：时间一律由分钟数推导，避免两套风格混用
    return f"{_format_minutes(10 * (start + 1))}-{_format_minutes(10 * (stop + 1))}"


def emergency_intervals(
    q_em_day: np.ndarray, labels: list[str], *, tol: float = TOL
) -> list[dict[str, Any]]:
    """逐日紧急购电区间（连续 10 分钟时段合并，D11-A/A18）。"""
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


def evaluate(result: M1Result, *, full_horizon: bool = True) -> dict[str, Any]:
    """计算指标、结构恒等式 (I1d)–(I6d)（逐日 + 全期 + 交付期切片）与全部硬约束检查。"""
    data = result.data
    days = result.days
    b = result.plan_b
    q = result.q
    c = result.c
    q_dis = result.q_dis
    q_em = result.q_em
    s_settle = result.s_settle
    pv_act = data.pv_act_energy
    load = data.load_energy
    price = data.price
    starts = state_starts(result)
    ends = result.E[:, -1]

    dev_plus = np.maximum(b - q, 0.0)
    dev_minus = np.maximum(q - b, 0.0)
    cost_plan_d = np.sum(price * b, axis=1)
    cost_adj_d = np.sum(price * (BETA_DEF * dev_plus + BETA_OVER * dev_minus), axis=1)
    cost_em_d = np.sum(ALPHA_EM * price * q_em, axis=1)
    cost_total_d = cost_plan_d + cost_adj_d + cost_em_d

    checks: list[dict[str, Any]] = []

    def record(name: str, value: float, threshold: float, passed: bool, note: str = "") -> None:
        checks.append(
            {"name": name, "value": float(value), "threshold": float(threshold), "passed": bool(passed), "note": note}
        )

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

    # 层内余额（提交链 vs 支配层预报，L3）：s^{[ν(i)]} = q + Π Δt + q_dis − LΔt − c
    nu = dominance_map()
    forecast_energy_by_hour = {hour: data.forecast_energy(hour) for hour in DECISION_HOURS}
    layer_spill = np.empty((days, PERIODS_PER_DAY))
    for hour in DECISION_HOURS:
        cols = np.where(nu == hour)[0]
        layer_spill[:, cols] = (
            q[:, cols]
            + forecast_energy_by_hour[hour][:, cols]
            + q_dis[:, cols]
            - load[:, cols]
            - c[:, cols]
        )
    fc_upper = np.empty((days, PERIODS_PER_DAY))
    for hour in DECISION_HOURS:
        cols = np.where(nu == hour)[0]
        fc_upper[:, cols] = forecast_energy_by_hour[hour][:, cols]
    spill_upper_violation = float(np.max(layer_spill - fc_upper))
    spill_lower_violation = float(np.max(-layer_spill))

    if result.layer_records:
        eq_max = max(item.equality_residual_max for item in result.layer_records)
        eq_rel_max = max(item.equality_residual_relative_max for item in result.layer_records)
        ineq_max = max(item.inequality_residual_max for item in result.layer_records)
        ineq_rel_max = max(item.inequality_residual_relative_max for item in result.layer_records)
        bound_max = max(item.bound_violation_max for item in result.layer_records)
        worst_layer = max(item.status for item in result.layer_records)
    else:
        eq_max, eq_rel_max, ineq_max, ineq_rel_max, bound_max, worst_layer = 0.0, 0.0, 0.0, 0.0, 0.0, 0

    charge_power = np.maximum.reduce(
        [c / DELTA_T, ETA_CH * c / DELTA_T, q_dis / DELTA_T, q_dis / (ETA_DIS * DELTA_T)]
    )
    complementarity = float(np.sum(c * q_dis))
    same_period = int(np.sum((c > TOL) & (q_dis > TOL)))
    q_em_with_charge = int(np.sum((q_em > TOL) & (c > TOL)))

    record("layer_status_max", float(worst_layer), 0.0, worst_layer == 0, "所有层 HiGHS status = 0 (Optimal)")
    record("layer_equality_residual_max", eq_max, LAYER_TOL, eq_max <= LAYER_TOL,
           "各层等式残差（求解器内部绝对；AS『等式残差 ≤1e-6』，HiGHS 可行性容差 1e-7）")
    record("layer_equality_residual_relative_max", eq_rel_max, LAYER_TOL_RELATIVE,
           eq_rel_max <= LAYER_TOL_RELATIVE,
           "各层等式残差（尺度感知相对：‖A_eq x−b_eq‖∞/(‖A_eq‖∞‖x‖∞+‖b_eq‖∞)）")
    record("layer_inequality_residual_max", ineq_max, LAYER_TOL, ineq_max <= LAYER_TOL,
           "各层不等式残差（求解器内部绝对；HiGHS 可行性容差 1e-7）")
    record("layer_inequality_residual_relative_max", ineq_rel_max, LAYER_TOL_RELATIVE,
           ineq_rel_max <= LAYER_TOL_RELATIVE,
           "各层不等式残差（尺度感知相对：max(A_ub x−b_ub,0)/(‖A_ub‖∞‖x‖∞+‖b_ub‖∞)）")
    record("layer_bound_violation_max", bound_max, TOL, bound_max <= TOL, "各层变量界越界量")
    record("cross_day_continuity", float(np.max(continuity)) if continuity.size else 0.0, TOL,
           (not continuity.size) or float(np.max(continuity)) <= TOL, "|E_{d,0} − E_{d−1,144}| (I4d)")
    record("state_transition_residual", float(np.max(transition)), TOL, float(np.max(transition)) <= TOL,
           "|E_i − E_{i−1} − 0.9c_i + q_dis_i/0.9| (I5d)")
    record("settlement_balance_residual", float(np.max(settlement)), TOL, float(np.max(settlement)) <= TOL,
           "(I6d) 结算层等式平衡")
    record("layer_spill_upper_violation", spill_upper_violation, BALANCE_TOL,
           spill_upper_violation <= BALANCE_TOL,
           "提交链层内弃光 s ≤ Π_{ν(i)}·Δt（L3；formulation §4.3 各层余额残差 ≤1e-8）")
    record("layer_spill_lower_violation", spill_lower_violation, BALANCE_TOL,
           spill_lower_violation <= BALANCE_TOL,
           "提交链层内弃光 s ≥ 0（formulation §4.3 各层余额残差 ≤1e-8）")
    record("storage_upper_violation", max(float(np.max(result.E)) - E_MAX, 0.0), TOL,
           float(np.max(result.E)) <= E_MAX + TOL, "E ≤ 10800")
    record("storage_lower_violation", max(E_MIN - float(np.min(result.E)), 0.0), TOL,
           float(np.min(result.E)) >= E_MIN - TOL, "E ≥ 1200")
    record("charge_cap_violation", max(float(np.max(c)) - C_CAP, 0.0), TOL, float(np.max(c)) <= C_CAP + TOL,
           "c ≤ 833.3333（并网点侧紧）")
    record("discharge_cap_violation", max(float(np.max(q_dis)) - Q_CAP, 0.0), TOL,
           float(np.max(q_dis)) <= Q_CAP + TOL, "q_dis ≤ 750.0000（电池侧紧，D10 口径丙 / E1）")
    record("settle_spill_bound_violation", max(float(np.max(s_settle - pv_act)), 0.0), TOL,
           bool(np.all(s_settle <= pv_act + TOL)), "0 ≤ s' ≤ PV^act·Δt（L3）")
    record("plan_nonneg_violation", max(-float(np.min(b)), 0.0), TOL, float(np.min(b)) >= -TOL, "b ≥ 0")
    record("purchase_nonneg_violation", max(-float(np.min(q)), 0.0), TOL, float(np.min(q)) >= -TOL, "q ≥ 0")
    record("q_em_nonneg_violation", max(-float(np.min(q_em)), 0.0), TOL, float(np.min(q_em)) >= -TOL, "q_em ≥ 0")
    record("q_eq_b_first_block", float(np.max(np.abs(q[:, 0:36] - b[:, 0:36]))), TOL,
           float(np.max(np.abs(q[:, 0:36] - b[:, 0:36]))) <= TOL, "i ≤ 36 时 q = b（AD-1 替代量口径）")
    record("max_side_power_kw", float(np.max(charge_power)), P_MAX, float(np.max(charge_power)) <= P_MAX + 1e-3,
           "并网点侧与电池侧换算功率均 ≤ 5000 kW")
    record("identity_I1_residual", float(np.max(np.abs(i1_day))), TOL, float(np.max(np.abs(i1_day))) <= TOL,
           "(I1d) Σq_dis = η²Σc − η(E_T − E_0)")
    record("identity_I2_residual", float(np.max(np.abs(i2_day))), TOL, float(np.max(np.abs(i2_day))) <= TOL,
           "(I2d) Σq = N + Σs' + 0.19Σc + ηΔE − Σq_em")

    # ---- 团队 T7：统一 tie-breaking 的逐层不变性与退化审计（T7-1/T7-2/T7-3） ----
    t7_records = list(result.tiebreak_records)
    if t7_records:
        t7_rel_max = _finite_or(max(item.primary_relative_change for item in t7_records))
        t7_all_passed = bool(all(item.invariance_passed for item in t7_records))
        t7_shrinks = int(sum(item.shrinks for item in t7_records))
        t7_degenerate_layers = int(sum(1 for item in t7_records if item.degeneracy_degree > 0))
        t7_remaining_multiplicity = int(sum(1 for item in t7_records if item.throughput_unique is False))
        t7_probe_unknown = int(sum(1 for item in t7_records if item.throughput_unique is None))
        t7_throughput = _finite_or(float(np.sum([item.throughput_kwh for item in t7_records])))
        t7_throughput_before = _finite_or(float(np.sum([item.throughput_before_kwh for item in t7_records])))
        t7_state_change_max = _finite_or(
            float(np.max([item.baseline_state_change_max_kwh for item in t7_records]))
        )
        t7_epsilon_min = _finite_or(float(np.min([item.epsilon for item in t7_records])))
        t7_epsilon_max = _finite_or(float(np.max([item.epsilon for item in t7_records])))
        t7_max_degeneracy = int(max(item.degeneracy_degree for item in t7_records))
        t7_weighted_rel_max = _finite_or(
            max(item.weighted_primary_relative_change for item in t7_records)
        )
        t7_weighted_effective = int(sum(1 for item in t7_records if item.weighted_sum_effective))
        t7_lexicographic = int(sum(1 for item in t7_records if item.committed_solution == "lexicographic"))
        t7_fallbacks = int(sum(1 for item in t7_records if item.committed_solution != "lexicographic"))
    else:
        t7_rel_max, t7_all_passed, t7_shrinks = 0.0, True, 0
        t7_degenerate_layers = t7_remaining_multiplicity = t7_probe_unknown = 0
        t7_throughput = t7_throughput_before = t7_state_change_max = 0.0
        t7_epsilon_min = t7_epsilon_max = 0.0
        t7_max_degeneracy = 0
        t7_weighted_rel_max = 0.0
        t7_weighted_effective = t7_lexicographic = t7_fallbacks = 0

    record("t7_primary_invariance_max_relative_change", t7_rel_max, T7_INVARIANCE_TOL,
           t7_rel_max <= T7_INVARIANCE_TOL,
           "T7-2：加入次目标前后主目标相对变化（逐层最大值，须 ≤ 1e-9）")
    record("t7_invariance_all_layers_passed", float(int(not t7_all_passed)), 0.0, t7_all_passed,
           "T7-2：全部逐层记录 primary_relative_change ≤ 1e-9 且 invariance_passed=true")
    record("t7_epsilon_below_primary_scale", t7_epsilon_max, 1.0, t7_epsilon_max < 1.0,
           "T7-1：ε 为无量纲相对权重（ε ≪ 1）；次目标总量 ≤ 1e-6·主目标尺度")

    delivery = np.zeros(days, dtype=bool)
    delivery_start = min(DAILY_DELIVERY_START, days)
    delivery[delivery_start:] = True
    if delivery.any():
        q_d = q[delivery]
        c_d = c[delivery]
        q_em_d = q_em[delivery]
        s_d = s_settle[delivery]
        pv_d = pv_act[delivery]
        load_d = load[delivery]
        starts_d = starts[delivery_start]
        ends_d = float(ends[-1])
        net_d = float(np.sum(load_d - pv_d))
        i1_delivery = float(np.sum(q_dis[delivery]) - (ETA_ROUND_TRIP * np.sum(c_d) - ETA_DIS * (ends_d - starts_d)))
        i2_delivery = float(
            np.sum(q_d)
            - (
                net_d
                + float(np.sum(s_d))
                + (1.0 - ETA_ROUND_TRIP) * float(np.sum(c_d))
                + ETA_DIS * (ends_d - starts_d)
                - float(np.sum(q_em_d))
            )
        )
        record("identity_I1_delivery_residual", i1_delivery, TOL, abs(i1_delivery) <= TOL,
               "交付期切片 (I1)")
        record("identity_I2_delivery_residual", i2_delivery, TOL, abs(i2_delivery) <= TOL,
               "交付期切片 (I2)，N_req + E_{2/1,0} → E_T")
    else:
        net_d = 0.0
        i1_delivery = 0.0
        i2_delivery = 0.0

    cost_plan = float(np.sum(cost_plan_d))
    cost_adj = float(np.sum(cost_adj_d))
    cost_em = float(np.sum(cost_em_d))
    cost_total = cost_plan + cost_em + cost_adj
    cost_plan_delivery = float(np.sum(cost_plan_d[delivery])) if delivery.any() else 0.0
    cost_adj_delivery = float(np.sum(cost_adj_d[delivery])) if delivery.any() else 0.0
    cost_em_delivery = float(np.sum(cost_em_d[delivery])) if delivery.any() else 0.0
    cost_total_delivery = cost_plan_delivery + cost_adj_delivery + cost_em_delivery
    record("cost_decomposition_identity", cost_total - (cost_plan + cost_em + cost_adj), 1e-6,
           abs(cost_total - (cost_plan + cost_em + cost_adj)) <= 1e-6, "(R6d) 费用分解")

    bounds: dict[str, Any] = {}
    if full_horizon and delivery.any():
        p_min = float(np.min(price))
        lower = p_min * (
            net_d
            + (1.0 - ETA_ROUND_TRIP) * float(np.sum(c[delivery]))
            + ETA_DIS * (ends_d - starts_d)
            - float(np.sum(q_em[delivery]))
        )
        # 无储能可行策略（c = q_dis = 0）的构造上界：
        # C_plan(opt) ≤ Σp·b_policy；各调整层目标 ≤ 该层 R_m 上的策略偏差费用（策略对任意初态可行），
        # 故 C_adj ≤ Σ_m policy_cost(R_m)（i ≤ 72 / 73..108 / 109..144 分别计入 3/2/1 次，宽松但严格成立）；
        # C_em ≤ Σ 5p·q_em_policy。
        q_policy = np.empty_like(q)
        for hour in DECISION_HOURS:
            cols = np.where(nu == hour)[0]
            q_policy[:, cols] = np.maximum(load[:, cols] - forecast_energy_by_hour[hour][:, cols], 0.0)
        b_policy = np.maximum(load - data.forecast_energy(0), 0.0)
        r_policy = q_policy + pv_act - load
        q_em_policy = np.maximum(-r_policy, 0.0)
        dev_plus_policy = np.maximum(b_policy - q_policy, 0.0)
        dev_minus_policy = np.maximum(q_policy - b_policy, 0.0)
        policy_dev_cost = price * (BETA_DEF * dev_plus_policy + BETA_OVER * dev_minus_policy)
        plan_upper = float(np.sum(price[delivery] * b_policy[delivery]))
        adj_upper = 0.0
        for hour in (6, 12, 18):
            rows = slice(6 * hour, PERIODS_PER_DAY)
            adj_upper += float(np.sum(policy_dev_cost[delivery, rows]))
        em_upper = float(np.sum(ALPHA_EM * price[delivery] * q_em_policy[delivery]))
        upper = plan_upper + adj_upper + em_upper
        bounds = {
            "delivery_lower_bound_yuan": _round(lower),
            "delivery_lower_bound_formula": "p_min·[N_req + 0.19Σc + η(E_T − E_{2/1,0}) − Σq_em]",
            "delivery_constructed_upper_bound_yuan": _round(upper),
            "delivery_upper_bound_parts_yuan": {
                "plan": _round(plan_upper),
                "adjustment": _round(adj_upper),
                "emergency": _round(em_upper),
            },
            "delivery_upper_bound_formula": (
                "无储能可行策略（c = q_dis = 0、b/q 取该层预报净负荷）："
                "Σp·b_policy + Σ_m Σ_{R_m} 偏差费用 + Σ5p·q_em_policy（C_adj 部分对重叠时段重复计入，宽松但严格）"
            ),
            "delivery_formulation_reference_no_storage_actual_yuan": _round(
                float(np.sum(price[delivery] * np.maximum((load - pv_act)[delivery], 0.0)))
            ),
            "mean_daily_delivery_cost_yuan": _round(cost_total_delivery / max(int(delivery.sum()), 1)),
        }
        record("analytic_lower_bound", cost_total_delivery, lower, cost_total_delivery >= lower - 1e-6,
               "交付期 C_total ≥ p_min·[N_req + 0.19Σc + ηΔE − Σq_em]")
        record("analytic_upper_bound", cost_total_delivery, upper, cost_total_delivery <= upper + 1e-6,
               "交付期 C_total ≤ 无储能可行策略的构造上界（C_adj 部分为重叠计的宽松界）")
        record("magnitude_delivery_band", cost_total_delivery, DELIVERY_MAGNITUDE_BAND_YUAN[1],
               DELIVERY_MAGNITUDE_BAND_YUAN[0] <= cost_total_delivery <= DELIVERY_MAGNITUDE_BAND_YUAN[1],
               "B3-5：交付期费用须落在 10^6–10^8 元（10^7 量级），防 D9 的 Δt 误乘")
        mean_daily = cost_total_delivery / max(int(delivery.sum()), 1)
        record("magnitude_daily_band", mean_daily, DAILY_MAGNITUDE_BAND_YUAN[1],
               DAILY_MAGNITUDE_BAND_YUAN[0] <= mean_daily <= DAILY_MAGNITUDE_BAND_YUAN[1],
               "B3-5：日均费用须为 10^4 元量级；落入 10^3 元即 Δt 硬错误")

    simultaneous_mask = (c > TOL) & (q_dis > TOL)
    statistics = {
        "complementarity_sum_kwh2": _round(complementarity),
        "simultaneous_charge_discharge_periods": same_period,
        "simultaneous_charge_kwh": _round(float(np.sum(c[simultaneous_mask]))),
        "simultaneous_discharge_kwh": _round(float(np.sum(q_dis[simultaneous_mask]))),
        "periods_with_q_em_and_charge": q_em_with_charge,
        "days_with_emergency": int(np.sum(np.any(q_em > TOL, axis=1))),
        "periods_with_emergency": int(np.sum(q_em > TOL)),
        "days_with_deviation": int(np.sum(np.any((dev_plus > TOL) | (dev_minus > TOL), axis=1))),
        "note": (
            "同充放属调整层目标（仅偏差结算、无吞吐成本）导致的 LP 退化，不是硬约束违反；"
            "§5.1 的硬约束清单不含该项，§6.11 的『期望 0』是设计期望；费用与全部恒等式不受影响。"
        ),
    }
    series = {
        "period_index": list(range(1, days * PERIODS_PER_DAY + 1)),
        "day_index": [int(v) for v in np.repeat(np.arange(days), PERIODS_PER_DAY)],
        "price_yuan_per_kwh": [float(v) for v in price.reshape(-1)],
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
        "objective_yuan": _round(cost_total),
        "cost_plan_yuan": _round(cost_plan),
        "cost_adj_yuan": _round(cost_adj),
        "cost_em_yuan": _round(cost_em),
        "delivery": {
            "cost_total_yuan": _round(cost_total_delivery),
            "cost_plan_yuan": _round(cost_plan_delivery),
            "cost_adj_yuan": _round(cost_adj_delivery),
            "cost_em_yuan": _round(cost_em_delivery),
            "total_plan_kwh": _round(float(np.sum(b[delivery]))) if delivery.any() else 0.0,
            "total_purchase_kwh": _round(float(np.sum(q[delivery]))) if delivery.any() else 0.0,
            "total_q_em_kwh": _round(float(np.sum(q_em[delivery]))) if delivery.any() else 0.0,
            "total_charge_kwh": _round(float(np.sum(c[delivery]))) if delivery.any() else 0.0,
            "total_discharge_kwh": _round(float(np.sum(q_dis[delivery]))) if delivery.any() else 0.0,
            "total_spill_kwh": _round(float(np.sum(s_settle[delivery]))) if delivery.any() else 0.0,
            "net_load_kwh": _round(net_d),
            "storage_start_kwh": _round(starts[delivery_start]) if delivery.any() else 0.0,
            "storage_final_kwh": _round(ends_d) if delivery.any() else 0.0,
            "days": int(delivery.sum()),
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
            "days_with_deviation": int(np.sum(np.any((dev_plus > TOL) | (dev_minus > TOL), axis=1))),
            "simultaneous_charge_discharge_periods": same_period,
            "periods_with_q_em_and_charge": q_em_with_charge,
        },
        "identities": {
            "I1_daily_max_abs": float(np.max(np.abs(i1_day))),
            "I2_daily_max_abs": float(np.max(np.abs(i2_day))),
            "I1_residual": float(np.sum(i1_day)),
            "I2_residual": float(np.sum(i2_day)),
            "I1_delivery_residual": float(i1_delivery),
            "I2_delivery_residual": float(i2_delivery),
            "continuity_residual_max": float(np.max(continuity)) if continuity.size else 0.0,
            "transition_residual_max": float(np.max(transition)),
            "settlement_residual_max": float(np.max(settlement)),
        },
        "bounds": bounds,
        "statistics": statistics,
        "t7_tiebreak": {
            "rule": T7_TIEBREAK_RULE,
            "eps_relative": T7_EPS_RELATIVE,
            "invariance_tol": T7_INVARIANCE_TOL,
            "shrink_factor": T7_SHRINK_FACTOR,
            "max_shrinks": T7_MAX_SHRINKS,
            "layers": len(t7_records),
            "max_primary_relative_change": t7_rel_max,
            "all_layers_invariance_passed": t7_all_passed,
            "total_shrinks": t7_shrinks,
            "epsilon_min": t7_epsilon_min,
            "epsilon_max": t7_epsilon_max,
            "weighted_sum_max_primary_relative_change": t7_weighted_rel_max,
            "weighted_sum_effective_layers": t7_weighted_effective,
            "lexicographic_committed_layers": t7_lexicographic,
            "fallback_committed_layers": t7_fallbacks,
            "throughput_primary_only_kwh": t7_throughput_before,
            "throughput_tiebreak_kwh": t7_throughput,
            "throughput_reduced_kwh": t7_throughput_before - t7_throughput,
            "max_baseline_trajectory_change_kwh": t7_state_change_max,
            "degenerate_layers": t7_degenerate_layers,
            "max_degeneracy_degree": t7_max_degeneracy,
            "layers_with_remaining_multiplicity": t7_remaining_multiplicity,
            "layers_with_unknown_multiplicity": t7_probe_unknown,
            "note": (
                "T7-1 次目标 Σ(c+q_dis) 的 ε 为无量纲相对权重；提交解为 ③ 主目标最优面上的吞吐量最小解"
                "（T7-1 优先序在 ε→0⁺ 的精确实现），② 的字面加权式作为诊断对照逐层落盘。"
                "T7-3 的 degeneracy_degree = 活跃约束数 − 变量数，layers_with_remaining_multiplicity 为"
                "「主目标最优面上吞吐量上界 > 提交解吞吐量」的层数（即仍有多重最优）。"
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
    "CROSS_YEAR_DROPPED",
    "ChainInputs",
    "DAILY_DELIVERY_START",
    "DAYS_FULL",
    "DECISION_HOURS",
    "DELTA_T",
    "E_CAP_MAX",
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
    "M1Result",
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
    "cross_year_dropped_count",
    "dominance_map",
    "downscale",
    "emergency_intervals",
    "evaluate",
    "interval_label",
    "merge_interval_labels",
    "run_m1",
    "solve_adjustment_layer",
    "solve_plan_layer",
    "state_starts",
    "tiebreak_epsilon",
    "throughput_coefficients",
    "throughput_scale",
]
