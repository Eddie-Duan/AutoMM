# Sanity Check Report

- problem_id: microgrid_2025
- question_id: prob02
- assumption_version: assumption_v001（accepted；末尾含「团队勘误 R1–R4」「团队裁定 B0–B5」「团队裁定（formulation D1–D8 与 R5）」）
- formulation_version: formulation_v001（accepted）
- task_id: dc8afc3deb5477641b99（attempt 1，status=succeeded，returncode=0，supervised，CPU HiGHS）
- output_directory: problems/microgrid_2025/prob02/versions/assumption_v001/results/prob02_v001_f001_run002
- overall: **PASS_WITH_WARNING**
- failure_type: `null`；return_to_stage: `null`（无硬门禁失败，登记技术债后推进）
- checked_at: 2026-09-11（动作 `act-847e8cb12a844527`，policy **P3** `run_agent`，stage=**sanity_check**，正式阶段复核）

> 本报告由 `sanity-checker` 出具，是 `sanity_check` 阶段的**正式复核**（上一动作 `act-7fe7441469fb43fd` 是
> `computation` 阶段的 `inspect_compute_result` 验收，二者对象相同，均为 **task `dc8afc3deb5477641b99` / run002**）。
> 本轮**重新独立执行** L1–L4 只读断言（不复用上一动作的 `independent_sanity_out.json`），并重新运行通用脚本；
> **不重解 LP**、不修改模型/代码/假设/公式/结果、不覆盖任何版本目录产物（唯一写入是 L2/L3 证据与报告本身）。
>
> 复核证据（全部新增于本动作 `runtime/actions/act-847e8cb12a844527/evidence/`，可复跑）：
> - `probe_prob02_formal_review.py` → **57 项独立只读断言，57 通过、0 失败**（`formal_review_out.json`）；
>   从原始附件 1/2 与 run002 `solution.json` 的 52,560 时段序列重建，(R1)/(R2)、界、两侧功率、互补性、
>   跨日连续、恒等式 (I1)/(I2)、目标与 `result2.xlsx` 逐格全部独立复算；
> - `scripts/run_sanity_check.py --output evidence/automated_sanity.json` →
>   `automated_status=PASS_WITH_WARNING`、`failures=[]`、8 个数值文件全 `finite=true`（`automated_sanity.json`）；
> - `automm.research.check_key_assumptions('microgrid_2025','prob02')` → `passed=true`、`errors=[]`；
> - `automm.common.hash_path` 独立重算追踪链：`code_hash`、`source_config_hash`、`input_hash`、`config_hash`
>   与 `task.json` 逐位一致，且 `compute_task_id` 复算回 `dc8afc3deb5477641b99`。
>
> **探针自纠记录（诚实登记，非模型缺陷）**：`probe_prob02_formal_review.py` 首次运行时 L3-06 报 6 个时段
> 不匹配，根因是探针把 AS01 的**1 基位置** `position∈{60,…,120}` 误当 0 基下标（`run_prob02.py` L142/L154
> 均为 `position-1`）；改为 `position-1` 后 57/57 全通过，产物数值从未变化。该自纠不影响本报告任何判定。

---

## Level 1：文件和运行完整性 — **PASS**

