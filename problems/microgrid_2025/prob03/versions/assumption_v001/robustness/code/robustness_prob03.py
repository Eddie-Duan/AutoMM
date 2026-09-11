#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""prob03 robustness 实验批（预注册方案见 ``../plan.md``，跑数前冻结）。

对象：``assumption_v001`` / ``formulation_v001`` 的 accepted ``M1``（计划层 0:00 → 调整层
6:00/12:00/18:00 → 实际结算层，365 天 × 144 时段，跨日状态连续，终端自由），交付口径为
``results/prob03_v001_f001_run003``。

本实验**不修改 accepted 代码与数据**，而是通过只读导入 ``prob03_model`` / ``prob03_io`` /
``run_prob03``，在每次情景运行前用「模块级参数覆盖 + 输入扰动 + 求解器设置注入 +
结构约束注入」构造变体，并在运行后恢复。

纪律：
* 全部模型与全部 run 一律使用团队 T7-1/T7-5 的同一 tie-breaking 规则；``--mode compact`` 只跳过
  T7 的 ② 字面加权式与 ④ 退化探测两个**诊断**环节（提交解的定义仍为 ③ 字典序），并在
  ``baseline_full`` 情景用未修改的四段式与 ``run003`` 逐项对账；若 ``compact`` 与 ``full``
  的提交解不一致，``baseline_check`` 直接判失败。
* 失败样本**保留在 raw_samples.jsonl 并计入可行率**，不静默删除。
* 原始样本（jsonl + trajectories）与汇总统计（summary/sensitivity）分开保存。
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

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_INPUT_INVALID = 3
EXIT_BASELINE_GATE_FAILED = 4
EXIT_BUDGET_EXCEEDED = 5

SEED_DEFAULT = 20260911
SPEC_DATES = (("2025-03-20", 78), ("2025-06-21", 171), ("2025-09-23", 265), ("2025-12-21", 354))
NOISE_FAMILIES = ("noise_white_5", "noise_white_10", "noise_day_5", "noise_joint_day_5")
MATRIX_FAMILIES = ("param", "solver", "structural")


def family_group(family: str) -> str:
    """把具体噪声族归并到 ``noise`` 组，其余族名原样返回。"""
    return "noise" if family in NOISE_FAMILIES else family


def _project_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "AGENTS.md").exists():
            return candidate
    raise RuntimeError("无法从脚本位置定位项目根目录")


ROOT = _project_root()
VERSION_DIR = ROOT / "problems" / "microgrid_2025" / "prob03" / "versions" / "assumption_v001"
ACCEPTED_CODE_DIR = VERSION_DIR / "code"
ROBUSTNESS_DIR = VERSION_DIR / "robustness"
if str(ACCEPTED_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(ACCEPTED_CODE_DIR))

import prob03_io as IO  # noqa: E402
import prob03_model as M  # noqa: E402
import run_prob03 as R  # noqa: E402

_ORIGINAL_SOLVE_WITH_TIEBREAK = M._solve_with_tiebreak
_REAL_LINPROG = M.linprog

PALETTE = {
    "primary": "#1F4E79",
    "secondary": "#70AD47",
    "accent": "#ED7D31",
    "neutral": "#7F8C8D",
    "warning": "#C00000",
}
FONT_STACK = ["Microsoft YaHei", "SimHei", "DengXian", "SimSun", "DejaVu Sans"]


def log(message: str) -> None:
    print(f"[robust03] {message}", flush=True)


def _round(value: Any, digits: int = 6) -> float:
    number = float(value)
    if not np.isfinite(number):
        return float("nan")
    return round(number, digits)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")


# --------------------------------------------------------------------------------------
# 参数覆盖 / 求解器注入 / 结构约束注入
# --------------------------------------------------------------------------------------


def apply_overrides(overrides: dict[str, float]) -> None:
    """把情景参数写入 ``prob03_model`` 的模块级常量，并重算派生常量。"""
    for key, value in overrides.items():
        setattr(M, key, float(value))
    M.P_MAX = float(getattr(M, "P_MAX"))
    M.C_CAP = M.P_MAX * M.DELTA_T
    M.Q_CAP = M.P_MAX * M.DELTA_T * M.ETA_DIS
    M.ETA_ROUND_TRIP = M.ETA_CH * M.ETA_DIS


def restore_defaults() -> None:
    M.ETA_CH = 0.9
    M.ETA_DIS = 0.9
    M.E_INIT = 6000.0
    M.E_MIN = 1200.0
    M.E_MAX = 10800.0
    M.P_MAX = 5000.0
    M.ALPHA_EM = 5.0
    M.BETA_DEF = 0.5
    M.BETA_OVER = 1.5
    M.C_CAP = M.P_MAX * M.DELTA_T
    M.Q_CAP = M.P_MAX * M.DELTA_T * M.ETA_DIS
    M.ETA_ROUND_TRIP = M.ETA_CH * M.ETA_DIS


class SolverOverride:
    """覆盖 ``prob03_model.linprog`` 的 method/presolve（T7-5 允许的唯一差异面）。"""

    def __init__(self, *, method: str = "highs", presolve: bool = True) -> None:
        self.method = method
        self.presolve = presolve

    def install(self) -> None:
        real = _REAL_LINPROG

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            kwargs["method"] = self.method
            options = dict(kwargs.get("options") or {})
            options["presolve"] = bool(self.presolve)
            kwargs["options"] = options
            return real(*args, **kwargs)

        M.linprog = wrapper

    @staticmethod
    def uninstall() -> None:
        M.linprog = _REAL_LINPROG


def _compact_solve_with_tiebreak(
    *,
    primary_objective: np.ndarray,
    throughput_objective: np.ndarray,
    scale: float,
    a_eq: Any,
    b_eq: np.ndarray,
    a_ub: Any,
    b_ub: np.ndarray | None,
    bounds: np.ndarray,
    layer: str,
    day: int,
    hour: int,
    boundary_index: int,
    time_limit_seconds: float,
) -> tuple[Any, Any, Any]:
    """T7 提交解的紧凑实现：① 基线取 ``P*`` + ③ 主目标最优面上最小吞吐量。

    ② 字面加权式与 ④ 退化探测属**诊断**，不影响提交解；跳过它们把每层 LP 调用从 4 次降到 2 次。
    提交解与 ``prob03_model._solve_with_tiebreak`` 的 ③ 使用同一 ``tol_primary``、同一目标与约束，
    因此逐位同解；任一环节异常即回退到未修改的四段式（保守）。
    """
    from scipy.sparse import csr_matrix, vstack

    n_variables = int(primary_objective.shape[0])
    primary_row = np.asarray(primary_objective, dtype=float).reshape(1, -1)
    total_seconds = 0.0

    baseline_result, baseline_seconds = M._solve(
        primary_objective, a_eq, b_eq, a_ub, b_ub, bounds, time_limit_seconds=time_limit_seconds
    )
    total_seconds += baseline_seconds
    if baseline_result.x is None:
        return _ORIGINAL_SOLVE_WITH_TIEBREAK(
            primary_objective=primary_objective,
            throughput_objective=throughput_objective,
            scale=scale,
            a_eq=a_eq,
            b_eq=b_eq,
            a_ub=a_ub,
            b_ub=b_ub,
            bounds=bounds,
            layer=layer,
            day=day,
            hour=hour,
            boundary_index=boundary_index,
            time_limit_seconds=time_limit_seconds,
        )
    x_baseline = np.asarray(baseline_result.x, dtype=float)
    primary_before = float(np.dot(primary_objective, x_baseline))
    throughput_before = float(np.dot(throughput_objective, x_baseline))
    tol_primary = M.T7_FACE_PRIMARY_TOL_FRACTION * M.T7_INVARIANCE_TOL * max(abs(primary_before), 1.0)

    if a_ub is not None and a_ub.shape[0]:
        face_a_ub = vstack([a_ub, csr_matrix(primary_row)]).tocsr()
        face_b_ub = np.concatenate([np.asarray(b_ub, dtype=float), [primary_before + tol_primary]])
    else:
        face_a_ub = csr_matrix(primary_row)
        face_b_ub = np.array([primary_before + tol_primary])

    lex_result, lex_seconds = M._solve(
        throughput_objective, a_eq, b_eq, face_a_ub, face_b_ub, bounds,
        time_limit_seconds=time_limit_seconds,
    )
    total_seconds += lex_seconds
    if lex_result.x is None or int(lex_result.status) != 0:
        return _ORIGINAL_SOLVE_WITH_TIEBREAK(
            primary_objective=primary_objective,
            throughput_objective=throughput_objective,
            scale=scale,
            a_eq=a_eq,
            b_eq=b_eq,
            a_ub=a_ub,
            b_ub=b_ub,
            bounds=bounds,
            layer=layer,
            day=day,
            hour=hour,
            boundary_index=boundary_index,
            time_limit_seconds=time_limit_seconds,
        )

    x = np.asarray(lex_result.x, dtype=float)
    primary_after = float(np.dot(primary_objective, x))
    relative = abs(primary_after - primary_before) / max(abs(primary_before), 1.0)
    throughput = float(np.dot(throughput_objective, x))
    record = M._layer_record(
        lex_result,
        lex_seconds,
        day=day,
        hour=hour,
        a_eq=a_eq,
        b_eq=b_eq,
        a_ub=a_ub,
        b_ub=b_ub,
        bounds=bounds,
        objective=primary_after,
    )
    tiebreak = M.TiebreakRecord(
        layer=layer,
        day=day,
        hour=hour,
        primary_before_yuan=primary_before,
        primary_after_yuan=primary_after,
        primary_relative_change=relative,
        epsilon=M.tiebreak_epsilon(primary_before, scale),
        shrinks=0,
        invariance_passed=bool(relative <= M.T7_INVARIANCE_TOL),
        throughput_kwh=throughput,
        throughput_before_kwh=throughput_before,
        throughput_reduced_kwh=throughput_before - throughput,
        baseline_state_change_max_kwh=float(np.max(np.abs(x - x_baseline))),
        degeneracy_degree=-1,
        active_constraints=-1,
        variables=n_variables,
        weighted_primary_relative_change=float("nan"),
        weighted_throughput_kwh=float("nan"),
        weighted_sum_effective=False,
        committed_solution="lexicographic",
        throughput_upper_on_optimal_face_kwh=None,
        throughput_unique=None,
        probe_status=None,
        boundary_state_kwh=float(x[boundary_index]),
        baseline_seconds=baseline_seconds,
        solver_seconds=total_seconds,
        note="compact_mode: T7 ②/④ 诊断环节跳过，提交解 = ③ 字典序",
    )
    return lex_result, record, tiebreak


