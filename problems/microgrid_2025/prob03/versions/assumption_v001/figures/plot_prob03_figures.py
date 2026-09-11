"""prob03 正式图表生成脚本（assumption_v001 / formulation_v001 / task 6de708bbd2d3dd273013 / run003）。

- 只读消费 accepted 版本的正式计算结果（solution.json / tables.json / run_manifest.json / t7_tiebreak.json）
  与原始附件（附件 2 实际光伏、附件 3 整点预报，仅用于展示信息结构），不改数据。
- 统一从 config/visualization.yaml 读取字体、色板、尺寸、DPI 与质检阈值。
- 每图使用 automm.visualization.stable_figure_id 生成稳定 ID，文件名不依赖易变图号。
- 自动质检 inspect_png 写 *.quality.json；manifest 登记到 problems/microgrid_2025/figures.yaml。
- 视觉复核状态由 Agent 通过 record_figure_review 命令写入（本脚本先登记为 pending）。
- 纪律：团队勘误 E3 —— 预报精度（RMSE）不作为「跳发布时刻」的比较轴；本脚本只展示信息结构，
  不做发布时刻之间的精度排序。T7-3/E7 的退化事实如实报告，不为唯一性调 ε。

运行（项目根目录）：
    .venv\\Scripts\\python.exe problems/microgrid_2025/prob03/versions/assumption_v001/figures/plot_prob03_figures.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.colors import TwoSlopeNorm

FIG_DIR = Path(__file__).resolve().parent
ROOT = FIG_DIR.parents[5]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(FIG_DIR.parent / "code"))

from automm.common import config_section, hash_path, read_yaml, relative, write_json, write_yaml  # noqa: E402
from automm.visualization import inspect_png, register_figure, stable_figure_id  # noqa: E402

import prob03_model as pm  # noqa: E402
import prob03_io as pio  # noqa: E402

PROBLEM_ID = "microgrid_2025"
QUESTION_ID = "prob03"
ASSUMPTION_VERSION = "assumption_v001"
FORMULATION_VERSION = "formulation_v001"
TASK_ID = "6de708bbd2d3dd273013"

RESULT_DIR = FIG_DIR.parent / "results" / "prob03_v001_f001_run003"
SOLUTION_PATH = RESULT_DIR / "solution.json"
TABLES_PATH = RESULT_DIR / "tables.json"
RUN_MANIFEST_PATH = RESULT_DIR / "run_manifest.json"
TIEBREAK_PATH = RESULT_DIR / "t7_tiebreak.json"

PROB02_SOLUTION = (
    ROOT / "problems/microgrid_2025/prob02/versions/assumption_v001/results/prob02_v001_f001_run002/solution.json"
)
ATT2_PATH = ROOT / "data/附件2.xlsx"
ATT3_PATH = ROOT / "data/附件3.xlsx"

DAYS = 365
SEGMENTS_PER_DAY = 144
TOTAL = DAYS * SEGMENTS_PER_DAY
DT_H = 1.0 / 6.0
P_MAX_KW = 5000.0
C_CAP_KWH = 833.3333333333333
Q_DIS_CAP_KWH = 750.0
E_MIN, E_MAX, E_INIT = 1200.0, 10800.0, 6000.0
ALPHA_EM, BETA_DEF, BETA_OVER = 5.0, 0.5, 1.5
DELIVERY_START_DAY = 31  # 2025-02-01（0 基日索引）
DECISION_HOURS = (0, 6, 12, 18)
SPEC_DAYS = {"2025-03-20": 78, "2025-06-21": 171, "2025-09-23": 265, "2025-12-21": 354}
DAY0 = date(2025, 1, 1)
MONTH_TICKS = [(date(2025, m, 1) - DAY0).days for m in range(1, 13)]
MONTH_LABELS = [f"{m} 月" for m in range(1, 13)]
SPEC_LABEL_DAY = {"2025-03-20": 78, "2025-06-21": 171, "2025-09-23": 265, "2025-12-21": 354}
# AS01 位置口径：时段 i（1..144）= [10(i−1), 10i) min，计划窗 0:10 → 24:10
PERIOD_CENTER_H = (np.arange(SEGMENTS_PER_DAY) + 0.5) * DT_H

STYLE = config_section("visualization", PROBLEM_ID, QUESTION_ID)
PALETTE = STYLE.get("palette", {})
PRIMARY = PALETTE.get("primary", "#1F4E79")
SECONDARY = PALETTE.get("secondary", "#70AD47")
ACCENT = PALETTE.get("accent", "#ED7D31")
NEUTRAL = PALETTE.get("neutral", "#7F8C8D")
WARNING = PALETTE.get("warning", "#C00000")
BG = STYLE.get("background", "white")
DPI = int(STYLE.get("dpi", 180))
FIG_W = float(STYLE.get("figure_width", 10))
FIG_H = float(STYLE.get("figure_height", 6))


def select_font() -> str:
    available = {font.name for font in font_manager.fontManager.ttflist}
    candidates = [STYLE.get("preferred_font"), *STYLE.get("fallback_fonts", [])]
    for candidate in candidates:
        if candidate and candidate in available:
            return str(candidate)
    raise RuntimeError(
        "未找到任何配置中的中文字体，拒绝出图（避免方框字符）。可用候选检查结果："
        + json.dumps({c: (c in available) for c in candidates if c}, ensure_ascii=False)
    )


FONT = select_font()
plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": [FONT, "DejaVu Sans"],
        "font.size": STYLE.get("font_size", 11),
        "axes.titlesize": STYLE.get("title_size", 14),
        "axes.unicode_minus": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.22,
        "figure.facecolor": BG,
        "savefig.facecolor": BG,
    }
)


# ---------------------------------------------------------------- 数据载入
def load_results() -> tuple[dict, dict, dict, dict]:
    solution = json.loads(SOLUTION_PATH.read_text(encoding="utf-8"))
    tables = json.loads(TABLES_PATH.read_text(encoding="utf-8"))
    run_manifest = json.loads(RUN_MANIFEST_PATH.read_text(encoding="utf-8"))
    tiebreak = json.loads(TIEBREAK_PATH.read_text(encoding="utf-8"))
    series = {}
    for key, values in solution["series"].items():
        if isinstance(values, list) and len(values) == TOTAL:
            series[key] = np.asarray(values, dtype=float)
    solution["series"] = series
    return solution, tables, run_manifest, tiebreak


DATA: dict = {}


def day_slice(day: int) -> np.s_[...]:
    return np.s_[day * SEGMENTS_PER_DAY : (day + 1) * SEGMENTS_PER_DAY]


def mark_months(ax: plt.Axes) -> None:
    for pos in MONTH_TICKS[1:]:
        ax.axvline(pos, color=NEUTRAL, lw=0.7, ls=":", alpha=0.55)
    ax.set_xticks(MONTH_TICKS)
    ax.set_xticklabels(MONTH_LABELS)


def finish_xlabel_days(ax: plt.Axes) -> None:
    ax.set_xlabel("日期（2025-01-01 → 2025-12-31；竖点线为月初；红虚线为 2025-02-01 交付期起点）")


def mark_delivery(ax: plt.Axes) -> None:
    ax.axvline(DELIVERY_START_DAY, color=WARNING, ls="--", lw=1.2, alpha=0.9)


def emit(
    fig: plt.Figure,
    *,
    kind: str,
    title: str,
    x,
    y: list[str],
    caption: str,
    source_hash: str,
    source_data: str,
    include_in_paper: bool = True,
) -> dict:
    figure_id = stable_figure_id(
        problem_id=PROBLEM_ID,
        question_id=QUESTION_ID,
        kind=kind,
        title=title,
        source_hash=source_hash,
        x=x,
        y=y,
        style=STYLE,
    )
    output = FIG_DIR / f"{figure_id}.png"
    fig.savefig(output, dpi=DPI, format="png", bbox_inches="tight")
    plt.close(fig)
    quality = inspect_png(output, PROBLEM_ID, QUESTION_ID)
    item = {
        "stable_id": figure_id,
        "problem_id": PROBLEM_ID,
        "question_id": QUESTION_ID,
        "assumption_version": ASSUMPTION_VERSION,
        "formulation_version": FORMULATION_VERSION,
        "task_id": TASK_ID,
        "kind": kind,
        "title": title,
        "caption": caption,
        "path": relative(output),
        "source_data": source_data,
        "source_hash": source_hash,
        "script": relative(Path(__file__).resolve()),
        "font": FONT,
        "style_config": "config/visualization.yaml",
        "included_in_summary": True,
        "included_in_paper": include_in_paper,
        "quality_report": relative(output.with_suffix(".quality.json")),
        "quality_status": quality["status"],
        "visual_review": {"status": "pending", "reason": ""},
    }
    register_figure(PROBLEM_ID, item)
    return item


def combined_hash(*paths: Path) -> str:
    joined = "".join(hash_path(path) for path in paths)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def prune_stale_figures(current_ids: set[str]) -> list[str]:
    """清理本小问在 manifest 中已失效的登记项（稳定 ID 随图定义变化时会产生孤儿条目）。

    只作用于 ``question_id == prob03`` 且稳定 ID 不在本次生成集合内的条目，并删除其 PNG/质检文件；
    不触碰 prob01/prob02/robustness/ablation 的任何登记项，也不改动 manifest 的其它字段。
    """
    manifest_path = ROOT / "problems" / PROBLEM_ID / "figures.yaml"
    manifest = read_yaml(manifest_path, {"figures": []})
    kept: list[dict] = []
    removed: list[str] = []
    for item in manifest.get("figures", []):
        if item.get("question_id") == QUESTION_ID and item.get("stable_id") not in current_ids:
            removed.append(str(item.get("stable_id")))
            for suffix in (".png", ".quality.json"):
                target = FIG_DIR / f"{item.get('stable_id')}{suffix}"
                if target.exists():
                    target.unlink()
            continue
        kept.append(item)
    if removed:
        manifest["figures"] = kept
        write_yaml(manifest_path, manifest)
    return removed


# ---------------------------------------------------------------- 派生量
def derive() -> None:
    solution = DATA["solution"]
    series = solution["series"]
    daily = solution["daily"]

    day_index = np.asarray(series["day_index"], dtype=int)
    price = series["price_yuan_per_kwh"]
    plan = series["plan_purchase_kwh"]
    final = series["final_purchase_kwh"]
    q_em = series["q_em_kwh"]
    charge = series["charge_kwh"]
    discharge = series["discharge_kwh"]
    spill = series["spill_settlement_kwh"]
    storage = series["storage_kwh"]
    load = series["load_energy_kwh"]
    pv_act = series["pv_actual_energy_kwh"]

    delta = final - plan
    DATA.update(
        {
            "day_index": day_index,
            "price": price,
            "plan": plan,
            "final": final,
            "q_em": q_em,
            "charge": charge,
            "discharge": discharge,
            "spill": spill,
            "storage": storage,
            "load": load,
            "pv_act": pv_act,
            "delta": delta,
            "delivery_mask": day_index >= DELIVERY_START_DAY,
        }
    )

    DATA["adjust_hourly"] = delta.reshape(DAYS, SEGMENTS_PER_DAY).reshape(DAYS, 24, 6).sum(axis=2)
    DATA["q_em_hourly"] = np.zeros(24)
    DATA["q_em_hour_count"] = np.zeros(24, dtype=int)
    hours_of_period = np.tile(np.repeat(np.arange(24), 6), DAYS)
    for hour in range(24):
        mask = hours_of_period == hour
        DATA["q_em_hourly"][hour] = q_em[mask].sum()
        DATA["q_em_hour_count"][hour] = int((q_em[mask] > 1e-9).sum())

    by_day = delta.reshape(DAYS, SEGMENTS_PER_DAY).sum(axis=1)
    DATA["daily_delta"] = by_day
    DATA["daily_q_em"] = np.asarray(daily["q_em_kwh"], dtype=float)
    daily_state_start = np.asarray(daily["state_start_kwh"], dtype=float)
    daily_state_end = np.asarray(daily["state_end_kwh"], dtype=float)
    period_end = storage.reshape(DAYS, SEGMENTS_PER_DAY)
    # 逐日区间含日初状态（E_{d,0}）与全部时段末状态（E 为时段末状态）
    DATA["daily_storage_min"] = np.minimum(period_end.min(axis=1), daily_state_start)
    DATA["daily_storage_max"] = np.maximum(period_end.max(axis=1), daily_state_start)
    DATA["daily_storage_mean"] = period_end.mean(axis=1)
    DATA["daily_state_start"] = daily_state_start
    DATA["daily_state_end"] = daily_state_end

    cost_plan = float((price * plan).sum())
    cost_adj = float((BETA_OVER * price * np.maximum(0.0, delta) + BETA_DEF * price * np.maximum(0.0, -delta)).sum())
    cost_em = float((ALPHA_EM * price * q_em).sum())
    DATA["recomputed_cost"] = {
        "plan": cost_plan,
        "adj": cost_adj,
        "em": cost_em,
        "total": cost_plan + cost_adj + cost_em,
    }

    p2 = json.loads(PROB02_SOLUTION.read_text(encoding="utf-8"))
    DATA["prob02"] = {
        "delivery_cost_yuan": float(p2["delivery_cost_yuan"]),
        "objective_yuan": float(p2["objective_yuan"]),
        "net_load_delivery_kwh": float(p2["totals"]["net_load_delivery_kwh"]),
        "state_start_delivery_kwh": float(np.asarray(p2["daily"]["state_start_kwh"], dtype=float)[DELIVERY_START_DAY]),
    }

    DATA["up_periods"] = int((delta > 1e-9).sum())
    DATA["down_periods"] = int((delta < -1e-9).sum())
    DATA["down_energy"] = float(delta[delta < 0].sum()) if (delta < 0).any() else 0.0

    # 信息链：附件 3 预报（整点 + 线性插值降尺度）与实际光伏
    attachment2 = pio.read_attachment2(ATT2_PATH)
    attachment3 = pio.read_attachment3(ATT3_PATH)
    pv_actual_kw = pv_act.reshape(DAYS, SEGMENTS_PER_DAY) / DT_H
    layers: dict[int, np.ndarray] = {}
    for hour in DECISION_HOURS:
        matrix = np.full((DAYS, SEGMENTS_PER_DAY), np.nan)
        for day in range(DAYS):
            row = pm.downscale(attachment3.fc_kw[day, DECISION_HOURS.index(hour)], hour)
            matrix[day, (hour * 6) :] = row[(hour * 6) :]
        layers[hour] = matrix
    DATA["fc_layers"] = layers
    # 最终决策实际采用的支配预报：t≤36→0:00；37–72→6:00；73–108→12:00；109–144→18:00
    dominant = np.full((DAYS, SEGMENTS_PER_DAY), np.nan)
    for block, hour in enumerate(DECISION_HOURS):
        dominant[:, block * 36 : (block + 1) * 36] = layers[hour][:, block * 36 : (block + 1) * 36]
    DATA["fc_dominant"] = dominant
    DATA["pv_actual_kw"] = pv_actual_kw

    DATA["tiebreak"] = DATA["tiebreak_raw"]["per_layer"]
    DATA["checks_failed"] = list(solution.get("checks_failed", []))


# ---------------------------------------------------------------- 图 1：信息链
def figure_forecast_chain(source_hash: str, source_data: str) -> dict:
    days = [SPEC_DAYS["2025-06-21"], SPEC_DAYS["2025-12-21"]]
    labels = ["2025-06-21（夏至）", "2025-12-21（冬至）"]
    fig, axes = plt.subplots(1, 2, figsize=(FIG_W + 3.4, FIG_H), layout="constrained")

    for ax, day, label in zip(axes, days, labels):
        actual = DATA["pv_actual_kw"][day]
        plan_fc = DATA["fc_layers"][0][day]
        axis_fc = DATA["fc_dominant"][day]
        for boundary in (6, 12, 18):
            ax.axvline(boundary, color=NEUTRAL, lw=0.9, ls=":", alpha=0.7)
        ax.plot(PERIOD_CENTER_H, actual, color="black", lw=2.0, label="附件 2 实际光伏 $PV^{act}$（结算层）")
        ax.plot(PERIOD_CENTER_H, plan_fc, color=PRIMARY, lw=1.6, ls="--", label="0:00 预报降尺度（计划层输入）")
        ax.plot(PERIOD_CENTER_H, axis_fc, color=ACCENT, lw=1.9, label="支配预报降尺度（调整层输入，逐段 ≤6 h 提前量）")
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 4))
        ax.set_ylim(-250, max(actual.max(), np.nanmax(plan_fc)) * 1.24)
        ax.set_xlabel("计划窗时刻 (h)（AS01 位置口径 0:10 → 24:10）")
        ax.set_ylabel("光伏功率 (kW)")
        ax.set_title(f"{label}：决策用预报与结算用实际")
        ax.legend(frameon=False, fontsize=8.4, loc="upper left")
        for boundary in (6, 12, 18):
            ax.annotate(
                f"{boundary}:00 发布",
                xy=(boundary + 0.15, ax.get_ylim()[1] * 0.02),
                fontsize=7.8,
                color=NEUTRAL,
                rotation=90,
                va="bottom",
            )

    fig.suptitle("prob03 三层信息结构：计划用 0:00 预报、调整用各时刻最新预报、结算用附件 2 实际值", fontsize=13)
    return emit(
        fig,
        kind="forecast_chain",
        title="prob03 三层信息结构：决策用预报与结算用实际（代表日）",
        x="time_of_day_h",
        y=["pv_actual_kw", "pv_forecast_plan_kw", "pv_forecast_dominant_kw"],
        caption=(
            "两个代表日的日内光伏：黑实线 = 附件 2 实际光伏 $PV^{act}$（只进结算层，F2）；蓝虚线 = 0:00 预报经 AS05 "
            "降尺度（整点点值 + 整点锚定线性插值）后的计划层输入；橙实线 = 该时段支配决策时刻（0:00/6:00/12:00/18:00，"
            "每个时刻支配 36 个时段）的预报降尺度结果，即调整层输入。竖点线为四个预报发布时刻。"
            "本图只展示信息结构，**不比较**四个发布时刻的预报精度：各时刻可用样本的提前量窗口与日内时段不同，"
            "团队勘误 E3 明确禁止把不同样本口径的 RMSE 横排成『某时刻更准』；AS05 的块内能量不守恒（T3）亦在此声明。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ---------------------------------------------------------------- 图 2：计划 / 调整 / 紧急
def figure_plan_adjust_profile(source_hash: str, source_data: str) -> dict:
    days = [SPEC_DAYS["2025-03-20"], SPEC_DAYS["2025-12-21"]]
    labels = ["2025-03-20（春分）", "2025-12-21（冬至）"]
    fig, axes = plt.subplots(2, 2, figsize=(FIG_W + 3.4, FIG_H + 3.2), layout="constrained", sharex="col")
    handles = None

    for column, (day, label) in enumerate(zip(days, labels)):
        ax = axes[0][column]
        plan = DATA["plan"][day_slice(day)]
        final = DATA["final"][day_slice(day)]
        delta = DATA["delta"][day_slice(day)]
        q_em = DATA["q_em"][day_slice(day)]
        price = DATA["price"][day_slice(day)]
        ax.plot(PERIOD_CENTER_H, plan, color=PRIMARY, lw=1.6, label="计划购电量 $b$（0:00 预报）")
        ax.plot(PERIOD_CENTER_H, final, color=ACCENT, lw=1.6, label="最终购电量 $q$（调整后）")
        ax.fill_between(PERIOD_CENTER_H, plan, final, where=final >= plan, color=ACCENT, alpha=0.30,
                        label="调整上调 $q-b$")
        ax.fill_between(PERIOD_CENTER_H, plan, final, where=final < plan, color=SECONDARY, alpha=0.35,
                        label="调整下调 $b-q$")
        ax.bar(PERIOD_CENTER_H, q_em, width=0.13, color=WARNING, alpha=0.75, label="紧急购电量 $q_{em}$")
        upper = max(float(final.max()), float(plan.max()))
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 4))
        ax.set_ylim(0, upper * 1.32)
        ax.set_ylabel("电量 (kWh/10min)")
        ax.set_title(f"{label}：计划 $b$、最终 $q$ 与紧急购电 $q_{{em}}$")
        if handles is None:
            handles, legend_labels = ax.get_legend_handles_labels()
        ax.annotate(
            f"当日 $\\Sigma(q-b)$ = {delta.sum():,.1f} kWh；$\\Sigma q_{{em}}$ = {q_em.sum():,.1f} kWh\n"
            f"当日 $C_{{adj}}$ = {(BETA_OVER * price * np.maximum(0, delta)).sum():,.0f} 元；"
            f"$C_{{em}}$ = {(ALPHA_EM * price * q_em).sum():,.0f} 元",
            xy=(0.985, 0.975),
            xycoords="axes fraction",
            ha="right",
            va="top",
            fontsize=8.2,
            color=NEUTRAL,
            bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": NEUTRAL, "alpha": 0.94},
        )

        ax2 = axes[1][column]
        colors = [ACCENT if value >= 0 else SECONDARY for value in delta]
        ax2.bar(PERIOD_CENTER_H, delta, width=0.14, color=colors, alpha=0.92)
        ax2.axhline(0.0, color="black", lw=0.8)
        peak = float(np.max(np.abs(delta)))
        ax2.set_ylim(-peak * 1.25, peak * 1.25)
        ax2.set_xticks(range(0, 25, 4))
        ax2.set_xlabel("计划窗时刻 (h)（AS01 位置口径 0:10 → 24:10）")
        ax2.set_ylabel("调整量 $q-b$ (kWh/10min)")
        ax2.set_title("逐时段调整量：本问主口径下只有上调（$q\\geq b$）")
        non_zero = int((np.abs(delta) > 1e-9).sum())
        ax2.annotate(
            f"非零调整时段 {non_zero} / {SEGMENTS_PER_DAY}；峰值 |q−b| = {peak:,.1f} kWh/10min\n"
            "D2-A 口径下下调只增加 $0.5p(b-q)$ 成本、不减少计划费（$\\Sigma p b$ 已全额沉没），\n"
            "盈余又可零成本弃光，故最优解满足 $q\\geq b$（全期下调仅 86 时段 / −2.87e-7 kWh，属容差）",
            xy=(0.985, 0.955),
            xycoords="axes fraction",
            ha="right",
            va="top",
            fontsize=8.0,
            color=NEUTRAL,
            bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": NEUTRAL, "alpha": 0.94},
        )

    fig.legend(handles, legend_labels, loc="lower center", bbox_to_anchor=(0.5, -0.055), ncol=5, frameon=False,
               fontsize=9)
    fig.suptitle("prob03 计划层 / 调整层 / 结算层的日内落地（两个指定日期）", fontsize=13)
    zero_days = int(sum(1 for value in DATA["daily_delta"] if abs(value) < 1e-6))
    return emit(
        fig,
        kind="plan_adjust_profile",
        title="prob03 计划购电量、最终购电量与紧急购电的日内剖面",
        x="time_of_day_h",
        y=["plan_purchase_kwh", "final_purchase_kwh", "q_em_kwh", "adjustment_kwh"],
        caption=(
            "两行两列：上排为指定日期的日内剖面（蓝线 = 计划层购电量 $b$，仅用 0:00 预报；橙线 = 调整后的最终购电量 $q$，"
            "各时段取其支配决策时刻的预报；橙/绿填充 = 上调 $q-b$ / 下调 $b-q$；红柱 = 结算层紧急购电量 $q_{em}$），"
            "下排为同一日期的逐时段调整量 $(q-b)$。主口径下 $q_{em}$ 只在结算层由「支配层预报 vs 附件 2 实际」的缺口产生"
            "（F3），决策层恒不激活。全期 52,560 时段中上调 5,810 个、下调 86 个（下调总量 −2.87e-7 kWh，属求解器容差），"
            "即最优解满足 $q\\geq b$：在 D2-A 口径下下调只增加 $0.5p(b-q)$ 成本而不减少已全额沉没的计划费 $\\Sigma p b$，"
            "盈余又可零成本弃光；成因是计划层目标 $\\min\\Sigma p b$ 不含偏差与紧急购电预期（团队裁定 T1/T6 与勘误 R11 的"
            f"『无对冲机制』）。全年另有 {zero_days} 天（含 2025-09-23）无任何调整，当日购电全部按计划执行、"
            "缺口仍由结算层紧急购电承担。",
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ---------------------------------------------------------------- 图 3：三维调整曲面
def figure_adjust_surface_3d(source_hash: str, source_data: str) -> dict:
    grid = DATA["adjust_hourly"]
    day_axis = np.arange(DAYS)
    hour_axis = np.arange(24)
    day_grid, hour_grid = np.meshgrid(day_axis, hour_axis, indexing="ij")

    fig = plt.figure(figsize=(FIG_W + 2.0, FIG_H + 2.6))
    ax = fig.add_subplot(111, projection="3d")
    cap = float(np.percentile(grid, 99.5))
    norm = TwoSlopeNorm(
        vmin=min(float(grid.min()), -1e-6),
        vcenter=0.0,
        vmax=max(cap, 1e-6),
    )
    surface = ax.plot_surface(
        day_grid,
        hour_grid,
        grid,
        cmap="coolwarm",
        norm=norm,
        rstride=3,
        cstride=1,
        linewidth=0.0,
        antialiased=True,
        alpha=0.96,
    )
    ax.set_xlabel("日期（日索引，0 = 2025-01-01）", labelpad=9)
    ax.set_ylabel("时刻 (h)", labelpad=9)
    ax.set_zlabel("调整量 $q-b$ (kWh/h)", labelpad=6)
    ax.set_yticks([0, 6, 12, 18, 23])
    ax.set_zlim(min(float(grid.min()), -1e-6), cap)
    ax.set_box_aspect(None, zoom=0.92)
    ax.view_init(elev=26, azim=-58)
    ax.set_title(
        "全年调整量三维曲面：日期 × 时刻 × 调整量 $q-b$\n"
        f"（365 × 24 = {grid.size:,} 个「日 × 小时」格；Z>0 上调（暖色）、Z<0 下调（冷色））"
    )
    bar = fig.colorbar(surface, ax=ax, shrink=0.6, pad=0.09)
    bar.set_label("调整量 (kWh/h)")
    ax.annotate(
        f"上调 {DATA['up_periods']:,} 时段 / 下调 {DATA['down_periods']} 时段；"
        f"$\\Sigma(q-b)$ = {DATA['delta'].sum():,.1f} kWh（全期）\n"
        f"色标与 Z 轴按 99.5 分位 {cap:,.0f} kWh/h 截断（峰值 {grid.max():,.0f}）；"
        "定量判读以二维图 adjust_heatmap_2d 为准",
        xy=(0.02, 0.96),
        xycoords="axes fraction",
        va="top",
        fontsize=8.8,
        color=NEUTRAL,
    )
    fig.tight_layout()
    return emit(
        fig,
        kind="adjust_surface_3d",
        title="prob03 全年调整量三维曲面：日期 × 时刻 ×（最终−计划）购电量",
        x="day_index",
        y=["time_of_day_hour", "adjustment_kwh_per_hour"],
        caption=(
            "三维曲面：X = 日期（2025 全年 365 天），Y = 时刻（0→23 h），Z = 该「日 × 小时」内 6 个时段的调整量之和 "
            "$(q-b)$（kWh/h），颜色以 0 为中心的双向色标（暖色=上调、冷色=下调）。视角 elev=26°、azim=−58°，"
            "为静态 PNG 可读性沿日期轴每 3 天抽 1 条网格线；色标与 Z 轴按 99.5 分位截断以保留低幅结构（已在图内注明峰值）。"
            "曲面几乎全部位于 Z≥0 半空间（上调 5,810 时段、下调 86 时段且总量 −2.87e-7 kWh），无自遮挡；"
            "定量判读以配套二维投影 adjust_heatmap_2d 为准。",
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ---------------------------------------------------------------- 图 4：二维配套投影
def figure_adjust_heatmap_2d(source_hash: str, source_data: str) -> dict:
    grid = DATA["adjust_hourly"]
    limit = float(np.nanpercentile(np.abs(grid), 99.0))
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(FIG_W + 2.0, FIG_H + 2.6), layout="constrained",
                                   gridspec_kw={"height_ratios": [1.35, 1.0]})

    image = ax1.pcolormesh(
        np.arange(DAYS + 1),
        np.arange(25),
        grid.T,
        cmap="coolwarm",
        norm=TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit),
        shading="flat",
    )
    bar = fig.colorbar(image, ax=ax1, pad=0.012)
    bar.set_label("调整量 $q-b$ (kWh/h)")
    mark_delivery(ax1)
    ax1.set_xticks(MONTH_TICKS)
    ax1.set_xticklabels(MONTH_LABELS, fontsize=9)
    ax1.set_yticks([0, 4, 8, 12, 16, 20, 24])
    ax1.set_ylabel("时刻 (h)")
    ax1.set_xlim(0, DAYS)
    ax1.set_title(
        "全年「日期 × 时刻」调整量热力图（色标按 |调整量| 99 分位截断，单位 kWh/h）"
    )
    ax1.grid(visible=False)
    ax1.annotate(
        f"红虚线 = 2025-02-01 交付期起点；99 分位 = {limit:,.0f} kWh/h；"
        f"上调 5,810 / 下调 {DATA['down_periods']} 时段",
        xy=(0.99, 0.965),
        xycoords="axes fraction",
        ha="right",
        va="top",
        fontsize=8.4,
        color=NEUTRAL,
        bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": NEUTRAL, "alpha": 0.9},
    )

    daily = DATA["daily_delta"] / 1000.0
    ax2.bar(np.arange(DAYS), daily, width=1.0, color=ACCENT, alpha=0.85, label="逐日 $\\Sigma(q-b)$")
    ax2.axhline(0.0, color="black", lw=0.8)
    delivery_mean = daily[DELIVERY_START_DAY:].mean()
    ax2.axhline(delivery_mean, color=PRIMARY, ls="--", lw=1.3,
                label=f"交付期日均 {delivery_mean:,.2f} MWh/日")
    mark_delivery(ax2)
    mark_months(ax2)
    ax2.set_ylabel("调整量 (MWh/日)")
    finish_xlabel_days(ax2)
    ax2.set_title("逐日调整量（$\\Sigma_t(q-b)$）：交付期几乎逐日为正，与三维曲面一致")
    ax2.legend(frameon=False, fontsize=9, loc="upper left")
    ax2.annotate(
        f"全期 $\\Sigma(q-b)$ = {DATA['delta'].sum():,.1f} kWh；交付期 = "
        f"{DATA['delta'][DATA['delivery_mask']].sum():,.1f} kWh\n"
        f"$C_{{adj}}$（全期）= {DATA['recomputed_cost']['adj']:,.2f} 元，其中 1.5× 上调项占主导（下调项 8.4e-8 元）",
        xy=(0.99, 0.96),
        xycoords="axes fraction",
        ha="right",
        va="top",
        fontsize=8.4,
        color=NEUTRAL,
        bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": NEUTRAL, "alpha": 0.9},
    )
    return emit(
        fig,
        kind="adjust_heatmap_2d",
        title="prob03 调整量的二维投影：日期 × 时刻热力图与逐日总量",
        x="day_index",
        y=["time_of_day_hour", "adjustment_kwh_per_hour", "daily_adjustment_kwh"],
        caption=(
            "上：全年「日期 × 时刻」调整量 $(q-b)$ 热力图（色标以 0 为中心并按 99 分位截断以防压色）；"
            "下：逐日调整量 $\\Sigma_t(q-b)$ 柱状与交付期日均线（MWh/日）。用于对三维曲面 adjust_surface_3d 做定量判读："
            "调整集中在日间光伏时段与傍晚，交付期（2025-02-01 起）几乎逐日为正。"
            "X 轴为自然日索引（0 = 2025-01-01）。",
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ---------------------------------------------------------------- 图 5：费用分解与跨问对比
def figure_cost_decomposition(source_hash: str, source_data: str) -> dict:
    solution = DATA["solution"]
    delivery = solution["delivery"]
    full = DATA["recomputed_cost"]
    p2 = DATA["prob02"]

    labels = ["交付期 $D_{req}$\n(2025-02-01…12-31，334 天)", "全期 $D_{full}$\n(2025 全年 365 天，含 1 月预热)"]
    plan_vals = np.array([delivery["cost_plan_yuan"], full["plan"]])
    adj_vals = np.array([delivery["cost_adj_yuan"], full["adj"]])
    em_vals = np.array([delivery["cost_em_yuan"], full["em"]])
    totals = plan_vals + adj_vals + em_vals

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(FIG_W + 3.0, FIG_H + 0.6), layout="constrained")

    xpos = np.arange(2)
    ax1.bar(xpos, plan_vals / 1e4, width=0.52, color=PRIMARY, label="计划购电费 $C_{plan}=\\Sigma p\\,b$")
    ax1.bar(xpos, adj_vals / 1e4, width=0.52, bottom=plan_vals / 1e4, color=ACCENT,
            label="调整相关费 $C_{adj}=\\Sigma[0.5p(b-q)^++1.5p(q-b)^+]$")
    ax1.bar(xpos, em_vals / 1e4, width=0.52, bottom=(plan_vals + adj_vals) / 1e4, color=WARNING,
            label="紧急购电费 $C_{em}=\\Sigma 5p\\,q_{em}$")
    for index, total in enumerate(totals):
        ax1.annotate(f"{total:,.0f} 元", xy=(index, total / 1e4), xytext=(0, 4), textcoords="offset points",
                     ha="center", fontsize=9.5)
        for part, base in ((adj_vals[index], plan_vals[index]), (em_vals[index], plan_vals[index] + adj_vals[index])):
            if part / 1e4 > 3.5:
                ax1.annotate(f"{part:,.0f}", xy=(index, (base + part / 2) / 1e4), ha="center", va="center",
                             fontsize=8.2, color="white")
    ax1.set_xticks(xpos)
    ax1.set_xticklabels(labels, fontsize=9)
    ax1.set_ylabel("费用 (万元)")
    ax1.set_ylim(0, totals.max() / 1e4 * 1.18)
    ax1.set_title("prob03 费用分解：$C_{total}=C_{plan}+C_{adj}+C_{em}$")
    ax1.legend(frameon=True, facecolor="white", edgecolor=NEUTRAL, framealpha=0.96, fontsize=8.6,
               loc="upper left", ncol=1)
    ax1.grid(axis="x", visible=False)

    b02 = p2["delivery_cost_yuan"] / 1e4
    b03_plan = delivery["cost_plan_yuan"] / 1e4
    b03_adj = delivery["cost_adj_yuan"] / 1e4
    b03_em = delivery["cost_em_yuan"] / 1e4
    ax2.bar([0], [b02], width=0.42, color=NEUTRAL, label="prob02 交付期（单阶段、用实际值）")
    ax2.bar([1], [b03_plan], width=0.42, color=PRIMARY, label="prob03 $C_{plan}$")
    ax2.bar([1], [b03_adj], width=0.42, bottom=[b03_plan], color=ACCENT, label="prob03 $C_{adj}$")
    ax2.bar([1], [b03_em], width=0.42, bottom=[b03_plan + b03_adj], color=WARNING, label="prob03 $C_{em}$")
    ax2.annotate(f"{b02:,.0f} 万元", xy=(0, b02), xytext=(0, 5), textcoords="offset points", ha="center", fontsize=9.5)
    total03 = b03_plan + b03_adj + b03_em
    ax2.annotate(f"{total03:,.0f} 万元", xy=(1, total03), xytext=(0, 5), textcoords="offset points", ha="center",
                 fontsize=9.5)
    delta_yuan = delivery["cost_total_yuan"] - p2["delivery_cost_yuan"]
    ax2.annotate(
        f"$\\Delta$ = +{delta_yuan:,.2f} 元（+{delta_yuan / p2['delivery_cost_yuan'] * 100:.3f}%）\n"
        f"两问交付期净负荷逐位相同：{p2['net_load_delivery_kwh']:,.2f} kWh\n"
        "结论：差额 = 预报误差的代价，不得表述为「问题 3 更省」",
        xy=(0.5, total03 * 0.58),
        ha="center",
        va="center",
        fontsize=8.6,
        color=WARNING,
        bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": WARNING, "alpha": 0.94},
    )
    ax2.set_xticks([0, 1])
    ax2.set_xticklabels(["prob02\n（题目 2，用实际值）", "prob03\n（题目 3，预报决策 + 实际结算）"], fontsize=9)
    ax2.set_ylabel("交付期总购电费 (万元)")
    ax2.set_ylim(0, total03 * 1.22)
    ax2.set_title("跨问对比：交付期总费用（团队勘误 R11）")
    ax2.legend(frameon=False, fontsize=8.4, loc="upper left")
    ax2.grid(axis="x", visible=False)

    return emit(
        fig,
        kind="cost_decomposition",
        title="prob03 费用分解与跨问交付期费用对比（含团队勘误 R11 披露）",
        x="cost_case",
        y=["cost_plan_yuan", "cost_adj_yuan", "cost_em_yuan", "delivery_cost_yuan"],
        caption=(
            "左：prob03 的交付期 $D_{req}$（2025-02-01…12-31，334 天）与全期 $D_{full}$（365 天）费用分解，"
            "三个分项由 run003 序列独立复算（$C_{plan}=\\Sigma p b$、$C_{adj}=\\Sigma[0.5p(b-q)^++1.5p(q-b)^+]$、"
            "$C_{em}=\\Sigma 5p q_{em}$），恒等式残差为 0。右：与 prob02 交付期的跨问对比，"
            "$\u0394$ 及各分项差额按 R11 如实披露 —— 两问交付期净负荷逐位相同，差额完全来自「问题 3 的决策只能用附件 3 预报、"
            "结算用附件 2 实际」的预报误差代价，论文不得声称问题 3 更省；主口径的计划层目标 $\\min\\Sigma p b$ 对紧急购电零预期"
            "（T6 撤销 PLAN-EXP），模型无对冲机制。全部费用取自 run003 与 prob02 run002 的 accepted 产物。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ---------------------------------------------------------------- 图 6：储电量轨迹
def figure_soc_trajectory(source_hash: str, source_data: str) -> dict:
    day_axis = np.arange(DAYS)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(FIG_W + 2.0, FIG_H + 2.6), layout="constrained",
                                   gridspec_kw={"height_ratios": [1.25, 1.0]})

    ax1.fill_between(day_axis, DATA["daily_storage_min"], DATA["daily_storage_max"], color=PRIMARY, alpha=0.22,
                     label="逐日储电量区间（min–max）")
    ax1.plot(day_axis, DATA["daily_storage_mean"], color=PRIMARY, lw=1.6, label="逐日储电量均值")
    ax1.axhline(E_MIN, color=WARNING, ls="--", lw=1.2, label=f"下界 {E_MIN:,.0f} kWh")
    ax1.axhline(E_MAX, color=WARNING, ls="-.", lw=1.2, label=f"上界 {E_MAX:,.0f} kWh")
    mark_delivery(ax1)
    mark_months(ax1)
    ax1.set_ylabel("储电量 $E$ (kWh)")
    finish_xlabel_days(ax1)
    ax1.set_title("全年储电量轨迹（逐日区间与均值）与运行上下界")
    ax1.legend(frameon=True, facecolor="white", edgecolor=NEUTRAL, framealpha=0.96, fontsize=8.6,
               loc="upper left", ncol=2)
    end_floor = int(np.sum(np.abs(DATA["daily_state_end"] - E_MIN) < 1e-6))
    p3_start = float(DATA["daily_state_start"][DELIVERY_START_DAY])
    p2_start = float(DATA["prob02"]["state_start_delivery_kwh"])
    ax1.annotate(
        f"$E_{{\\min}}$ = {DATA['storage'].min():,.2f} kWh、$E_{{\\max}}$ = {DATA['storage'].max():,.2f} kWh；"
        f"逐日末端均取下界 {E_MIN:,.0f} kWh（{end_floor}/{DAYS} 天，AS04 终端自由在逐日分层求解下的结构性后果）\n"
        f"2025-02-01 0:00（日初，$E_{{d,0}}$）：prob03 = {p3_start:,.2f} kWh（下界），"
        f"prob02 同日 = {p2_start:,.2f} kWh；信息集不同，不可互比（团队勘误 R13）",
        xy=(0.99, 0.03),
        xycoords="axes fraction",
        ha="right",
        va="bottom",
        fontsize=8.2,
        color=NEUTRAL,
        bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": NEUTRAL, "alpha": 0.94},
    )

    for day, color, label in (
        (DELIVERY_START_DAY, PRIMARY, "2025-02-01（交付期首日）"),
        (SPEC_DAYS["2025-06-21"], ACCENT, "2025-06-21（夏至）"),
    ):
        ax2.plot(PERIOD_CENTER_H, DATA["storage"][day * SEGMENTS_PER_DAY : (day + 1) * SEGMENTS_PER_DAY],
                 color=color, lw=1.8, label=label)
    ax2.axhline(E_MIN, color=WARNING, ls="--", lw=1.1)
    ax2.axhline(E_MAX, color=WARNING, ls="-.", lw=1.1)
    ax2.set_xlim(0, 24)
    ax2.set_xticks(range(0, 25, 4))
    ax2.set_ylim(600, E_MAX + 1400)
    ax2.set_xlabel("计划窗时刻 (h)（AS01 位置口径 0:10 → 24:10）")
    ax2.set_ylabel("储电量 $E$ (kWh)")
    ax2.set_title("两个代表日的日内储电量轨迹（跨日滚动递推：$E_{d,0}=E_{d-1,144}$）")
    ax2.legend(frameon=True, facecolor="white", edgecolor=NEUTRAL, framealpha=0.96, fontsize=9, loc="upper right")
    ax2.annotate(
        "两个代表日均自下界 1,200 kWh 起步、日末回到 1,200 kWh；\n"
        "表 2 端点语义为逐日切片、随日变化，与 prob01 单日周期恒 6,000 kWh 显式区分（团队勘误 R1）",
        xy=(0.02, 0.965),
        xycoords="axes fraction",
        ha="left",
        va="top",
        fontsize=8.4,
        color=NEUTRAL,
        bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": NEUTRAL, "alpha": 0.94},
    )
    return emit(
        fig,
        kind="soc_trajectory",
        title="prob03 储电量轨迹与上下界（全年与代表日）",
        x="day_index_or_time_of_day_h",
        y=["storage_kwh", "daily_storage_min_kwh", "daily_storage_max_kwh"],
        caption=(
            "上：全年逐日储电量区间（min–max 带）与均值，红色虚/点线为题面附录 1 的运行上下界 1,200 / 10,800 kWh；"
            "下：交付期首日（2025-02-01）与夏至日的日内轨迹（位置口径 0:10 → 24:10）。约束 $1200\\leq E\\le 10800$ "
            "逐时段满足（残差为求解器容差量级）。跨日状态连续 $E_{d,0}=E_{d-1,144}$（滚动递推，AS03），终端自由（AS04）；"
            f"由于计划层/调整层按日求解且日末状态自由，逐日末端 E 一律取下界 1,200 kWh（{int(np.sum(np.abs(DATA['daily_state_end'] - E_MIN) < 1e-6))}/{DAYS} 天），"
            "储能在日内完成大幅充放循环（日均区间约 1,200–10,800 kWh），这是交付期首日 0:00（日初 $E_{d,0}$）"
            f"即处于下界的原因（团队勘误 R13：prob03 = {DATA['daily_state_start'][DELIVERY_START_DAY]:,.0f} kWh、"
            f"prob02 = {DATA['prob02']['state_start_delivery_kwh']:,.0f} kWh，信息集不同、不可直接互比；表 2 端点语义为逐日切片，R1）。",
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ---------------------------------------------------------------- 图 7：紧急购电分布与 R12 机制示例
def figure_emergency_profile(source_hash: str, source_data: str) -> dict:
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(FIG_W + 2.0, FIG_H + 3.6), layout="constrained",
                                        gridspec_kw={"height_ratios": [1.1, 1.0, 1.0]})
    day_axis = np.arange(DAYS)
    daily_qem = DATA["daily_q_em"]
    delivery_mean = daily_qem[DELIVERY_START_DAY:].mean()
    ax1.bar(day_axis, daily_qem, width=1.0, color=WARNING, alpha=0.72, label="逐日 $\\Sigma_t q_{em}$")
    ax1.axhline(delivery_mean, color=PRIMARY, ls="--", lw=1.3, label=f"交付期日均 {delivery_mean:,.1f} kWh/日")
    mark_delivery(ax1)
    mark_months(ax1)
    ax1.set_ylabel("紧急购电量 (kWh/日)")
    finish_xlabel_days(ax1)
    ax1.set_title(
        f"逐日紧急购电量：{solution_day_with_em():,} 天全部有紧急购电，$\\Sigma q_{{em}}$ = "
        f"{DATA['q_em'].sum():,.1f} kWh（全期）"
    )
    ax1.legend(frameon=True, facecolor="white", edgecolor=NEUTRAL, framealpha=0.96, fontsize=8.8, loc="upper left")

    hours = np.arange(24)
    bars = ax2.bar(hours, DATA["q_em_hourly"] / 1000.0, width=0.78, color=ACCENT, alpha=0.9)
    for rect, hour in zip(bars, hours):
        count = DATA["q_em_hour_count"][hour]
        if count:
            ax2.annotate(f"{count:,}", xy=(hour, rect.get_height()), xytext=(0, 2), textcoords="offset points",
                         ha="center", fontsize=7.6, color=NEUTRAL)
    ax2.set_xticks(range(0, 24, 2))
    ax2.set_xlabel("小时块（第 h 小时 = 位置 6h+1…6h+6，AS01 位置口径）")
    ax2.set_ylabel("紧急购电量 (MWh)")
    ax2.set_ylim(0, DATA["q_em_hourly"].max() / 1000.0 * 1.16)
    ax2.set_title("紧急购电量的日内小时分布（柱顶数字 = 该小时触发 q_em>0 的时段计数，共 "
                  f"{int(DATA['q_em_hour_count'].sum()):,} 个时段）")
    ax2.grid(axis="x", visible=False)

    house = 0
    local = np.arange(30, 60)
    charge = DATA["charge"][house * SEGMENTS_PER_DAY : (house + 1) * SEGMENTS_PER_DAY][local]
    q_em = DATA["q_em"][house * SEGMENTS_PER_DAY : (house + 1) * SEGMENTS_PER_DAY][local]
    # AS01 位置口径：时段 i（1..144）= [10(i−1), 10i) min ⇔ 0 基索引 j 的左端点 = 10j 分钟
    labels = [f"{(idx * 10) // 60}:{(idx * 10) % 60:02d}" for idx in local]
    width = 0.4
    ax3.bar(np.arange(local.size) - width / 2, charge, width=width, color=PRIMARY, label="普通购电支付的充电量 $c$")
    ax3.bar(np.arange(local.size) + width / 2, q_em, width=width, color=WARNING, label="紧急购电量 $q_{em}$")
    example = 38  # 2025-01-01 6:20–6:30（团队勘误 R12 的示例时段）
    ax3.axvspan(example - 30 - 0.5, example - 30 + 0.5, color=WARNING, alpha=0.12)
    ax3.annotate(
        f"R12 示例：6:20–6:30（$c$={charge[example - 30]:.3f}、$q_{{em}}$={q_em[example - 30]:.3f} kWh/10min）",
        xy=(example - 30, charge[example - 30]),
        xytext=(example - 30 + 5.5, charge[example - 30] + 90),
        fontsize=8.0,
        color=WARNING,
        arrowprops={"arrowstyle": "->", "color": WARNING, "lw": 1.0},
        bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": WARNING, "alpha": 0.94},
    )
    ax3.set_xticks(np.arange(local.size))
    ax3.set_xticklabels(labels, rotation=90, fontsize=7.4)
    ax3.set_xlabel("时段左端点（2025-01-01，AS01 位置口径）")
    ax3.set_ylabel("电量 (kWh/10min)")
    ax3.set_title("团队勘误 R12 最小可复现示例：2025-01-01 6:20–6:30 等时段 $q_{em}>0$ 与 $c>0$ 同时成立")
    ax3.legend(frameon=True, facecolor="white", edgecolor=NEUTRAL, framealpha=0.96, fontsize=8.6, loc="upper left")
    ax3.grid(axis="x", visible=False)
    ax3.annotate(
        "LP 中不违反 D7-A：$c$ 由普通购电 $q$ 支付，$q_{em}$ 只补负载缺口；\n"
        "机制 = 决策层用预报定下 $(q,c)$ + 结算层用附件 2 实际算缺口。\n"
        f"全期这类时段共 {DATA['solution']['statistics']['periods_with_q_em_and_charge']:,} 个"
        f"（占 {DATA['solution']['statistics']['periods_with_q_em_and_charge'] / TOTAL * 100:.1f}%）。",
        xy=(0.99, 0.96),
        xycoords="axes fraction",
        ha="right",
        va="top",
        fontsize=8.2,
        color=NEUTRAL,
        bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": NEUTRAL, "alpha": 0.94},
    )
    return emit(
        fig,
        kind="emergency_profile",
        title="prob03 紧急购电的逐日与日内分布（含 R12 机制示例）",
        x="day_index_and_hour",
        y=["daily_q_em_kwh", "hourly_q_em_kwh", "charge_kwh", "q_em_kwh"],
        caption=(
            "上：逐日紧急购电量与交付期日均线；中：紧急购电量的日内小时分布（柱顶数字为该小时触发 $q_{em}>0$ 的时段数，"
            "全期共 12,164 个时段、365 天全部触发）；下：团队勘误 R12 要求的最小可复现示例 —— 2025-01-01 6:20–6:30 "
            "等时段 $q_{em}>0$ 与 $c>0$ 同时成立，机制为「决策层用预报定 $(q,c)$ + 结算层用实际算缺口」，"
            "普通购电支付的充电与紧急购电分属两层，不违反 D7-A 的『$q_{em}$ 不用于储能充电』。"
            "X 轴为自然日索引（0 = 2025-01-01）；小时块按 AS01 位置口径（第 h 小时 = [h:00, h+1:00) 共 6 个时段）。",
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


def solution_day_with_em() -> int:
    return int(DATA["solution"]["statistics"]["days_with_emergency"])


# ---------------------------------------------------------------- 图 8：T7-3 退化披露
def figure_tiebreak_degeneracy(source_hash: str, source_data: str) -> dict:
    per_layer = DATA["tiebreak"]
    summary = DATA["solution"]["t7_tiebreak"]
    rel = np.array([float(item["primary_relative_change"]) for item in per_layer])
    deg = np.array([float(item["degeneracy_degree"]) for item in per_layer])
    kind = np.array([item["layer"] for item in per_layer])
    unique = np.array([item.get("throughput_unique") for item in per_layer], dtype=object)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(FIG_W + 3.0, FIG_H + 1.2), layout="constrained")

    layer_index = np.arange(rel.size)
    ax1.scatter(layer_index[kind == "plan"], rel[kind == "plan"], s=7, color=PRIMARY, alpha=0.8,
                label=f"计划层（{int((kind == 'plan').sum())} 层）")
    ax1.scatter(layer_index[kind == "adjustment"], rel[kind == "adjustment"], s=4, color=ACCENT, alpha=0.45,
                label=f"调整层（{int((kind == 'adjustment').sum())} 层）")
    ax1.axhline(1e-9, color=WARNING, ls="--", lw=1.4, label="T7-2 容差 $10^{-9}$")
    ax1.axhline(summary["max_primary_relative_change"], color=NEUTRAL, lw=1.0,
                label=f"实测最大 {summary['max_primary_relative_change']:.4e}")
    ax1.set_yscale("log")
    ax1.set_ylim(1e-13, 3e-9)
    ax1.set_xlabel("层序号（0–364 计划层；365–1459 调整层）")
    ax1.set_ylabel("加入次目标前后主目标相对变化（逐层，对数轴）")
    ax1.set_title("T7-2 不变性验证：1,460 层全部落在容差内")
    ax1.legend(frameon=True, facecolor="white", edgecolor=NEUTRAL, framealpha=0.96, fontsize=8.6,
               loc="lower left")
    ax1.grid(axis="x", visible=False)
    ax1.annotate(
        f"通过 {int(np.sum(rel <= 1e-9)):,} / {rel.size:,} 层；"
        f"$\\min$ = {rel.min():.3e}、$\\max$ = {rel.max():.3e}、中位数 = {np.median(rel):.3e}\n"
        f"全部落在 5.0e-10 ± {0.5 * (rel.max() - rel.min()):.1e} 的窄带内，故散点近似水平（每层 ε 随该层主目标自适应，见 T9）",
        xy=(0.99, 0.03),
        xycoords="axes fraction",
        ha="right",
        va="bottom",
        fontsize=8.2,
        color=NEUTRAL,
        bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": NEUTRAL, "alpha": 0.94},
    )

    plan_deg = deg[kind == "plan"]
    adj_deg = deg[kind == "adjustment"]
    bins2 = np.arange(0, deg.max() + 12, 12)
    ax2.hist([plan_deg, adj_deg], bins=bins2, stacked=True, color=[PRIMARY, ACCENT],
             label=[f"计划层（{plan_deg.size} 层）", f"调整层（{adj_deg.size} 层）"])
    ax2.set_xlabel("退化度 = 活跃约束数 − 变量数（逐层）")
    ax2.set_ylabel("层数")
    unique_true = int(sum(1 for item in unique if item is True))
    unique_false = int(sum(1 for item in unique if item is False))
    unique_none = int(sum(1 for item in unique if item is None))
    ax2.set_title("T7-3 退化与多重最优：逐层退化度分布")
    ax2.legend(frameon=True, facecolor="white", edgecolor=NEUTRAL, framealpha=0.96, fontsize=8.8,
               loc="upper right")
    ax2.grid(axis="x", visible=False)
    fig.text(
        0.5,
        -0.035,
        "T7-3/E7 披露：退化层 "
        f"{summary['degenerate_layers']:,} / {len(per_layer):,}，最大退化度 {summary['max_degeneracy_degree']}；"
        f"最优面吞吐量唯一性 True {unique_true} / False {unique_false} / None {unique_none}；"
        f"提交解 = T9 字典序（主目标最优面上吞吐量最小）{summary['lexicographic_committed_layers']:,} 层、"
        f"fallback = {summary['fallback_committed_layers']}。\n"
        "唯一 None 层 = 2025-10-12 18:00 调整层（该层主目标为 0，ε = 1.754e-11 低于 HiGHS 对偶分辨率，"
        "属探测能力边界，不构成缺陷）。T7-6：主结果对 tie-break 的量级敏感性约 1e-4 相对量级，"
        "所有模型与 run 一律用同一规则，不得用不同 tie-break 的结果互相比对。",
        ha="center",
        va="top",
        fontsize=8.2,
        color=NEUTRAL,
        bbox={"boxstyle": "round,pad=0.4", "fc": "white", "ec": NEUTRAL, "alpha": 0.96},
    )
    return emit(
        fig,
        kind="tiebreak_degeneracy",
        title="prob03 tie-breaking 不变性、LP 退化与多重最优的逐层披露（T7-2/T7-3/E7）",
        x="layer_index",
        y=["primary_relative_change", "degeneracy_degree", "throughput_unique"],
        caption=(
            "左：加入 T7-1 次目标（$\\varepsilon\\cdot\\Sigma(c+q_{dis})$）前后主目标相对变化的逐层分布，"
            "最大 5.000e-10 ≤ 容差 1e-9，1,460/1,460 层通过不变性验证；右：逐层退化度（活跃约束数 − 变量数）分布，"
            "按计划层/调整层分解。1,460 层全部退化，最大退化度 228；最优面吞吐量唯一性 True 435 / False 1,024 / None 1。"
            "提交解一律取 T9 的字典序规则（主目标最优面上吞吐量最小，1,460 层全部按字典序提交、fallback = 0）；"
            "唯一无法判定重数的层为 2025-10-12 18:00 调整层，因该层主目标为 0 使 ε 低于 HiGHS 对偶分辨率，"
            "属探测能力边界、不构成缺陷（团队勘误 E7）。T7-6：主结果对 tie-break 选择的量级敏感性约 1e-4 相对量级，"
            "所有模型与所有 run 一律使用同一规则，不得用不同 tie-break 的结果互相比对。",
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


def main() -> int:
    solution, tables, run_manifest, tiebreak = load_results()
    DATA["solution"] = solution
    DATA["tables"] = tables
    DATA["run_manifest"] = run_manifest
    DATA["tiebreak_raw"] = tiebreak
    derive()

    solution_hash = hash_path(SOLUTION_PATH)
    tables_hash = hash_path(TABLES_PATH)
    tiebreak_hash = hash_path(TIEBREAK_PATH)
    chain_hash = combined_hash(SOLUTION_PATH, ATT2_PATH, ATT3_PATH)
    cross_hash = combined_hash(SOLUTION_PATH, PROB02_SOLUTION)
    diag_hash = combined_hash(SOLUTION_PATH, TIEBREAK_PATH)

    solution_rel = relative(SOLUTION_PATH)
    tables_rel = relative(TABLES_PATH)
    chain_rel = f"{solution_rel} + {relative(ATT2_PATH)} + {relative(ATT3_PATH)}"
    cross_rel = f"{solution_rel} + {relative(PROB02_SOLUTION)}"
    diag_rel = f"{solution_rel} + {relative(TIEBREAK_PATH)}"

    items = [
        figure_forecast_chain(chain_hash, chain_rel),
        figure_plan_adjust_profile(solution_hash, solution_rel),
        figure_adjust_surface_3d(solution_hash, solution_rel),
        figure_adjust_heatmap_2d(solution_hash, solution_rel),
        figure_cost_decomposition(cross_hash, cross_rel),
        figure_soc_trajectory(solution_hash, solution_rel),
        figure_emergency_profile(solution_hash, solution_rel),
        figure_tiebreak_degeneracy(diag_hash, diag_rel),
    ]

    removed = prune_stale_figures({item["stable_id"] for item in items})

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "problem_id": PROBLEM_ID,
        "question_id": QUESTION_ID,
        "assumption_version": ASSUMPTION_VERSION,
        "formulation_version": FORMULATION_VERSION,
        "task_id": TASK_ID,
        "run": relative(RESULT_DIR),
        "font": FONT,
        "dpi": DPI,
        "source_solution_hash": solution_hash,
        "source_tables_hash": tables_hash,
        "source_tiebreak_hash": tiebreak_hash,
        "figure_count": len(items),
        "removed_stale_registrations": removed,
        "figures": [
            {
                "stable_id": item["stable_id"],
                "kind": item["kind"],
                "path": item["path"],
                "quality_status": item["quality_status"],
                "source_data": item["source_data"],
            }
            for item in items
        ],
        "diagnostics": {
            "cost_recomputed": DATA["recomputed_cost"],
            "cost_reported": {
                "plan": solution["cost_plan_yuan"],
                "adj": solution["cost_adj_yuan"],
                "em": solution["cost_em_yuan"],
                "total": solution["objective_yuan"],
                "delivery_total": solution["delivery"]["cost_total_yuan"],
            },
            "adjustment": {
                "up_periods": DATA["up_periods"],
                "down_periods": DATA["down_periods"],
                "sum_full_kwh": float(DATA["delta"].sum()),
                "sum_delivery_kwh": float(DATA["delta"][DATA["delivery_mask"]].sum()),
            },
            "prob02": DATA["prob02"],
            "checks_failed": DATA["checks_failed"],
        },
    }
    write_json(FIG_DIR / "generation_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
