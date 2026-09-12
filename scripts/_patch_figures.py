# -*- coding: utf-8 -*-
"""精确改写 build_paper_figures.py 中的 f13 与 f20 两个函数（按定义边界切片替换）。"""
from __future__ import annotations

from pathlib import Path

P = Path(__file__).resolve().parent / "build_paper_figures.py"

F20 = '''def f20_rh_depth():
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
                     label="链 %s（前瞻 1 天基线 %.2f 百万元）" % (ch, cost[ch][0] / 1e7))
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
            axes[1].annotate("贴下限\\n%d/365 天" % int(floor[ch][j]),
                             (j + (i - 0.5) * w, mean[ch][j]), textcoords="offset points",
                             xytext=(0, 3), ha="center", fontsize=7)
    axes[1].axhline(1200, color="#c62828", ls="--", lw=1.0, label="储电量下限 1200 kWh")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(["前瞻 %d 天" % h for h in hs])
    axes[1].set_ylabel("日末储电量均值 / kWh")
    axes[1].set_ylim(0, 7600)
    axes[1].legend(fontsize=8, loc="upper left")
    axes[1].set_title("日边界储电量行为：分链、分前瞻深度")
    fig.suptitle("滚动时域对照：只改变“优化时看多远”，决策时刻与承诺规则完全不变", y=1.02)
    save(fig, "fig20_rh_depth.png")


'''

F13 = '''def f13_p3_soc():
    """问题三日边界储电量（仅供人工查看，数据正确但信息量低，未列入论文）。"""
    s = load_json(SOL03 / "solution.json")["daily"]
    st = np.array(s["state_start_kwh"], float)
    en = np.array(s["state_end_kwh"], float)
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 3.4))
    axes[0].plot(np.arange(len(en)), en, color="#00897b", lw=1.0, label="日末储电量")
    axes[0].plot(np.arange(len(st)), st, color="#6a1b9a", lw=1.0, label="日初储电量")
    axes[0].axhline(1200, color="#c62828", ls="--", lw=1.0, label="储电量下限 1200 kWh")
    axes[0].set_xlabel("日期序号（0 = 2025-01-01）")
    axes[0].set_ylabel("储电量 / kWh")
    axes[0].legend(fontsize=8)
    axes[0].set_title("全年日边界储电量（原始量纲，两条曲线重合于下限）")
    axes[1].hist(en - 1200.0, bins=20, color="#00897b")
    axes[1].set_xlabel("日末储电量 − 下限 / kWh")
    axes[1].set_ylabel("天数")
    axes[1].set_yscale("log")
    axes[1].set_title("日末储电量偏离下限的分布（365 天全部为 0）")
    fig.suptitle("问题三：日边界储电量恒为下限，属“单日决策 + 终端自由”结构的涌现结果", y=1.02)
    save(fig, "fig13_p3_soc.png")


'''


def splice(src: str, start_marker: str, end_marker: str, new_text: str) -> str:
    i = src.index(start_marker)
    j = src.index(end_marker)
    assert i < j, (start_marker, end_marker)
    return src[:i] + new_text + src[j:]


def main() -> None:
    src = P.read_text(encoding="utf-8")
    src = splice(src, "def f13_p3_soc():", "def f14_p4_price():", F13)
    src = splice(src, "def f20_rh_depth():", "def main() -> None:", F20)
    P.write_text(src, encoding="utf-8")
    print("patched f13 and f20")
    for probe in ("means = [1200.0", "days_at_floor = [365", '"前瞻 3 天及以上"'):
        print(probe, "->", probe in src)


if __name__ == "__main__":
    main()