class TiebreakPatch:
    """把结构约束注入 ``bounds``，并按 ``compact`` 选择紧凑/完整四段式。"""

    def __init__(self, *, days: int, compact: bool, structural: dict[str, float] | None = None) -> None:
        self.days = days
        self.compact = compact
        self.structural = dict(structural or {})

    def __call__(self, **kwargs: Any) -> Any:
        bounds = np.array(kwargs["bounds"], dtype=float, copy=True)
        divisor = 7 if kwargs["layer"] == "adjustment" else 5
        n_periods = bounds.shape[0] // divisor
        cap_kwh = self.structural.get("buy_cap_kwh")
        if cap_kwh is not None:
            bounds[0:n_periods, 1] = np.minimum(bounds[0:n_periods, 1], float(cap_kwh))
        terminal = self.structural.get("terminal_e_kwh")
        if (
            terminal is not None
            and kwargs["layer"] == "adjustment"
            and int(kwargs["day"]) == self.days - 1
            and int(kwargs["hour"]) == 18
        ):
            bounds[int(kwargs["boundary_index"])] = np.array([float(terminal), float(terminal)])
        patched = dict(kwargs)
        patched["bounds"] = bounds
        if self.compact:
            return _compact_solve_with_tiebreak(**patched)
        return _ORIGINAL_SOLVE_WITH_TIEBREAK(**patched)


# --------------------------------------------------------------------------------------
# 情景定义
# --------------------------------------------------------------------------------------


def _pct(base: float, factor: float) -> float:
    return float(base * (1.0 + factor))


def build_matrix_scenarios() -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []

    def add(sid: str, family: str, label: str, *, params=None, solver=None, structural=None, noise=None) -> None:
        scenarios.append(
            {
                "sid": sid,
                "family": family,
                "label": label,
                "params": dict(params or {}),
                "solver": dict(solver or {}),
                "structural": dict(structural or {}),
                "noise": dict(noise or {}),
            }
        )

    add("baseline", "baseline", "基线（accepted 口径，默认参数）")
    add("baseline_full", "baseline", "基线（四段式完整 T7 审计，对账 run003）", structural={"full_tiebreak": 1.0})

    for factor in (-0.20, -0.10, -0.05, 0.05, 0.10, 0.20):
        value = _pct(0.9, factor)
        if value <= 0.0 or value > 1.0:
            continue
        add(
            f"eta_both_{value:.3f}",
            "param",
            f"η_ch = η_dis = {value:.4f}（{factor:+.0%}）",
            params={"ETA_CH": value, "ETA_DIS": value},
        )
    for factor in (-0.10, 0.10):
        add(f"eta_ch_{_pct(0.9, factor):.3f}", "param", f"η_ch = {_pct(0.9, factor):.4f}（η_dis 不变）",
            params={"ETA_CH": _pct(0.9, factor)})
        add(f"eta_dis_{_pct(0.9, factor):.3f}", "param", f"η_dis = {_pct(0.9, factor):.4f}（η_ch 不变）",
            params={"ETA_DIS": _pct(0.9, factor)})
    for factor in (-0.20, -0.10, -0.05, 0.05, 0.10, 0.20):
        add(f"alpha_em_{_pct(5.0, factor):.3f}", "param", f"α_em = {_pct(5.0, factor):.4f}（{factor:+.0%}）",
            params={"ALPHA_EM": _pct(5.0, factor)})
    for factor, tag in ((-0.20, "m20"), (-0.10, "m10"), (0.10, "p10"), (0.20, "p20")):
        add(
            f"beta_{tag}",
            "param",
            f"β_def/β_over = {_pct(0.5, factor):.3f}/{_pct(1.5, factor):.3f}（{factor:+.0%}）",
            params={"BETA_DEF": _pct(0.5, factor), "BETA_OVER": _pct(1.5, factor)},
        )
    for factor in (-0.20, -0.10, -0.05, 0.05, 0.10, 0.20):
        add(f"e_init_{_pct(6000.0, factor):.0f}", "param", f"E_init = {_pct(6000.0, factor):.1f} kWh（{factor:+.0%}）",
            params={"E_INIT": _pct(6000.0, factor)})
    for factor in (-0.20, -0.10, -0.05, 0.05, 0.10, 0.20):
        value = _pct(5000.0, factor)
        add(f"p_max_{value:.0f}", "param", f"P_max = {value:.1f} kW（{factor:+.0%}，C/Q 上限同步）",
            params={"P_MAX": value})
    for factor in (-0.20, -0.10, 0.10, 0.20):
        add(f"e_min_{_pct(1200.0, factor):.0f}", "param", f"E_min = {_pct(1200.0, factor):.1f} kWh（{factor:+.0%}）",
            params={"E_MIN": _pct(1200.0, factor)})
    for factor, value, note in (
        (-0.20, 8640.0, "-20%"),
        (-0.10, 9720.0, "-10%"),
        (0.10, 11880.0, "+10%"),
        (0.20, M.E_CAP_MAX, "+20% 截到登记上限 E_cap_max = 12000 kWh"),
    ):
        add(f"e_max_{value:.0f}", "param", f"E_max = {value:.1f} kWh（{note}）", params={"E_MAX": value})

    add("solver_highs_ds", "solver", "求解器 highs-ds（presolve=True）", solver={"method": "highs-ds"})
    add("solver_highs_ipm", "solver", "求解器 highs-ipm（presolve=True）", solver={"method": "highs-ipm"})
    add("solver_highs_nopresolve", "solver", "highs + presolve=False", solver={"method": "highs", "presolve": False})

    add("terminal_e_6000", "structural", "终端储电量 = 6000 kWh（AS04 验证建议的情景对照）",
        structural={"terminal_e_kwh": 6000.0})
    for cap_kw in (10326.0, 9000.0, 8000.0, 7500.0, 7000.0, 6500.0, 6000.0, 5000.0, 4375.0, 4218.75, 3500.0):
        add(
            f"buy_cap_{cap_kw:g}kW",
            "structural",
            f"购电上限 = {cap_kw:g} kW（决策层 q/b 上限，结构约束压力；R5 交叉验证）",
            structural={"buy_cap_kwh": cap_kw * M.DELTA_T},
        )
    return scenarios


def noise_scenarios(samples: int, seed: int) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    for family in NOISE_FAMILIES:
        for index in range(samples):
            scenarios.append(
                {
                    "sid": f"{family}_{index + 1:03d}",
                    "family": family,
                    "label": f"{family} 样本 {index + 1}/{samples}",
                    "params": {},
                    "solver": {},
                    "structural": {},
                    "noise": {"family": family, "index": index, "seed": seed + index},
                }
            )
    return scenarios


# --------------------------------------------------------------------------------------
# 输入构造与扰动
# --------------------------------------------------------------------------------------


