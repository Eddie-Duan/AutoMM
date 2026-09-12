# -*- coding: utf-8 -*-
"""修 f20 图例单位（百万元 → 万元），重新出图并导出右图 2× 放大裁切，便于核对标签。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

P = ROOT / "scripts" / "build_paper_figures.py"
OLD = 'label="链 %s（前瞻 1 天基线 %.2f 百万元）" % (ch, cost[ch][0] / 1e7)'
NEW = 'label="链 %s（前瞻 1 天基线 %.0f 万元）" % (ch, cost[ch][0] / 1e4)'

src = P.read_text(encoding="utf-8")
if OLD in src:
    P.write_text(src.replace(OLD, NEW), encoding="utf-8")
    print("unit label fixed")
else:
    print("unit label already fixed:", NEW in src)

import build_paper_figures as B  # noqa: E402

B.add_paths()
B.f20_rh_depth()

from PIL import Image  # noqa: E402

im = Image.open(ROOT / "paper" / "figs" / "fig20_rh_depth.png")
w, h = im.size
im.crop((int(w * 0.48), 0, w, h)).resize((int(w * 0.52 * 2.2), int(h * 2.2)), Image.LANCZOS).save(
    ROOT / ".tmp" / "fig20_right_zoom.png")
print("zoom saved; original size", im.size)
