# -*- coding: utf-8 -*-
"""prob02 `b_cap_curve` 的**论文版**重绘（团队裁定 R8）。

为什么要重绘：原图 `ablation_b_cap_curve.png` 由 ablation 阶段代码生成，标题里带内部文档编号
「（阈值 β 见勘误 R5）」—— 论文版不能出现内部勘误编号。**不修改已完成阶段的代码**
（`ablations/code/ablation_prob02.py` 的 hash 已登记在 `run_manifest.json`，改它会破坏审计链），
改为在 `ablations/figures/` 下另出一个论文版图件（与 R6 对 `ablation_model_cost.png` 的处置一致）。

改进点（相对原图，均为呈现层）：
- 标题去掉内部勘误编号；用「激活阈值夹逼区间」代替「见勘误 R5」。
- Σq_em 改用**对数轴**：原图线性轴 0–8×10⁶ 会把 β 附近的 8,707.40 kWh 压成 0（不可见），
  这是原图的真实可读性缺陷；对数轴让 8.7×10³ → 7.8×10⁶ 的机制可见。
- 拆成上下双面板（共享等距网格 X 轴），不再用双 Y 轴。
- 该网格 5 个点 Σq_em = 0（B ≥ 4,375），对数轴无法表示 0，故零值点以底部灰色标记 + 「0」标注
  （与 `prob02_ablation_model_cost_delta.png` 的同一处置保持一致，不产生误读）。

数据源：`ablations/results/prob02_v001_ablation_run001/comparison.json` 的 `purchase_cap`
（10 个网格点，与 ablation task `5b87ce0a8d9e4706c82c` 同源，**不重跑任何计算**）。
"""

from __future__ import annotations

import hashlib
import io
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PRIMARY = "#1F4E79"
ACCENT = "#ED7D31"
NEUTRAL = "#7F8C8D"
WARNING = "#C00000"
BAND = "#F2C14E"
FONT = "Microsoft YaHei"
ZERO_FLOOR = 3.0e2          # 对数轴上的零值置底高度（kWh）
Y_MIN, Y_MAX = 2.0e2, 2.2e7

RUN = "prob02_v001_ablation_run001"


def project_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    while here != here.parent and not (here / "runtime" / "workflow_state.json").exists():
        here = here.parent
    return here


def main() -> int:
    root = project_root()
    base = root / "problems" / "microgrid_2025" / "prob02" / "versions" / "assumption_v001" / "ablations"
    src = base / "results" / RUN / "comparison.json"
    rows = sorted(
        json.load(io.open(src, encoding="utf-8"))["purchase_cap"],
        key=lambda r: r["b_cap_kw"],
    )  # 升序：2000 → 10326
    b = [float(r["b_cap_kw"]) for r in rows]
    q = [float(r["q_em_kwh"]) for r in rows]
    c = [float(r["objective_yuan"]) for r in rows]
    c0 = c[-1]              # 基线 = 上限最大的网格点（上限不受限、无绑定），= M1 全期费用
    gain = [x - c0 for x in c]   # > 0 表示比无绑定基线更贵

    plt.rcParams["font.sans-serif"] = [FONT, "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10.0, 8.0), sharex=True, gridspec_kw={"height_ratios": [1.35, 1.0]}
    )
    x = list(range(len(b)))

    # ---------- 面板 A：Σq_em（对数轴） ----------
    pos = [v if v > 0 else ZERO_FLOOR for v in q]
    ax1.plot(x, pos, "-", color=PRIMARY, linewidth=1.8, zorder=3)
    nz = [(i, v) for i, v in enumerate(q) if v > 0]
    ax1.plot([i for i, _ in nz], [v for _, v in nz], "o", color=PRIMARY, markersize=7, zorder=4,
             label="紧急购电总量 Σq_em")
    zero = [i for i, v in enumerate(q) if v == 0]
    ax1.plot(zero, [ZERO_FLOOR] * len(zero), "o", color=NEUTRAL, markersize=7, zorder=4,
             label="Σq_em = 0（不激活）")
    for i in zero:
        ax1.annotate("0", (i, ZERO_FLOOR), textcoords="offset points", xytext=(0, -13),
                     ha="center", fontsize=9, color=NEUTRAL)
    for i, v in nz:
        ax1.annotate(
            format(int(round(v)), ","),
            (i, v), textcoords="offset points", xytext=(0, 9), ha="center", fontsize=9, color=PRIMARY,
        )

    i4357, i4218 = x[b.index(4375.0)], x[b.index(4218.75)]
    ax1.axvspan(i4218, i4357, color=BAND, alpha=0.45, zorder=0,
                label="激活阈值夹逼区间 β ∈ (4,218.75, 4,375.00] kW")

    ax1.set_yscale("log")
    ax1.set_ylim(Y_MIN, Y_MAX)
    ax1.set_ylabel("紧急购电总量 Σq_em（kWh，对数轴）", fontsize=11)
    ax1.set_title("外网购电上限对紧急购电与总费用的影响（全期 365 天）", fontsize=14, pad=12)
    ax1.grid(alpha=0.25, which="both", linestyle=":")
    leg1 = ax1.legend(loc="upper right", fontsize=9, framealpha=0.92)
    leg1.get_frame().set_edgecolor("0.8")

    # ---------- 面板 B：全期总费用 ----------
    ax2.axhline(c0, color=NEUTRAL, linestyle="--", linewidth=1.2, zorder=1,
                label="上限不受限（无绑定）基线")
    ax2.plot(x, c, "-", color=ACCENT, linewidth=1.8, marker="s", markersize=6, zorder=3,
             label="全期总费用")
    for i, text in ((0, "%s 元" % format(int(round(c[0])), ",")),
                    (i4218, "+%s 元" % format(int(round(gain[i4218])), ",")),
                    (len(b) - 1, "基线 %s 元" % format(int(round(c0)), ","))):
        align = "left" if i == 0 else ("right" if i == len(b) - 1 else "center")
        ax2.annotate(
            text, (i, c[i]), textcoords="offset points", xytext=(0, 11), ha=align, va="bottom",
            fontsize=9, color=ACCENT,
        )
    ax2.axvspan(i4218, i4357, color=BAND, alpha=0.45, zorder=0)
    ax2.set_ylabel("全期总费用（元）", fontsize=11)
    ax2.grid(alpha=0.25, linestyle=":")
    leg2 = ax2.legend(loc="upper right", fontsize=9, framealpha=0.92)
    leg2.get_frame().set_edgecolor("0.8")
    ax2.set_ylim(bottom=c0 - (max(c) - c0) * 0.06, top=max(c) * 1.22)

    ax2.set_xticks(x)
    ax2.set_xticklabels([("%g" % v) if v == int(v) else ("%g" % v) for v in b], rotation=45, ha="right", fontsize=9)
    ax2.set_xlabel("外网购电上限 B（kW；网格点等距排列，标签为实际上限值）", fontsize=11)
    ax2.margins(x=0.03)

    fig.tight_layout()
    out = base / "figures" / "prob02_ablation_bcap_paper.png"
    fig.savefig(out, dpi=180, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)

    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    print("written:", out.relative_to(root))
    print("axis limits: ax1=%s  ax2=%s" % (ax1.get_ylim(), ax2.get_ylim()))
    print("source :", src.relative_to(root), "sha256:", digest[:16], "…")
    print("baseline C0 = %.6f 元（B 不受限）" % c0)
    for i, v in enumerate(b):
        print("  B=%10.2f kW  Σq_em=%14.6f kWh  C=%18.6f 元  ΔC=%+15.6f 元" % (v, q[i], c[i], gain[i]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
