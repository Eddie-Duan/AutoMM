# 论文校验报告（`reports/paper/draft_paper.md`）

> 生成者：paper-writer 角色（本任务直接驱动）。生成时间：2026-09-12。
> 输入：`config/paper.yaml`、`templates/paper_template.md`、`request/problem.md`、
> 四问 accepted 版本（`assumption_v00*` + `formulation_v001` + `question_summary.md`
> + `robustness/report.md` + `ablations/report.md`）、`problems/microgrid_2025/figures.yaml`、
> `problems/microgrid_2025/citations.yaml`、`reports/cross_question_review.md`。

---

## 1. 校验结论

| 项 | 结果 |
|---|---|
| `scripts/build_paper.py validate --draft reports/paper/draft_paper.md` | **PASS**（`errors = []`） |
| 交付图表数（`included_in_paper = true`） | **33**（prob01 7 / prob02 9 / prob03 8 / prob04 9） |
| 正文引用 ID 数 / registry 条数 | **97 / 97**（双向闭合，无悬空、无未引用） |
| 正文占位符 | **0**（无 `> 待`、无 `{{NAME}}`、无「待 paper-writer」） |
| 附录 A 支撑材料文件列表 | 存在（`reports/support/` 下 2 个文件） |
| 附录 B 建模源程序代码 | 存在（22 个 `.py`，覆盖四问 `code/`、`robustness/code/`、`ablations/code/`） |
| AI 工具使用声明位置与表述 | 位于「参考文献」之前，采用规定第 3 条第（2）项表述 |
| 结构自检（`.tmp/check_paper.py`） | **0 失败 / 25 项检查** |
| 关键数值抽样复核（`.tmp/verify_numbers.py`） | **0 失败 / 10 项**，正文数字与 accepted `solution.json` 逐字一致 |

**关键数值抽样复核明细**（正文数字直接取自 accepted 产物，未重算）：

| 量 | 正文值 | 出处 |
|---|---|---|
| 问题一全天购电费 | 35,126.948589 元 | `prob01/.../run002/solution.json` → `objective_yuan` |
| 问题二全期总费用 | 13,758,182.573724 元 | `prob02/.../run002/solution.json` |
| 问题三全期总费用 | 16,179,176.145228 元 | `prob03/.../run003/solution.json` |
| 链 `4-2` 全期总费用 | 14,755,884.322036 元 | `prob04/.../4-2_run002/solution.json` |
| 链 `4-3` 全期总费用 | 17,181,202.515506 元 | `prob04/.../4-3_run002/solution.json` |
| `C-ANCHOR-P03` 复现 prob03 全期/交付期 | 16,179,176.145228 / 14,540,616.335652 元 | `.../4-3_run003/C-ANCHOR-P03/summary.json` |
| 交付期两链差额及其三分项 | 2,282,639.673590 = 100,230.446225 + 522,512.788776 + 1,659,896.438588 元 | 两链 `solution.json`（残差 ≤1e-6） |

---

## 2. 本轮补全的内容（相对上一版草稿）

上一版草稿的 `validate` 结果为 `NEEDS_REVISION`，错误 6 项（正文占位符、附录缺文件列表、
附录未内联源码、prob02/03/04 无图表进入论文）。本轮逐项闭合：

| # | 原错误 | 处理 |
|---|---|---|
| 1 | 正文仍包含待写占位符 | 补写**摘要 + 关键词**（替换 `> 待 paper-writer…`）、**第 7 章 敏感性、鲁棒性与消融分析**（7.1–7.4，四问分述）、**第 8 章 模型评价与不足**（替换 `> 待撰写。`） |
| 2 | 附录缺少支撑材料文件列表 | 由 `build_paper.appendix_section` 重新拼装（`reports/support/` 2 个文件） |
| 3 | 附录未内联任何源程序代码 | 同上，内联 22 个 `.py`（合计约 1.04 MB） |
| 4–6 | prob02 / prob03 / prob04 没有任何图表进入论文 | 33 张交付图全部以 Markdown 图片形式**内嵌正文**，含全文连续图号「图 1–图 33」、图注（取自 `figures.yaml` 的 `caption`）与源文件路径 |

**新增的图表编号规则**：图号按 `figures.yaml` 中 `included_in_paper = true` 的出现顺序
全文连续编号；插图位置在各小问「图表索引」小节之后，不打断正文论证。

---

## 3. 章节完整性