def load_base_inputs(args: argparse.Namespace) -> dict[str, Any]:
    attachment1 = IO.read_attachment1(ROOT / args.data, expected_rows=144)
    attachment2 = IO.read_attachment2(ROOT / args.data2, expected_days=365, expected_periods=144)
    attachment3 = IO.read_attachment3(ROOT / args.data3, expected_days=365)
    if attachment3.dates != attachment2.dates:
        raise IO.InputValidationError("附件 3 与附件 2 的日期序列不一致")
    template_info = IO.inspect_template(ROOT / args.template)
    days = args.days
    forecast = {hour: np.vstack([M.downscale(attachment3.row(day, hour), hour) for day in range(days)])
                for hour in M.DECISION_HOURS}
    for hour in M.DECISION_HOURS:
        dominated = np.where(np.isfinite(forecast[hour][0]))[0]
        if not np.isfinite(forecast[hour][:, dominated]).all():
            raise IO.InputValidationError(f"降尺度预报在支配域含 NaN：hour={hour}")
    return {
        "days": days,
        "attachment1": attachment1,
        "attachment2": attachment2,
        "attachment3": attachment3,
        "template_info": template_info,
        "price": np.tile(attachment1.price, (days, 1)),
        "load_energy": attachment2.load_kw[:days] * M.DELTA_T,
        "pv_act_energy": attachment2.pv_kw[:days] * M.DELTA_T,
        "forecast_kw": forecast,
    }


def perturb(base: dict[str, Any], spec: dict[str, Any]) -> tuple[M.ChainInputs, dict[str, Any]]:
    """按情景噪声设置生成扰动输入（预报矩阵结构不变，只缩放射支配域内部的有限元）。"""
    price = np.array(base["price"], dtype=float, copy=True)
    load = np.array(base["load_energy"], dtype=float, copy=True)
    pv = np.array(base["pv_act_energy"], dtype=float, copy=True)
    days = base["days"]
    info: dict[str, Any] = {"noise": None}
    if spec.get("noise"):
        family = spec["noise"]["family"]
        rng = np.random.default_rng(int(spec["noise"]["seed"]))
        sigma = 0.10 if "10" in family else 0.05
        if family.startswith("noise_white"):
            load *= 1.0 + rng.normal(0.0, sigma, size=load.shape)
            pv *= 1.0 + rng.normal(0.0, sigma, size=pv.shape)
        elif family == "noise_day_5":
            load *= 1.0 + rng.normal(0.0, sigma, size=(days, 1))
            pv *= 1.0 + rng.normal(0.0, sigma, size=(days, 1))
        elif family == "noise_joint_day_5":
            load *= 1.0 + rng.normal(0.0, sigma, size=(days, 1))
            pv *= 1.0 + rng.normal(0.0, sigma, size=(days, 1))
            price *= 1.0 + rng.normal(0.0, sigma, size=(days, 1))
        else:
            raise ValueError(f"未知噪声族：{family}")
        np.clip(load, 0.0, None, out=load)
        np.clip(pv, 0.0, None, out=pv)
        np.clip(price, 1e-6, None, out=price)
        info["noise"] = {
            "family": family,
            "sigma": sigma,
            "load_mean_relative_shift": _round(float(np.mean(load) / np.mean(base["load_energy"]) - 1.0), 9),
            "pv_mean_relative_shift": _round(float(np.mean(pv) / np.mean(base["pv_act_energy"]) - 1.0), 9),
            "price_mean_relative_shift": _round(float(np.mean(price) / np.mean(base["price"]) - 1.0), 9),
        }
    chain = M.ChainInputs(
        days=days,
        price=price,
        load_energy=load,
        pv_act_energy=pv,
        forecast_kw=base["forecast_kw"],
    )
    return chain, info


# --------------------------------------------------------------------------------------
# 单情景汇总（不调用 M.evaluate，避免构造 52,560 点 series）
# --------------------------------------------------------------------------------------


def summarize(result: M.M1Result, *, seconds: float) -> dict[str, Any]:
    data = result.data
    days = result.days
    p = data.price
    load = data.load_energy
    pv = data.pv_act_energy
    b, q, c, qd = result.plan_b, result.q, result.c, result.q_dis
    qe, spill, E = result.q_em, result.s_settle, result.E
    starts = M.state_starts(result)
    ends = E[:, -1]
    dev_plus = np.maximum(b - q, 0.0)
    dev_minus = np.maximum(q - b, 0.0)
    cost_plan_d = np.sum(p * b, axis=1)
    cost_adj_d = np.sum(p * (M.BETA_DEF * dev_plus + M.BETA_OVER * dev_minus), axis=1)
    cost_em_d = np.sum(M.ALPHA_EM * p * qe, axis=1)
    total_d = cost_plan_d + cost_adj_d + cost_em_d
    start = M.DAILY_DELIVERY_START if days > M.DAILY_DELIVERY_START else 0
    delivery = slice(start, days)
    has_delivery = days > start

    settlement = np.abs(q + qe + pv + qd - load - c - spill)
    transition = np.abs(np.diff(np.concatenate([starts[:, None], E], axis=1), axis=1) - M.ETA_CH * c + qd / M.ETA_DIS)
    continuity = np.abs(starts[1:] - ends[:-1]) if days > 1 else np.zeros(0)
    records = result.layer_records
    t7 = result.tiebreak_records
    probed = [item for item in t7 if item.probe_status is not None]
    finite_rel = [item for item in t7 if np.isfinite(item.primary_relative_change)]
    same_period = int(np.sum((c > M.TOL) & (qd > M.TOL)))
    q_em_with_charge = int(np.sum((qe > M.TOL) & (c > M.TOL)))
    periods = days * M.PERIODS_PER_DAY

    return {
        "objective_yuan": _round(float(np.sum(total_d))),
        "cost_plan_yuan": _round(float(np.sum(cost_plan_d))),
        "cost_adj_yuan": _round(float(np.sum(cost_adj_d))),
        "cost_em_yuan": _round(float(np.sum(cost_em_d))),
        "delivery": {
            "days": int(days - start),
            "cost_total_yuan": _round(float(np.sum(total_d[delivery]))) if has_delivery else 0.0,
            "cost_plan_yuan": _round(float(np.sum(cost_plan_d[delivery]))) if has_delivery else 0.0,
            "cost_adj_yuan": _round(float(np.sum(cost_adj_d[delivery]))) if has_delivery else 0.0,
            "cost_em_yuan": _round(float(np.sum(cost_em_d[delivery]))) if has_delivery else 0.0,
            "total_plan_kwh": _round(float(np.sum(b[delivery]))) if has_delivery else 0.0,
            "total_purchase_kwh": _round(float(np.sum(q[delivery]))) if has_delivery else 0.0,
            "total_q_em_kwh": _round(float(np.sum(qe[delivery]))) if has_delivery else 0.0,
            "total_spill_kwh": _round(float(np.sum(spill[delivery]))) if has_delivery else 0.0,
            "total_charge_kwh": _round(float(np.sum(c[delivery]))) if has_delivery else 0.0,
            "total_discharge_kwh": _round(float(np.sum(qd[delivery]))) if has_delivery else 0.0,
            "storage_final_kwh": _round(float(ends[-1])) if has_delivery else 0.0,
        },
        "totals": {
            "total_plan_kwh": _round(float(np.sum(b))),
            "total_purchase_kwh": _round(float(np.sum(q))),
            "total_q_em_kwh": _round(float(np.sum(qe))),
            "total_spill_kwh": _round(float(np.sum(spill))),
            "total_charge_kwh": _round(float(np.sum(c))),
            "total_discharge_kwh": _round(float(np.sum(qd))),
            "net_load_kwh": _round(float(np.sum(load - pv))),
            "storage_initial_kwh": _round(float(starts[0])),
            "storage_final_kwh": _round(float(ends[-1])),
            "storage_min_kwh": _round(float(np.min(E))),
            "storage_max_kwh": _round(float(np.max(E))),
            "max_charge_kwh": _round(float(np.max(c))),
            "max_discharge_kwh": _round(float(np.max(qd))),
            "max_plan_purchase_kwh": _round(float(np.max(b))),
            "max_final_purchase_kwh": _round(float(np.max(q))),
        },
        "residuals": {
            "settlement_balance_max": _round(float(np.max(settlement)), 9),
            "state_transition_max": _round(float(np.max(transition)), 9),
            "cross_day_continuity_max": _round(float(np.max(continuity)) if continuity.size else 0.0, 9),
            "cost_decomposition_max": _round(
                float(np.max(np.abs(total_d - (cost_plan_d + cost_adj_d + cost_em_d)))), 9
            ),
            "layer_status_max": int(max((item.status for item in records), default=0)),
            "layer_equality_residual_max": _round(
                max((item.equality_residual_max for item in records), default=0.0), 9
            ),
            "layer_equality_residual_relative_max": _round(
                max((item.equality_residual_relative_max for item in records), default=0.0), 12
            ),
            "layer_inequality_residual_max": _round(
                max((item.inequality_residual_max for item in records), default=0.0), 9
            ),
            "layer_inequality_residual_relative_max": _round(
                max((item.inequality_residual_relative_max for item in records), default=0.0), 12
            ),
            "layer_bound_violation_max": _round(max((item.bound_violation_max for item in records), default=0.0), 9),
        },
        "statistics": {
            "periods": int(periods),
            "simultaneous_charge_discharge_periods": same_period,
            "periods_with_q_em_and_charge": q_em_with_charge,
            "periods_with_q_em_and_charge_ratio": _round(q_em_with_charge / max(periods, 1), 9),
            "periods_with_emergency": int(np.sum(qe > M.TOL)),
            "days_with_emergency": int(np.sum(np.any(qe > M.TOL, axis=1))),
            "days_with_deviation": int(np.sum(np.any((dev_plus > M.TOL) | (dev_minus > M.TOL), axis=1))),
            "q_eq_b_first_block_max": _round(float(np.max(np.abs(q[:, 0:36] - b[:, 0:36]))), 9),
            "max_side_power_kw": _round(
                float(np.max(np.maximum.reduce([c / M.DELTA_T, M.ETA_CH * c / M.DELTA_T,
                                                qd / M.DELTA_T, qd / (M.ETA_DIS * M.DELTA_T)]))), 6
            ),
        },
        "t7": {
            "layers": len(t7),
            "probe_coverage": _round(len(probed) / max(len(t7), 1), 9),
            "lexicographic_committed_layers": int(
                sum(1 for item in t7 if item.committed_solution == "lexicographic")
            ),
            "fallback_committed_layers": int(sum(1 for item in t7 if item.committed_solution != "lexicographic")),
            "max_primary_relative_change": _round(
                max((item.primary_relative_change for item in finite_rel), default=0.0), 12
            ),
            "all_layers_invariance_passed": bool(finite_rel) and all(item.invariance_passed for item in finite_rel),
            "throughput_kwh": _round(sum(item.throughput_kwh for item in t7 if np.isfinite(item.throughput_kwh))),
            "throughput_primary_only_kwh": _round(
                sum(item.throughput_before_kwh for item in t7 if np.isfinite(item.throughput_before_kwh))
            ),
            "degenerate_layers": int(sum(1 for item in probed if item.degeneracy_degree > 0)),
            "layers_with_remaining_multiplicity": int(sum(1 for item in probed if item.throughput_unique is False)),
            "layers_with_unknown_multiplicity": int(sum(1 for item in probed if item.throughput_unique is None)),
        },
        "daily_cost_total_yuan": [_round(v) for v in total_d],
        "seconds": _round(seconds, 6),
    }


