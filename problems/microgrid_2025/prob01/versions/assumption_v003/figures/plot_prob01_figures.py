"""prob01 正式图表生成脚本（assumption_v003 / formulation_v001 / task 1300a936c4d95653f9d1 / run002）。

- 只读消费 accepted 版本的正式计算结果（solution.json / tables.json / run_manifest.json），不改数据。
- 统一从 config/visualization.yaml 读取字体、色板、尺寸、DPI 与质检阈值。
- 每图使用 automm.visualization.stable_figure_id 生成稳定 ID，文件名不依赖易变图号。
- 自动质检 inspect_png 写 *.quality.json；manifest 登记到 problems/microgrid_2025/figures.yaml。
- 视觉复核状态由 Agent 通过 record_figure_review 命令写入（本脚本先登记为 pending）。

运行（项目根目录）：
    .venv\\Scripts\\python.exe problems/microgrid_2025/prob01/versions/assumption_v003/figures/plot_prob01_figures.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager

FIG_DIR = Path(__file__).resolve().parent
ROOT = FIG_DIR.parents[5]
sys.path.insert(0, str(ROOT / "scripts"))

from automm.common import config_section, hash_path, relative, write_json  # noqa: E402
from automm.visualization import inspect_png, register_figure, stable_figure_id  # noqa: E402

PROBLEM_ID = "microgrid_2025"
QUESTION_ID = "prob01"
ASSUMPTION_VERSION = "assumption_v003"
FORMULATION_VERSION = "formulation_v001"
TASK_ID = "1300a936c4d95653f9d1"

RESULT_DIR = FIG_DIR.parent / "results" / "prob01_v003_f001_run002"
SOLUTION_PATH = RESULT_DIR / "solution.json"
TABLES_PATH = RESULT_DIR / "tables.json"
RUN_MANIFEST_PATH = RESULT_DIR / "run_manifest.json"

SEGMENTS = 144
DT_H = 1.0 / 6.0

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

X_LABEL = "时段序号 i（第 i 段 = 附件 1 第 i 行；区间 [10(i−1), 10i) min）"


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


def load_results() -> tuple[dict, dict, dict]:
    solution = json.loads(SOLUTION_PATH.read_text(encoding="utf-8"))
    tables = json.loads(TABLES_PATH.read_text(encoding="utf-8"))
    run_manifest = json.loads(RUN_MANIFEST_PATH.read_text(encoding="utf-8"))
    for key, series in solution["series"].items():
        if isinstance(series, list) and len(series) == SEGMENTS and key != "time_label":
            solution["series"][key] = np.asarray(series, dtype=float)
    return solution, tables, run_manifest


def tick_positions() -> tuple[list[int], list[str]]:
    labels = [str(item) for item in SOLUTION_SERIES["time_label"]]
    positions = list(range(12, SEGMENTS + 1, 12))
    return positions, [labels[pos - 1] for pos in positions]


def finish_axes(ax: plt.Axes, *, show_xlabel: bool) -> None:
    positions, labels = TICK_POSITIONS
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=0)
    ax.set_xlim(0.5, SEGMENTS + 0.5)
    if show_xlabel:
        ax.set_xlabel(X_LABEL)


def emit(
    fig: plt.Figure,
    *,
    kind: str,
    title: str,
    x: str,
    y: list[str],
    caption: str,
    source_hash: str,
    source_data: str,
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
        "included_in_paper": False,
        "quality_report": relative(output.with_suffix(".quality.json")),
        "quality_status": quality["status"],
        "visual_review": {"status": "pending", "reason": ""},
    }
    register_figure(PROBLEM_ID, item)
    return item


# ---------------------------------------------------------------- 图 1：输入曲线
def figure_input_profile(source_hash: str, source_data: str) -> dict:
    series = SOLUTION_SERIES
    idx = series["period_index"]
    load_kw = series["load_energy_kwh"] / DT_H
    pv_kw = series["pv_energy_kwh"] / DT_H
    price = series["price_yuan_per_kwh"]

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(FIG_W, FIG_H + 2.2), sharex=True, gridspec_kw={"height_ratios": [3, 2]},
        layout="constrained",
    )
    ax1.plot(idx, load_kw, color=PRIMARY, lw=2.0, label="负载功率 $L_t$")
    ax1.plot(idx, pv_kw, color=SECONDARY, lw=2.0, label="光伏预测功率 $PV_t$")
    ax1.set_ylabel("功率 (kW)")
    ax1.legend(frameon=False, loc="upper left", ncol=2)
    ax1.set_title("prob01 代表性单日输入：负载、光伏与电价（附件 1，144 时段）")

    ax2.fill_between(idx, price, color=ACCENT, alpha=0.25)
    ax2.plot(idx, price, color=ACCENT, lw=2.0)
    ax2.set_ylabel("电价 (元/kWh)")
    ax2.annotate(
        f"电价区间 [{price.min():.4f}, {price.max():.4f}] 元/kWh",
        xy=(0.01, 0.96),
        xycoords="axes fraction",
        ha="left",
        va="top",
        fontsize=9,
        color=NEUTRAL,
    )
    finish_axes(ax2, show_xlabel=True)
    return emit(
        fig,
        kind="input_profile",
        title="prob01 代表性单日输入：负载、光伏与电价（附件 1，144 时段）",
        x="period_index",
        y=["load_power_kw", "pv_power_kw", "price_yuan_per_kwh"],
        caption=(
            "上：附件 1 的负载功率 L_t 与光伏预测功率 PV_t（kW）；下：电价 p_t（元/kWh）。"
            "X 轴为位置口径（AS01 左端点：第 i 段 = [10(i−1), 10i) min，刻度为附件时间戳）；"
            "计划窗按模板为 0:10→24:10，相对自然日整体前移 10 分钟。"
            "数据来源：assumption_v003 / formulation_v001 / task 1300a936c4d95653f9d1 / run002。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ------------------------------------------------- 图 2：净负荷与套利窗口
def figure_netload_arbitrage(source_hash: str, source_data: str) -> dict:
    series = SOLUTION_SERIES
    idx = series["period_index"]
    net = series["load_energy_kwh"] - series["pv_energy_kwh"]
    price = series["price_yuan_per_kwh"]
    charge = series["charge_kwh"]
    discharge = series["discharge_kwh"]
    surplus = net < 0
    q25, q75 = np.quantile(price, [0.25, 0.75])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(FIG_W, FIG_H + 2.0), sharex=True, layout="constrained")
    ax1.fill_between(idx, net, 0, where=net >= 0, color=PRIMARY, alpha=0.35, label="净负荷 ≥ 0（需购电）")
    ax1.fill_between(idx, net, 0, where=net < 0, color=SECONDARY, alpha=0.55, label="净负荷 < 0（光伏盈余）")
    ax1.plot(idx, net, color=NEUTRAL, lw=1.2)
    ax1.axhline(0, color="black", lw=0.8)
    ax1.set_ylabel("净负荷电量 (kWh/10min)")
    ax1.legend(frameon=False, loc="upper left", ncol=2)
    ax1.set_title("净负荷与电价分位：光伏盈余窗口与储能充放电价位")
    ax1.annotate(
        f"盈余时段 {int(surplus.sum())}/{SEGMENTS} 个（PV > L）",
        xy=(0.01, 0.30),
        xycoords="axes fraction",
        ha="left",
        va="top",
        fontsize=9,
        color=NEUTRAL,
    )

    ax2.plot(idx, price, color=ACCENT, lw=2.0, label="电价 $p_t$")
    ax2.axhline(q25, color=NEUTRAL, ls="--", lw=1.1, label=f"电价 25% 分位 {q25:.4f}")
    ax2.axhline(q75, color=WARNING, ls="--", lw=1.1, label=f"电价 75% 分位 {q75:.4f}")
    ax2.scatter(idx[charge > 1e-6], price[charge > 1e-6], marker="^", s=26, color=SECONDARY,
                label=f"充电时段 ({int((charge > 1e-6).sum())})", zorder=5)
    ax2.scatter(idx[discharge > 1e-6], price[discharge > 1e-6], marker="v", s=26, color=WARNING,
                label=f"放电时段 ({int((discharge > 1e-6).sum())})", zorder=5)
    ax2.set_ylabel("电价 (元/kWh)")
    ax2.legend(bbox_to_anchor=(0.5, -0.40), loc="upper center", ncol=3, frameon=False, fontsize=9)
    finish_axes(ax2, show_xlabel=True)
    return emit(
        fig,
        kind="netload_arbitrage",
        title="净负荷与电价分位：光伏盈余窗口与储能充放电价位",
        x="period_index",
        y=["net_load_kwh", "price_yuan_per_kwh", "charge_kwh", "discharge_kwh"],
        caption=(
            "上：净负荷电量 (L_t−PV_t)·Δt（kWh/10min），绿色为光伏盈余时段；下：电价与 25%/75% 分位线，"
            "三角标记充电（▲）与放电（▼）发生的时段。用于说明储能在低价时段充电、高价时段放电的套利动机。"
            "X 轴为 AS01 左端点位置口径（计划窗 0:10→24:10）。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ------------------------------------------------- 图 3：最优计划调度
def figure_dispatch_profile(source_hash: str, source_data: str) -> dict:
    series = SOLUTION_SERIES
    idx = series["period_index"]
    purchase = series["purchase_kwh"]
    charge = series["charge_kwh"]
    discharge = series["discharge_kwh"]
    cost = float(series.get("__objective__", 0.0))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(FIG_W, FIG_H + 2.0), sharex=True, layout="constrained")
    ax1.fill_between(idx, purchase, color=PRIMARY, alpha=0.35)
    ax1.plot(idx, purchase, color=PRIMARY, lw=1.6)
    ax1.set_ylabel("计划购电量 $b_t$\n(kWh/10min)")
    ax1.set_title(
        f"最优计划：购电量与充放电安排（$\\Sigma b_t$ = {purchase.sum():,.2f} kWh，$C^*$ = {cost:,.2f} 元）"
    )
    ax1.annotate(
        f"购电峰值 {purchase.max():.2f} kWh/10min（第 {purchase.argmax() + 1} 段）",
        xy=(0.42, 0.95),
        xycoords="axes fraction",
        ha="left",
        va="top",
        fontsize=9,
        color=NEUTRAL,
    )

    ax2.bar(idx, charge, width=0.9, color=SECONDARY, label="充电 $c_t$（向上）")
    ax2.bar(idx, -discharge, width=0.9, color=ACCENT, label="放电 $q_{dis,t}$（向下）")
    ax2.axhline(0, color="black", lw=0.8)
    ax2.set_ylabel("充/放电量 (kWh/10min)")
    ax2.legend(frameon=False, loc="lower left", ncol=1, fontsize=9)
    finish_axes(ax2, show_xlabel=True)
    return emit(
        fig,
        kind="dispatch_profile",
        title="最优计划：购电量与充放电安排",
        x="period_index",
        y=["purchase_kwh", "charge_kwh", "discharge_kwh"],
        caption=(
            "上：最优计划购电量 b_t（kWh/10min，面积）；下：充电 c_t（向上，绿）与放电 q_dis_t（向下，橙）。"
            "充电集中在凌晨低价时段、放电集中在午间与晚间高价时段；全程无同时充放电（AS07，互补残差 = 0）。"
            "单位与量纲按 AS03a/D9：Σ p_t·b_t 直接为元，不乘 Δt。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ------------------------------------------------- 图 4：储电量轨迹
def figure_soc_trajectory(source_hash: str, source_data: str) -> dict:
    series = SOLUTION_SERIES
    idx = series["period_index"]
    storage = series["storage_kwh"]

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), layout="constrained")
    ax.plot(idx, storage, color=PRIMARY, lw=2.2, label="时段末储电量 $E_t$")
    ax.axhline(10800, color=NEUTRAL, ls="--", lw=1.2, label="运行上界 $E_{max}$ = 10800 kWh")
    ax.axhline(1200, color=WARNING, ls="--", lw=1.2, label="运行下界 $E_{min}$ = 1200 kWh")
    ax.axhline(6000, color=SECONDARY, ls=":", lw=1.4, label="窗首/窗末 $E_0=E_{144}$ = 6000 kWh")
    ax.scatter([1, SEGMENTS], [6000.0, storage[-1]], color=ACCENT, zorder=5, s=45)
    ax.annotate(
        "$E_0$ = 6000.0 kWh（给定初值）",
        xy=(1, 6000.0),
        xytext=(16, -30),
        textcoords="offset points",
        arrowprops={"arrowstyle": "->", "color": ACCENT, "lw": 1.1},
        fontsize=9,
        color=ACCENT,
    )
    ax.annotate(
        f"$E_{{144}}$ = {storage[-1]:.1f} kWh",
        xy=(SEGMENTS, storage[-1]),
        xytext=(-18, 20),
        textcoords="offset points",
        ha="right",
        arrowprops={"arrowstyle": "->", "color": ACCENT, "lw": 1.1},
        fontsize=9,
        color=ACCENT,
    )
    ax.set_ylim(600, 11800)
    ax.set_ylabel("储电量 $E_t$ (kWh)")
    ax.set_title("储电量轨迹与运行区间：区间内运行且日周期闭合")
    ax.legend(frameon=False, loc="lower left", fontsize=9)
    ax.annotate(
        f"实测 $E_t \\in$ [{storage.min():.1f}, {storage.max():.1f}] kWh；"
        f"$|E_{{144}}-E_0|$ = {abs(storage[-1] - 6000.0):.1e} kWh",
        xy=(0.99, 0.95),
        xycoords="axes fraction",
        ha="right",
        va="top",
        fontsize=9,
        color=NEUTRAL,
    )
    finish_axes(ax, show_xlabel=True)
    return emit(
        fig,
        kind="soc_trajectory",
        title="储电量轨迹与运行区间：区间内运行且日周期闭合",
        x="period_index",
        y=["storage_kwh"],
        caption=(
            "最优解的时段末储电量 E_t（kWh）轨迹：先充电至接近 9750/10800 kWh，再在高峰时段放电至 1200 kWh 附近，"
            "末段回升至 6000 kWh 使日周期闭合（E_144 = E_0 = 6000，AS10/AS11）。"
            "虚线为运行上下界 E_min = 1200、E_max = 10800 kWh（AS06）；"
            "0:00/24:00 为计划窗首/末状态（AS01 左端点口径，计划窗 0:10→24:10）。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ------------------------------------------------- 图 5：逐时段供需构成
def figure_energy_balance(source_hash: str, source_data: str) -> dict:
    series = SOLUTION_SERIES
    idx = series["period_index"]
    purchase = series["purchase_kwh"]
    pv_used = series["pv_energy_kwh"] - series["spill_kwh"]
    discharge = series["discharge_kwh"]
    demand = series["load_energy_kwh"] + series["charge_kwh"]

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), layout="constrained")
    ax.stackplot(
        idx,
        purchase,
        pv_used,
        discharge,
        colors=[PRIMARY, SECONDARY, ACCENT],
        alpha=0.82,
        labels=["外网购电 $b_t$", "光伏消纳 $PV_t\\Delta t - s_t$", "储能放电 $q_{dis,t}$"],
    )
    ax.plot(idx, demand, color="black", lw=1.8, ls="--", label="需求 = 负载 $L_t\\Delta t$ + 充电 $c_t$")
    ax.set_ylabel("电量 (kWh/10min)")
    ax.set_title("逐时段供需构成：供给来源堆叠与需求总量完全重合")
    ax.legend(frameon=False, loc="upper left", ncol=2, fontsize=9)
    ax.annotate(
        f"残差 $\\Sigma|$供给−需求$|$ = {np.abs(purchase + pv_used + discharge - demand).sum():.2e} kWh；"
        f"弃光 $\\Sigma s_t$ = {series['spill_kwh'].sum():.1f} kWh",
        xy=(0.99, 0.95),
        xycoords="axes fraction",
        ha="right",
        va="top",
        fontsize=9,
        color=NEUTRAL,
    )
    finish_axes(ax, show_xlabel=True)
    return emit(
        fig,
        kind="energy_balance",
        title="逐时段供需构成：供给来源堆叠与需求总量完全重合",
        x="period_index",
        y=["purchase_kwh", "pv_used_kwh", "discharge_kwh", "demand_kwh"],
        caption=(
            "堆叠面积为供给侧三项之和（购电 b_t、光伏实际消纳 PV_tΔt−s_t、储能放电 q_dis_t），"
            "黑色虚线为需求侧（负载 L_tΔt + 充电 c_t）；两者逐时段重合验证电量平衡 (R1) 闭合（残差 ~1e-13）。"
            "最优解弃光 Σs_t = 0（光伏盈余全部被储能吸收），故光伏消纳等于 PV_tΔt。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ------------------------------------------------- 图 6：三维调度轨迹
def figure_price_action_3d(source_hash: str, source_data: str) -> dict:
    series = SOLUTION_SERIES
    idx = series["period_index"].astype(float)
    price = series["price_yuan_per_kwh"]
    net = series["discharge_kwh"] - series["charge_kwh"]

    fig = plt.figure(figsize=(FIG_W, FIG_H + 1.6))
    ax = fig.add_subplot(111, projection="3d")
    points = ax.scatter(idx, price, net, c=net, cmap="coolwarm", s=18, depthshade=False)
    order = np.argsort(idx)
    ax.plot(idx[order], price[order], net[order], color=NEUTRAL, lw=0.9, alpha=0.6)
    ax.set_xlabel("时段序号 i", labelpad=8)
    ax.set_ylabel("电价 (元/kWh)", labelpad=8)
    ax.set_zlabel("净放电 $q_{dis,t}-c_t$ (kWh)", labelpad=6)
    ax.set_title("调度轨迹三维视图：时段 × 电价 × 净放电")
    ax.view_init(elev=20, azim=-62)
    fig.colorbar(points, ax=ax, shrink=0.62, pad=0.09, label="净放电 (kWh/10min)")
    ax.annotate(
        ">$0$ 放电 / $<0$ 充电",
        xy=(0.02, 0.95),
        xycoords="axes fraction",
        fontsize=9,
        color=NEUTRAL,
    )
    fig.tight_layout()
    return emit(
        fig,
        kind="price_action_3d",
        title="调度轨迹三维视图：时段 × 电价 × 净放电",
        x="period_index",
        y=["price_yuan_per_kwh", "net_discharge_kwh"],
        caption=(
            "三维散点+连线：X = 时段序号 i，Y = 电价 p_t（元/kWh），Z = 净放电 q_dis_t − c_t（kWh/10min，"
            "正值放电、负值充电），颜色对应净放电量。视角 elev=20°、azim=−62°，用于展示调度在"
            "「时间—价格—动作」三维空间中的轨迹结构；投影歧义由配套二维图 price_action_2d 消除。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ------------------------------------------------- 图 7：三维配套二维投影
def figure_price_action_2d(source_hash: str, source_data: str) -> dict:
    series = SOLUTION_SERIES
    idx = series["period_index"]
    price = series["price_yuan_per_kwh"]
    net = series["discharge_kwh"] - series["charge_kwh"]
    hours = (idx - 1) * DT_H + DT_H / 2.0

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), layout="constrained")
    sc = ax.scatter(price, net, c=hours, cmap="viridis", s=34, alpha=0.9, edgecolors="none")
    ax.axhline(0, color="black", lw=1.0)
    ax.set_xlabel("电价 $p_t$ (元/kWh)")
    ax.set_ylabel("净放电 $q_{dis,t}-c_t$ (kWh/10min)")
    ax.set_title("三维轨迹的二维投影：电价—净放电关系（颜色 = 时段）")
    bar = fig.colorbar(sc, ax=ax, pad=0.02)
    bar.set_label("时段 (h)")
    ax.annotate(
        "低电价区 → 净放电 < 0（充电）",
        xy=(0.02, 0.08),
        xycoords="axes fraction",
        fontsize=9,
        color=SECONDARY,
    )
    ax.annotate(
        "高电价区 → 净放电 > 0（放电）",
        xy=(0.98, 0.92),
        xycoords="axes fraction",
        ha="right",
        fontsize=9,
        color=WARNING,
    )
    return emit(
        fig,
        kind="price_action_2d",
        title="三维轨迹的二维投影：电价—净放电关系",
        x="price_yuan_per_kwh",
        y=["net_discharge_kwh"],
        caption=(
            "price_action_3d 的配套二维投影：横轴电价 p_t（元/kWh），纵轴净放电 q_dis_t − c_t（kWh/10min），"
            "颜色为时段（h，按 0:10→24:10 计划窗的中值）。左下方（低电价）集中充电、右上方（高电价）集中放电，"
            "与前两分位套利结构一致；配套图消除三维视角下的遮挡与深度辨识歧义。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ------------------------------------------------- 图 8：表 2 汇总
def figure_block_summary(source_hash: str, source_data: str, tables: dict) -> dict:
    table2 = tables["table2"]
    blocks = np.arange(1, 7)
    charge = np.asarray(table2["block_charge_kwh"], dtype=float)
    discharge = np.asarray(table2["block_discharge_kwh"], dtype=float)
    width = 0.38

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), layout="constrained")
    bars_c = ax.bar(blocks - width / 2, charge, width, color=SECONDARY, label="充电量 $\\Sigma c_t$")
    bars_d = ax.bar(blocks + width / 2, discharge, width, color=ACCENT, label="放电量 $\\Sigma q_{dis,t}$")
    for bars in (bars_c, bars_d):
        for rect in bars:
            height = rect.get_height()
            ax.annotate(
                f"{height:,.1f}",
                xy=(rect.get_x() + rect.get_width() / 2, height),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8.5,
            )
    ax.set_xticks(blocks)
    ax.set_xticklabels([f"块 {k}\n行 {24 * (k - 1) + 1}–{24 * k}" for k in blocks])
    ax.set_xlabel("表 2 的 4 小时块（按 result1 模板行位置聚合，AS13/D8）")
    ax.set_ylabel("电量 (kWh)")
    ax.set_title("表 2 汇总：6 个 4 小时块充放电量与计划窗端点储电量")
    ax.legend(frameon=False, loc="upper right")
    ax.set_ylim(0, max(charge.max(), discharge.max()) * 1.22)
    ax.annotate(
        f"0:00 储电量 = {table2['storage_0_00_kwh']:.1f} kWh；"
        f"24:00 储电量 = {table2['storage_24_00_kwh']:.1f} kWh\n"
        "（计划窗首/末状态，AS01 左端点口径；充放电量分别列示不冲抵）",
        xy=(0.01, 0.99),
        xycoords="axes fraction",
        ha="left",
        va="top",
        fontsize=9,
        color=NEUTRAL,
        bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": NEUTRAL, "alpha": 0.92},
    )
    return emit(
        fig,
        kind="block_summary",
        title="表 2 汇总：6 个 4 小时块充放电量与计划窗端点储电量",
        x="block_index",
        y=["block_charge_kwh", "block_discharge_kwh", "storage_0_00_kwh", "storage_24_00_kwh"],
        caption=(
            "表 2 六个 4 小时块的充电量（绿）与放电量（橙）分别列示、不冲抵（AS13/D8）；块 k 对应 result1 行 "
            "24(k−1)+1…24k。计划窗首/末储电量均为 6000.0 kWh（E_0 = E_144，AS10/AS11；按 AS01 左端点口径，"
            "0:00/24:00 为计划窗首/末状态，计划窗为 0:10→24:10）。数值取自 tables.json（来源 solution.json 序列）。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ------------------------------------------------- 图 9：费用量级检验
def figure_cost_bounds(source_hash: str, source_data: str, solution: dict) -> dict:
    checks = {item["name"]: item for item in solution["checks"]}
    lower = float(checks["analytic_lower_bound"]["value"])
    upper = float(checks["analytic_upper_bound"]["value"])
    optimum = float(solution["objective_yuan"])
    share = (optimum - lower) / (upper - lower)

    labels = ["解析下界\n$p_{min}\\Sigma N$", "最优解\n$C^*$", "无储能可行上界\n（构造解）"]
    values = [lower, optimum, upper]
    colors = [NEUTRAL, PRIMARY, NEUTRAL]

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), layout="constrained")
    ax.axvspan(lower, upper, color=PRIMARY, alpha=0.08, zorder=0)
    bars = ax.barh(labels, values, color=colors, height=0.5, zorder=3)
    for rect, value in zip(bars, values):
        ax.annotate(
            f"{value:,.2f} 元",
            xy=(value, rect.get_y() + rect.get_height() / 2),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=10,
        )
    ax.axvline(optimum, color=ACCENT, ls="--", lw=1.4, zorder=4)
    ax.set_xlim(0, upper * 1.12)
    ax.set_xlabel("全天购电费 $C_{plan}=\\Sigma p_t b_t$ (元)")
    ax.set_title("费用量级检验：最优解落在解析可行区间内（$10^4$ 元量级）")
    ax.annotate(
        f"区间宽度 {upper - lower:,.2f} 元；$C^*$ 位于区间 {share * 100:.1f}% 处",
        xy=(0.99, 0.12),
        xycoords="axes fraction",
        ha="right",
        fontsize=9,
        color=NEUTRAL,
    )
    ax.grid(axis="y", visible=False)
    return emit(
        fig,
        kind="cost_bounds",
        title="费用量级检验：最优解落在解析可行区间内",
        x="cost_case",
        y=["cost_yuan"],
        caption=(
            "最优全天购电费 C* = 35126.95 元（蓝）落在解析下界 20622.73 元（p_min·N）与无储能构造可行解上界 "
            "48052.05 元之间，量级为 10⁴ 元，符合 D9 量纲口径（若误乘 Δt 会落入 10³ 元量级即硬错误）。"
            "数值取自 solution.json 的 checks（analytic_lower_bound / analytic_upper_bound / objective_yuan）。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


def main() -> int:
    global SOLUTION_SERIES, TICK_POSITIONS
    solution, tables, run_manifest = load_results()
    SOLUTION_SERIES = solution["series"]
    SOLUTION_SERIES["__objective__"] = float(solution["objective_yuan"])
    TICK_POSITIONS = tick_positions()

    solution_hash = hash_path(SOLUTION_PATH)
    tables_hash = hash_path(TABLES_PATH)
    combined_hash = hashlib.sha256(f"{solution_hash}{tables_hash}".encode("utf-8")).hexdigest()
    solution_rel = relative(SOLUTION_PATH)
    tables_rel = relative(TABLES_PATH)

    items = [
        figure_input_profile(solution_hash, solution_rel),
        figure_netload_arbitrage(solution_hash, solution_rel),
        figure_dispatch_profile(solution_hash, solution_rel),
        figure_soc_trajectory(solution_hash, solution_rel),
        figure_energy_balance(solution_hash, solution_rel),
        figure_price_action_3d(solution_hash, solution_rel),
        figure_price_action_2d(solution_hash, solution_rel),
        figure_block_summary(combined_hash, f"{solution_rel} + {tables_rel}", tables),
        figure_cost_bounds(solution_hash, solution_rel, solution),
    ]

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "problem_id": PROBLEM_ID,
        "question_id": QUESTION_ID,
        "assumption_version": ASSUMPTION_VERSION,
        "formulation_version": FORMULATION_VERSION,
        "task_id": TASK_ID,
        "run": str(RESULT_DIR),
        "font": FONT,
        "dpi": DPI,
        "source_solution_hash": solution_hash,
        "source_tables_hash": tables_hash,
        "figure_count": len(items),
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
    }
    write_json(FIG_DIR / "generation_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
