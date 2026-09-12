# -*- coding: utf-8 -*-
"""按正文实际引用顺序重建 paper/refs.tex（GB/T 7714 数字标注）。

只保留正文 \\cite 中出现的条目，编号顺序即首次引用顺序；未引用条目不再输出。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"
CIT = ROOT / "problems" / "microgrid_2025" / "citations.yaml"

CITE_RE = re.compile(r"\\cite\{([^}]*)\}")
BIB_RE = re.compile(r"\\bibitem\{(ref-[^}]+)\}\s*\n(.*)")


def cited_keys() -> list[str]:
    order: list[str] = []
    files = ["sec1_restate.tex", "sec2_analysis.tex", "sec3_assumptions.tex", "sec4_symbols.tex",
             "sec5_data.tex", "sec6_framework.tex", "sec7_prob1.tex", "sec8_prob2.tex",
             "sec9_prob3.tex", "sec10_prob4.tex", "sec11_robust.tex", "sec12_eval.tex"]
    for name in files:
        p = PAPER / name
        if not p.exists():
            continue
        for m in CITE_RE.finditer(p.read_text(encoding="utf-8")):
            for key in (k.strip() for k in m.group(1).split(",")):
                if key and key not in order:
                    order.append(key)
    return order


def clean(text: str) -> str:
    """去掉 DOI 与生成期说明性括注，使条目更紧凑（GB/T 7714 允许省略 DOI）。"""
    text = re.sub(r"\s*DOI:\s*\S+\.?\s*$", "", text.strip())
    text = re.sub(r"\s*（[^）]*Crossref[^）]*）\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text.endswith("."):
        text += "."
    return text


def main() -> None:
    entries: dict[str, str] = {}
    for m in BIB_RE.finditer((PAPER / "refs.tex").read_text(encoding="utf-8")):
        entries[m.group(1)] = m.group(2).strip()

    order = cited_keys()
    missing = [k for k in order if k not in entries]
    print("cited:", len(order), "| missing from bibliography:", missing)

    lines = ["% 参考文献（GB/T 7714；数字标注；按正文首次引用顺序排列）", "\\begin{thebibliography}{99}",
             "\\small"]
    for i, key in enumerate(order, start=1):
        lines.append(f"\\bibitem{{{key}}}")
        lines.append(clean(entries[key]))
    lines.append("\\end{thebibliography}")
    (PAPER / "refs.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote paper/refs.tex with", len(order), "entries")
    print("citations.yaml present:", CIT.exists())


if __name__ == "__main__":
    main()
