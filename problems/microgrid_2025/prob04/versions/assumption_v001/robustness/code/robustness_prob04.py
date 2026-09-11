#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ruff: noqa: E501 —— 文件含大量中文判据/口径长字符串（rule/detail/label/note 等），折行会损害
# 「判据原文与 plan.md 逐字一致」的可审计性；其余规则（E/F/I/W）全部启用并通过。
"""prob04 robustness 实验批（预注册方案见 ``../plan.md``，跑数前冻结）。

对象：``assumption_v001`` / ``formulation_v001`` 的 accepted 主口径 **`4-2`**（逐日向前递推计划层 + 闭式结算层，
``q ≡ b``）与 **`M4-3`**（0:00 计划 + 6:00/12:00/18:00 调整 + ``0.5×``/``1.5×`` 双向偏差结算），
365 天 × 144 时段 = 52,560 时段，跨日状态连续、终端自由、1 月预热期不计交付；交付口径锚点为
``results/prob04_v001_f001_4-2_run002`` 与 ``results/prob04_v001_f001_4-3_run002``。

本实验**不修改 accepted 代码与数据**，而是通过只读导入 ``prob04_io`` / ``prob04_model`` / ``prob04_predict`` /
``run_prob04``，在每次情景运行前用「模块级参数覆盖 + 输入扰动 + 求解器设置注入 + 结构约束注入」构造变体，运行后恢复。

纪律（详见 ``../plan.md``）：

* 全部模型与全部 run 一律使用团队冻结的 ``AS21`` 字典序 tie-breaking；``--mode compact`` 只跳过
  ``T7`` 的 ② 字面加权式与 ④ 退化探测两个**诊断**环节（提交解仍为 ③ 字典序），并在 ``baseline_full``
  情景用**未修改的四段式**与 ``run002`` 逐项对账；若 compact 与 full 的提交解不一致，``baseline_check`` 直接判失败。
* ``A8-(b)`` 派生⑤：任何情景**不得**让决策层看到当天实际价。价格扰动一律作用于**价格序列本身**，
  并由扰动后的序列**重算** ``decision_price``（``PF-PERSIST`` / ``PF-DUAL`` / ``PF-HIST`` 都只用 ``≤ d−1`` 的信息）。
* ``4-2`` 与 ``4-3`` **分别提交、分别落盘到独立 output_directory**，判据与图表一律分链陈述。
* 失败样本**保留在 ``raw_samples.jsonl`` 并计入可行率**，不静默删除。
* 原始样本（jsonl + trajectories）与汇总统计（summary/sensitivity）分开保存；图件**不登记**为交付图表。
* 原始样本与 accepted 代码目录均为只读：脚本**不写** ``results/prob04_v001_f001_*``、``data/附件5/*`` 与 ``code/*``。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy.sparse import csr_matrix, vstack


def _project_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "AGENTS.md").exists():
            return candidate
    raise RuntimeError("无法从脚本位置定位项目根目录")


ROOT = _project_root()
VERSION_DIR = ROOT / "problems" / "microgrid_2025" / "prob04" / "versions" / "assumption_v001"
ACCEPTED_CODE_DIR = VERSION_DIR / "code"
ROBUSTNESS_DIR = VERSION_DIR / "robustness"
if str(ACCEPTED_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(ACCEPTED_CODE_DIR))

import prob04_io as IO  # noqa: E402
import prob04_model as M  # noqa: E402
import prob04_predict as P  # noqa: E402
import run_prob04 as R  # noqa: E402

_ORIGINAL_SOLVE_WITH_TIEBREAK = M._solve_with_tiebreak
_REAL_LINPROG = M.linprog
_ORIGINAL_KAPPA_SCHEDULE = P.kappa_schedule

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_SOLVER_NOT_OPTIMAL = 2
EXIT_INPUT_INVALID = 3
EXIT_BASELINE_GATE_FAILED = 4
EXIT_BUDGET_EXCEEDED = 5

CHAIN_42 = "4-2"
CHAIN_43 = "4-3"
CHAINS = (CHAIN_42, CHAIN_43)

SEED_DEFAULT = 20260911
DAYS_FULL = 365
PERIODS_PER_DAY = 144
D_REQ_START = int(M.D_REQ_START)

REFERENCE_DIRS = {
    CHAIN_42: "problems/microgrid_2025/prob04/versions/assumption_v001/results/prob04_v001_f001_4-2_run002",
    CHAIN_43: "problems/microgrid_2025/prob04/versions/assumption_v001/results/prob04_v001_f001_4-3_run002",
}
TEMPLATES = {
    CHAIN_42: "data/附件5/result4-2.xlsx",
    CHAIN_43: "data/附件5/result4-3.xlsx",
}

# 各决策层的「每时段变量块数」（用于从 bounds 行数反推时段数；见 prob04_model 的层求解器）
BOUNDS_DIVISOR = {"plan42": 6, "plan43": 5, "adjustment6": 7, "adjustment12": 7, "adjustment18": 7}

NOISE_FAMILIES_COMMON = ("noise_white_5", "noise_white_10", "noise_day_5", "noise_joint_day_5")
NOISE_FAMILIES_43 = ("noise_pvfc_5",)
NOISE_SIGMA = {
    "noise_white_5": 0.05,
    "noise_white_10": 0.10,
    "noise_day_5": 0.05,
    "noise_joint_day_5": 0.05,
    "noise_pvfc_5": 0.05,
}

FAMILY_GROUPS = ("param", "predictor", "input", "solver", "structural", "noise")

OAT_SPEC = {
    # group: (param key(s), 档位（升序）, 单调方向；+1 表示「参数上升 ⇒ 费用不增」，-1 表示「不降」)
    "eta_both": (("ETA_CH", "ETA_DIS"), (0.72, 0.855, 0.945, 0.99), +1),
    "eta_ch": (("ETA_CH",), (0.81, 0.99), +1),
    "eta_dis": (("ETA_DIS",), (0.81, 0.99), +1),
    "alpha_em": (("ALPHA_EM",), (4.0, 4.5, 4.75, 5.25, 5.5, 6.0), -1),
    "e_init": (("E_INIT",), (4800.0, 5400.0, 5700.0, 6300.0, 6600.0, 7200.0), 0),
    "p_max": (("P_MAX",), (4000.0, 4500.0, 4750.0, 5250.0, 5500.0, 6000.0), +1),
    "e_min": (("E_MIN",), (960.0, 1080.0, 1320.0, 1440.0), -1),
    "e_max": (("E_MAX",), (8640.0, 9720.0, 11880.0, 12000.0), +1),
    "beta": (("BETA_DEF", "BETA_OVER"), (0.4, 0.45, 0.55, 0.6), -1),
    "kappa_bounds": ((), (0.0, 1.0), 0),  # 仅 4-3；0 = 放宽 [0.25,4.0]，1 = 收紧 [0.75,1.25]
}
OAT_ORDER = (
    "eta_both",
    "eta_ch",
    "eta_dis",
    "alpha_em",
    "e_init",
    "p_max",
    "e_min",
    "e_max",
    "beta",
)

BUY_CAP_KW = (10326.0, 9000.0, 8000.0, 7500.0, 7000.0, 6500.0, 6000.0, 5500.0, 5000.0, 4500.0, 4000.0, 3500.0)

TOL = float(M.TOL)
LAYER_TOL = float(M.LAYER_TOL)
LAYER_TOL_RELATIVE = float(M.LAYER_TOL_RELATIVE)
T7_INVARIANCE_TOL = float(M.T7_INVARIANCE_TOL)
INVARIANCE_BOUNDARY_TOL = 1e-9
DELIVERY_BAND = tuple(float(v) for v in M.DELIVERY_MAGNITUDE_BAND_YUAN)
Q_EM_BAND = (0.5, 2.0)
# CF-10：Σq_em 是 max(0,·) 泛函，σ=10% 的输入扰动会**系统性**抬高它（本动作 34 天先导探针实测
# 2/4 的 noise_white_10 样本 > 2× 基准），故「机制完好」用宽带 [0.25×, 4×]，窄带 [0.5×, 2×]
# 的越界只作**披露**（narrow_band_excursions），不判失败。判据在实验批开始前冻结。
Q_EM_BAND_WIDE = (0.25, 4.0)
PALETTE = {
    "primary": "#1F4E79",
    "secondary": "#70AD47",
    "accent": "#ED7D31",
    "neutral": "#7F8C8D",
    "warning": "#C00000",
}


def log(message: str) -> None:
    print(f"[robust04] {message}", flush=True)


def _round(value: Any, digits: int = 6) -> Any:
    number = float(value)
    if not np.isfinite(number):
        return float("nan")
    return round(number, digits)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.write_text(text, encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)


def _pct(base: float, factor: float) -> float:
    return float(base * (1.0 + factor))


def _stable_seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def family_group(family: str) -> str:
    return "noise" if family.startswith("noise_") else family


# ---------------------------------------------------------------------------
# 模块级覆盖 / 恢复
# ---------------------------------------------------------------------------

_OVERRIDE_KEYS = (
    "ETA_CH",
    "ETA_DIS",
    "ETA_ROUND_TRIP",
    "E_INIT",
    "E_MIN",
    "E_MAX",
    "P_MAX",
    "C_CAP",
    "Q_CAP",
    "ALPHA_EM",
    "BETA_DEF",
    "BETA_OVER",
)
_SNAPSHOT = {name: float(getattr(M, name)) for name in _OVERRIDE_KEYS}
_KAPPA_SNAPSHOT = (float(P.KAPPA_LOWER), float(P.KAPPA_UPPER))


def apply_overrides(overrides: dict[str, float]) -> None:
    """把情景参数写入 ``prob04_model`` 的模块级常量，并**重算派生常量**。

    ``ETA_ROUND_TRIP`` / ``C_CAP`` / ``Q_CAP`` 在 ``prob04_model`` 导入时派生（M.py L45/L50-L51），
    故必须在每次覆盖后重算，否则 ``evaluate`` 的恒等式与 ``AS21`` 的 ε 尺度会用到过期值。
    """
    for key, value in overrides.items():
        setattr(M, key, float(value))
    M.ETA_ROUND_TRIP = M.ETA_CH * M.ETA_DIS
    M.C_CAP = M.P_MAX * M.DELTA_T
    M.Q_CAP = M.P_MAX * M.DELTA_T * M.ETA_DIS


def restore_defaults() -> None:
    """绝对复位（不依赖快照之外的状态）；恢复顺序与安装顺序相反。"""
    for name, value in _SNAPSHOT.items():
        setattr(M, name, value)
    M.ETA_ROUND_TRIP = M.ETA_CH * M.ETA_DIS
    M.C_CAP = M.P_MAX * M.DELTA_T
    M.Q_CAP = M.P_MAX * M.DELTA_T * M.ETA_DIS
    P.KAPPA_LOWER, P.KAPPA_UPPER = _KAPPA_SNAPSHOT
    M.linprog = _REAL_LINPROG
    M._solve_with_tiebreak = _ORIGINAL_SOLVE_WITH_TIEBREAK
    P.kappa_schedule = _ORIGINAL_KAPPA_SCHEDULE


class SolverOverride:
    """覆盖 ``prob04_model.linprog`` 的 method / presolve（``AS21``/``T7-5`` 允许的唯一差异面）。"""

    def __init__(self, *, method: str = "highs", presolve: bool = True) -> None:
        self.method = method
        self.presolve = bool(presolve)

    def install(self) -> None:
        real = _REAL_LINPROG
        method = self.method
        presolve = self.presolve

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            kwargs["method"] = method
            options = dict(kwargs.get("options") or {})
            options["presolve"] = presolve
            kwargs["options"] = options
            return real(*args, **kwargs)

        M.linprog = wrapper

    @staticmethod
    def uninstall() -> None:
        M.linprog = _REAL_LINPROG


def _compact_solve_with_tiebreak(**kwargs: Any) -> Any:
    """``AS21`` 字典序提交解的紧凑实现：只跑 ① 基线 + ③ 最优面字典序（每层 2 次 LP）。

    ② 字面 ε 加权式与 ④ 退化探测是**诊断**环节，跳过不改变 ③ 的提交解。
    任一异常（基线不可行 / 字典序不可行）一律**委派原始四段式**，保证不会因紧凑而改变提交解。
    """
    primary = np.asarray(kwargs["primary_objective"], dtype=float)
    throughput = np.asarray(kwargs["throughput_objective"], dtype=float)
    a_eq = kwargs["a_eq"]
    b_eq = kwargs["b_eq"]
    a_ub = kwargs["a_ub"]
    b_ub = kwargs["b_ub"]
    bounds = kwargs["bounds"]
    time_limit = float(kwargs["time_limit_seconds"])
    n_variables = int(primary.shape[0])

    baseline_result, baseline_seconds = M._solve(
        primary, a_eq, b_eq, a_ub, b_ub, bounds, time_limit_seconds=time_limit
    )
    if baseline_result.x is None or int(baseline_result.status) != 0:
        return _ORIGINAL_SOLVE_WITH_TIEBREAK(**kwargs)

    x_baseline = np.asarray(baseline_result.x, dtype=float)
    primary_before = float(np.dot(primary, x_baseline))
    throughput_before = float(np.dot(throughput, x_baseline))
    tol_primary = M.T7_FACE_PRIMARY_TOL_FRACTION * M.T7_INVARIANCE_TOL * max(abs(primary_before), 1.0)
    primary_row = primary.reshape(1, -1)
    if a_ub is not None and a_ub.shape[0]:
        face_a_ub = vstack([a_ub, csr_matrix(primary_row)]).tocsr()
        face_b_ub = np.concatenate([np.asarray(b_ub, dtype=float), [primary_before + tol_primary]])
    else:
        face_a_ub = csr_matrix(primary_row)
        face_b_ub = np.array([primary_before + tol_primary])

    lex_result, lex_seconds = M._solve(
        throughput, a_eq, b_eq, face_a_ub, face_b_ub, bounds, time_limit_seconds=time_limit
    )
    if lex_result.x is None or int(lex_result.status) != 0:
        return _ORIGINAL_SOLVE_WITH_TIEBREAK(**kwargs)

    x = np.asarray(lex_result.x, dtype=float)
    primary_after = float(np.dot(primary, x))
    relative = abs(primary_after - primary_before) / max(abs(primary_before), 1.0)
    throughput_kwh = float(np.dot(throughput, x))
    degeneracy_degree, active_constraints = M._degeneracy_proxy(
        x, n_variables, a_eq, a_ub, b_ub, bounds, tol=TOL
    )
    record = M._layer_record(
        lex_result,
        lex_seconds,
        day=kwargs["day"],
        hour=kwargs["hour"],
        layer=kwargs["layer"],
        a_eq=a_eq,
        b_eq=b_eq,
        a_ub=a_ub,
        b_ub=b_ub,
        bounds=bounds,
        objective=primary_after,
    )
    tiebreak = M.TiebreakRecord(
        layer=kwargs["layer"],
        day=kwargs["day"],
        hour=kwargs["hour"],
        primary_before_yuan=primary_before,
        primary_after_yuan=primary_after,
        primary_relative_change=relative,
        epsilon=M.tiebreak_epsilon(primary_before, float(kwargs["scale"])),
        shrinks=0,
        invariance_passed=bool(relative <= T7_INVARIANCE_TOL),
        throughput_kwh=throughput_kwh,
        throughput_before_kwh=throughput_before,
        throughput_reduced_kwh=throughput_before - throughput_kwh,
        baseline_state_change_max_kwh=float(np.max(np.abs(x - x_baseline))),
        degeneracy_degree=degeneracy_degree,
        active_constraints=active_constraints,
        variables=n_variables,
        weighted_primary_relative_change=float("nan"),
        weighted_throughput_kwh=float("nan"),
        weighted_sum_effective=False,
        committed_solution="lexicographic",
        throughput_upper_on_optimal_face_kwh=None,
        throughput_unique=None,
        probe_status=None,
        boundary_state_kwh=float(x[int(kwargs["boundary_index"])]),
        baseline_seconds=baseline_seconds,
        solver_seconds=baseline_seconds + lex_seconds,
        note="compact_mode: T7 ②/④ 诊断环节跳过，提交解 = ③ 字典序",
    )
    return lex_result, record, tiebreak


class TiebreakPatch:
    """把结构约束注入 ``bounds``，并按 ``compact`` 选择紧凑 / 完整四段式。

    * 购电上限：各层购电量块（每层第 0 块）的逐时段上界压到 ``cap·Δt``（kWh）；
    * 终端储电量：``4-2`` 钉在最后一天的计划层、``4-3`` 钉在最后一天的 ``m = 18`` 调整层；
    * ``boundary_index`` 在两个链的所有层都指向该层 ``E`` 块的最后一个元素（M.py L798/L871/L965）。
    """

    def __init__(self, *, chain: str, days: int, compact: bool, structural: dict[str, Any] | None = None) -> None:
        self.chain = chain
        self.days = days
        self.compact = compact
        self.structural = dict(structural or {})

    def _is_terminal_layer(self, layer: str) -> bool:
        if self.chain == CHAIN_42:
            return layer == "plan42"
        return layer == "adjustment18"

    def __call__(self, **kwargs: Any) -> Any:
        layer = str(kwargs["layer"])
        bounds = np.array(kwargs["bounds"], dtype=float, copy=True)
        n_periods = bounds.shape[0] // BOUNDS_DIVISOR[layer]
        cap_kwh = self.structural.get("buy_cap_kwh")
        if cap_kwh is not None:
            bounds[0:n_periods, 1] = np.minimum(bounds[0:n_periods, 1], float(cap_kwh))
        terminal = self.structural.get("terminal_e_kwh")
        if terminal is not None and self._is_terminal_layer(layer) and int(kwargs["day"]) == self.days - 1:
            bounds[int(kwargs["boundary_index"])] = np.array([float(terminal), float(terminal)])
        patched = dict(kwargs)
        patched["bounds"] = bounds
        if self.compact:
            return _compact_solve_with_tiebreak(**patched)
        return _ORIGINAL_SOLVE_WITH_TIEBREAK(**patched)


def _install_kappa_frozen() -> None:
    """``D6-C`` / ``AS11``：``κ_m ≡ 1``（调整层不更新价格预测）。"""

    def frozen(price: np.ndarray, day_index: int) -> dict[str, Any]:
        schedule = _ORIGINAL_KAPPA_SCHEDULE(price, day_index)
        records = []
        for item in schedule["records"]:
            record = dict(item)
            record["kappa_raw_formula"] = record.get("kappa")
            record["kappa"] = 1.0
            record["clipped"] = False
            record["reason"] = "kappa_frozen_1（D6-C/AS11 的 robustness 侧对照：调整层不更新价格预测）"
            records.append(record)
        return {
            "day_index": int(day_index),
            "records": records,
            "kappa": {int(item["m"]): 1.0 for item in records},
            "clip_events": [],
        }

    P.kappa_schedule = frozen


# ---------------------------------------------------------------------------
# 输入装载与情景扰动
# ---------------------------------------------------------------------------


def build_base(args: argparse.Namespace) -> dict[str, Any]:
    data2_path = ROOT / args.data2
    data4_path = ROOT / args.data4
    attachment2 = IO.read_attachment2(data2_path, expected_days=IO.DAYS_FULL)
    attachment4 = IO.read_attachment4_price(data4_path, expected_days=IO.DAYS_FULL)
    if attachment4.time_labels != attachment2.time_labels:
        raise IO.InputValidationError("附件 4 与附件 2 的 144 个时间列标签不一致（相位不同）")
    if attachment4.dates != attachment2.dates:
        raise IO.InputValidationError("附件 4 与附件 2 的日期序列不一致")
    days = args.days
    attachment3 = None
    forecast_kw: dict[int, np.ndarray] = {}
    if args.chain == CHAIN_43:
        attachment3 = IO.read_attachment3(ROOT / args.data3, expected_days=IO.DAYS_FULL)
        if attachment3.dates != attachment2.dates:
            raise IO.InputValidationError("附件 3 与附件 2 的日期序列不一致")
        forecast_kw = {
            int(hour): np.vstack([M.downscale(attachment3.row(day, hour), hour) for day in range(days)])
            for hour in P.DECISION_HOURS
        }
        for hour, matrix in forecast_kw.items():
            dominated = np.where(np.isfinite(matrix[0]))[0]
            if not np.isfinite(matrix[:, dominated]).all():
                raise IO.InputValidationError(f"降尺度预报在支配域含 NaN：hour={hour}")
    return {
        "chain": args.chain,
        "days": days,
        "attachment2": attachment2,
        "attachment3": attachment3,
        "attachment4": attachment4,
        "price_act": np.array(attachment4.price[:days], dtype=float, copy=True),
        "load_energy": np.array(attachment2.load_kw[:days], dtype=float, copy=True) * M.DELTA_T,
        "pv_act_energy": np.array(attachment2.pv_kw[:days], dtype=float, copy=True) * M.DELTA_T,
        "forecast_kw": forecast_kw,
    }


def build_decision_prices(price_act: np.ndarray, days: int, method: str) -> tuple[np.ndarray, int]:
    """由**给定价格序列**经预测器重算 ``\\hat p``（只用 ``≤ d−1`` 的历史，``AS07``/``AS08``）。"""
    matrix = np.empty((days, PERIODS_PER_DAY), dtype=float)
    fallbacks = 0
    for day in range(days):
        item = P.predict(price_act, day, method)
        matrix[day] = np.asarray(item["price"], dtype=float)
        if item["fallback"]:
            fallbacks += 1
    return matrix, fallbacks


def perturb(base: dict[str, Any], spec: dict[str, Any]) -> tuple[M.ChainInputs, dict[str, Any]]:
    """按情景构造扰动输入（预报矩阵结构不变；价格扰动后 ``decision_price`` 必须重算）。"""
    days = int(base["days"])
    price = np.array(base["price_act"], dtype=float, copy=True)
    load = np.array(base["load_energy"], dtype=float, copy=True)
    pv = np.array(base["pv_act_energy"], dtype=float, copy=True)
    forecast = {int(hour): np.array(matrix, dtype=float, copy=True) for hour, matrix in base["forecast_kw"].items()}
    info: dict[str, Any] = {"noise": None, "input": {}}

    noise = spec.get("noise") or {}
    if noise:
        family = str(noise["family"])
        sigma = float(NOISE_SIGMA[family])
        rng = np.random.default_rng(int(noise["seed"]))
        if family in ("noise_white_5", "noise_white_10"):
            load *= 1.0 + rng.normal(0.0, sigma, size=load.shape)
            pv *= 1.0 + rng.normal(0.0, sigma, size=pv.shape)
        elif family == "noise_day_5":
            load *= 1.0 + rng.normal(0.0, sigma, size=(days, 1))
            pv *= 1.0 + rng.normal(0.0, sigma, size=(days, 1))
        elif family == "noise_joint_day_5":
            load *= 1.0 + rng.normal(0.0, sigma, size=(days, 1))
            pv *= 1.0 + rng.normal(0.0, sigma, size=(days, 1))
            price *= 1.0 + rng.normal(0.0, sigma, size=(days, 1))
            price *= 1.0 + rng.normal(0.0, sigma, size=price.shape)
        elif family in ("noise_pvfc_5", "noise_pvfc_10"):
            for hour in forecast:
                matrix = forecast[hour]
                factor = 1.0 + rng.normal(0.0, sigma, size=matrix.shape)
                forecast[hour] = np.where(np.isfinite(matrix), np.maximum(matrix * factor, 0.0), matrix)
        else:
            raise ValueError(f"未知噪声族：{family}")
        info["noise"] = {
            "family": family,
            "index": int(noise["index"]),
            "sigma": sigma,
            "load_mean_relative_shift": _round(float(np.mean(load) / np.mean(base["load_energy"]) - 1.0), 9),
            "pv_mean_relative_shift": _round(float(np.mean(pv) / np.mean(base["pv_act_energy"]) - 1.0), 9),
            "price_mean_relative_shift": _round(float(np.mean(price) / np.mean(base["price_act"]) - 1.0), 9),
        }

    inp = spec.get("input") or {}
    if inp:
        rng = np.random.default_rng(_stable_seed(f"{spec['sid']}::input"))
        if "price_level" in inp:
            price *= float(inp["price_level"])
        if inp.get("price_noise_sigma"):
            price *= 1.0 + rng.normal(0.0, float(inp["price_noise_sigma"]), size=price.shape)
        if inp.get("load_noise_sigma"):
            load *= 1.0 + rng.normal(0.0, float(inp["load_noise_sigma"]), size=load.shape)
        if inp.get("pv_act_noise_sigma"):
            pv *= 1.0 + rng.normal(0.0, float(inp["pv_act_noise_sigma"]), size=pv.shape)
        if "pv_fc_bias" in inp:
            bias = float(inp["pv_fc_bias"])
            for hour in forecast:
                matrix = forecast[hour]
                forecast[hour] = np.where(np.isfinite(matrix), matrix * bias, matrix)
        if inp.get("pv_fc_noise_sigma"):
            sigma = float(inp["pv_fc_noise_sigma"])
            for hour in forecast:
                matrix = forecast[hour]
                factor = 1.0 + rng.normal(0.0, sigma, size=matrix.shape)
                forecast[hour] = np.where(np.isfinite(matrix), np.maximum(matrix * factor, 0.0), matrix)
        info["input"] = dict(inp)
        info["input"]["price_mean_relative_shift"] = _round(
            float(np.mean(price) / np.mean(base["price_act"]) - 1.0), 9
        )

    np.clip(load, 0.0, None, out=load)
    np.clip(pv, 0.0, None, out=pv)
    np.clip(price, 1e-6, None, out=price)

    method = str(spec.get("predictor") or P.PRIMARY_METHOD)
    decision, fallback_days = build_decision_prices(price, days, method)
    info["predictor"] = {"method": method, "fallback_days": fallback_days}
    inputs = M.ChainInputs(
        days=days,
        price_act=price,
        decision_price=decision,
        load_energy=load,
        pv_act_energy=pv,
        forecast_kw=forecast,
    )
    return inputs, info


# ---------------------------------------------------------------------------
# 单情景运行
# ---------------------------------------------------------------------------


def run_scenario(
    spec: dict[str, Any],
    base: dict[str, Any],
    *,
    compact: bool,
    time_limit: float,
    with_tables: bool = False,
    template_labels: list[str] | None = None,
) -> dict[str, Any]:
    chain = str(base["chain"])
    apply_overrides(spec.get("params") or {})
    bounds_override = spec.get("kappa_bounds")
    if bounds_override is not None:
        P.KAPPA_LOWER = float(bounds_override[0])
        P.KAPPA_UPPER = float(bounds_override[1])
    structural = dict(spec.get("structural") or {})
    force_full = bool(structural.pop("full_tiebreak", None))
    use_compact = compact and not force_full
    solver = spec.get("solver") or {}
    override = SolverOverride(method=str(solver.get("method", "highs")), presolve=bool(solver.get("presolve", True)))
    patch = TiebreakPatch(chain=chain, days=int(base["days"]), compact=use_compact, structural=structural)
    override.install()
    M._solve_with_tiebreak = patch
    if spec.get("kappa_frozen"):
        _install_kappa_frozen()
    started = time.perf_counter()
    try:
        inputs, perturb_info = perturb(base, spec)
        if chain == CHAIN_42:
            result = M.run_chain_42(inputs, time_limit_seconds=time_limit, deadline=None)
        else:
            result = M.run_chain_43(inputs, time_limit_seconds=time_limit, deadline=None)
        extra: dict[str, Any] = {}
        if with_tables:
            # 仅 baseline_full：走一次完整 evaluate + build_tables，与 run002 逐位对账。
            truncated = int(base["days"]) < DAYS_FULL
            metrics = M.evaluate(result, probe_mode=truncated, full_horizon=not truncated)
            tables = R.build_tables(
                result,
                metrics,
                base["attachment2"].time_labels,
                list(template_labels or []),
                probe_mode=truncated,
            )
            extra = {"metrics": metrics, "tables": tables}
        seconds = time.perf_counter() - started
        summary = summarize(result, seconds=seconds)
        summary["noise"] = perturb_info["noise"]
        summary["input"] = perturb_info["input"]
        summary["predictor_info"] = perturb_info["predictor"]
        return {"ok": True, "summary": summary, "info": perturb_info, **extra}
    finally:
        M._solve_with_tiebreak = _ORIGINAL_SOLVE_WITH_TIEBREAK
        SolverOverride.uninstall()
        restore_defaults()


def summarize(result: M.ChainResult, *, seconds: float) -> dict[str, Any]:
    """从 ``ChainResult`` 计算指标与恒等式（**不调用** ``M.evaluate``，避免构造 52,560 点 series）。"""
    days = int(result.days)
    chain = str(result.chain)
    b = result.plan_b
    q = result.q
    c = result.c
    q_dis = result.q_dis
    q_em = result.q_em
    spill = result.s_settle
    E = result.E
    price = result.price_act
    load = result.load_energy
    pv = result.pv_act_energy

    cb_act = M.cost_breakdown(result, use_actual_price=True)
    cb_fc = M.cost_breakdown(result, use_actual_price=False)
    starts = M.state_starts(result)
    ends = E[:, -1]

    delivery_start = min(D_REQ_START, days)
    has_delivery = days > delivery_start
    idx = slice(delivery_start, days)

    net_day = np.sum(load - pv, axis=1)
    i1_day = np.sum(q_dis, axis=1) - (
        M.ETA_ROUND_TRIP * np.sum(c, axis=1) - M.ETA_DIS * (ends - starts)
    )
    i2_day = np.sum(q, axis=1) - (
        net_day
        + np.sum(spill, axis=1)
        + (1.0 - M.ETA_ROUND_TRIP) * np.sum(c, axis=1)
        + M.ETA_DIS * (ends - starts)
        - np.sum(q_em, axis=1)
    )
    transition = np.abs(
        np.diff(np.concatenate([starts[:, None], E], axis=1), axis=1) - M.ETA_CH * c + q_dis / M.ETA_DIS
    )
    settlement = np.abs(q + q_em + pv + q_dis - load - c - spill)
    continuity = np.abs(starts[1:] - ends[:-1]) if days > 1 else np.zeros(0)
    cost_decomposition = cb_act["total"] - (cb_act["plan"] + cb_act["adjustment"] + cb_act["emergency"])

    records = result.layer_records
    if records:
        layer_status_max = int(max(item.status for item in records))
        eq_max = float(max(item.equality_residual_max for item in records))
        eq_rel_max = float(max(item.equality_residual_relative_max for item in records))
        ineq_max = float(max(item.inequality_residual_max for item in records))
        ineq_rel_max = float(max(item.inequality_residual_relative_max for item in records))
        bound_max = float(max(item.bound_violation_max for item in records))
        layer_seconds = float(sum(item.seconds for item in records))
        variables_max = int(max(item.variables for item in records))
    else:
        layer_status_max = 0
        eq_max = eq_rel_max = ineq_max = ineq_rel_max = bound_max = 0.0
        layer_seconds = 0.0
        variables_max = 0

    if chain == CHAIN_43:
        dev_plus = np.maximum(b - q, 0.0)
        dev_minus = np.maximum(q - b, 0.0)
    else:
        dev_plus = np.zeros_like(b)
        dev_minus = np.zeros_like(b)

    delivery = {
        "cost_total_yuan": _round(float(np.sum(cb_act["total"][idx]))) if has_delivery else 0.0,
        "cost_plan_yuan": _round(float(np.sum(cb_act["plan"][idx]))) if has_delivery else 0.0,
        "cost_adj_yuan": _round(float(np.sum(cb_act["adjustment"][idx]))) if has_delivery else 0.0,
        "cost_em_yuan": _round(float(np.sum(cb_act["emergency"][idx]))) if has_delivery else 0.0,
        "cost_total_fc_yuan": _round(float(np.sum(cb_fc["total"][idx]))) if has_delivery else 0.0,
        "delta_c_price_yuan": (
            _round(float(np.sum((cb_act["total"] - cb_fc["total"])[idx]))) if has_delivery else 0.0
        ),
        "delta_c_plan_yuan": (
            _round(float(np.sum((cb_act["plan"] - cb_fc["plan"])[idx]))) if has_delivery else 0.0
        ),
        "delta_c_adj_yuan": (
            _round(float(np.sum((cb_act["adjustment"] - cb_fc["adjustment"])[idx]))) if has_delivery else 0.0
        ),
        "delta_c_em_yuan": (
            _round(float(np.sum((cb_act["emergency"] - cb_fc["emergency"])[idx]))) if has_delivery else 0.0
        ),
        "total_plan_kwh": _round(float(np.sum(b[idx]))) if has_delivery else 0.0,
        "total_purchase_kwh": _round(float(np.sum(q[idx]))) if has_delivery else 0.0,
        "total_q_em_kwh": _round(float(np.sum(q_em[idx]))) if has_delivery else 0.0,
        "total_charge_kwh": _round(float(np.sum(c[idx]))) if has_delivery else 0.0,
        "total_discharge_kwh": _round(float(np.sum(q_dis[idx]))) if has_delivery else 0.0,
        "total_spill_kwh": _round(float(np.sum(spill[idx]))) if has_delivery else 0.0,
        "net_load_kwh": _round(float(np.sum(net_day[idx]))) if has_delivery else 0.0,
        "storage_start_kwh": (
            _round(float(starts[min(delivery_start, days - 1)])) if days else 0.0
        ),
        "storage_final_kwh": _round(float(ends[-1])),
        "days": int(days - delivery_start),
        "first_date_index": int(delivery_start),
        "last_date_index": int(days - 1),
    }
    totals = {
        "cost_total_yuan": _round(float(np.sum(cb_act["total"]))),
        "cost_plan_yuan": _round(float(np.sum(cb_act["plan"]))),
        "cost_adj_yuan": _round(float(np.sum(cb_act["adjustment"]))),
        "cost_em_yuan": _round(float(np.sum(cb_act["emergency"]))),
        "cost_total_fc_yuan": _round(float(np.sum(cb_fc["total"]))),
        "delta_c_price_yuan": _round(float(np.sum(cb_act["total"] - cb_fc["total"]))),
        "total_plan_kwh": _round(float(np.sum(b))),
        "total_purchase_kwh": _round(float(np.sum(q))),
        "total_q_em_kwh": _round(float(np.sum(q_em))),
        "total_charge_kwh": _round(float(np.sum(c))),
        "total_discharge_kwh": _round(float(np.sum(q_dis))),
        "total_spill_kwh": _round(float(np.sum(spill))),
        "net_load_kwh": _round(float(np.sum(net_day))),
        "max_charge_kwh": _round(float(np.max(c))),
        "max_discharge_kwh": _round(float(np.max(q_dis))),
        "max_plan_purchase_kwh": _round(float(np.max(b))),
        "max_final_purchase_kwh": _round(float(np.max(q))),
        "max_side_power_kw": _round(
            float(
                np.max(
                    np.maximum.reduce(
                        [c / M.DELTA_T, M.ETA_CH * c / M.DELTA_T, q_dis / M.DELTA_T, q_dis / (M.ETA_DIS * M.DELTA_T)]
                    )
                )
            )
        ),
        "storage_initial_kwh": _round(float(M.E_INIT)),
        "storage_final_kwh": _round(float(ends[-1])),
        "storage_range_kwh": [_round(float(np.min(E))), _round(float(np.max(E)))],
        "days_with_emergency": int(np.sum(np.any(q_em > TOL, axis=1))),
        "periods_with_emergency": int(np.sum(q_em > TOL)),
        "simultaneous_charge_discharge_periods": int(np.sum((c > TOL) & (q_dis > TOL))),
        "periods_with_q_em_and_charge": int(np.sum((q_em > TOL) & (c > TOL))),
        "deviation_plus_kwh": _round(float(np.sum(dev_plus))),
        "deviation_minus_kwh": _round(float(np.sum(dev_minus))),
    }
    statistics = {
        "periods_with_spill": int(np.sum(spill > TOL)),
        "days_with_emergency": totals["days_with_emergency"],
        "periods_with_emergency": totals["periods_with_emergency"],
        "simultaneous_charge_discharge_periods": totals["simultaneous_charge_discharge_periods"],
        "periods_with_q_em_and_charge": totals["periods_with_q_em_and_charge"],
        "max_purchase_kwh": totals["max_plan_purchase_kwh"],
        "max_purchase_day_kwh": _round(float(np.max(np.sum(b, axis=1)))),
        "kappa_clip_events": int(
            sum(1 for record in result.kappa_records if bool(record.get("clipped")))
        ),
        "kappa_records": int(len(result.kappa_records)),
        "state_start_kwh": [_round(float(v)) for v in starts],
        "state_end_kwh": [_round(float(v)) for v in ends],
    }
    residuals = {
        "layer_status_max": layer_status_max,
        "layer_equality_residual_max": eq_max,
        "layer_equality_residual_relative_max": eq_rel_max,
        "layer_inequality_residual_max": ineq_max,
        "layer_inequality_residual_relative_max": ineq_rel_max,
        "layer_bound_violation_max": bound_max,
        "I1_daily_max_abs": float(np.max(np.abs(i1_day))),
        "I2_daily_max_abs": float(np.max(np.abs(i2_day))),
        "settlement_balance_max": float(np.max(settlement)),
        "state_transition_max": float(np.max(transition)),
        "cross_day_continuity_max": float(np.max(continuity)) if continuity.size else 0.0,
        "cost_decomposition_max": float(np.max(np.abs(cost_decomposition))),
    }
    bounds_check = {
        "max_charge_kwh": totals["max_charge_kwh"],
        "c_cap_kwh": _round(float(M.C_CAP)),
        "max_discharge_kwh": totals["max_discharge_kwh"],
        "q_cap_kwh": _round(float(M.Q_CAP)),
        "storage_min_kwh": _round(float(np.min(E))),
        "storage_max_kwh": _round(float(np.max(E))),
        "e_min_kwh": _round(float(M.E_MIN)),
        "e_max_kwh": _round(float(M.E_MAX)),
        "max_side_power_kw": totals["max_side_power_kw"],
        "p_max_kw": _round(float(M.P_MAX)),
        "min_price_yuan_per_kwh": _round(float(np.min(price))),
        "max_price_yuan_per_kwh": _round(float(np.max(price))),
        "min_plan_purchase_kwh": _round(float(np.min(b))),
        "min_q_em_kwh": _round(float(np.min(q_em))),
        "min_spill_kwh": _round(float(np.min(spill))),
    }
    t7 = _tiebreak_summary(result)
    return {
        "chain": chain,
        "days": days,
        "objective_yuan": totals["cost_total_yuan"],
        "cost_plan_yuan": totals["cost_plan_yuan"],
        "cost_adj_yuan": totals["cost_adj_yuan"],
        "cost_em_yuan": totals["cost_em_yuan"],
        "delivery": delivery,
        "totals": totals,
        "residuals": residuals,
        "bounds": bounds_check,
        "statistics": statistics,
        "t7": t7,
        "daily_cost_total_yuan": [_round(float(v)) for v in cb_act["total"]],
        "daily_cost_total_fc_yuan": [_round(float(v)) for v in cb_fc["total"]],
        "daily_charge_kwh": [_round(float(v)) for v in np.sum(c, axis=1)],
        "daily_discharge_kwh": [_round(float(v)) for v in np.sum(q_dis, axis=1)],
        "daily_purchase_kwh": [_round(float(v)) for v in np.sum(q, axis=1)],
        "daily_plan_kwh": [_round(float(v)) for v in np.sum(b, axis=1)],
        "daily_q_em_kwh": [_round(float(v)) for v in np.sum(q_em, axis=1)],
        "daily_spill_kwh": [_round(float(v)) for v in np.sum(spill, axis=1)],
        "seconds": _round(seconds, 6),
        "layer_seconds_total": _round(layer_seconds, 6),
        "lp_calls": int(len(records)),
        "variables_max": variables_max,
    }


def _tiebreak_summary(result: M.ChainResult) -> dict[str, Any]:
    records = result.tiebreak_records
    if not records:
        return {
            "layers": 0,
            "max_primary_relative_change": 0.0,
            "all_layers_invariance_passed": True,
            "total_shrinks": 0,
            "lexicographic_committed_layers": 0,
            "fallback_committed_layers": 0,
            "degenerate_layers": 0,
            "max_degeneracy_degree": 0,
            "layers_with_remaining_multiplicity": 0,
            "layers_with_unknown_multiplicity": 0,
            "probe_coverage": 0.0,
            "throughput_primary_only_kwh": 0.0,
            "throughput_tiebreak_kwh": 0.0,
            "throughput_reduced_kwh": 0.0,
            "max_baseline_trajectory_change_kwh": 0.0,
        }
    relative = [float(item.primary_relative_change) for item in records]
    unique = [item.throughput_unique for item in records]
    known = [value for value in unique if value is not None]
    return {
        "layers": len(records),
        "max_primary_relative_change": _round(max(relative), 12),
        "all_layers_invariance_passed": bool(all(item.invariance_passed for item in records)),
        "total_shrinks": int(sum(int(item.shrinks) for item in records)),
        "lexicographic_committed_layers": int(
            sum(1 for item in records if item.committed_solution == "lexicographic")
        ),
        "fallback_committed_layers": int(
            sum(1 for item in records if item.committed_solution != "lexicographic")
        ),
        "degenerate_layers": int(sum(1 for item in records if int(item.degeneracy_degree) > 0)),
        "max_degeneracy_degree": int(max(int(item.degeneracy_degree) for item in records)),
        "layers_with_remaining_multiplicity": int(sum(1 for value in known if value is False)),
        "layers_with_unknown_multiplicity": int(sum(1 for value in unique if value is None)),
        "probe_coverage": _round(len(known) / len(records), 6),
        "throughput_primary_only_kwh": _round(sum(float(item.throughput_before_kwh) for item in records)),
        "throughput_tiebreak_kwh": _round(sum(float(item.throughput_kwh) for item in records)),
        "throughput_reduced_kwh": _round(sum(float(item.throughput_reduced_kwh) for item in records)),
        "max_baseline_trajectory_change_kwh": _round(
            max(float(item.baseline_state_change_max_kwh) for item in records)
        ),
    }


def check_subsample_identities(summary: dict[str, Any]) -> list[str]:
    """逐情景恒等式闸门（返回失败项名列表；不抛异常）。"""
    failed: list[str] = []
    res = summary["residuals"]
    if res["layer_status_max"] != 0:
        failed.append("layer_status_max")
    if res["layer_equality_residual_max"] > LAYER_TOL:
        failed.append("layer_equality_residual_max")
    if res["layer_equality_residual_relative_max"] > LAYER_TOL_RELATIVE:
        failed.append("layer_equality_residual_relative_max")
    if res["layer_inequality_residual_max"] > LAYER_TOL:
        failed.append("layer_inequality_residual_max")
    if res["layer_inequality_residual_relative_max"] > LAYER_TOL_RELATIVE:
        failed.append("layer_inequality_residual_relative_max")
    if res["layer_bound_violation_max"] > TOL:
        failed.append("layer_bound_violation_max")
    if res["I1_daily_max_abs"] > TOL:
        failed.append("I1_daily_max_abs")
    if res["I2_daily_max_abs"] > TOL:
        failed.append("I2_daily_max_abs")
    if res["settlement_balance_max"] > TOL:
        failed.append("settlement_balance_max")
    if res["state_transition_max"] > TOL:
        failed.append("state_transition_max")
    if res["cross_day_continuity_max"] > TOL:
        failed.append("cross_day_continuity_max")
    if abs(res["cost_decomposition_max"]) > TOL:
        failed.append("cost_decomposition_max")
    bounds = summary["bounds"]
    if bounds["max_charge_kwh"] > bounds["c_cap_kwh"] + TOL:
        failed.append("charge_cap")
    if bounds["max_discharge_kwh"] > bounds["q_cap_kwh"] + TOL:
        failed.append("discharge_cap")
    if bounds["storage_min_kwh"] < bounds["e_min_kwh"] - TOL:
        failed.append("storage_lower_bound")
    if bounds["storage_max_kwh"] > bounds["e_max_kwh"] + TOL:
        failed.append("storage_upper_bound")
    if bounds["max_side_power_kw"] > bounds["p_max_kw"] + TOL:
        failed.append("side_power_cap")
    if bounds["min_plan_purchase_kwh"] < -TOL:
        failed.append("purchase_nonnegativity")
    if bounds["min_q_em_kwh"] < -TOL:
        failed.append("q_em_nonnegativity")
    if summary["chain"] == CHAIN_42:
        totals = summary["totals"]
        if totals["total_q_em_kwh"] > INVARIANCE_BOUNDARY_TOL:
            failed.append("q_em_theorem_42")
        if totals["days_with_emergency"] != 0:
            failed.append("q_em_days_42")
    return failed


# ---------------------------------------------------------------------------
# 情景枚举
# ---------------------------------------------------------------------------


def _scenario(sid: str, family: str, label: str, **kwargs: Any) -> dict[str, Any]:
    spec = {
        "sid": sid,
        "family": family,
        "group": family_group(family),
        "label": label,
        "params": {},
        "predictor": None,
        "kappa_bounds": None,
        "kappa_frozen": False,
        "structural": {},
        "solver": {},
        "noise": {},
        "input": {},
    }
    spec.update(kwargs)
    return spec


def build_matrix_scenarios(chain: str) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = [
        _scenario("baseline", "baseline", "基线（默认参数、compact 提交解）"),
        _scenario(
            "baseline_full",
            "baseline",
            "基线（未修改四段式 tie-break，用于与 run002 逐位对账）",
            structural={"full_tiebreak": 1.0},
        ),
    ]

    # --- 参数 OAT ---
    for group in OAT_ORDER:
        keys, levels, _direction = OAT_SPEC[group]
        if group == "beta" and chain != CHAIN_43:
            continue
        if group == "kappa_bounds":
            continue
        for level in levels:
            params: dict[str, float] = {}
            if group == "beta":
                params["BETA_DEF"] = float(level)
                params["BETA_OVER"] = float(level) * 3.0
                sid = f"beta_{'m' if level < 0.5 else 'p'}{abs(level - 0.5) / 0.5 * 100:.0f}"
                label = f"β_def = {level:.2f} / β_over = {level * 3.0:.2f}（同比例）"
            else:
                for key in keys:
                    params[key] = float(level)
                sid = f"{group}_{level:g}".replace(".", "p")
                label = " / ".join(f"{key} = {float(level):g}" for key in keys)
            specs.append(
                _scenario(
                    sid,
                    "param",
                    label,
                    params=params,
                    oat_group=group,
                    oat_value=float(level),
                )
            )
    if chain == CHAIN_43:
        specs.append(
            _scenario(
                "kappa_bounds_wide",
                "param",
                "κ_m 截断界放宽到 [0.25, 4.0]（诊断：基准 [0.5,2.0] 实测截断 0 次）",
                kappa_bounds=(0.25, 4.0),
                oat_group="kappa_bounds",
                oat_value=0.0,
            )
        )
        specs.append(
            _scenario(
                "kappa_bounds_tight",
                "param",
                "κ_m 截断界收紧到 [0.75, 1.25]",
                kappa_bounds=(0.75, 1.25),
                oat_group="kappa_bounds",
                oat_value=1.0,
            )
        )

    # --- 预测机制（价格预报误差） ---
    for method in ("PF-DUAL", "PF-HIST"):
        specs.append(
            _scenario(
                f"predictor_{method.lower().replace('-', '_')}",
                "predictor",
                f"主预测器由 PF-PERSIST 换为 {method}",
                predictor=method,
            )
        )
    if chain == CHAIN_43:
        specs.append(
            _scenario(
                "kappa_frozen_1",
                "predictor",
                "κ_m ≡ 1：调整层不更新价格预测（AS11 / D6-C 的 robustness 侧对照）",
                kappa_frozen=True,
            )
        )

    # --- 输入扰动 ---
    for level in (0.9, 1.1):
        specs.append(
            _scenario(
                f"price_level_{'m' if level < 1 else 'p'}{abs(level - 1.0) * 100:.0f}",
                "input",
                f"价格序列整体 ×{level:g}（历史价与结算价同时缩放）",
                input={"price_level": level},
            )
        )
    for sigma in (0.05, 0.10):
        specs.append(
            _scenario(
                f"price_noise_w{int(sigma * 100)}",
                "input",
                f"价格序列逐时段乘性白噪声 σ = {sigma:.0%}（预测器历史与结算价同源）",
                input={"price_noise_sigma": sigma},
            )
        )
        specs.append(
            _scenario(
                f"load_noise_w{int(sigma * 100)}",
                "input",
                f"负载逐时段乘性白噪声 σ = {sigma:.0%}",
                input={"load_noise_sigma": sigma},
            )
        )
        specs.append(
            _scenario(
                f"pv_act_noise_w{int(sigma * 100)}",
                "input",
                f"附件 2 实际光伏逐时段乘性白噪声 σ = {sigma:.0%}",
                input={"pv_act_noise_sigma": sigma},
            )
        )
    if chain == CHAIN_43:
        for level in (0.9, 1.1):
            specs.append(
                _scenario(
                    f"pv_forecast_bias_{'m' if level < 1 else 'p'}{abs(level - 1.0) * 100:.0f}",
                    "input",
                    f"附件 3 降尺度预报 ×{level:g}（系统性偏差）",
                    input={"pv_fc_bias": level},
                )
            )
        for sigma in (0.10, 0.20):
            specs.append(
                _scenario(
                    f"pv_forecast_noise_w{int(sigma * 100)}",
                    "input",
                    f"附件 3 降尺度预报逐时段乘性白噪声 σ = {sigma:.0%}",
                    input={"pv_fc_noise_sigma": sigma},
                )
            )

    # --- 求解器压力 ---
    specs.append(
        _scenario("solver_highs_ds", "solver", "HiGHS dual simplex（method='highs-ds'）", solver={"method": "highs-ds"})
    )
    specs.append(
        _scenario("solver_highs_ipm", "solver", "HiGHS interior point（method='highs-ipm'）", solver={"method": "highs-ipm"})
    )
    specs.append(
        _scenario(
            "solver_highs_nopresolve",
            "solver",
            "HiGHS + presolve=False",
            solver={"method": "highs", "presolve": False},
        )
    )

    # --- 结构约束压力 ---
    specs.append(
        _scenario(
            "terminal_e_6000",
            "structural",
            "决策链末端储电量强制 = 6000 kWh（AS03 验证建议）",
            structural={"terminal_e_kwh": 6000.0},
        )
    )
    for cap_kw in BUY_CAP_KW:
        specs.append(
            _scenario(
                f"buy_cap_{cap_kw:g}kW".replace(".", "p"),
                "structural",
                f"决策层购电上限 {cap_kw:g} kW（逐时段上界 = cap·Δt）",
                structural={"buy_cap_kwh": float(cap_kw) * float(M.DELTA_T)},
                buy_cap_kw=float(cap_kw),
            )
        )
    return specs


def noise_scenarios(chain: str, samples: int, seed: int) -> list[dict[str, Any]]:
    families = list(NOISE_FAMILIES_COMMON) + (list(NOISE_FAMILIES_43) if chain == CHAIN_43 else [])
    specs: list[dict[str, Any]] = []
    for family in families:
        for index in range(samples):
            specs.append(
                _scenario(
                    f"{family}_{index + 1:03d}",
                    family,
                    f"{family} 样本 {index + 1}/{samples}",
                    noise={"family": family, "index": index, "seed": seed + index},
                )
            )
    return specs


# ---------------------------------------------------------------------------
# 汇总 / 敏感性 / 判据
# ---------------------------------------------------------------------------


def _ci95(values: np.ndarray, rng: np.random.Generator, bootstrap: int = 10000) -> dict[str, float]:
    values = np.asarray(values, dtype=float)
    n = int(values.size)
    if n == 0:
        return {
            "n": 0,
            "mean": float("nan"),
            "std": float("nan"),
            "median": float("nan"),
            "p05": float("nan"),
            "p95": float("nan"),
            "min": float("nan"),
            "max": float("nan"),
            "ci95_half_width_t": float("nan"),
            "ci95_half_width_bootstrap": float("nan"),
            "ci95_half_width_relative": float("nan"),
        }
    mean = float(np.mean(values))
    std = float(np.std(values, ddof=1)) if n > 1 else 0.0
    half_t = float(1.96 * std / np.sqrt(n)) if n > 1 else 0.0
    if n > 1:
        boots = rng.choice(values, size=(bootstrap, n), replace=True)
        means = np.mean(boots, axis=1)
        low, high = np.percentile(means, [2.5, 97.5])
        half_boot = float((high - low) / 2.0)
    else:
        half_boot = 0.0
    return {
        "n": n,
        "mean": _round(mean),
        "std": _round(std),
        "median": _round(float(np.median(values))),
        "p05": _round(float(np.percentile(values, 5))),
        "p95": _round(float(np.percentile(values, 95))),
        "min": _round(float(np.min(values))),
        "max": _round(float(np.max(values))),
        "ci95_half_width_t": _round(half_t),
        "ci95_half_width_bootstrap": _round(half_boot),
        "ci95_half_width_relative": _round(half_t / max(abs(mean), 1e-9), 9),
    }


def build_sensitivity(
    samples: list[dict[str, Any]],
    baseline_summary: dict[str, Any],
    *,
    chain: str,
    seed: int,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed + 1)
    base_total = float(baseline_summary["objective_yuan"])
    base_delivery = float(baseline_summary["delivery"]["cost_total_yuan"])
    ok_rows = [item for item in samples if item.get("ok")]

    def _row(item: dict[str, Any]) -> dict[str, Any]:
        summary = item["summary"]
        return {
            "scenario": item["scenario"],
            "family": item["family"],
            "group": family_group(item["family"]),
            "label": item["label"],
            "params": item.get("params") or {},
            "oat_group": item.get("oat_group"),
            "oat_value": item.get("oat_value"),
            "kappa_bounds": list(item["kappa_bounds"]) if item.get("kappa_bounds") else None,
            "predictor": item.get("predictor"),
            "input": summary.get("input") or {},
            "structural": item.get("structural") or {},
            "solver": item.get("solver") or {},
            "cost_total_yuan": summary["objective_yuan"],
            "delivery_cost_total_yuan": summary["delivery"]["cost_total_yuan"],
            "delta_cost_total_yuan": _round(summary["objective_yuan"] - base_total),
            "delta_relative": _round(summary["objective_yuan"] / base_total - 1.0, 9),
            "delta_delivery_relative": _round(summary["delivery"]["cost_total_yuan"] / max(abs(base_delivery), 1.0) - 1.0, 9),
            "delta_c_price_yuan": summary["delivery"]["delta_c_price_yuan"],
            "total_q_em_kwh": summary["totals"]["total_q_em_kwh"],
            "total_plan_kwh": summary["totals"]["total_plan_kwh"],
            "total_purchase_kwh": summary["totals"]["total_purchase_kwh"],
            "total_spill_kwh": summary["totals"]["total_spill_kwh"],
            "storage_final_kwh": summary["totals"]["storage_final_kwh"],
            "seconds": summary["seconds"],
        }

    def _slim(item: dict[str, Any]) -> dict[str, Any]:
        summary = item.get("summary") or {}
        return {
            "scenario": item["scenario"],
            "family": item["family"],
            "group": family_group(item["family"]),
            "label": item["label"],
            "ok": bool(item.get("ok")),
            "failure": item.get("failure"),
            "params": item.get("params") or {},
            "structural": item.get("structural") or {},
            "solver": item.get("solver") or {},
            "buy_cap_kw": item.get("buy_cap_kw"),
            "objective_yuan": summary.get("objective_yuan"),
            "delivery_cost_total_yuan": (summary.get("delivery") or {}).get("cost_total_yuan"),
            "delta_delivery_relative": (
                _round(
                    (summary.get("delivery") or {}).get("cost_total_yuan", 0.0) / max(abs(base_delivery), 1.0) - 1.0,
                    9,
                )
                if item.get("ok")
                else None
            ),
            "total_q_em_kwh": (summary.get("totals") or {}).get("total_q_em_kwh"),
            "storage_final_kwh": (summary.get("totals") or {}).get("storage_final_kwh"),
            "seconds": summary.get("seconds"),
        }

    param_rows = [_row(item) for item in ok_rows if family_group(item["family"]) == "param"]
    predictor_rows = [_row(item) for item in ok_rows if family_group(item["family"]) == "predictor"]
    input_rows = [_row(item) for item in ok_rows if family_group(item["family"]) == "input"]

    tornado: list[dict[str, Any]] = []
    for group in OAT_ORDER + ("kappa_bounds",):
        rows = [row for row in param_rows if row.get("oat_group") == group or _matches_oat(row, group)]
        if not rows:
            continue
        spread = max((abs(row["delta_cost_total_yuan"]) for row in rows), default=0.0)
        tornado.append(
            {
                "family": group,
                "label": group,
                "scenarios": [row["scenario"] for row in rows],
                "delta_min_yuan": _round(min(row["delta_cost_total_yuan"] for row in rows)),
                "delta_max_yuan": _round(max(row["delta_cost_total_yuan"] for row in rows)),
                "spread_abs_yuan": _round(spread),
                "spread_relative": _round(spread / max(abs(base_total), 1e-9), 9),
                "max_abs_relative": _round(max(abs(row["delta_relative"]) for row in rows), 9),
            }
        )
    tornado.sort(key=lambda item: item["spread_abs_yuan"], reverse=True)

    mechanism: list[dict[str, Any]] = []
    for group in ("param", "predictor", "input", "solver"):
        rows = [row for row in ok_rows if family_group(row["family"]) == group]
        if not rows:
            continue
        rels = [abs(row["summary"]["objective_yuan"] / base_total - 1.0) for row in rows]
        mechanism.append(
            {
                "group": group,
                "scenarios": len(rows),
                "max_abs_relative": _round(max(rels), 9),
                "mean_abs_relative": _round(float(np.mean(rels)), 9),
                "max_abs_delta_yuan": _round(
                    max(abs(row["summary"]["objective_yuan"] - base_total) for row in rows)
                ),
            }
        )

    families = list(NOISE_FAMILIES_COMMON) + (list(NOISE_FAMILIES_43) if chain == CHAIN_43 else [])
    noise_stats: dict[str, Any] = {}
    for family in families:
        rows = [item["summary"] for item in ok_rows if item["family"] == family]
        if not rows:
            continue
        totals = np.array([row["objective_yuan"] for row in rows], dtype=float)
        deliveries = np.array([row["delivery"]["cost_total_yuan"] for row in rows], dtype=float)
        q_em = np.array([row["totals"]["total_q_em_kwh"] for row in rows], dtype=float)
        entry = {
            "samples": len(rows),
            "cost_total": _ci95(totals, rng),
            "delivery_cost_total": _ci95(deliveries, rng),
            "total_q_em_kwh": _ci95(q_em, rng),
            "failures": [item["scenario"] for item in samples if item["family"] == family and not item.get("ok")],
        }
        mean = float(np.mean(deliveries))
        std = float(np.std(deliveries, ddof=1)) if deliveries.size > 1 else 0.0
        z = np.abs((deliveries - mean) / std) if std > 0 else np.zeros_like(deliveries)
        entry["delivery_max_abs_z"] = _round(float(np.max(z)))
        entry["delivery_std_relative"] = _round(std / max(abs(mean), 1e-9), 9)
        entry["delivery_mean_yuan"] = _round(mean)
        entry["delivery_mean_relative_vs_baseline"] = _round(mean / max(abs(base_delivery), 1e-9) - 1.0, 9)
        noise_stats[family] = entry

    structural_rows = [_slim(item) for item in samples if family_group(item["family"]) == "structural"]
    buy_cap = sorted(
        [row for row in structural_rows if row["buy_cap_kw"] is not None],
        key=lambda row: float(row["buy_cap_kw"]),
    )
    solver_rows = [_slim(item) for item in samples if family_group(item["family"]) == "solver"]

    return {
        "chain": chain,
        "baseline": {
            "objective_yuan": base_total,
            "delivery_cost_total_yuan": base_delivery,
            "total_q_em_kwh": baseline_summary["totals"]["total_q_em_kwh"],
        },
        "param_rows": param_rows,
        "predictor_rows": predictor_rows,
        "input_rows": input_rows,
        "tornado": tornado,
        "mechanism": mechanism,
        "noise": noise_stats,
        "structural": structural_rows,
        "buy_cap": buy_cap,
        "solver": solver_rows,
        "scenario_index": sorted(item["scenario"] for item in samples),
    }


def _matches_oat(row: dict[str, Any], group: str) -> bool:
    scenario = str(row["scenario"])
    if group in ("eta_both", "eta_ch", "eta_dis", "alpha_em", "e_init", "p_max", "e_min", "e_max"):
        return scenario.startswith(f"{group}_")
    if group == "beta":
        return scenario.startswith("beta_")
    if group == "kappa_bounds":
        return scenario.startswith("kappa_bounds_")
    return False


def _oat_rows(rows: list[dict[str, Any]], group: str) -> list[tuple[float, float, str]]:
    """把某 OAT 族的样本整理为 ``(参数档位, 费用, scenario)`` 升序列表。"""
    out: list[tuple[float, float, str]] = []
    for row in rows:
        if not _matches_oat(row, group):
            continue
        scenario = str(row["scenario"])
        value = float(row["summary"]["objective_yuan"])
        params = row.get("params") or {}
        if group == "kappa_bounds":
            level = 0.0 if scenario == "kappa_bounds_wide" else 1.0
        elif group == "beta":
            level = float(params["BETA_DEF"])
        else:
            key = OAT_SPEC[group][0][0]
            level = float(params[key])
        out.append((level, value, scenario))
    out.sort(key=lambda item: item[0])
    return out


def evaluate_criteria(
    samples: list[dict[str, Any]],
    sensitivity: dict[str, Any],
    baseline_summary: dict[str, Any],
    *,
    chain: str,
) -> dict[str, Any]:
    """S1–S7 判定 + ``stability_grade``。判据阈值在 ``plan.md`` 跑数前冻结。"""
    base_total = float(baseline_summary["objective_yuan"])
    base_delivery = float(baseline_summary["delivery"]["cost_total_yuan"])
    judged = [
        item
        for item in samples
        if item.get("ok")
        and family_group(item["family"]) in {"baseline", "param", "solver", "noise"}
    ]
    judged_all = [
        item
        for item in samples
        if family_group(item["family"]) in {"baseline", "param", "solver", "noise"}
    ]
    failed = [item for item in judged_all if not item.get("ok")]
    identity_failed = [item for item in judged if item.get("identity_failed")]
    feasible_rate = len(judged) / max(len(judged_all), 1)

    # ---- S1 ----
    s1_pass = bool(feasible_rate >= 1.0 and not identity_failed)
    s1 = {
        "pass": s1_pass,
        "rule": (
            "受判子集 {baseline, param, solver, noise} 的每层 LP status=0、层残差 ≤ 1e-6（相对 ≤1e-8）、"
            "界违反 ≤1e-6、结算/状态/跨日残差 ≤1e-6、费用分解残差 ≤1e-6；可行率 = 100% 且无恒等式失败"
        ),
        "detail": {
            "judged": len(judged_all),
            "solved": len(judged),
            "feasible_rate": _round(feasible_rate, 9),
            "failed_scenarios": [item["scenario"] for item in failed],
            "identity_failed_scenarios": [item["scenario"] for item in identity_failed],
        },
    }

    # ---- S2 ----
    if chain == CHAIN_42:
        worst_q_em = max((abs(item["summary"]["totals"]["total_q_em_kwh"]) for item in judged), default=0.0)
        worst_days = max((int(item["summary"]["totals"]["days_with_emergency"]) for item in judged), default=0)
        s2_pass = bool(worst_q_em <= INVARIANCE_BOUNDARY_TOL and worst_days == 0)
        s2_detail = {
            "chain": chain,
            "max_abs_total_q_em_kwh": _round(worst_q_em),
            "threshold_kwh": INVARIANCE_BOUNDARY_TOL,
            "max_days_with_emergency": worst_days,
            "note": "4-2 的 q_em ≡ 0 是 AS16 的定理级结论（等式平衡 + 自由处置）",
        }
    else:
        base_q_em = float(baseline_summary["totals"]["total_q_em_kwh"])
        values = [float(item["summary"]["totals"]["total_q_em_kwh"]) for item in judged]
        wide_low, wide_high = Q_EM_BAND_WIDE[0] * base_q_em, Q_EM_BAND_WIDE[1] * base_q_em
        narrow_low, narrow_high = Q_EM_BAND[0] * base_q_em, Q_EM_BAND[1] * base_q_em
        value_of = {item["scenario"]: float(item["summary"]["totals"]["total_q_em_kwh"]) for item in judged}
        out_of_band = [sid for sid, val in value_of.items() if not (wide_low <= val <= wide_high)]
        narrow_excursions = [
            {"scenario": sid, "family": item["family"], "total_q_em_kwh": _round(value_of[sid])}
            for item in judged
            for sid in [item["scenario"]]
            if not (narrow_low <= value_of[sid] <= narrow_high)
        ]
        s2_pass = bool(values and min(values) > 0 and not out_of_band)
        s2_detail = {
            "chain": chain,
            "baseline_total_q_em_kwh": _round(base_q_em),
            "band_kwh": [_round(wide_low), _round(wide_high)],
            "band_rule": "机制完好带 [0.25×, 4×]（CF-10：Σq_em 是 max(0,·) 泛函，σ=10% 输入扰动会系统性抬高它）",
            "min_total_q_em_kwh": _round(min(values)) if values else None,
            "max_total_q_em_kwh": _round(max(values)) if values else None,
            "out_of_band_scenarios": out_of_band,
            "narrow_band_kwh": [_round(narrow_low), _round(narrow_high)],
            "narrow_band_excursions": narrow_excursions,
            "note": "4-3 的 Σq_em > 0 由「决策层光伏预报 vs 结算层实际」缺口驱动，属统计与机制归因（承 prob03 C7/C8）",
        }
    s2 = {
        "pass": s2_pass,
        "rule": (
            "4-2：max|Σq_em| ≤ 1e-9 kWh 且 days_with_emergency = 0；"
            "4-3：Σq_em > 0 且落在基准的 [0.25×, 4×] 机制完好带内（窄带 [0.5×, 2×] 越界逐样本披露，见 CF-10）"
        ),
        "detail": s2_detail,
    }

    # ---- S3 ----
    s3_groups: list[dict[str, Any]] = []
    for group in OAT_ORDER + ("kappa_bounds",):
        if group == "beta" and chain != CHAIN_43:
            continue
        if group == "kappa_bounds" and chain != CHAIN_43:
            continue
        rows = _oat_rows(samples, group)
        if len(rows) < 2:
            continue
        direction = OAT_SPEC[group][2] if group in OAT_SPEC else 0
        if group == "kappa_bounds":
            direction = 0
        tol = 1e-6 * max(abs(base_total), 1.0)
        reversals: list[str] = []
        if direction != 0:
            for (_, value_a, sid_a), (_, value_b, sid_b) in zip(rows, rows[1:]):
                if direction > 0 and value_b > value_a + tol:
                    reversals.append(f"{sid_a}->{sid_b}")
                if direction < 0 and value_b < value_a - tol:
                    reversals.append(f"{sid_a}->{sid_b}")
        s3_groups.append(
            {
                "group": group,
                "direction": "参数上升 ⇒ 费用不增" if direction > 0 else ("参数上升 ⇒ 费用不降" if direction < 0 else "无方向预注册（诊断）"),
                "points": [{"scenario": sid, "level": level, "cost_total_yuan": value} for level, value, sid in rows],
                "reversals": reversals,
                "passed": not reversals if direction != 0 else None,
            }
        )
    s3_pass = bool(all(group["passed"] is not False for group in s3_groups))
    s3 = {
        "pass": s3_pass,
        "rule": "K3 的参数方向在 OAT 端点对上不反转（相对容差 1e-6·max(|C_base|,1)）",
        "detail": {"groups": s3_groups},
    }

    # ---- S4 ----
    families = list(sensitivity["noise"].keys())
    s4_bad: list[str] = []
    family_means: dict[str, float] = {}
    family_mean_vs_baseline: dict[str, float] = {}
    for family, entry in sensitivity["noise"].items():
        stats = entry["delivery_cost_total"]
        if entry["samples"] < 25:
            s4_bad.append(f"{family}:n<25")
        if entry["failures"]:
            s4_bad.append(f"{family}:failures={len(entry['failures'])}")
        if not np.isfinite(stats["std"]) or stats["ci95_half_width_relative"] > 0.05:
            s4_bad.append(f"{family}:ci95_relative={stats['ci95_half_width_relative']}")
        if entry["delivery_std_relative"] > 0.05:
            s4_bad.append(f"{family}:std_relative={entry['delivery_std_relative']}")
        if entry["delivery_max_abs_z"] > 4.0:
            s4_bad.append(f"{family}:max_abs_z={entry['delivery_max_abs_z']}")
        family_means[family] = float(entry["delivery_mean_yuan"])
        family_mean_vs_baseline[family] = float(entry["delivery_mean_relative_vs_baseline"])
        # CF-10：族间均值差只允许在**同一 σ 档**内比较（设计上 5% 与 10% 两档，跨档比较是范畴错误）；
        # 每个族另需**锚定基线**：均值相对基线 ≤ 5%。
        if abs(family_mean_vs_baseline[family]) > 0.05:
            s4_bad.append(f"{family}:mean_vs_baseline={family_mean_vs_baseline[family]}")
    sigma5_families = [name for name in families if "10" not in name]
    sigma5_means = [family_means[name] for name in sigma5_families if name in family_means]
    if len(sigma5_means) >= 2:
        spread = (max(sigma5_means) - min(sigma5_means)) / max(abs(np.mean(sigma5_means)), 1e-9)
        if spread > 0.03:
            s4_bad.append(f"family_mean_spread_sigma5={_round(spread, 6)}")
    else:
        spread = 0.0
    all_means = [value for value in family_means.values() if np.isfinite(value)]
    spread_all = (
        (max(all_means) - min(all_means)) / max(abs(np.mean(all_means)), 1e-9) if len(all_means) >= 2 else 0.0
    )
    s4 = {
        "pass": bool(not s4_bad),
        "rule": (
            "每个噪声族 n ≥ 25、交付期 C_total 相对标准差 ≤ 5%、95% CI 半宽 ≤ 5%、max|z| ≤ 4、无失败样本；"
            "每族均值相对基线 ≤ 5%；**同一 σ 档内**族间均值差 ≤ 3%（跨 σ 档只披露，见 CF-10）"
        ),
        "detail": {
            "families": families,
            "violations": s4_bad,
            "family_mean_relative_vs_baseline": {
                name: _round(value, 9) for name, value in family_mean_vs_baseline.items()
            },
            "family_mean_spread_sigma5_group": _round(spread, 9),
            "family_mean_spread_all_groups_disclosure": _round(spread_all, 9),
            "sigma5_families": sigma5_families,
        },
    }

    # ---- S5 ----
    solver_rows = sensitivity["solver"]
    solver_bad = [row["scenario"] for row in solver_rows if not row["ok"]]
    rels = [
        abs(float(row["objective_yuan"]) / base_total - 1.0)
        for row in solver_rows
        if row["ok"] and row["objective_yuan"] is not None
    ]
    solver_max_relative = max(rels) if rels else 0.0
    s5_pass = bool(solver_rows and not solver_bad and solver_max_relative <= 0.01)
    s5 = {
        "pass": s5_pass,
        "rule": "三种求解器设置全部可行且残差合格；链级费用最大相对差 ≤ 1%",
        "detail": {
            "scenarios": [row["scenario"] for row in solver_rows],
            "infeasible": solver_bad,
            "solver_max_relative": _round(solver_max_relative, 9),
            "t7_6_registered_relative": 1e-4,
        },
    }

    # ---- S6 ----
    buy_cap = sensitivity["buy_cap"]
    buy_cap_feasible = [row for row in buy_cap if row["ok"]]
    buy_cap_infeasible = [row for row in buy_cap if not row["ok"]]
    terminal_rows = [row for row in sensitivity["structural"] if row["scenario"] == "terminal_e_6000"]
    bracket: dict[str, Any] = {"feasible_kw": [row["buy_cap_kw"] for row in buy_cap_feasible]}
    if buy_cap_feasible and buy_cap_infeasible:
        bracket["bracket_kw"] = [
            max(row["buy_cap_kw"] for row in buy_cap_infeasible),
            min(row["buy_cap_kw"] for row in buy_cap_feasible),
        ]
    elif buy_cap_feasible:
        bracket["conclusion"] = "全域可行"
    elif buy_cap_infeasible:
        bracket["conclusion"] = "全域不可行"
    s6_pass = bool(buy_cap and terminal_rows and terminal_rows[0]["ok"])
    s6 = {
        "pass": s6_pass,
        "rule": "buy_cap 全档均产出状态并给出分链分界（或全域结论）；terminal_e_6000 产出数值",
        "detail": {
            "buy_cap_levels": len(buy_cap),
            "buy_cap_bracket": bracket,
            "buy_cap_infeasible": [row["buy_cap_kw"] for row in buy_cap_infeasible],
            "terminal_e_6000": terminal_rows[0] if terminal_rows else None,
            "note": "分链重新实测；不得引用 prob02 的 β ∈ (4218.75, 4375.00] kW 或 prob03 的 [4375.0, 5000.0] kW",
        },
    }

    # ---- S7 ----
    predictor_rows = sensitivity["predictor_rows"] + sensitivity["input_rows"]
    predictor_failures = [
        item["scenario"]
        for item in samples
        if family_group(item["family"]) in {"predictor", "input"} and not item.get("ok")
    ]
    backtest = sensitivity.get("backtest") or {}
    metrics_ok = _backtest_metrics_complete(backtest)
    s7_pass = bool(predictor_rows and not predictor_failures and metrics_ok)
    s7 = {
        "pass": s7_pass,
        "rule": "预测机制族（PF-DUAL/PF-HIST）与价格类输入扰动全部跑通并给出 ΔC_total；回测同时给出 MAE/MAPE/RMSE/bias/P50/P90/P99（E-F5）",
        "detail": {
            "scenarios": [row["scenario"] for row in predictor_rows],
            "failures": predictor_failures,
            "backtest_metrics_complete": metrics_ok,
        },
    }

    failed_criteria = [
        name
        for name, item in (("S1", s1), ("S2", s2), ("S3", s3), ("S4", s4), ("S5", s5), ("S6", s6), ("S7", s7))
        if not item["pass"]
    ]
    if "S1" in failed_criteria:
        grade = "脆弱（可行率或恒等式失败，须缩小适用范围）"
    elif not failed_criteria:
        grade = "稳定"
    elif len(failed_criteria) == 1:
        grade = "条件稳定（需给出适用边界）"
    else:
        grade = "脆弱（合理扰动导致多判据反转，须缩小适用范围）"
    return {
        "chain": chain,
        "S1": s1,
        "S2": s2,
        "S3": s3,
        "S4": s4,
        "S5": s5,
        "S6": s6,
        "S7": s7,
        "failed": failed_criteria,
        "stability_grade": grade,
        "baseline_delivery_cost_yuan": base_delivery,
        "delivery_magnitude_band_yuan": list(DELIVERY_BAND),
    }


def _backtest_metrics_complete(backtest: dict[str, Any]) -> bool:
    windows = (backtest or {}).get("windows") or {}
    needed = ("mae", "mape", "rmse", "bias", "p50", "p90", "p99")
    for window in ("D_req", "D_full"):
        metrics = ((windows.get(window) or {}).get("metrics")) or {}
        for method in ("PF-PERSIST", "PF-DUAL", "PF-HIST"):
            row = metrics.get(method) or {}
            if not all(key in row for key in needed):
                return False
    return True


# ---------------------------------------------------------------------------
# 基线闸门
# ---------------------------------------------------------------------------

_GATE_TOTALS = (
    # (闸门项名, reference 取值函数, summary 的 section, summary 的 key)
    ("D_full.objective_yuan", lambda m, s: s["objective_yuan"], None, "objective_yuan"),
    ("D_full.cost_plan_yuan", lambda m, s: s["cost_plan_yuan"], None, "cost_plan_yuan"),
    ("D_full.cost_adj_yuan", lambda m, s: s["cost_adj_yuan"], None, "cost_adj_yuan"),
    ("D_full.cost_em_yuan", lambda m, s: s["cost_em_yuan"], None, "cost_em_yuan"),
    ("D_full.total_plan_kwh", lambda m, s: s["totals"]["total_plan_kwh"], "totals", "total_plan_kwh"),
    ("D_full.total_purchase_kwh", lambda m, s: s["totals"]["total_purchase_kwh"], "totals", "total_purchase_kwh"),
    ("D_full.total_q_em_kwh", lambda m, s: s["totals"]["total_q_em_kwh"], "totals", "total_q_em_kwh"),
    ("D_full.total_spill_kwh", lambda m, s: s["totals"]["total_spill_kwh"], "totals", "total_spill_kwh"),
    ("D_full.storage_final_kwh", lambda m, s: s["totals"]["storage_final_kwh"], "totals", "storage_final_kwh"),
    ("D_req.cost_total_yuan", lambda m, s: m["delivery"]["cost_total_yuan"], "delivery", "cost_total_yuan"),
    ("D_req.cost_plan_yuan", lambda m, s: m["delivery"]["cost_plan_yuan"], "delivery", "cost_plan_yuan"),
    ("D_req.cost_adj_yuan", lambda m, s: m["delivery"]["cost_adj_yuan"], "delivery", "cost_adj_yuan"),
    ("D_req.cost_em_yuan", lambda m, s: m["delivery"]["cost_em_yuan"], "delivery", "cost_em_yuan"),
    ("D_req.total_plan_kwh", lambda m, s: m["delivery"]["total_plan_kwh"], "delivery", "total_plan_kwh"),
    ("D_req.total_purchase_kwh", lambda m, s: m["delivery"]["total_purchase_kwh"], "delivery", "total_purchase_kwh"),
    ("D_req.total_q_em_kwh", lambda m, s: m["delivery"]["total_q_em_kwh"], "delivery", "total_q_em_kwh"),
    ("D_req.total_charge_kwh", lambda m, s: m["delivery"]["total_charge_kwh"], "delivery", "total_charge_kwh"),
    ("D_req.total_spill_kwh", lambda m, s: m["delivery"]["total_spill_kwh"], "delivery", "total_spill_kwh"),
    ("D_req.storage_final_kwh", lambda m, s: m["delivery"]["storage_final_kwh"], "delivery", "storage_final_kwh"),
)


def _pick(summary: dict[str, Any], section: str | None, key: str) -> float:
    if section is None:
        return float(summary[key])
    return float(summary[section][key])


def check_baseline_gate(
    baseline: dict[str, Any],
    baseline_full: dict[str, Any] | None,
    reference_dir: Path,
) -> dict[str, Any]:
    """与 accepted ``run002`` 的基线复现闸门（只读；D_full 取 ``solution.json``、D_req 取 ``run_manifest.json``）。"""
    manifest = json.loads((reference_dir / "run_manifest.json").read_text(encoding="utf-8"))
    solution = json.loads((reference_dir / "solution.json").read_text(encoding="utf-8"))
    rows = []
    worst = 0.0
    for name, reference_getter, section, key in _GATE_TOTALS:
        reference = float(reference_getter(manifest, solution))
        value = _pick(baseline, section, key)
        relative = abs(value - reference) / max(abs(reference), 1.0)
        worst = max(worst, relative)
        rows.append(
            {
                "name": name,
                "value": _round(value),
                "reference": _round(reference),
                "relative_diff": _round(relative, 12),
            }
        )

    table_rows: list[dict[str, Any]] = []
    t7_rows: list[dict[str, Any]] = []
    tables_path = reference_dir / "tables.json"
    tiebreak_path = reference_dir / "tiebreak_audit.json"
    if baseline_full is not None and tables_path.exists():
        reference_tables = json.loads(tables_path.read_text(encoding="utf-8"))
        for date_text, _day_index in M.SPEC_DATES:
            if date_text not in reference_tables["table1"]:
                continue
            if date_text not in baseline_full["tables"]["table1"]:
                continue
            full_slots = {slot["slot"]: slot for slot in baseline_full["tables"]["table1"][date_text]["slots"]}
            for slot in reference_tables["table1"][date_text]["slots"]:
                full_slot = full_slots.get(slot["slot"])
                if full_slot is None:
                    continue
                table_rows.append(
                    {
                        "date": date_text,
                        "slot": slot["slot"],
                        "reference_kwh": slot["final_purchase_kwh"],
                        "full_mode_kwh": full_slot["final_purchase_kwh"],
                    }
                )
    if baseline_full is not None and tiebreak_path.exists():
        reference_t7 = json.loads(tiebreak_path.read_text(encoding="utf-8"))["summary"]
        for key in (
            "layers",
            "max_primary_relative_change",
            "lexicographic_committed_layers",
            "fallback_committed_layers",
            "degenerate_layers",
            "layers_with_remaining_multiplicity",
            "layers_with_unknown_multiplicity",
        ):
            t7_rows.append(
                {"key": key, "full_mode": baseline_full["summary"]["t7"].get(key), "reference": reference_t7.get(key)}
            )
    max_table_diff = max((abs(row["reference_kwh"] - row["full_mode_kwh"]) for row in table_rows), default=0.0)
    t7_mismatch = [
        row["key"]
        for row in t7_rows
        if row["full_mode"] is not None
        and row["reference"] is not None
        and abs(float(row["full_mode"]) - float(row["reference"])) > 1e-9 * max(abs(float(row["reference"])), 1.0)
    ]
    passed = bool(
        worst <= 1e-6
        and max_table_diff <= 1e-5
        and baseline_full is not None
        and bool(table_rows)
        and not t7_mismatch
    )
    return {
        "reference_dir": str(reference_dir.relative_to(ROOT)),
        "totals": rows,
        "worst_relative_diff": _round(worst, 12),
        "table1_rows": table_rows,
        "table1_max_abs_diff_kwh": _round(max_table_diff, 9),
        "t7_full_mode": t7_rows,
        "t7_mismatch_keys": t7_mismatch,
        "baseline_full_available": baseline_full is not None,
        "passed": passed,
        "rule": (
            "19 项总量（D_full 9 项取 solution.json、D_req 10 项取 run_manifest.json）相对差 ≤ 1e-6；"
            "表 1 四日期六时段最大绝对差 ≤ 1e-5 kWh；四段式 T7 审计与 run002 逐项一致；"
            "baseline_full 必须存在（否则闸门判失败）"
        ),
    }


# ---------------------------------------------------------------------------
# 图件（延迟导入 matplotlib；不走 record_figure_review）
# ---------------------------------------------------------------------------


def _select_font() -> str:
    from matplotlib import font_manager

    available = {font.name for font in font_manager.fontManager.ttflist}
    candidates = [
        "Microsoft YaHei",
        "PingFang SC",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "WenQuanYi Micro Hei",
        "SimHei",
        "Arial Unicode MS",
    ]
    for candidate in candidates:
        if candidate in available:
            return candidate
    raise RuntimeError("未找到任何可用中文字体，拒绝出图（避免方框字符）。")


def make_figures(
    output: Path,
    chain: str,
    sensitivity: dict[str, Any],
    baseline: dict[str, Any],
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = [_select_font(), "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 180
    figure_dir = output / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"robustness_prob04_{chain.replace('-', '')}_"
    created: list[str] = []
    base_delivery = float(sensitivity["baseline"]["delivery_cost_total_yuan"])

    def _save(fig: Any, name: str) -> None:
        path = figure_dir / f"{prefix}{name}.png"
        fig.tight_layout()
        fig.savefig(path)
        plt.close(fig)
        created.append(str(path))

    # 1) 龙卷
    tornado = sensitivity["tornado"]
    if tornado:
        fig, ax = plt.subplots(figsize=(10, 6))
        labels = [row["family"] for row in tornado][::-1]
        lows = [-row["spread_abs_yuan"] for row in tornado][::-1]
        highs = [row["spread_abs_yuan"] for row in tornado][::-1]
        ax.barh(labels, lows, color=PALETTE["primary"], label="负向扰动最大 |ΔC|")
        ax.barh(labels, highs, color=PALETTE["accent"], label="正向扰动最大 |ΔC|")
        ax.axvline(0.0, color=PALETTE["neutral"], linewidth=1.0)
        ax.set_xlabel("交付期 C_total 相对基线的最大偏差（元）")
        ax.set_title(f"prob04 链 {chain}：参数 OAT 龙卷图（spread = max|ΔC|）")
        ax.legend(loc="lower right")
        _save(fig, "tornado")

    # 2) 响应曲线
    groups = [row["family"] for row in tornado if row["family"] in OAT_ORDER][:6]
    if groups:
        fig, axes = plt.subplots(2, 3, figsize=(13, 7))
        rows = sensitivity["param_rows"]
        for ax, group in zip(axes.ravel(), groups):
            points = _oat_rows(
                [{"scenario": row["scenario"], "params": row["params"], "summary": {"objective_yuan": row["delivery_cost_total_yuan"]}} for row in rows],
                group,
            )
            if not points:
                ax.axis("off")
                continue
            x = [item[0] for item in points]
            y = [item[1] for item in points]
            ax.plot(x, y, marker="o", color=PALETTE["primary"])
            ax.axhline(base_delivery, color=PALETTE["neutral"], linestyle="--", linewidth=1.0)
            ax.set_title(group)
            ax.set_xlabel("参数取值")
            ax.set_ylabel("交付期 C_total（元）")
            ax.grid(alpha=0.25)
        for ax in axes.ravel()[len(groups):]:
            ax.axis("off")
        fig.suptitle(f"prob04 链 {chain}：单参数响应曲线（虚线 = 基线交付期费用）")
        _save(fig, "response_curves")

    # 3) 噪声 ECDF
    noise = sensitivity["noise"]
    rows = [item for item in sensitivity.get("noise_rows", [])]
    if noise and rows:
        fig, ax = plt.subplots(figsize=(10, 6))
        colors = [PALETTE["primary"], PALETTE["secondary"], PALETTE["accent"], PALETTE["warning"], PALETTE["neutral"]]
        for index, (family, entry) in enumerate(noise.items()):
            values = sorted(v for f, v in rows if f == family)
            if not values:
                continue
            array = np.asarray(values, dtype=float)
            ecdf = np.arange(1, array.size + 1) / array.size
            ax.step(array, ecdf, where="post", color=colors[index % len(colors)], label=f"{family}（n={entry['samples']}）")
        ax.axvline(base_delivery, color=PALETTE["neutral"], linestyle="--", linewidth=1.2, label="基线")
        ax.set_xlabel("交付期 C_total（元）")
        ax.set_ylabel("经验累积分布")
        ax.set_title(f"prob04 链 {chain}：输入噪声族的交付期费用 ECDF")
        ax.legend()
        ax.grid(alpha=0.25)
        _save(fig, "noise_ecdf")

    # 4) 购电上限扫掠
    buy_cap = sensitivity["buy_cap"]
    if buy_cap:
        fig, ax = plt.subplots(figsize=(10, 6))
        feasible = [(row["buy_cap_kw"], row["delivery_cost_total_yuan"]) for row in buy_cap if row["ok"]]
        infeasible = [row["buy_cap_kw"] for row in buy_cap if not row["ok"]]
        if feasible:
            ax.plot([p[0] for p in feasible], [p[1] for p in feasible], marker="o", color=PALETTE["primary"], label="可行")
        if infeasible:
            ax.plot(
                infeasible,
                [base_delivery] * len(infeasible),
                marker="x",
                linestyle="none",
                color=PALETTE["warning"],
                label="决策层不可行",
            )
        ax.axhline(base_delivery, color=PALETTE["neutral"], linestyle="--", linewidth=1.0)
        ax.set_xlabel("决策层购电上限（kW）")
        ax.set_ylabel("交付期 C_total（元）")
        ax.set_title(f"prob04 链 {chain}：购电上限扫掠（分链重新实测）")
        ax.legend()
        ax.grid(alpha=0.25)
        _save(fig, "buy_cap_curve")

    # 5) 情景箱线（参数 + 预测机制 + 输入三族）
    groups_for_box = [
        ("param", sensitivity["param_rows"]),
        ("predictor", sensitivity["predictor_rows"]),
        ("input", sensitivity["input_rows"]),
    ]
    box_values = [
        [row["delta_delivery_relative"] for row in rows]
        for _name, rows in groups_for_box
        if rows
    ]
    if box_values:
        fig, ax = plt.subplots(figsize=(10, 6))
        names = [name for name, rows in groups_for_box if rows]
        ax.boxplot(box_values, tick_labels=names, showmeans=True)
        ax.axhline(0.0, color=PALETTE["neutral"], linestyle="--", linewidth=1.0)
        ax.set_ylabel("交付期 C_total 相对变化")
        ax.set_title(f"prob04 链 {chain}：参数 / 预测机制 / 输入扰动的相对费用分布")
        ax.grid(alpha=0.25)
        _save(fig, "scenarios")

    # 6) spider
    if tornado:
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection="polar")
        labels = [row["family"] for row in tornado]
        values = [min(float(row["spread_relative"]), 1.0) for row in tornado]
        angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
        values_closed = values + values[:1]
        angles_closed = angles + angles[:1]
        ax.plot(angles_closed, values_closed, color=PALETTE["primary"])
        ax.fill(angles_closed, values_closed, color=PALETTE["primary"], alpha=0.25)
        ax.set_xticks(angles)
        ax.set_xticklabels(labels)
        ax.set_title(f"prob04 链 {chain}：参数敏感度雷达（spread_relative，截断到 1.0）")
        _save(fig, "spider")

    # 7) 机制级敏感性（参数 vs 预测机制 vs 输入 vs 求解器）
    mechanism = sensitivity["mechanism"]
    if mechanism:
        fig, ax = plt.subplots(figsize=(10, 6))
        names = [row["group"] for row in mechanism]
        max_rel = [row["max_abs_relative"] for row in mechanism]
        mean_rel = [row["mean_abs_relative"] for row in mechanism]
        x = np.arange(len(names))
        ax.bar(x - 0.2, max_rel, width=0.4, color=PALETTE["primary"], label="max |ΔC|/C_base")
        ax.bar(x + 0.2, mean_rel, width=0.4, color=PALETTE["accent"], label="mean |ΔC|/C_base")
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel("交付期/全期费用的相对偏差")
        ax.set_title(f"prob04 链 {chain}：机制级敏感性分组对照（K7/K8）")
        ax.legend()
        ax.grid(alpha=0.25)
        _save(fig, "mechanism_sensitivity")

    return created


# ---------------------------------------------------------------------------
# CLI / main
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="prob04 robustness 实验批（预注册见 ../plan.md）")
    parser.add_argument("--chain", choices=CHAINS, required=True, help="交付链：4-2 或 4-3（两链必须分别提交）")
    parser.add_argument("--data2", default="data/附件2.xlsx")
    parser.add_argument("--data3", default="data/附件3.xlsx")
    parser.add_argument("--data4", default="data/附件4.xlsx")
    parser.add_argument("--reference", default="", help="覆盖 accepted computation 产物目录（默认取 plan.md 登记值）")
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=SEED_DEFAULT)
    parser.add_argument("--samples", type=int, default=25, help="每个噪声族的样本数")
    parser.add_argument("--time-limit", type=float, default=30.0, help="单层 LP 的 HiGHS 时限（秒）")
    parser.add_argument("--days", type=int, default=DAYS_FULL)
    parser.add_argument("--mode", choices=("compact", "full"), default="compact")
    parser.add_argument("--families", default="all", help="all 或逗号分隔：param,predictor,input,solver,structural,noise")
    parser.add_argument("--scenarios", default="", help="逗号分隔的情景 id 白名单（仅用于探针）")
    parser.add_argument("--max-wall-seconds", type=float, default=6600.0)
    parser.add_argument("--probe", action="store_true", help="探针模式：只用于代码接口自检，产物不是交付证据")
    return parser.parse_args(argv)


def _assert_output_scope(output: Path, *, probe_mode: bool) -> None:
    """自证纪律：正式产物必须落在本版本 ``robustness/results`` 之下；任何模式都禁止写受保护路径。

    受保护路径：``data/``（原始附件与模板）、accepted ``code/``、以及 accepted 交付目录
    ``results/prob04_v001_f001_*``。探针（``--days < 365`` 或 ``--probe``）允许写 action evidence 等
    任意 ROOT 内路径，用于代码接口自检。
    """
    resolved = output.resolve()
    root = ROOT.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"--output 必须位于项目根目录内，收到 {output}") from exc
    parts = relative.parts
    if parts and parts[0] == "data":
        raise RuntimeError(f"禁止写入 data/（原始附件与模板只读）：{output}")
    if len(parts) >= 2 and parts[0] == "problems" and "code" in parts:
        raise RuntimeError(f"禁止写入 accepted code/ 目录：{output}")
    if "results" in parts and any(part.startswith("prob04_v001_f001") for part in parts):
        raise RuntimeError(f"禁止写入 accepted 交付目录 results/prob04_v001_f001_*：{output}")
    if probe_mode:
        return
    try:
        inside = resolved.relative_to(ROBUSTNESS_DIR.resolve())
    except ValueError as exc:
        raise RuntimeError(f"正式模式的 --output 必须位于 {ROBUSTNESS_DIR} 内，收到 {output}") from exc
    if "results" not in inside.parts:
        raise RuntimeError(f"正式模式的 --output 必须位于 robustness/results 之下，收到 {output}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not 2 <= args.days <= DAYS_FULL:
        log(f"--days 必须在 [2, {DAYS_FULL}]，收到 {args.days}")
        return EXIT_INPUT_INVALID
    output = (ROOT / args.output).resolve()
    probe_mode = args.days < DAYS_FULL or args.probe
    try:
        _assert_output_scope(output, probe_mode=probe_mode)
    except RuntimeError as exc:
        log(str(exc))
        return EXIT_INPUT_INVALID
    output.mkdir(parents=True, exist_ok=True)
    chain = str(args.chain)
    reference_dir = ROOT / (args.reference or REFERENCE_DIRS[chain])
    started = time.perf_counter()
    restore_defaults()

    try:
        base = build_base(args)
    except IO.InputValidationError as exc:
        log(f"输入校验失败：{exc}")
        return EXIT_INPUT_INVALID

    families = list(FAMILY_GROUPS) if args.families == "all" else [item.strip() for item in args.families.split(",") if item.strip()]
    scenarios = build_matrix_scenarios(chain)
    if "noise" in families:
        scenarios = scenarios + noise_scenarios(chain, args.samples, args.seed)
    scenarios = [
        spec
        for spec in scenarios
        if spec["group"] in families or spec["group"] == "baseline"
    ]
    if args.scenarios:
        wanted = {item.strip() for item in args.scenarios.split(",") if item.strip()}
        scenarios = [spec for spec in scenarios if spec["sid"] in wanted]
    if not scenarios:
        log("情景列表为空")
        return EXIT_INPUT_INVALID

    # 预测器滚动回测：与 accepted run_prob04 同口径，始终用**附件 4 全序列**与 D_full 天数
    # （探针窗口不截断回测，否则 D_req 窗口为空、roll_backtest 会 IndexError）。
    backtest = P.roll_backtest(np.asarray(base["attachment4"].price, dtype=float), days=DAYS_FULL)
    write_json(output / "forecast_backtest.json", backtest)
    template_labels = _template_labels(chain)

    run_manifest: dict[str, Any] = {
        "problem_id": "microgrid_2025",
        "question_id": "prob04",
        "stage": "robustness",
        "assumption_version": "assumption_v001",
        "formulation_version": "formulation_v001",
        "chain": chain,
        "model": "M4-2" if chain == CHAIN_42 else "M4-3",
        "mode": args.mode,
        "probe_mode": probe_mode,
        "days": args.days,
        "periods": args.days * PERIODS_PER_DAY,
        "seed": args.seed,
        "samples_per_noise_family": args.samples,
        "families": families,
        "scenario_count": len(scenarios),
        "scenario_ids": [spec["sid"] for spec in scenarios],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "outcome": "running",
        "reference_dir": str(reference_dir.relative_to(ROOT)),
        "tiebreak_rule": (
            "AS21（承 prob03 T7-1/T7-5）：提交解 = 主目标最优面上吞吐量最小的字典序解；"
            "compact 只跳过 T7 ② 字面加权式 / ④ 退化探测两个诊断环节"
        ),
        "output_directory": str(output.relative_to(ROOT)),
        "device": "cpu",
        "gpu_required": False,
        "input": {
            "attachment2": args.data2,
            "attachment3": args.data3 if chain == CHAIN_43 else None,
            "attachment4": args.data4,
            "attachment1_used": False,
            "md5": {
                "attachment2": base["attachment2"].md5,
                "attachment4": base["attachment4"].md5,
                "attachment3": base["attachment3"].md5 if base["attachment3"] is not None else None,
            },
        },
    }
    write_json(output / "run_manifest.json", run_manifest)

    raw_path = output / "raw_samples.jsonl"
    if raw_path.exists():
        raw_path.unlink()
    trajectories_dir = output / "trajectories"

    samples: list[dict[str, Any]] = []
    baseline_summary: dict[str, Any] | None = None
    baseline_full: dict[str, Any] | None = None
    budget_exceeded = False

    log(f"链 {chain}：情景数 {len(scenarios)}，模式 {args.mode}，天数 {args.days}，单层时限 {args.time_limit}s")
    for index, spec in enumerate(scenarios, 1):
        if time.perf_counter() - started > args.max_wall_seconds:
            budget_exceeded = True
            log(f"墙钟预算耗尽：已完成 {index - 1}/{len(scenarios)} 个情景")
            break
        try:
            outcome = run_scenario(
                spec,
                base,
                compact=args.mode == "compact",
                time_limit=args.time_limit,
                with_tables=spec["sid"] == "baseline_full",
                template_labels=template_labels,
            )
        except (M.LayerFailure, M.BudgetExceeded) as exc:
            record = {
                "scenario": spec["sid"],
                "family": spec["family"],
                "group": spec["group"],
                "label": spec["label"],
                "params": spec.get("params") or {},
                "predictor": spec.get("predictor"),
                "structural": spec.get("structural") or {},
                "solver": spec.get("solver") or {},
                "noise": spec.get("noise") or None,
                "input": spec.get("input") or {},
                "buy_cap_kw": spec.get("buy_cap_kw"),
                "ok": False,
                "failure": {
                    "type": "solver_not_optimal",
                    "status": int(getattr(exc, "status", -1)),
                    "message": str(exc)[:400],
                },
            }
            samples.append(record)
            append_jsonl(raw_path, record)
            log(f"[{index}/{len(scenarios)}] {spec['sid']} 不可行：{str(exc)[:120]}")
            continue
        except Exception as exc:  # noqa: BLE001 - 保留失败样本，不静默删除
            record = {
                "scenario": spec["sid"],
                "family": spec["family"],
                "group": spec["group"],
                "label": spec["label"],
                "params": spec.get("params") or {},
                "predictor": spec.get("predictor"),
                "structural": spec.get("structural") or {},
                "solver": spec.get("solver") or {},
                "noise": spec.get("noise") or None,
                "input": spec.get("input") or {},
                "buy_cap_kw": spec.get("buy_cap_kw"),
                "ok": False,
                "failure": {
                    "type": "exception",
                    "message": f"{type(exc).__name__}: {exc}"[:400],
                    "traceback": traceback.format_exc()[-1200:],
                },
            }
            samples.append(record)
            append_jsonl(raw_path, record)
            log(f"[{index}/{len(scenarios)}] {spec['sid']} 异常：{type(exc).__name__}: {str(exc)[:120]}")
            continue

        summary = outcome["summary"]
        identity_failed = check_subsample_identities(summary)
        record = {
            "scenario": spec["sid"],
            "family": spec["family"],
            "group": spec["group"],
            "label": spec["label"],
            "params": spec.get("params") or {},
            "predictor": spec.get("predictor"),
            "kappa_bounds": list(spec["kappa_bounds"]) if spec.get("kappa_bounds") else None,
            "kappa_frozen": bool(spec.get("kappa_frozen")),
            "structural": spec.get("structural") or {},
            "solver": spec.get("solver") or {},
            "noise": spec.get("noise") or None,
            "input": spec.get("input") or {},
            "buy_cap_kw": spec.get("buy_cap_kw"),
            "oat_group": spec.get("oat_group"),
            "oat_value": spec.get("oat_value"),
            "ok": True,
            "identity_failed": identity_failed,
            "summary": summary,
        }
        samples.append(record)
        append_jsonl(raw_path, record)
        if spec["sid"] == "baseline":
            baseline_summary = summary
        if spec["sid"] == "baseline_full":
            if outcome.get("tables") is None or outcome.get("metrics") is None:
                raise RuntimeError("baseline_full 未产出 tables/metrics（内部一致性错误）")
            baseline_full = {"summary": summary, "tables": outcome["tables"], "metrics": outcome["metrics"]}
        keep_trajectory = spec["group"] != "noise"
        if keep_trajectory:
            write_json(trajectories_dir / f"{spec['sid']}.json", _trajectory_payload(spec, summary))
        if index % 10 == 0 or spec["sid"] in {"baseline", "baseline_full"}:
            log(
                f"[{index}/{len(scenarios)}] {spec['sid']} 完成：全期 {summary['objective_yuan']:.2f} 元、"
                f"交付期 {summary['delivery']['cost_total_yuan']:.2f} 元、{summary['seconds']:.2f}s"
            )

    elapsed = time.perf_counter() - started
    if baseline_summary is None:
        write_json(
            output / "solver_status.json",
            {"chain": chain, "status": -1, "feasible_incumbent": False, "message": "baseline 未成功", "probe_mode": probe_mode},
        )
        write_json(output / "summary.json", {"chain": chain, "outcome": "baseline_failed", "wall_seconds": _round(elapsed, 6)})
        return EXIT_BASELINE_GATE_FAILED

    sensitivity = build_sensitivity(samples, baseline_summary, chain=chain, seed=args.seed)
    sensitivity["noise_rows"] = [
        (item["family"], item["summary"]["delivery"]["cost_total_yuan"])
        for item in samples
        if item.get("ok") and family_group(item["family"]) == "noise"
    ]
    sensitivity["backtest"] = backtest
    criteria = evaluate_criteria(samples, sensitivity, baseline_summary, chain=chain)
    baseline_check = check_baseline_gate(baseline_summary, baseline_full, reference_dir)
    write_json(output / "baseline_check.json", baseline_check)
    write_json(output / "sensitivity.json", sensitivity)

    solved = [item for item in samples if item.get("ok")]
    failures = [
        {
            "scenario": item["scenario"],
            "family": item["family"],
            "type": (item.get("failure") or {}).get("type"),
            "status": (item.get("failure") or {}).get("status"),
            "identity_failed": item.get("identity_failed") or [],
        }
        for item in samples
        if not item.get("ok") or item.get("identity_failed")
    ]
    structural_findings = {
        "buy_cap_feasibility_bracket_kw": criteria["S6"]["detail"]["buy_cap_bracket"],
        "buy_cap_infeasible_kw": criteria["S6"]["detail"]["buy_cap_infeasible"],
        "terminal_e_6000": criteria["S6"]["detail"]["terminal_e_6000"],
        "mechanism_sensitivity": sensitivity["mechanism"],
        "kappa_clip_events_total": int(
            sum(int(item["summary"]["statistics"]["kappa_clip_events"]) for item in solved)
        ),
    }
    figures: list[str] = []
    try:
        figures = make_figures(output, chain, sensitivity, baseline_summary)
    except Exception as exc:  # noqa: BLE001 - 出图失败不掩盖数值结论，但如实登记
        log(f"图件生成失败（数值结论不受影响）：{type(exc).__name__}: {exc}")

    write_json(
        output / "summary.json",
        {
            "chain": chain,
            "scenario_count": len(scenarios),
            "sample_count": len(samples),
            "solved_count": len(solved),
            "failed_count": len(samples) - len(solved),
            "failures": failures,
            "baseline": {
                "objective_yuan": baseline_summary["objective_yuan"],
                "delivery_cost_total_yuan": baseline_summary["delivery"]["cost_total_yuan"],
                "cost_plan_yuan": baseline_summary["cost_plan_yuan"],
                "cost_adj_yuan": baseline_summary["cost_adj_yuan"],
                "cost_em_yuan": baseline_summary["cost_em_yuan"],
                "total_q_em_kwh": baseline_summary["totals"]["total_q_em_kwh"],
                "t7": baseline_summary["t7"],
            },
            "criteria": criteria,
            "stability_grade": criteria["stability_grade"],
            "failed_criteria": criteria["failed"],
            "structural_findings": structural_findings,
            "figures": [Path(item).name for item in figures],
            "wall_seconds": _round(elapsed, 6),
            "budget_exceeded": budget_exceeded,
            "probe_mode": probe_mode,
            "max_local_concurrent_tasks_note": "CPU HiGHS，单 worker 串行；不占单卡 GPU 串行额度",
        },
    )
    write_json(
        output / "solver_status.json",
        {
            "chain": chain,
            "status": 0,
            "message": "robustness 实验批完成",
            "solver": "scipy.optimize.linprog(method='highs')",
            "feasible_incumbent": True,
            "baseline_check_passed": baseline_check["passed"],
            "probe_mode": probe_mode,
            "device": "cpu",
            "gpu_required": False,
            "seed": args.seed,
            "days": args.days,
            "scenario_count": len(scenarios),
            "solved_count": len(solved),
            "failed_count": len(samples) - len(solved),
            "lp_calls_total": int(sum(int(item["summary"]["lp_calls"]) for item in solved)),
            "layer_seconds_total": _round(sum(float(item["summary"]["layer_seconds_total"]) for item in solved), 6),
            "wall_seconds": _round(elapsed, 6),
            "budget_exceeded": budget_exceeded,
            "stability_grade": criteria["stability_grade"],
            "failed_criteria": criteria["failed"],
        },
    )

    manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    manifest.update(
        {
            "outcome": "budget_exceeded" if budget_exceeded else "completed",
            "solved_count": len(solved),
            "failed_count": len(samples) - len(solved),
            "wall_seconds": _round(elapsed, 6),
            "baseline_check_passed": baseline_check["passed"],
            "stability_grade": criteria["stability_grade"],
            "failed_criteria": criteria["failed"],
            "figures": [Path(item).name for item in figures],
            "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "assumption_code_sha256": {
                name: hashlib.sha256((ACCEPTED_CODE_DIR / f"{name}.py").read_bytes()).hexdigest()
                for name in ("prob04_io", "prob04_model", "prob04_predict", "run_prob04")
            },
        }
    )
    write_json(output / "run_manifest.json", manifest)

    log(
        f"链 {chain} 完成：{len(solved)}/{len(samples)} 情景成功，墙钟 {elapsed:.1f}s，"
        f"基线闸门 {'PASS' if baseline_check['passed'] else 'FAIL'}，分级 {criteria['stability_grade']}"
    )
    if not baseline_check["passed"]:
        return EXIT_BASELINE_GATE_FAILED
    if budget_exceeded:
        return EXIT_BUDGET_EXCEEDED
    return EXIT_OK


def _template_labels(chain: str) -> list[str]:
    path = ROOT / TEMPLATES[chain]
    info = IO.inspect_template42(path) if chain == CHAIN_42 else IO.inspect_template43(path)
    return info["measured"]["purchase"][IO.PLAN_SHEET]["labels"]


def _trajectory_payload(spec: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "scenario": spec["sid"],
        "family": spec["family"],
        "group": spec["group"],
        "label": spec["label"],
        "params": spec.get("params") or {},
        "predictor": spec.get("predictor"),
        "structural": spec.get("structural") or {},
        "solver": spec.get("solver") or {},
        "input": spec.get("input") or {},
        "noise": spec.get("noise") or None,
        "state_start_kwh": summary["statistics"]["state_start_kwh"],
        "state_end_kwh": summary["statistics"]["state_end_kwh"],
        "daily_plan_kwh": summary["daily_plan_kwh"],
        "daily_purchase_kwh": summary["daily_purchase_kwh"],
        "daily_q_em_kwh": summary["daily_q_em_kwh"],
        "daily_charge_kwh": summary["daily_charge_kwh"],
        "daily_discharge_kwh": summary["daily_discharge_kwh"],
        "daily_spill_kwh": summary["daily_spill_kwh"],
        "daily_cost_total_yuan": summary["daily_cost_total_yuan"],
        "daily_cost_total_fc_yuan": summary["daily_cost_total_fc_yuan"],
        "delivery": summary["delivery"],
        "totals": summary["totals"],
        "residuals": summary["residuals"],
        "t7": {key: summary["t7"][key] for key in ("layers", "probe_coverage", "lexicographic_committed_layers")},
        "seconds": summary["seconds"],
    }


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