| 检查项 | 方法 / 证据 | 阈值 | 实测 | 判定 |
|---|---|---|---|---|
| 任务终态 | `runtime/tasks/dc8afc3deb5477641b99/status.json` | succeeded, rc=0, attempt=1 | succeeded / 0 / 1 / supervised / feasible_incumbent=true / consumed=true | PASS |
| 必需产物 | run002 目录 5 个文件 | 全部存在 | solution.json / solver_status.json / tables.json / run_manifest.json / result2.xlsx | PASS |
| 非探针运行 | `run_manifest.json` | probe_mode=false, days=365, periods=52560, model=M1 | false / 365 / 52560 / M1 | PASS |
| task 身份 | `task.json` vs `attempt-001-task.json` vs manifest | 相等 | 逐字段相同；`task_id=dc8afc3deb5477641b99` 回显一致 | PASS |
| 输入未被修改 | 附件 1/2/模板 md5 vs run_manifest | 相等 | `dbe06f92…` / `bb3e493f…` / `b878ce2b…` 全部一致 | PASS |
| 代码指纹 | 实际 `code/*.py` sha256 vs manifest | 逐文件一致 | `10ea7e49…` / `a1cebf40…` / `a3ff906a…` 逐位一致 | PASS |
| harness 追踪链 | `hash_path`/`compute_task_id` 独立重算 | 逐位相等 | `code_hash=a37eda25…`、`source_config_hash=f781f7f6…`、`input_hash=4343d799…`、`config_hash=ebd08796…`；task_id 复算一致 | PASS |
| 代码变更可控 | run001 vs run002 `task.json` | code_hash 变、input/config 不变 | run001 `code_hash=b8f88661…` → run002 `a37eda25…`（仅 `prob02_io.py` 修复）；input/config 不变；task_id 不同 | PASS |
| 历史隔离 | 两次运行产物 sha256 | run001 未被覆盖 | run001 五件 sha256 与上一轮登记逐位不变（solution `1dbc100b…`、solver_status `4e87f187…`、tables `49c00bd6…`、result2 `ac7eba87…`、run_manifest `8b3397d4…`） | PASS |
| 数值未被修复污染 | run001 vs run002 数值产物 | 逐字节相同 | solution.json / solver_status.json / tables.json **三者 sha256 完全相同** | PASS |
| worker 日志 | attempt-001 stdout/stderr | 存在且 rc=0、stderr 空 | stdout 记录完成行，`失败检查=[]`；stderr 0 字节 | PASS |
| 求解器状态 | `solver_status.json` | status=0, feasible, mip_gap=null | 0 / feasible_incumbent=true / mip_gap=null（纯 LP 无该概念）/ HiGHS Status 7 Optimal | PASS |
| GPU 纪律 | run_manifest / solver_status | device=cpu, gpu_required=false | cpu / false（CPU HiGHS，不占单卡 GPU 串行额度） | PASS |

- L1 结论：**PASS**（追踪链完整、输入/模板未变、run001 未被覆盖、修复未触及任何数值）。

## Level 2：数值范围和约束 — **PASS**

从 run002 `solution.json` 的 52,560 时段序列 + 原始附件 1/2 **独立重建**（不读 `checks` 字段、不重解 LP）：

| 检查项 | 阈值 | 实测 | 判定 |
|---|---|---|---|
| (R1) 平衡残差 `b+q_em+PV·Δt+q_dis−L·Δt−c−s` | ≤1e-6 | max **4.547e-13** | PASS |
| (R2) 状态转移重建残差 `E_t−E_{t−1}−0.9c+q_dis/0.9` | ≤1e-6 | max **1.819e-12** | PASS |
| `E_τ ∈ [1200, 10800]` | 双侧 | [1200.000000, 10800.000000]（两端活跃） | PASS |
| `E_0 = 6000`、终端自由 | 口径 | E_0=6000；E_T=1200.000000（AS04/D2-A 期末放空） | PASS |
| 充电上限 `c ≤ 833.3333` | ≤1e-6 | max 833.333333（顶到上限） | PASS |
| 放电上限 `q_dis ≤ 750.0000`（E1/D10 丙） | ≤1e-6 | max 750.000000（顶到上限） | PASS |
| `0 ≤ s ≤ PV·Δt` | ≤1e-6 | 逐点满足；Σs = 990,168.090312 kWh > 0 | PASS |
| 非负 `b, q_em, c, q_dis, s ≥ 0` | ≤1e-6 | 逐点满足 | PASS |
| 两侧换算功率 ≤5000 kW（E1 要求） | ≤5000 kW | `max(c/Δt, η·c/Δt, q_dis/Δt, q_dis/(η·Δt)) = 5000.000000` | PASS |
| 互补性 `Σ c·q_dis` / 同充放时段 | ≤1e-6 | 0.0 / 0 个时段 | PASS |
| 跨日连续性 | ≤1e-6 | `daily` 日初/末 = 独立重建轨迹（偏差 0）；`continuity_residual_max=0.0`；`E_{2/1,0}=7950.000000` | PASS |
| 日初不复位 | =96 个水平 | `day_start_unique_levels=96`（滚动递推落地） | PASS |
| 供给 ≥ 负载（H1） | ≥0 | `c+s+q_em ≥ 0`，min 残差 0 | PASS |
| `Σ q_em = 0`（定理 T1） | =0 | 0.0（逐时段 max=0；`days_with_emergency=0`） | PASS |
| (I1) `Σq_dis = η²Σc − η(E_T−E_0)` | ≤1e-6 | 0.0 | PASS |
| (I2) `Σb = N + Σs + 0.19Σc + ηΔE − Σq_em` | ≤1e-6 | 0.0 | PASS |
| (I1)/(I2) **交付期切片** | ≤1e-6 | 0.0 / 0.0（交付期日初 E=7950.000000） | PASS |
| totals 与序列自洽 | ≤1e-4 | Σb=22,657,938.157435、Σc=7,364,620.676347、Σq_dis=5,969,662.747841、Σs=990,168.090312、N=20,272,812.138617 | PASS |
| 数值有限性 | 无 NaN/Inf | 9 条序列全部 finite | PASS |

