"""`scripts/build_paper.py` 的回归测试（真实缺陷修复，2026-09-12）。

背景：`reports/paper/draft_paper.md` 的正文引用了题面，而题面自带
`## 附录 1 储能设备的参数` / `## 附录 2 附件说明` 等同形标题；校验器原先用
`APPENDIX_HEADING_RE.search` 定位「附录起点」，一旦命中这些同形标题，就会把
正文（数据与假设、四问总结、敏感性/鲁棒性与消融、模型评价）整段划成"附录之前"，
使占位符检查漏检 `> 待撰写`（带附录的稿子因此永远判 PASS）；同时 `{{`/`}}`
的粗暴检查会命中公式里的 `\\Bigr\\}` 与附录内联源码里的 f-string 转义，使
带附录的稿子永远判 NEEDS_REVISION（`final` 不可达）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT / "scripts"))

from build_paper import (  # noqa: E402
    PLACEHOLDER_RE,
    find_appendix_start,
    splice_appendix,
)


def test_find_appendix_start_ignores_problem_statement_appendix_headings() -> None:
    """题面里的 `## 附录 1` / `## 附录 2` 不能被当成论文附录。"""
    text = (
        "## 摘要\n\n正文。\n\n"
        "## 附录 1 储能设备的参数\n\n储能最大容量 12000 kWh。\n\n"
        "## 附录 2 附件说明\n\n附件 1…\n\n"
        "## 8 模型评价与不足\n\n> 待撰写。\n\n"
        "## AI 工具使用声明\n\n声明。\n\n"
        "## 参考文献\n\n[1] …\n\n"
        "## 附录\n\n### 附录 A 支撑材料文件列表\n\n| 文件 | 字节 |\n|---|---|\n\n"
        "### 附录 B 建模源程序代码\n\n```python\nprint('ok')\n```\n"
    )
    start = find_appendix_start(text)
    assert start is not None
    body = text[:start]
    assert "## 8 模型评价与不足" in body, "正文（含第 8 章）必须在附录之前"
    assert "> 待撰写。" in body, "附录起点不得把第 8 章的待写占位符划到正文之外"
    assert "### 附录 A 支撑材料文件列表" not in body


def test_find_appendix_start_without_real_appendix_returns_none() -> None:
    """没有论文附录时不能把题面同形标题当附录。"""
    text = "## 摘要\n\n正文\n\n## 附录 1 储能设备的参数\n\n参数…\n"
    assert find_appendix_start(text) is None


def test_placeholder_regex_flags_template_placeholders_only() -> None:
    """只标记真正的待写占位符，不误伤公式与代码。"""
    assert PLACEHOLDER_RE.search("> 待 paper-writer 撰写摘要。")
    assert PLACEHOLDER_RE.search("> 待撰写。")
    assert PLACEHOLDER_RE.search("## 摘要\n\n{{ABSTRACT}}\n")
    # 公式里的 `\Bigr\}`、f-string 转义、中文引号包裹都不应命中
    assert not PLACEHOLDER_RE.search(r"\\sum_{\\tau}\\Bigl(p_{\\tau}b_{\\tau}\\Bigr),")
    assert not PLACEHOLDER_RE.search('f"m 必须属于 {{0,6,12,18}}"')
    assert not PLACEHOLDER_RE.search("待团队选定的决策点")


def test_splice_appendix_is_idempotent(tmp_path: Path) -> None:
    """重复调用 `splice_appendix` 不得产生多份附录，也不得截掉正文。"""
    draft = tmp_path / "draft.md"
    draft.write_text(
        "## 摘要\n\n正文。\n\n"
        "## 附录 2 附件说明\n\n附件 1…\n\n"
        "## 8 模型评价与不足\n\n评价。\n\n"
        "## AI 工具使用声明\n\n声明。\n\n"
        "## 参考文献\n\n[1] …\n\n"
        "## 附录\n\n### 附录 A 支撑材料文件列表\n\n"
        "| 文件 | 字节 |\n|---|---|\n| `a.md` | 1 |\n\n"
        "### 附录 B 建模源程序代码\n\n```python\nprint(1)\n```\n",
        encoding="utf-8",
    )
    appendix = "## 附录\n\n### 附录 A 支撑材料文件列表\n\n| 文件 | 字节 |\n|---|---|\n| `a.md` | 1 |\n\n### 附录 B 建模源程序代码\n\n```python\nprint(1)\n```\n"
    splice_appendix(draft, appendix)
    splice_appendix(draft, appendix)
    text = draft.read_text(encoding="utf-8")
    # splice_appendix 是「替换式拼接」：正文保留，附录恰好一份（第二次调用不得追加第二份）
    assert text.count("## 附录\n") == 1, "附录标题只允许出现一次"
    assert text.count("### 附录 A 支撑材料文件列表") == 1, "附录不得出现两份"
    assert "## 8 模型评价与不足" in text, "正文第 8 章必须保留"
    assert text.index("## 8 模型评价与不足") < text.index("## 附录\n"), "第 8 章在附录之前"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