def check_subsample_identities(summary: dict[str, Any]) -> list[str]:
    failed: list[str] = []
    res = summary["residuals"]
    if res["layer_status_max"] != 0:
        failed.append("layer_status_max")
    if res["layer_equality_residual_max"] > M.LAYER_TOL:
        failed.append("layer_equality_residual_max")
    if res["layer_equality_residual_relative_max"] > M.LAYER_TOL_RELATIVE:
        failed.append("layer_equality_residual_relative_max")
    if res["layer_inequality_residual_max"] > M.LAYER_TOL:
        failed.append("layer_inequality_residual_max")
    if res["layer_inequality_residual_relative_max"] > M.LAYER_TOL_RELATIVE:
        failed.append("layer_inequality_residual_relative_max")
    if res["layer_bound_violation_max"] > M.TOL:
        failed.append("layer_bound_violation_max")
    if res["settlement_balance_max"] > M.TOL:
        failed.append("settlement_balance_max")
    if res["state_transition_max"] > M.TOL:
        failed.append("state_transition_max")
    if res["cross_day_continuity_max"] > M.TOL:
        failed.append("cross_day_continuity_max")
    if abs(res["cost_decomposition_max"]) > M.TOL:
        failed.append("cost_decomposition_max")
    return failed


# --------------------------------------------------------------------------------------
# 情景执行
# --------------------------------------------------------------------------------------


def run_scenario(
    spec: dict[str, Any],
    base: dict[str, Any],
    *,
    compact: bool,
    time_limit: float,
) -> dict[str, Any]:
    apply_overrides(spec.get("params") or {})
    structural = dict(spec.get("structural") or {})
    force_full = bool(structural.pop("full_tiebreak", None))
    use_compact = compact and not force_full
    solver = spec.get("solver") or {}
    override = SolverOverride(method=solver.get("method", "highs"), presolve=solver.get("presolve", True))
    tiebreak_patch = TiebreakPatch(days=base["days"], compact=use_compact, structural=structural)
    override.install()
    M._solve_with_tiebreak = tiebreak_patch
    started = time.perf_counter()
    try:
        chain, noise_info = perturb(base, spec)
        result = M.run_m1(chain, time_limit_seconds=time_limit, deadline=None)
        seconds = time.perf_counter() - started
        summary = summarize(result, seconds=seconds)
        summary["noise"] = noise_info["noise"]
        return {"ok": True, "summary": summary, "result": result}
    finally:
        M._solve_with_tiebreak = _ORIGINAL_SOLVE_WITH_TIEBREAK
        SolverOverride.uninstall()
        restore_defaults()


def trajectory_payload(result: M.M1Result, spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "scenario": spec["sid"],
        "family": spec["family"],
        "label": spec["label"],
        "params": spec.get("params") or {},
        "structural": spec.get("structural") or {},
        "solver": spec.get("solver") or {},
        "state_start_kwh": [round(float(v), 6) for v in M.state_starts(result)],
        "state_end_kwh": [round(float(v), 6) for v in result.E[:, -1]],
        "daily_purchase_kwh": [round(float(v), 6) for v in np.sum(result.q, axis=1)],
        "daily_q_em_kwh": [round(float(v), 6) for v in np.sum(result.q_em, axis=1)],
        "daily_cost_plan_yuan": [round(float(v), 6) for v in np.sum(result.data.price * result.plan_b, axis=1)],
        "daily_charge_kwh": [round(float(v), 6) for v in np.sum(result.c, axis=1)],
        "daily_discharge_kwh": [round(float(v), 6) for v in np.sum(result.q_dis, axis=1)],
        "daily_spill_kwh": [round(float(v), 6) for v in np.sum(result.s_settle, axis=1)],
    }


# --------------------------------------------------------------------------------------
# 汇总、判据与图
# --------------------------------------------------------------------------------------


