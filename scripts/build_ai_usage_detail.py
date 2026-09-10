"""生成支撑材料《AI 工具使用详情.pdf》。

依据《全国大学生数学建模竞赛人工智能工具使用规定（2026 年试行）》第 4 条：使用 AI 工具的参赛
作品，应在支撑材料中包含 PDF 格式的说明文件（文件名固定为「AI 工具使用详情.pdf」），内容包括：

  （1）所用 AI 工具名称、版本或型号；
  （2）具体使用目的和环节；
  （3）主要提示方式与使用过程说明（可附典型交互示例）；
  （4）对 AI 输出的采纳、人工修改和核验的主要情况（语言润色除外）。

内容来源为 `config/paper.yaml` 的 `ai_declaration.detail`；其中 `{key}` 占位符由运行环境自动
填充，未知占位符直接报错，避免带着未填项提交。脚本同时写出同名 Markdown，便于人工校对与版本对比。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from automm.common import ROOT, read_yaml, relative, resolve_project_path, utc_now, write_text

PLACEHOLDER_RE = re.compile(r"\{([a-z0-9_]+)\}")
FONT_CANDIDATES = (
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/Deng.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
)

SECTIONS = (
    ("一、所用 AI 工具名称、版本或型号", "tools"),
    ("二、具体使用目的和环节", "purposes"),
    ("三、主要提示方式与使用过程说明", "prompting"),
    ("四、对 AI 输出的采纳、人工修改和核验情况", "review"),
)


def _run(command: list[str], timeout: int = 20) -> str:
    executable = shutil.which(command[0])
    if not executable:
        return ""
    try:
        result = subprocess.run(
            [executable, *command[1:]],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip().splitlines()[0].strip() if result.stdout else ""


def _dsh_model() -> str:
    settings = Path.home() / ".dsh" / "settings.yaml"
    if not settings.is_file():
        return ""
    try:
        value = read_yaml(settings)
    except Exception:
        return ""
    model = (value.get("agent-default-model") or {}).get("model")
    return str(model) if model else ""


def _torch_version() -> str:
    if not importlib.util.find_spec("torch"):
        return "未使用"
    try:
        import torch  # noqa: PLC0415 - 仅在需要时导入

        return f"{torch.__version__}（CUDA 可用：{torch.cuda.is_available()}）"
    except Exception:
        return "未采集到"


def collect_facts() -> dict[str, str]:
    return {
        "python_version": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()}（{platform.machine()}）",
        "dsh_version": _run(["dsh", "--version"]) or "未采集到",
        "dsh_model": _dsh_model() or "未采集到",
        "torch_version": _torch_version(),
        "generated_at": utc_now(),
    }


def substitute(value: Any, facts: dict[str, str], where: str) -> str:
    text = str(value)

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in facts:
            raise SystemExit(f"{where} 使用了未知占位符 {{{key}}}；可用占位符：{', '.join(sorted(facts))}")
        return facts[key]

    return PLACEHOLDER_RE.sub(replace, text)


def build_document(config: dict[str, Any], facts: dict[str, str]) -> dict[str, Any]:
    item = config.get("ai_declaration") or {}
    if not item.get("used", True):
        raise SystemExit(
            "ai_declaration.used 为 false：未使用 AI 工具时无需生成《AI 工具使用详情.pdf》，"
            "只需在论文中保留未使用声明。"
        )
    detail = item.get("detail") or {}
    for field in ("tools", "purposes", "prompting", "review"):
        if not detail.get(field):
            raise SystemExit(f"config/paper.yaml 的 ai_declaration.detail.{field} 不能为空（规定第 4 条要求）。")

    tools = []
    for index, entry in enumerate(detail["tools"], 1):
        for field in ("name", "version", "role"):
            if not entry.get(field):
                raise SystemExit(f"ai_declaration.detail.tools[{index}] 缺少字段 {field}")
        tools.append(
            {
                "name": substitute(entry["name"], facts, f"tools[{index}].name"),
                "version": substitute(entry["version"], facts, f"tools[{index}].version"),
                "role": substitute(entry["role"], facts, f"tools[{index}].role"),
            }
        )

    examples = [
        {
            "label": substitute(entry["label"], facts, "examples.label"),
            "text": substitute(entry["text"], facts, "examples.text"),
        }
        for entry in detail.get("examples") or []
    ]
    if examples:
        examples[-1]["is_last"] = True

    return {
        "title": substitute(detail.get("title", "AI 工具使用详情"), facts, "title"),
        "subtitle": substitute(detail.get("subtitle", ""), facts, "subtitle"),
        "lead": substitute(
            detail.get(
                "lead",
                "本参赛队在竞赛过程中使用了 AI 工具，核心建模与分析由参赛队主导，"
                "以下按《全国大学生数学建模竞赛人工智能工具使用规定（2026 年试行）》第 4 条逐项说明。",
            ),
            facts,
            "lead",
        ),
        "tools": tools,
        "purposes": [substitute(item, facts, "purposes") for item in detail["purposes"]],
        "prompting": [substitute(item, facts, "prompting") for item in detail["prompting"]],
        "examples": examples,
        "review": [substitute(item, facts, "review") for item in detail["review"]],
        "environment": [
            f"Python {facts['python_version']}",
            f"操作系统 {facts['platform']}",
            f"Agent 运行时 dsh {facts['dsh_version']}",
            f"底层模型 {facts['dsh_model']}",
            f"PyTorch {facts['torch_version']}",
        ],
        "generated_at": facts["generated_at"],
    }


def render_markdown(document: dict[str, Any]) -> str:
    lines = [f"# {document['title']}", "", f"_{document['subtitle']}_", "", document["lead"], ""]
    for heading, key in SECTIONS:
        lines += [f"## {heading}", ""]
        if key == "tools":
            for entry in document["tools"]:
                lines += [f"- **{entry['name']}**", f"  - 版本或型号：{entry['version']}", f"  - 用途：{entry['role']}"]
        elif key == "prompting":
            lines += [f"- {item}" for item in document["prompting"]]
            if document["examples"]:
                lines += ["", "**典型交互示例**", ""]
                for entry in document["examples"]:
                    lines += [f"- {entry['label']}：{entry['text']}"]
        else:
            lines += [f"- {item}" for item in document[key]]
        lines.append("")
    lines += ["## 附：生成环境", "", *[f"- {item}" for item in document["environment"]], f"- 生成时间 {document['generated_at']}", ""]
    return "\n".join(lines)


def render_pdf(document: dict[str, Any], output: Path, font_path: Path) -> None:
    from fpdf import FPDF  # noqa: PLC0415 - 仅在生成 PDF 时导入

    pdf = FPDF(format="A4")
    pdf.set_margins(22, 20, 22)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_font("cjk", "", str(font_path))
    pdf.add_page()

    def line(text: str, size: int, *, gap: float = 0.0, indent: float = 0.0) -> None:
        pdf.set_font("cjk", size=size)
        pdf.set_x(pdf.l_margin + indent)
        pdf.multi_cell(0, size * 0.62, text, new_x="LMARGIN", new_y="NEXT")
        if gap:
            pdf.ln(gap)

    line(document["title"], 18, gap=1)
    if document["subtitle"]:
        line(document["subtitle"], 11, gap=4)
    line(document["lead"], 10.5, gap=4)

    for heading, key in SECTIONS:
        line(heading, 13, gap=2)
        if key == "tools":
            for entry in document["tools"]:
                line(f"· {entry['name']}", 10.5)
                line(f"    版本或型号：{entry['version']}", 10.5)
                line(f"    用途：{entry['role']}", 10.5, gap=1.5)
        elif key == "prompting":
            for item in document["prompting"]:
                line(f"· {item}", 10.5)
            if document["examples"]:
                line("典型交互示例", 10.5, gap=1.5)
                for entry in document["examples"]:
                    line(f"· {entry['label']}：{entry['text']}", 10.5, gap=1.5)
        else:
            for item in document[key]:
                line(f"· {item}", 10.5)
        pdf.ln(3)

    line("附：生成环境", 13, gap=2)
    for item in document["environment"]:
        line(f"· {item}", 10.5)
    line(f"· 生成时间 {document['generated_at']}", 10.5)

    output.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output))


def resolve_font(detail: dict[str, Any]) -> Path:
    candidates = [detail.get("font"), *FONT_CANDIDATES]
    for candidate in candidates:
        if candidate and Path(str(candidate)).is_file():
            return Path(str(candidate))
    raise SystemExit("未找到可用的中文字体；请在 ai_declaration.detail.font 指定一个 TTF/TTC 路径。")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成支撑材料《AI 工具使用详情.pdf》")
    parser.add_argument("--output", help="覆盖 config/paper.yaml 中的 ai_declaration.detail.output")
    parser.add_argument("--facts-only", action="store_true", help="只打印自动采集的环境信息，不生成文件")
    args = parser.parse_args()

    facts = collect_facts()
    if args.facts_only:
        print(json.dumps(facts, ensure_ascii=False, indent=2))
        return

    config = read_yaml(ROOT / "config" / "paper.yaml")
    detail = (config.get("ai_declaration") or {}).get("detail") or {}
    document = build_document(config, facts)

    output = resolve_project_path(args.output or detail.get("output", "reports/support/AI 工具使用详情.pdf"))
    if output.name != "AI 工具使用详情.pdf":
        raise SystemExit("文件名必须为「AI 工具使用详情.pdf」（规定第 4 条）。")
    font_path = resolve_font(detail)
    render_pdf(document, output, font_path)

    markdown_output = resolve_project_path(detail.get("markdown_output", "reports/support/AI 工具使用详情.md"))
    write_text(markdown_output, render_markdown(document))

    print(
        json.dumps(
            {
                "pdf": relative(output),
                "markdown": relative(markdown_output),
                "bytes": output.stat().st_size,
                "font": str(font_path),
                "generated_at": document["generated_at"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
