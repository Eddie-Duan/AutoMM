# 论文构建说明与工具修复登记（2026-09-12）

本文件记录本次把 AutoMM 推进到"可用论文"的过程中，对 `scripts/build_paper.py` 的**两处 bug 修复**、
完整构建链路、当前产物状态与"终稿待批准"的确切要求。**不改动任何小问的假设 / 公式 / 结果 / 结论。**

## 1. 本次修复的两个 bug（均为原始代码问题，最小改动）

### BUG-1：`splice_appendix()` 会**整段吃掉论文正文**

- **现象**：`python scripts/build_paper.py draft --with-appendix` 生成的文件里，
  "数据与建模假设 / 四问章节 / 敏感性-鲁棒性-消融 / 模型评价"**全部消失**，只剩摘要、§1 与附录（1,048,484 B）。
- **根因**：原实现用 `marker = "\n## 附录"` 查找既有附录位置；而**题面引文本身**含
  `## 附录 1 储能设备的参数` 与 `## 附录 2 附件说明`，`text.index(marker)` 命中前者，
  于是把从该处到末尾的**全部正文截断**再拼附录。
- **修复**：新增 `APPENDIX_HEADING_RE = re.compile(r"(?m)^## 附录[ \t]*\r?$")`，
  只匹配**独占一行的 `## 附录`**（并容错 CRLF 行尾）；幂等性保持（重复调用不会产生多份附录）。
- **验证**：修复后 `draft --with-appendix` = **1,540,847 B / 26,000+ 行 / 53 个二级标题**，
  四问章节（`## 3 prob01` … `## 6 prob04`）与附录**同时**在位。

### BUG-2：`validate()` 的 `{{` 占位符检查**误伤附录内联源码**，使终稿不可达

- **现象**：附录会内联全部建模源程序，其中合法的 Python f-string 转义（如
  `raise ValueError(f"m 必须属于 {{0,6,12,18}}，收到 {m}")`）会被 `"{{" in text` 判为"待写占位符"
  ⇒ **带附录的稿永远无法 PASS**，`final` 分支因此不可达。
- **修复**：占位符检查**只扫正文**（`APPENDIX_HEADING_RE` 之前的正文段），附录检查（支撑材料列表、
  内联源码）保持原样。
- **验证**：`python scripts/build_paper.py validate` → `status = PASS`、`errors = []`。

## 2. 完整构建链路（本次实际执行）

| 步骤 | 命令 / 产物 | 结果 |
|---|---|---|
| 小问总结（3 份缺失交付件） | 由项目自身 agent 运行时 `dsh --profile headless`（`tools_mode: native`）按 `knowledge/question-summary.md` + `wiki/summaries-archives.md` 撰写 | `prob02` 44,690 B / `prob03` 35,815 B / `prob04` 40,084 B |
| 整题摘要门禁 | `python scripts/build_final_summary.py` | `reports/final_summary.md` **174,308 B** + 归档副本；`problem_state.summary_status = built` |
| 论文草稿 | `python scripts/build_paper.py draft --with-appendix` | `reports/paper/draft_paper.md` **1,540,847 B** |
| 论文校验 | `python scripts/build_paper.py validate` | **PASS**：`errors = []`、`included_figure_count = 33`、`citation_ids_used = 97`；`problem_state.paper_status = draft_ready` |
| 支撑材料 | `python scripts/build_ai_usage_detail.py` | `reports/support/AI 工具使用详情.pdf` 65,982 B + `.md` 4,387 B |

## 3. 终稿（`reports/paper/final_paper.md`）为何需要人工批准

`build_paper.py final` 的硬性前置（**没有任何脚本会代替人设置**，属设计内的人门禁）：

1. `problems/microgrid_2025/problem_state.json` 的 `paper_status` 必须为 `"approved"`；
2. 存在批准记录文件（`{"command": "APPROVE", "request_id": "…"}`），可用 `--approval-file` 指定；
3. 该次校验必须 `PASS`（现已满足）。

满足 1–2 后执行：

```powershell
.venv\Scripts\python.exe scripts/build_paper.py final --approval-file "<批准记录路径>"
```

生成 `reports/paper/final_paper.md` 并把 `paper_status` 置为 `finalized`。

## 4. 遗留事项（不阻塞现在这份草稿）

- `problem_state.completion_notification = pending`：整题完成回执尚未发送（需一次 runner 唤醒执行 P8 动作）。
- `config/notifications.yaml` 中 SMTP 口令以**明文**存放；建议改为仅用环境变量
  `AUTOMM_SMTP_PASSWORD`（配置中已声明该键）并轮换口令。
- 本文件所述两处修复应同步进项目变更记录（`RELEASE_PROVENANCE.md`）后再发布。