- L2 结论：**PASS**（无 NaN/Inf、无界越界、无硬约束违反）。

## Level 3：量纲和公式 — **PASS**

1. **目标量纲（D9）**：独立计算 `Σ p·b + 5Σ p·q_em` = **13,758,182.573724 元**，与 `objective_yuan`
   一致（≤1e-6）；`C_em = 0`、`C_plan = C_total`（因 `q_em ≡ 0`）；交付期 **12,233,050.830708 元**、
   1 月 **1,525,131.743016 元**，且 `交付期 + 1月 = 全期`。若误乘 Δt 交付期会落到约 2.04e6 元（量级差 6 倍）；
   量级自检 10^7 元通过 → **目标不含 Δt，量纲正确**。
2. **矩阵规模（formulation §3.9 ↔ code）**：`run_manifest.matrix_scale` 为
   `variables=315,360=6T`、`equality_constraints=105,120=2T`、`variable_bounds=315,360`、
   `integer_variables=0`，与 code 常量（`KINDS=6`、每时段 2 条等式、纯 LP）逐项一致；
   `nnz=473,039=9T−1`；code 常量 `Δt=1/6、η=0.9、E_init=6000、α_em=5、P_max=5000、C_CAP=833.33、Q_CAP=750.00、
   DAILY_DELIVERY_START=31` 与 accepted 口径逐项一致 → **formulation 与实现一致**。
3. **表 1 / 表 2 / 表 3 与序列回溯**：4 个指定日期（附件 2 日索引 78/171/265/354）的 6 个时段
   （AS01 **1 基位置** 60/72/84/96/108/120 → 0 基下标 59/71/83/95/107/119）购电量与序列逐位一致（≤1e-6），
   `attachment_timestamp`（左端点）与 `template_label`（完整区间）双标签校验 `table1_label_checks_passed=true`；
   表 2 六块充电量/放电量分别求和、不冲抵，且 `storage_0_00_kwh`/`storage_24_00_kwh` 与 `E_{d,0}`/`E_{d,144}`
   逐位一致（如 2025-03-20 = 8550.000000/4352.866148）；表 3 四日 `intervals=[]`、`total_kwh=0`、`paper_text=无（0 kWh）`，
   `table3_note` 含「**格式示例**」表述（R2 附带要求）。
4. **`result2.xlsx` 数值与填报格式回溯（全部独立逐格，硬门禁）**：
   - `计划购电量` 147 列表头（`0:10-0:20 … 0:00-0:10+1`、**无** `0:00-0:10` 列、末两列 `全天购电量`/`全天购电费`）；
     334 天 × 144 时段 + 全天能量 + 全天费用 **max|Δ| ≤ 1e-6**，日期列逐日一致；
   - `充放电量` 334×6 = **2,004 行**：日期只写块首行、`时刻`（第 1 行 `00:00:00`、第 2 行 `24:00`）/`储电量`
     只写每日前两行、第 3–6 行为空；块充/放电量与序列块和 ≤1e-6；端点储电量 ≤1e-6；
   - `紧急购电量` 334 行：逐日 `时间段=—`、`购电量=0`（勘误 R4 允许的登记偏离，模板 3 行块形未照搬）；
   - 全簿无模板 `⁝` 压缩行残留；`run_manifest.workbook_info.format_residuals = []`（实现侧硬门禁）
     与外部逐格扫描**互为独立证据**；
   - ✅ **上一轮 `NEEDS_REVISION` 的交付格式缺陷（`充放电量!A15=2025-12-31`、`!E16='24:00'`）已闭合**：
     修复后 `prob02_io._assign` 以 `cell(...).value = value` 真正清空 `None`，`_clear_rows`/`fill_result2_workbook`
     全走 `_assign`；run002 逐格偏差 0，且 run001 同脚本负对照恰得 2 处（证明扫描有效）。

