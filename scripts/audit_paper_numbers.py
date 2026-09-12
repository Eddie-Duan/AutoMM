# -*- coding: utf-8 -*-
"""复核：把论文正文中出现的每个关键数字与已落盘产物逐项对账。

做法：从 paper/sec*.tex 中抽取“数字声明”（形如 13\\,758\\,182.573724），
与产物 JSON 中的目标值集合做比对，报告不一致项。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
B = ROOT / "problems" / "microgrid_2025" / "paper"  # 占位，真正路径在下面
B = ROOT / "problems" / "microgrid_2025"
PAPER = ROOT / "paper"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def collect_numbers(obj, out: set[float], depth: int = 0) -> None:
    if depth > 4:
        return
    if isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj[:2000]:
            collect_numbers(v, out, depth + 1)
    elif isinstance(obj, float):
        out.add(round(obj, 9))


def main() -> None:
    src: set[float] = set()
    files = [
        B / "prob01/versions/assumption_v003/results/prob01_v003_f001_run002/solution.json",
        B / "prob01/versions/assumption_v003/results/prob01_v003_f001_run002/run_manifest.json",
        B / "prob02/versions/assumption_v001/results/prob02_v001_f001_run002/solution.json",
        B / "prob02/versions/assumption_v001/results/prob02_v001_f001_run002/run_manifest.json",
        B / "prob03/versions/assumption_v001/results/prob03_v001_f001_run003/solution.json",
        B / "prob03/versions/assumption_v001/results/prob03_v001_f001_run003/tables.json",
        B / "prob04/versions/assumption_v001/results/prob04_v001_f001_4-2_run002/solution.json",
        B / "prob04/versions/assumption_v001/results/prob04_v001_f001_4-3_run002/solution.json",
        B / "prob04/versions/assumption_v001/results/prob04_v001_f001_4-2_run002/forecast_backtest.json",
        B / "prob04/versions/assumption_v001/ablations/results/prob04_v001_ablation_4-2_run003/criteria.json",
        B / "prob02/versions/assumption_v001/ablations/results/prob02_v001_ablation_run001/comparison.json",
    ]
    for f in files:
        if f.exists():
            collect_numbers(load(f), src)
    print("source numbers collected:", len(src))

    # 论文中的数字：形如 13\,758\,182.573724 / 35126.948589 / 4.86\times10^{-13}
    txt = "\n".join((PAPER / n).read_text(encoding="utf-8")
                    for n in sorted(p.name for p in PAPER.glob("sec*.tex")))
    raw = re.findall(r"\d[\d\\,\s]*\.\d+", txt)
    checked = mismatched = 0
    bad: list[str] = []
    for token in raw:
        norm = token.replace("\\,", "").replace(" ", "").replace("\n", "")
        try:
            val = float(norm)
        except ValueError:
            continue
        if val < 1000:  # 只复核大额金额/电量，避免与阈值、系数混淆
            continue
        checked += 1
        if round(val, 9) not in src:
            mismatched += 1
            bad.append(norm)
    print(f"checked large numbers: {checked}, not found verbatim in artifacts: {mismatched}")
    for b in sorted(set(bad))[:40]:
        print("   ", b)

    # 关键恒等式与差额
    s2 = load(B / "prob02/versions/assumption_v001/results/prob02_v001_f001_run002/solution.json")
    s3 = load(B / "prob03/versions/assumption_v001/results/prob03_v001_f001_run003/solution.json")
    d42 = load(B / "prob04/versions/assumption_v001/results/prob04_v001_f001_4-2_run002/solution.json")["delivery"]
    d43 = load(B / "prob04/versions/assumption_v001/results/prob04_v001_f001_4-3_run002/solution.json")["delivery"]
    print("\n--- 关键恒等式复核 ---")
    print("问题三 vs 问题二 交付期差额 = %.2f 元 (相对 %.3f%%)" % (
        s3["delivery"]["cost_total_yuan"] - s2["delivery_cost_yuan"],
        100 * (s3["delivery"]["cost_total_yuan"] / s2["delivery_cost_yuan"] - 1)))
    print("问题二 全期 = 交付期 + 1 月: %.6f" % (
        s2["delivery_cost_yuan"] + s2["january_cost_yuan"] - s2["objective_yuan"]))
    tot = d43["cost_plan_yuan"] + d43["cost_adj_yuan"] + d43["cost_em_yuan"] - d43["cost_total_yuan"]
    print("链 4-3 三项之和 - 总费用 = %.6f 元" % tot)
    diff = d43["cost_total_yuan"] - d42["cost_total_yuan"]
    parts = (d43["cost_plan_yuan"] - d42["cost_plan_yuan"]) + d43["cost_adj_yuan"] + d43["cost_em_yuan"]
    print("两链差额 %.9f vs 三分项之和 %.9f (残差 %.2e)" % (diff, parts, diff - parts))
    print("净负荷一致：prob02 %.9f | prob03 %.9f | 4-2 %.9f | 4-3 %.9f" % (
        s2["totals"]["net_load_delivery_kwh"], s3["totals"]["net_load_kwh"],
        load(B / "prob04/versions/assumption_v001/results/prob04_v001_f001_4-2_run002/solution.json")["totals"]["net_load_kwh"],
        load(B / "prob04/versions/assumption_v001/results/prob04_v001_f001_4-3_run002/solution.json")["totals"]["net_load_kwh"]))


if __name__ == "__main__":
    main()
