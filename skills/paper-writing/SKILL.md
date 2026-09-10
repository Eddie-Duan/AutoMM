---
name: paper-writing
description: 在全局检查通过且人类确认后生成最终 Markdown 论文。
---

# Paper Writing

本 Skill 在初版本中禁用。当前终态只构建 `reports/final_summary.md`，不创建 draft/final 论文，
也不等待 APPROVE/REJECT/REVISE。以下内容仅保留为后续版本设计草案。

## Draft Gate

所有小问 locally completed；最终 sanity 为 PASS/WARN；条件性阶段完成或有跳过理由；Level 5 通过；引用双向闭合；图表清单完整。

## Draft

读取模板、风格样本和接受版本材料，生成 `draft_paper.md`。统一符号、公式和图表编号；按 GB/T 7714 组织引用；关键文献加 `[待人工复核]`。同时生成论文检查报告。

## AI 工具使用声明

按《全国大学生数学建模竞赛人工智能工具使用规定（2026年试行）》第 3 条，在论文「参考文献」之前设置「AI 工具使用声明」，两种表述二选一（未使用 / 使用了并简述用途 + 指向支撑材料）。使用 AI 工具时，支撑材料须含 PDF《AI 工具使用详情.pdf》，写明工具名称与版本、使用目的和环节、主要提示方式与过程、人工修改与核验情况（语言润色除外）。上述字段由 `config/paper.yaml` 的 `ai_declaration` 配置驱动。

## 授权

发送带唯一 request ID 的邮件。只接受允许发件人、同一线程、未处理 message ID 的 APPROVE/REJECT/REVISE。等待期间暂停其他研究动作。

## Final

APPROVE 后才写 final；REVISE 回论文修订；REJECT 保留 draft 和材料。final 生成失败必须保留 draft，不伪装完成。