- L3 结论：**PASS**（模型、量纲、公式、交付工作簿数值与填报口径均与 accepted AS12 + 团队勘误 R3/R4 一致）。

## Level 4：常识与文献合理性 — **PASS_WITH_WARNING**

1. **解析界（独立重算，不用硬编码常量）**：`p_min = 0.3713`、`N_full = 20,272,812.138617 kWh`，
   下界 `p_min·[N + η(E_min−E_0)] = 7,525,691.131 元`；无储能可行解上界 `Σ p·max(0, L−PV) = 18,298,592.366 元`；
   `C_total = 13,758,182.574 元 ∈ [下界, 上界]`，交付期 12,233,050.83 元为 **10^7 元量级**。PASS
2. **套利方向**：充电加权均价 **0.520371 元/kWh** < 放电加权均价 **1.154986 元/kWh**，符合「低价充、高价放」。PASS
3. **定理 T1 前提**：`p>0`、`α_em=5>1`、`b` 无上界同时成立，`Σq_em=0` 是模型内推论（非文献结论）。PASS
4. **终端自由披露**：`E_T = 1200 kWh`（期末放空，能量账等价少购 4320 kWh），AS04/D2-A 要求论文显式披露并与价格套利区分。PASS
5. **日初不复位**：日初状态取 96 个不同水平；`E_{2/1,0} = 7950.00 kWh`，滚动递推口径落地。PASS
6. **关键假设文献门禁**：真实调用 `automm.research.check_key_assumptions('microgrid_2025','prob02')`
   → `passed=true`、`errors=[]`、`assumption_version=assumption_v001`（6 条关键假设各绑定 ≥1 条 verified+used 文献）。PASS
7. **不越界**：A6/A7/A8/A9 属 prob03/04；附件 3/4 未被使用（附件 1 只用**电价列**、附件 2 用**实际值**）。PASS
8. **技术债（警告）**：文献池 23 条未逐篇阅读正文（19 `abstract_oa` + 4 `metadata`），引用只支撑框架级/机制级主张；
   D10「5000 kW 作用侧」为 team_decision，两池无一条涉及，论文不得包装为文献支持。→ 见 warnings。

- L4 结论：**PASS_WITH_WARNING**（硬门禁「关键假设引用」「物理/经济常识」通过；文献证据等级与口径缺文献支撑为技术债）。

## Level 5 / Level 6

> **更新（动作 `act-8f35ac7d5f354489`，2026-09-11T03:33Z）**：robustness 阶段已完成
> （`record_optional_stage(stage="robustness", decision="completed")`，task `f7a4e670b91ad469d771`）。
> **L6 已在本报告末尾「附：Level 6 鲁棒性与敏感性复核」正式执行，判定 PASS_WITH_WARNING
> （`criteria_failed=["S1","S5"]`、`stability_grade=脆弱（需缩小适用范围）`）；L5 仍为 not_applicable。**
> 以下为 L1–L4 阶段（robustness 尚未执行时）的原始记录，**保留不改**以维持审计轨迹。

- **L5（跨小问一致性）本阶段 not_applicable**：触发条件为「所有小问 locally completed」；prob01 已 locally_completed，
  但 prob03/prob04 尚未进入计算（`problem_state.current_question=prob02`）。结转项见下节。