def _ci95(values: np.ndarray, rng: np.random.Generator, bootstrap: int = 10000) -> dict[str, float]:
    values = np.asarray(values, dtype=float)
    n = int(values.size)
    if n == 0:
        return {"n": 0, "mean": float("nan"), "std": float("nan"), "half_width_t": float("nan")}
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
    baseline: dict[str, Any],
    *,
    seed: int,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed + 1)
    base_total = baseline["objective_yuan"]
    base_delivery = baseline["delivery"]["cost_total_yuan"]
    by_sid = {item["scenario"]: item for item in samples if item.get("ok")}

    param_rows: list[dict[str, Any]] = []
    for item in samples:
        if item["family"] != "param" or not item.get("ok"):
            continue
        summary = item["summary"]
        param_rows.append(
            {
                "scenario": item["scenario"],
                "label": item["label"],
                "params": item["params"],
                "cost_total_yuan": summary["objective_yuan"],
                "delivery_cost_total_yuan": summary["delivery"]["cost_total_yuan"],
                "delta_cost_total_yuan": _round(summary["objective_yuan"] - base_total),
                "delta_relative": _round(summary["objective_yuan"] / base_total - 1.0, 9),
                "delta_delivery_relative": _round(summary["delivery"]["cost_total_yuan"] / base_delivery - 1.0, 9),
                "total_q_em_kwh": summary["totals"]["total_q_em_kwh"],
                "total_spill_kwh": summary["totals"]["total_spill_kwh"],
                "storage_final_kwh": summary["totals"]["storage_final_kwh"],
            }
        )

    tornado: list[dict[str, Any]] = []
    families = {
        "eta_both": ("η_ch=η_dis", lambda p: p.get("ETA_CH")),
        "eta_ch": ("η_ch", lambda p: p.get("ETA_CH")),
        "eta_dis": ("η_dis", lambda p: p.get("ETA_DIS")),
        "alpha_em": ("α_em", lambda p: p.get("ALPHA_EM")),
        "beta": ("β_def/β_over", lambda p: p.get("BETA_DEF")),
        "e_init": ("E_init", lambda p: p.get("E_INIT")),
        "p_max": ("P_max", lambda p: p.get("P_MAX")),
        "e_min": ("E_min", lambda p: p.get("E_MIN")),
        "e_max": ("E_max", lambda p: p.get("E_MAX")),
    }
    for key, (label, getter) in families.items():
        rows = [row for row in param_rows if len(row["params"]) and _matches_family(row["scenario"], key)]
        if not rows:
            continue
        lows = [row for row in rows if getter(row["params"]) is not None and getter(row["params"]) < _default_of(key)]
        highs = [row for row in rows if getter(row["params"]) is not None and getter(row["params"]) > _default_of(key)]
        spread = max([abs(row["delta_cost_total_yuan"]) for row in rows], default=0.0)
        tornado.append(
            {
                "family": key,
                "label": label,
                "default": _default_of(key),
                "scenarios": [row["scenario"] for row in rows],
                "delta_min_yuan": _round(min(row["delta_cost_total_yuan"] for row in rows)),
                "delta_max_yuan": _round(max(row["delta_cost_total_yuan"] for row in rows)),
                "spread_abs_yuan": _round(spread),
                "spread_relative": _round(spread / max(abs(base_total), 1e-9), 9),
                "low_side_max_abs_relative": _round(
                    max([abs(row["delta_relative"]) for row in lows], default=0.0), 9
                ),
                "high_side_max_abs_relative": _round(
                    max([abs(row["delta_relative"]) for row in highs], default=0.0), 9
                ),
            }
        )
    tornado.sort(key=lambda item: item["spread_abs_yuan"], reverse=True)

    noise_stats: dict[str, Any] = {}
    for family in NOISE_FAMILIES:
        rows = [item["summary"] for item in samples if item["family"] == family and item.get("ok")]
        if not rows:
            continue
        totals = np.array([row["objective_yuan"] for row in rows], dtype=float)
        deliveries = np.array([row["delivery"]["cost_total_yuan"] for row in rows], dtype=float)
        q_em = np.array([row["totals"]["total_q_em_kwh"] for row in rows], dtype=float)
        noise_stats[family] = {
            "samples": len(rows),
            "cost_total": _ci95(totals, rng),
            "delivery_cost_total": _ci95(deliveries, rng),
            "total_q_em_kwh": _ci95(q_em, rng),
            "failures": [item["scenario"] for item in samples if item["family"] == family and not item.get("ok")],
        }
        if rows:
            values = deliveries
            mean = float(np.mean(values))
            std = float(np.std(values, ddof=1)) if values.size > 1 else 0.0
            z = np.abs((values - mean) / std) if std > 0 else np.zeros_like(values)
            noise_stats[family]["delivery_max_abs_z"] = _round(float(np.max(z)))
            noise_stats[family]["delivery_std_relative"] = _round(std / max(abs(mean), 1e-9), 9)

    structural_rows: list[dict[str, Any]] = []
    for item in samples:
        if item["family"] != "structural":
            continue
        summary = item.get("summary") or {}
        structural_rows.append(
            {
                "scenario": item["scenario"],
                "label": item["label"],
                "structural": item.get("structural") or {},
                "ok": bool(item.get("ok")),
                "failure": item.get("failure"),
                "objective_yuan": summary.get("objective_yuan"),
                "delivery_cost_total_yuan": (summary.get("delivery") or {}).get("cost_total_yuan"),
                "delta_delivery_relative": (
                    _round((summary["delivery"]["cost_total_yuan"] / base_delivery - 1.0), 9)
                    if item.get("ok")
                    else None
                ),
                "total_q_em_kwh": (summary.get("totals") or {}).get("total_q_em_kwh"),
                "storage_final_kwh": (summary.get("totals") or {}).get("storage_final_kwh"),
            }
        )
    cap_rows = sorted(
        [row for row in structural_rows if "buy_cap_kwh" in (row["structural"] or {})],
        key=lambda row: row["structural"]["buy_cap_kwh"],
    )

    solver_rows = [
        {
            "scenario": item["scenario"],
            "label": item["label"],
            "ok": bool(item.get("ok")),
            "failure": item.get("failure"),
            "objective_yuan": (item.get("summary") or {}).get("objective_yuan"),
            "delta_relative": _round(
                ((item["summary"]["objective_yuan"] / base_total) - 1.0), 9
            ) if item.get("ok") else None,
            "total_q_em_kwh": ((item.get("summary") or {}).get("totals") or {}).get("total_q_em_kwh"),
        }
        for item in samples
        if item["family"] == "solver"
    ]

    return {
        "baseline": {
            "objective_yuan": base_total,
            "delivery_cost_total_yuan": base_delivery,
            "total_q_em_kwh": baseline["totals"]["total_q_em_kwh"],
        },
        "param_rows": param_rows,
        "tornado": tornado,
        "noise": noise_stats,
        "structural": structural_rows,
        "buy_cap": cap_rows,
        "solver": solver_rows,
        "scenario_index": sorted(by_sid.keys()),
    }


_DEFAULTS = {
    "eta_both": 0.9,
    "eta_ch": 0.9,
    "eta_dis": 0.9,
    "alpha_em": 5.0,
    "beta": 0.5,
    "e_init": 6000.0,
    "p_max": 5000.0,
    "e_min": 1200.0,
    "e_max": 10800.0,
}


def _default_of(key: str) -> float:
    return _DEFAULTS[key]


_PARAM_OF_FAMILY = {
    "eta_both": "ETA_CH",
    "eta_ch": "ETA_CH",
    "eta_dis": "ETA_DIS",
    "alpha_em": "ALPHA_EM",
    "beta": "BETA_DEF",
    "e_init": "E_INIT",
    "p_max": "P_MAX",
    "e_min": "E_MIN",
    "e_max": "E_MAX",
}


def _param_of(row: dict[str, Any], key: str) -> float:
    value = (row.get("params") or {}).get(_PARAM_OF_FAMILY[key])
    return float("nan") if value is None else float(value)


def _matches_family(sid: str, key: str) -> bool:
    if key == "beta":
        return sid.startswith("beta_")
    prefix = {
        "eta_both": "eta_both_",
        "eta_ch": "eta_ch_",
        "eta_dis": "eta_dis_",
        "alpha_em": "alpha_em_",
        "e_init": "e_init_",
        "p_max": "p_max_",
        "e_min": "e_min_",
        "e_max": "e_max_",
    }[key]
    return sid.startswith(prefix)


