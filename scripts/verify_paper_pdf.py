# -*- coding: utf-8 -*-
"""校验最终 PDF：页数、正文引用编号的压缩写法、以及被改动的那一句。

用 pypdf 抽取中文文本；逐页 try/except，避开附录中 listings 生成的复杂内容流。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from pypdf import PdfReader

sys.stdout.reconfigure(encoding="utf-8")

pdf = Path(sys.argv[1] if len(sys.argv) > 1 else ".tmp/verify_snapshot.pdf")
r = PdfReader(str(pdf), strict=False)
n = len(r.pages)
print("PDF:", pdf, "| 总页数", n)


def text_of(i: int) -> str:
    try:
        return r.pages[i].extract_text() or ""
    except Exception:  # noqa: BLE001
        return ""


SCAN = min(45, n)
pages = [text_of(i) for i in range(SCAN)]

app = None
for i, t in enumerate(pages):
    if "附录 A" in t and "支撑材料" in t:
        app = i + 1
        break
if app is None:
    print("!! 前 %d 页未定位到附录起始页" % SCAN)
    app = SCAN + 1
print("附录起始页", app, "=> 摘要页 + 正文（含参考文献） =", app - 1)

body_flat = re.sub(r"\s+", "", "".join(pages[: app - 1]))
cites = re.findall(r"\[[0-9][0-9,\- ]*\]", body_flat)
print("正文引用出现次数:", len(cites))
print("压缩为区间的写法:", sorted(set(c for c in cites if "-" in c)))
print("仍为逗号列表的:", sorted(set(c for c in cites if "," in c)))

i = body_flat.find("对调度结果的影响")
print("原句:", body_flat[max(0, i - 36): i + 46] if i >= 0 else "(未找到)")

refs_flat = re.sub(r"\s+", "", "".join(pages[max(0, app - 7): app - 1]))
j = refs_flat.find("[1]")
print("参考文献前 120 字:", refs_flat[j: j + 120] if j >= 0 else "(未找到参考文献表)")
for k in (28, 29, 30):
    pos = refs_flat.find("[%d]" % k)
    print("  [%d] ->" % k, refs_flat[pos + 3: pos + 70] if pos >= 0 else "(未找到)")
