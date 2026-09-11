"""prob02 正式图表生成脚本（assumption_v001 / formulation_v001 / task dc8afc3deb5477641b99 / run002）。

- 只读消费 accepted 版本的正式计算结果（solution.json / tables.json / run_manifest.json），不改数据。
- 统一从 config/visualization.yaml 读取字体、色板、尺寸、DPI 与质检阈值。
- 每图使用 automm.visualization.stable_figure_id 生成稳定 ID，文件名不依赖易变图号。
- 自动质检 inspect_png 写 *.quality.json；manifest 登记到 problems/microgrid_2025/figures.yaml。
- 视觉复核状态由 Agent 通过 record_figure_review 命令写入（本脚本先登记为 pending）。

运行（项目根目录）：
    .venv\\Scripts\\python.exe problems/microgrid_2025/prob02/versions/assumption_v001/figures/plot_prob02_figures.py
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
from matplotlib.colors import LogNorm, TwoSlopeNorm

FIG_DIR = Path(__file__).resolve().parent
ROOT = FIG_DIR.parents[5]
sys.path.insert(0, str(ROOT / "scripts"))

from automm.common import config_section, hash_path, relative, write_json  # noqa: E402
from automm.visualization import inspect_png, register_figure, stable_figure_id  # noqa: E402

PROBLEM_ID = "microgrid_2025"
QUESTION_ID = "prob02"
ASSUMPTION_VERSION = "assumption_v001"
FORMULATION_VERSION = "formulation_v001"
TASK_ID = "dc8afc3deb5477641b99"

RESULT_DIR = FIG_DIR.parent / "results" / "prob02_v001_f001_run002"
SOLUTION_PATH = RESULT_DIR / "solution.json"
TABLES_PATH = RESULT_DIR / "tables.json"
RUN_MANIFEST_PATH = RESULT_DIR / "run_manifest.json"

DAYS = 365
SEGMENTS_PER_DAY = 144
TOTAL = DAYS * SEGMENTS_PER_DAY
DT_H = 1.0 / 6.0
ETA_CH = 0.9
ETA_DIS = 0.9
ETA_ROUND_TRIP = ETA_CH * ETA_DIS
DELIVERY_START_DAY = 31  # 2025-02-01（0 基日索引）
SPEC_DAYS = {"2025-03-20": 78, "2025-06-21": 171, "2025-09-23": 265, "2025-12-21": 354}
DAY0 = date(2025, 1, 1)
MONTH_TICKS = [(date(2025, m, 1) - DAY0).days for m in range(1, 13)]
MONTH_LABELS = [f"{m} 月" for m in range(1, 13)]
CLOCK_POS = [1 + 6 * h for h in range(0, 25, 4)]
CLOCK_LABELS = ["0:00", "4:00", "8:00", "12:00", "16:00", "20:00", "24:00"]

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
def load_results() -> tuple[dict, dict, dict]:
    solution = json.loads(SOLUTION_PATH.read_text(encoding="utf-8"))
    tables = json.loads(TABLES_PATH.read_text(encoding="utf-8"))
    run_manifest = json.loads(RUN_MANIFEST_PATH.read_text(encoding="utf-8"))
    series = {}
    for key, values in solution["series"].items():
        if isinstance(values, list) and len(values) == TOTAL:
            series[key] = np.asarray(values, dtype=float)
    solution["series"] = series
    return solution, tables, run_manifest


DATA: dict = {}


def day_slice(day: int) -> np.ndarray:
    return np.s_[day * SEGMENTS_PER_DAY : (day + 1) * SEGMENTS_PER_DAY]


def month_of(day: int) -> int:
    return (DAY0 + timedelta(days=int(day))).month


def mark_months(ax: plt.Axes, *, offset: float = 0.0) -> None:
    for pos in MONTH_TICKS[1:]:
        ax.axvline(pos, color=NEUTRAL, lw=0.7, ls=":", alpha=0.55)
    ax.set_xticks(MONTH_TICKS)
    ax.set_xticklabels(MONTH_LABELS)
    ax.set_xlim(0 + offset, DAYS - 1 + offset)


def finish_xlabel_days(ax: plt.Axes) -> None:
    ax.set_xlabel("日期（2025-01-01 → 2025-12-31；竖虚线为月初；交付期自 2025-02-01 起）")


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


# ---------------------------------------------------------------- 派生量
def derive() -> None:
    solution = DATA["solution"]
    series = solution["series"]
    daily = solution["daily"]

    day_index = np.asarray(daily["day_index"], dtype=float)
    pv_e = series["pv_energy_kwh"]
    price = series["price_yuan_per_kwh"]
    purchase = series["purchase_kwh"]
    charge = series["charge_kwh"]
    discharge = series["discharge_kwh"]
    spill = series["spill_kwh"]
    load = series["load_energy_kwh"]
    storage = series["storage_kwh"]

    DATA["price"] = price
    DATA["purchase"] = purchase
    DATA["charge"] = charge
    DATA["discharge"] = discharge
    DATA["spill"] = spill
    DATA["load"] = load
    DATA["storage"] = storage
    DATA["pv_energy"] = pv_e
    DATA["net_discharge"] = discharge - charge
    DATA["day_index"] = day_index

    DATA["daily_purchase"] = np.asarray(daily["purchase_kwh"], dtype=float)
    DATA["daily_charge"] = np.asarray(daily["charge_kwh"], dtype=float)
    DATA["daily_discharge"] = np.asarray(daily["discharge_kwh"], dtype=float)
    DATA["daily_spill"] = np.asarray(daily["spill_kwh"], dtype=float)
    DATA["daily_cost"] = np.asarray(daily["cost_total_yuan"], dtype=float)
    DATA["daily_em"] = np.asarray(daily["q_em_kwh"], dtype=float)
    DATA["state_start"] = np.asarray(daily["state_start_kwh"], dtype=float)
    DATA["state_end"] = np.asarray(daily["state_end_kwh"], dtype=float)

    DATA["daily_load"] = load.reshape(DAYS, SEGMENTS_PER_DAY).sum(axis=1)
    DATA["daily_pv"] = pv_e.reshape(DAYS, SEGMENTS_PER_DAY).sum(axis=1)
    DATA["daily_netload"] = DATA["daily_load"] - DATA["daily_pv"]
    DATA["daily_wavg_price"] = (
        (price * purchase).reshape(DAYS, SEGMENTS_PER_DAY).sum(axis=1) / DATA["daily_purchase"]
    )
    DATA["gap"] = DATA["state_end"] - DATA["state_start"]
    DATA["month"] = np.asarray([month_of(day) for day in day_index], dtype=int)

    # 热力图矩阵：行=日，列=时段
    DATA["heat_purchase"] = purchase.reshape(DAYS, SEGMENTS_PER_DAY) / DT_H
    DATA["heat_storage"] = storage.reshape(DAYS, SEGMENTS_PER_DAY)
    DATA["heat_price"] = price.reshape(DAYS, SEGMENTS_PER_DAY)

    # 电价—净放电二维密度
    p_bins = np.linspace(price.min(), price.max(), 60)
    a_bins = np.linspace(DATA["net_discharge"].min(), DATA["net_discharge"].max(), 60)
    hist, _, _ = np.histogram2d(price, DATA["net_discharge"], bins=[p_bins, a_bins])
    DATA["pa_hist"] = (hist, p_bins, a_bins)

    # 月度汇总
    months = np.unique(DATA["month"])
    DATA["months"] = months
    DATA["month_purchase"] = np.asarray([DATA["daily_purchase"][DATA["month"] == m].sum() for m in months])
    DATA["month_pv"] = np.asarray([DATA["daily_pv"][DATA["month"] == m].sum() for m in months])
    DATA["month_discharge"] = np.asarray([DATA["daily_discharge"][DATA["month"] == m].sum() for m in months])
    DATA["month_load"] = np.asarray([DATA["daily_load"][DATA["month"] == m].sum() for m in months])
    DATA["month_spill"] = np.asarray([DATA["daily_spill"][DATA["month"] == m].sum() for m in months])
    DATA["month_charge"] = np.asarray([DATA["daily_charge"][DATA["month"] == m].sum() for m in months])
    DATA["month_discharge_sum"] = np.asarray([DATA["daily_discharge"][DATA["month"] == m].sum() for m in months])
    DATA["month_cost"] = np.asarray([DATA["daily_cost"][DATA["month"] == m].sum() for m in months])

    # 月度闭合残差（复述 (I2) 的月度切片，仅用于图注）
    #   注意：窗口前的状态须取该月第一个时段**之前**的 E（即上一时段末），
    #   不能用窗口内首点的 E，否则会引入 0.9·(E_before − E_first) 的边界误差。
    month_residual = np.zeros(len(months))
    for k, m in enumerate(months):
        rows = np.where(DATA["month"] == m)[0]
        p0 = int(rows[0]) * SEGMENTS_PER_DAY
        p1 = (int(rows[-1]) + 1) * SEGMENTS_PER_DAY  # 独占上界
        sl = np.s_[p0:p1]
        e_before = DATA["solution"]["totals"]["storage_initial_kwh"] if p0 == 0 else float(storage[p0 - 1])
        lhs = DATA["purchase"][sl].sum()
        rhs = (
            (DATA["load"][sl] - pv_e[sl]).sum()
            + DATA["spill"][sl].sum()
            + (1.0 - ETA_ROUND_TRIP) * DATA["charge"][sl].sum()
            + ETA_DIS * (float(storage[p1 - 1]) - e_before)
        )
        month_residual[k] = abs(lhs - rhs)
    DATA["month_residual"] = month_residual

    # 3D 降采样（每 12 个时段取 1 点 → 4,380 点，兼顾覆盖与静态可读性）
    sub = np.arange(0, TOTAL, 12)
    DATA["sub_idx"] = sub
    DATA["sub_day"] = sub // SEGMENTS_PER_DAY
    DATA["sub_tod"] = (sub % SEGMENTS_PER_DAY + 0.5) * DT_H
    DATA["sub_net"] = DATA["net_discharge"][sub]
    DATA["sub_price"] = price[sub]

    # 恒等式闭合量（用于图注/注记，仅复述 solution 已登记的检查项）
    totals = solution["totals"]
    DATA["identity_i2_term"] = (
        totals["net_load_kwh"]
        + totals["total_spill_kwh"]
        + 0.1 * totals["total_charge_kwh"]
        - 0.9 * (totals["storage_initial_kwh"] - totals["storage_final_kwh"])
    )


# ---------------------------------------------------------------- 图 1：全年能量流
def figure_year_energy_flow(source_hash: str, source_data: str) -> dict:
    idx = DATA["day_index"]
    pv = DATA["daily_pv"] / 1000.0
    buy = DATA["daily_purchase"] / 1000.0
    load = DATA["daily_load"] / 1000.0
    net = DATA["daily_netload"] / 1000.0

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(FIG_W, FIG_H + 3.0), sharex=False, gridspec_kw={"height_ratios": [3, 2]},
        layout="constrained",
    )
    ax1.bar(idx, pv, width=0.9, color=SECONDARY, alpha=0.85, label="光伏发电量 $\\Sigma(PV\\Delta t)$")
    ax1.bar(idx, buy, width=0.9, bottom=pv, color=PRIMARY, alpha=0.85, label="计划购电量 $\\Sigma b$")
    ax1.plot(idx, load, color=WARNING, lw=1.8, label="小区负载 $\\Sigma(L\\Delta t)$")
    ax1.plot(idx, net, color="black", lw=1.4, ls="--", label="净负荷 $\\Sigma(L-PV)\\Delta t$")
    ax1.set_ylabel("日电量 (MWh/日)")
    ax1.set_title(
        f"全年（365 天）日能量构成：光伏 + 计划购电 ≥ 负载，净负荷与购电差异来自储能往返\n"
        f"全期 $\\Sigma b$ = {DATA['solution']['totals']['total_purchase_kwh'] / 1000:,.1f} MWh；"
        f"$\\Sigma q_{{em}}$ = 0（紧急购电未激活，定理 T1）"
    )
    ax1.legend(frameon=False, loc="upper left", ncol=2, fontsize=9)
    mark_months(ax1)
    ax1.annotate(
        f"最大日购电量 {buy.max():,.1f} MWh（{date(2025, 1, 1) + timedelta(days=int(idx[buy.argmax()]))}）；"
        f"最小 {buy.min():,.1f} MWh",
        xy=(0.99, 0.62), xycoords="axes fraction", ha="right", va="top", fontsize=9, color=NEUTRAL,
    )

    tod = (np.arange(SEGMENTS_PER_DAY) + 0.5) * DT_H
    day = SPEC_DAYS["2025-06-21"]
    sl = day_slice(day)
    ax2.plot(tod, DATA["load"][sl] / DT_H / 1000.0, color=WARNING, lw=1.8, label="负载功率 $L_t$")
    ax2.plot(tod, DATA["pv_energy"][sl] / DT_H / 1000.0, color=SECONDARY, lw=1.8, label="光伏实际功率 $PV_t$")
    ax2.plot(tod, DATA["purchase"][sl] / DT_H / 1000.0, color=PRIMARY, lw=1.6, ls="--", label="计划购电功率 $b_t/\\Delta t$")
    ax2.set_xlim(0, 24)
    ax2.set_xticks(np.arange(0, 25, 4))
    ax2.set_xticklabels([f"{h}:00" for h in range(0, 25, 4)])
    ax2.set_xlabel("代表日 2025-06-21 时刻（位置口径：第 i 段 = [10(i−1), 10i) min，计划窗 0:10→24:10）")
    ax2.set_ylabel("功率 (MW)")
    ax2.set_title(f"代表日（2025-06-21，日费用 {DATA['daily_cost'][day]:,.0f} 元）日内功率平衡（实际数据，非附件 1 代表日）")
    ax2.legend(frameon=False, loc="upper left", ncol=2, fontsize=9)
    return emit(
        fig,
        kind="year_energy_flow",
        title="prob02 全年日能量构成与代表日功率平衡",
        x="day_index",
        y=["daily_pv_kwh", "daily_purchase_kwh", "daily_load_kwh", "daily_net_load_kwh"],
        caption=(
            "上：365 天逐日电量堆叠（光伏发电量 + 计划购电量）与小区负载、净负荷曲线（单位 MWh/日）；"
            "两者之差即储能净放电与往返损耗。下：交付期内代表日 2025-06-21 的日内功率（MW，实际负载/光伏来自附件 2，"
            "非附件 1 的代表日预测）。X 轴为自然日日期，竖虚线为月初；交付范围 2025-02-01→12-31（334 天），"
            "1 月为预热期。数据来源：assumption_v001 / formulation_v001 / task dc8afc3deb5477641b99 / run002。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ---------------------------------------------------------------- 图 2：日费用与电价
def figure_cost_price_rhythm(source_hash: str, source_data: str) -> dict:
    idx = DATA["day_index"]
    cost = DATA["daily_cost"]
    wavg = DATA["daily_wavg_price"]
    purchase = DATA["daily_purchase"] / 1000.0

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(FIG_W, FIG_H + 2.0), sharex=True, layout="constrained",
    )
    ax1.fill_between(idx, cost, color=PRIMARY, alpha=0.30)
    ax1.plot(idx, cost, color=PRIMARY, lw=1.3, label="日购电费 $C_d$（计划口径）")
    ax1.axhline(cost[DELIVERY_START_DAY:].mean(), color=WARNING, ls="--", lw=1.3,
                label=f"交付期日均 {cost[DELIVERY_START_DAY:].mean():,.0f} 元")
    ax1.set_ylabel("日购电费 (元/日)")
    ax1.set_title(
        f"全年日购电费与购电加权均价：交付期合计 {cost[DELIVERY_START_DAY:].sum():,.0f} 元"
        f"（10⁷ 元量级，AS05/D9 不乘 Δt）"
    )
    ax1.legend(frameon=False, loc="upper left", ncol=2, fontsize=9)
    ax1.annotate(
        f"1 月预热期 {cost[:DELIVERY_START_DAY].sum():,.0f} 元（不计入交付）；"
        f"单日区间 [{cost.min():,.0f}, {cost.max():,.0f}] 元",
        xy=(0.99, 0.60), xycoords="axes fraction", ha="right", va="top", fontsize=9, color=NEUTRAL,
    )

    sc = ax2.scatter(idx, wavg, c=cost, cmap="YlOrRd", s=14, alpha=0.9, edgecolors="none")
    ax2.set_ylabel("购电加权均价 $\\Sigma p b / \\Sigma b$\n(元/kWh)")
    ax2.set_title("日购电加权均价（颜色 = 日费用）：均价越低、日费用越低，全年结构由分时电价与光伏季节共同决定")
    bar = fig.colorbar(sc, ax=ax2, pad=0.015)
    bar.set_label("日购电费 (元)")
    ax2.set_ylim(wavg.min() * 0.97, wavg.max() * 1.03)
    finish_xlabel_days(ax2)
    return emit(
        fig,
        kind="cost_price_rhythm",
        title="全年日购电费与购电加权均价（含 1 月预热期标注）",
        x="day_index",
        y=["daily_cost_yuan", "daily_weighted_avg_price"],
        caption=(
            "上：逐日购电费 C_d = Σ_t p_t·b_t（元/日，不带 Δt，符合 D9 量纲）；红虚线为交付期（2025-02-01 起 334 天）日均值。"
            "下：逐日购电加权均价 Σpb/Σb（元/kWh），颜色表示日费用。1 月（预热期）不计入交付期合计；"
            "全年日均价差异由分时电价（每日重复）与实际光伏出力（季节性）共同造成，非价格曲线变化。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ---------------------------------------------------------------- 图 3：时空热力图
def figure_temporal_heatmap(source_hash: str, source_data: str) -> dict:
    rows = np.arange(DAYS)
    cols = np.arange(SEGMENTS_PER_DAY) / 6.0

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(FIG_W, FIG_H + 3.2), sharex=True, layout="constrained",
    )
    im1 = ax1.pcolormesh(cols, rows, DATA["heat_purchase"], cmap="YlGnBu", shading="auto")
    ax1.set_ylabel("日期（日索引，1 = 2025-01-01）")
    ax1.set_title("全年逐日×时段计划购电功率 $b_{d,t}/\\Delta t$（MW）：分时电价造成的固定日内节律")
    bar1 = fig.colorbar(im1, ax=ax1, pad=0.015)
    bar1.set_label("购电功率 (MW)")
    for label, day in SPEC_DAYS.items():
        ax1.plot(12, day, marker="o", ms=5, mfc="none", mec=WARNING, mew=1.4)
        ax1.annotate(label, xy=(12, day), xytext=(11, 0), textcoords="offset points",
                     fontsize=8, color=WARNING, ha="left", va="center",
                     bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.78})
    ax1.set_yticks(MONTH_TICKS)
    ax1.set_yticklabels(MONTH_LABELS)
    ax1.invert_yaxis()
    ax1.grid(visible=False)

    im2 = ax2.pcolormesh(cols, rows, DATA["heat_storage"], cmap="RdYlBu_r", shading="auto",
                         vmin=1200, vmax=10800)
    ax2.set_ylabel("日期（日索引）")
    ax2.set_title("全年逐日×时段储电量 $E_{d,t}$（kWh）：贴近运行上界运行、年末放空至 $E_{min}$")
    bar2 = fig.colorbar(im2, ax=ax2, pad=0.015)
    bar2.set_label("储电量 (kWh)")
    ax2.set_yticks(MONTH_TICKS)
    ax2.set_yticklabels(MONTH_LABELS)
    ax2.invert_yaxis()
    ax2.grid(visible=False)
    ax2.set_xlim(0, 24)
    ax2.set_xticks(np.arange(0, 25, 4))
    ax2.set_xticklabels([f"{h}:00" for h in range(0, 25, 4)])
    ax2.set_xlabel(
        "时段（位置口径 AS01：第 i 段 = [10(i−1), 10i) min，计划窗 0:10→24:10；行 = 自然日，"
        "故每行首末两列相差 10 分钟相位）"
    )
    im1.set_clim(0, np.percentile(DATA["heat_purchase"], 99.5))
    return emit(
        fig,
        kind="temporal_heatmap",
        title="全年时空热力图：购电功率与储电量的日×时段结构",
        x="time_of_day_hour",
        y=["purchase_power_mw", "storage_kwh"],
        caption=(
            "上：全年 365×144 的计划购电功率 b/Δt（MW，色标上限取 99.5 分位以避免尖峰压色）；"
            "下：储电量 E（kWh，色标固定为运行区间 [1200, 10800]）。红圈标出题面表 1/表 2 的 4 个指定日期"
            "（2025-03-20/06-21/09-23/12-21）。两图纵轴为自然日（1 月在上），横轴为 10 分钟时段（0:10→24:10 位置口径）；"
            "储电量在年末放空至 1200 kWh 是 AS04 终端自由口径的结果，须与价格套利区分。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ---------------------------------------------------------------- 图 4：储电量轨迹
def figure_soc_trajectory(source_hash: str, source_data: str) -> dict:
    storage = DATA["storage"]
    idx = np.arange(1, TOTAL + 1)
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(FIG_W + 4.0, FIG_H + 1.2), layout="constrained",
        gridspec_kw={"width_ratios": [2, 1]},
    )
    ax1.plot(idx, storage, color=PRIMARY, lw=0.8, label="时段末储电量 $E$")
    ax1.axhline(10800, color=WARNING, ls="--", lw=1.2, label="$E_{max}$ = 10800 kWh")
    ax1.axhline(1200, color=WARNING, ls=":", lw=1.2, label="$E_{min}$ = 1200 kWh")
    ax1.axhline(6000, color=SECONDARY, ls="-.", lw=1.2, label="$E_{1/1,0}$ = 6000 kWh（题面初值）")
    for pos in [d * SEGMENTS_PER_DAY for d in MONTH_TICKS[1:]]:
        ax1.axvline(pos, color=NEUTRAL, lw=0.6, ls=":", alpha=0.5)
    ax1.set_xticks([d * SEGMENTS_PER_DAY for d in MONTH_TICKS])
    ax1.set_xticklabels(MONTH_LABELS)
    ax1.set_xlim(1, TOTAL)
    ax1.set_ylim(900, 12200)
    ax1.set_ylabel("储电量 $E$ (kWh)")
    ax1.set_xlabel("时段序号（第 d 日第 t 段 = 144(d−1)+t；竖虚线为月初）")
    ax1.set_title("全年 52,560 时段储电量轨迹：滚动递推、贴近上界运行、跨日连续")
    ax1.annotate(
        "$E_{max}$ = 10800 kWh（红虚线）　$E_{min}$ = 1200 kWh（红点线）　"
        "$E_{1/1,0}$ = 6000 kWh（绿点划线）",
        xy=(0.5, 0.985), xycoords="axes fraction", ha="center", va="top", fontsize=8.6, color=NEUTRAL,
        bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": NEUTRAL, "alpha": 0.9},
    )
    ax1.annotate(
        f"实测 $E\\in$[{storage.min():,.0f}, {storage.max():,.0f}] kWh；日初取值 "
        f"{DATA['solution']['totals']['day_start_unique_levels']} 个水平；"
        f"$E_{{2/1,0}}$ = {DATA['state_start'][DELIVERY_START_DAY]:,.0f} kWh",
        xy=(0.5, 0.02), xycoords="axes fraction", ha="center", va="bottom", fontsize=8.8, color=NEUTRAL,
        bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": NEUTRAL, "alpha": 0.9},
    )

    zoom = np.s_[-14 * SEGMENTS_PER_DAY :]
    z_idx = np.arange(1, 14 * SEGMENTS_PER_DAY + 1)
    ax2.plot(z_idx - 1, storage[zoom], color=PRIMARY, lw=1.4, label="储电量 $E$")
    ax2.axhline(1200, color=WARNING, ls=":", lw=1.2, label="$E_{min}$ = 1200 kWh")
    ax2.axhline(10800, color=WARNING, ls="--", lw=1.2, label="$E_{max}$ = 10800 kWh")
    ax2.set_xticks([14 * (d + 1) - 1 for d in range(0, 14, 2)])
    ax2.set_xticklabels([(DAY0 + timedelta(days=DAYS - 14 + d)).strftime("%m-%d") for d in range(0, 14, 2)],
                        fontsize=8.5)
    ax2.set_xlim(0, 14 * SEGMENTS_PER_DAY - 1)
    ax2.set_ylabel("储电量 $E$ (kWh)")
    ax2.set_xlabel("年末 14 天（2025-12-18 → 12-31）")
    ax2.set_title("年末放大：期末放空至 $E_{min}$")
    ax2.legend(loc="lower left", fontsize=8, ncol=1, handlelength=1.6, framealpha=0.85,
               facecolor="white", edgecolor=NEUTRAL)
    ax2.annotate(
        f"$E_{{12/31,144}}$ = {DATA['solution']['totals']['storage_final_kwh']:,.0f} kWh\n"
        "（AS04 终端自由：放空 4320 kWh\n等价少购，非价格套利）",
        xy=(0.98, 0.03), xycoords="axes fraction", ha="right", va="bottom", fontsize=8, color=WARNING,
        bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": WARNING, "alpha": 0.92},
    )
    return emit(
        fig,
        kind="soc_trajectory",
        title="prob02 全年储电量轨迹与年末终值放大",
        x="period_index",
        y=["storage_kwh"],
        caption=(
            "左：全年 52,560 时段末储电量 E（kWh）轨迹，虚线为运行区间 [E_min, E_max] = [1200, 10800] kWh，"
            "点划线为题面初值 6000 kWh（2025-01-01 0:00）；储电量长期贴近上界运行，跨日由 E_{d,0}=E_{d−1,144} 连续衔接"
            "（continuity_residual_max = 0）。右：年末 14 天放大，期末放空至 E_{12/31,144} = 1200.00 kWh（AS04 终端自由口径），"
            "该「放空」等价于少购 4320 kWh，须与价格套利区分（论文须披露）。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ---------------------------------------------------------------- 图 5：全年供需构成与弃光
def figure_energy_balance(source_hash: str, source_data: str) -> dict:
    months = DATA["months"]
    labels = [f"{m} 月" for m in months]
    x = np.arange(len(months))
    pv = DATA["month_pv"] / 1e6
    buy = DATA["month_purchase"] / 1e6
    dis = DATA["month_discharge_sum"] / 1e6
    demand = (DATA["month_load"] + DATA["month_charge"]) / 1e6
    spill = DATA["month_spill"] / 1e6

    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(FIG_W + 2.0, FIG_H), layout="constrained", gridspec_kw={"width_ratios": [3, 2]},
    )
    ax1.stackplot(
        x,
        buy,
        pv - spill,
        dis,
        colors=[PRIMARY, SECONDARY, ACCENT],
        alpha=0.85,
        labels=["外网购电 $\\Sigma b$", "光伏实际消纳 $\\Sigma(PV\\Delta t - s)$", "储能放电 $\\Sigma q_{dis}$"],
    )
    residual = DATA["month_residual"] / 1e6
    ax1.plot(x, demand, color="black", lw=1.8, ls="--", label="需求 = 负载 $\\Sigma L\\Delta t$ + 充电 $\\Sigma c$")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=0, fontsize=9)
    ax1.set_ylabel("电量 (GWh/月)")
    ax1.set_xlabel("月份（2025 年，含 1 月预热期）")
    ax1.set_title("全年供需构成（按月汇总）：供给三项堆叠与需求曲线逐月重合")
    ax1.legend(frameon=False, loc="upper left", ncol=1, fontsize=9)
    ax1.annotate(
        f"闭合残差最大 {residual.max():.3e} GWh；全期 $\\Sigma s$ = {DATA['solution']['totals']['total_spill_kwh'] / 1e6:,.3f} GWh",
        xy=(0.99, 0.60), xycoords="axes fraction", ha="right", va="top", fontsize=9, color=NEUTRAL,
    )

    ratio = 100.0 * DATA["month_spill"] / np.maximum(DATA["month_pv"], 1e-9)
    bars = ax2.barh(labels[::-1], ratio[::-1], color=ACCENT, alpha=0.9)
    for rect, value, kwh in zip(bars, ratio[::-1], DATA["month_spill"][::-1] / 1e6):
        ax2.annotate(
            f"{value:.1f}%  ({kwh:.2f} GWh)",
            xy=(value, rect.get_y() + rect.get_height() / 2),
            xytext=(4, 0), textcoords="offset points", va="center", fontsize=8,
        )
    ax2.set_xlim(0, ratio.max() * 1.42)
    ax2.set_xlabel("弃光率 $\\Sigma s / \\Sigma(PV\\Delta t)$ (%)")
    ax2.set_title("逐月弃光率与弃光电量\n（AS09：$s\\leq PV\\Delta t$、目标系数 0，无售电收益）")
    ax2.grid(axis="y", visible=False)
    ax2.annotate(
        "弃光在 2–11 月真实发生；\n1 月与 12 月光伏低、弃光为 0",
        xy=(0.98, 0.03), xycoords="axes fraction", ha="right", va="bottom", fontsize=8.5, color=NEUTRAL,
        bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": NEUTRAL, "alpha": 0.92},
    )
    return emit(
        fig,
        kind="energy_balance",
        title="prob02 全年供需构成与弃光（按月汇总）",
        x="month",
        y=["purchase_kwh", "pv_used_kwh", "discharge_kwh", "demand_kwh", "spill_kwh"],
        caption=(
            "左：按月汇总的供给三项堆叠（外网购电 b、光伏实际消纳 PVΔt−s、储能放电 q_dis）与需求（负载 LΔt + 充电 c），"
            "两者逐月重合；闭合关系即恒等式 (I2) 的月度切片，残差量级 ~1e-9 GWh（全期 (I2) 残差为 0）。"
            "右：逐月弃光率（Σs/ΣPVΔt）与弃光电量；全期弃光 Σs = 990,168.09 kWh（0.99 GWh），"
            "因 AS09 的 s 目标系数为 0，弃光不产生收益也不受惩罚。单位 GWh/月。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ---------------------------------------------------------------- 图 6：三维全年调度节律
def figure_rhythm_3d(source_hash: str, source_data: str) -> dict:
    day = DATA["sub_day"]
    tod = DATA["sub_tod"]
    net = DATA["sub_net"]

    fig = plt.figure(figsize=(FIG_W + 1.6, FIG_H + 2.4))
    ax = fig.add_subplot(111, projection="3d")
    norm = TwoSlopeNorm(vmin=-833.34, vcenter=0.0, vmax=750.0)
    points = ax.scatter(day, tod, net, c=net, cmap="coolwarm", norm=norm, s=3.2, alpha=0.45,
                        depthshade=False, linewidths=0)
    ax.set_xlabel("日期（日索引，1 = 2025-01-01）", labelpad=10)
    ax.set_ylabel("时刻 (h)", labelpad=10)
    ax.set_zlabel("净放电 $q_{dis}-c$ (kWh/10min)", labelpad=7)
    ax.set_title(
        "全年调度三维视图：日期 × 时刻 × 净放电\n"
        f"（全 52,560 时段的 1/12 抽样 = {len(day):,} 点；Z>0 放电（红）、Z<0 充电（蓝）、Z=0 不动作（近白））"
    )
    ax.view_init(elev=22, azim=-52)
    ax.set_yticks([0, 6, 12, 18, 24])
    ax.set_zlim(-833.34, 750.0)
    bar = fig.colorbar(points, ax=ax, shrink=0.62, pad=0.10)
    bar.set_label("净放电 (kWh/10min)")
    ax.annotate(
        f"$\\Sigma q_{{dis}}$ = {DATA['solution']['totals']['total_discharge_kwh'] / 1e6:,.2f} GWh；"
        f"$\\Sigma c$ = {DATA['solution']['totals']['total_charge_kwh'] / 1e6:,.2f} GWh；同充放时段 0\n"
        f"净放电 = 0 的时段 {int((np.abs(DATA['net_discharge']) < 1e-9).sum()):,} / {TOTAL:,}",
        xy=(0.01, 0.98), xycoords="axes fraction", va="top", fontsize=9, color=NEUTRAL,
    )
    fig.tight_layout()
    return emit(
        fig,
        kind="rhythm_3d",
        title="全年调度三维视图：日期 × 时刻 × 净放电",
        x="day_index",
        y=["time_of_day_hour", "net_discharge_kwh"],
        caption=(
            "三维散点：X = 日期（2025 全年 365 天），Y = 时刻（0→24 h），Z = 净放电 q_dis−c（kWh/10min，正=放电、负=充电），"
            "颜色以 0 为中心的双向色标（红=放电、蓝=充电、近白=不动作）；为保持静态 PNG 可读性按每 12 个时段抽 1 点"
            "（4,380 点）。视角 elev=22°、azim=−52°。该图用于展示全年「时间—时刻—动作」的节律结构，"
            "定量判读以配套二维投影 rhythm_2d 与 soc_trajectory / energy_balance 为准。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ---------------------------------------------------------------- 图 7：配套二维投影
def figure_rhythm_2d(source_hash: str, source_data: str) -> dict:
    hist, p_bins, a_bins = DATA["pa_hist"]
    pc = 0.5 * (p_bins[1:] + p_bins[:-1])
    ac = 0.5 * (a_bins[1:] + a_bins[:-1])
    hist = hist.T

    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(FIG_W + 3.0, FIG_H), layout="constrained",
    )
    masked = np.ma.masked_where(hist <= 0, hist)
    im = ax1.pcolormesh(p_bins, a_bins, masked, cmap="viridis", shading="auto", norm=LogNorm(vmin=1, vmax=hist.max()))
    ax1.axhline(0, color="white", lw=0.9)
    ax1.set_xlabel("电价 $p_t$ (元/kWh)")
    ax1.set_ylabel("净放电 $q_{dis,t}-c_t$ (kWh/10min)")
    ax1.set_title("全部 52,560 时段的（电价，净放电）联合密度\n（对数色标；白色零线分隔充/放电）")
    bar = fig.colorbar(im, ax=ax1, pad=0.015)
    bar.set_label("时段计数（对数）")
    ax1.grid(visible=False)

    day = DATA["day_index"]
    sc = ax2.scatter(day, DATA["daily_netload"] / 1000.0, c=DATA["daily_wavg_price"], cmap="coolwarm",
                     s=16, alpha=0.9, edgecolors="none")
    ax2.axvline(DELIVERY_START_DAY, color=WARNING, ls="--", lw=1.3)
    ax2.annotate("2025-02-01 交付起点", xy=(DELIVERY_START_DAY + 3, DATA["daily_netload"].min() / 1000.0 * 0.95),
                 fontsize=8.5, color=WARNING, va="bottom")
    bar2 = fig.colorbar(sc, ax=ax2, pad=0.015)
    bar2.set_label("购电加权均价 (元/kWh)")
    ax2.set_ylabel("日净负荷 $\\Sigma(L-PV)\\Delta t$ (MWh/日)")
    ax2.set_title("逐日净负荷与购电均价（颜色）：季节性由光伏出力驱动")
    mark_months(ax2)
    finish_xlabel_days(ax2)
    return emit(
        fig,
        kind="rhythm_2d",
        title="三维节律的二维投影：电价—净放电密度与逐日净负荷",
        x="price_yuan_per_kwh + day_index",
        y=["net_discharge_kwh", "daily_net_load_kwh"],
        caption=(
            "左：全年 52,560 个时段的（电价 p_t，净放电 q_dis−c）二维直方图（对数色标），消除三维视角的遮挡与深度歧义；"
            "低电价段集中在净放电 < 0（充电）区，中高电价段出现净放电 = 0（不动作）与 > 0（放电）两支，"
            "量化了「低价充、高价放」的分时套利结构。右：逐日净负荷（MWh/日）与购电加权均价（颜色），"
            "红虚线为 2025-02-01 交付起点；净负荷的季节性完全由附件 2 实际光伏出力驱动（电价曲线逐日重复）。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ---------------------------------------------------------------- 图 8：指定日期四联
def figure_spec_dates(source_hash: str, source_data: str, tables: dict) -> dict:
    tod = (np.arange(SEGMENTS_PER_DAY) + 0.5) * DT_H
    fig, axes = plt.subplots(2, 2, figsize=(FIG_W + 2.0, FIG_H + 4.2))
    fig.subplots_adjust(left=0.075, right=0.985, top=0.90, bottom=0.215, hspace=0.42, wspace=0.22)
    notes = []
    for ax, (label, day) in zip(axes.ravel(), SPEC_DAYS.items()):
        sl = day_slice(day)
        entry = tables["table1"][label]
        t2 = tables["table2"][label]
        ax.fill_between(tod, DATA["purchase"][sl] / DT_H / 1000.0, color=PRIMARY, alpha=0.28,
                        label="计划购电 $b_t/\\Delta t$")
        ax.plot(tod, DATA["purchase"][sl] / DT_H / 1000.0, color=PRIMARY, lw=1.4)
        ax.plot(tod, DATA["load"][sl] / DT_H / 1000.0, color=WARNING, lw=1.5, label="负载 $L_t$")
        ax.plot(tod, DATA["pv_energy"][sl] / DT_H / 1000.0, color=SECONDARY, lw=1.5, label="光伏 $PV_t$")
        ax.set_xlim(0, 24)
        ax.set_xticks(np.arange(0, 25, 4))
        ax.set_xticklabels([f"{h}:00" for h in range(0, 25, 4)], fontsize=8.5)
        ax.set_ylim(0, max(DATA["load"][sl].max(), DATA["pv_energy"][sl].max()) / DT_H / 1000.0 * 1.25)
        ax.set_title(
            f"{label}（日索引 {day}）\n"
            f"$C_d$ = {entry['all_day_cost_yuan']:,.0f} 元；$\\Sigma b$ = {entry['all_day_energy_kwh']:,.1f} kWh；"
            f"$E_{{d,0}}$ = {t2['storage_0_00_kwh']:,.1f} → $E_{{d,144}}$ = {t2['storage_24_00_kwh']:,.1f} kWh",
            fontsize=10,
        )
        ax.set_ylabel("功率 (MW)", fontsize=9)
        notes.append(
            f"{label}：表 1 六时段购电量 (kWh) = "
            + " / ".join(f"{s['purchase_kwh']:,.1f}" for s in entry["slots"])
        )
    axes[0, 0].legend(frameon=False, loc="upper left", ncol=1, fontsize=8.5)
    fig.suptitle(
        "题面指定 4 个交付日期（2025-03-20 / 06-21 / 09-23 / 12-21）的日内功率与表 1/表 2 摘要",
        fontsize=12.5,
    )
    fig.text(
        0.5, 0.055,
        "表 2 计划窗端点储电量（0:00/24:00 为计划窗首/末状态，AS01 左端点相位；本问为全年滚动逐日切片，"
        "与 prob01 的单日周期恒 6000 kWh 语义不同）\n"
        + "\n".join(notes)
        + "\n全部数值取自 tables.json（来源 solution.json 序列）；表 1 时段位置 i = 60/72/84/96/108/120 对应 "
          "10:00/12:00/14:00/16:00/18:00/20:00 起点。",
        ha="center", va="center", fontsize=8.4, color=NEUTRAL,
        bbox={"boxstyle": "round,pad=0.4", "fc": "white", "ec": NEUTRAL, "alpha": 0.95},
    )
    return emit(
        fig,
        kind="spec_dates",
        title="题面 4 个指定日期的日内功率与表 1/表 2 摘要",
        x="time_of_day_hour",
        y=["purchase_power_mw", "load_power_mw", "pv_power_mw", "storage_0_00_kwh", "storage_24_00_kwh"],
        caption=(
            "四个交付期指定日期（2025-03-20 / 06-21 / 09-23 / 12-21）的日内功率：阴影+实线为计划购电 b/Δt，"
            "红为负载 L，绿为光伏 PV（MW）。每格下方标注该日表 2 的计划窗首/末储电量与表 1 的六个时段购电量"
            "（位置 i = 60/72/84/96/108/120，对应 10:00/12:00/14:00/16:00/18:00/20:00 起点）。"
            "注意：表 2 的端点储电量在本问为全年滚动的逐日切片（如 2025-03-20 = 8550.00 → 4352.87 kWh），"
            "与 prob01 的单日周期口径（恒 6000 kWh）语义不同，论文须显式区分。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ---------------------------------------------------------------- 图 9：3D 跨日耦合
def figure_daily_coupling_3d(source_hash: str, source_data: str) -> dict:
    day = DATA["day_index"]
    start = DATA["state_start"]
    gap = DATA["gap"]
    cost = DATA["daily_cost"]

    fig = plt.figure(figsize=(FIG_W + 1.6, FIG_H + 2.0))
    ax = fig.add_subplot(111, projection="3d")
    points = ax.scatter(day, start, gap, c=cost, cmap="viridis", s=16, alpha=0.9, depthshade=False)
    ax.set_xlabel("日期（日索引）", labelpad=9)
    ax.set_ylabel("日初储电量 $E_{d,0}$ (kWh)", labelpad=9)
    ax.set_zlabel("$\\Delta E_d = E_{d,144}-E_{d,0}$ (kWh)", labelpad=6)
    ax.set_title(
        "跨日耦合三维视图：日期 × 日初储电量 × 日内净变化（颜色 = 日费用）\n"
        "滚动递推 $E_{d,0}=E_{d-1,144}$（连续性残差 0）"
    )
    ax.view_init(elev=24, azim=-64)
    bar = fig.colorbar(points, ax=ax, shrink=0.62, pad=0.10)
    bar.set_label("日购电费 (元)")
    ax.annotate(
        f"日初取值 {DATA['solution']['totals']['day_start_unique_levels']} 个水平；"
        f"$\\Sigma\\Delta E_d$ = {gap.sum():,.0f} kWh（= 期末 1200 − 期初 6000）",
        xy=(0.01, 0.95), xycoords="axes fraction", fontsize=9, color=NEUTRAL,
    )
    fig.tight_layout()
    return emit(
        fig,
        kind="daily_coupling_3d",
        title="跨日耦合三维视图：日期 × 日初储电量 × 日内净变化",
        x="day_index",
        y=["state_start_kwh", "delta_e_kwh", "daily_cost_yuan"],
        caption=(
            "三维散点：X = 日期，Y = 日初储电量 E_{d,0}（kWh），Z = ΔE_d = E_{d,144} − E_{d,0}（kWh），颜色 = 日购电费（元）。"
            "用于展示 AS03 滚动递推下跨日状态耦合的结构：日初储电量取值有限（96 个水平）而 ΔE_d 分布较宽，"
            "Σ ΔE_d = −4800 kWh 即期末放空（E_{12/31,144} = 1200 相对 E_{1/1,0} = 6000）。"
            "定量判读以配套二维图 daily_coupling_2d 与 tables.json 为准。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ---------------------------------------------------------------- 图 10：跨日耦合二维配套
def figure_daily_coupling_2d(source_hash: str, source_data: str) -> dict:
    month = DATA["month"]
    start = DATA["state_start"]
    end = DATA["state_end"]
    cost = DATA["daily_cost"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(FIG_W + 2.0, FIG_H), layout="constrained")
    sc = ax1.scatter(start, cost, c=month, cmap="twilight_shifted", s=20, alpha=0.9, edgecolors="none")
    bar = fig.colorbar(sc, ax=ax1, pad=0.015, ticks=list(range(1, 13, 2)))
    bar.set_label("月份")
    ax1.set_xlabel("日初储电量 $E_{d,0}$ (kWh)")
    ax1.set_ylabel("日购电费 $C_d$ (元)")
    ax1.set_title("日初储电量—日费用（颜色 = 月份）\n日初取值 96 个水平（LP 最优面非唯一）")
    r = float(np.corrcoef(start, cost)[0, 1])
    ax1.annotate(
        f"Pearson $r$ = {r:+.3f}\n冬季（深色）费用高、夏季（浅色）费用低",
        xy=(0.02, 0.97), xycoords="axes fraction", ha="left", va="top", fontsize=9, color=NEUTRAL,
        bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": NEUTRAL, "alpha": 0.9},
    )

    ax2.scatter(start, end, c=DATA["day_index"], cmap="cividis", s=18, alpha=0.9, edgecolors="none")
    lo, hi = 1100, 10900
    ax2.plot([lo, hi], [lo, hi], color=WARNING, ls="--", lw=1.2, label="对角参考线 $E_{d,144}=E_{d,0}$")
    ax2.set_xlim(lo, hi)
    ax2.set_ylim(lo, hi)
    ax2.set_xlabel("日初储电量 $E_{d,0}$ (kWh)")
    ax2.set_ylabel("日末储电量 $E_{d,144}$ (kWh)")
    ax2.set_title("滚动递推闭合检验：$E_{d,0}$ 与 $E_{d−1,144}$ 逐日衔接\n（散点 = 各日 (初, 末) 对）")
    ax2.legend(frameon=False, loc="upper left", fontsize=8.5)
    ax2.annotate(
        f"$|E_{{d,0}}-E_{{d-1,144}}|_{{\\max}}$ = {DATA['solution']['identities']['continuity_residual_max']:.1e} kWh\n"
        f"$E_{{12/31,144}}$ = {end[-1]:,.0f} kWh（期末放空）",
        xy=(0.98, 0.05), xycoords="axes fraction", ha="right", va="bottom", fontsize=9, color=WARNING,
        bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": WARNING, "alpha": 0.92},
    )
    return emit(
        fig,
        kind="daily_coupling_2d",
        title="跨日耦合的二维投影：日初储电量—日费用与滚动闭合检验",
        x="state_start_kwh",
        y=["daily_cost_yuan", "state_end_kwh"],
        caption=(
            "左：各日初储电量 E_{d,0} 与日购电费 C_d 的关系（颜色 = 月份），日初取值 96 个水平，"
            "说明 LP 最优面不唯一、日初状态可落在多个水平；费用差异主要由光伏季节性（净负荷）驱动。"
            "右：各日 (E_{d,0}, E_{d,144}) 散点与对角线参考；跨日连续性由 E_{d,0}=E_{d−1,144} 保证（残差 0），"
            "右下角点 (8550, 1200) 为 2025-12-31 的期末放空日（AS04 终端自由）。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


# ---------------------------------------------------------------- 图 11：费用量级与恒等式
def figure_cost_bounds(source_hash: str, source_data: str) -> dict:
    solution = DATA["solution"]
    checks = {item["name"]: item for item in solution["checks"]}
    # 口径核对（prob02_model.evaluate 的 record 语义与 prob01 相反）：
    #   analytic_lower_bound: value = cost, threshold = 解析下界 min(p)·[N+η(E_min−E_0)]
    #   analytic_upper_bound: value = 无储能构造上界, threshold = cost
    lower = float(checks["analytic_lower_bound"]["threshold"])
    upper = float(checks["analytic_upper_bound"]["value"])
    optimum = float(solution["objective_yuan"])
    delivery = float(solution["delivery_cost_yuan"])
    january = float(solution["january_cost_yuan"])
    assert abs(float(checks["analytic_lower_bound"]["value"]) - optimum) < 1e-6
    assert abs(float(checks["analytic_upper_bound"]["threshold"]) - optimum) < 1e-6
    assert lower < optimum < upper, (lower, optimum, upper)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(FIG_W, FIG_H + 2.4), layout="constrained",
                                   gridspec_kw={"height_ratios": [2, 3]})
    labels = ["全期目标值\n$C^*$（365 天）", "交付期合计\n2025-02-01→12-31", "1 月预热期"]
    values = [optimum, delivery, january]
    colors = [PRIMARY, SECONDARY, NEUTRAL]
    bars = ax1.bar(labels, values, color=colors, width=0.5)
    for rect, value, share in zip(bars, values, [1.0, delivery / optimum, january / optimum]):
        ax1.annotate(
            f"{value:,.0f} 元\n({share * 100:.2f}%)",
            xy=(rect.get_x() + rect.get_width() / 2, value), xytext=(0, 4),
            textcoords="offset points", ha="center", va="bottom", fontsize=9.5,
        )
    ax1.axhline(1e7, color=WARNING, ls="--", lw=1.2)
    ax1.annotate("10⁷ 元量级门禁", xy=(0.99, 1.02e7), ha="right", va="bottom", fontsize=8.5, color=WARNING)
    ax1.set_ylim(0, optimum * 1.32)
    ax1.set_ylabel("购电费 (元)")
    ax1.set_title("费用量级与口径分解（D9：目标 $\\min\\Sigma(p b + 5p q_{em})$，不乘 $\\Delta t$）")
    ax1.grid(axis="x", visible=False)

    rows = [
        ("解析下界\n$p_{min}[N+\\eta(E_{min}-E_0)]$", lower, NEUTRAL),
        ("最优目标值 $C^*$", optimum, PRIMARY),
        ("无储能可行上界\n$\\Sigma p\\max(0,L-PV)\\Delta t$", upper, NEUTRAL),
    ]
    ypos = np.arange(len(rows))
    ax2.axvspan(lower, upper, color=PRIMARY, alpha=0.07, zorder=0)
    bars2 = ax2.barh(ypos, [r[1] for r in rows], color=[r[2] for r in rows], height=0.45, zorder=3)
    for rect, (label, value, _), share in zip(bars2, rows, [(lower - lower) / (upper - lower),
                                                             (optimum - lower) / (upper - lower), 1.0]):
        ax2.annotate(
            f"{value:,.2f} 元",
            xy=(value, rect.get_y() + rect.get_height() / 2), xytext=(6, 0),
            textcoords="offset points", va="center", fontsize=9.5,
        )
    ax2.axvline(optimum, color=ACCENT, ls="--", lw=1.4, zorder=4)
    ax2.set_yticks(ypos)
    ax2.set_yticklabels([r[0] for r in rows], fontsize=9.5)
    ax2.set_xlim(0, upper * 1.16)
    ax2.set_xlabel("全期购电费 (元)")
    ax2.set_title("最优解落在独立重算的解析可行区间内")
    ax2.grid(axis="y", visible=False)
    ax2.annotate(
        f"区间宽度 {upper - lower:,.0f} 元；$C^*$ 位于区间 {(optimum - lower) / (upper - lower) * 100:.1f}% 处\n"
        f"恒等式 (I2) 闭合：$\\Sigma b$ = {solution['totals']['total_purchase_kwh']:,.1f} kWh\n"
        f"= 净负荷 + 弃光 + 0.1·充电 − 0.9·(6000−1200)，残差 {solution['identities']['I2_residual']:.1e}",
        xy=(0.99, 0.05), xycoords="axes fraction", ha="right", va="bottom", fontsize=8.6, color=NEUTRAL,
        bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": NEUTRAL, "alpha": 0.92},
    )
    return emit(
        fig,
        kind="cost_bounds",
        title="prob02 费用量级检验与解析区间（含 (I2) 恒等式）",
        x="cost_case",
        y=["cost_yuan", "analytic_bounds_yuan"],
        caption=(
            "上：全期目标值 13,758,182.57 元、交付期 12,233,050.83 元（88.91%）、1 月预热期 1,525,131.74 元，量级 10⁷ 元，"
            "符合 D9 量纲口径（不带 Δt）。下：最优值落在独立重算的解析下界 7,525,691.13 元（p_min[N+η(E_min−E_0)]）与"
            "无储能构造上界 18,298,592.37 元之间（C* 位于区间 59.1% 处）；注记为结构恒等式 (I2) 的闭合关系（残差 0）。"
        ),
        source_hash=source_hash,
        source_data=source_data,
    )


def main() -> int:
    solution, tables, run_manifest = load_results()
    DATA["solution"] = solution
    DATA["tables"] = tables
    DATA["run_manifest"] = run_manifest
    derive()

    solution_hash = hash_path(SOLUTION_PATH)
    tables_hash = hash_path(TABLES_PATH)
    combined_hash = hashlib.sha256(f"{solution_hash}{tables_hash}".encode("utf-8")).hexdigest()
    solution_rel = relative(SOLUTION_PATH)
    tables_rel = relative(TABLES_PATH)

    items = [
        figure_year_energy_flow(solution_hash, solution_rel),
        figure_cost_price_rhythm(solution_hash, solution_rel),
        figure_temporal_heatmap(solution_hash, solution_rel),
        figure_soc_trajectory(solution_hash, solution_rel),
        figure_energy_balance(solution_hash, solution_rel),
        figure_rhythm_3d(solution_hash, solution_rel),
        figure_rhythm_2d(solution_hash, solution_rel),
        figure_spec_dates(combined_hash, f"{solution_rel} + {tables_rel}", tables),
        figure_daily_coupling_3d(solution_hash, solution_rel),
        figure_daily_coupling_2d(solution_hash, solution_rel),
        figure_cost_bounds(solution_hash, solution_rel),
    ]

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