def evaluate_criteria(
    samples: list[dict[str, Any]],
    sensitivity: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    """预注册判据 S1–S6（阈值见 plan.md，跑数前冻结）。"""
    judged = [item for item in samples if family_group(item["family"]) in ("baseline", "param", "solver", "noise")]
    judged_ok = [item for item in judged if item.get("ok")]
    failures = [item for item in judged if not item.get("ok")]
    feasible_rate = len(judged_ok) / max(len(judged), 1)
    base_total = baseline["objective_yuan"]
    base_delivery = baseline["delivery"]["cost_total_yuan"]

    s1_detail: dict[str, Any] = {
        "judged_samples": len(judged),
        "feasible_samples": len(judged_ok),
        "feasible_rate": _round(feasible_rate, 9),
        "failed_samples": [{"scenario": item["scenario"], "failure": item.get("failure")} for item in failures],
        "identity_failed_samples": [
            {"scenario": item["scenario"], "failed": item.get("identity_failed")}
            for item in judged_ok
            if item.get("identity_failed")
        ],
    }
    s1_pass = feasible_rate >= 1.0 and not s1_detail["identity_failed_samples"]

    s2_rows: list[dict[str, Any]] = []
    for item in judged_ok:
        summary = item["summary"]
        totals = summary["totals"]
        stats = summary["statistics"]
        s2_rows.append(
            {
                "scenario": item["scenario"],
                "total_q_em_positive": totals["total_q_em_kwh"] > 0.0,
                "q_eq_b_first_block_max": stats["q_eq_b_first_block_max"],
                "simultaneous_periods": stats["simultaneous_charge_discharge_periods"],
                "delivery_cost_in_band": 3.0e6 <= summary["delivery"]["cost_total_yuan"] <= 5.0e7,
                "q_em_charge_ratio": stats["periods_with_q_em_and_charge_ratio"],
            }
        )
    s2_bad = [
        row["scenario"]
        for row in s2_rows
        if not row["total_q_em_positive"]
        or row["q_eq_b_first_block_max"] > 1e-6
        or row["simultaneous_periods"] != 0
        or not row["delivery_cost_in_band"]
        or row["q_em_charge_ratio"] > 0.15
    ]
    s2_detail = {"rows": len(s2_rows), "violations": s2_bad, "max_q_em_charge_ratio": _round(
        max([row["q_em_charge_ratio"] for row in s2_rows], default=0.0), 9)}
    s2_pass = not s2_bad and len(s2_rows) == len(judged)

    monotone_specs = [
        ("eta_both", "up_total_not_up", "η 上升 ⇒ C_total 不上升"),
        ("alpha_em", "up_total_not_down", "α_em 上升 ⇒ C_total 不下降"),
        ("p_max", "up_total_not_up", "P_max 上升 ⇒ C_total 不上升"),
        ("e_min", "up_total_not_down", "E_min 上升（收紧）⇒ C_total 不下降"),
        ("e_max", "up_total_not_up", "E_max 上升（放松）⇒ C_total 不上升"),
        ("beta", "up_total_not_down", "β_def/β_over 上升 ⇒ C_total 不下降"),
    ]
    s3_rows: list[dict[str, Any]] = []
    for key, direction, note in monotone_specs:
        rows = [row for row in sensitivity["param_rows"] if _matches_family(row["scenario"], key)]
        ordered = sorted(rows, key=lambda row: _param_of(row, key))
        if len(ordered) < 2:
            continue
        costs = [row["cost_total_yuan"] for row in ordered]
        tol = 1e-6 * max(abs(base_total), 1.0)
        reversed_at = []
        for left, right in zip(costs, costs[1:]):
            if direction == "up_total_not_up" and right > left + tol:
                reversed_at.append([_round(left), _round(right)])
            if direction == "up_total_not_down" and right < left - tol:
                reversed_at.append([_round(left), _round(right)])
        s3_rows.append(
            {
                "family": key,
                "note": note,
                "levels": [_param_of(row, key) for row in ordered],
                "costs": costs,
                "violations": reversed_at,
            }
        )
    s3_bad = [row["family"] for row in s3_rows if row["violations"]]
    s3_pass = not s3_bad and bool(s3_rows)
    s3_detail = {"rows": s3_rows, "violations": s3_bad}

    s4_rows: dict[str, Any] = {}
    for family, stats in sensitivity["noise"].items():
        delivery = stats["delivery_cost_total"]
        s4_rows[family] = {
            "n": delivery["n"],
            "std_relative_delivery": stats.get("delivery_std_relative"),
            "ci95_half_width_relative": delivery["ci95_half_width_relative"],
            "max_abs_z": stats.get("delivery_max_abs_z"),
            "failures": stats["failures"],
        }
    s4_bad: list[str] = []
    means = []
    for family, row in s4_rows.items():
        if row["n"] < 25:
            s4_bad.append(f"{family}:n<25")
        if (row["std_relative_delivery"] or 0.0) > 0.05:
            s4_bad.append(f"{family}:std>5%")
        if (row["ci95_half_width_relative"] or 0.0) > 0.05:
            s4_bad.append(f"{family}:ci>5%")
        if (row["max_abs_z"] or 0.0) > 4.0:
            s4_bad.append(f"{family}:|z|>4")
        if row["failures"]:
            s4_bad.append(f"{family}:failures")
        means.append(sensitivity["noise"][family]["delivery_cost_total"]["mean"])
    family_spread = (max(means) - min(means)) / max(abs(base_delivery), 1e-9) if means else 0.0
    if family_spread > 0.03:
        s4_bad.append("inter_family_mean_spread>3%")
    s4_pass = not s4_bad

    solver_rows = sensitivity["solver"]
    solver_bad = [row["scenario"] for row in solver_rows if not row["ok"]]
    solver_deltas = [abs(row["delta_relative"]) for row in solver_rows
                     if row["ok"] and row["delta_relative"] is not None]
    solver_max_relative = max(solver_deltas, default=0.0)
    s5_pass = not solver_bad and solver_max_relative <= 0.01
    s5_detail = {
        "rows": solver_rows,
        "feasibility_violations": solver_bad,
        "max_abs_relative_diff": _round(solver_max_relative, 9),
        "t7_6_registered_relative": 2.2566e-4,
        "note": (
            "求解器设置（highs-ds / highs-ipm / presolve=False）的链级费用差异经 LP 最优面选择与跨日初值"
            "传播放大，属团队 T7-6 已登记的口径敏感性（非实现缺陷）；仅当任一设置不可行或相对差 > 1% 才判脆弱。"
        ),
    }

    cap_feasible = [row for row in sensitivity["buy_cap"] if row["ok"]]
    cap_infeasible = [row for row in sensitivity["buy_cap"] if not row["ok"]]
    bracket = None
    if cap_infeasible and cap_feasible:
        lowest_feasible = min(row["structural"]["buy_cap_kwh"] for row in cap_feasible)
        highest_infeasible = max(row["structural"]["buy_cap_kwh"] for row in cap_infeasible)
        bracket = [_round(highest_infeasible / M.DELTA_T, 6), _round(lowest_feasible / M.DELTA_T, 6)]
    terminal = [row for row in sensitivity["structural"] if row["scenario"] == "terminal_e_6000"]
    s6_detail = {
        "buy_cap_rows": sensitivity["buy_cap"],
        "buy_cap_feasibility_bracket_kw": bracket,
        "prob02_R5_beta_bracket_kw": [4218.75, 4375.0],
        "terminal_e_6000": terminal[0] if terminal else None,
    }
    s6_notes: list[str] = []
    if not sensitivity["buy_cap"]:
        s6_notes.append("购电上限情景为空，未产出结构压力数值")
    elif bracket is None:
        if all(row["ok"] for row in sensitivity["buy_cap"]):
            s6_notes.append("购电上限扫掠全档可行（未出现绑定/不可行分界）")
        else:
            s6_notes.append("购电上限扫掠全档决策层不可行（分界高于最高档）")
    if bracket is not None and not (bracket[0] <= 4375.0 and bracket[1] >= 4218.75):
        s6_notes.append("购电上限夹逼区间与 prob02 勘误 R5 的 β∈(4218.75, 4375.00] kW 不一致，登记冲突点")
    if terminal and terminal[0]["delta_delivery_relative"] is not None:
        if abs(terminal[0]["delta_delivery_relative"]) > 0.01:
            s6_notes.append("终端 = 6000 情景的交付期费用相对变化 > 1%，须在论文中作为结构性发现披露")
    s6_pass = bool(sensitivity["buy_cap"]) and bool(terminal)

    criteria = {
        "S1": {"pass": s1_pass, "rule": "全部受判样本求解最优、四条恒等式与层残差在容差内、可行率 = 100%",
               "detail": s1_detail},
        "S2": {"pass": s2_pass,
               "rule": "受判样本全部满足 Σq_em>0、q=b(i≤36)、同充放 0、交付期费用 10^7 量级带、q_em&c 占比 ≤15%",
               "detail": s2_detail},
        "S3": {"pass": s3_pass, "rule": "六组 OAT 单调方向不反转（相对容差 1e-6）", "detail": s3_detail},
        "S4": {"pass": s4_pass, "rule": "噪声族 n≥25、std≤5%、95%CI 半宽≤5%、|z|≤4、族间均值差≤3%、无失败样本",
               "detail": {"families": s4_rows, "violations": s4_bad}},
        "S5": {"pass": s5_pass,
               "rule": "三种求解器设置全部可行且残差合格；链级费用最大相对差 ≤1%"
                       "（T7-6 口径敏感性，>1e-3 登记 warning）",
               "detail": s5_detail},
        "S6": {"pass": s6_pass, "rule": "购电上限情景给出夹逼区间；终端情景如实登记", "detail": s6_detail,
               "notes": s6_notes},
    }
    failed = [key for key, value in criteria.items() if not value["pass"]]
    if not failed:
        grade = "稳定"
    elif "S1" in failed:
        grade = "脆弱（可行率或恒等式失败，须缩小适用范围）"
    elif len(failed) == 1:
        grade = "条件稳定（需给出适用边界）"
    else:
        grade = "脆弱（合理扰动导致多判据反转，须缩小适用范围）"
    criteria["failed"] = failed
    criteria["stability_grade"] = grade
    return criteria


# --------------------------------------------------------------------------------------
# 图
# --------------------------------------------------------------------------------------


def make_figures(output: Path, samples: list[dict[str, Any]], sensitivity: dict[str, Any],
                 baseline: dict[str, Any], seed: int) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = FONT_STACK
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 180
    figure_dir = output / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    base_total = baseline["objective_yuan"]

    # 1) tornado
    tornado = sensitivity["tornado"]
    if tornado:
        labels = [item["label"] for item in tornado][::-1]
        lows = [(item["delta_min_yuan"] or 0.0) for item in tornado][::-1]
        highs = [(item["delta_max_yuan"] or 0.0) for item in tornado][::-1]
        fig, ax = plt.subplots(figsize=(10, 6))
        ypos = np.arange(len(labels))
        ax.barh(ypos, lows, color=PALETTE["primary"], label="负向扰动最大 ΔC")
        ax.barh(ypos, highs, color=PALETTE["accent"], label="正向扰动最大 ΔC")
        ax.set_yticks(ypos)
        ax.set_yticklabels(labels)
        ax.axvline(0.0, color=PALETTE["neutral"], linewidth=0.8)
        ax.set_xlabel("全期 C_total 相对基线变化（元）")
        ax.set_title("prob03 robustness：参数 OAT 龙卷图（基线 %.3e 元）" % base_total)
        ax.legend(loc="lower right")
        ax.grid(axis="x", alpha=0.3)
        path = figure_dir / "robustness_prob03_tornado.png"
        fig.tight_layout()
        fig.savefig(path)
        plt.close(fig)
        created.append(str(path))

    # 2) 参数响应曲线
    rows = sensitivity["param_rows"]
    panels = [
        ("eta_both", "η_ch = η_dis", lambda p: p.get("ETA_CH")),
        ("alpha_em", "α_em", lambda p: p.get("ALPHA_EM")),
        ("p_max", "P_max (kW)", lambda p: p.get("P_MAX")),
        ("e_init", "E_init (kWh)", lambda p: p.get("E_INIT")),
        ("e_min", "E_min (kWh)", lambda p: p.get("E_MIN")),
        ("e_max", "E_max (kWh)", lambda p: p.get("E_MAX")),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    for ax, (key, xlabel, getter) in zip(axes.reshape(-1), panels):
        subset = [row for row in rows if _matches_family(row["scenario"], key)]
        subset = [row for row in subset if getter(row["params"]) is not None]
        subset.sort(key=lambda row: getter(row["params"]))
        if subset:
            ax.plot([getter(row["params"]) for row in subset],
                    [row["delivery_cost_total_yuan"] for row in subset],
                    marker="o", color=PALETTE["primary"])
        ax.axhline(baseline["delivery"]["cost_total_yuan"], color=PALETTE["neutral"],
                   linestyle="--", linewidth=0.9)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("交付期 C_total（元）")
        ax.grid(alpha=0.3)
    fig.suptitle("prob03 robustness：单参数响应曲线（虚线 = 基线）")
    path = figure_dir / "robustness_prob03_response_curves.png"
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    created.append(str(path))

    # 3) 噪声 ECDF
    fig, ax = plt.subplots(figsize=(10, 6))
    for index, (family, stats) in enumerate(sensitivity["noise"].items()):
        values = stats["delivery_cost_total"]
        rows_family = [item["summary"]["delivery"]["cost_total_yuan"] for item in samples
                       if item["family"] == family and item.get("ok")]
        if not rows_family:
            continue
        ordered = np.sort(np.asarray(rows_family, dtype=float))
        ecdf = np.arange(1, ordered.size + 1) / ordered.size
        ax.step(ordered, ecdf, where="post",
                color=[PALETTE["primary"], PALETTE["secondary"], PALETTE["accent"], PALETTE["warning"]][index % 4],
                label=f"{family}（n={values['n']}）")
    ax.axvline(baseline["delivery"]["cost_total_yuan"], color=PALETTE["neutral"], linestyle="--",
               label="基线交付期 C_total")
    ax.set_xlabel("交付期 C_total（元）")
    ax.set_ylabel("经验累积分布")
    ax.set_title("prob03 robustness：输入噪声的交付期费用 ECDF")
    ax.legend()
    ax.grid(alpha=0.3)
    path = figure_dir / "robustness_prob03_noise_ecdf.png"
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    created.append(str(path))

    # 4) 购电上限曲线
    cap_rows = sensitivity["buy_cap"]
    if cap_rows:
        fig, ax = plt.subplots(figsize=(10, 6))
        feasible = [row for row in cap_rows if row["ok"]]
        infeasible = [row for row in cap_rows if not row["ok"]]
        if feasible:
            ax.plot([row["structural"]["buy_cap_kwh"] / M.DELTA_T for row in feasible],
                    [row["delivery_cost_total_yuan"] for row in feasible],
                    marker="o", color=PALETTE["primary"], label="决策层可行")
        if infeasible:
            ax.scatter([row["structural"]["buy_cap_kwh"] / M.DELTA_T for row in infeasible],
                       [baseline["delivery"]["cost_total_yuan"] for _ in infeasible],
                       marker="x", color=PALETTE["warning"], label="决策层不可行")
        ax.axhline(baseline["delivery"]["cost_total_yuan"], color=PALETTE["neutral"], linestyle="--",
                   label="基线（无上限）")
        ax.set_xlabel("购电上限（kW）")
        ax.set_ylabel("交付期 C_total（元）")
        ax.set_title("prob03 robustness：购电上限结构情景（R5 交叉验证）")
        ax.legend()
        ax.grid(alpha=0.3)
        path = figure_dir / "robustness_prob03_buy_cap_curve.png"
        fig.tight_layout()
        fig.savefig(path)
        plt.close(fig)
        created.append(str(path))

    # 5) 情景箱线图
    noise_values = [
        [item["summary"]["delivery"]["cost_total_yuan"] for item in samples
         if item["family"] == family and item.get("ok")]
        for family in NOISE_FAMILIES
    ]
    if any(noise_values):
        present = [(family, values) for family, values in zip(NOISE_FAMILIES, noise_values) if values]
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.boxplot([values for _family, values in present], tick_labels=[family for family, _values in present])
        ax.axhline(baseline["delivery"]["cost_total_yuan"], color=PALETTE["warning"], linestyle="--",
                   label="基线")
        ax.set_ylabel("交付期 C_total（元）")
        ax.set_title("prob03 robustness：噪声族情景箱线图")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)
        path = figure_dir / "robustness_prob03_scenarios.png"
        fig.tight_layout()
        fig.savefig(path)
        plt.close(fig)
        created.append(str(path))

    # 6) spider
    if sensitivity["tornado"]:
        labels = [item["label"] for item in sensitivity["tornado"]]
        rel = [min(item["spread_relative"] or 0.0, 1.0) for item in sensitivity["tornado"]]
        angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
        rel_closed = rel + rel[:1]
        angles_closed = angles + angles[:1]
        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"projection": "polar"})
        ax.plot(angles_closed, rel_closed, color=PALETTE["primary"], marker="o")
        ax.fill(angles_closed, rel_closed, color=PALETTE["primary"], alpha=0.25)
        ax.set_xticks(angles)
        ax.set_xticklabels(labels)
        ax.set_title("prob03 robustness：参数相对影响（|ΔC_total| / C_total）")
        path = figure_dir / "robustness_prob03_spider.png"
        fig.tight_layout()
        fig.savefig(path)
        plt.close(fig)
        created.append(str(path))

    return created


