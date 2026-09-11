# -*- coding: utf-8 -*-
"""prob03 ablation 报告级配图重绘（只读，修正 task 原始图的字段口径缺陷）。

背景：task 产出的 `figures/ablation_identities.png` 取 `case.json.summary["identities"]` 下的
`settlement_balance_max` / `state_transition_max` / `cross_day_continuity_max`，但这三个键实际位于
`summary["residuals"]`（`identities` 下的键名是 `settlement_max` / `transition_max` / `continuity_max`），
故所有柱值被 `or 0.0` + 下限 1e-16 兜底成常数，图 4 无法反映真实残差量级（真实最大残差 ~1e-7，M2b 跨日连续性 4800）。

本脚本只读 `ablations/results/prob03_v001_ablation_run001/` 的既有 JSON，重绘**修正版**图到
`ablations/figures/`（新目录，**不覆盖** task 原始图，也**不改** `ablations/code/`）。
按团队 B5/R24 纪律，ablation 图件**不**调用 record_figure_review、不作为交付图表。
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# 与 task 侧（ablations/code/ablation_prob03.py）一致的中文字体栈与负号设置
FONT_STACK = ["Microsoft YaHei", "SimHei", "DengXian", "SimSun", "DejaVu Sans"]
plt.rcParams["font.sans-serif"] = FONT_STACK
plt.rcParams["axes.unicode_minus"] = False

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
ABL_RES = os.path.join(HERE, "results", "prob03_v001_ablation_run001")
OUT = os.path.join(HERE, "figures")

ORDER = ["M1", "M2a", "M2b", "M3", "M4", "M5a", "M5b", "M7_D2B", "M7_D2C", "M7_D5B", "M8", "M8b"]
METRICS = [
    ("settlement_balance_max", "逐时段平衡（结算层）"),
    ("state_transition_max", "状态转移 (I5d)"),
    ("cross_day_continuity_max", "跨日连续性 (I4d)"),
    ("cost_decomposition_max", "费用分解恒等式"),
]
FLOOR = 1e-12

cases = {}
for cid in ORDER:
    p = os.path.join(ABL_RES, cid, "case.json")
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as fh:
            cases[cid] = json.load(fh)["summary"]["residuals"]

os.makedirs(OUT, exist_ok=True)

fig, ax = plt.subplots(figsize=(12.0, 5.6), dpi=150)
width = 0.2
xs = np.arange(len(cases))
colors = ["#1f4e79", "#c00000", "#2e7d32", "#7f7f7f"]
for offset, (key, label) in enumerate(METRICS):
    values = [max(float(cases[cid].get(key, 0.0)), FLOOR) for cid in cases]
    ax.bar(xs + (offset - 1.5) * width, values, width=width, label=label, color=colors[offset])
ax.set_yscale("log")
ax.set_ylim(FLOOR / 3.0, 2e4)
ax.axhline(1e-6, color="k", linestyle="--", linewidth=1.0)
ax.text(len(cases) - 0.5, 1.3e-6, "判据阈值 1e-6", fontsize=8, ha="right")
ax.set_xticks(xs)
ax.set_xticklabels(list(cases), rotation=30, ha="right", fontsize=9)
ax.set_ylabel("最大残差（kWh 或 元，对数轴；≤1e-12 显示为下限）")
ax.set_title("prob03 消融：四条恒等式最大残差（修正版；M2b 跨日连续性 4800 kWh 为口径预期违反，非缺陷）")
ax.annotate("M2b 跨日连续性 = 4800.000000（日初复位口径的预期违反）",
            xy=(2 + 1.5 * width, 4800.0), xytext=(2.6, 2.0e3), fontsize=8,
            arrowprops=dict(arrowstyle="->", color="#c00000", lw=1.0), color="#c00000")
ax.legend(fontsize=8, loc="lower right")
fig.tight_layout()
path = os.path.join(OUT, "ablation_identities_fixed.png")
fig.savefig(path)
plt.close(fig)
print("written:", os.path.relpath(path, ROOT))
print("M2b cross_day_continuity_max =", cases["M2b"]["cross_day_continuity_max"])
print("max state_transition_max =", max(cases[c]["state_transition_max"] for c in cases))