- **L6（鲁棒性与敏感性）L1–L4 阶段当时 not_applicable**：触发条件为 `after_robustness`；`config/workflow.yaml` 已把
  robustness/ablation 列为 **mandatory**（`optional_stages=[]`）。robustness 现已完成并由本报告附录正式复核。

---

## 与 accepted 团队裁定/勘误的接口（显式记录，不静默沿用旧登记）

| 编号 | 团队口径（效力最高） | 本问执行 / 证据 | 状态 |
|---|---|---|---|
| **C1/E1** | `q_dis ≤ 750.00 kWh`（口径丙，并网点侧与电池侧同时 ≤5000 kW、取更严者） | code `Q_CAP=750.0`；本复核 `max q_dis=750.000000`、四式两侧功率 max=5000.000000 kW；`global_symbols.yaml` 第 248 行已回写 **750.00** | **一致，冲突已闭合** |
| **C2/E2** | `q_spill.first_question = prob01` | 符号表第 273 行已回写 **prob01**；本问沿用 `s_{d,t}`，Σs=990,168.090312 kWh | **一致，冲突已闭合** |
| **C3/E3** | `prob01/assumption_v003/version.yaml` 的 AS08「必然被激活」措辞应更正 | **仍未更正**（属 prob01 assumption 阶段产物）；本问按「变量保留、最优解允许取 0」执行，实测量 `Σs>0` | 结转技术债，权威回写待 `cross_question_review` |
| **R5** | 购电上限**激活阈值** `β ∈ (4218.75, 4375.00] kW`；`10,326 kW` 只是非绑定阈值 | 本问主口径无上限、`Σq_em=0`，与 R5 一致；下游 ablation/论文必须改用 β 表述 | 一致（下游纪律须遵守） |
| **D10** | 「5000 kW 作用侧」为 `team_decision` | code 按口径丙实现；文献池无支撑，未包装为文献 | 技术债（无文献支撑） |
| **B0–B5** | 主结果只以 M1 为准；M1–M7+M6′ 由 ablation 实跑；robustness/ablation 必做 | 本 run 只交付 M1；`q_em≡0`、矩阵规模、B2 的解析恒等式 ①②③④ 已由本动作独立核验 | 一致；M2–M7+M6′ 属 ablation |
| **formulation D1–D8** | 采纳 A（M1 唯一交付口径；C2 只判 M2a；M4 与 M1 同为 365 天；M6 保留原网格 + 追加 M6′；M3 限时 ≤300 s + 4 代表日 MILP；表 2 端点语义披露；表 3 主口径全零 + T1 说明；M5 只在 ablation 出数） | 本 run 为 M1；表 2 四日端点齐备；表 3 全零且带「格式示例」说明 | 一致（下游 ablation 须执行） |
| **R1** | 论文表 2 须区分 prob01（单日周期，端点恒 6000）与 prob02（全年滚动、随日变化） | 本问表 2 端点随日变化（2025-03-20 = 8550.00/4352.866148；2025-06-21 = 2361.059963/8550.00）；论文须显式区分 | 待论文落地（警告） |
| **R3/R4** | `充放电量` 前两行为 `时刻/储电量`；`紧急购电量` 每日期至少 1 行 | run002 逐格复核 0 偏差、334 行 `—`/0 | 一致 |
| **A2/A5/A10/A11/A13/A14/A17/A18** | 本版本末尾工作流已按 D1–D8 推荐项落盘 | 参数 `days=365`、`DAILY_DELIVERY_START=31`、`b_upper=null`、终端自由、`q_em` 保留为变量 | 一致 |
| **A6/A7/A8/A9** | 属 prob03/prob04 | 本问未裁定、未使用附件 3/4 | 未越界 |

---

## 路由与命令

- `status`: **success**（`failure_type=null`，无 `return_to_stage`）
- `blocking_reasons`: `[]`（非人工阻塞；无硬门禁失败）
- `recommended_next_stage`: **visualization**
- 命令：`record_sanity(level_1_4, PASS_WITH_WARNING, failure_type=null, return_stage=null)`（正式阶段复核落盘）
  + `transition(target_stage="visualization", ...)`（`computation→sanity_check→visualization` 均在 `config/gates.yaml`
  允许迁移内；`visualization` 前置门禁 `sanity.level_1_4 ∈ {PASS, PASS_WITH_WARNING}` 已满足）+ `append_ledger`