# --------------------------------------------------------------------------------------
# 基线闸门
# --------------------------------------------------------------------------------------


def check_baseline_gate(
    baseline: dict[str, Any],
    baseline_full: dict[str, Any] | None,
    reference_dir: Path,
) -> dict[str, Any]:
    manifest = json.loads((reference_dir / "run_manifest.json").read_text(encoding="utf-8"))
    pairs = [
        ("objective_yuan", baseline["objective_yuan"], manifest["objective_yuan"]),
        ("cost_plan_yuan", baseline["cost_plan_yuan"], manifest["cost_plan_yuan"]),
        ("cost_adj_yuan", baseline["cost_adj_yuan"], manifest["cost_adj_yuan"]),
        ("cost_em_yuan", baseline["cost_em_yuan"], manifest["cost_em_yuan"]),
        ("delivery_cost_yuan", baseline["delivery"]["cost_total_yuan"], manifest["delivery_cost_yuan"]),
        ("total_purchase_kwh", baseline["delivery"]["total_purchase_kwh"], manifest["total_purchase_kwh"]),
        ("total_q_em_kwh", baseline["delivery"]["total_q_em_kwh"], manifest["total_q_em_kwh"]),
        ("total_spill_kwh", baseline["delivery"]["total_spill_kwh"], manifest["total_spill_kwh"]),
        ("storage_final_kwh", baseline["totals"]["storage_final_kwh"], manifest["storage_final_kwh"]),
    ]
    rows = []
    worst = 0.0
    for name, value, reference in pairs:
        relative = abs(float(value) - float(reference)) / max(abs(float(reference)), 1.0)
        worst = max(worst, relative)
        rows.append({"name": name, "value": _round(value), "reference": _round(reference),
                     "relative_diff": _round(relative, 12)})
    table_rows: list[dict[str, Any]] = []
    tables_path = reference_dir / "tables.json"
    t7_rows: list[dict[str, Any]] = []
    if baseline_full is not None and tables_path.exists():
        reference_tables = json.loads(tables_path.read_text(encoding="utf-8"))
        for date_text, _day_index in SPEC_DATES:
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
        reference_t7 = json.loads((reference_dir / "t7_tiebreak.json").read_text(encoding="utf-8"))["summary"]
        for key in ("layers", "max_primary_relative_change", "lexicographic_committed_layers",
                    "fallback_committed_layers", "degenerate_layers", "layers_with_remaining_multiplicity",
                    "layers_with_unknown_multiplicity"):
            t7_rows.append(
                {
                    "key": key,
                    "full_mode": baseline_full["summary"]["t7"].get(key),
                    "reference": reference_t7.get(key),
                }
            )
    max_table_diff = max((abs(row["reference_kwh"] - row["full_mode_kwh"]) for row in table_rows), default=0.0)
    passed = worst <= 1e-6 and max_table_diff <= 1e-5
    return {
        "reference_dir": str(reference_dir.relative_to(ROOT)),
        "totals": rows,
        "worst_relative_diff": _round(worst, 12),
        "table1_rows": table_rows,
        "table1_max_abs_diff_kwh": _round(max_table_diff, 9),
        "t7_full_mode": t7_rows,
        "baseline_full_available": baseline_full is not None,
        "passed": bool(passed),
    }


