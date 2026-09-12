# -*- coding: utf-8 -*-
"""生成论文插图：全部图件均从已落盘的解序列/统计量重绘，图内文字不含内部编号与过程注记。

输出目录：paper/figs（文件名统一为 figNN_*.png）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
B = ROOT / "problems" / "microgrid_2025"
DATA = ROOT / "data"
OUT = ROOT / "paper" / "figs"

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150
plt.rcParams["savefig.dpi"] = 150
plt.rcParams["font.size"] = 10
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.3
plt.rcParams["axes.titlesize"] = 10.5

P01 = B / "prob01/versions/assumption_v003"
P02 = B / "prob02/versions/assumption_v001"
P03 = B / "prob03/versions/assumption_v001"
P04 = B / "prob04/versions/assumption_v001"
SOL01 = P01 / "results/prob01_v003_f001_run002"
SOL02 = P02 / "results/prob02_v001_f001_run002"
SOL03 = P03 / "results/prob03_v001_f001_run003"
SOL42 = P04 / "results/prob04_v001_f001_4-2_run002"
SOL43 = P04 / "results/prob04_v001_f001_4-3_run002"
AB02 = P02 / "ablations/results/prob02_v001_ablation_run001"
ROB03 = P03 / "robustness/results/prob03_v001_robust_run001"
AB42 = P04 / "ablations/results/prob04_v001_ablation_4-2_run003"
AB43 = P04 / "ablations/results/prob04_v001_ablation_4-3_run003"

SPEC_DATES = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]
DT = 1.0 / 6.0
HOURS = (np.arange(144) + 1) * 10 / 60.0  # 左端点口径：第 i 段结束于 10i 分钟


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def add_paths() -> None:
    for sub in ("prob01/versions/assumption_v003/code", "prob02/versions/assumption_v001/code",
                "prob03/versions/assumption_v001/code", "prob04/versions/assumption_v001/code"):
        sys.path.insert(0, str(B / sub))


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT / name, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", name)


# ---------------------------------------------------------------- 输入数据

def f01_inputs():
    import prob01_io

    a1 = prob01_io.read_attachment1(DATA / "附件1.xlsx")
    fig, axes = plt.subplots(3, 1, figsize=(7.6, 7.0), sharex=True)
    axes[0].plot(HOURS, a1.pv_kw, color="#2f7d32", lw=1.2, label="光伏发电功率")
    axes[0].plot(HOURS, a1.load_kw, color="#c62828", lw=1.4, label="小区负载")
    axes[0].set_ylabel("功率 / kW")
    axes[0].legend(loc="upper left", fontsize=9)
    axes[0].set_title("代表性单日的光伏、负载与电价")
    axes[1].bar(HOURS, (a1.load_kw - a1.pv_kw) * DT, width=DT * 0.9, color="#5c6bc0")
    axes[1].axhline(0, color="k", lw=0.6)
    axes[1].set_ylabel("净负荷电量 / kWh")
    mask = a1.pv_kw > a1.load_kw
    axes[1].fill_between(HOURS, 0, (a1.load_kw - a1.pv_kw) * DT, where=mask,
                         color="#a5d6a7", alpha=0.8, step="mid")
    axes[1].set_title("净负荷电量与光伏盈余时段")
    axes[2].plot(HOURS, a1.price, color="#ef6c00", lw=1.4)
    axes[2].set_ylabel("电价 / (元/kWh)")
    axes[2].set_xlabel("时刻")
    axes[2].set_title("电价曲线")
    save(fig, "fig01_inputs.png")


def f02_year_structure():
    import prob03_io

    a2 = prob03_io.read_attachment2(DATA / "附件2.xlsx")
    net = (a2.load_kw - a2.pv_kw) / 1000.0  # MW
    days = np.arange(365)
    fig, axes = plt.subplots(2, 1, figsize=(7.6, 6.6), sharex=True)
    im0 = axes[0].pcolormesh(HOURS, days, np.maximum(a2.pv_kw / 1000.0, 0), cmap="YlGn", shading="auto")
    axes[0].set_ylabel("日期序号")
    axes[0].set_title("光伏实际出力的日期×时段结构")
    fig.colorbar(im0, ax=axes[0], pad=0.01, label="MW")
    im1 = axes[1].pcolormesh(HOURS, days, net, cmap="RdBu_r",
                             vmin=-np.percentile(np.abs(net), 99.5), vmax=np.percentile(np.abs(net), 99.5),
                             shading="auto")
    axes[1].set_ylabel("日期序号")
    axes[1].set_xlabel("时刻")
    axes[1].set_title("全年净负荷的日期×时段分布")
    fig.colorbar(im1, ax=axes[1], pad=0.01, label="MW")
    save(fig, "fig02_year_structure.png")


# ---------------------------------------------------------------- 问题一

def f03_p1_arbitrage():
    s = load_json(SOL01 / "solution.json")["series"]
    price = np.array(s["price_yuan_per_kwh"])
    net = (np.array(s["load_energy_kwh"]) - np.array(s["pv_energy_kwh"]))
    ch = np.array(s["charge_kwh"])
    dis = np.array(s["discharge_kwh"])
    netdis = dis - ch
    fig, axes = plt.subplots(2, 1, figsize=(7.6, 5.8), sharex=True)
    order = np.argsort(price)
    colors = np.full(144, "#90a4ae", dtype=object)
    colors[order[:29]] = "#66bb6a"     # 最便宜 20%
    colors[order[-29:]] = "#ef5350"    # 最贵 20%
    axes[0].bar(HOURS, netdis, width=DT * 0.9, color=list(colors))
    axes[0].axhline(0, color="k", lw=0.6)
    axes[0].set_ylabel("净放电量 / kWh")
    axes[0].set_title("问题一：净放电量与电价分位")
    axes[0].legend(handles=[Patch(facecolor="#66bb6a", label="电价最低 20%"),
                            Patch(facecolor="#ef5350", label="电价最高 20%")],
                   fontsize=9, loc="upper left")
    axes[1].plot(HOURS, price, color="#ef6c00", lw=1.4)
    axes[1].scatter(HOURS[ch > 1e-9], price[ch > 1e-9], marker="^", s=22, color="#2e7d32", label="充电时段")
    axes[1].scatter(HOURS[dis > 1e-9], price[dis > 1e-9], marker="v", s=22, color="#c62828", label="放电时段")
    axes[1].set_ylabel("电价 / (元/kWh)")
    axes[1].set_xlabel("时刻")
    axes[1].legend(fontsize=9, loc="upper left")
    axes[1].set_title("充电与放电的电价分布")
    save(fig, "fig03_p1_arbitrage.png")


def f04_p1_dispatch():
    s = load_json(SOL01 / "solution.json")["series"]
    b = np.array(s["purchase_kwh"])
    ch = np.array(s["charge_kwh"])
    dis = np.array(s["discharge_kwh"])
    fig, axes = plt.subplots(2, 1, figsize=(7.6, 5.6), sharex=True)
    axes[0].fill_between(HOURS, 0, b, color="#1e88e5", alpha=0.55, step="mid", label="计划购电量")
    axes[0].plot(HOURS, b, color="#1565c0", lw=1.0)
    axes[0].set_ylabel("电量 / kWh")
    axes[0].legend(fontsize=9)
    axes[0].set_title("问题一最优计划购电量")
    axes[1].bar(HOURS, ch, width=DT * 0.9, color="#2e7d32", label="充电")
    axes[1].bar(HOURS, -dis, width=DT * 0.9, color="#ef6c00", label="放电")
    axes[1].axhline(0, color="k", lw=0.6)
    axes[1].set_ylabel("充 / 放电量 / kWh")
    axes[1].set_xlabel("时刻")
    axes[1].legend(fontsize=9)
    axes[1].set_title("储能充放电安排")
    save(fig, "fig04_p1_dispatch.png")


def f05_p1_soc():
    s = load_json(SOL01 / "solution.json")["series"]
    e = np.array(s["storage_kwh"])
    fig, ax = plt.subplots(figsize=(7.6, 3.7))
    ax.plot(np.concatenate([[0.0], HOURS]), np.concatenate([[6000.0], e]), color="#6a1b9a", lw=1.6)
    ax.axhline(1200, color="#c62828", ls="--", lw=1.0, label="储电量下限 1200 kWh")
    ax.axhline(10800, color="#c62828", ls="--", lw=1.0, label="储电量上限 10800 kWh")
    ax.axhline(6000, color="#455a64", ls=":", lw=1.0, label="日周期端点 6000 kWh")
    ax.set_ylim(1000, 11200)
    ax.set_xlabel("时刻")
    ax.set_ylabel("储电量 / kWh")
    ax.legend(fontsize=9, loc="lower right", ncol=3)
    ax.set_title("问题一储电量轨迹")
    save(fig, "fig05_p1_soc.png")


# ---------------------------------------------------------------- 问题二

def f06_p2_energy_flow():
    import prob03_io

    a2 = prob03_io.read_attachment2(DATA / "附件2.xlsx")
    d = load_json(SOL02 / "solution.json")["daily"]
    days = np.arange(365)
    load_d = a2.load_kw.sum(axis=1) * DT / 1000.0
    pv_d = a2.pv_kw.sum(axis=1) * DT / 1000.0
    b = np.array(d["purchase_kwh"]) / 1000.0
    spill = np.array(d["spill_kwh"]) / 1000.0
    cost = np.array(d["cost_total_yuan"]) / 1e4
    fig, axes = plt.subplots(2, 1, figsize=(7.6, 6.2), sharex=True)
    axes[0].stackplot(days, pv_d - spill, b, labels=["光伏消纳", "计划购电"], colors=["#a5d6a7", "#90caf9"], alpha=0.9)
    axes[0].plot(days, load_d, color="#c62828", lw=1.3, label="小区负载")
    axes[0].set_ylabel("电量 / MWh（每日）")
    axes[0].legend(fontsize=9, loc="upper left", ncol=3)
    axes[0].set_title("问题二：全年逐日供给构成与负载")
    axes[1].plot(days, cost, color="#ef6c00", lw=1.0)
    axes[1].axhline(np.mean(cost[31:]), color="#455a64", ls="--", lw=1.0,
                    label="交付期日均 %.2f 万元" % np.mean(cost[31:]))
    axes[1].axvline(31, color="#546e7a", ls=":", lw=1.0, label="交付期起点")
    axes[1].set_xlabel("日期序号（0 = 2025-01-01）")
    axes[1].set_ylabel("日购电费 / 万元")
    axes[1].legend(fontsize=9)
    axes[1].set_title("逐日购电费")
    save(fig, "fig06_p2_energy_flow.png")


def f07_p2_soc():
    d = load_json(SOL02 / "solution.json")["daily"]
    st = np.array(d["state_start_kwh"])
    fig, ax = plt.subplots(figsize=(7.6, 3.8))
    ax.plot(np.arange(365), st, color="#6a1b9a", lw=1.2, label="日初储电量")
    ax.plot(np.arange(1, 366), np.array(d["state_end_kwh"]), color="#00897b", lw=1.0, alpha=0.85, label="日末储电量")
    ax.axhline(1200, color="#c62828", ls="--", lw=1.0, label="储电量下限 1200 kWh")
    ax.axhline(8550, color="#546e7a", ls=":", lw=1.0, label="最常出现的水平 8550 kWh")
    ax.set_xlabel("日期序号（0 = 2025-01-01）")
    ax.set_ylabel("储电量 / kWh")
    ax.legend(fontsize=9, ncol=2)
    ax.set_title("问题二全年储电量轨迹")
    save(fig, "fig07_p2_soc.png")


def f08_p2_spec_dates():
    import prob03_io

    a2 = prob03_io.read_attachment2(DATA / "附件2.xlsx")
    s = load_json(SOL02 / "solution.json")["series"]
    b = np.array(s["purchase_kwh"])
    e = np.array(s["storage_kwh"])
    idx = [int(x) for x in (a2.dates.index(x) for x in SPEC_DATES)]
    fig, axes = plt.subplots(2, 2, figsize=(8.4, 6.2), sharex=True)
    for ax, day, label in zip(axes.ravel(), idx, SPEC_DATES):
        sl = slice(day * 144, (day + 1) * 144)
        ax.plot(HOURS, a2.load_kw[day], color="#c62828", lw=1.3, label="负载")
        ax.plot(HOURS, a2.pv_kw[day], color="#2e7d32", lw=1.3, label="光伏实际")
        ax2 = ax.twinx()
        ax2.fill_between(HOURS, 0, b[sl] / DT / 1000.0, color="#1e88e5", alpha=0.45, step="mid",
                         label="计划购电功率")
        ax2.set_ylim(0, 14)
        ax2.set_ylabel("购电功率 / MW", fontsize=9)
        ax2.grid(False)
        ax.set_title(label, fontsize=10)
        ax.set_ylabel("功率 / kW", fontsize=9)
        if ax is axes[0][0]:
            ax.legend(fontsize=8, loc="upper left")
    axes[1][0].set_xlabel("时刻")
    axes[1][1].set_xlabel("时刻")
    fig.suptitle("问题二：四个指定日期的日内功率构成", y=1.0)
    save(fig, "fig08_p2_spec_dates.png")


def f09_p2_bcap():
    comp = load_json(AB02 / "comparison.json")
    rows = comp["purchase_cap"]
    caps = np.array([r["b_cap_kw"] for r in rows])
    qem = np.array([r["q_em_kwh"] for r in rows])
    cost = np.array([r["objective_yuan"] for r in rows])
    order = np.argsort(-caps)
    caps, qem, cost = caps[order], qem[order], cost[order]
    base = cost.max() * 0 + load_json(SOL02 / "solution.json")["objective_yuan"]
    fig, axes = plt.subplots(2, 1, figsize=(7.6, 6.0), sharex=True)
    axes[0].plot(np.arange(len(caps)), np.maximum(qem, 1e-3), "o-", color="#1565c0")
    axes[0].set_yscale("log")
    axes[0].set_ylabel("紧急购电量 / kWh")
    axes[0].set_title("外网购电上限对紧急购电量与总费用的影响")
    for i, v in enumerate(qem):
        if v > 0:
            axes[0].annotate(f"{v:,.0f}", (i, max(v, 1e-3)), textcoords="offset points",
                             xytext=(0, 6), ha="center", fontsize=8)
    axes[1].plot(np.arange(len(caps)), cost / 1e6, "s-", color="#ef6c00")
    axes[1].axhline(base / 1e6, color="#455a64", ls="--", lw=1.0, label="无上限基准 %.2f 百万元" % (base / 1e6))
    axes[1].set_ylabel("全期总费用 / 百万元")
    axes[1].set_xticks(np.arange(len(caps)))
    axes[1].set_xticklabels([("%g" % c) for c in caps], rotation=45, fontsize=8)
    axes[1].set_xlabel("外网购电功率上限 / kW")
    axes[1].legend(fontsize=9)
    axes[1].set_title("紧急购电量与总费用随上限的变化")
    save(fig, "fig09_p2_bcap.png")


# ---------------------------------------------------------------- 问题三

def f10_p3_forecast():
    import prob03_io

    a2 = prob03_io.read_attachment2(DATA / "附件2.xlsx")
    a3 = prob03_io.read_attachment3(DATA / "附件3.xlsx")
    s = load_json(SOL03 / "solution.json")["series"]
    plan_pv = None
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 3.4))
    for ax, day, label in zip(axes, (31, 171), ("2025-02-01", "2025-06-21")):
        fc24 = np.asarray(a3.fc_kw[day, 0], dtype=float)  # 0:00 发布的 24 个整点值
        hours24 = np.arange(1, 25)
        # 整点锚定线性插值（首小时前向保持）
        anchors_x = np.concatenate([[0.0], hours24.astype(float)])
        anchors_y = np.concatenate([[fc24[0]], fc24])
        ax.plot(hours24, fc24, "o--", ms=3.5, color="#1565c0", lw=1.1, label="整点预报")
        ax.plot(np.concatenate([[0.0], HOURS]), np.concatenate([[fc24[0]], np.interp(HOURS, anchors_x, anchors_y)]),
                color="#1e88e5", lw=1.3, label="降尺度预报")
        ax.plot(np.concatenate([[0.0], HOURS]), np.concatenate([[a2.pv_kw[day, 0]], a2.pv_kw[day]]),
                color="#2e7d32", lw=1.4, label="光伏实际")
        ax.set_title(label, fontsize=10)
        ax.set_xlabel("时刻")
        ax.set_ylabel("功率 / kW", fontsize=9)
        ax.legend(fontsize=8)
    fig.suptitle("问题三：光伏预报的降尺度与预报—实际落差", y=1.02)
    save(fig, "fig10_p3_forecast.png")


def f11_p3_profile():
    import prob03_io

    a2 = prob03_io.read_attachment2(DATA / "附件2.xlsx")
    s = load_json(SOL03 / "solution.json")["series"]
    b = np.array(s["plan_purchase_kwh"])
    q = np.array(s["final_purchase_kwh"])
    qem = np.array(s["q_em_kwh"])
    day = int(a2.dates.index("2025-03-20"))
    sl = slice(day * 144, (day + 1) * 144)
    fig, axes = plt.subplots(2, 1, figsize=(7.6, 5.8), sharex=True)
    axes[0].plot(HOURS, b[sl] / DT / 1000.0, color="#1565c0", lw=1.3, label="计划购电功率")
    axes[0].plot(HOURS, q[sl] / DT / 1000.0, color="#ef6c00", lw=1.3, label="最终购电功率")
    for h in (6, 12, 18):
        axes[0].axvline(h, color="#78909c", ls=":", lw=0.9)
    axes[0].set_ylabel("功率 / MW")
    axes[0].legend(fontsize=9)
    axes[0].set_title("问题三：计划与最终购电量")
    axes[1].bar(HOURS, qem[sl], width=DT * 0.9, color="#c62828", label="紧急购电量")
    axes[1].set_ylabel("电量 / kWh")
    axes[1].set_xlabel("时刻")
    axes[1].legend(fontsize=9)
    axes[1].set_title("紧急购电量")
    save(fig, "fig11_p3_profile.png")


def f12_p3_cost():
    s3 = load_json(SOL03 / "solution.json")
    s2 = load_json(SOL02 / "solution.json")
    dl = s3["delivery"]
    plan, adj, em = dl["cost_plan_yuan"], dl["cost_adj_yuan"], dl["cost_em_yuan"]
    tot = plan + adj + em
    p2 = s2["delivery_cost_yuan"]
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 3.8))
    axes[0].bar(["计划购电费", "调整结算费", "紧急购电费"], [plan, adj, em],
                color=["#1565c0", "#ef6c00", "#c62828"])
    for i, v in enumerate([plan, adj, em]):
        axes[0].annotate(f"{v/1e4:,.1f} 万元", (i, v), textcoords="offset points", xytext=(0, 4),
                         ha="center", fontsize=9)
    axes[0].set_ylabel("费用 / 元")
    axes[0].set_title("问题三交付期费用分解")
    bottom = 0.0
    for v, c, lb in ((plan, "#1565c0", "计划购电费"), (adj, "#ef6c00", "调整结算费"), (em, "#c62828", "紧急购电费")):
        axes[1].bar(1, v, bottom=bottom, color=c, label=lb)
        bottom += v
    axes[1].bar(0, p2, color="#90a4ae", label="问题二交付期")
    axes[1].annotate("%.0f 万元" % (p2 / 1e4), (0, p2), textcoords="offset points", xytext=(0, 4), ha="center", fontsize=9)
    axes[1].annotate("%.0f 万元" % (tot / 1e4), (1, tot), textcoords="offset points", xytext=(0, 4), ha="center", fontsize=9)
    axes[1].annotate("差额 %.2f 万元"
                     % ((tot - p2) / 1e4), (0.5, max(tot, p2) * 0.55), ha="center", fontsize=8.5,
                     bbox=dict(fc="#fff8e1", ec="#f9a825"))
    axes[1].set_xticks([0, 1])
    axes[1].set_xticklabels(["问题二", "问题三"])
    axes[1].set_ylabel("交付期费用 / 元")
    axes[1].legend(fontsize=8)
    axes[1].set_title("问题三与问题二的交付期费用对比")
    save(fig, "fig12_p3_cost.png")


def f13_p3_soc():
    """问题三：日内满量程吞吐 + 日边界归零。

    旧版把「日末储电量」与「日初储电量」画成两条线，但二者在 365 天里取值相同
    （均为 1200 kWh），后画的线把先画的完全遮住；且 y 轴 90% 是空白，读者容易
    误判成“日初储电量只有第 0 天有数据、其余缺测”。这里改为两个子图：
    (a) 一个代表日的日内轨迹，展示满量程吞吐与日末回到下限；
    (b) 全年 365 天的日内区间带 + 日末储电量，直接说明“每天覆盖整个运行区间、
        日末恒为下限”。
    """
    sol = load_json(SOL03 / "solution.json")
    st = np.asarray(sol["daily"]["state_start_kwh"], dtype=float)
    en = np.asarray(sol["daily"]["state_end_kwh"], dtype=float)
    ser = np.asarray(sol["series"]["storage_kwh"], dtype=float)

    day = 78  # 2025-03-20
    xs = np.concatenate([[0.0], HOURS])
    ys = np.concatenate([[st[day]], ser[day * 144:(day + 1) * 144]])

    fig, axes = plt.subplots(1, 2, figsize=(8.8, 3.4))

    ax = axes[0]
    ax.plot(xs, ys, color="#6a1b9a", lw=1.6, label="时段末储电量")
    ax.axhline(10800, color="#c62828", ls="--", lw=1.0, label="运行上/下限 10800 与 1200 kWh")
    ax.axhline(1200, color="#c62828", ls="--", lw=1.0)
    ax.set_ylim(1000, 11300)
    ax.set_xlabel("时刻")
    ax.set_ylabel("储电量 / kWh")
    ax.set_title("(a) 代表日 2025-03-20：日内满量程吞吐，日末回到下限", fontsize=9.5)
    ax.legend(fontsize=8, loc="lower right")

    ax = axes[1]
    days = np.arange(365)
    mins = np.array([ser[i * 144:(i + 1) * 144].min() for i in days])
    maxs = np.array([ser[i * 144:(i + 1) * 144].max() for i in days])
    ax.fill_between(days, mins, maxs, color="#90caf9", alpha=0.9, label="日内的储电量范围")
    ax.plot(days, en, color="#00695c", lw=1.2, label="日末储电量（跨日边界值）")
    ax.axhline(1200, color="#c62828", ls="--", lw=1.0)
    ax.axhline(10800, color="#c62828", ls="--", lw=1.0)
    ax.set_ylim(1000, 11300)
    ax.set_xlabel("日期序号（0 = 2025-01-01）")
    ax.set_ylabel("储电量 / kWh")
    ax.set_title("(b) 全年：每日覆盖全运行区间，日末恒为下限（365/365 天）", fontsize=9.5)
    ax.annotate("日末储电量 365 天取值唯一：1200 kWh\n$\\sum_d |E_{d,144}-1200|=0$",
                xy=(205, 1200), xytext=(96, 4300), fontsize=8.5, color="#00695c",
                arrowprops=dict(arrowstyle="->", color="#00695c", lw=1.0))
    ax.legend(fontsize=8, loc="upper left")
    save(fig, "fig13_p3_soc.png")


def f14_p4_price():
    import prob04_io

    a4 = prob04_io.read_attachment4_price(DATA / "附件4.xlsx")
    s42 = load_json(SOL42 / "solution.json")["series"]
    s43 = load_json(SOL43 / "solution.json")["series"]
    pa = np.array(s42["price_actual_yuan_per_kwh"])
    pb = np.array(s42["price_belief_yuan_per_kwh"])
    pb43 = np.array(s43["price_belief_yuan_per_kwh"])
    dates = a4.dates
    days = [int(dates.index("2025-02-01")), int(dates.index("2025-06-21"))]
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 3.6))
    for ax, day, label in zip(axes, days, ("2025-02-01", "2025-06-21")):
        sl = slice(day * 144, (day + 1) * 144)
        ax.plot(HOURS, pa[sl], color="k", lw=1.6, label="实际电价")
        ax.plot(HOURS, pb[sl], color="#1565c0", lw=1.2, ls="--", label="决策层预测价（4-2）")
        ax.plot(HOURS, pb43[sl], color="#ef6c00", lw=1.0, ls=":", label="决策层预测价（4-3）")
        ax.set_title(label, fontsize=10)
        ax.set_xlabel("时刻")
        ax.set_ylabel("电价 / (元/kWh)", fontsize=9)
        ax.legend(fontsize=8)
    fig.suptitle("问题四：实际电价与决策层预测价", y=1.03)
    save(fig, "fig14_p4_price.png")


def f15_p4_backtest():
    bt = load_json(SOL42 / "forecast_backtest.json")
    mm = bt["windows"]["D_req"]["metrics"]
    name_map = {"PF-PERSIST": "前一日同时段（主）", "PF-DUAL": "水平×时段双因子",
                "PF-HIST": "历史同时段均值", "PF-AR": "自回归"}
    order = [k for k in ("PF-PERSIST", "PF-DUAL", "PF-HIST", "PF-AR") if k in mm]
    labels = [name_map.get(k, k) for k in order]
    mae = [float(mm[k]["mae"]) for k in order]
    mape = [float(mm[k]["mape"]) for k in order]
    rmse = [float(mm[k]["rmse"]) for k in order]
    p90 = [float(mm[k]["p90"]) for k in order]
    p99 = [float(mm[k]["p99"]) for k in order]
    x = np.arange(len(labels))
    w = 0.32
    fig, axes = plt.subplots(1, 2, figsize=(8.8, 3.6))
    axes[0].bar(x - w / 2, mae, w, label="MAE", color="#1565c0")
    axes[0].bar(x + w / 2, mape, w, label="MAPE", color="#ef6c00")
    for i, (a, b) in enumerate(zip(mae, mape)):
        axes[0].annotate("%.4f" % a, (i - w / 2, a), textcoords="offset points", xytext=(0, 3),
                         ha="center", fontsize=8)
        axes[0].annotate("%.2f%%" % (b * 100), (i + w / 2, b), textcoords="offset points", xytext=(0, 3),
                         ha="center", fontsize=8)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels, fontsize=8)
    axes[0].set_ylim(0, 0.20)
    axes[0].set_ylabel("MAE / (元/kWh) 与 MAPE")
    axes[0].legend(fontsize=8)
    axes[0].set_title("平均类误差")
    axes[1].bar(x - w, rmse, w, label="RMSE", color="#2e7d32")
    axes[1].bar(x, p90, w, label="P90", color="#6a1b9a")
    axes[1].bar(x + w, p99, w, label="P99", color="#c62828")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels, fontsize=8)
    axes[1].set_ylabel("尾部类误差 / (元/kWh)")
    axes[1].legend(fontsize=8)
    axes[1].set_title("尾部类误差")
    fig.suptitle("价格预测器的滚动回测", y=1.02)
    save(fig, "fig15_p4_backtest.png")


def f16_p4_cost():
    s42 = load_json(SOL42 / "solution.json")
    s43 = load_json(SOL43 / "solution.json")
    d42, d43 = s42["delivery"], s43["delivery"]
    p42, a42, e42 = d42["cost_plan_yuan"], d42["cost_adj_yuan"], d42["cost_em_yuan"]
    p43, a43, e43 = d43["cost_plan_yuan"], d43["cost_adj_yuan"], d43["cost_em_yuan"]
    fig, axes = plt.subplots(1, 2, figsize=(8.8, 3.9))
    for i, (p, a, e, lb) in enumerate(((p42, a42, e42, "链 4-2（≙重算问题二）"), (p43, a43, e43, "链 4-3（≙重算问题三）"))):
        bt = 0.0
        for v, c, n in ((p, "#1565c0", "计划购电费"), (a, "#ef6c00", "调整结算费"), (e, "#c62828", "紧急购电费")):
            axes[0].bar(i, v, bottom=bt, color=c, label=n if i == 0 else None)
            bt += v
        axes[0].annotate("%.2f 百万元" % (bt / 1e6), (i, bt), textcoords="offset points", xytext=(0, 4),
                         ha="center", fontsize=9)
    axes[0].set_xticks([0, 1])
    axes[0].set_xticklabels(["链 4-2", "链 4-3"])
    axes[0].set_ylabel("交付期费用 / 元")
    axes[0].legend(fontsize=8, loc="lower right")
    axes[0].set_title("两链交付期费用构成")
    labels = ["计划口径差", "偏差结算", "紧急购电"]
    vals = [p43 - p42, a43, e43]
    colors = ["#5c6bc0", "#ef6c00", "#c62828"]
    axes[1].bar(labels, vals, color=colors)
    for i, v in enumerate(vals):
        axes[1].annotate(f"{v/1e4:,.2f} 万元", (i, v), textcoords="offset points", xytext=(0, 4), ha="center", fontsize=9)
    axes[1].set_ylabel("金额 / 元")
    axes[1].set_title("两链差额的三分项归因")
    save(fig, "fig16_p4_cost.png")


def f17_p4_adjust():
    import prob04_io

    a4 = prob04_io.read_attachment4_price(DATA / "附件4.xlsx")
    s = load_json(SOL43 / "solution.json")["series"]
    b = np.array(s["plan_purchase_kwh"])
    q = np.array(s["final_purchase_kwh"])
    dev = (q - b).reshape(365, 144) / DT / 1000.0  # MW
    lim = np.percentile(np.abs(dev), 99.5)
    fig, axes = plt.subplots(2, 1, figsize=(7.6, 5.8), sharex=True)
    im = axes[0].pcolormesh(HOURS, np.arange(365), dev, cmap="RdBu_r", vmin=-lim, vmax=lim, shading="auto")
    axes[0].set_ylabel("日期序号")
    axes[0].set_title("链 4-3 调整量的日期×时段结构")
    fig.colorbar(im, ax=axes[0], pad=0.01, label="MW")
    daily_up = np.where(dev > 0, dev, 0).sum(axis=1)
    daily_dn = np.where(dev < 0, dev, 0).sum(axis=1)
    axes[1].bar(np.arange(365), daily_up, color="#c62828", width=0.9, label="日上调总量")
    axes[1].bar(np.arange(365), daily_dn, color="#1565c0", width=0.9, label="日下调总量")
    axes[1].set_xlabel("日期序号（0 = 2025-01-01）")
    axes[1].set_ylabel("电量 / MWh（每日）")
    axes[1].legend(fontsize=9)
    axes[1].set_title("逐日调整总量")
    save(fig, "fig17_p4_adjust.png")


def f18_p4_emergency():
    s43 = load_json(SOL43 / "solution.json")["daily"]
    s42 = load_json(SOL42 / "solution.json")["daily"]
    q43 = np.array(s43["q_em_kwh"])
    q42 = np.array(s42["q_em_kwh"])
    fig, ax = plt.subplots(figsize=(7.6, 3.6))
    ax.fill_between(np.arange(365), 0, q43, color="#ef9a9a", alpha=0.9, label="链 4-3 紧急购电量")
    ax.plot(np.arange(365), q43, color="#c62828", lw=0.8)
    ax.plot(np.arange(365), q42, color="#1565c0", lw=1.2, label="链 4-2 紧急购电量")
    ax.axvline(31, color="#546e7a", ls=":", lw=1.0, label="交付期起点")
    ax.set_xlabel("日期序号（0 = 2025-01-01）")
    ax.set_ylabel("紧急购电量 / kWh")
    ax.legend(fontsize=9)
    ax.set_title("链 4-3 逐日紧急购电量")
    save(fig, "fig18_p4_emergency.png")


# ---------------------------------------------------------------- 稳健性

def f19_robust_tornado():
    sens = load_json(ROB03 / "sensitivity.json")
    rows = sens["tornado"]
    cn = {"eta_both": "往返效率（充放同步）", "eta_ch": "充电效率", "eta_dis": "放电效率",
          "alpha_em": "紧急购电电价倍数", "e_init": "初始储电量", "p_max": "最大充放电功率",
          "e_min": "储电量下限", "e_max": "储电量上限", "beta": "偏差结算倍数",
          "beta_def_over": "偏差结算倍数"}
    labels = [cn.get(str(r.get("family", "")), str(r.get("label", ""))) for r in rows]
    lo = [r["delta_min_yuan"] / 1e4 for r in rows]
    hi = [r["delta_max_yuan"] / 1e4 for r in rows]
    y = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(7.6, 4.0))
    ax.barh(y, lo, color="#1565c0", label="参数向不利方向变动")
    ax.barh(y, hi, color="#ef6c00", label="参数向有利方向变动")
    ax.axvline(0, color="k", lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("交付期费用相对基准的变化 / 万元")
    ax.legend(fontsize=9)
    ax.set_title("单因素扰动下的参数敏感性")
    save(fig, "fig19_robust_tornado.png")


def f20_rh_depth():
    """前瞻深度对照：左图为两链的全期费用响应，右图为分链、分前瞻深度的日末储电量统计。

    所有数值直接读自 ablations 的 criteria.json（C4 / C_RH_BOUNDARY），不含手写常量。
    """
    crit = {ch: load_json((AB42 if ch == "4-2" else AB43) / "criteria.json")["criteria"]
            for ch in ("4-2", "4-3")}
    hs = [1, 3, 7, 14]
    cost = {ch: np.array([crit[ch]["C4"]["D_full_cost_by_horizon"]["H%d" % h] for h in hs])
            for ch in ("4-2", "4-3")}
    stat = {ch: crit[ch]["C_RH_BOUNDARY"]["state_end_statistics"] for ch in ("4-2", "4-3")}
    floor = {ch: np.array([stat[ch]["S-RH-H%d" % h]["days_at_lower_bound"] for h in hs], dtype=float)
             for ch in ("4-2", "4-3")}
    mean = {ch: np.array([stat[ch]["S-RH-H%d" % h]["mean"] for h in hs]) for ch in ("4-2", "4-3")}

    fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.8))
    style = {"4-2": ("#1565c0", "-", "o"), "4-3": ("#ef6c00", "--", "s")}
    x = np.arange(len(hs))
    for ch in ("4-2", "4-3"):
        c, ls, mk = style[ch]
        axes[0].plot(x, (cost[ch] / cost[ch][0] - 1) * 100, ls, marker=mk, color=c,
                     label="链 %s（前瞻 1 天基线 %.0f 万元）" % (ch, cost[ch][0] / 1e4))
    axes[0].axhline(0, color="k", lw=0.7)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(["%d 天" % h for h in hs])
    axes[0].set_xlabel("优化时的前瞻深度")
    axes[0].set_ylabel("全期费用相对前瞻 1 天的差 / %")
    axes[0].legend(fontsize=8)
    axes[0].set_title("前瞻深度对全期费用（365 天）的影响")
    axes[0].annotate("3 天之后饱和：3→14 天增量仅数元", (2, (cost["4-2"][2] / cost["4-2"][0] - 1) * 100),
                     textcoords="offset points", xytext=(-4, 16), fontsize=8, ha="right")

    w = 0.36
    for i, ch in enumerate(("4-2", "4-3")):
        axes[1].bar(x + (i - 0.5) * w, mean[ch], w, color=style[ch][0], label="链 %s" % ch)
    for i, ch in enumerate(("4-2", "4-3")):
        for j in range(len(hs)):
            axes[1].annotate("贴下限\n%d/365 天" % int(floor[ch][j]),
                             (j + (i - 0.5) * w, mean[ch][j]), textcoords="offset points",
                             xytext=(0, 5), ha="center", fontsize=8)
    axes[1].axhline(1200, color="#c62828", ls="--", lw=1.0, label="储电量下限 1200 kWh")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(["前瞻 %d 天" % h for h in hs])
    axes[1].set_ylabel("日末储电量均值 / kWh")
    axes[1].set_ylim(0, 8400)
    axes[1].legend(fontsize=8, loc="upper left")
    axes[1].set_title("日边界储电量行为：分链、分前瞻深度")
    fig.suptitle("滚动时域对照：只改变“优化时看多远”，决策时刻与承诺规则完全不变", y=1.02)
    save(fig, "fig20_rh_depth.png")


def main() -> None:
    add_paths()
    fns = [f01_inputs, f02_year_structure, f03_p1_arbitrage, f04_p1_dispatch, f05_p1_soc,
           f06_p2_energy_flow, f07_p2_soc, f08_p2_spec_dates, f09_p2_bcap,
           f10_p3_forecast, f11_p3_profile, f12_p3_cost, f13_p3_soc,
           f14_p4_price, f15_p4_backtest, f16_p4_cost, f17_p4_adjust, f18_p4_emergency,
           f19_robust_tornado, f20_rh_depth]
    for fn in fns:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            print("FAILED", fn.__name__, "->", type(exc).__name__, exc)


if __name__ == "__main__":
    main()