- 机器摘要：`machine_sanity.json`；独立复核：本动作 `evidence/formal_review_out.json`、
  `evidence/automated_sanity.json`、`evidence/formal_review_stdout.txt`

**warnings（技术债，随本阶段结转）**

1. 文献池 23 条未逐篇读正文（19 摘要级 + 4 元数据级），引用只支撑框架级/机制级主张；公式级/定量级引用须取得全文后再用。
2. D10「5000 kW 作用侧」为 team_decision，无文献支撑；`q_em≡0`、`α_em=5` 不得包装为文献结论。
3. C3/E3：`prob01/assumption_v003/version.yaml` 的 AS08「必然被激活」措辞未回写；待 `cross_question_review`。
4. R5：下游 ablation 与论文须用 `β ∈ (4218.75, 4375.00] kW` 表述购电上限激活阈值，不得沿用 `10,326 kW`。
5. 表 2 端点为「计划窗首/末状态」（AS01 左端点相位 0:10→24:10），prob02 为全年滚动逐日切片；论文与图注须与 prob01 显式区分（R1）。
6. LP 最优面可能不唯一（E 上下界两端活跃、`c`/`q_dis` 上界均顶到）：验收以约束残差 + (I1)/(I2) + 目标值 + 表 1/2/3 +
   `result2.xlsx` 数值为准，不比对逐点解唯一性。
7. A6（附件 3 降尺度与年末边界）、A7（prob03 结算口径）、A8（prob04 电价可观测性）、A9（附加预报时刻分析）未裁定且属 prob03/04。
8. `run_manifest.json` 的 `code_sha256` 为脚本自算（仅 `*.py`），与 harness `code_hash`（含 task_config/task_spec）算法不同；
   追踪以 harness 值 `a37eda25…` 为准。
9. `q_em ≡ 0` 依赖「完全信息 + 外网购电无功率上限 + α_em=5」三项同时成立；若团队改 D3 或 D6，紧急购电会被激活，
   表 3 不再是全零，须重算并按 A18 规则填报。
10. run001 仅作历史对照保留（其 `result2.xlsx` 含 2 处已闭合的模板残留），**交付与引用一律以 run002 为准**。
11. 本报告为 `sanity_check` 阶段 L1–L4 正式结论；**不替代**后续 L5（全题跨小问一致性）与 L6（robustness 后复核）。

---

## 附：Level 6 鲁棒性与敏感性复核（动作 `act-8f35ac7d5f354489`）

- **调用背景**：robustness 阶段完成（`record_optional_stage(stage="robustness", decision="completed")`）后，
  Runner 按 `config/sanity_check.yaml` 的 `level_6.trigger = after_robustness` 迁移到 `sanity_check`
  并调用 sanity-checker（policy P3 `run_agent`，`level=level_6`）。这是 **L6 的正式执行**，不是重跑 robustness。
- **对象（只读）**：`robustness/results/prob02_v001_robust_run001`（task `f7a4e670b91ad469d771`，
  attempt 1、`succeeded`、`supervised`、CPU、`rc=0`、`probe_mode=false`、`seed=20260910`、
  `wall_clock_seconds=907.269`、49 个矩阵情景 + 100 个噪声样本 = **149 次全年 LP**）；
  参考基线仍为 accepted `results/prob02_v001_f001_run002`（task `dc8afc3deb5477641b99`）。
- **复核方式（全部只读，不重解 LP、不导入 robustness 代码、不修改模型/代码/假设/原始数据、不覆盖既有产物）**：
  `evidence/probe_l6_review.py` 从 `raw_samples.jsonl`/`summary.json`/`sensitivity.json`/`baseline_check.json`/
  `run_manifest.json`/`trajectories/` 与 accepted run002 产物出发，**独立重算**预注册判据 S1–S6、基线闸门、
  结构发现、数值健康度与追踪链，共 **45 项断言、0 失败**（结论：`PASS`）；
  另有 `scripts/run_sanity_check.py` 在同动作 `evidence/auto_scope`（数值副本）上跑 L1/L2-finite，
  `automated_status=PASS_WITH_WARNING`、`failures=[]`、6 个数值文件全 finite（未覆盖版本目录）。
