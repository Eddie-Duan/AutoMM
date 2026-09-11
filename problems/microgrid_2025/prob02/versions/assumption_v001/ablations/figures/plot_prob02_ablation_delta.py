# -*- coding: utf-8 -*-
"""prob02 ablation 费用对照图的重绘（论文版，无解释性注释）：改用「与 M1 的差值」与「对数相对偏差」口径。

原图 `ablation_model_cost.png` 把 7 个模型的全期费用画在同一线性轴上（0 → 1.4e7 元），
而全部模型的极差只有 26,894.74 元 = 全期的 0.195%（不到 1 像素），故柱子完全不可分辨、
不携带有效信息。本脚本读同一份 `comparison.json`，改画：
  上：ΔC = C(model) − C(M1)（元，线性小刻度）
  下：|ΔC|/C(M1)（‰，对数刻度；恒等者单列标注）
只读结果文件，不修改任何既有产物；输出新文件名，不覆盖原图。
"""

from __future__ import annotations

import io
import json
import pathlib

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
matplotlib.rcParams["axes.unicode_minus"] = False

def _project_root() -> pathlib.Path:
    node = pathlib.Path(__file__).resolve()
    while node != node.parent and not (node / "runtime" / "workflow_state.json").exists():
        node = node.parent
    return node


ROOT = _project_root()
COMPARISON = (
    ROOT
    / "problems/microgrid_2025/prob02/versions/assumption_v001/ablations"
    / "results/prob02_v001_ablation_run001/comparison.json"
)
OUT = (
    ROOT
    / "problems/microgrid_2025/prob02/versions/assumption_v001/ablations"
    / "figures/prob02_ablation_model_cost_delta.png"
)
ORDER = ["M1", "M7", "M5", "M2a", "M2b", "M4", "M3_full"]
LABELS = {
    "M1": "M1\n基准LP",
    "M7": "M7\n独立实现",
    "M5": "M5\n终端=6000",
    "M2a": "M2a\n精确分解",
    "M2b": "M2b\n日终自由递推",
    "M4": "M4\n每日独立",
    "M3_full": "M3\n互补MILP",
}
PALETTE = {"primary": "#1F4E79", "secondary": "#70AD47", "accent": "#ED7D31",
           "neutral": "#7F8C8D", "warning": "#C00000"}


def main() -> int:
    models = {row["label"]: row for row in json.load(io.open(COMPARISON, encoding="utf-8"))["models"]}
    base = models["M1"]["objective_yuan"]
    labels = [LABELS[key] for key in ORDER]
    costs = np.array([models[key]["objective_yuan"] for key in ORDER], dtype=float)
    delta = costs - base
    rel_permille = delta / base * 1000.0

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10, 6), dpi=180, gridspec_kw={"height_ratios": [1.55, 1.0], "hspace": 0.55}
    )
    fig.suptitle("结构/模型族对照：与 M1 的费用差（全期 365 天）", fontsize=14, y=0.99)

    # ---- 上：ΔC（元）----
    colors = []
    for value in delta:
        if abs(value) < 1e-9:
            colors.append(PALETTE["neutral"])
        elif value < 10.0:
            colors.append(PALETTE["primary"])
        elif value < 1e4:
            colors.append(PALETTE["secondary"])
        else:
            colors.append(PALETTE["accent"])
    bars = ax1.bar(range(len(ORDER)), delta, color=colors, width=0.62)
    for bar, value in zip(bars, delta):
        note = "0" if abs(value) < 1e-9 else ("%+.2f" % value if abs(value) < 10 else format(value, "+,.2f"))
        ax1.annotate(
            note,
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            textcoords="offset points",
            xytext=(0, 5 if value >= 0 else -14),
            ha="center",
            fontsize=9,
            color=PALETTE["warning"] if abs(value) >= 1e4 else "#333333",
        )
    ax1.set_ylabel("ΔC = C(模型) − C(M1)  （元）", fontsize=11)
    ax1.set_xticks(range(len(ORDER)))
    ax1.set_xticklabels(labels, fontsize=9)
    ax1.axhline(0.0, color="#333333", lw=0.8)
    ax1.set_ylim(-0.12 * delta.max(), 1.22 * delta.max())
    ax1.grid(axis="y", ls=":", color="#BBBBBB", lw=0.7)
    ax1.set_axisbelow(True)

    # ---- 下：|ΔC|/C*（‰，对数）----
    floor = 3e-4
    heights, ticks = [], []
    for value in rel_permille:
        if abs(value) < 1e-9:
            heights.append(floor)
            ticks.append("0")
        else:
            heights.append(abs(value))
            ticks.append("%.4g" % abs(value) if abs(value) < 0.01 else "%.3f" % abs(value))
    bars2 = ax2.bar(range(len(ORDER)), heights, width=0.62,
                    color=[PALETTE["neutral"] if abs(v) < 1e-9 else PALETTE["secondary"] for v in rel_permille])
    for bar, text, value in zip(bars2, ticks, rel_permille):
        ax2.annotate(
            text, (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            textcoords="offset points", xytext=(0, 5), ha="center", fontsize=9,
            color=PALETTE["warning"] if abs(value) >= 1.0 else "#333333",
        )
    ax2.axhline(1.0, color=PALETTE["accent"], ls="--", lw=1.0)
    ax2.annotate("1‰", (len(ORDER) - 0.42, 1.0), xytext=(4, 3),
                 textcoords="offset points", fontsize=8, color=PALETTE["accent"])
    ax2.set_yscale("log")
    ax2.set_ylim(floor * 0.8, max(heights) * 3.4)
    ax2.set_ylabel("|ΔC| / C(M1)  （‰，对数轴）", fontsize=11)
    ax2.set_xticks(range(len(ORDER)))
    ax2.set_xticklabels(labels, fontsize=9)
    ax2.grid(axis="y", ls=":", color="#BBBBBB", lw=0.7)
    ax2.set_axisbelow(True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("written:", OUT.relative_to(ROOT))
    print("base C(M1) = %.6f 元" % base)
    for key, d, r in zip(ORDER, delta, rel_permille):
        print("  %-9s ΔC=%+15.6f 元   相对=%9.5f ‰" % (key, d, r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
