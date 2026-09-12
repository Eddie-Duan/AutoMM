# -*- coding: utf-8 -*-
"""定点复核：论文表格/正文中引用的对照数值与派生量是否在产物中有出处。"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
B = ROOT / "problems" / "microgrid_2025"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


comp = load(B / "prob02/versions/assumption_v001/ablations/results/prob02_v001_ablation_run001/comparison.json")
models = {m["label"]: m for m in comp["models"]}
caps = {c["label"]: c for c in comp["purchase_cap"]}

print("--- 问题二模型族对照（论文表 9） ---")
for lab in ("M1", "M7", "M2a", "M2b", "M4", "M5", "M3_full"):
    m = models.get(lab)
    if m:
        print(f"{lab:8s} {m['objective_yuan']:18.6f}  feasible={m['feasible']}  time={m.get('solve_time_seconds')}")
print("购电上限档位：")
for lab, c in caps.items():
    print(f"{lab:12s} cap={c['b_cap_kw']:8.2f} kW  Σq_em={c['q_em_kwh']:16.6f}  C={c['objective_yuan']:18.6f}")

print("\n--- 问题三对照（论文表 11） ---")
ab3 = load(B / "prob03/versions/assumption_v001/ablations/results/prob03_v001_ablation_run001/comparison.json") \
    if (B / "prob03/versions/assumption_v001/ablations/results/prob03_v001_ablation_run001/comparison.json").exists() else None
if ab3:
    for m in ab3.get("models", [])[:14]:
        print(f"{m.get('label'):22s} {m.get('objective_yuan')}  Δ={m.get('delta_vs_baseline_yuan')}")

print("\n--- prob02 解析界（论文 5.4.3） ---")
sol2 = load(B / "prob02/versions/assumption_v001/results/prob02_v001_f001_run002/solution.json")
for chk in sol2.get("checks", []):
    if any(k in str(chk.get("name", "")) for k in ("bound", "analytic", "cost_range", "objective")):
        print(" ", chk)

print("\n--- 交付期净负荷（论文 5.1.2：四问逐位相同） ---")
import sys
sys.path.insert(0, str(B / "prob03/versions/assumption_v001/code"))
import prob03_io  # noqa: E402

a2 = prob03_io.read_attachment2(ROOT / "data" / "附件2.xlsx")
net = (a2.load_kw - a2.pv_kw) * (1 / 6.0)
print("全期净负荷        = %.6f kWh" % net.sum())
print("交付期(第 31..364 天) = %.6f kWh" % net[31:365].sum())
print("prob02 登记: 全期 %.6f | 交付期 %.6f" % (
    sol2["totals"]["net_load_kwh"], sol2["totals"]["net_load_delivery_kwh"]))

print("\n--- 附件 4 统计事实（论文 5.1.1） ---")
import prob04_io  # noqa: E402  (pip 路径已加入)

a4 = prob04_io.read_attachment4_price(ROOT / "data" / "附件4.xlsx")
p = np.asarray(a4.price, dtype=float)
print("min %.4f max %.4f mean %.7f | <0.10 %d 格 | <0.05 %d 格" % (
    p.min(), p.max(), p.mean(), int((p < 0.10).sum()), int((p < 0.05).sum())))
print("日均价范围 %.4f ~ %.4f" % (p.mean(axis=1).min(), p.mean(axis=1).max()))
print("同时段跨日均值曲线与附件1相关性：", end="")
a1 = prob03_io.read_attachment1(ROOT / "data" / "附件1.xlsx")
c = np.corrcoef(p.mean(axis=0), np.asarray(a1.price, dtype=float))[0, 1]
print("%.10f | 极值 附件4 %.4f/%.4f, 附件1 %.4f/%.4f" % (
    c, p.mean(axis=0).min(), p.mean(axis=0).max(),
    np.asarray(a1.price).min(), np.asarray(a1.price).max()))