| 题面小问 | 论文章节 | 覆盖情况 |
|---|---|---|
| 问题 1 | `## 3 prob01` | 问题描述与口径、数学模型、主结果（表 1/表 2）、结果验证 L1–L4/L6、鲁棒性（948 情景）、模型对比（A–F 12 对照）、结论、局限与技术债 |
| 问题 2 | `## 4 prob02` | 目标、数据与预处理、假设与团队口径、完整模型 M1、表 1/表 2/表 3、L1–L6、robustness + ablation 17 case、限制、引用 |
| 问题 3 | `## 5 prob03` | 目标、数据、三层信息结构、M1–M8、费用与电量（双口径）、交付表、机制解释、L1–L6、robustness（156 情景）+ ablation（12 case）、团队裁定承接、限制、引用 |
| 问题 4 | `## 6 prob04` | **分链**：`4-2` / `4-3` 两套定义、两套输入、两个交付件；费用分解、表 1/2/3、工作簿回溯、分链 sanity、分链 robustness、分链 ablation（23 case）、限制、引用 |
| 全部小问 | `## 7 敏感性、鲁棒性与消融分析` | 7.1 prob01（948 情景 / C1–C7）、7.2 prob02（149 次 LP / 17 case）、7.3 prob03（156 情景 / 12 case）、7.4 prob04（分链 162 与 198 情景 / 23 case） |
| — | `## 8 模型评价与不足` | 优点、不足与适用边界（含 4 项未通过判据的如实登记）、改进方向 |

其它必备章节：`## 摘要`（+ 关键词）、`## 1 问题重述与符号说明`、`## 2 数据与建模假设`、
`## AI 工具使用声明`、`## 参考文献`、`## 附录`。

---

## 4. 引用闭合检查

- 正文 `[@引用ID]` 标记 131 处、唯一 ID **97** 个，与 `citations.yaml` 的 97 条**逐一对应**：
  - `used - known = ∅`（无未登记引用）；
  - `known - used = ∅`（无未引用条录）；
  - registry 中 `used_by` 字段全部为空，`validate` 的 `used_by` 一致性检查不产生要求。
- 参考文献按 GB/T 7714 顺序编码制重排为 `[序号] 作者. 题名[文献类型]. 来源, 年. DOI: …`，
  类型标志由 `source` 推断（期刊 `J` / 会议 `C`）。
- **证据等级如实披露**：97 条题录均经 Crossref 核验，等级分布为 `abstract_oa` 与 `metadata`
  两类，**没有全文级**；报告末尾给出「题录核验说明」，声明引用只支撑框架级/机制级主张。
- 对与建模口径直接相关的 10 条关键文献加 `[待人工复核]` 标记
  （`agents/paper-writer.md` 第 7 步要求）。

---

## 5. 图表检查

- **33/33** 交付图的 `stable_id` 均在正文出现（`validate` 硬门禁通过）；
- **33/33** 图件文件存在，且 Markdown 图片路径逐一指向真实文件；
- 图注均保留三处口径提示（AS01 计划窗相位、目标不含 Δt、终端自由与期末放空须与价格套利区分），
  并按 `figures.yaml` 原文如实保留「退化图已弃用」「图内无『当天电价已知』类表述」等约束；
- `included_in_paper = false` 的实验图（robustness / ablations 阶段图件）**未**进入正文，
  仅在图表索引中以文字说明留档，符合团队 B5/R24 纪律。

---

## 6. 本轮修复的代码缺陷（有回归测试）

`scripts/build_paper.py` 的校验器存在两处**互相独立**的真实缺陷（本次修复，见
`tests/test_build_paper.py`）：

1. **附录起点误判（漏检占位符）**：题面引文自带 `## 附录 1 储能设备的参数` /
   `## 附录 2 附件说明`，且正文里存在独占一行的 `## 附录`。原 `APPENDIX_HEADING_RE.search`
   会命中它，把正文（第 2 章数据与假设、四问总结、第 7/8 章）整段划成「附录之前」，
   导致 `> 待撰写。` 永远不被检出（带附录的稿恒判 PASS）。
   修复：新增 `find_appendix_start`，以**最后一个** `### 附录 A 支撑材料文件列表` 定位附录，
   再回退到其前最近的独占一行 `## 附录`；`splice_appendix` 与 `validate` 统一使用。
2. **占位符检查误伤公式与代码**：原实现用 `"{{" in body or "}}" in body`，会命中正文公式里的
   `\Bigr\}` 与附录内联源码里的 f-string 转义（如 `{{0,6,12,18}}`），使带附录的稿
   **永远无法通过**校验（`final` 不可达）。
   修复：改用 `PLACEHOLDER_RE = ^>\s*待 | 待 paper-writer | {{NAME}}`，只匹配真正的模板占位符。

缺陷 1 曾在本轮实际发生：修复前 `validate` 报「正文仍包含待写占位符」而定位不到位置，
正是因为正文里的 LaTeX `}}` 被当成占位符；修复后 `validate` 与结构自检同时通过。

---

## 7. 已披露的警告、局限与技术债（不在论文阶段处理）

论文正文已在对应章节逐条披露，**未**通过调参、放宽判据或挑选指标掩盖：

