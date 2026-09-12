# -*- coding: utf-8 -*-
"""核对问题三“日边界储电量”图的底层数据。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sol = json.loads((ROOT / "problems/microgrid_2025/prob03/versions/assumption_v001/"
                  "results/prob03_v001_f001_run003/solution.json").read_text(encoding="utf-8"))
d = sol["daily"]
st = np.asarray(d["state_start_kwh"], dtype=float)
en = np.asarray(d["state_end_kwh"], dtype=float)
ser = np.asarray(sol["series"]["storage_kwh"], dtype=float)

print("天数:", len(st))
print("日初 state_start: 第0天 = %.6f，第1天起唯一取值 = %s（共 %d 天）" % (
    st[0], sorted(set(np.round(st[1:], 6))), len(st) - 1))
print("日末 state_end  : 唯一取值 = %s（共 %d 天）" % (sorted(set(np.round(en, 6))), len(en)))
print("E_{d,144} 贴下限(1200) 天数 = %d / %d" % (int(np.isclose(en, 1200.0, atol=1e-4).sum()), len(en)))
print("Σ|E_{d,144}-1200| = %.6e kWh" % np.abs(en - 1200.0).sum())
print("时段级储电量 storage_kwh: min %.4f  max %.4f  唯一取值数 %d" % (
    ser.min(), ser.max(), len(np.unique(np.round(ser, 4)))))
print("日内波动幅度（每日 max-min）: 中位数 %.1f kWh，最大 %.1f kWh" % (
    np.median([ser[i * 144:(i + 1) * 144].max() - ser[i * 144:(i + 1) * 144].min() for i in range(365)]),
    max(ser[i * 144:(i + 1) * 144].max() - ser[i * 144:(i + 1) * 144].min() for i in range(365))))
print("日末 E_{d,144} 的均值 %.6f，标准差 %.6e" % (en.mean(), en.std()))