# --------------------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="prob03 robustness 实验批（预注册见 ../plan.md）")
    parser.add_argument("--data", default="data/附件1.xlsx")
    parser.add_argument("--data2", default="data/附件2.xlsx")
    parser.add_argument("--data3", default="data/附件3.xlsx")
    parser.add_argument("--template", default="data/附件5/result3.xlsx")
    parser.add_argument("--reference", required=True, help="accepted computation 产物目录（run003）")
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=SEED_DEFAULT)
    parser.add_argument("--samples", type=int, default=25, help="每个噪声族的样本数")
    parser.add_argument("--time-limit", type=float, default=30.0, help="单层 LP 的 HiGHS 时限（秒）")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--mode", choices=("compact", "full"), default="compact")
    parser.add_argument("--families", default="all", help="all 或逗号分隔：param,solver,structural,noise")
    parser.add_argument("--scenarios", default="", help="逗号分隔的情景 id 白名单（用于探针）")
    parser.add_argument("--max-wall-seconds", type=float, default=5400.0)
    parser.add_argument("--probe", action="store_true", help="探针模式：只写 action evidence 允许的产物")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not 2 <= args.days <= 365:
        log(f"--days 必须在 [2, 365]，收到 {args.days}")
        return EXIT_INPUT_INVALID
    output = ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)
    reference_dir = ROOT / args.reference
    probe_mode = args.days < 365 or args.probe
    started = time.perf_counter()

    restore_defaults()
    try:
        base = load_base_inputs(args)
    except IO.InputValidationError as exc:
        log(f"输入校验失败：{exc}")
        return EXIT_INPUT_INVALID
    log(f"输入就绪：days={args.days} periods={args.days * M.PERIODS_PER_DAY}")

    families = args.families.split(",") if args.families != "all" else ["param", "solver", "structural", "noise"]
    scenarios = build_matrix_scenarios()
    if "noise" in families:
        scenarios = scenarios + noise_scenarios(args.samples, args.seed)
    scenarios = [spec for spec in scenarios
                 if family_group(spec["family"]) in families or spec["family"] == "baseline"]
    if args.scenarios:
        allow = {item.strip() for item in args.scenarios.split(",") if item.strip()}
        scenarios = [spec for spec in scenarios if spec["sid"] in allow]
    if not scenarios:
        log("没有可运行的情景")
        return EXIT_INPUT_INVALID

    write_json(
        output / "run_manifest.json",
        {
            "problem_id": "microgrid_2025",
            "question_id": "prob03",
            "stage": "robustness",
            "assumption_version": "assumption_v001",
            "formulation_version": "formulation_v001",
            "model": "M1",
            "mode": args.mode,
            "probe_mode": probe_mode,
            "days": args.days,
            "seed": args.seed,
            "samples_per_noise_family": args.samples,
            "families": families,
            "scenario_count": len(scenarios),
            "scenario_ids": [spec["sid"] for spec in scenarios],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "outcome": "running",
            "tiebreak_rule": "T7-1/T7-5 统一规则；compact 模式跳过 ②/④ 诊断，提交解 = ③ 字典序",
        },
    )

    raw_path = output / "raw_samples.jsonl"
    if raw_path.exists():
        raw_path.unlink()
    samples: list[dict[str, Any]] = []
    baseline_summary: dict[str, Any] | None = None
    baseline_full: dict[str, Any] | None = None
    trajectories_dir = output / "trajectories"
    budget_exceeded = False

    for index, spec in enumerate(scenarios, 1):
        if time.perf_counter() - started > args.max_wall_seconds:
            budget_exceeded = True
            log(f"墙钟预算耗尽：已完成 {index - 1}/{len(scenarios)} 个情景")
            break
        keep_trajectory = spec["family"] != "noise"
        try:
            outcome = run_scenario(spec, base, compact=(args.mode == "compact"), time_limit=args.time_limit)
            summary = outcome["summary"]
            identity_failed = check_subsample_identities(summary)
            record = {
                "scenario": spec["sid"],
                "family": spec["family"],
                "label": spec["label"],
                "params": spec.get("params") or {},
                "solver": spec.get("solver") or {},
                "structural": spec.get("structural") or {},
                "noise": spec.get("noise") or {},
                "ok": True,
                "identity_failed": identity_failed,
                "summary": summary,
            }
            if keep_trajectory:
                write_json(trajectories_dir / f"{spec['sid']}.json", trajectory_payload(outcome["result"], spec))
            if spec["sid"] == "baseline":
                baseline_summary = summary
            if spec["sid"] == "baseline_full":
                metrics = M.evaluate(outcome["result"], full_horizon=not probe_mode)
                tables = R.build_tables(outcome["result"], metrics, base["attachment1"], base["template_info"],
                                        probe_mode=probe_mode)
                baseline_full = {
                    "summary": summary,
                    "metrics": {
                        "objective_yuan": metrics["objective_yuan"],
                        "cost_plan_yuan": metrics["cost_plan_yuan"],
                        "cost_adj_yuan": metrics["cost_adj_yuan"],
                        "cost_em_yuan": metrics["cost_em_yuan"],
                        "delivery_cost_yuan": metrics["delivery"]["cost_total_yuan"],
                        "checks_failed": metrics["checks_failed"],
                        "t7_tiebreak": metrics["t7_tiebreak"],
                    },
                    "tables": tables,
                }
            log(
                f"[{index}/{len(scenarios)}] {spec['sid']}：全期 {summary['objective_yuan']:.4f} 元、"
                f"交付期 {summary['delivery']['cost_total_yuan']:.4f} 元、"
                f"Σq_em {summary['totals']['total_q_em_kwh']:.4f} kWh、{summary['seconds']:.2f} s"
            )
        except (M.LayerFailure, M.BudgetExceeded) as exc:
            status = int(getattr(exc, "status", -1))
            record = {
                "scenario": spec["sid"],
                "family": spec["family"],
                "label": spec["label"],
                "params": spec.get("params") or {},
                "solver": spec.get("solver") or {},
                "structural": spec.get("structural") or {},
                "noise": spec.get("noise") or {},
                "ok": False,
                "failure": {"type": "solver_not_optimal", "status": status, "message": str(exc)[:400]},
            }
            log(f"[{index}/{len(scenarios)}] {spec['sid']}：不可行/未达最优（status={status}）")
        except Exception as exc:  # noqa: BLE001
            record = {
                "scenario": spec["sid"],
                "family": spec["family"],
                "label": spec["label"],
                "params": spec.get("params") or {},
                "solver": spec.get("solver") or {},
                "structural": spec.get("structural") or {},
                "noise": spec.get("noise") or {},
                "ok": False,
                "failure": {"type": "exception", "message": f"{type(exc).__name__}: {exc}"[:400],
                            "traceback": traceback.format_exc()[-1200:]},
            }
            log(f"[{index}/{len(scenarios)}] {spec['sid']}：异常 {type(exc).__name__}: {exc}")
        finally:
            restore_defaults()
            M._solve_with_tiebreak = _ORIGINAL_SOLVE_WITH_TIEBREAK
            SolverOverride.uninstall()
        samples.append(record)
        append_jsonl(raw_path, record)

    elapsed = time.perf_counter() - started
    solved = [item for item in samples if item.get("ok")]
    if baseline_summary is None:
        baseline_summary = next((item["summary"] for item in solved if item["scenario"] == "baseline"), None)
    if baseline_summary is None:
        write_json(output / "solver_status.json",
                   {"status": -1, "feasible_incumbent": False,
                    "message": "基线情景未成功，整批作废", "seconds": _round(elapsed, 6)})
        write_json(output / "summary.json", {"outcome": "baseline_failed", "samples": len(samples)})
        log("基线情景未成功，整批作废")
        return EXIT_BASELINE_GATE_FAILED

    sensitivity = build_sensitivity(samples, baseline_summary, seed=args.seed)
    criteria = evaluate_criteria(samples, sensitivity, baseline_summary)
    figures = make_figures(output, samples, sensitivity, baseline_summary, args.seed)
    baseline_check = check_baseline_gate(baseline_summary, baseline_full, reference_dir)

    write_json(output / "baseline_check.json", baseline_check)
    write_json(output / "sensitivity.json", sensitivity)
    write_json(
        output / "summary.json",
        {
            "scenario_count": len(scenarios),
            "sample_count": len(samples),
            "solved_count": len(solved),
            "failed_count": len(samples) - len(solved),
            "failures": [{"scenario": item["scenario"], "failure": item.get("failure")}
                         for item in samples if not item.get("ok")],
            "baseline": baseline_summary,
            "criteria": criteria,
            "stability_grade": criteria["stability_grade"],
            "failed_criteria": criteria["failed"],
            "structural_findings": {
                "buy_cap_feasibility_bracket_kw": criteria["S6"]["detail"]["buy_cap_feasibility_bracket_kw"],
                "terminal_e_6000": criteria["S6"]["detail"]["terminal_e_6000"],
                "solver_rows": sensitivity["solver"],
            },
            "figures": figures,
            "wall_seconds": _round(elapsed, 6),
            "budget_exceeded": budget_exceeded,
        },
    )
    write_json(
        output / "solver_status.json",
        {
            "status": 0 if not budget_exceeded else 1,
            "feasible_incumbent": True,
            "baseline_check_passed": baseline_check["passed"],
            "model": "M1",
            "device": "cpu",
            "gpu_required": False,
            "seed": args.seed,
            "scenario_count": len(scenarios),
            "solved_count": len(solved),
            "failed_count": len(samples) - len(solved),
            "wall_seconds": _round(elapsed, 6),
            "mode": args.mode,
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
        }
    )
    write_json(output / "run_manifest.json", manifest)

    log(f"完成：{len(solved)}/{len(samples)} 情景成功，{elapsed:.1f} s，稳定性分级 = {criteria['stability_grade']}")
    if not baseline_check["passed"]:
        log("基线复现闸门失败（与 run003 不一致），整批判为失败")
        return EXIT_BASELINE_GATE_FAILED
    if budget_exceeded:
        return EXIT_BUDGET_EXCEEDED
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