| 类别 | 条目（论文中位置） |
|---|---|
| 未通过的预注册判据 | 问题二 `S1`/`S5` FAIL（稳定档 = **脆弱**，§7.2.2）；问题三 `S4` FAIL（**条件稳定**，§7.3.2）；问题四链 `4-3` `S4` FAIL（**条件稳定**，§7.4.2）；问题三消融 `C3` FAIL（链级阈值，§7.3.3）；问题四链 `4-3` 消融 `C6`（`spill_bound_pass = false`，§7.4.3）；问题一 `A-DR8` 判据余量仅 0.21 个百分点（§7.1.4） |
| 文献证据边界 | 97 条全部摘要/元数据级、0 条全文；`α_em = 5`、`β_def/β_over = 0.5/1.5`、`5000 kW` 作用侧、`q_em ≡ 0` 均**不得**包装为文献支持（§7.1.4、§7.2.4、§7.3.4、§7.4.4、§8.2） |
| 口径与多解性 | LP 最优面非唯一（验收以残差 + 恒等式 + 目标值 + 交付表为准，不比对逐点解唯一性）；全规模互补 MILP 未证明最优（`mip_gap ≈ 3.17e-7`，incumbent）；`ΔC_price` 基数分歧（权威 258,485.465704 元 vs 备选读法，不得跨基数比较） |
| 跨问不可外推 | 购电上限阈值必须分问分链引用（prob02 `(4218.75, 4375.00]`、prob03 `[4375, 5000]`、`4-2`/`4-3` `(4500, 5000]` kW）；`Σs` 经济贡献为 0 只对 prob02 成立；「日边界不携带电量」只在「逐日 0:00 决策 + 终端自由」结构内成立 |
| 数据事实披露 | 附件 4 含极端低价（`min 0.0076` 元/kWh、`<0.10` 仅 28 格）⇒ `p_min` 解析下界极松；附件 4 的日内形状 ≡ 附件 1 曲线（相关 1.0000），差异在日间水平与逐点扰动 |
| Harness 环境事实 | `supervised` 模式下的 `RESUME`/`reconcile` 误杀缺陷未修（`E-F6`），论文与报告均以纪律规避方式披露 |

---

## 8. 尚未完成：最终稿授权

- `reports/paper/final_paper.md` **未生成**。
- 阻塞条件（`scripts/build_paper.py finalize` 的前置条件）：需要一条**匹配 request ID、
  允许发件人、同一线程、未处理 message ID** 的 `APPROVE` 记录
  （`runtime/email/approvals/<request_id>.json`），且 `problem_state.paper_status == approved`。
- 现状：`runtime/email/approvals/` **目录不存在**；`runtime/email/requests/` 下仅有 4 条
  `kind = question-complete` 的单向通知请求，**无任何 APPROVE 记录**；
  `runtime/workflow_state.json` 无 `last_approved_request_id` / `awaiting_request_id`。
- 因此最终稿必须等待人工邮件授权；在此之前保留本 draft 与其校验结果，不生成 final。

---

## 9. 复现入口

```powershell
# 1) 重新拼装第 7/8 章 + 内嵌 33 张交付图 + 重建参考文献（幂等）
python .tmp/assemble_paper.py

# 2) 官方校验（引用闭合 / 图表闭合 / AI 声明 / 附录）
python scripts/build_paper.py validate --draft reports/paper/draft_paper.md

# 3) 结构自检（章节顺序、图号连续、图片文件存在、引用双向闭合）
python .tmp/check_paper.py

# 4) 回归测试（附录起点误判 + 占位符误伤）
python .tmp/run_tests_direct.py        # 或 pytest tests/test_build_paper.py
```

> 说明：`.tmp/` 下脚本是本次组装流程的留档实现；`tests/test_build_paper.py` 为正式回归测试
> （因本环境沙箱禁止 pytest 在系统临时目录建目录，直接运行脚本形式的等价入口见上）。

---

## 10. 逐小问承接的强制披露纪律核对

按 `reports/cross_question_review.md` §13 的要求，逐条核对论文是否落实：

| 编号 | 纪律 | 论文位置 |
|---|---|---|
| X-1 | 全期/交付期两套费用字段必须随口径标注、禁止跨口径比较 | §4.6.1、§5.6.1、§6.6.1、§8.2.9 |
| X-2 | `ΔC_price` 必须声明基数与所属对照 | §6.6.1、§7.4.4、§8.2.9 |
| X-5 | `5000 kW` 作用侧为团队裁定，不得包装为文献支持 | §7.1.4、§8.2.1 |
| X-6 | 链 `4-2` 的 `q_em` 表述为「机制级恒零」 | §6.6.1、§7.4.2、§8.2.9 |
| X-9 | 购电上限阈值分问分链引用、禁止外推 | §7.2.2、§7.3.2、§7.4.2 |
| X-10 | 价格预测器指标成对报告、不得计为两个独立敏感性来源 | §7.4.3、§8.2.9 |
| X-11 | 文献边界（只支撑框架级/机制级） | §8.2.1、参考文献核验说明 |
| X-12 | 链 `4-3` 条件稳定的适用边界 | §7.4.2、§8.2.7 |
| X-13 | AS23 自放电措辞冲突如实登记 | §7.4.4 |

---

**结论**：`reports/paper/draft_paper.md` 满足 `config/agent_response.schema.json` 与
`config/paper.yaml` 的草稿要求，`validate` 判 **PASS**；最终稿待人工邮件授权后由
`python scripts/build_paper.py final` 生成。
