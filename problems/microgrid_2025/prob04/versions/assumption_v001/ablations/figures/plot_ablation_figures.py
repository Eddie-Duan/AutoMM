# ruff: noqa: E501 —— 中文图注/说明长字符串，折行会损害图内文字与可读性，故按文件豁免行长规则。
"""prob04 ablation 阶段图件生成脚本（assumption_v001 / formulation_v001 / 两链 run003）。

- 只读消费 ablation run003 的落盘产物：
  `comparison.json` / `criteria.json` / `results.json` / `baseline_check.json` / `run_manifest.json`；
- 不求解任何 LP、不新建 task、不写 `data/`、不写 accepted `code/`、不写 `results/prob04_v001_f001_*`；
- 图件为**实验产物**；按 plan_v001 §4，是否登记为交付图表（figures.yaml + record_figure_review）
  留待结果就绪后的动作按 A4.2 决定，本脚本**不登记**、不写 figures.yaml。

纪律（prob04 阶段级强制要求）：
  1. 两链（4-2 / 4-3）结论**分别**指明，不混为一条；
  2. A8-(b)：图内文字不得出现「0:00 即已知当天全时段实时电价」这类表述；决策层用预测价、结算层一律用附件 4 实际价；
  3. E-F5：凡引用预报误差处同时给出 MAE / MAPE / P90（或 P99）；
  4. 判据/阈值不做任何放宽，图只呈现落盘数值。

运行（项目根目录）：
    .venv\\Scripts\\python.exe problems/microgrid_2025/prob04/versions/assumption_v001/ablations/figures/plot_ablation_figures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager

FIG_DIR = Path(__file__).resolve().parent
ABL_DIR = FIG_DIR.parent
ROOT = FIG_DIR.parents[6]
sys.path.insert(0, str(ROOT / "scripts"))

from automm.common import config_section  # noqa: E402

PROBLEM_ID = "microgrid_2025"
QUESTION_ID = "prob04"
ACTION_ID = "act-d9d013c46e6647f5"

RUN_DIRS = {
    "4-2": ABL_DIR / "results" / "prob04_v001_ablation_4-2_run003",
    "4-3": ABL_DIR / "results" / "prob04_v001_ablation_4-3_run003",
}
TASK_IDS = {"4-2": "e54f83cea3e31a1c0879", "4-3": "20906d684ca14f498047"}
HORIZONS = [1, 3, 7, 14]
SEG = 144
DT_H = 1.0 / 6.0
E_MIN = 1200.0

STYLE = config_section("visualization", PROBLEM_ID, QUESTION_ID)
PALETTE = STYLE.get("palette", {})
PRIMARY = PALETTE.get("primary", "#1F4E79")
SECONDARY = PALETTE.get("secondary", "#70AD47")
ACCENT = PALETTE.get("accent", "#ED7D31")
NEUTRAL = PALETTE.get("neutral", "#7F8C8D")
WARNING = PALETTE.get("warning", "#C00000")
DPI = int(STYLE.get("dpi", 180))
FIG_W = float(STYLE.get("figure_width", 10))
FIG_H = float(STYLE.get("figure_height", 6))
CHAIN_COLOR = {"4-2": PRIMARY, "4-3": ACCENT}


def select_font() -> str:
    available = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in [STYLE.get("preferred_font"), *STYLE.get("fallback_fonts", [])]:
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
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
    }
)

DATA: dict[str, dict] = {}


def load() -> None:
    for chain, directory in RUN_DIRS.items():
        DATA[chain] = {
            "dir": directory,
            "comparison": json.loads((directory / "comparison.json").read_text(encoding="utf-8")),
            "criteria": json.loads((directory / "criteria.json").read_text(encoding="utf-8")),
            "results": json.loads((directory / "results.json").read_text(encoding="utf-8")),
            "baseline": json.loads((directory / "baseline_check.json").read_text(encoding="utf-8")),
            "manifest": json.loads((directory / "run_manifest.json").read_text(encoding="utf-8")),
        }


def footer(fig: plt.Figure, text: str) -> None:
    fig.text(0.01, 0.012, text, fontsize=8.2, color=NEUTRAL, ha="left", va="bottom")


def save(fig: plt.Figure, name: str, caption: str, tight: bool = True) -> None:
    path = FIG_DIR / name
    if tight:
        fig.tight_layout(rect=(0.0, 0.045, 1.0, 1.0))
    else:
        fig.subplots_adjust(left=0.07, right=0.98, top=0.88, bottom=0.09, hspace=0.45, wspace=0.22)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    print(f"[fig] {path.name} <- {caption}")


# ---------------------------------------------------------------- 图 1：对照成本矩阵
def fig_cost_matrix() -> None:
    rows = {
        "4-2": [
            ("BASE", 0.0),
            ("S-RH-H1", 0.0),
            ("S-RH-H3", -0.17850388144631021),
            ("S-RH-H7", -0.17851317994547972),
            ("S-RH-H14", -0.17852827121017942),
            ("PF-AR", -0.27220461974321947),
            ("S-ABL-SPILL", -2.864195423838536e-14),
            ("S-ABL-TIEBREAK", 8.51421157361586e-07),
            ("S-ABL-ETA-both", 0.0),
            ("S-ABL-ETA-charge_only", -4.308629448614899),
            ("S-ABL-ETA-discharge_only", -1.9880312802555087),
            ("S-ABL-ETA-round_trip", -3.1603596415758752),
        ],
        "4-3": [
            ("BASE", 0.0),
            ("C-ANCHOR-P03", -4.895231188970967),
            ("S-RH-H1", 0.0),
            ("S-RH-H3", -0.14917188144015775),
            ("S-RH-H7", -0.14918350721933332),
            ("S-RH-H14", -0.14920463657599548),
            ("S-ABL-SPILL", 0.05153666890181454),
            ("S-ABL-KAPPA1", 9.746295876619703e-14),
        ],
    }
    fig, axes = plt.subplots(1, 2, figsize=(FIG_W * 1.35, FIG_H * 1.05), sharex=False)
    for ax, chain in zip(axes, ("4-2", "4-3"), strict=True):
        labels = [name for name, _ in rows[chain]][::-1]
        values = [value for _, value in rows[chain]][::-1]
        colors = [WARNING if abs(v) < 1e-6 else (SECONDARY if v <= 0 else ACCENT) for v in values]
        y = np.arange(len(labels))
        ax.barh(y, values, color=colors, height=0.62)
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=9)
        ax.axvline(0.0, color=NEUTRAL, lw=1.0)
        ax.set_xlabel("交付期 D_req 费用相对主口径 BASE 的差（%，负 = 更省）")
        ax.set_title(f"链 {chain}：{len(labels)} 个全年口径对照（run003，365 天）", fontsize=12)
        for yi, value in zip(y, values, strict=True):
            if abs(value) < 1e-6:
                text, color = "0.000000%", NEUTRAL
            else:
                text, color = f"{value:+.6f}%", "#333333"
            offset = 0.02 * (ax.get_xlim()[1] - ax.get_xlim()[0])
            ax.text(value + (offset if value >= 0 else -offset), yi, text, va="center",
                    ha="left" if value >= 0 else "right", fontsize=8.2, color=color)
        ax.margins(x=0.22)
    axes[0].legend(
        handles=[
            plt.Rectangle((0, 0), 1, 1, color=SECONDARY),
            plt.Rectangle((0, 0), 1, 1, color=ACCENT),
            plt.Rectangle((0, 0), 1, 1, color=WARNING),
        ],
        labels=["更省（ΔC<0）", "更贵（ΔC>0）", "数值为 0（机制不激活）"],
        loc="upper left",
        fontsize=8.6,
    )
    fig.suptitle("prob04 ablation 成本矩阵：预注册对照 × 两链全年口径（ΔC = 对照费用 − 主口径费用）", fontsize=14)
    footer(
        fig,
        "数据：ablations/results/prob04_v001_ablation_{4-2,4-3}_run003/comparison.json（task "
        f"{TASK_IDS['4-2']} / {TASK_IDS['4-3']}，supervised，CPU HiGHS，seed=20260911）。"
        "4-2 的 14 个对照中 12 个为全年口径（本图），S-VAR / S-VAR-RH 为 12 代表日窗口口径（不可与全年费用同轴，见 report.md 表 3）；"
        "4-3 的 9 个对照中 8 个为全年口径（本图），S-VAR 为窗口口径。"
        "主口径 = PF-PERSIST 点预测 + 确定性 LP；结算一律用附件 4 实际价（A8-(b)）。"
        "C-ANCHOR-P03 为退化情景复现锚点（价格←附件 1 单日曲线），只作实现正确性闸门，不作交付值。"
    )
    save(fig, "ablation_cost_matrix.png", "成本矩阵（两链分列）")


# ---------------------------------------------------------------- 图 2：S-RH 前瞻深度
def fig_srh_depth() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(FIG_W * 1.3, FIG_H * 0.95))
    for ax, chain in zip(axes, ("4-2", "4-3"), strict=True):
        c4 = DATA[chain]["criteria"]["criteria"]["C4"]
        by_h = c4["D_full_cost_by_horizon"]
        costs = [by_h[f"H{h}"] for h in HORIZONS]
        base = costs[0]
        pct = [(c - base) / base * 100.0 for c in costs]
        x = np.arange(len(HORIZONS))
        ax.plot(x, pct, marker="o", color=CHAIN_COLOR[chain], lw=2.0, label="D_full（365 天）相对 H=1 的差")
        ax.axhline(0.0, color=NEUTRAL, lw=1.0, ls="--")
        ax.scatter([0], [0.0], s=110, facecolors="none", edgecolors=WARNING, lw=2.0, zorder=5,
                   label="C3 基线闸门：H=1 逐位复现主口径")
        for xi, value in zip(x, pct, strict=True):
            ax.annotate(f"{value:+.4f}%", (xi, value), textcoords="offset points", xytext=(0, 9),
                        ha="center", fontsize=8.4)
        ax.set_xticks(x)
        ax.set_xticklabels([f"H={h}" for h in HORIZONS])
        ax.set_xlabel("S-RH 前瞻深度 H（天；超 24 h 的负荷/光伏用历史同月均值，价格用 PF-PERSIST）")
        ax.set_ylabel("D_full 费用相对 H=1 的差（%）")
        gate = "C3 pass：H=1 逐位复现主口径"
        if chain == "4-2":
            mono = "C4 成立：H 增大则费用不增，无反例"
        else:
            mono = "C4 不适用（§3.3.4 冻结边界），仅报数值"
        ax.set_title(f"链 {chain}：D_full 费用随 H 的响应", fontsize=12)
        ax.set_ylim(min(pct) * 1.35, 0.03)
        ax.annotate(
            f"{gate}\n{mono}",
            xy=(0.03, 0.06), xycoords="axes fraction", fontsize=8.4, color="#333333",
            bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": NEUTRAL, "alpha": 0.95},
        )
        ax.legend(loc="upper right", fontsize=8.4)
    fig.suptitle("prob04 S-RH：计划层跨日前瞻深度对费用与日边界储电量的影响（两链分列）", fontsize=14)
    footer(
        fig,
        "数据：run003 criteria.json 的 C4.D_full_cost_by_horizon。4-2 的 C4 是预注册方向性判据（H 增大则费用不增）；"
        "4-3 按 plan_v001 §3.3.4 的冻结边界只报数值、不作单调性要求（深度只作用于计划层的 0:00 决策窗口，"
        "6:00/12:00/18:00 调整层仍只支配当天）。两个 absolute 值见 report.md 表 2。"
    )
    save(fig, "ablation_srh_depth.png", "S-RH 深度响应（两链）")


# ---------------------------------------------------------------- 图 3：S-VAR 首阶段对冲形状
def fig_svar_hedge() -> None:
    fig = plt.figure(figsize=(FIG_W * 1.3, FIG_H * 1.1))
    gs = fig.add_gridspec(2, 2, height_ratios=[2.0, 1.0], hspace=0.45, wspace=0.22)
    ax_main = fig.add_subplot(gs[0, :])
    axes_block = [fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])]
    hours = (np.arange(SEG) + 0.5) * DT_H
    for chain in ("4-2", "4-3"):
        cases = DATA[chain]["results"]["S-VAR"]["cases"]
        diffs = np.array([np.asarray(c["plan_shape"]["diff"], dtype=float) for c in cases])
        mean_diff = diffs.mean(axis=0)
        ax_main.plot(hours, mean_diff, color=CHAIN_COLOR[chain], lw=1.6,
                     label=f"链 {chain}（12 个代表日逐时段均值）")
    ax_main.axhline(0.0, color=NEUTRAL, lw=0.9, ls="--")
    ax_main.set_xlim(0, 24)
    ax_main.set_xticks(range(0, 25, 2))
    ax_main.set_xlabel("计划窗时段（AS01 左端点口径，0:10→24:10，相位前移 10 分钟）")
    ax_main.set_ylabel("b^(S-VAR) − b^(BASE) 的 12 日均值（kWh/时段）")
    ax_main.set_title("S-VAR 首阶段计划购电量 b 的形状差异：两阶段随机 vs 主口径点预测", fontsize=12.5)
    ax_main.legend(loc="upper left", fontsize=8.8)
    top = DATA["4-2"]["results"]["S-VAR"]["first_stage_shape"]["top_periods"][:3]
    ax_main.annotate(
        "4-2 幅度最大 3 个时段：" + "，".join(
            f"第 {t['period']} 格（{t['mean_diff_kwh']:+.1f} kWh）" for t in top
        ),
        xy=(0.015, 0.03), xycoords="axes fraction", fontsize=8.4, color="#333333",
    )
    for ax, chain in zip(axes_block, ("4-2", "4-3"), strict=True):
        blocks = DATA[chain]["results"]["S-VAR"]["first_stage_shape"]["block_mean_diff_kwh"]
        x = np.arange(len(blocks))
        ax.bar(x, blocks, color=CHAIN_COLOR[chain], width=0.62)
        ax.axhline(0.0, color=NEUTRAL, lw=0.9)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{4 * i}–{4 * (i + 1)}h" for i in range(len(blocks))], fontsize=8.6)
        ax.set_title(f"链 {chain}：4 小时分块均值差", fontsize=10)
        ax.set_ylabel("kWh/时段", fontsize=9)
    fig.suptitle("prob04 S-VAR（24 经验场景两阶段随机）：对冲体现在哪些时段（两链分列）", fontsize=14)
    footer(
        fig,
        "数据：run003 results.json 的 S-VAR.cases[*].plan_shape.diff（12 代表日 × 144 时段）与 first_stage_shape.block_mean_diff_kwh。"
        "场景池 = 代表日之前（≤ d−1）的同型日（d′ mod 7 == d mod 7），确定性等距抽 24 个、等概率；该经验分布只是对照口径，不是真实价格分布。"
        "计划购电账单本身场景相关（团队 R-1 必须的改写，不含 c^base·P_plan）；结算一律用附件 4 实际价。"
    )
    save(fig, "ablation_svar_hedge.png", "S-VAR 首阶段对冲形状（两链）", tight=False)


# ---------------------------------------------------------------- 图 4：日边界储电量行为
def fig_soc_boundary() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(FIG_W * 1.3, FIG_H * 0.95))
    for ax, chain in zip(axes, ("4-2", "4-3"), strict=True):
        stats = DATA[chain]["criteria"]["criteria"]["C_RH_BOUNDARY"]["state_end_statistics"]
        means = [stats[f"S-RH-H{h}"]["mean"] for h in HORIZONS]
        lows = [stats[f"S-RH-H{h}"]["days_at_lower_bound"] for h in HORIZONS]
        unique = [stats[f"S-RH-H{h}"]["unique"] for h in HORIZONS]
        x = np.arange(len(HORIZONS))
        ax.bar(x, means, color=CHAIN_COLOR[chain], width=0.55, label="E_{d,144} 日均值（kWh）")
        ax.axhline(E_MIN, color=WARNING, lw=1.4, ls="--", label="E_min = 1200 kWh（下限）")
        for xi, (m, lo, uq) in enumerate(zip(means, lows, unique, strict=True)):
            ax.annotate(f"贴下限 {lo}/365 天\n唯一取值 {uq}", (xi, m), textcoords="offset points",
                        xytext=(0, 10), ha="center", fontsize=8.2)
        ax.set_xticks(x)
        ax.set_xticklabels([f"H={h}" for h in HORIZONS])
        ax.set_ylim(0, max(max(means), E_MIN) * 1.42)
        ax.set_ylabel("交付期末储电量 E_{d,144}（kWh）")
        ax.set_xlabel("S-RH 前瞻深度 H（天）")
        ax.set_title(f"链 {chain}：日边界储电量行为（回应 prob03 E8/R18；365 天）", fontsize=11)
        ax.legend(loc="upper left", fontsize=8.4)
    fig.suptitle("prob04 S-RH：H = 1 时两链日边界均贴 E_min（不跨日携带电量），H > 1 才出现跨日携带", fontsize=14)
    footer(
        fig,
        "数据：run003 criteria.json 的 C_RH_BOUNDARY.state_end_statistics（由 run003 任务从逐日 E_{d,144} 序列统计后落盘）。"
        "H = 1 时点数与主口径逐位一致（C3 pass），其 E_{d,144} 贴 E_min 属主口径的终端自由后果；"
        "H > 1 的跨日携带量是前瞻深度的结构性发现，不作为稳定性判据。"
        "说明：任务只落盘统计量、未落盘逐日 E_{d,144} 序列（技术债 A-DR1 同类）。"
    )
    save(fig, "ablation_soc_boundary.png", "日边界储电量行为（两链）")


def main() -> int:
    load()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig_cost_matrix()
    fig_srh_depth()
    fig_svar_hedge()
    fig_soc_boundary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