- **基线复现闸门（强制前置）= 通过**：8 项总量相对差全为 `0.0`；4 个指定日期的全天购电量/购电费相对差
  ≤ 2e-11、表 1 六时段最大绝对差 3.33e-7 kWh（参考 `tables.json` 的 6 位小数舍入）。
  独立重算的 run002 总量、逐日合计与恒等式与 `baseline_check.json` 逐位一致（本动作另核 4 个指定日期的
  购电量/费用/0:00/24:00 储电量，相对差 ≤1e-9）。
- **S1–S6 独立复算结果（与 report.md 逐位一致，判据未事后修改）**：

| 判据 | 阈值 | 独立复算 | 判定 |
|---|---|---|---|
| **S1 可行率** | 参数族 ≥0.99 且核心族 ≥0.95 | 核心族 135/136=0.992647；参数族 35/36=0.972222（唯一失败 `solver_highs-ipm`） | **FAIL** |
| **S2 幅度与符号** | `max|ΔC|/C* ≤25%`（η 档 35%）且方向全通过 | 0.140782（η@0.72）；`∂C/∂η≤0`、`∂C/∂P_max≤0`、`|弹性(E_init)|≤1.5` 全成立 | PASS |
| **S3 噪声区间** | 分位半宽 ≤20% 且 \|均值偏移\| ≤10% | 0.9565% / 0.2249%（100 样本） | PASS |
| **S4 套利方向** | 核心族 100% | 136/136 | PASS |
| **S5 交付表稳定** | 全天量/费 ≤10%；slot ≤15% | 19.0998% / 19.6225%（`eta_both_0.99@2025-06-21`），slot 0.9912% | **FAIL** |
| **S6 求解器一致性** | 两两相对差 ≤1e-6 | 全为 0.0 | PASS |

  独立结论：`criteria_failed=["S1","S5"]`、`stability_grade=脆弱（需缩小适用范围）`，与 `summary.json`/
  `run_manifest.json` 登记一致。
- **S1 失败归因（照实记 FAIL，不改判据）**：唯一失败样本 `solver_highs-ipm` 的目标值 `13,758,182.573724 元`
  与基线**逐位相同**、等式残差 2e-12、界越界 0.0、可行；唯一失败检查为 `complementarity_sum=4.41358e8`
  （同充放时段 1136）。AS07 **不禁止**同时充放电、`formulation_v001 §3.12 引理 L1` 只断言**存在**互补最优解，
  故该检查是**返回解清洁度**而非可行性。本动作独立复算：**剔除 complementarity_sum 后 core/param 均为 1.0**。
  这不构成「模型脆弱」证据，但也不得抹去；论文必须同时呈现「S1 FAIL」与「同值最优解」。
- **S5 失败归因（真实日尺度敏感性，双向）**：`eta_both_0.99` 使 2025-06-21 全天购电量/购电费下降
  19.10%/19.62%（**有利方向**，实现按 `_rel_diff` 绝对值口径计入失败）；本动作独立复算全 365 天：
  η=0.99 无一天购电量上升 >10%（最大 +7.17%，逐日费用最大升幅仅 +1.82%），而 η=0.81 的不利方向
  逐日购电费最多 **+12.97%**（21 天 >+10%、1 天购电量 >+10%）——报告 §5.2 的逐日声明逐条吻合。
  论文引用表 1/表 2 时须说明「日尺度量对效率口径敏感（±10% η 可移动约 ±20%），年度/交付期总量仅 ±7%」。
