# -*- coding: utf-8 -*-
"""prob01 ablation 交付图表：从 task 产物重绘并登记到 figures.yaml。

- 输入（只读）：ablations/results/prob01_v003_ablation_run001/{comparison.json,dp_granularity.json,summary.json}
  —— 全部数值逐项取自 task c1faaa09dedfb103c598 的产物，本脚本**不重新求解**任何模型。
- 本脚本生成的是「登记版」图件，写入 ablations/figures/；task 自身产出的
  ablations/results/.../figures/ 保持原样不改动（实验原始图）。
  task 原始图中 ablation_waterfall / ablation_complexity_tradeoff 存在文字被坐标轴或相邻点标注遮挡，
  故按 config/visualization.yaml 统一重绘（同数据、同口径），并统一改为中文标注以与 prob01 交付图风格一致。
- 自动质检 inspect_png 写 *.quality.json；register_figure 登记 problem 级 figures.yaml。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[7]
sys.path.insert(0, str(ROOT / "scripts"))
from automm.visualization import inspect_png, register_figure, stable_figure_id  # noqa: E402

PROBLEM_ID = "microgrid_2025"
QUESTION_ID = "prob01"
ASSUMPTION_VERSION = "assumption_v003"
FORMULATION_VERSION = "formulation_v001"
TASK_ID = "c1faaa09dedfb103c598"

ABL = ROOT / "problems/microgrid_2025/prob01/versions/assumption_v003/ablations"
RES = ABL / "results/prob01_v003_ablation_run001"
FIGDIR = ABL / "figures"
STYLE_CONFIG = "config/visualization.yaml"
FONT = "Microsoft YaHei"

PRIMARY = "#1F4E79"
SECONDARY = "#70AD47"
ACCENT = "#ED7D31"
NEUTRAL = "#7F8C8D"
WARNING = "#C00000"

plt.rcParams.update({
    "figure.dpi": 180,
    "savefig.dpi": 180,
    "font.size": 11,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "font.sans-serif": [FONT, "DejaVu Sans"],
    "axes.unicode_minus": False,
})

comparison = json.loads((RES / "comparison.json").read_text(encoding="utf-8"))
dp_granularity = json.loads((RES / "dp_granularity.json").read_text(encoding="utf-8"))
summary = json.loads((RES / "summary.json").read_text(encoding="utf-8"))
base_cost = float(comparison["baseline_objective_yuan"])
rows = comparison["rows"]
source_hash = hashlib.sha256(
    (RES / "comparison.json").read_bytes() + (RES / "dp_granularity.json").read_bytes()
).hexdigest()
SOURCE_DATA = (
    "problems/microgrid_2025/prob01/versions/assumption_v003/ablations/results/"
    "prob01_v003_ablation_run001/comparison.json"
    " + problems/microgrid_2025/prob01/versions/assumption_v003/ablations/results/"
    "prob01_v003_ablation_run001/dp_granularity.json"
)

registered: list[dict] = []


def emit(stem: str, kind: str, title: str, caption: str, *, in_paper: bool) -> None:
    FIGDIR.mkdir(parents=True, exist_ok=True)
    path = FIGDIR / f"{stem}.png"
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close("all")
    quality = inspect_png(path, PROBLEM_ID, QUESTION_ID)
    style = {"dpi": 180, "palette": [PRIMARY, SECONDARY, ACCENT, NEUTRAL, WARNING], "font": FONT}
    stable_id = stable_figure_id(
        problem_id=PROBLEM_ID, question_id=QUESTION_ID, kind=kind, title=title,
        source_hash=source_hash, x=None, y=[], style=style,
    )
    item = {
        "stable_id": stable_id,
        "problem_id": PROBLEM_ID,
        "question_id": QUESTION_ID,
        "assumption_version": ASSUMPTION_VERSION,
        "formulation_version": FORMULATION_VERSION,
        "task_id": TASK_ID,
        "kind": kind,
        "title": title,
        "caption": caption,
        "path": path.relative_to(ROOT).as_posix(),
        "source_data": SOURCE_DATA,
        "source_hash": source_hash,
        "script": (FIGDIR / "plot_ablation_figures.py").relative_to(ROOT).as_posix(),
        "font": FONT,
        "style_config": STYLE_CONFIG,
        "included_in_summary": True,
        "included_in_paper": in_paper,
        "quality_report": path.with_suffix(".quality.json").relative_to(ROOT).as_posix(),
        "quality_status": quality["status"],
    }
    register_figure(PROBLEM_ID, item)
    registered.append({"stable_id": stable_id, "path": item["path"], "quality": quality["status"],
                       "included_in_paper": in_paper, "size": [quality["width"], quality["height"]]})


# ---------------------------------------------------------------- 图 1：模型 × 指标费用对比
labels = [row["label"] for row in rows]
costs = [float(row["objective_yuan"]) for row in rows]
rels = [(value - base_cost) / base_cost * 100.0 for value in costs]
colors = [PRIMARY if label == "A_baseline_LP" else SECONDARY for label in labels]

fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.0))
axes[0].bar(range(len(labels)), costs, color=colors)
axes[0].axhline(base_cost, color=WARNING, linestyle="--", linewidth=1.1, label="accepted LP $C^*$=35126.95 元")
axes[0].set_xticks(range(len(labels)))
axes[0].set_xticklabels(labels, rotation=55, ha="right", fontsize=8)
axes[0].set_ylabel("全天购电费 $C$（元）")
axes[0].set_title("模型族与结构消融：目标值对比")
axes[0].legend(fontsize=8)
axes[0].set_ylim(0, max(costs) * 1.12)
axes[1].bar(range(len(labels)), rels, color=colors)
axes[1].axhline(0, color="black", linewidth=0.8)
axes[1].set_xticks(range(len(labels)))
axes[1].set_xticklabels(labels, rotation=55, ha="right", fontsize=8)
axes[1].set_ylabel("相对 $C^*$ 的变化（%，负值=更省）")
axes[1].set_title("相对 accepted LP 的偏差（同数据/同预算）")
axes[1].set_ylim(min(rels) * 1.25, max(rels) * 1.25)
fig.tight_layout()
emit("ablation_model_cost", "model_cost_comparison",
     "模型族与结构消融的费用对比（A–F 全部实跑，含 DP 四档粒度）",
     "左：12 个对照的全天购电费 C（元），红虚线为 accepted LP 的 $C^*$=35126.948589 元；右：相对 $C^*$ 的百分比变化（负值表示比 accepted LP 更省）。"
     "A/B/E/F_place_both 与 $C^*$ 完全相同；C 族（SOC 离散化 DP）随网格加密单调逼近；D（去掉日周期约束）因末状态可放空至 1200 kWh 而最省（−6.312%）。"
     "数据来源：task c1faaa09dedfb103c598 的 comparison.json（未重新求解）。",
     in_paper=True)

# ---------------------------------------------------------------- 图 2：DP 粒度-偏差
points = [p for p in dp_granularity["points"] if p.get("objective_yuan")]
xs = [float(p["step_kwh"]) for p in points]
ys = [float(p["objective_yuan"]) for p in points]
fig, ax = plt.subplots(figsize=(8.4, 5.0))
ax.plot(xs, ys, marker="o", color=PRIMARY, label="DP 目标值")
for x, y in zip(xs, ys):
    ax.annotate(f"{(y - base_cost) / base_cost * 100:+.3f}%", (x, y), textcoords="offset points",
                xytext=(0, 9), ha="center", fontsize=9)
ax.axhline(base_cost, color=WARNING, linestyle="--", linewidth=1.1, label="accepted LP $C^*$=35126.95 元")
ax.set_xscale("log")
ax.set_xticks(xs)
ax.set_xticklabels([f"{int(x)}" for x in xs])
ax.set_xlabel("SOC 离散化步长 $h$（kWh，对数轴）")
ax.set_ylabel("DP 最优目标值（元）")
ax.set_title("离散化 DP 的粒度-偏差：步长越小越逼近 LP")
ax.legend(fontsize=9)
ax.margins(x=0.12, y=0.16)
fig.tight_layout()
emit("ablation_dp_granularity", "dp_granularity_bias",
     "离散化 DP 粒度-偏差曲线：h=400/200/100/50 kWh 的费用偏差",
     "红色虚线为 accepted LP 的 $C^*$=35126.948589 元；蓝点为 SOC 离散化 DP 在各状态步长下的最优值，标注相对 $C^*$ 的偏差："
     "+7.087%（h=400）、+3.063%（h=200）、+1.600%（h=100）、+0.791%（h=50），随步长减小单调下降且恒 ≥ $C^*$（网格受限下 DP 是精确最优）。"
     "预注册判据 C3 要求 h=50 的偏差 ∈[0,1%]，实测 +0.791% 通过，余量约 0.21 个百分点。数据来源：task c1faaa09dedfb103c598 的 dp_granularity.json。",
     in_paper=True)

# ---------------------------------------------------------------- 图 3：消融瀑布（修正标签遮挡）
ordered = sorted(rows, key=lambda row: float(row["objective_yuan"]))
names = [row["label"] for row in ordered]
values = [float(row["objective_yuan"]) - base_cost for row in ordered]
fig, ax = plt.subplots(figsize=(9.8, 5.0))
ax.barh(range(len(names)), values, color=[PRIMARY if v >= 0 else WARNING for v in values])
ax.axvline(0, color="black", linewidth=0.8)
ax.set_yticks(range(len(names)))
ax.set_yticklabels(names, fontsize=9)
for index, value in enumerate(values):
    ax.annotate(f"{value:+.2f}", (value, index), textcoords="offset points",
                xytext=(7 if value >= 0 else -7, 0), va="center",
                ha="left" if value >= 0 else "right", fontsize=9)
span = max(abs(min(values)), abs(max(values)))
ax.set_xlim(-span * 1.45, span * 1.35)
ax.set_xlabel("$\\Delta C$ 相对 accepted LP $C^*$（元）")
ax.set_title("消融瀑布：各对照相对 accepted LP 的费用变化")
fig.tight_layout()
emit("ablation_waterfall", "ablation_waterfall",
     "消融瀑布图：日周期约束、弃光变量与效率作用位置的经济贡献",
     "$\\Delta C$ = 对照费用 − accepted LP 的 $C^*$（元）；正值=更贵，负值=更省。D_no_periodic（去掉 $E_0=E_{144}$）−2217.08 元即日周期约束的经济价值；"
     "E_no_spill（删除弃光变量 $s_t$）与 B_milp（互补二元）、F_place_both 均为 +0.00 元（不改变最优值）；C 族 DP 为离散化偏差（+277.72 ~ +2489.57 元）；"
     "F 族单侧/往返效率口径分别比 accepted 的两侧 0.9 省 958.34 / 1325.45 / 1710.42 元。数据来源：comparison.json。",
     in_paper=True)

# ---------------------------------------------------------------- 图 4：复杂度-费用（修正标签重叠/截断）
offsets = {
    "A_baseline_LP": (-8, 12, "right"),
    "E_no_spill": (-8, -18, "right"),
    "F_place_both": (10, -16, "left"),
    "B_milp": (8, 8, "left"),
    "D_no_periodic": (8, -4, "left"),
    "F_place_charge_only": (8, -4, "left"),
    "F_place_discharge_only": (8, -4, "left"),
    "F_place_round_trip": (8, -4, "left"),
    "C_dp_h400": (8, -12, "left"),
    "C_dp_h200": (8, 8, "left"),
    "C_dp_h100": (8, 8, "left"),
    "C_dp_h050": (-8, 10, "right"),
}
fig, ax = plt.subplots(figsize=(9.0, 5.4))
for row in rows:
    complexity = row.get("complexity") or {}
    seconds = max(float(complexity.get("solve_seconds") or 0.0), 1e-4)
    variables = complexity.get("variables")
    ax.scatter(seconds, float(row["objective_yuan"]), s=48, color=PRIMARY if row["label"] == "A_baseline_LP" else SECONDARY)
    dx, dy, ha = offsets.get(row["label"], (8, 4, "left"))
    ax.annotate(f"{row['label']}\n(vars={variables})", (seconds, float(row["objective_yuan"])),
                textcoords="offset points", xytext=(dx, dy), ha=ha, fontsize=8)
ax.axhline(base_cost, color=WARNING, linestyle="--", linewidth=1.1, label="accepted LP $C^*$=35126.95 元")
ax.set_xscale("log")
ax.set_xlabel("求解时间（s，对数轴）")
ax.set_ylabel("目标值 $C$（元）")
ax.set_title("复杂度-费用权衡：变量规模与求解时间")
ax.legend(fontsize=9, loc="center right")
ax.margins(x=0.30, y=0.16)
fig.tight_layout()
emit("ablation_complexity_tradeoff", "complexity_tradeoff",
     "复杂度-费用权衡：各对照的变量规模与求解时间",
     "横轴为求解时间（s，对数轴），纵轴为全天购电费（元）；点标注给出对照编号与变量数。DP 族变量数最少（25–193）但目标值最差（离散化偏差）；"
     "B_milp 变量数最多（864，含 144 个二元变量）而目标值与 accepted LP 相同；结构性对照（D/E/F）变量数均为 720（E 为 576，删除 $s_t$）。"
     "全部 case 在 60 s 预算内完成。数据来源：comparison.json 的 complexity 字段（solve_seconds）。",
     in_paper=False)

print(json.dumps({"registered": registered, "source_hash": source_hash}, ensure_ascii=False, indent=2))
