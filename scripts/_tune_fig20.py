# -*- coding: utf-8 -*-
"""微调 f20 图注字号与留白，并重新出图。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

P = ROOT / "scripts" / "build_paper_figures.py"
src = P.read_text(encoding="utf-8")
pairs = [
    ('xytext=(0, 3), ha="center", fontsize=7)', 'xytext=(0, 5), ha="center", fontsize=8)'),
    ("axes[1].set_ylim(0, 7600)", "axes[1].set_ylim(0, 8400)"),
]
for old, new in pairs:
    if old in src:
        src = src.replace(old, new)
        print("replaced:", old[:40])
P.write_text(src, encoding="utf-8")

import build_paper_figures as B  # noqa: E402

B.add_paths()
B.f20_rh_depth()