- **结构情景独立复算**：`b_cap` 10 档严格单调（上限↓ ⇒ Σq_em↑、总费用↑）；Σq_em 为零的最大上限 **4375 kW**、
  为正的最小上限 **4218.75 kW** ⇒ **β ∈ (4218.75, 4375.00] kW**，与 `formulation §3.8 定理 T2`、团队勘误 **R5**
  一致；**10,326 kW 为非绑定阈值（Σq_em=0）**，不得再称「低于即强制激活」。4218.75 kW 档 Σq_em=8707.398542 kWh、
  14 天、紧急购电费 18,237.601302 元；2,000 kW 档 Σq_em=7,845,369.336456 kWh、365 天。
  `s_bound`（D5-B 物理盈余界）目标值与 Σs=990,168.090312 kWh **不变**（K5 前半成立）；`s_sell` 松界 + 0.50 元/kWh
  售出 5,845,778.709901 kWh > 物理盈余 3,120,221.003233 kWh（非物理套利，不得作交付数值），
  先收紧物理界后 Σs=2,795,527.333984 kWh 回到盈余以内；`α_em=0.50` 时 q_em>0、365 天全启用（机制可激活）。
- **数值健康度（独立复算）**：149/149 可行、无 NaN/Inf、solver_status 全 0；参数/结构族等式残差 ≤8e-12、
  界越界 ≤2e-12、`I1/I2` ≤7e-9、跨日连续 0、两侧功率 ≤5000 kW、`c ≤ P·Δt`、`q ≤ P·Δt·η_dis`（η 族按口径丙
  同步换算，如 η=0.99 时 q ≤825.0，**不是**违反 E1 的 750.0）、参数族同充放仅 `highs-ipm` 的 1136 时段；
  baseline `E_T=1200`、`Σq_em=0`、日初 96 个水平、交付期 10^7 元量级且 `C_opt < C_nostorage`。
- **追踪链（独立重算）**：按 `scripts/automm/common.py::hash_path` 重实现后重算
  `code_hash=1e98c310…`、`source_config_hash=25dd6585…`、`input_hash=4343d799…`，与 `task.json` 逐位一致；
  robustness 代码 sha256 与 `run_manifest.code_sha256` 一致；accepted `code/*.py` sha256、
  run002 四件参考产物 sha256（含 L1–L4 动作登记值）与两个附件 md5 **全部未变**；输出目录独立，
  `robustness/results/` 下仅 `prob02_v001_robust_run001` 一份，6 张图件齐备非空。
- **本动作新增发现（L6-D1，仅文档标注，不影响数值）**：`report.md §8.4` 把 `α_em=0.50` 情景的
  `Σq_em=22,657,938.157435 kWh` 标注为「= 全年净负荷」，但全年净负荷为 `20,272,812.138617 kWh`；
  该值实际**等于基线 `Σb`**（同一物理计划整体改记为紧急购电：`Σq_em = Σb = 净负荷 + Σc − Σq_dis + Σs`），
  且该情景目标 `6,879,091.286862 元` 恰为基线的 **0.5 倍**。论文不得称其为「净负荷」，并应说明 α<1 的
  「机制激活」是把全部购电量重标为紧急购电的重标定效应，而非新的物理调度。
- **判定与路由**：`overall = PASS_WITH_WARNING`（无硬门禁失败；S1/S5 的 FAIL 为预注册技术债，
  已在 `robustness/report.md §5/§9` 登记且判据未事后修改）；
  `failure_type=null`、`return_to_stage=null`、`blocking_reasons=[]`；
  `recommended_next_stage = ablation`（`config/workflow.yaml: mandatory_stages`，B0–B5/D4 要求实跑 M1–M7 + M6′）。
- **本动作请求**：`record_sanity(level_6, PASS_WITH_WARNING, failure_type=null, return_stage=null)` + `append_ledger`；
  **不**发起阶段迁移命令（`robustness → sanity_check` 已由 Runner 完成，下一阶段 `ablation` 由 Runner 按状态机推进）。
- 机器报告：`machine_sanity_level6.json`（L1–L4 的 `machine_sanity.json` 保留不改）；
  独立复核证据：`runtime/actions/act-8f35ac7d5f354489/evidence/`
  （`probe_l6_review.py` / `probe_l6_review_out.json` / `probe_l6_review_stdout.txt` /
  `automated_sanity_stdout.txt` / `auto_scope/machine_sanity_finite.json`）。
- **warnings（技术债，随本阶段结转）**：见 `machine_sanity_level6.json.warnings`（D-R1…D-R9、L6-D1、
  结构边界与 LP 最优面非唯一、结转 L1–L4 的文献/AS06/上游登记/A6–A9/conclusion 空缺等）。
