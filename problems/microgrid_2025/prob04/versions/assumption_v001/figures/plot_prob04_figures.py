# ruff: noqa: E501 —— 本文件含大量中文图注/说明长字符串（caption 与图内注记逐字对应），折行会改变可读性，故按文件豁免行长规则。
"""prob04 正式图表生成脚本（assumption_v001 / formulation_v001 / 两链 run002）。

- 只读消费 accepted 版本的两条链正式计算结果
  （solution.json / tables.json / run_manifest.json / solver_status.json / forecast_backtest.json / tiebreak_audit.json），
  不改数据、不改模型、不新建 task。
- 统一从 config/visualization.yaml 读取字体、色板、尺寸、DPI 与质检阈值。
- 每图使用 automm.visualization.stable_figure_id 生成稳定 ID，文件名不依赖易变图号。
- 自动质检 inspect_png 写 *.quality.json；manifest 登记到 problems/microgrid_2025/figures.yaml。
- 视觉复核状态由 Agent 通过 record_figure_review 命令写入（本脚本先登记为 pending）。

纪律（prob04 阶段级强制要求与团队勘误）：
  1. 一道小问两套结果：凡结论性图件必须显式指明是 4-2 还是 4-3 链，不得混为一条；
  2. A8-(b) 派生⑤：图内文字与图注不得出现「全天电价已知」类表述；
     决策层用预测价（4-3 调整层用 kappa_m 滚动更新的预测价），结算层一律用附件 4 实际价；
  3. E-F5：凡引用「预报误差」处同时给出 MAE、MAPE 与 P90（或 P99），禁止只报单一指标；
  4. N1 更正：kappa_m in [0.6623297807778713, 1.5493928472727483]（不得再用 [0.50133, ...]）；
  5. E-F2：p_min 解析下界极松、深谷时段 5x 紧急价仅 0.038 元/kWh，须披露；
  6. D11/D12：LP 退化与 tie-break 敏感性如实登记，不以逐点解唯一性作判据。

运行（项目根目录）：
    .venv\\Scripts\\python.exe problems/microgrid_2025/prob04/versions/assumption_v001/figures/plot_prob04_figures.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
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

from automm.common import config_section, hash_path, read_yaml, relative, write_json, write_yaml  # noqa: E402
from automm.visualization import inspect_png, register_figure, stable_figure_id  # noqa: E402

PROBLEM_ID = "microgrid_2025"
QUESTION_ID = "prob04"
ASSUMPTION_VERSION = "assumption_v001"
FORMULATION_VERSION = "formulation_v001"
ACTION_ID = "act-a752e4172fdd43b4"

RESULT_DIRS = {
    "4-2": FIG_DIR.parent / "results" / "prob04_v001_f001_4-2_run002",
    "4-3": FIG_DIR.parent / "results" / "prob04_v001_f001_4-3_run002",
}
TASK_IDS = {"4-2": "892351beefa2bc5f7804", "4-3": "eca261e1d516ab2867d9"}
TASK_BOTH = f"{TASK_IDS['4-2']}+{TASK_IDS['4-3']}"

DAYS = 365
SEG = 144
TOTAL = DAYS * SEG
DT_H = 1.0 / 6.0
DELIVERY_START = 31  # 2025-02-01（0 基日索引），交付期 D_req = 334 天
ALPHA_EM, BETA_DEF, BETA_OVER = 5.0, 0.5, 1.5
E_MIN, E_MAX, E_INIT = 1200.0, 10800.0, 6000.0
LOCK = {0: 0, 6: 36, 12: 72, 18: 108}
KAPPA_LO, KAPPA_HI = 0.5, 2.0
SPEC_DAYS = {"2025-03-20": 78, "2025-06-21": 171, "2025-09-23": 265, "2025-12-21": 354}
DAY0 = date(2025, 1, 1)
MONTH_TICKS = [(date(2025, m, 1) - DAY0).days for m in range(1, 13)]
MONTH_LABELS = [f"{m} 月" for m in range(1, 13)]
PERIOD_CENTER_H = (np.arange(SEG) + 0.5) * DT_H
# 落盘 series.storage_kwh 的第 d 日切片为 E_{d,1}…E_{d,144}（时段末状态），不含 E_{d,0}；
# 日内轨迹必须把 E_{d,0}（daily.state_start_kwh，= 前一日末态）前置，x 用时段端点。
PERIOD_EDGE_H = np.arange(SEG + 1) * DT_H

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

CHAIN_COLOR = {"4-2": PRIMARY, "4-3": ACCENT}


def select_font() -> str:
    available = {font.name for font in font_manager.fontManager.ttflist}
    candidates = [STYLE.get("preferred_font"), *STYLE.get("fallback_fonts", [])]
    for candidate in candidates:
        if candidate and candidate in available:
            return str(candidate)
    raise RuntimeError("未找到任何配置中的中文字体，拒绝出图（避免方框字符）。")


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
def load_chain(chain: str) -> dict:
    directory = RESULT_DIRS[chain]
    solution = json.loads((directory / "solution.json").read_text(encoding="utf-8"))
    solution["series"] = {
        key: np.asarray(values, dtype=float)
        for key, values in solution["series"].items()
        if isinstance(values, list) and len(values) == TOTAL
    }
    return {
        "dir": directory,
        "solution": solution,
        "tables": json.loads((directory / "tables.json").read_text(encoding="utf-8")),
        "manifest": json.loads((directory / "run_manifest.json").read_text(encoding="utf-8")),
        "solver": json.loads((directory / "solver_status.json").read_text(encoding="utf-8")),
        "backtest": json.loads((directory / "forecast_backtest.json").read_text(encoding="utf-8")),
        "tiebreak": json.loads((directory / "tiebreak_audit.json").read_text(encoding="utf-8")),
    }


DATA: dict = {}


def day_slice(day: int) -> np.s_[...]:
    return np.s_[day * SEG : (day + 1) * SEG]


def day_storage(chain: str, day: int) -> np.ndarray:
    """当日完整储电量轨迹 E_{d,0}, E_{d,1}, …, E_{d,144}（145 点，对应 PERIOD_EDGE_H）。"""
    blob = DATA["chains"][chain]["d"]
    start = float(np.asarray(blob["daily"]["state_start_kwh"], dtype=float)[day])
    return np.concatenate(([start], blob["storage"][day_slice(day)]))


def mark_months(ax: plt.Axes) -> None:
    for pos in MONTH_TICKS[1:]:
        ax.axvline(pos, color=NEUTRAL, lw=0.7, ls=":", alpha=0.5)
    ax.set_xticks(MONTH_TICKS)
    ax.set_xticklabels(MONTH_LABELS)


def mark_delivery(ax: plt.Axes) -> None:
    ax.axvline(DELIVERY_START, color=WARNING, ls="--", lw=1.2, alpha=0.9)


def xlabel_days(ax: plt.Axes) -> None:
    ax.set_xlabel("日期（2025-01-01 → 2025-12-31；竖点线为月初；红虚线为 2025-02-01 交付期起点）")


def note(ax: plt.Axes, text: str, *, xy=(0.985, 0.97), ha="right", va="top", fontsize=7.6) -> None:
    ax.annotate(text, xy=xy, xycoords="axes fraction", ha=ha, va=va, fontsize=fontsize, color=NEUTRAL,
                bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": NEUTRAL, "alpha": 0.94})


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
    task_id: str,
    include_in_paper: bool = True,
) -> dict:
    figure_id = stable_figure_id(
        problem_id=PROBLEM_ID, question_id=QUESTION_ID, kind=kind, title=title,
        source_hash=source_hash, x=x, y=y, style=STYLE,
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
        "task_id": task_id,
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
    """清理 prob04 在 manifest 中已失效的登记项（稳定 ID 随图定义变化时会产生孤儿条目）。"""
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


# ---------------------------------------------------------------- 派生量与自检
def derive() -> None:
    """整理绘图用派生量，并做关键恒等式自检（任一失败即中止，防止图件与 accepted 口径脱钩）。"""
    for chain, blob in DATA["chains"].items():
        series = blob["solution"]["series"]
        daily = blob["solution"]["daily"]
        price = series["price_actual_yuan_per_kwh"]
        belief = series["price_belief_yuan_per_kwh"]
        plan = series["plan_purchase_kwh"]
        final = series["final_purchase_kwh"]
        q_em = series["q_em_kwh"]
        charge = series["charge_kwh"]
        discharge = series["discharge_kwh"]
        storage = series["storage_kwh"]
        load = series["load_energy_kwh"]
        pv = series["pv_actual_energy_kwh"]

        # 结算层缺口恒等式：r = q + q_dis + PV^act*Dt - L*Dt - c；q_em = max(0, -r)
        residual = final + discharge + pv - load - charge
        gap_check = float(np.max(np.abs(np.maximum(0.0, -residual) - q_em)))
        if gap_check > 1e-6:
            raise RuntimeError(f"{chain} 结算层缺口恒等式不成立：{gap_check}")

        d0 = DELIVERY_START * SEG
        dev_up = np.maximum(final - plan, 0.0)
        dev_down = np.maximum(plan - final, 0.0)
        c_plan = float(np.sum(price[d0:] * plan[d0:]))
        c_em = float(np.sum(ALPHA_EM * price[d0:] * q_em[d0:]))
        c_adj = (
            float(np.sum(price[d0:] * (BETA_DEF * dev_down[d0:] + BETA_OVER * dev_up[d0:])))
            if chain == "4-3" else 0.0
        )
        c_fc = float(np.sum(belief[d0:] * plan[d0:]))
        c_fc_em = float(np.sum(ALPHA_EM * belief[d0:] * q_em[d0:]))
        c_fc_adj = (
            float(np.sum(belief[d0:] * (BETA_DEF * dev_down[d0:] + BETA_OVER * dev_up[d0:])))
            if chain == "4-3" else 0.0
        )
        blob["d"] = {
            "price": price, "belief": belief, "plan": plan, "final": final, "q_em": q_em,
            "charge": charge, "discharge": discharge, "storage": storage, "load": load, "pv": pv,
            "dev_up": dev_up, "dev_down": dev_down,
            "residual_negative": np.maximum(0.0, -residual),
            "daily": daily,
            "c_plan": c_plan, "c_adj": c_adj, "c_em": c_em,
            "c_total": c_plan + c_adj + c_em,
            "c_fc": c_fc + c_fc_adj + c_fc_em,
            "delta_c_price": (c_plan + c_adj + c_em) - (c_fc + c_fc_adj + c_fc_em),
            "delta_c_plan": c_plan - c_fc,
            "delta_c_adj": c_adj - c_fc_adj,
            "delta_c_em": c_em - c_fc_em,
            "up_kwh": float(np.sum(dev_up)),
            "adj_down_kwh": float(np.sum(dev_down)),
            "adj_up_periods": int(np.sum(dev_up > 1e-9)),
            "adj_down_periods": int(np.sum(dev_down > 1e-9)),
            "adj_equal_periods": int(np.sum(np.abs(final - plan) <= 1e-9)),
            "q_em_periods": int(np.sum(q_em > 1e-9)),
            "q_em_delivery_periods": int(np.sum(q_em[d0:] > 1e-9)),
            "q_em_delivery_days": int(np.sum(np.asarray(daily["q_em_kwh"])[DELIVERY_START:] > 1e-9)),
            "q_em_delivery_kwh": float(np.sum(q_em[d0:])),
            "price_mae_delivery": float(np.mean(np.abs(price[d0:] - belief[d0:]))),
            "gap_check": gap_check,
        }

    # 4-3 的 kappa_m 独立重建（kappa_m = A_m/B_m），并与落盘信念价逐位比对。
    p43 = DATA["chains"]["4-3"]["d"]["price"].reshape(DAYS, SEG)
    belief43 = DATA["chains"]["4-3"]["d"]["belief"]
    rebuilt = np.empty(TOTAL)
    rebuilt[:SEG] = 1.0
    rebuilt[SEG:] = p43[:-1].reshape(-1)
    kappa = {}
    fallback_day = np.ones(SEG)  # 2025-01-01：H_d 为空集，四层一律用常量中性价 1.0
    for m in (6, 12, 18):
        lock = LOCK[m]
        ks = np.ones(DAYS)
        for d in range(1, DAYS):
            a = float(np.mean(p43[d, :lock]))
            b = float(np.mean(p43[d - 1, :lock]))
            ks[d] = min(max(a / b, KAPPA_LO), KAPPA_HI) if b > 0 else 1.0
        kappa[m] = ks
        for d in range(DAYS):
            base = p43[d - 1] if d > 0 else fallback_day
            rebuilt[d * SEG + lock : (d + 1) * SEG] = ks[d] * base[lock:]
    kappa_err = float(np.max(np.abs(rebuilt - belief43)))
    if kappa_err > 1e-12:
        raise RuntimeError(f"kappa_m 独立重建与落盘信念价不一致：{kappa_err}")
    all_kappa = np.concatenate([kappa[6], kappa[12], kappa[18]])
    argmin = int(np.argmin(all_kappa))
    DATA["kappa"] = {
        "series": kappa,
        "all": all_kappa,
        "err": kappa_err,
        "min": float(all_kappa.min()),
        "max": float(all_kappa.max()),
        "clip_events": int(np.sum((all_kappa <= KAPPA_LO + 1e-12) | (all_kappa >= KAPPA_HI - 1e-12))),
        "argmin_m": (6, 12, 18)[argmin // DAYS],
        "argmin_day": argmin % DAYS,
    }

    # 4-3 逐时段支配决策层 nu(i)
    layer_of_period = np.zeros(SEG, dtype=int)
    for m in (6, 12, 18):
        layer_of_period[LOCK[m] :] = m
    DATA["layer_of_period"] = layer_of_period

    # 两链差额三分项归因
    a, b = DATA["chains"]["4-2"]["d"], DATA["chains"]["4-3"]["d"]
    DATA["cross"] = {
        "delta_total": b["c_total"] - a["c_total"],
        "delta_plan": b["c_plan"] - a["c_plan"],
        "delta_adj": b["c_adj"],
        "delta_em": b["c_em"],
    }
    DATA["cross"]["residual"] = DATA["cross"]["delta_total"] - (
        DATA["cross"]["delta_plan"] + DATA["cross"]["delta_adj"] + DATA["cross"]["delta_em"]
    )

    # 与 run_manifest.delivery 逐位自检
    for chain, blob in DATA["chains"].items():
        man = blob["manifest"]["delivery"]
        checks = {
            "cost_total": (blob["d"]["c_total"], man["cost_total_yuan"]),
            "cost_plan": (blob["d"]["c_plan"], man["cost_plan_yuan"]),
            "cost_adj": (blob["d"]["c_adj"], man["cost_adj_yuan"]),
            "cost_em": (blob["d"]["c_em"], man["cost_em_yuan"]),
            "cost_fc": (blob["d"]["c_fc"], man["cost_total_fc_yuan"]),
            "delta_c_price": (blob["d"]["delta_c_price"], man["delta_c_price_yuan"]),
        }
        for name, (got, want) in checks.items():
            if abs(got - want) > 1e-6:
                raise RuntimeError(f"{chain} {name} 与 run_manifest 不一致：{got} vs {want}")


# ---------------------------------------------------------------- 图 1：价格信念链（两链）
def figure_price_belief_chain(source_hash: str, source_data: str, task_id: str) -> dict:
    days = [DELIVERY_START, SPEC_DAYS["2025-06-21"]]
    labels = ["2025-02-01（交付期首日）", "2025-06-21（夏至）"]
    fig, axes = plt.subplots(2, 2, figsize=(FIG_W + 3.6, FIG_H + 3.0), layout="constrained")
    handles = None
    for column, (day, label) in enumerate(zip(days, labels)):
        ax = axes[0][column]
        actual = DATA["chains"]["4-2"]["d"]["price"][day_slice(day)]
        plan_belief = DATA["chains"]["4-2"]["d"]["belief"][day_slice(day)]
        layer_belief = DATA["chains"]["4-3"]["d"]["belief"][day_slice(day)]
        ax.plot(PERIOD_CENTER_H, actual, color="black", lw=2.0, label="附件 4 实际价（结算层唯一价格）")
        ax.plot(PERIOD_CENTER_H, plan_belief, color=PRIMARY, lw=1.5, ls="--",
                label="计划层信念价（两链共用 = 前一日同时段）")
        ax.plot(PERIOD_CENTER_H, layer_belief, color=ACCENT, lw=1.5,
                label="链 4-3 逐层信念价（滚动水平校正）")
        for hour in (6, 12, 18):
            ax.axvline(hour, color=NEUTRAL, lw=0.8, ls=":", alpha=0.7)
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 4))
        ax.set_ylabel("电价 (元/kWh)")
        ax.set_title(f"{label}：决策价与结算价")
        note(ax, "竖点线 = 6:00 / 12:00 / 18:00 调整时刻", xy=(0.985, 0.03), va="bottom", fontsize=7.2)
        if handles is None:
            handles, legend_labels = ax.get_legend_handles_labels()

    ax = axes[1][0]
    sample = np.arange(0, TOTAL, 7)
    layer_index = np.tile(DATA["layer_of_period"], DAYS)[sample]
    belief43 = DATA["chains"]["4-3"]["d"]["belief"][sample]
    actual43 = DATA["chains"]["4-3"]["d"]["price"][sample]
    layer_colors = {0: PRIMARY, 6: SECONDARY, 12: ACCENT, 18: WARNING}
    for m in (0, 6, 12, 18):
        mask = layer_index == m
        ax.scatter(actual43[mask], belief43[mask], s=2.6, alpha=0.32, color=layer_colors[m],
                   edgecolors="none", label=f"支配层 m={m}" + ("（计划层）" if m == 0 else ""))
    lim = [0.0, float(np.nanmax(actual43)) * 1.02]
    ax.plot(lim, lim, color="black", lw=1.1, ls="--", label="45 度参考（预测 = 实际）")
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_xlabel("附件 4 实际价 (元/kWh)")
    ax.set_ylabel("链 4-3 信念价 (元/kWh)")
    ax.set_title("链 4-3：信念价 vs 实际价（按支配决策层着色）")
    ax.legend(loc="upper left", fontsize=7.4, markerscale=2.4, framealpha=0.92)

    ax = axes[1][1]
    for chain in ("4-2", "4-3"):
        err = np.abs(DATA["chains"][chain]["d"]["price"][DELIVERY_START * SEG :]
                     - DATA["chains"][chain]["d"]["belief"][DELIVERY_START * SEG :])
        ax.hist(err, bins=120, range=(0.0, 0.8), histtype="step", lw=1.7, color=CHAIN_COLOR[chain],
                label=f"链 {chain}：MAE {np.mean(err):.5f} / P90 {np.percentile(err, 90):.4f} "
                      f"/ P99 {np.percentile(err, 99):.4f} 元/kWh")
    ax.set_xlabel("交付期逐时段绝对价格误差 (元/kWh)")
    ax.set_ylabel("时段数（交付期 48,096 时段）")
    ax.set_title("决策—结算分离的代价来源：价格信念误差分布（两链）")
    ax.legend(loc="upper right", fontsize=7.6, framealpha=0.92)
    note(
        ax,
        "0:00 制定计划时当天电价尚不可知：\n"
        "决策层只用历史价（≤ 前一日 144 点），结算层一律用附件 4 实际价。\n"
        "链 4-3 的 6:00/12:00/18:00 调整层用滚动更新的预测价（水平校正）。",
        xy=(0.985, 0.60), fontsize=7.4,
    )

    fig.legend(handles, legend_labels, loc="lower center", bbox_to_anchor=(0.5, -0.05), ncol=3, frameon=False,
               fontsize=8.6)
    fig.suptitle("prob04 价格信息结构：决策层预测价与结算层实际价的分离（两链）", fontsize=13)
    return emit(
        fig,
        kind="price_belief_chain",
        title="prob04 价格信念链：决策层预测价与结算层实际价的分离（两链分别标注）",
        x="time_of_day_h / price_actual_yuan_per_kwh",
        y=["price_belief_yuan_per_kwh", "price_actual_yuan_per_kwh"],
        caption=(
            "上排：交付期首日 2025-02-01 与夏至 2025-06-21 的日内电价——黑实线 = 附件 4 实际价 $p^{act}$（结算层唯一价格入口，"
            "`AS09`/`AS14`）；蓝虚线 = 计划层信念价 $\\hat p^{(0)}$（两链共用，`PF-PERSIST` = 前一日同时段）；"
            "橙线 = 链 `4-3` 的逐层信念价 $\\hat p^{(\\nu(i))}$（`AS11`：$i\\leq 6m$ 用当日已实现实际价、"
            "$i>6m$ 用 $\\kappa_m\\cdot p^{act}_{d-1,i}$），竖点线为 6:00/12:00/18:00 调整时刻。"
            "下排左：链 `4-3` 全部 52,560 时段的（实际价, 信念价）散点（每 7 时段抽 1 点），按支配决策层 $m$ 着色，"
            "45 度线为完全预知参考；下排右：两链交付期逐时段绝对价格误差直方图"
            "（`E-F5` 要求同时给出 MAE/MAPE 与分位数，此处给 MAE/P90/P99）。"
            "交付期价格 MAE：`4-2` = %.8f、`4-3` = %.8f 元/kWh（`4-3` 因调整层消费当日已实现价而更低）。"
            "**本图不含任何「当天电价已知」口径**：0:00 时当天实时电价不可知，价格不确定性只体现在费用"
            "（$\\Delta C_{price}$），不产生 `4-2` 的能量缺口。数据来源：assumption_v001 / formulation_v001 / "
            "两链 task %s & %s / run002。"
            % (
                DATA["chains"]["4-2"]["d"]["price_mae_delivery"],
                DATA["chains"]["4-3"]["d"]["price_mae_delivery"],
                TASK_IDS["4-2"],
                TASK_IDS["4-3"],
            )
        ),
        source_hash=source_hash,
        source_data=source_data,
        task_id=task_id,
    )


# ---------------------------------------------------------------- 图 2：预测器滚动回测
def figure_forecast_backtest(source_hash: str, source_data: str, task_id: str) -> dict:
    metrics = DATA["chains"]["4-2"]["backtest"]["windows"]["D_req"]["metrics"]
    order = ["PF-PERSIST", "PF-DUAL", "PF-HIST", "PF-AR"]
    colors = [PRIMARY, SECONDARY, ACCENT, NEUTRAL]
    name_map = {
        "PF-PERSIST": "PF-PERSIST\n（主口径）",
        "PF-DUAL": "PF-DUAL\n（强制基准）",
        "PF-HIST": "PF-HIST\n（强制基准）",
        "PF-AR": "PF-AR\n（仅 ablation）",
    }
    fig, axes = plt.subplots(1, 2, figsize=(FIG_W + 3.2, FIG_H + 0.6), layout="constrained")

    ax = axes[0]
    x = np.arange(len(order))
    width = 0.36
    mae = [metrics[k]["mae"] for k in order]
    mape = [metrics[k]["mape"] * 100 for k in order]
    bars1 = ax.bar(x - width / 2, mae, width, color=PRIMARY, alpha=0.92, label="MAE (元/kWh)")
    ax2 = ax.twinx()
    bars2 = ax2.bar(x + width / 2, mape, width, color=ACCENT, alpha=0.85, label="MAPE (%)")
    ax.set_xticks(x)
    ax.set_xticklabels([name_map[k] for k in order], fontsize=8.2)
    ax.set_ylabel("MAE (元/kWh)")
    ax2.set_ylabel("MAPE (%)")
    ax2.grid(False)
    for bar, value in zip(bars1, mae):
        ax.annotate(f"{value:.5f}", (bar.get_x() + bar.get_width() / 2, value), textcoords="offset points",
                    xytext=(0, 3), ha="center", fontsize=8.0)
    for bar, value in zip(bars2, mape):
        ax2.annotate(f"{value:.2f}%", (bar.get_x() + bar.get_width() / 2, value), textcoords="offset points",
                     xytext=(0, 3), ha="center", fontsize=8.0, color=ACCENT)
    ax.set_ylim(0, max(mae) * 1.30)
    ax2.set_ylim(0, max(mape) * 1.30)
    ax.set_title("主判据：MAE / MAPE（交付期 334 天滚动回测）")
    line1, lab1 = ax.get_legend_handles_labels()
    line2, lab2 = ax2.get_legend_handles_labels()
    ax.legend(line1 + line2, lab1 + lab2, loc="upper left", fontsize=8.4, framealpha=0.92)

    ax = axes[1]
    tail_keys = ["rmse", "p90", "p99"]
    tail_labels = ["RMSE", "P90", "P99"]
    x = np.arange(len(tail_keys))
    width = 0.20
    for index, (key, color) in enumerate(zip(order, colors)):
        values = [metrics[key][m] for m in tail_keys]
        bars = ax.bar(x + (index - 1.5) * width, values, width, color=color, alpha=0.9, label=key)
        for bar, value in zip(bars, values):
            ax.annotate(f"{value:.4f}", (bar.get_x() + bar.get_width() / 2, value), textcoords="offset points",
                        xytext=(0, 2.5), ha="center", fontsize=6.8, rotation=90)
    ax.set_xticks(x)
    ax.set_xticklabels(tail_labels)
    ax.set_ylabel("误差 (元/kWh)")
    ax.set_ylim(0, max(metrics[k]["p99"] for k in order) * 1.78)
    ax.set_title("尾部指标：RMSE / P90 / P99（优劣方向与 MAE 相反）")
    ax.legend(loc="upper left", fontsize=8.0, framealpha=0.92)
    note(
        ax,
        "E-F5：主口径 = PF-PERSIST（MAE/MAPE/P50 为主判据）；\n"
        "PF-DUAL 的 RMSE/P90/P99 更优 → 必须成对给出、禁止只报单一指标、\n"
        "禁止据单一指标宣称任一预测器更优；PF-AR 的 MAE 更低，\n"
        "但按 AS08 只作 ablation 对照、不参与主口径选择。",
        xy=(0.98, 0.88), ha="right", fontsize=7.2,
    )
    fig.suptitle("prob04 主价格预测器与强制基准的滚动回测（两链共用同一预测器）", fontsize=13)
    return emit(
        fig,
        kind="forecast_backtest",
        title="prob04 价格预测器滚动回测：MAE/MAPE 与 RMSE/P90/P99 成对报告（`E-F5`）",
        x="predictor",
        y=["mae", "mape_pct", "rmse", "p90", "p99"],
        caption=(
            "交付期 $D_{req}$（2025-02-01…12-31，334 天）的滚动回测指标。左：MAE（元/kWh，主判据）与 MAPE（%%）；"
            "右：RMSE / P90 / P99（元/kWh，尾部指标）。**两链（`4-2`/`4-3`）共用同一预测器与同一回测协议**（`AS13`）。"
            "读数：`PF-PERSIST` MAE=%.8f、MAPE=%.4f%%、P90=%.4f、P99=%.4f 为最优平均账单误差；"
            "`PF-DUAL` 的 RMSE=%.5f、P90=%.4f、P99=%.4f **更优**（尾部），`PF-HIST` 全指标最差；"
            "`PF-AR` 的 MAE=%.5f 虽更低，但按 `AS08` **只作 `ablation` 对照、不参与主口径选择**。"
            "按 `E-F5`，论文不得据单一指标宣称任一预测器「更优」，亦不得更换主预测器。"
            "数据来源：两链 run002 的 forecast_backtest.json（逐字节相同）。"
            % (
                metrics["PF-PERSIST"]["mae"], metrics["PF-PERSIST"]["mape"] * 100,
                metrics["PF-PERSIST"]["p90"], metrics["PF-PERSIST"]["p99"],
                metrics["PF-DUAL"]["rmse"], metrics["PF-DUAL"]["p90"], metrics["PF-DUAL"]["p99"],
                metrics["PF-AR"]["mae"],
            )
        ),
        source_hash=source_hash,
        source_data=source_data,
        task_id=task_id,
    )


# ---------------------------------------------------------------- 图 3：kappa_m 滚动校正（仅 4-3）
def figure_kappa_correction(source_hash: str, source_data: str, task_id: str) -> dict:
    fig, axes = plt.subplots(1, 2, figsize=(FIG_W + 3.2, FIG_H + 0.4), layout="constrained")
    colors = {6: PRIMARY, 12: SECONDARY, 18: ACCENT}
    ax = axes[0]
    for m in (6, 12, 18):
        ax.plot(np.arange(DAYS), DATA["kappa"]["series"][m], color=colors[m], lw=0.9, alpha=0.9,
                label=f"调整层 m={m}")
    ax.axhline(1.0, color="black", lw=0.9, ls="--", label="水平校正 = 1（不校正）")
    ax.axhline(KAPPA_LO, color=WARNING, lw=0.9, ls=":", label=f"防御截断界 [{KAPPA_LO}, {KAPPA_HI}]")
    ax.axhline(KAPPA_HI, color=WARNING, lw=0.9, ls=":")
    mark_months(ax)
    mark_delivery(ax)
    ax.set_ylabel("水平校正因子")
    ax.set_title("链 4-3：逐日滚动水平校正因子（365 天）")
    ax.legend(loc="upper left", fontsize=8.0, ncol=2, framealpha=0.92)
    ax.set_xlabel("日期（2025-01-01 → 2025-12-31）")

    ax = axes[1]
    bins = np.linspace(0.6, 1.65, 70)
    for m in (6, 12, 18):
        ax.hist(DATA["kappa"]["series"][m], bins=bins, histtype="stepfilled", alpha=0.42, color=colors[m],
                label=f"调整层 m={m}：均值 {DATA['kappa']['series'][m].mean():.4f}")
    ax.axvline(1.0, color="black", lw=1.0, ls="--")
    ax.set_xlabel("水平校正因子取值")
    ax.set_ylabel("天数")
    ax.set_title("水平校正因子分布：集中于 1 附近，无截断事件")
    ax.legend(loc="upper right", fontsize=8.2, framealpha=0.92)
    note(
        ax,
        f"独立重建（当日 i≤6m 实际均价 / 前一日同时段实际均价）：\n"
        f"范围 [{DATA['kappa']['min']:.8f}, {DATA['kappa']['max']:.8f}]，"
        f"最小值在 0-based day {DATA['kappa']['argmin_day']} 的 m={DATA['kappa']['argmin_m']}；\n"
        f"截断事件 {DATA['kappa']['clip_events']} 次（界 [{KAPPA_LO}, {KAPPA_HI}] 未触发）；"
        f"重建信念价与落盘序列最大差 {DATA['kappa']['err']:.1e}。\n"
        "按 sanity 的 N1 更正，上游登记的 [0.50133, 1.54939] 下界不可复现，\n"
        "论文与下游一律用本图范围。",
        xy=(0.98, 0.44), fontsize=7.4,
    )
    fig.suptitle("prob04 链 4-3 调整层的滚动价格预测：水平校正因子与防御截断", fontsize=13)
    return emit(
        fig,
        kind="kappa_rolling_correction",
        title="prob04 链 `4-3` 调整层 $\\kappa_m$ 滚动水平校正：逐日序列、分布与截断纪律",
        x="day_index / kappa_value",
        y=["kappa_6", "kappa_12", "kappa_18"],
        caption=(
            "仅链 `4-3`（`AS11`）：调整时刻 $m\\in\\{6,12,18\\}$ 的水平校正因子 $\\kappa_m = A_m/B_m$，"
            "$A_m$ = 当日 $i\\leq 6m$ 已实现实际均价、$B_m$ = 前一日同时段实际均价，防御性截断 $\\kappa_m\\in[0.5, 2.0]$。"
            "左：逐日序列（竖点线为月初），横虚线为 $\\kappa_m=1$ 与截断界；右：三条 $\\kappa_m$ 的分布。"
            "实测范围 **[%.8f, %.8f]**（最小值在 0-based day %d 的 $m=%d$），截断事件 **0 次**；"
            "独立重建的逐层信念价与落盘 `series.price_belief_yuan_per_kwh` 最大差 **%.1e**（逐位一致）。"
            "按 `sanity` **N1** 更正，上游登记的 $[0.50133, 1.54939]$ 下界不可复现，本图范围为准。"
            "该层只用**截至该时刻已实现的实际价 + 历史价**，不含未来价格（`AS07`/`AS11`）。"
            "数据来源：链 `4-3` task %s / run002。"
            % (
                DATA["kappa"]["min"], DATA["kappa"]["max"], DATA["kappa"]["argmin_day"],
                DATA["kappa"]["argmin_m"], DATA["kappa"]["err"], TASK_IDS["4-3"],
            )
        ),
        source_hash=source_hash,
        source_data=source_data,
        task_id=task_id,
    )


# ---------------------------------------------------------------- 图 4：链 4-2 日内调度
def figure_dispatch_profile_42(source_hash: str, source_data: str, task_id: str) -> dict:
    days = [SPEC_DAYS["2025-03-20"], SPEC_DAYS["2025-12-21"]]
    labels = ["2025-03-20（春分）", "2025-12-21（冬至）"]
    d = DATA["chains"]["4-2"]["d"]
    fig, axes = plt.subplots(2, 2, figsize=(FIG_W + 3.6, FIG_H + 3.0), layout="constrained", sharex="col")
    handles = None
    for column, (day, label) in enumerate(zip(days, labels)):
        sl = day_slice(day)
        price = d["price"][sl]
        ax = axes[0][column]
        ax.bar(PERIOD_CENTER_H, d["plan"][sl], width=0.13, color=PRIMARY, alpha=0.72,
               label="计划购电量（= 最终购电量）")
        ax.bar(PERIOD_CENTER_H, d["charge"][sl], width=0.13, color=SECONDARY, alpha=0.9, label="充电")
        ax.bar(PERIOD_CENTER_H, -d["discharge"][sl], width=0.13, color=ACCENT, alpha=0.9, label="放电（向下）")
        ax.axhline(0.0, color="black", lw=0.8)
        lo = float(min(-d["discharge"][sl].max(), 0.0))
        hi = float(max(d["plan"][sl].max(), d["charge"][sl].max(), 1.0))
        ax.set_ylim(lo * 1.22 - 20, hi * 1.30)
        ax.set_ylabel("电量 (kWh/10min)")
        ax.set_title(f"{label}：链 4-2 计划购电与充放电")
        ax2 = ax.twinx()
        ax2.plot(PERIOD_CENTER_H, price, color="black", lw=1.4, ls="--", label="附件 4 实际价")
        ax2.set_ylim(0, float(price.max()) * 1.28)
        ax2.set_ylabel("电价 (元/kWh)")
        ax2.grid(False)
        if handles is None:
            line1, lab1 = ax.get_legend_handles_labels()
            line2, lab2 = ax2.get_legend_handles_labels()
            handles, legend_labels = line1 + line2, lab1 + lab2
        note(
            ax,
            f"当日购电量 {d['plan'][sl].sum():,.1f} kWh；充电 {d['charge'][sl].sum():,.1f}；"
            f"放电 {d['discharge'][sl].sum():,.1f}\n"
            f"当日结算费用 {float((price * d['plan'][sl]).sum()):,.2f} 元；偏差费与紧急购电费恒为 0\n"
            f"当日紧急购电量 {d['q_em'][sl].sum():.1e} kWh（定理级恒零）",
            xy=(0.985, 0.97), fontsize=7.4,
        )

        ax = axes[1][column]
        storage = day_storage("4-2", day)
        ax.plot(PERIOD_EDGE_H, storage, color=PRIMARY, lw=2.0, label="储电量（链 4-2）")
        ax.axhline(E_MIN, color=WARNING, lw=1.0, ls="--", label=f"运行下界 {E_MIN:,.0f} kWh")
        ax.axhline(E_MAX, color=WARNING, lw=1.0, ls=":", label=f"运行上界 {E_MAX:,.0f} kWh")
        ax.scatter([0, 24], [storage[0], storage[-1]], color="black", s=22, zorder=5)
        ax.set_ylim(0, 11800)
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 4))
        ax.set_ylabel("储电量 (kWh)")
        ax.set_xlabel("计划窗时刻 (h)（AS01 左端点口径 0:10 → 24:10）")
        ax.set_title(f"{label}：链 4-2 的日内储电量轨迹")
        ax.legend(loc="upper left", fontsize=7.6, framealpha=0.92)
        note(
            ax,
            f"日初 E(d,0) = {storage[0]:,.1f} kWh（= 前一日末态）；"
            f"日末 E(d,144) = {storage[-1]:,.1f} kWh\n"
            "跨日连续，连续性残差 0.0；日内大幅充放循环",
            xy=(0.985, 0.04), va="bottom", fontsize=7.4,
        )
    fig.legend(handles, legend_labels, loc="lower center", bbox_to_anchor=(0.5, -0.05), ncol=4, frameon=False,
               fontsize=8.6)
    fig.suptitle("prob04 链 4-2（波动电价下重算问题 2）的日内调度与储电量（两个指定日期）", fontsize=13)
    return emit(
        fig,
        kind="dispatch_profile_42",
        title="prob04 链 4-2 日内调度剖面：计划购电量、充放电与储电量（指定日期）",
        x="time_of_day_h",
        y=["plan_purchase_kwh", "charge_kwh", "discharge_kwh", "storage_kwh", "price_actual_yuan_per_kwh"],
        caption=(
            "**仅链 `4-2`**（≙ 在波动电价下重算问题 2；逐日 0:00 一次计划、$q\\equiv b$、无调整层与偏差结算）。"
            "上排：2025-03-20（春分）与 2025-12-21（冬至）的计划购电量 $b$（蓝柱）、充电 $c$（绿，向上）与"
            "放电 $q_{dis}$（橙，向下），黑虚线为附件 4 实际价（右轴，结算用价）；下排：同日储电量轨迹与运行上下界。"
            "两日的指定时段数值与 `tables.json` 表 1（`final_quantity` = $b$）和表 2 六块充/放电量一致；"
            "当日费用 $C^{act}=\\Sigma p^{act}b$（元，不乘 $\\Delta t$），$C_{adj}=C_{em}\\equiv 0$、"
            "$\\Sigma q_{em}\\equiv 0$（`AS16` 定理：附件 2 实际负载/光伏在 0:00 即已知、等式平衡 + $s\\geq 0$ 自由处置 "
            "→ 结算层无缺口；价格不确定性只影响费用）。数据来源：链 `4-2` task %s / run002。" % TASK_IDS["4-2"]
        ),
        source_hash=source_hash,
        source_data=source_data,
        task_id=task_id,
    )


# ---------------------------------------------------------------- 图 5：链 4-3 计划/调整/紧急
def figure_plan_adjust_profile_43(source_hash: str, source_data: str, task_id: str) -> dict:
    days = [SPEC_DAYS["2025-03-20"], SPEC_DAYS["2025-12-21"]]
    labels = ["2025-03-20（春分）", "2025-12-21（冬至）"]
    d = DATA["chains"]["4-3"]["d"]
    fig, axes = plt.subplots(2, 2, figsize=(FIG_W + 3.6, FIG_H + 3.2), layout="constrained", sharex="col")
    handles = None
    for column, (day, label) in enumerate(zip(days, labels)):
        sl = day_slice(day)
        price = d["price"][sl]
        plan = d["plan"][sl]
        final = d["final"][sl]
        delta = final - plan
        q_em = d["q_em"][sl]
        ax = axes[0][column]
        ax.plot(PERIOD_CENTER_H, plan, color=PRIMARY, lw=1.6, label="计划购电量（0:00 计划层）")
        ax.plot(PERIOD_CENTER_H, final, color=ACCENT, lw=1.6, label="最终购电量（调整层提交）")
        ax.fill_between(PERIOD_CENTER_H, plan, final, where=final >= plan, color=ACCENT, alpha=0.28,
                        label="上调 q − b")
        ax.fill_between(PERIOD_CENTER_H, plan, final, where=final < plan, color=SECONDARY, alpha=0.34,
                        label="下调 b − q")
        ax.bar(PERIOD_CENTER_H, q_em, width=0.13, color=WARNING, alpha=0.72, label="紧急购电量（结算层）")
        upper = float(max(final.max(), plan.max(), 1.0))
        ax.set_ylim(0, upper * 1.35)
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 4))
        ax.set_ylabel("电量 (kWh/10min)")
        ax.set_title(f"{label}：链 4-3 计划、最终购电与紧急购电")
        if handles is None:
            handles, legend_labels = ax.get_legend_handles_labels()
        note(
            ax,
            f"当日调整量 {delta.sum():,.1f} kWh（上调 {int((delta > 1e-9).sum())} / "
            f"下调 {int((delta < -1e-9).sum())} 时段）\n"
            f"当日偏差结算费 {float((price * (BETA_DEF * np.maximum(-delta, 0) + BETA_OVER * np.maximum(delta, 0))).sum()):,.2f} 元；"
            f"紧急购电费 {float((ALPHA_EM * price * q_em).sum()):,.2f} 元",
            xy=(0.985, 0.97), fontsize=7.4,
        )

        ax = axes[1][column]
        colors = [ACCENT if value >= 0 else SECONDARY for value in delta]
        ax.bar(PERIOD_CENTER_H, delta, width=0.14, color=colors, alpha=0.92)
        ax.axhline(0.0, color="black", lw=0.8)
        peak = float(np.max(np.abs(delta))) if np.any(delta) else 1.0
        ax.set_ylim(-peak * 1.3, peak * 1.3)
        ax.set_xticks(range(0, 25, 4))
        ax.set_xlabel("计划窗时刻 (h)（AS01 左端点口径 0:10 → 24:10）")
        ax.set_ylabel("调整量 q − b (kWh/10min)")
        ax.set_title(f"{label}：链 4-3 逐时段调整量")
        note(
            ax,
            f"非零调整时段 {int((np.abs(delta) > 1e-9).sum())} / {SEG}；峰值 {peak:,.1f} kWh/10min\n"
            "调整层只在未锁定段决策，已提交段不回溯（AS18）",
            xy=(0.985, 0.95), fontsize=7.4,
        )
    fig.legend(handles, legend_labels, loc="lower center", bbox_to_anchor=(0.5, -0.05), ncol=5, frameon=False,
               fontsize=8.6)
    fig.suptitle("prob04 链 4-3（波动电价下重算问题 3）计划层 / 调整层 / 结算层的日内落地", fontsize=13)
    return emit(
        fig,
        kind="plan_adjust_profile_43",
        title="prob04 链 4-3 计划/调整/紧急购电日内剖面（指定日期）",
        x="time_of_day_h",
        y=["plan_purchase_kwh", "final_purchase_kwh", "adjustment_kwh", "q_em_kwh"],
        caption=(
            "**仅链 `4-3`**（0:00 计划 + 6:00/12:00/18:00 调整 + $0.5\\times$/$1.5\\times$ 双向分段结算 + 紧急购电）。"
            "上排：2025-03-20 与 2025-12-21 的日内剖面——蓝线 = 计划层购电量 $b$（0:00 用附件 3 的 0:00 预报与 `PF-PERSIST` 预测价），"
            "橙线 = 调整后的最终购电量 $q$（各时段取其支配决策时刻的预测价），橙/绿填充 = 上调 $q-b$ / 下调 $b-q$，"
            "红柱 = 结算层紧急购电量 $q_{em}$；下排：同日逐时段调整量 $(q-b)$。"
            "全期上调 %.1f kWh（%d 时段）、下调 %.1f kWh（%d 时段）、无调整 %d 时段。"
            "$q_{em}$ 只在**结算层**由「支配层光伏预报 vs 附件 2 实际」的缺口产生（`AS16`/`AS18`：实际光伏只进结算层），"
            "决策层按 $\\alpha_{em}=5>1.5$ 恒不激活。两日指定时段数值与 `tables.json` 表 1（`final_quantity` = $q$）一致。"
            "数据来源：链 `4-3` task %s / run002。"
            % (
                d["up_kwh"], d["adj_up_periods"], d["adj_down_kwh"], d["adj_down_periods"],
                d["adj_equal_periods"], TASK_IDS["4-3"],
            )
        ),
        source_hash=source_hash,
        source_data=source_data,
        task_id=task_id,
    )


# ---------------------------------------------------------------- 图 6：费用分解与跨链归因
def figure_cost_decomposition(source_hash: str, source_data: str, task_id: str) -> dict:
    full = {}
    for chain, blob in DATA["chains"].items():
        d = blob["d"]
        price, plan, final, q_em, belief = d["price"], d["plan"], d["final"], d["q_em"], d["belief"]
        dev = BETA_DEF * np.maximum(plan - final, 0) + BETA_OVER * np.maximum(final - plan, 0)
        full[chain] = {
            "plan": float(np.sum(price * plan)),
            "adj": float(np.sum(price * dev)) if chain == "4-3" else 0.0,
            "em": float(np.sum(ALPHA_EM * price * q_em)),
            "fc": float(np.sum(belief * plan)) + (float(np.sum(belief * dev)) if chain == "4-3" else 0.0)
            + float(np.sum(ALPHA_EM * belief * q_em)),
        }
        full[chain]["total"] = full[chain]["plan"] + full[chain]["adj"] + full[chain]["em"]

    fig, axes = plt.subplots(1, 2, figsize=(FIG_W + 4.0, FIG_H + 1.2), layout="constrained")
    ax = axes[0]
    bars = ["4-2\n交付期", "4-3\n交付期", "4-2\n全期", "4-3\n全期"]
    plan_v = np.asarray([DATA["chains"]["4-2"]["d"]["c_plan"], DATA["chains"]["4-3"]["d"]["c_plan"],
                         full["4-2"]["plan"], full["4-3"]["plan"]])
    adj_v = np.asarray([0.0, DATA["chains"]["4-3"]["d"]["c_adj"], 0.0, full["4-3"]["adj"]])
    em_v = np.asarray([0.0, DATA["chains"]["4-3"]["d"]["c_em"], 0.0, full["4-3"]["em"]])
    fcs = np.asarray([DATA["chains"]["4-2"]["d"]["c_fc"], DATA["chains"]["4-3"]["d"]["c_fc"],
                      full["4-2"]["fc"], full["4-3"]["fc"]])
    x = np.arange(4)
    ax.bar(x, plan_v, 0.55, color=PRIMARY, label="计划购电费（按实际价结算）")
    ax.bar(x, adj_v, 0.55, bottom=plan_v, color=SECONDARY, label="偏差结算费（仅 4-3）")
    ax.bar(x, em_v, 0.55, bottom=plan_v + adj_v, color=WARNING, label="紧急购电费")
    totals = plan_v + adj_v + em_v
    for xi, (total, fc) in enumerate(zip(totals, fcs)):
        ax.annotate(f"主值 {total / 1e6:,.4f}e6 元\n价格预报误差代价 {(total - fc) / 1e3:,.1f}e3 元",
                    (xi, total), textcoords="offset points", xytext=(0, 5), ha="center", fontsize=7.4)
    ax.set_xticks(x)
    ax.set_xticklabels(bars, fontsize=9)
    ax.set_ylabel("费用 (元)")
    ax.set_ylim(0, float(totals.max()) * 1.32)
    ax.set_title("两链费用分解（结算口径主结果，交付期与全期）")
    ax.legend(loc="upper left", fontsize=7.8, framealpha=0.92)

    ax = axes[1]
    a_total = DATA["chains"]["4-2"]["d"]["c_total"]
    steps = [
        ("链 4-2\n交付期主值", a_total, PRIMARY),
        ("计划购电费差\n价格预报误差", DATA["cross"]["delta_plan"], SECONDARY),
        ("偏差结算制度", DATA["cross"]["delta_adj"], ACCENT),
        ("紧急购电费\n光伏预报误差", DATA["cross"]["delta_em"], WARNING),
        ("链 4-3\n交付期主值", a_total + DATA["cross"]["delta_total"], NEUTRAL),
    ]
    running = 0.0
    for index, (label, value, color) in enumerate(steps):
        if index in (0, len(steps) - 1):
            ax.bar(index, value, 0.55, color=color, alpha=0.9)
            ax.annotate(f"{value / 1e6:,.4f}e6 元", (index, value), textcoords="offset points", xytext=(0, 5),
                        ha="center", fontsize=8.0)
            running = value
            continue
        ax.bar(index, value, 0.55, bottom=running, color=color, alpha=0.9)
        ax.annotate(f"+{value / 1e3:,.2f}e3 元", (index, running + value), textcoords="offset points",
                    xytext=(0, 5), ha="center", fontsize=8.0)
        running += value
    ax.plot([0.28, 0.72], [a_total, a_total], color="black", lw=0.9, ls=":")
    ax.plot([3.28, 3.72], [a_total + DATA["cross"]["delta_total"]] * 2, color="black", lw=0.9, ls=":")
    ax.set_xticks(range(len(steps)))
    ax.set_xticklabels([s[0] for s in steps], fontsize=8.2)
    ax.set_ylabel("交付期费用 (元)")
    ax.set_ylim(a_total * 0.94, (a_total + DATA["cross"]["delta_total"]) * 1.05)
    ax.set_title("两链交付期差额的三分项归因")
    note(
        ax,
        f"链 4-3 − 链 4-2 = {DATA['cross']['delta_total']:,.6f} 元\n"
        f"= 计划购电费差 {DATA['cross']['delta_plan']:,.6f}\n"
        f"+ 偏差结算费 {DATA['cross']['delta_adj']:,.6f}\n"
        f"+ 紧急购电费 {DATA['cross']['delta_em']:,.6f}\n"
        f"（残差 {DATA['cross']['residual']:.1e} 为 6 位小数舍入）\n"
        "两链交付期净负荷逐位相同 → 差额完全来自三项，\n"
        "不得只报总差（P4-D5 / D11）。\n"
        f"价格预报误差代价不是差额分项：4-2 {DATA['chains']['4-2']['d']['delta_c_price']:,.2f} 元、\n"
        f"4-3 {DATA['chains']['4-3']['d']['delta_c_price']:,.2f} 元，两链符号相同、基数不同，不可相减归因。",
        xy=(0.02, 0.99), ha="left", fontsize=6.8,
    )
    fig.suptitle("prob04 两链费用分解与跨链差额归因（结算口径为主，决策口径作对照）", fontsize=13)
    return emit(
        fig,
        kind="cost_decomposition",
        title="prob04 两链费用分解、价格预报误差代价与交付期差额三分项归因",
        x="chain_and_window",
        y=["C_plan", "C_adj", "C_em", "C_total", "delta_c_price"],
        caption=(
            "左：交付期 $D_{req}$（334 天）与全期 $D_{full}$（365 天）的两链费用堆叠——"
            "$C_{plan}^{act}=\\Sigma p^{act}b$、$C_{adj}^{act}=\\Sigma[0.5p^{act}(b-q)^+ + 1.5p^{act}(q-b)^+]$（仅 `4-3`）、"
            "$C_{em}^{act}=5\\Sigma p^{act}q_{em}$；柱顶标注主交付值 $C^{act}$ 与决策口径差额 $\\Delta C_{price}=C^{act}-C^{fc}$。"
            "交付期：`4-2` = 13,006,411.041148 元（= $C_{plan}$，$C_{adj}=C_{em}\\equiv 0$）；"
            "`4-3` = 15,289,050.714738 元 = 13,106,641.487373 + 522,512.788776 + 1,659,896.438588。"
            "右：交付期差额瀑布 $C^{act}(4-3)-C^{act}(4-2)$ = 2,282,639.673590 元 = 计划购电费差 100,230.446225 "
            "+ 偏差结算费 522,512.788776 + 紧急购电费 1,659,896.438588。"
            "$\\Delta C_{price}$ 两链分别为 520,790.839035 / 258,485.465704 元（决策—结算分离的代价，`AS09`），"
            "与差额三分项是**不同口径**、不得混用（`D7`/`D11`）。费用分解恒等式残差 0.0，全部数值与 "
            "run_manifest.delivery 逐位一致。数据来源：两链 task %s & %s / run002。"
            % (TASK_IDS["4-2"], TASK_IDS["4-3"])
        ),
        source_hash=source_hash,
        source_data=source_data,
        task_id=task_id,
    )


# ---------------------------------------------------------------- 图 7：两链储电量轨迹
def figure_soc_trajectory(source_hash: str, source_data: str, task_id: str) -> dict:
    fig, axes = plt.subplots(1, 3, figsize=(FIG_W + 7.0, FIG_H + 0.6), layout="constrained")
    days_axis = np.arange(DAYS)

    ax = axes[0]
    for chain, blob in DATA["chains"].items():
        storage = blob["d"]["storage"].reshape(DAYS, SEG)
        ax.fill_between(days_axis, storage.min(axis=1), storage.max(axis=1), color=CHAIN_COLOR[chain], alpha=0.16)
        ax.plot(days_axis, storage.mean(axis=1), color=CHAIN_COLOR[chain], lw=1.2, label=f"链 {chain} 日内均值")
    ax.axhline(E_MIN, color=WARNING, lw=1.1, ls="--", label=f"运行下界 {E_MIN:,.0f} kWh")
    ax.axhline(E_MAX, color=WARNING, lw=1.1, ls=":", label=f"运行上界 {E_MAX:,.0f} kWh")
    mark_months(ax)
    mark_delivery(ax)
    ax.set_ylabel("储电量 (kWh)")
    ax.set_ylim(900, 11400)
    ax.set_title("(a) 全年日内储电量 min–max 带与均值")
    ax.legend(loc="lower left", fontsize=7.0, ncol=2, framealpha=0.92)
    ax.set_xlabel("日期（2025-01-01 → 2025-12-31）")

    ax = axes[1]
    day_list = [DELIVERY_START, SPEC_DAYS["2025-06-21"]]
    day_labels = ["2025-02-01（交付期首日）", "2025-06-21（夏至）"]
    for day, label in zip(day_list, day_labels):
        for chain in ("4-2", "4-3"):
            storage = day_storage(chain, day)
            ax.plot(PERIOD_EDGE_H, storage, color=CHAIN_COLOR[chain], lw=1.6,
                    ls="-" if day == day_list[0] else "--",
                    label=f"{label} · 链 {chain}（日初 {storage[0]:,.1f} kWh）")
    ax.axhline(E_MIN, color=WARNING, lw=1.1, ls="--", label=f"运行下界 {E_MIN:,.0f} kWh")
    ax.axhline(E_MAX, color=WARNING, lw=1.1, ls=":", label=f"运行上界 {E_MAX:,.0f} kWh")
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 4))
    ax.set_ylim(900, 11400)
    ax.set_xlabel("计划窗时刻 (h)（AS01 左端点口径 0:10 → 24:10）")
    ax.set_ylabel("储电量 (kWh)")
    ax.set_title("(b) 交付期首日与夏至日的日内轨迹")
    ax.legend(loc="lower right", fontsize=6.8, framealpha=0.92)

    ax = axes[2]
    labels7 = ["4-2\n日初 E(d,0)", "4-2\n日末 E(d,144)", "4-3\n日初 E(d,0)", "4-3\n日末 E(d,144)"]
    values, lows, highs, carries = [], [], [], []
    for chain in ("4-2", "4-3"):
        daily = DATA["chains"][chain]["d"]["daily"]
        starts = np.asarray(daily["state_start_kwh"], dtype=float)[DELIVERY_START:]
        ends = np.asarray(daily["state_end_kwh"], dtype=float)[DELIVERY_START:]
        for series in (starts, ends):
            values.append(float(series.mean()))
            lows.append(float(series.min()))
            highs.append(float(series.max()))
            carries.append(float(np.sum(np.abs(series - E_MIN))))
    positions = np.arange(4)
    ax.bar(positions, values, 0.55, color=[PRIMARY, PRIMARY, ACCENT, ACCENT], alpha=0.92)
    ax.errorbar(positions, values, yerr=[np.asarray(values) - np.asarray(lows),
                                         np.asarray(highs) - np.asarray(values)],
                fmt="none", ecolor="black", elinewidth=1.1, capsize=5)
    for position, value, high in zip(positions, values, highs):
        ax.annotate(f"{value:,.6f}\n(max {high:.6f})", (position, high), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=7.0)
    ax.axhline(E_MIN, color=WARNING, lw=1.2, ls="--", label=f"运行下界 {E_MIN:,.0f} kWh")
    ax.axhline(E_MAX, color=WARNING, lw=1.1, ls=":", label=f"运行上界 {E_MAX:,.0f} kWh")
    ax.set_xticks(positions)
    ax.set_xticklabels(labels7, fontsize=8.0)
    ax.set_ylim(0, 11600)
    ax.set_ylabel("储电量 (kWh)")
    ax.set_title("(c) 交付期 334 天的日初/日末储电量（min–max 误差棒）")
    ax.legend(loc="upper right", fontsize=7.0, framealpha=0.92)
    note(
        ax,
        "日边界行为（直面 prob03 E8/R18）：\n"
        "交付期 334 天的日初与日末储电量**全部** = 1200 kWh\n"
        f"（4-2 逐位 1200.000000；4-3 最大偏差 "
        f"{max(abs(np.asarray(DATA['chains']['4-3']['d']['daily']['state_end_kwh'])[DELIVERY_START:] - E_MIN)):.2e} kWh）；\n"
        f"跨日携带量 Σ|E(d,144) − 1200| = {carries[1]:.2e}（4-2）/ {carries[3]:.2e}（4-3）kWh。\n"
        "→ 日边界不携带电量、跨日无对冲（唯一例外是预热期\n"
        "首日 E(1/1,0) = 6000 kWh，不计入交付期）。\n"
        "前瞻深度对照（S-RH）正是为检验该结构，仅进 ablation。",
        xy=(0.02, 0.72), ha="left", fontsize=6.8,
    )
    fig.suptitle("prob04 两链储电量轨迹与日边界行为（滚动递推 + 终端自由）", fontsize=13)
    return emit(
        fig,
        kind="soc_trajectory",
        title="prob04 两链储电量轨迹：全年区间、日内轨迹与日边界储电量（含日边界不携带电量）",
        x="day_index / time_of_day_h / day_boundary_state_kwh",
        y=["storage_kwh", "state_start_kwh", "state_end_kwh"],
        caption=(
            "(a) 两链全年 52,560 时段储电量的逐日 min–max 带与日内均值，叠加运行上下界 $E_{min}=1200$ / $E_{max}=10800$ kWh 与"
            "2025-02-01 交付期起点；(b) 交付期首日 2025-02-01 与夏至 2025-06-21 的日内完整轨迹 "
            "$E_{d,0},\\ldots,E_{d,144}$（两链分色，实线 = 首日、虚线 = 夏至；落盘 `series.storage_kwh` 的日切片为 "
            "$E_{d,1}\\ldots E_{d,144}$，绘图时已把 `daily.state_start_kwh` 的 $E_{d,0}$ 前置对齐到时段端点）；"
            "(c) 交付期 334 天日初/日末储电量的均值与 min–max 误差棒（两链各两项）。跨日状态连续 "
            "$E_{d,0}=E_{d-1,144}$（连续性残差 0.0，`AS03` 滚动递推、终端自由）。**日边界行为**：交付期全部 334 天两链的"
            "$E_{d,0}$ 与 $E_{d,144}$ **全部** = 1200 kWh（`4-2` 逐位 1200.000000、`4-3` 最大偏差 3.07e-7），"
            "跨日携带量 $\\Sigma_d|E_{d,144}-1200|$ 为 0.0（`4-2`）/ 1.60e-5（`4-3`）kWh → 日边界不携带电量、跨日无对冲，"
            "直接回应 prob03 `E8`/`R18`（唯一例外是 1 月预热期首日 $E_{1/1,0}=6000$ kWh，不计入交付期）。"
            "注：`prob01` 单日周期口径的 $E_0=E_{144}=6000$ kWh 与本问多日滚动逐日切片口径必须显式区分"
            "（承 prob02 勘误 `R1`）。数据来源：两链 task %s & %s / run002。"
            % (TASK_IDS["4-2"], TASK_IDS["4-3"])
        ),
        source_hash=source_hash,
        source_data=source_data,
        task_id=task_id,
    )


# ---------------------------------------------------------------- 图 8：链 4-3 紧急购电
def figure_emergency_profile_43(source_hash: str, source_data: str, task_id: str) -> dict:
    d43 = DATA["chains"]["4-3"]["d"]
    d42 = DATA["chains"]["4-2"]["d"]
    daily43 = np.asarray(d43["daily"]["q_em_kwh"], dtype=float)
    q_em = d43["q_em"]
    price = d43["price"]
    fig, axes = plt.subplots(2, 2, figsize=(FIG_W + 3.6, FIG_H + 2.8), layout="constrained")

    ax = axes[0][0]
    ax.fill_between(np.arange(DAYS), daily43, color=WARNING, alpha=0.35)
    ax.plot(np.arange(DAYS), daily43, color=WARNING, lw=1.0, label="链 4-3 逐日紧急购电量")
    ax.plot(np.arange(DAYS), np.asarray(d42["daily"]["q_em_kwh"], dtype=float), color=PRIMARY, lw=1.2,
            label="链 4-2 逐日紧急购电量（恒 0 对照）")
    mean_delivery = daily43[DELIVERY_START:].mean()
    ax.axhline(mean_delivery, color="black", lw=1.0, ls="--", label=f"交付期日均 {mean_delivery:,.1f} kWh/日")
    mark_months(ax)
    mark_delivery(ax)
    ax.set_ylabel("紧急购电量 (kWh/日)")
    ax.set_ylim(0, float(daily43.max()) * 1.42)
    ax.set_title("两链逐日紧急购电量：4-3 非零、4-2 恒零")
    ax.legend(loc="upper left", fontsize=7.2, framealpha=0.92)
    xlabel_days(ax)

    ax = axes[0][1]
    hourly = q_em.reshape(DAYS, SEG).sum(axis=0).reshape(24, 6).sum(axis=1)
    counts = (q_em.reshape(DAYS, SEG) > 1e-9).sum(axis=0).reshape(24, 6).sum(axis=1)
    ax.bar(np.arange(24), hourly / 1e3, 0.72, color=WARNING, alpha=0.85)
    for hour in range(24):
        if counts[hour]:
            ax.annotate(f"{counts[hour]:,}", (hour, hourly[hour] / 1e3), textcoords="offset points",
                        xytext=(0, 2.5), ha="center", fontsize=6.4)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlabel("小时块（AS01 位置口径：第 h 小时 = [h:00, h+1:00)，含 6 个时段）")
    ax.set_ylabel("紧急购电量 (MWh)")
    ax.set_ylim(0, float(hourly.max()) / 1e3 * 1.16)
    ax.set_title("链 4-3 紧急购电的日内小时分布（柱顶为触发时段数）")
    note(
        ax,
        f"全期 {q_em.sum():,.3f} kWh，{int((q_em > 1e-9).sum()):,} 个时段 / "
        f"{int((daily43 > 1e-9).sum())} 天出现\n"
        f"交付期 {d43['q_em_delivery_kwh']:,.3f} kWh（{d43['q_em_delivery_periods']:,} 时段 / "
        f"{d43['q_em_delivery_days']} 天）\n"
        "紧急购电与充电同时成立的时段 6,003，二者分属两层，\n不违反「紧急购电不用于储能充电」的口径",
        xy=(0.98, 0.62), fontsize=7.2,
    )

    ax = axes[1][0]
    sl = day_slice(DELIVERY_START)
    ax.bar(PERIOD_CENTER_H, d43["residual_negative"][sl] / 1e3, width=0.13, color=NEUTRAL, alpha=0.55,
           label="结算层缺口 max(0, −r)")
    ax.bar(PERIOD_CENTER_H, q_em[sl] / 1e3, width=0.13, color=WARNING, alpha=0.9, label="落盘紧急购电量")
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 4))
    ax.set_xlabel("计划窗时刻 (h)")
    ax.set_ylabel("电量 (MWh/10min)")
    ax.set_title("2025-02-01：结算层缺口与紧急购电逐时段重合")
    ax.legend(loc="upper right", fontsize=7.6, framealpha=0.92)
    note(
        ax,
        "缺口 r = 最终购电量 + 放电 + 实际光伏 − 负载 − 充电，紧急购电 = max(0, −r)：\n"
        "全期 52,560 时段最大偏差 < 1e-6 kWh → 恒等式成立。\n"
        "缺口来源 = 光伏预报误差（决策层用附件 3 预报、结算层用附件 2 实际），\n"
        "不是价格误差（价格只改变费用，不改变能量平衡）。",
        xy=(0.02, 0.97), ha="left", fontsize=7.0,
    )

    ax = axes[1][1]
    bins = np.linspace(0.0, 1.8, 60)
    triggered = price[q_em > 1e-9]
    ax.hist(price, bins=bins, density=True, histtype="step", color=NEUTRAL, lw=1.4,
            label="全期全部时段的实际价（密度）")
    ax.hist(triggered, bins=bins, density=True, histtype="stepfilled", color=WARNING, alpha=0.42,
            label=f"紧急购电时段的实际价（{triggered.size:,} 个时段）")
    ax.axvline(0.0076, color=WARNING, lw=1.2, ls=":")
    ax.set_xlabel("附件 4 实际价 (元/kWh)")
    ax.set_ylabel("概率密度")
    ax.set_title("链 4-3：紧急购电时段的价格分布（E-F2 披露）")
    ax.legend(loc="upper right", fontsize=7.4, framealpha=0.92)
    note(
        ax,
        f"附件 4 含极端低价：最小值 0.0076 元/kWh，小于 0.10 的仅 28 格；\n"
        f"深谷时段 5 倍紧急电价仅 0.038 元/kWh → 缺电惩罚在该时段几乎消失，\n"
        f"讨论惩罚机制时不得用全期均价 {price.mean():.4f} 元/kWh 外推（E-F2 后果 2）。\n"
        "以最小价构造的解析下界 155,129.41 元不足实际费用 1.1%，量级自检极松。",
        xy=(0.98, 0.60), fontsize=7.0,
    )
    fig.suptitle("prob04 链 4-3 紧急购电：逐日/日内分布、结算层机制与 E-F2 价格事实", fontsize=13)
    return emit(
        fig,
        kind="emergency_profile_43",
        title="prob04 链 4-3 紧急购电分布、结算层缺口机制与 E-F2 披露（4-2 全零对照）",
        x="day_index / hour_block / time_of_day_h / price_actual",
        y=["q_em_kwh", "settlement_gap_kwh"],
        caption=(
            "仅链 `4-3` 有非零紧急购电，链 `4-2` 恒零为对照。左上：两链逐日 $\\Sigma q_{em}$"
            "（`4-3` 填充、`4-2` 恒零线）与交付期日均线；右上：`4-3` 紧急购电的日内小时块分布"
            "（柱顶数字为该小时触发 $q_{em}>0$ 的时段数）；左下：2025-02-01 的结算层缺口 $\\max(0,-r)$ 与落盘 $q_{em}$ "
            "逐时段重合（恒等式最大偏差 < 1e-6 kWh）；右下：触发时段的价格分布 vs 全期价格分布，"
            "配合 `E-F2` 的深谷披露（$5\\times$ 紧急价最低仅 0.038 元/kWh）。"
            "机制：$q_{em}$ 由**支配层光伏预报 vs 附件 2 实际**的缺口在结算层产生（`AS16`/`AS18`），"
            "决策层按 $\\alpha_{em}=5>1.5$ 恒不激活；$q_{em}>0$ 且 $c>0$ 的时段数 6003 与同充放 1456 "
            "属**统计与机制归因**（承 prob03 `C7`/`C8`），**不得**判为模型失败。`4-2` 的 $\\Sigma q_{em}\\equiv 0$ "
            "是定理级结论，论文**必须给机制说明**而非只报空表。数据来源：两链 task %s & %s / run002。"
            % (TASK_IDS["4-2"], TASK_IDS["4-3"])
        ),
        source_hash=source_hash,
        source_data=source_data,
        task_id=task_id,
    )


# ---------------------------------------------------------------- 图 9/10：链 4-3 调整量 3D + 2D
def adjustment_grid() -> np.ndarray:
    delta = DATA["chains"]["4-3"]["d"]["final"] - DATA["chains"]["4-3"]["d"]["plan"]
    return delta.reshape(DAYS, SEG).reshape(DAYS, 24, 6).sum(axis=2)


def figure_adjust_surface_3d(source_hash: str, source_data: str, task_id: str) -> dict:
    grid = adjustment_grid()
    day_axis, hour_axis = np.arange(DAYS), np.arange(24)
    day_grid, hour_grid = np.meshgrid(day_axis, hour_axis, indexing="ij")
    fig = plt.figure(figsize=(FIG_W + 2.0, FIG_H + 2.4))
    ax = fig.add_subplot(111, projection="3d")
    cap = float(np.percentile(grid, 99.5))
    floor = float(np.percentile(grid, 0.5))
    norm = TwoSlopeNorm(vmin=min(floor, -1e-6), vcenter=0.0, vmax=max(cap, 1e-6))
    surface = ax.plot_surface(day_grid, hour_grid, grid, cmap="coolwarm", norm=norm, rstride=5, cstride=1,
                              linewidth=0.0, antialiased=True, alpha=0.96)
    ax.set_xlabel("日期（日索引，0 = 2025-01-01）", labelpad=9)
    ax.set_ylabel("时刻 (h)", labelpad=9)
    ax.set_zlabel("调整量 (kWh/h)", labelpad=6)
    ax.set_yticks([0, 6, 12, 18, 23])
    ax.set_zlim(float(grid.min()), float(grid.max()))
    ax.set_box_aspect(None, zoom=0.86)
    ax.view_init(elev=26, azim=-58)
    ax.contour(day_grid, hour_grid, grid, levels=12, zdir="z", offset=float(grid.min()), cmap="coolwarm",
               linewidths=0.7, alpha=0.85)
    ax.set_title("链 4-3 全年调整量三维曲面：日期 × 时刻 × 调整量\n"
                 f"（365 × 24 = {grid.size:,} 个「日 × 小时」格；Z>0 上调（暖色）、Z<0 下调（冷色）；"
                 "底面为同数据的等高线投影）")
    bar = fig.colorbar(surface, ax=ax, shrink=0.55, pad=0.035, aspect=18)
    bar.set_label("调整量 (kWh/h)")
    d43 = DATA["chains"]["4-3"]["d"]
    ax.annotate(
        f"上调 {d43['adj_up_periods']:,} 时段 / 下调 {d43['adj_down_periods']:,} 时段；"
        f"全期调整量合计 {d43['up_kwh'] - d43['adj_down_kwh']:,.1f} kWh\n"
        f"Z 轴为完整值域 [{grid.min():,.0f}, {grid.max():,.0f}] kWh/h（不截断，故峰值柱完整）；"
        f"色标按 99.5 分位 {cap:,.0f} 截断以防压色；\n"
        "底面等高线为同数据投影，用于读出低幅结构；定量判读以二维配套图为准",
        xy=(0.02, 0.94), xycoords="axes fraction", va="top", fontsize=9.0, color=NEUTRAL,
    )
    fig.tight_layout()
    return emit(
        fig,
        kind="adjust_surface_3d",
        title="prob04 链 4-3 全年调整量三维曲面：日期 × 时刻 ×（最终−计划）购电量",
        x="day_index",
        y=["time_of_day_hour", "adjustment_kwh_per_hour"],
        caption=(
            "**仅链 `4-3`**。三维曲面：X = 日期（2025 全年 365 天），Y = 时刻（0→23 h），"
            "Z = 该「日 × 小时」内 6 个时段的调整量之和 $(q-b)$（kWh/h），颜色以 0 为中心的双向色标"
            "（暖色 = 上调、冷色 = 下调）。视角 elev=26°、azim=−58°；为保持静态 PNG 可读性沿日期轴每 3 天抽 1 条网格线；"
            "色标按 99.5 分位截断以防个别尖峰压色（Z 轴为完整值域、不截断，故峰值柱完整可见；"
            "底面另绘同数据的等高线投影以读出低幅结构）；"
            "曲面几乎全部位于 Z≥0 半空间（上调 %d 时段、下调 %d 时段），无自遮挡；"
            "投影歧义由二维配套图 `adjust_heatmap_2d` 消除，定量判读以二维图为准。"
            "数据来源：链 `4-3` task %s / run002。"
            % (DATA["chains"]["4-3"]["d"]["adj_up_periods"], DATA["chains"]["4-3"]["d"]["adj_down_periods"],
               TASK_IDS["4-3"])
        ),
        source_hash=source_hash,
        source_data=source_data,
        task_id=task_id,
        include_in_paper=False,
    )


def figure_adjust_heatmap_2d(source_hash: str, source_data: str, task_id: str) -> dict:
    grid = adjustment_grid()
    daily_delta = grid.sum(axis=1)
    fig, axes = plt.subplots(2, 1, figsize=(FIG_W + 1.2, FIG_H + 2.6), layout="constrained",
                             gridspec_kw={"height_ratios": [2.1, 1.0]})
    ax = axes[0]
    cap = float(np.percentile(np.abs(grid), 99.0))
    image = ax.imshow(grid.T, aspect="auto", origin="lower", cmap="coolwarm",
                      norm=TwoSlopeNorm(vmin=-cap, vcenter=0.0, vmax=cap),
                      extent=[-0.5, DAYS - 0.5, -0.5, 23.5])
    ax.axvline(DELIVERY_START, color="black", lw=1.2, ls="--")
    ax.set_xticks(MONTH_TICKS)
    ax.set_xticklabels(MONTH_LABELS)
    ax.set_yticks([0, 6, 12, 18, 23])
    ax.set_ylabel("时刻 (h)")
    ax.set_title(f"链 4-3 全年「日期 × 时刻」调整量热力图（色标按绝对值 99 分位 {cap:,.0f} kWh/h 截断）")
    bar = fig.colorbar(image, ax=ax, pad=0.015)
    bar.set_label("调整量 (kWh/h)")
    ax.grid(False)
    ax.annotate(
        f"全期调整量合计 {daily_delta.sum():,.1f} kWh；上调 {DATA['chains']['4-3']['d']['adj_up_periods']:,} 时段 / "
        f"下调 {DATA['chains']['4-3']['d']['adj_down_periods']:,} 时段\n黑虚线 = 2025-02-01 交付期起点",
        xy=(0.01, 0.96), xycoords="axes fraction", ha="left", va="top", fontsize=8.0, color="black",
        bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": NEUTRAL, "alpha": 0.92},
    )

    ax = axes[1]
    ax.bar(np.arange(DAYS), daily_delta / 1e3, 0.9, color=ACCENT, alpha=0.9, label="逐日调整量合计")
    mean_delivery = daily_delta[DELIVERY_START:].mean()
    ax.axhline(mean_delivery / 1e3, color="black", lw=1.1, ls="--",
               label=f"交付期日均 {mean_delivery / 1e3:,.3f} MWh/日")
    mark_months(ax)
    mark_delivery(ax)
    ax.set_ylabel("调整量 (MWh/日)")
    ax.set_ylim(min(0.0, float(daily_delta.min()) / 1e3 * 1.15), float(daily_delta.max()) / 1e3 * 1.25)
    ax.legend(loc="upper left", fontsize=8.0, framealpha=0.92)
    ax.set_title("链 4-3 逐日调整量总量")
    xlabel_days(ax)
    fig.suptitle("prob04 链 4-3 调整量二维投影：热力图与逐日总量（三维曲面的定量配套）", fontsize=13)
    return emit(
        fig,
        kind="adjust_heatmap_2d",
        title="prob04 链 4-3 调整量二维投影：日期×时刻热力图与逐日总量",
        x="day_index",
        y=["time_of_day_hour", "adjustment_kwh_per_hour", "daily_adjustment_kwh"],
        caption=(
            "**仅链 `4-3`**，作为 `adjust_surface_3d` 的二维定量配套（消除三维视角的遮挡与深度歧义）。"
            "上：全年「日期 × 时刻」调整量 $(q-b)$ 热力图（色标以 0 为中心、按绝对值 99 分位截断以防压色；"
            "黑虚线 = 2025-02-01 交付期起点）；下：逐日调整量 $\\Sigma_t(q-b)$ 柱与交付期日均线。"
            "调整集中在日间光伏时段与傍晚：全期上调 %.1f kWh（%d 时段）、下调 %.1f kWh（%d 时段）、无调整 %d 时段。"
            "X 轴为自然日索引（0 = 2025-01-01），与三维图同源。数据来源：链 `4-3` task %s / run002。"
            % (
                DATA["chains"]["4-3"]["d"]["up_kwh"], DATA["chains"]["4-3"]["d"]["adj_up_periods"],
                DATA["chains"]["4-3"]["d"]["adj_down_kwh"], DATA["chains"]["4-3"]["d"]["adj_down_periods"],
                DATA["chains"]["4-3"]["d"]["adj_equal_periods"], TASK_IDS["4-3"],
            )
        ),
        source_hash=source_hash,
        source_data=source_data,
        task_id=task_id,
    )


# ---------------------------------------------------------------- 图 11：AS21 tie-break 与 LP 退化
def figure_tiebreak_degeneracy(source_hash: str, source_data: str, task_id: str) -> dict:
    fig, axes = plt.subplots(1, 2, figsize=(FIG_W + 3.6, FIG_H + 0.6), layout="constrained")
    ax = axes[0]
    for chain, blob in DATA["chains"].items():
        per_layer = blob["tiebreak"]["per_layer"]
        rel = np.asarray([abs(item["primary_relative_change"]) for item in per_layer])
        ax.scatter(np.arange(rel.size), np.maximum(rel, 1e-18), s=3.0, alpha=0.55, color=CHAIN_COLOR[chain],
                   label=f"链 {chain}：{rel.size:,} 层，最大 {rel.max():.3e}")
    ax.axhline(1e-9, color=WARNING, lw=1.2, ls="--", label="AS21 容差 1e-9")
    ax.set_yscale("log")
    ax.set_ylim(1e-10, 1e-8)
    ax.set_xlabel("层序号（4-2 为 365 层 / 4-3 为 1460 层，各自独立编号）")
    ax.set_ylabel("主目标相对变化")
    ax.set_title("AS21 次目标加入前后主目标不变性（逐层）")
    ax.legend(loc="upper right", fontsize=7.6, framealpha=0.92)
    note(
        ax,
        "全部层落在 [5.0000e-10, 5.0001e-10] 的极窄带内（带宽约 1e-14），\n"
        "距容差 1e-9 有约 1 个数量级余量。\n"
        "两链 all_layers_invariance_passed = True、total_shrinks = 0、\n"
        "字典序提交层数 = 365 / 1460、fallback 层数 = 0。\n"
        "T7-6：全部模型与全部 run 必须使用同一 tie-break 规则，\n"
        "不得用不同 tie-break 或求解器设置的结果互相比对。",
        xy=(0.02, 0.28), ha="left", va="bottom", fontsize=7.0,
    )

    ax = axes[1]
    for chain, blob in DATA["chains"].items():
        per_layer = blob["tiebreak"]["per_layer"]
        degrees = np.asarray([item["degeneracy_degree"] for item in per_layer], dtype=float)
        degrees = degrees[np.isfinite(degrees)]
        summary = blob["tiebreak"]["summary"]
        ax.hist(degrees, bins=40, histtype="step", lw=1.6, density=True, color=CHAIN_COLOR[chain],
                label=f"链 {chain}：退化 {summary['degenerate_layers']:,} / {summary['layers']:,} 层，"
                      f"最大退化度 {summary['max_degeneracy_degree']}")
    ax.axvline(0.0, color="black", lw=0.9, ls="--")
    ax.set_xlabel("逐层退化度 = 活跃约束数 − 变量数")
    ax.set_ylabel("密度")
    ax.set_title("LP 退化度分布：两链逐层披露")
    ax.set_ylim(0, ax.get_ylim()[1] * 1.32)
    ax.legend(loc="upper left", fontsize=7.4, framealpha=0.92)
    note(
        ax,
        "4-2 剩余多重最优层数 365；4-3 为 984；\n"
        "4-3 未知重数层数 0。\n"
        "D11 纪律：验收以约束残差 + (I1)/(I2) 恒等式 + 目标值\n"
        "+ 交付表为准，不比对逐点解唯一性；退化不是失败。\n"
        "口径：eps_relative = 1e-6、invariance_tol = 1e-9、max_shrinks = 8。",
        xy=(0.98, 0.72), fontsize=7.0,
    )
    fig.suptitle("prob04 两链 AS21 tie-break 不变性、LP 退化与多重最优的逐层披露", fontsize=13)
    return emit(
        fig,
        kind="tiebreak_degeneracy",
        title="prob04 两链 AS21 tie-break 不变性与 LP 退化度逐层披露（D11/T7-6）",
        x="layer_index / degeneracy_degree",
        y=["primary_relative_change", "degeneracy_degree"],
        caption=(
            "左：加入 `AS21` 次目标（$\\varepsilon\\cdot\\Sigma(c+q_{dis})$）前后**主目标**的逐层相对变化，"
            "红线为容差 $1\\times10^{-9}$；两链 `max_primary_relative_change` = 5.0000091e-10（`4-2`）/ "
            "5.0001249e-10（`4-3`）；`all_layers_invariance_passed` = True、`total_shrinks` = 0。"
            "右：两链逐层 LP 退化度（活跃约束数 − 变量数）分布——`4-2` 退化 364/365 层、"
            "`4-3` 退化 1459/1460 层、最大退化度 263。按 `D11`，验收以约束残差 + (I1)/(I2) 恒等式 + 目标值 + 交付表为准，"
            "**不以逐点解唯一性作判据**，退化与多重最优不构成失败。`T7-6`：所有模型与所有 run 一律使用同一 tie-break 规则，"
            "不得用不同 tie-break / 求解器设置的结果互相比对。数据来源：两链 task %s & %s / run002 的 tiebreak_audit.json。"
            % (TASK_IDS["4-2"], TASK_IDS["4-3"])
        ),
        source_hash=source_hash,
        source_data=source_data,
        task_id=task_id,
        include_in_paper=False,
    )


# ---------------------------------------------------------------- main
def main() -> int:
    DATA["chains"] = {chain: load_chain(chain) for chain in ("4-2", "4-3")}
    derive()

    source_hash = combined_hash(*[blob["dir"] / "solution.json" for blob in DATA["chains"].values()])
    source_data = " + ".join(
        relative(blob["dir"] / name)
        for blob in DATA["chains"].values()
        for name in ("solution.json", "tables.json", "run_manifest.json", "forecast_backtest.json",
                     "tiebreak_audit.json")
    )

    builders = [
        (figure_price_belief_chain, TASK_BOTH),
        (figure_forecast_backtest, TASK_BOTH),
        (figure_kappa_correction, TASK_IDS["4-3"]),
        (figure_dispatch_profile_42, TASK_IDS["4-2"]),
        (figure_plan_adjust_profile_43, TASK_IDS["4-3"]),
        (figure_cost_decomposition, TASK_BOTH),
        (figure_soc_trajectory, TASK_BOTH),
        (figure_emergency_profile_43, TASK_BOTH),
        (figure_adjust_surface_3d, TASK_IDS["4-3"]),
        (figure_adjust_heatmap_2d, TASK_IDS["4-3"]),
        (figure_tiebreak_degeneracy, TASK_BOTH),
    ]
    items = []
    for builder, task_id in builders:
        item = builder(source_hash, source_data, task_id)
        items.append(item)
        print(f"[ok] {item['stable_id']}  quality={item['quality_status']}")

    removed = prune_stale_figures({item["stable_id"] for item in items})
    summary = {
        "action_id": ACTION_ID,
        "question_id": QUESTION_ID,
        "assumption_version": ASSUMPTION_VERSION,
        "formulation_version": FORMULATION_VERSION,
        "source_hash": source_hash,
        "figure_count": len(items),
        "figures": [
            {
                "stable_id": item["stable_id"],
                "kind": item["kind"],
                "title": item["title"],
                "path": item["path"],
                "quality_status": item["quality_status"],
                "included_in_paper": item["included_in_paper"],
                "task_id": item["task_id"],
            }
            for item in items
        ],
        "pruned_stale_figures": removed,
        "key_values": {
            "4-2": {
                "C_total_act_delivery": DATA["chains"]["4-2"]["d"]["c_total"],
                "C_plan": DATA["chains"]["4-2"]["d"]["c_plan"],
                "C_adj": DATA["chains"]["4-2"]["d"]["c_adj"],
                "C_em": DATA["chains"]["4-2"]["d"]["c_em"],
                "C_total_fc": DATA["chains"]["4-2"]["d"]["c_fc"],
                "delta_c_price": DATA["chains"]["4-2"]["d"]["delta_c_price"],
                "price_mae_delivery": DATA["chains"]["4-2"]["d"]["price_mae_delivery"],
                "gap_identity_max_abs": DATA["chains"]["4-2"]["d"]["gap_check"],
            },
            "4-3": {
                "C_total_act_delivery": DATA["chains"]["4-3"]["d"]["c_total"],
                "C_plan": DATA["chains"]["4-3"]["d"]["c_plan"],
                "C_adj": DATA["chains"]["4-3"]["d"]["c_adj"],
                "C_em": DATA["chains"]["4-3"]["d"]["c_em"],
                "C_total_fc": DATA["chains"]["4-3"]["d"]["c_fc"],
                "delta_c_price": DATA["chains"]["4-3"]["d"]["delta_c_price"],
                "price_mae_delivery": DATA["chains"]["4-3"]["d"]["price_mae_delivery"],
                "q_em_delivery_kwh": DATA["chains"]["4-3"]["d"]["q_em_delivery_kwh"],
                "kappa_min": DATA["kappa"]["min"],
                "kappa_max": DATA["kappa"]["max"],
                "kappa_argmin_day": DATA["kappa"]["argmin_day"],
                "kappa_argmin_m": DATA["kappa"]["argmin_m"],
                "kappa_clip_events": DATA["kappa"]["clip_events"],
                "kappa_rebuild_max_abs_err": DATA["kappa"]["err"],
                "gap_identity_max_abs": DATA["chains"]["4-3"]["d"]["gap_check"],
            },
            "cross_chain": DATA["cross"],
        },
    }
    write_json(FIG_DIR / "generation_summary.json", summary)
    print(json.dumps(summary["key_values"], ensure_ascii=False, indent=2))
    print("figures:", len(items), "pruned:", removed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
