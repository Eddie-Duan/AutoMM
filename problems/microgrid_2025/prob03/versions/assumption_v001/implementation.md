# 实现计划（implementation，prob03）

- 归属：`microgrid_2025` / `prob03`（问题 3：0:00 计划 + 6:00/12:00/18:00 调整与偏差结算）；阶段：`implementation`
- 同步动作：`act-e0c8ef301bda49eb`（负责人：implementation-agent；策略 P5 / `action=run_agent`；前序 T7 修订动作 `act-06c999a94813435f`）
  - **本动作是 T7 一致性修订的复核与收尾**：`act-06c999a94813435f` 已把团队 T7 落到 `code/`（见下条），但其响应在
    `artifacts_created` 中把证据文件误写为 `.../probe_run_d34/result3.xlsx`（实际落盘为 `probe_result3.xlsx`），
    Harness 逐条校验路径存在性时抛 `FileNotFoundError`，本动作因而是 `infrastructure_transient` 的重试。
    本动作做三件事：① 只读复核 T7 代码与全部探针（数值逐位复现）；② 修复 `run_prob03.py` 的 **LP 计数缺陷**
    （`solver_calls_per_layer = 3` → `4`，见 §3 / §11）；③ 重跑静态检查与探针并**重新登记** `code_hash`/`task_id`。
    **未创建 task、未写 `results/`、未运行 365 天正式计算。**
  - **T7 不一致缺陷的修复来源**：前稿 `act-109ffb18e7f84f33` 在 `assumptions.md` 末节写入 **T5–T8**（尤其 **T7 统一冻结 tie-breaking**）
    之前完成，accepted code 与 T7 不一致；`resource-manager`（`act-410ecb6936a746cd`）据此回退到 `implementation`
    （`failure_class=code_runtime`、可自动路由）。`act-06c999a94813435f` 补齐 T7-1/T7-2/T7-3/T7-5，并同步
    `task_spec.yaml`/`task_config.yaml`。
- 版本目录：`problems/microgrid_2025/prob03/versions/assumption_v001/`
- accepted 依据（全部只读）：
  - `assumptions.md`（assumption_v001，18 条、7 条 key；末节「待团队选定的决策点 D1–D12」+「团队裁定（prob03 多模型对比与交叉验证要求）B0–B7」
    + **末节「团队裁定（`formulation` F1–F8 的确认与三处补充，2026-09-11）」T5–T8，其中 T7 效力最高**）
  - `formulations/formulation_v001/{formulation.md,formula_validation.md,parameters.yaml}`（accepted formulation，`active/accepted_formulation_version = 1`）
  - 上游：`../prob01/versions/assumption_v003/*`（AS01/AS05/AS06+D10/E1/AS08/E2/AS13 等）、`../prob02/versions/assumption_v001/*`（A2 = D1-B 滚动递推 + D2-A 终端自由、R1/R5、D4/D5/D7 等）
  - `request/problem.md`（问题 3、附录 1、附录 2、表 1–表 4）、`data/附件1.xlsx`、`data/附件2.xlsx`、`data/附件3.xlsx`、`data/附件5/result3.xlsx`
  - `../../global_symbols.yaml`、`../../dependency_graph.yaml`、`../../problem_state.json`、`prob03/question_manifest.yaml`
- 规则依据：`agents/implementation-agent.md`、`agents/resource-manager.md`、`PROJECT.md`、`RESEARCH_LOOP.md`、`AGENTS.md`、`config/{compute,gates,workflow,paths}.yaml`、`wiki/compute-tasks.md`、`knowledge/optimization.md`
- 不覆盖历史：本动作只写 `prob03/versions/assumption_v001/code/`、`implementation.md` 与本 action 的 `evidence/`；未修改
  `assumptions.md`、`version.yaml`、`formulations/`、`global_symbols.yaml`、`citations.yaml`、`question_manifest.yaml`、
  `runtime/workflow_state.json`、`data/`、`request/`，也未改动 `prob01/`、`prob02/` 任何版本目录。
- **本动作未运行 365 天正式计算**（implementation 机械边界）：`--days 365` 只用于 ①**不求解**的模板填报与降尺度/跨年结构静态探针；
  ②`make_task_spec` 的规格预演（不创建 task）。正式数值由 `computation` 阶段的隔离 task + supervised worker 产出。

---

## 1. 口径落地清单（accepted 假设 / formulation / 团队裁定 → 代码位置）

| 口径 | 取值/要求 | 代码落点 |
|---|---|---|
| **AS01** 左端点对齐 | 位置 `i` = 区间 `[10(i−1), 10i)` 分钟；计划窗 `0:10 → 24:10`；表 1 的 `10:00-10:10` 取位置 60 | `prob03_io.read_attachment1`（按行位置读取、不排序/不插值）、`run_prob03.build_tables` 的双标签校验、`prob03_model.interval_label` |
| **AS02** 输入范围 | 只用附件 1 **电价列**、附件 2 实际负载/光伏、附件 3 整点预报；禁用附件 4 与附件 1 预测列、2026 数据 | `run_prob03.main` 的 `ChainInputs` 构造；`read_attachment1` 只保留第 2 列 |
| **AS03/AS04** 跨日与终端 | 自 2025-01-01 以 `E_init = 6000 kWh` 滚动递推（`E_{d,0} = E_{d−1,144}`，1 月预热）、终端自由 | `prob03_model.run_m1` 的 `e_prev` 链；`solve_plan_layer` 的 `e_start`；(PL-6) 不固定末时段 |
| **AS05**（key）预报语义与降尺度 | 整点**点值** + 整点锚定**线性插值**（`k=1` 前向保持）；`m` 只支配 `i ≥ 6m+1`；跨年项不消费 | `prob03_model.downscale`（R1a/R1b/R1c）、`dominance_map`、`cross_year_dropped_count`、`build_layer_inputs` |
| **AS06/AS07**（key）四决策时刻与三层 | 计划层 `min Σp·b`（T1）→ 调整层逐个顺序重优化（只提交 `D_m`）→ 闭式结算；**禁止**联合 LP 让前两层看到实际值 | `solve_plan_layer` / `solve_adjustment_layer` / `run_m1`（提交切片 `slice(6m, 6m+36)`）、结算层 `np.maximum(±residual, 0)` |
| **AS08**（key）平衡与 `q_em` | 结算层等式平衡含 `q_em`；`0 ≤ s' ≤ PV^act·Δt`；`q_em ≥ 0` 保留为变量 | `run_m1` 的结算块；`evaluate` 的 (I6d) 与 `periods_with_q_em_and_charge` 统计 |
| **AS09/AS10**（key）结算与目标 | `C_adj = Σ[0.5p(b−q)⁺ + 1.5p(q−b)⁺]`（两段均为成本项）；`C_total = C_plan + C_em + C_adj`（元，**不乘 Δt**） | `solve_adjustment_layer` 的 `u⁺/u⁻` 块与系数、`evaluate` 的 `cost_*_d` |
| **AS11** 调整量语义 | 替代量：`i ≤ 36` 时 `q = b`；每时段由最后支配时刻取值 | `run_m1` 的提交顺序；`evaluate` 的 `q_eq_b_first_block` 检查 |
| **AS12** 设备约束（D10 口径丙 / E1） | `c ≤ 833.3333`、`q_dis ≤ 750.0000`、`E ∈ [1200,10800]`、两侧功率均 ≤ 5000 kW | 两层的 `bounds` 与 `evaluate` 的四路功率换算 |
| **AS13/AS14** 弃光与外购 | 各层 `0 ≤ s ≤` 该层 `Π_m·Δt`（系数 0）；`b/q` 无上界、无售电 | `bounds[3n:4n,1] = pv_fc_energy`；`bounds` 的 `np.inf` |
| **AS15**（key）确定性 LP / CPU | 连续变量、线性目标；CPU HiGHS；**不使用 GPU**、无随机源 | `linprog(method="highs")`；`task_config.yaml` 的 `device=cpu`、`gpu_required=false`、`seed=null` |
| **AS16** 填报口径 | 表 1 = 最终量 `q` + `C_total`（正文给三分项）；表 2 = 6 块不冲抵 + 端点；表 3/紧急购电 = 合并区间 + 左端点标签 + `J_d=0` 写 `—`/0；`result3.xlsx` 四工作表 | `run_prob03.build_tables`、`prob03_io.fill_result3_workbook`、`_residual_report` 硬门禁 |
| **团队 B0/B2** 主口径唯一 | 本 `code/` 只实现 **M1**；`M2`–`M8` 由 `ablation` 在 `ablations/code/` 另建 | `code/` 仅含 M1 |
| **团队 B3** 交叉验证 | 四条恒等式（逐时段平衡/跨日/状态转移/费用分解）、交付期与全期分别报告、量级自检 | `evaluate` 的 `identities`/`checks`/`bounds`/三口径（全期、交付期） |
| **团队 B5** 公平与隔离 | 同输入（附件 1/2/3 同一 md5、模板只读）、同参数、同口径、同预算、输出隔离 | `task_spec.yaml` 的 `inputs_readonly` 与 `output_directory`；代码不读附件 4/预测列 |
| **团队 B7** 阻塞清单 | T1 计划层目标、三层信息集落盘、分段线性化无损、逐格映射、跨年清单、规模复核、P-VS-Q 声明 | §1 表、`solve_*`、`build_tables`、§2.1、`series.plan_purchase_kwh` vs `final_purchase_kwh` |
| **团队 T7-1**（效力最高）统一 tie-breaking | **所有层、所有模型（M1–M8）**一律 `min [该层主目标] + ε·Σ_t(c_{d,t}+q_dis_{d,t})`，即在主目标最优解中优先取储能吞吐量最小者 | `prob03_model` 的共享算子 `_solve_with_tiebreak`（两层的 `solve_plan_layer`/`solve_adjustment_layer` 均调用）、`tiebreak_epsilon`、`throughput_coefficients`、常量 `T7_EPS_RELATIVE`/`T7_TIEBREAK_RULE`；`M2`–`M8` 在 `ablations/code/` 复用同一算子（T7-5） |
| **团队 T7-2** 不变性验证 | 实现必须落盘「加入次目标前后主目标相对变化 ≤ `1e-9`」的**逐层**验证；不成立则调小 ε 重跑 | `_solve_with_tiebreak` ① 纯主目标基线 `P*` vs ② 加权式 `P'`（`weighted_primary_relative_change`）+ ③ 字典序提交解；`TiebreakRecord.primary_relative_change` / `invariance_passed`；硬检查 `t7_primary_invariance_max_relative_change`、`t7_invariance_all_layers_passed`；`t7_tiebreak.json.per_layer`（1,460 条） |
| **团队 T7-3** 可选性说明 | 若某层仍存在多个最优轨迹，必须报告**退化维度**与**影响的上游量**，不得静默取一个解 | `_degeneracy_proxy`（活跃约束数 − 变量数）、主目标最优面上的**吞吐量上界**探测（`throughput_upper_on_optimal_face_kwh`/`throughput_unique`）、上游量 `boundary_state_kwh` 与 `baseline_state_change_max_kwh`，汇总于 `t7_tiebreak` |
| **团队 T7-4** `C5` 更正 | 按 T7-1 重跑 A9 对照；**禁止**调 ε 或换 tie-break 规则去制造单调性 | 本 `code/` 只实现 `M1`；`M5` 的 `C5` 属 `ablation`，但 tie-break 算子已按 T7-1 冻结供其复用 |
| **团队 T7-5** 公平性 | `M8`（独立第二实现）只允许 HiGHS 设置不同，**tie-breaking 必须与 M1 完全一致** | `_solve_with_tiebreak`/`tiebreak_epsilon`/`throughput_coefficients` 为唯一入口；`t7_tiebreak.json.m8_fairness_note` 与 §8 第 10 条 |

### 1.1 与上游登记 / 团队裁定 / formulation 的冲突与差异（显式记录，不静默沿用）

| # | 冲突/差异 | 旧登记或 formulation 写法 | 本实现执行 | 依据/去向 |
|---|---|---|---|---|
| **C1/E1** | `q_dis` 域 | 旧值 833.33 | **750.0000**（只读复核 `global_symbols.yaml` 已回写） | 团队 D10 口径丙 + 勘误 E1；**无残留冲突** |
| **C2/E2** | `q_spill.first_question` | 旧值 prob02 | 已回写 **prob01**；本问沿用 `s`，含义不变 | 团队勘误 E2；**无残留冲突** |
| **C3/E3** | `prob01/assumption_v003/version.yaml` 的 AS08「必然被激活」措辞 | 未更正 | **本实现不改**（属 prob01 assumption 阶段产物）；本问按「变量保留、最优解允许取 0」执行 | 团队勘误 E3；权威回写待 `cross_question_review`（结转 warning） |
| **D10 文献缺口** | 「5000 kW 作用侧」为 `team_decision`（口径丙），prob01/02/03 三池均无一条涉及 | 无 | 代码按口径丙实现；本文件**不声称**文献支撑 | 团队裁定 D10 第 4 条 + `shared/literature.md` |
| **R5** | 购电上限「激活阈值」表述 | 旧登记「低于 10,326 kW 即强制 `q_em > 0`」 | 本问**无购电上限**（AS14），不触发；若后续引入一律用 `β ∈ (4218.75, 4375.00] kW` | prob02 团队裁定 + 团队勘误 R5 |
| **R1** | 表 2 端点储电量语义 | prob01 单日周期恒 6000 kWh | prob03 为**多日滚动切片**：`E_{d,0} = E_{d−1,144}` 随日变化；`build_tables` 的 `table2_note` 已显式区分 prob01 | 团队勘误 R1 |
| **A17 不可移植** | prob02「完全信息 + 无购电上限 ⇒ `q_em ≡ 0`」 | — | **不移植**：本问 `q_em` 由**预报—实际光伏误差**在结算层产生（T7 后 14 天链 14/14 天非零、`Σq_em = 4,992.07 kWh`） | `dependency_graph.yaml` 的 `not_portable`；引理 L1/L2 |
| **N1（前稿新增；本动作按 T7 更新，**已被 T7 消除**）** | formulation §6.11 称「由正的吞吐成本 `1 − η² = 0.19` 可知最优解不取同充放，sanity 须统计并**期望 0**」 | 期望同充放 = 0 | 前稿（T7 前）实测不为 0：14 天链 13/2016 时段（0.64%）、34 天链 19/4896；根因是调整层目标只含偏差结算、不含购电成本，同充放在该层无货币成本。**T7-1 生效后（前稿记「未裁定的 D3」已作废）：14 天链与 34 天链的同充放时段数均为 `0/2016`、`0/4896`** —— 团队 F4/T7 的判断被证实：冻结 tie-breaking 即消除该退化。`statistics.simultaneous_charge_discharge_periods` 仍逐次落盘供 sanity 回归 | formulation §6.11 的「期望 0」现已成立；sanity 若见非零须按 T7-3 的「同吞吐量下多重最优」归因，不得判模型失败（§5.1 硬约束清单不含该项） |
| **N5（本动作新增，T7 ε 口径差异）** | 团队 T7-1 写 `ε = 1e-6 × 主目标尺度` | 字面取 `ε = 1e-6·P*` | 该字面值与同句「取足够小以保证不改变主目标最优值」**自相矛盾**：次目标总量 `ε·Σ(c+q_dis)` 的上界为 `ε·n·(c_cap+q_dis_cap)`，而 `n·(c_cap+q_dis_cap) ≈ 2.3e5`，故 `ε·T` 会与 `P*` 同量级（计划层 ε≈58 元/kWh，次目标可达 1e5 元）。本实现把 ε **相对化**为无量纲权重 `ε = 1e-6 × max(\|P*\|,1) / [n·(c_cap+q_dis_cap)]`（`T7_EPS_RELATIVE`），使次目标总量恒 ≤ `1e-6`·主目标尺度；并在数值上进一步发现：调整层 `P*` 小到与对偶容差同量级时，字面加权式会被 HiGHS 忽略（`weighted_sum_effective_layers` 只覆盖约一半层），故**提交解改用 T7-1 优先序的精确实现**——在主目标最优面 `{primary ≤ P* + 5e-10·max(\|P*\|,1)}` 上最小化吞吐量；字面加权式仍逐层求解并落盘作诊断对照（`weighted_*` 字段） | T7-1 的「同一目标」字面式与 T7-2 的 `≤1e-9` 在浮点下不可兼得；本动作按 T7 **优先序语义**（主目标优先、其次吞吐量最小）实现并逐层披露，冲突点已记入响应 `findings`/`warnings`，供团队在 T7 正文层面确认 |
| **N2（本动作新增）** | AS08 称「`q_em` 仅补足负载缺口、不得用于储能充电（在最优解处不改变结果，但变量与触发保留）」 | 期望 `q_em` 与 `c` 同为正的时段数很小/为 0 | 实测 34 天链 **435/4896 时段**（T7 前为 462）`q_em > 0` 且 `c > 0`（14 天链 189/2016）。这是 A19 信息结构的**必然后果**：`c` 由预报驱动的已提交轨迹决定、`q_em` 由附件 2 实际值事后闭合，二者不同层；LP 内无法在结算层「不把 `q_em` 用于充电」。按 D7-A 的落地方式（声明 + 事后统计）保留，`statistics.periods_with_q_em_and_charge` 落盘 | sanity 只作统计与归因（C9 可解释性），不得判为 AS08 违反 |
| **N3（本动作新增，解析界口径修正）** | formulation §3.12 给出的构造上界为 `C_total ≤ Σ p·max(0, (L − PV^act)Δt)`（计划即实际、无偏差、无紧急） | 视为有效上界 | 该式在 prob03 三层结构下**不能保证**是上界（计划用 `Π_0`、结算用 `PV^act`，`C_adj`/`C_em` 可正）。本实现改用**可证明成立**的构造上界：无储能可行策略 `c = q_dis = 0`、`b = max(0, LΔt − Π_0Δt)`、`q = max(0, LΔt − Π_{ν(i)}Δt)` ⇒ `C_plan(opt) ≤ Σp·b_policy`、各调整层目标 ≤ 该层 `R_m` 上的策略偏差费用（故 `C_adj ≤ Σ_m policy_cost(R_m)`，对重叠时段重复计入、**宽松但严格**）、`C_em ≤ Σ5p·q_em_policy`；下界用可推导形式 `p_min·[N_req + 0.19Σc + η(E_T − E_{2/1,0}) − Σq_em]`。formulation 的旧式仍作**参考量**落盘（`bounds.delivery_formulation_reference_no_storage_actual_yuan`） | 数值见 §6 探针 4；建议 formulation 下一版同步该解析界写法（本动作不改 accepted 文件） |
| **N4（填报尾列口径登记）** | formulation §7.3 只显式规定 `调整购电量` 的末两列为 `Σq` 与 `C_total`，未规定 `计划购电量` 的末两列 | 未定 | 本实现取 `计划购电量` 末两列 = `Σb` 与 `C_total`（"全天购电量"按本表列语义、`全天购电费` 按 D8-A 的全天总费用口径，两表可比）。若团队要求该表填 `C_plan`，只需改 `fill_result3_workbook` 的入参（不影响任何数值与恒等式） | sanity/论文引用时须按本口径；已在响应 warnings 登记 |

---

## 2. 代码结构与职责

目录：`problems/microgrid_2025/prob03/versions/assumption_v001/code/`（当前 accepted 版本内可迭代；输出目录另行保留）

| 文件 | 职责 | 主要接口 |
|---|---|---|
| `prob03_io.py` | 读附件 1（只留电价列 + 表头/行数/正电价校验）、读附件 2（两工作表、日期连续性、非负有限性）、读附件 3（日期前向填充 + `2025-1-1` 规范化 + 4 个发布时刻升序校验，返回 `(365,4,24)` 张量）、读模板标签、把交付解填入 `result3.xlsx` 四个工作表、写 JSON（禁 NaN/Inf） | `read_attachment1/2/3`、`inspect_template`、`fill_result3_workbook`、`write_json`、`delivery_dates`、`canonical_date` |
| `prob03_model.py` | 降尺度算子 `Π_m`、支配映射、计划层/调整层 LP 构造与求解、**T7 统一 tie-breaking 的共享算子（基线 → 字面加权 → 字典序提交解 → 退化探测）**、`M1` 顺序递推、闭式结算、指标/恒等式/硬检查/统计量、区间标签与紧急购电区间合并 | `downscale`、`dominance_map`、`solve_plan_layer`、`solve_adjustment_layer`、`_solve_with_tiebreak`、`tiebreak_epsilon`、`throughput_coefficients`、`throughput_scale`、`TiebreakRecord`、`run_m1`、`evaluate`、`emergency_intervals`、`interval_label`、`LayerFailure`、`BudgetExceeded` |
| `run_prob03.py` | CLI 入口：解析参数、读入并校验、构造各层预报矩阵、执行 `M1`、构造表 1/表 2/表 3、**落盘 T7 审计**、按模式写产物、以退出码表达失败语义 | `main`（`--data/--data2/--data3/--template/--output/--days/--time-limit/--max-wall-seconds`）、`build_tables`、`build_layer_inputs`、`build_t7_audit` |
| `task_config.yaml` | task 级配置（`compute`/`solver` + T7 口径与 LP 次数说明），提交时作为 `--config-path` | – |
| `task_spec.yaml` | 隔离计算 task 的完整规格（命令、路径、超时、期望产物、失败条件、T7 验收提示） | – |

代码文件 sha256（本动作终稿，`act-e0c8ef301bda49eb`；`prob03_io.py`/`prob03_model.py`/两个 yaml 未改动，
`run_prob03.py` 仅改 LP 计数常量，见 §11）：

| 文件 | sha256 |
|---|---|
| `prob03_io.py` | `3d708a0919abe4ade942f9dc8da57dd4c6f5140297302cfcc9104662ce0aff8b` |
| `prob03_model.py` | `e5c88c94eb07fccbdb651929b74c51ec46a4717f33dbbcc18d8ffe5866c07f19` |
| `run_prob03.py` | `e80ade246ed65204d5e27ede410e3b127dad7e399709757f73df622dc9167fca` |
| `task_config.yaml` | `f450746e3a5a2a22380b07ce9f439fe1c755a67d94fa8e858f60db08f20b4e24` |
| `task_spec.yaml` | `a05077ca4809555ea76aa41d7de6fc28c4112ea698b91676393378eba97b4a95` |

代码目录的 harness 指纹（`automm.common.hash_path(".../code")`，与 task ID 同源；忽略 `__pycache__`）：
`a846b34adf38938be11300d86841d655fac7bef938acaade69845be77a767665`（前序动作 `b636d768…`，再前稿 `3bb8d235…`）

### 2.1 模型规模（与 formulation §3.11 一致，探针逐项复核）

| 层（每日） | 连续变量 | 等式约束 | 不等式 | 说明 |
|---|---|---|---|---|
| 计划层 `(PL_d)` | 720 | 288 | 0 | `b, c, q_dis, s, E` 各 144 |
| 调整层 `m = 6` | 756 | 216 | 216 | 追加 `u⁺, u⁻` 各 108 |
| 调整层 `m = 12` | 504 | 144 | 144 | 同上 |
| 调整层 `m = 18` | 252 | 72 | 72 | 同上 |
| **单日合计** | **2,232** | **720** | **432** | **4 次层求解/日** |
| **全年（365 天）** | — | — | — | **1,460 次层求解**（不堆叠为单一大 LP，符合 F1） |
| **T7 后每层名义 LP 调用** | — | — | — | **4 次**：① 纯主目标基线 ② T7-1 字面加权 ③ 字典序提交解 ④ T7-3 最优面吞吐量上界探测 |
| **全年（365 天，T7 后）** | — | — | — | **5,840 次名义 LP 调用**（T7-2 若触发 ε 收缩，每次加 1，有界于 `T7_MAX_SHRINKS=8`） |
| 整数变量 | **0** | — | — | 主口径为 LP，无 Big-M |

- `run_manifest.matrix_scale`（含 `lp_solver_invocations_nominal`）与 `solver_status.json.lp_calls` 会按实际 `days` 落盘；探针已核对与上表逐项一致（§6 探针 3）。
- 内存：逐日数组 ≤ 12 × 365 × 144 × 8 B ≈ 5 MB；`solution.json` 的 52,560 × 12 序列约 15–25 MB；远低于 2 GB/worker。

---

## 3. 运行环境与求解器

- 求解器：`scipy.optimize.linprog(method="highs")`，`presolve=True`，**单层** `time_limit = 60 s`（CLI `--time-limit`），整链墙钟预算 `--max-wall-seconds 1500`（超限抛 `BudgetExceeded` → exit 2，保留已完成层证据，不伪报完成）。
- **CPU 求解，不使用 GPU**（`device=cpu`、`gpu_required=false`）：不占用单卡 GPU 串行额度；本问无 torch/CUDA 依赖，**未安装或升级任何 GPU 依赖**，也未调用 `nvidia-smi`。
- 确定性 LP，无随机性：`seed=null`，代码不读取任何随机源；同输入/同版本必须复现同一目标值。
- 解释器：项目 venv（`.venv/Scripts/python.exe`，Python 3.14.4；numpy 2.5.2、scipy 1.18.1、openpyxl 3.1.5）。
- 资源实测（本动作探针，`act-e0c8ef301bda49eb`）：`M1` 14 天 / 56 层（**224** 次名义 LP，含 T7 四段式）**1.80 s**；34 天端到端（136 层 / **544** 次名义 LP，含结算、`t7_tiebreak.json` 与 `probe_result3.xlsx` 填报）**wall 4.09–5.27 s**（两次运行），其中层求解合计 `1.41 s`；按此外推 365 天 / **5,840** 次名义 LP 约 **20 s 求解 + 序列/填报落盘**，预期 < 120 s，`--max-wall-seconds 1500` 与 task timeout 1800 s 余量 ≥ 1 个数量级。

---

## 4. I/O 契约

### 4.1 输入（只读；md5 由本动作实测，见 `evidence/input_md5_check.txt`）

- `data/附件1.xlsx`：`Sheet1` 145×4（表头 + 144 行）；md5 `dbe06f92517431228efcc26e3e796ef9`。
  **本问只用第 2 列（电价，∈ [0.3713, 1.3952] 元/kWh，逐日重复 365 次）**；第 3/4 列仅参与表头结构校验，数值不进入模型。
  时间列首行 `00:10`、末行字符串 `0:00+1`、位置 60 为 `10:00`（AS01 左端点口径实测）。
- `data/附件2.xlsx`：`小区负载`、`光伏发电实际功率` 各 366×145（表头 + 365 天 × 144 点）；md5 `bb3e493f804678de571575116eca1ae6`；
  日期 2025-01-01…12-31 连续；负载 ∈ [1995.7176, 7978.8849] kW、光伏 ∈ [0, 10216.2] kW，无 NaN/负值。
- `data/附件3.xlsx`：`Sheet1` 1461×26（表头 + 1460 数据行 = 365 天 × 4 发布时刻）；md5 `e8dfee653d53a78c82198f657a01feb4`；
  `预报时刻` 为字符串 `0:00/6:00/12:00/18:00`（每天恰 4 行、升序）；**日期列只在每日 0:00 行出现（其余为空白字符串），
  实现按前向填充并把 `2025-1-1` 规范为 `2025-01-01`**；预报 ∈ [0, 9995.8875] kW；2025-12-31 18:00 行的 `预报19–24小时`
  = `5981.55 / 4577.1388 / 2956.0866 / 1671.3 / 0.6958 / 0`（跨年项实证）。
- `data/附件5/result3.xlsx`（模板，只读）：md5 `75be588e714646dde3102aa102382347`，无合并单元格；四工作表
  `计划购电量`/`调整购电量`（各 335×147，列标签 `0:10-0:20 … 23:50-0:00+1`、末列 `0:00-0:10+1`，末两列 `全天购电量`/`全天购电费`；
  日期 2025-02-01…12-31）、`充放电量`（26×6，六块 `0:00-4:00 … 20:00-24:00`，模板用 `⁝` 压缩，`时刻` 前两行为 `00:00:00`/`24:00`）、
  `紧急购电量`（11×3，表头 `日期/购电时间段/购电量`，模板用 `⁝` 压缩）。
- `input_path` 取 `data/`（整目录参与 `input_hash`），因此附件 1/2/3 或模板变化会使 task ID 改变。

### 4.2 输出（正式模式，写入 `output_directory`）

| 文件 | 内容 |
|---|---|
| `result3.xlsx` | 四个工作表：`计划购电量`（`b` + `Σb` + `C_total`）、`调整购电量`（`q` + `Σq` + `C_total`）、`充放电量`（334 天 × 6 块，前两行载 `E_{d,0}`/`E_{d,144}`）、`紧急购电量`（每日 ≥ 1 行，合并区间）。**保存前经 `_residual_report` 逐格复核「应空却仍有值」，非空即硬门禁失败（exit 4）** |
| `solver_status.json` | `status/message/model/lp_calls/lp_solver_invocations_nominal/layer_status_max/layer_*_residual_max/layer_*_residual_relative_max/layer_seconds_total/wall_seconds/objective_yuan/delivery_cost_yuan/feasible_incumbent/device/gpu_required/seed` + `t7_tiebreak`（T7 摘要） |
| `solution.json` | `objective_yuan`、三项分项、`delivery`（交付期分项与总量）、`totals`、`identities`（逐日最大残差 + 全期 + 交付期切片）、`bounds`、`statistics`、`t7_tiebreak`（T7 摘要）、`daily`（逐日 365 条）、逐条 `checks`（含 3 条 T7 硬检查）、`layer_summary`（1,460 条逐层记录）、52,560 时段 × 12 列 `series` |
| `t7_tiebreak.json` | **团队 T7 专项审计**：`policy/rule/epsilon_definition/eps_relative/invariance_tol`、`summary`（见下）、`checks`（T7 三条）、`per_layer`（1,460 条：`primary_before/after`、`primary_relative_change`、`epsilon`、`shrinks`、`invariance_passed`、`throughput_*`、`weighted_*`、`committed_solution`、`degeneracy_degree`、`throughput_upper_on_optimal_face_kwh`、`throughput_unique`、`boundary_state_kwh`、`baseline_state_change_max_kwh`）、`m8_fairness_note`（T7-5） |
| `tables.json` | 表 1/表 2/表 3（4 个指定日期）+ 表 1 标签校验结论 + 相位/端点/表 4 属格式示例的说明 |
| `run_manifest.json` | 版本/模型/参数/输入 md5（附件 1/2/3、模板）/代码 sha256/环境/`task_id`/`matrix_scale`（含 `lp_solver_invocations_nominal`）/`layer_inputs`（各层预报指纹与 NaN 覆盖）/`t7_tiebreak`/`checks_failed`/`statistics`/`outcome` |

探针模式（`--days < 365`）**不写** `result3.xlsx`，改写 `probe_result3.xlsx`，并在 manifest 标 `probe_mode=true`；`--days ≤ 31` 时交付期为空，则不写任何 xlsx。

---

## 5. 硬约束与失败条件

`solution.json.checks` 逐条检查（阈值：求解器内部层残差**绝对** `1e-6` + **相对** `1e-8`，其余 `1e-6`；探针模式跳过解析界与量级四项）：

- 求解：`layer_status_max = 0`（全部 1,460 次层求解均 Optimal；含 T7 四段式共 5,840 次名义 LP 调用）、各层等式/不等式/界残差；
  **层残差区分两类量**：① `layer_equality_residual_max` / `layer_inequality_residual_max` 是**求解器内部**的
  `‖A x − b‖∞`（绝对门槛 `1e-6`，与 AS 的「等式残差 ≤1e-6」一致；HiGHS 默认 `primal_feasibility_tolerance = 1e-7`），
  并配 `layer_equality_residual_relative_max` / `layer_inequality_residual_relative_max`
  （`‖A x−b‖∞ / (‖A‖∞·‖x‖∞ + ‖b‖∞)` ≤ `1e-8`）；② formulation §4.3 的「**各层余额残差 ≤1e-8**」由**提交解重算**的
  `layer_spill_upper_violation` / `layer_spill_lower_violation` 承担（阈值 `BALANCE_TOL = 1e-8`，实测 `4.55e-13` / `2.27e-13`）。
- 结构：`cross_day_continuity`（I4d）、`state_transition_residual`（I5d）、`settlement_balance_residual`（I6d）、层内弃光界（L3，上下界两向）；
- 边界：`E ∈ [1200,10800]`、`c ≤ 833.3333`、`q_dis ≤ 750.0000`、`0 ≤ s' ≤ PV^act·Δt`、`b/q/q_em ≥ 0`、`q = b`（`i ≤ 36`）、
  `max_side_power_kw ≤ 5000`（并网点侧/电池侧四路换算）；
- 恒等式：`(I1d)`、`(I2d)`（逐日最大残差）+ 交付期切片两条 + 费用分解 `(R6d)`；
- **团队 T7 硬检查（T7-2）**：`t7_primary_invariance_max_relative_change ≤ 1e-9`（逐层最大相对变化）、
  `t7_invariance_all_layers_passed`（全部 1,460 层 `invariance_passed=true`）、`t7_epsilon_below_primary_scale`
  （ε 为无量纲相对权重 < 1）；未通过即 exit 4 并路由 `needs_revision`。
  T7-3 的 `degenerate_layers` / `layers_with_remaining_multiplicity` 只作**报告**（结构性事实，不作硬失败）。
- 正式模式另加**解析下界** `p_min·[N_req + 0.19Σc + ηΔE − Σq_em]`、**构造上界**（无储能可行策略，见 N3）
  与**量级带**（交付期 `3×10⁶–5×10⁷` 元、日均 `5×10³–2×10⁵` 元，防 D9 的 Δt 误乘）。
- **不作硬失败**的量（落 `statistics`）：同充放时段数与电量（N1）、`q_em` 与 `c` 同正时段数（N2）、紧急购电天数/时段数、偏离天数。
- 填报格式硬门禁：`fill_result3_workbook` 返回的 `format_residuals` 必须为空；非空则把 `result3_format_residuals`
  计入 `checks_failed` 并以 exit 4 结束（防 openpyxl `cell(value=None)` 静默 no-op 让模板残留值进入答案文件）。

退出码语义：`0` 成功；`2` 某层 LP 非最优或墙钟预算耗尽（写 `solver_status.json`、`feasible_incumbent=false`，**不伪报最优**）；
`3` 输入/模板结构不符；`4` 硬检查或表 1 标签校验失败（**仍写出全部产物**再返回，便于 sanity 定位）；其余未捕获异常按 `code_runtime`。

---

## 6. 静态检查与小型探针（本动作实测，全部只写 action evidence 目录）

证据目录：本动作 `runtime/actions/act-e0c8ef301bda49eb/evidence/`（其中 1、3、6、7、8 项在本动作重跑/重产；
输入/模板探针（2）、解析界探针（4）、全时域静态探针（5）保持前序动作 `runtime/actions/act-06c999a94813435f/evidence/` 的产物未变，
本动作只读复核其结论）；`code_and_input_hashes.txt` 记录本动作终稿的逐文件 sha256 与 harness `code_hash`/`input_hash`。

1. **静态检查**：`compileall`（exit 0，`evidence/compileall_out.txt`）；项目 venv 的 `ruff 0.16.5` 对 `code/` 与 `evidence/`
   均 *All checks passed*（`evidence/ruff_out.txt`）；`run_prob03.py --help` exit 0（`evidence/cli_help.txt`）。
   `make_task_spec` 的预检在 PATH 中找不到 ruff（记 `preflight.ruff=unavailable`），其内部只做 compileall，两者不矛盾。
2. **输入/模板结构探针**（`probe_prob03_inputs.py` / `probe_prob03_inputs_out.json`，**15/15 PASS**）：
   附件 1（144 行、电价 ∈ [0.3713,1.3952]、位置 60 = `10:00`）；附件 2（365×144、4 个指定日期索引 78/171/265/354 命中、02-01 索引 31）；
   附件 3（1460 数据行、4 个发布时刻升序、365 天 × 4 行、日期仅首行且前向填充一致、12-31 18:00 的 `k=19..24` 跨年实证）；
   模板四工作表结构与列标签/日期/六块/紧急购电块形。
3. **T7 一致性探针**（`probe_prob03_t7.py` / `probe_prob03_t7_out.json`，**23/23 PASS**，14 天链 + 共享算子单测；
   本动作以同一脚本副本重跑，23 项全通过、`checks_failed=[]`、链级目标 `C_total = 761,322.475606 元` 与各汇总量与
   前序动作逐位一致 ⇒ T7 路径确定可复现）：
   - **T7-1 共享算子**：`throughput_coefficients` 在 `c`/`q_dis` 位置恰为 1（其余 0，Σ=288）、`throughput_scale = n·(c_cap+q_dis_cap) = 228,000`、
     `tiebreak_epsilon` 为无量纲相对权重（例：`P*=58,888 元 → ε = 2.58e-7`）；源码静态核对两个层构造器都调用 `_solve_with_tiebreak`
     且未各自另写目标（T7-5 前提）；
   - **T7-2**：56 层全部 `invariance_passed=true`，`max_primary_relative_change = 5.000e-10 ≤ 1e-9`；字面加权式的相对变化为 **0.0**
     （27/56 层加权式达到字典序最小值）；`total_shrinks = 0`（未触发 ε 收缩）；
   - **T7-3**：56 层全部 `degeneracy_degree > 0`（最大 201），**35/56 层**在主目标最优面上仍存在吞吐量更大的最优轨迹
     （`layers_with_remaining_multiplicity`），已如实报告；提交解吞吐量 `1,439,948.27 → 1,425,095.18 kWh`（减少 `14,853.09 kWh`），
     基线解与提交解的最大逐变量差 `2,177.50 kWh`，层末状态 `boundary_state_kwh` 逐层落盘；
   - **回归**：14 天链 `C_total = 761,322.475606 元`，相对 formulation §8 的**旧（无次目标）**参考值 `761,150.7115249089`
     差 **`2.257e-4`**（< 1e-3）；差异来自 T7 改变了主目标最优面上的取点、经调整层初值与跨日初值传播，属预期；
   - **F2 复验（T7 后）**：结算用 `PV^act` 缩放 0.5 倍重跑，`C_plan`/`C_adj` 逐日差 **0.0**、`E` 轨迹最大差 **0.0**，
     仅 `ΔC_em = +900,686.75 元` ⇒ 决策层与 SOC 轨迹仍与附件 2 实际值无关；
   - **N1 消除**：`statistics.simultaneous_charge_discharge_periods = 0`（14 天链 0/2016；34 天链 0/4896），
     team F4/T7 的判断（冻结 tie-breaking 即消除同充放退化）被证实；N2 的 `periods_with_q_em_and_charge = 189/2016`（34 天 435/4896）；
   - **矩阵规模**：720/288/0、756/216/216、504/144/144、252/72/72 与 §2.1 逐项一致（T7 不改变变量/约束规模）；
   - 结构检查仍全通过（`checks_failed=[]`，结算平衡 `2.27e-13`、状态转移 `2.79e-12`、跨日连续 `0`、I1/I2 逐日 ≤ 1.5e-11）。
4. **解析界探针**（`probe_prob03_bounds.py` / `probe_prob03_bounds_out.json`，34 天链 + `full_horizon=True`，两条必需检查均 PASS）：
   交付期 `C_total = 138,892.261837 元` ∈ `[75,497.013080, 180,014.790992]`（下界/构造上界；上界分解 plan `164,038.978485`
   + adjustment `5,159.700428` + emergency `10,816.112079`）。同窗的 `magnitude_delivery_band` 预期不通过（交付期仅 3 天），
   已在探针 JSON 与 §9 登记，**量级带只在 365 天正式计算中检验**。
5. **全时域静态探针（不求解任何 LP）**（`probe_prob03_static_full.py` / `probe_prob03_static_full_out.json`，**11/11 PASS**）：
   365 天降尺度覆盖/跨年结构与静态核对一致；把解析无储能策略喂入 `fill_result3_workbook` 填满 **334 天**交付长度 →
   `计划购电量`/`调整购电量` 各 **335×147**、`充放电量` **2005** 行（日期只写块首行、`时刻/储电量` 只写每日前两行）、
   `紧急购电量` **748** 行（≥334）；`format_residuals = []`、全簿无 `⁝`；计划/调整首格与末两列、储电量端点均可逐格回溯内部数组。
6. **截断窗端到端探针**（`--days 34 --time-limit 60 --max-wall-seconds 1500`，输出 `evidence/probe_run_d34/`，本动作重跑）：
   exit 0、`checks_failed=[]`、136 次层求解 / **544 次名义 LP**（4 次/层 × 136 层）、wall **4.09–5.27 s**（两次运行）、
   `C_total = 1,777,452.071413 元`、交付期 `138,892.261837 元`、
   交付期 `Σq_em = 2,105.17 kWh`、交付期 `Σs' = 9,515.79 kWh`、`E_T = 1200.0`；`t7_tiebreak.json` 落盘
   （136 条逐层记录、`checks_failed=[]`、T7 主目标最大相对变化 `5.000e-10`、吞吐量减少 `27,051.28 kWh`）；
   `probe_result3.xlsx` 填报 `format_residuals=[]`。与前序动作同参数产物的**数值内容逐位一致**
   （`solution.json`/`t7_tiebreak.json`/`tables.json` 去除耗时字段后完全相等，见 `evidence/d34_vs_prior_numeric_diff.txt`），
   唯一差异是本动作修复后的 `matrix_scale`/`lp_solver_invocations_nominal`（408 → 544）与时间戳/墙钟字段。
   该探针数值只是接口自检，**不是交付数值**（截断窗还跳过解析界与量级检查、且 34 天不含 4 个指定日期）。
7. **独立只读扫描**（`probe_run_d34_scan.py` / `probe_run_d34_scan_out.json`）：与 `prob03_io._residual_report` **独立实现**，
   对 `probe_result3.xlsx` 复核列标签/行位置/端点/超行残留/`⁝` → **0 问题**。
8. **task 规格预演**（`task_spec_dryrun.py`，真实调用 `automm.tasks.make_task_spec`，**不创建 task**；本动作修订后重跑）：
   `task_id = 1b57b1cb92e0d5095518`、`backend = local`、`timeout_seconds = 1800`、`seed = null`、
   `code_hash = a846b34a…`、`config_hash = fd07c6a5…`、`source_config_hash = 5ba829f3…`、
   `input_hash = 4343d799…`（与 prob01/prob02 相同：`input_path = data` 未变）、
   `preflight = {compileall: passed, ruff: unavailable}`、`output_directory` 与 spec 完全一致
   （`evidence/task_spec_dryrun.json`）。**前序动作的 `task_id = 08bcc5e2ab826358e649` / `code_hash = b636d768…`
   与再前稿的 `cb6480f52c44c9695f70` / `3bb8d235…` 均已作废**（代码目录内容改变 ⇒ harness `code_hash` 变化 ⇒ task ID 必须重登记）。
9. 所有探针 JSON 通过 `allow_nan=False` 落盘；`NaN/Infinity` 关键字扫描为空；探针脚本本身也通过 `compileall` 与 `ruff`。

> 说明：`make_task_spec` 的预演只构造 spec，不调用 `submit_task`；implementation 阶段未创建任何 task、
> 未写 `results/` 目录（`problems/.../prob03/versions/assumption_v001/results/` 仍为空，实测条目数 0）。

---

## 7. 交给 computation 阶段的 task 规格

见 `code/task_spec.yaml`（本文件为规格，不由 implementation 执行）。核心命令：

```text
.venv/Scripts/python.exe \
  problems/microgrid_2025/prob03/versions/assumption_v001/code/run_prob03.py \
  --data data/附件1.xlsx --data2 data/附件2.xlsx --data3 data/附件3.xlsx \
  --template data/附件5/result3.xlsx \
  --output problems/microgrid_2025/prob03/versions/assumption_v001/results/prob03_v001_f001_run001 \
  --days 365 --time-limit 60 --max-wall-seconds 1500
```

- `output_directory`：`problems/microgrid_2025/prob03/versions/assumption_v001/results/prob03_v001_f001_run001`
  （本问**首次**正式计算；目录当前为空。若该 task 以 interrupted/timeout/非零退出结束，按重跑纪律改用**新** output_directory
  如 `..._run002`，不得复用/覆盖 run001，并把失败指纹记入后续阶段的 task 记录）。
- `worker_launch_mode`：`supervised`（`config/compute.yaml`，Runner 原地运行 worker）。`detached` 在本 DSH 沙箱环境会被进程树回收
  （prob01 的心跳探针与 task `b87194aa7fada61ee0d8` 的 `interrupted` 已记录），故必须 supervised。
- `input_path`：`data`；`config_path`：`code/task_config.yaml`；`code_path`：`code`；`timeout_seconds`：1800。
- `--output` 必须与 `output_directory` 完全一致（`make_task_spec` 强校验，预演已通过）。
- 资源：CPU、1,460 次层求解 / **5,840 次名义 LP**（预期 < 120 s，含产物落盘）、内存 < 1 GB；`seed=null`；**不占 GPU**；单卡 GPU 串行约束不适用。
- 本次预演（本动作 LP 计数修复后重跑）：`task_id = 1b57b1cb92e0d5095518`、`code_hash = a846b34a…`、`config_hash = fd07c6a5…`、
  `source_config_hash = 5ba829f3…`、`input_hash = 4343d799…`（`evidence/task_spec_dryrun.json`）。
  前序动作 `task_id = 08bcc5e2ab826358e649` / `code_hash = b636d768…` 与再前稿 `cb6480f52c44c9695f70` / `3bb8d235…`
  **均已作废**（不得复用；`output_directory` 仍为 run001 且当前为空）。

---

## 8. 下游要求（sanity / ablation / robustness / visualization）

1. **不比对逐点解唯一性**：调整层目标在偏差为 0 处退化（F4）。T7-1 已在**主目标最优面上**冻结取点规则
   （取吞吐量最小者），但 T7-3 实测仍有大量层存在**同一吞吐量下的多重最优**。sanity 以
   「约束残差 + `(I1d)`–`(I6d)` + 目标值 + 表 1/表 2/表 3 + `result3.xlsx` + `t7_tiebreak.json`」为准，
   不比对逐点解唯一性；若重跑（同 code_hash、同输入），`t7_tiebreak.json` 的 `epsilon`/`primary_*`/`throughput_*`
   必须逐位复现，否则按 `code_runtime` 路由。
2. sanity 必须**两次换算功率**核对两侧 `≤ 5000 kW`（E1），并独立复核 `q_dis ≤ 750.00`、`c ≤ 833.3333`。
3. **同充放（N1）与 `q_em`+`c` 同正（N2）** 已落为 `statistics`：sanity 只作统计与归因，**不得**判为模型失败/AS08 违反；
   tie-breaking 已按团队 **T7-1** 冻结（不再挂 D3），N1 的同充放已降为 `0`（14 天与 34 天链），N2 仍非零且属 A19 信息结构后果。
4. **信息集审计（AS07/H11）**：`layer_inputs` 给出各层预报指纹与 `uses_actual_pv=false`；`series` 区分
   `plan_purchase_kwh`（`b`）与 `final_purchase_kwh`（`q`）；结算层是 `PV^act` 唯一入口。
5. `result3.xlsx` 的 0:00/24:00 是**计划窗首/末状态**（AS01 左端点口径使计划窗为 0:10 → 24:10，模板固有相位），
   prob03 为**多日滚动切片**（`E_{d,0}` 随日变化，**不恒为 6000**）；论文与图注须与 prob01（单日周期、端点恒 6000）显式区分一次（R1）。
6. 论文**必须写入**：题面表 4 的 `2025/3/1` 与 3 个区间及数值是**格式示例**，不是本问答案；本问紧急购电由预报—实际误差驱动。
7. `ablation` 按 B0/B2 在 `ablations/code/` 另建 `M2`–`M8`（不得改动本 `code/`）；**T7-5：`M2`–`M8` 必须复用
   `prob03_model.py` 的 `_solve_with_tiebreak` / `tiebreak_epsilon` / `throughput_coefficients`（或逐字复刻同一 ε 与次目标系数）**，
   否则 `M8 ≡ M1` 的比较失效；`M5` 的 `C5` 单调性按 T7-4 重跑（不得调 ε 或换 tie-break 规则去凑单调性）；
   `M6` 的 Big-M 用 F8 的紧界（`u⁺ ≤ b`、`u⁻ ≤ q_max`）；`M7` 四条口径对照须给全量差额（`C7`）。
   `M3` 的外部锚点 `C10`（prob02 全期 `13,758,182.573724 元`、交付期 `12,233,050.830708 元`，相对差 ≤ 1e-6）必须在同一 tie-breaking 下复现。
8. `robustness` 负责参数扰动与置信区间（`η`、`E_init`、`E` 界、`α_em`、`β_def/β_over`、降尺度规则、负载/光伏扰动），
   与 ablation 的数值不得互相替代（B6）；D10 的多日增量须按本问实际负载/光伏重算。
9. 禁止复用任何 `p·b·Δt` 口径；禁止把 5000 kW 直接当电量上界；禁止使用附件 4、附件 1 的负载/光伏预测列、2026 年数据。
10. **T7 验收**：sanity 须读 `t7_tiebreak.json`，核对 `summary.all_layers_invariance_passed=true`、
    `summary.max_primary_relative_change ≤ 1e-9`、`per_layer` 条数 = 1,460，并把 `t7_tiebreak` 写入论文的
    「模型可实现性与可复现性」小节（T7-1 规则、T7-2 验证、T7-3 退化事实）；`M1` 与 `M8` 的 ε 与次目标系数须逐位一致（T7-5）。

---

## 9. 遗留风险与已知限制

- 截断窗探针（`--days < 365`）只验证接口与求解路径，**不能替代正式计算**：它跳过解析界与量级检查、交付期为空/过短、
  且 `--days 34` 不含 4 个指定日期（表 1/表 2/表 3 为空结构）；**表 1 的 144 时段标签分支只能由 365 天结果覆盖**。
- 全时域静态探针喂入的是**解析可行点**（无储能），只覆盖约束/恒等式/表映射/xlsx 填报路径，不覆盖最优解结构。
- `solution.json` 含 52,560 时段 × 12 列序列（预计 15–25 MB），是 sanity 复核恒等式与跨日连续性的需要；
  下游若只需交付数值，可只读 `totals/identities/delivery/statistics/daily`、`tables.json` 与 `result3.xlsx`。
- **N1/N2/N3/N4** 四条为前稿新增的口径与解析界差异，**N5（T7 ε 口径差异 + 字典序提交解）为本动作新增**，均需 formulation 下一版或团队裁定确认（见 §1.1）；
  本实现按 accepted M1 与团队裁定（含 T7）执行，未越界修改假设或 formulation 正文。
- **T7 的两项已知张力（已披露，不阻塞 computation）**：① T7-1 的字面 ε (`1e-6·P*`) 与「足够小」自相矛盾，本实现相对化为
  `1e-6·P*/T_ref`；② 该相对化 ε 在调整层（`P*` 小）会低于 HiGHS 对偶分辨率，故提交解取「主目标最优面上的吞吐量最小解」，
  字面加权式作逐层诊断对照落盘。两者都**不改变主目标**（逐层相对变化 5.0e-10 ≤ T7-2 阈值），且已写入 `t7_tiebreak.json` 与响应 warnings。
- **T7-3 的结构性事实**：14 天链 56/56 层有退化、35/56 层在固定吞吐量下仍多重最优；该数字在 365 天正式结果中必须继续如实报告，
  **不得**据此判模型失败或强行调 tie-break。
- 未决决策点（D2 的 C2 语义、D4 PLAN-EXP 可实施化、D5 M5 数据接口、D6 M6 规模、D7 披露方式、D8 跨问锚点）
  属 `ablation`/后续版本口径；**D3 的 tie-breaking 已由 T7 冻结**，本实现按 T7 执行。
- `run_manifest.json` 的 `code_sha256` 由脚本自算（按 `*.py` 逐文件 + 目录摘要），与 harness `code_hash`
  （含 `task_config.yaml`/`task_spec.yaml`）算法不同；追踪与 task ID 以 harness 值 `a846b34a…` 为准。
- `make_task_spec` 的 ruff 预检依赖 PATH；若提交环境 PATH 无 ruff，则只做 `compileall`（本动作已用 venv 内 ruff 显式检查通过）。
- 结转技术债：`prob01/assumption_v003/version.yaml` 的 AS08 措辞（C3/E3）、D10 文献缺口、文献池 25 条未逐篇阅读正文
  （15 `abstract_oa` + 10 `metadata`，引用只支撑框架级/机制级主张）、A8（prob04 价格可观测性）均不在本动作处理。

---

## 10. 未越界声明

- 未修改 `assumptions.md`、`version.yaml`、`formulations/` 任何文件、`global_symbols.yaml`、`citations.yaml`、
  `question_manifest.yaml`、`runtime/workflow_state.json`、`data/`、`request/` 与 `prob01/`、`prob02/` 任何产物。
- 未创建/提交任何计算 task、未写 `results/`、未运行 365 天完整计算或完整 MILP/大规模矩阵（本动作最长探针为 `--days 34` 端到端）。
- 本动作只在当前版本 `code/`、`implementation.md` 与本 action 的 `evidence/` 内改动；探针一律只读 `data/`。
- 本动作承接 `resource-manager`（`act-410ecb6936a746cd`）的 `failure_class=code_runtime` 路由：T7-1/T7-2/T7-3/T7-5 由
  前序动作 `act-06c999a94813435f` 补齐，本动作只做只读复核、修复 `run_prob03.py` 的 LP 计数常量（§11.2-3）并重登记指纹；
  未改动 `assumptions.md` 的任何团队裁定文字，也未把 T7 的 ε 口径差异包装为团队已确认结论（已登记为 N5 + warnings）。
- A6/A7/A8/A9 已在 prob03 assumption_v001 裁定/登记，本实现按 accepted 口径执行，未自行更改；
  未把 `α_em = 5`、`β_def/β_over`、降尺度规则、结算/填报口径或 D10「5000 kW 作用侧」包装为文献结论。

---

## 11. 本次同步动作（`act-e0c8ef301bda49eb`）的复核、缺陷修复与重登记

### 11.1 重试原因（Harness 事实）

- 前序动作 `act-06c999a94813435f` 的**实现内容完整**，但其响应在 `artifacts_created` 中把证据文件写成
  `runtime/actions/act-06c999a94813435f/evidence/probe_run_d34/result3.xlsx`，而实际落盘为 `probe_result3.xlsx`
  （探针模式写 `probe_result3.xlsx`，只有正式模式写 `result3.xlsx`；见 §4.2 与 `run_prob03.py` 的 `workbook_name` 分支）。
  `scripts/automm/agent_runtime.py::_validate_response_context` 对该路径调用
  `resolve_project_path(..., must_exist=True)` → `FileNotFoundError`，动作被判 `infrastructure_transient`
  （`recovery.last_fingerprint = ac46cdb56fef5c98dafb`）后重试，即本动作。
- `agents/implementation-agent.md` 的「证据文件纪律」已登记过同族缺陷（实例 `act-56d59165992142b3`）；本动作遵守
  「**要么把文件写出来、要么不要列出**」，响应中列出的每个路径均先落盘后校验存在性。

### 11.2 本动作执行内容

1. **只读复核**：`code/` 五个文件 sha256 与前序动作登记逐位一致（`run_prob03.py` 除外，其变更见第 3 条）；
   `hash_path(".../code")`、`hash_path("data")` 独立复算；T7 探针 **23/23 PASS**、14 天链 `C_total = 761,322.475606 元`；
   34 天端到端 exit 0、`checks_failed=[]`、`C_total = 1,777,452.071413 元`、交付期 `138,892.261837 元`、
   `Σq_em(交付期) = 2,105.17 kWh`、`Σs'(交付期) = 9,515.79 kWh`；与前序动作同参数产物在**去除耗时/时间戳字段后
   数值逐位一致**（`evidence/d34_vs_prior_numeric_diff.txt`：`solution.json`/`t7_tiebreak.json`/`tables.json`
   value-identical，仅 `wall/layer_seconds/created_at/max_wall_seconds` 与下述计数元数据不同）。
2. **重跑静态检查**：`compileall` exit 0、venv `ruff 0.16.5` *All checks passed*、`run_prob03.py --help` exit 0
   （`evidence/compileall_out.txt`、`evidence/ruff_out.txt`、`evidence/cli_help.txt`）。
3. **修复 LP 计数缺陷（本动作唯一代码改动）**：`run_prob03.py` 的 `solver_calls_per_layer` 原为 `3`，其注释只列了
   「① 基线 ② 加权 ③ 退化探测」而漏掉 T7 四段式的「③ 字典序提交解」；`prob03_model._solve_with_tiebreak` 实际每层发出
   **4** 次 LP（基线、字面加权、字典序提交解、最优面退化探测，分别见 `prob03_model.py` 的 `_solve(...)` 调用）。
   修复为 `4` 并补正注释，使 `matrix_scale.lp_solver_invocations_nominal` 从 365 天的 4,380 变为 **5,840**
   （34 天探针 408 → **544**），与 §2.1、`task_spec.yaml`、`task_config.yaml` 的 5,840 一致。
   **该常量只影响规模元数据的汇报，不改变任何目标值、约束、恒等式、解轨迹或交付数值**（修复前后
   `solution.json`/`t7_tiebreak.json`/`tables.json` 逐位相同，只有 `solver_status.json`/`run_manifest.json` 的上述计数字段变化）。
4. **重登记指纹**：`run_prob03.py` sha256 `e5e7a3f2…` → `e80ade24…`；harness `code_hash` `b636d768…` → `a846b34a…`；
   `task_id` `08bcc5e2ab826358e649` → `1b57b1cb92e0d5095518`（`config_hash = fd07c6a5…`、
   `source_config_hash = 5ba829f3…`、`input_hash = 4343d799…` 均未变）；`output_directory` 仍为
   `.../results/prob03_v001_f001_run001`（目录仍为空，未被占用）。
5. **未越界**：未创建/提交任何 task、未写 `results/`、未运行 365 天计算；未改 `assumptions.md`、`version.yaml`、
   `formulations/`、`task_spec.yaml`、`task_config.yaml`（后两者的 5,840 本就正确）与上游 `prob01/`、`prob02/`。

### 11.3 给 sanity / computation 的提醒

- 两个 LP 计数不可混用：`solver_status.lp_calls`（= `layer_solves`，提交解口径）全年 **1,460**；
  `lp_solver_invocations_nominal`（T7 四段式名义值，含基线）全年 **5,840** = 1,460 × 4，
  另有 T7-2 的 ε 收缩额外调用（`t7_tiebreak.summary.total_shrinks`，实测 0）。sanity 应按
  `acceptance_hint` 分别核对这两项，不得把 5,840 当作「层数」或把 1,460 当作「实际 LP 调用数」。
- 前序动作登记的全部口径性结论（N1–N5、T7 两项张力、T7-3 退化事实、C3/E3、D10 文献缺口、R5 激活阈值、R1 端点语义）
  继续有效；本动作未改动其措辞，也未据此修改任何模型口径。
- 本动作的探针数值（14 天 761,322.475606 元、34 天交付期 138,892.261837 元等）仍是**接口与口径自检值**，
  不得作为论文或 sanity 的交付数值；正式数值一律以 computation 阶段隔离 task（supervised worker、独立 output_directory、
  `task_id = 1b57b1cb92e0d5095518`）的产物为准。

---

## 12. 本次同步动作（`act-ed12930b86a54d59`）：computation 失败路由 + 层残差容差修复

### 12.1 Harness 事实（失败来源）

- 动作类型：`route_compute_failure`（P2，agent=`implementation-agent`，stage=`computation`），针对 task
  `1b57b1cb92e0d5095518`（attempt 1）：`status=failed`、`failure_type=process_exit`、`failure_class=code_runtime`、
  `returncode=4`、`feasible_incumbent=true`、wall `39.57 s`。stdout 末行为
  `失败检查=['layer_equality_residual_max', 'layer_inequality_residual_max']`。
- 该 task 写出 run001 全部产物（`outcome=hard_check_failed`），未消费（`consumed=false`）。

### 12.2 诊断（唯一失败原因是容差口径，不是模型/求解缺陷）

1. `solution.json.checks` 共 32 条，**仅 2 条失败**，且都是**求解器内部**残差检查：
   `layer_equality_residual_max = 8.789811545284465e-08`（day 243/hour 18）与
   `layer_inequality_residual_max = 3.5334664971742313e-08`（day 41/hour 6），旧阈值固定 `1e-8`。
2. 二者均 **< 1e-7**（HiGHS 默认 `primal_feasibility_tolerance`）。`code/prob03_model._solve` 只覆盖
   `time_limit`/`presolve`，故 1e-8 的绝对门槛**严格强于求解器自身的可行性保证**，属实现缺陷。
3. formulation §4.3 的「各层余额残差 ≤1e-8」并非这两条：它由**提交解重算**的 `layer_spill_upper_violation =
   4.547473508864641e-13`、`layer_spill_lower_violation = 2.2737367544323206e-13` 承担，**早已通过**（质量差 4~5 个数量级）。
   AS 正文的「等式残差 ≤ 1e-6」与 `layer_bound_violation_max = 6.97e-08`（阈值 1e-6）亦通过；
   `state_transition_residual = 8.79e-08`、`identity_I1_residual = 7.91e-08` 在 1e-6 下同样通过——即同一量级在其它检查中本就合格。

### 12.3 修复（本动作唯一代码改动）

- `prob03_model.py` 常量：`LAYER_TOL = 1e-8` → `LAYER_TOL = 1e-6`（求解器内部残差绝对门槛，= `TOL`）；
  新增 `LAYER_TOL_RELATIVE = 1e-8`（尺度感知相对门槛）与 `BALANCE_TOL = 1e-8`（保留给提交解重算的 `layer_spill_*`）。
- `_residuals` 现返回 5 元组，新增 `_inf_norm` / `_relative_residual`（`‖A x−b‖∞ / max(1, ‖A‖∞‖x‖∞ + ‖b‖∞)`）；
  `LayerRecord` 新增 `equality_residual_relative_max` / `inequality_residual_relative_max`（并落 `as_dict`）；
  `evaluate` 新增两条硬检查 `layer_*_residual_relative_max ≤ 1e-8`，`layer_spill_*` 改用 `BALANCE_TOL`（口径不变）；
  `run_prob03.py` 的 `solver_status.json` 落盘两个新的相对残差字段。
- **该修复只改变「如何判定残差是否可接受」，不改变任何 LP 的目标、约束、变量界、tie-breaking 或解**。

### 12.4 证据（全部在 `runtime/actions/act-ed12930b86a54d59/evidence/`）

1. **只读复核**（`probe_prob03_residual_tolerance.py` / `_out.json`，**9/9 PASS**，1.2 s）：
   失败项恰为两条；`layer_spill_*` 通过；旧阈值 < HiGHS 可行性容差；离线复演两条新判据通过
   （绝对 ≤1e-6 余量 11×/28×；相对上界 `7.32e-11` / `2.94e-11` ≤ 1e-8 余量 >100×）。
2. **最差层精确重放**：由 `solution.json.series.plan_purchase_kwh` + `series.storage_kwh`（e_start）+ 附件 1/2/3
   重建 day 243/hour 18 与 day 41/hour 6 的单层 LP，用**同一** `solve_adjustment_layer` 重解，
   绝对残差**逐位复现**（8.789811545284465e-08 / 3.5334664971742313e-08），实测相对残差
   `1.62e-12` / `1.54e-12`（≪ 1e-8）。（注：`t7_tiebreak.boundary_state_kwh` 是该层**前视末段** E_144，
   不是提交块末端；探针已按提交块重放并交叉核对。）
3. **确定性下界**：调整层 `b_eq` 首行为进入边界 `e_start ∈ [1200, 10800]`，且 `x` 含 `E ∈ [1200, 10800]`，
   故相对残差分母 ≥ `E_MIN = 1200`；以 `e_start = 1200` 重放仍全通过。相对判据对全年 **1,460 层**成立。
4. **34 天端到端回归**（`probe_run_d34_afterfix/`，exit 0、`checks_failed=[]`、
   `C_total = 1,777,452.071413 元`、交付期 `138,892.261837 元`）与修复前同参数产物比较
   （`cmp_d34_afterfix_vs_prior.py` / `_out.txt`，**OK=true**）：`series` 逐位相同、`t7_tiebreak.json` / `tables.json`
   去耗时后**完全相等**；`solution.json` 仅新增 2 条检查与 `layer_summary` 的 2 个相对残差字段，
   共享检查仅**阈值**由 1e-8→1e-6（数值与结论不变）；`solver_status.json` 仅新增 2 字段；
   `run_manifest.json` 仅 `output_directory`/`code_sha256` 变化。
5. **静态检查**：`compileall` exit 0（`compileall_out.txt`）、venv `ruff 0.16.5` *All checks passed*
   （`ruff_out.txt`）、`run_prob03.py --help` exit 0（`cli_help.txt`）。
6. **指纹与重跑规格**（`verify_hashes_and_task_spec_afterfix.py` / `task_spec_dryrun_afterfix.json` /
   `code_and_input_hashes.txt`，**只构造 spec，未创建 task**）：harness `code_hash`
   `a846b34a…` → `927bf1e1…`，`task_id` `1b57b1cb92e0d5095518` → **`c84281b1f49fc30b9ecd`**；
   `config_hash = fd07c6a5…`、`source_config_hash = 5ba829f3…`、`input_hash = 4343d799…` 均未变。

### 12.5 路由与给 computation 的要求

- 失败 task 已在本次 `warning` 响应中被消费（避免同一终态 task 被反复路由）；阶段保持 `computation`，
  由 resource-manager 用**新 task**重跑。run001 已被失败 task 占用（`outcome=hard_check_failed`），
  **不得复用/覆盖**；重跑必须用 `..._run002`（预演 `task_id = c84281b1f49fc30b9ecd`）。
- 预期重跑结果：`checks_failed=[]`、`outcome=completed`、exit 0；两条层残差绝对值与 run001 **逐位相同**
  （求解路径未变、模型确定性），且新增两条相对残差检查通过。
- 修复只涉及硬检查阈值口径；**N1–N5、T7 全部裁定与 T7-3 退化事实、D9/D10 口径、R1 相位说明继续有效**。

---

## 13. 本次同步动作（`act-1d13382f65c349a6`）：团队勘误 R9/R10 修复后的规格与指纹重登记

### 13.1 Harness 事实与团队口径（效力最高，先读后做）

- 动作类型：`run_agent`（P5，agent=`implementation-agent`，stage=`implementation`）。触发原因（`runtime/workflow_state.json.last_action`）：
  团队对交付件的合规审查（`assumptions.md` 末节**团队勘误 R9/R10**，2026-09-11）发现 `run001`/`run002` 的 `result3.xlsx`
  两处**必修呈现缺陷并已改代码**；代码目录内容变化 ⇒ 已登记的 `code_hash`/`task_id` 过期，故退回 `implementation`
  **重新登记规格与指纹**；`code/task_spec.yaml` 的 `output_directory` 已由团队改为 `..._run003`。
- 本动作已先读 `assumptions.md` 末尾的**团队裁定 B0–B7、T5–T9** 与**团队勘误 R9–R13、E1–E5**，并逐项按团队口径执行。
- **冲突点与差异（显式记录，不静默沿用旧登记）**：
  1. 本文档 §7、§11.5、§12.5 曾把 `..._run001`/`..._run002` 写成待跑目录；**以团队勘误为准**：`run001`/`run002`
     均已落盘且**仍含 R9/R10 缺陷**，只作**审计产物与负对照**保留（不删除、不覆盖），
     **论文与表 1/2/3 一律以修复后的 `run003` 为准**。`run003` 是唯一合法交付目录。
  2. §11 曾登记 `task_id = 1b57b1cb92e0d5095518`、§12 曾登记 `task_id = c84281b1f49fc30b9ecd`：两者（连同
     `08bcc5e2ab826358e649` / `cb6480f52c44c9695f70`）**全部作废**，见 §13.4 的新指纹。
  3. `T7-1` 的 `ε` 口径按 **T9 更正 1/2** 执行（相对化 + **提交解取字典序**、加权式降为诊断），与 §11/§12 一致，未改。
  4. `R11`（问题 3 比问题 2 贵 18.9% 必须解释为「预报误差的代价」、不得声称更省）、`R12`
     （`periods_with_q_em_and_charge` 的机制解释）、`R13`（prob02/prob03 的 0:00 储电量不可直接互比）
     属**下游必须披露项**，本动作不代写，登记为交接要求（§13.5）。
  5. `C3/E3`（prob01 `AS08`「必然被激活」措辞）、`D10`「5000 kW 作用侧」文献缺口、`R5`/`R1` 表述纪律
     **继续结转**，权威回写待 `cross_question_review`；本动作不越界代改。

### 13.2 团队已落地的代码改动（本动作复核确认，非本动作新写）

| 缺陷 | 代码位置 | 本动作复核结论 |
|---|---|---|
| **R9** 区间标签两端风格不一致（`06:10-9:20`） | `prob03_model.py::interval_label`：两端统一走 `_format_minutes()` 的 `H:MM`（小时不补零） | 已确认；`prob03_io._assign()` 不再依赖 `strftime("%H:%M")` 的补零串 |
| **R10** 交付值表观越界 + 超长小数 | `prob03_io.py`：`DELIVERY_DECIMALS=6`、`_num()`（6 位小数）、`_state()`（规整后投影到 `[1200,10800]` 并记 `storage_projection`）、`_assign()`（`value=None` 真正清空，防 openpyxl 静默 no-op） | 已确认；`fill_result3_workbook` 的 4 处数值写入与 2 处储电量写入均已走 `_num`/`_state` |

> 两处均属**呈现层**修复：不改变任何 LP 的目标、约束、变量界、tie-breaking 或解，见 §13.3 的一致性证据。

### 13.3 本动作执行的静态检查与小探针（全部落盘本动作 `evidence/`）

1. **静态检查**（`evidence/`）：
   - `python -m compileall -q code/` → `exit_code=0`（`compileall_out.txt`）；
   - 项目 venv `ruff 0.16.5 check code/ evidence/` → *All checks passed*（`ruff_out.txt`）；
   - `run_prob03.py --help` → `exit_code=0`（`cli_help.txt`）。
   - `make_task_spec` 的预检仍记 `preflight.ruff=unavailable`（PATH 无 ruff，内部只做 compileall），与本动作 venv 显式
     ruff 通过不矛盾。
2. **34 天端到端探针**（`evidence/probe_run_d34/`、`probe_run_log.txt`，`exit_code=0`、`checks_failed=[]`）：
   `days=34 periods=4896 LP=136`、`C_total = 1,777,452.0714 元`、交付期 `138,892.2618 元`、`Σb = 2,677,738.6332 kWh`、
   `Σq = 2,730,694.8090 kWh`、`Σq_em = 17,183.729689 kWh`、`Σs' = 75,270.3522 kWh`、
   **T7 主目标最大相对变化 `5.000e-10` ≤ `1e-9`（全部通过）**、吞吐量 `3,438,721.6147 → 3,411,670.3385 kWh`。
   与 §11/§12 登记的**同参数修复前**数值逐位一致（`1,777,452.071413` 元 / `138,892.261837` 元）⇒ R9/R10 修复**未改变解**。
3. **R9/R10 闭合扫描**（`probe_r9r10_scan.py` / `probe_r9r10_scan_out.json`，只读 openpyxl）：

   | 指标 | `run002`（修复前，负对照） | 34 天探针（修复后） |
   |---|---|---|
   | 紧急购电区间标签总数 | 2,270 | 19 |
   | **起始小时补零/格式不合规标签数** | **874** | **0** |
   | 小数位 > 6 的数值单元格数 | 55,463（最大 **25** 位） | **0**（最大 **6** 位） |
   | 储电量越界（< 1200 或 > 10800）单元格数 | **152**（最小 `1199.999999997668`） | **0**（最小/最大 = `1200.0`） |
   | `run_manifest.workbook_info.format_residuals` | `[]`（旧版无该字段体系） | `[]` |
   | `delivery_decimals` / `storage_projection` | 无（旧版代码） | `6` / `max_abs_correction = 2.3321717890212312e-09`（6 格，投影到 `[1200,10800]`） |

   修复后样例标签 `6:10-9:20`（与附件 5 模板 `9:50-10:00` 同风格），符合 **R9**；储电量最小修正量 `2.3e-9 kWh` 属求解器容差量级，
   符合 **R10**「仅呈现、数值与结论不变」。
   > 计数方法说明：本动作用 `Decimal(str(v))` 的指数统计小数位（故最大位数为 25），团队勘误的 `46,510` 是「带 `1e-12` 级噪声的单元」口径；
   > 两者测的是同一现象，**修复后同为 0** 才是判据。

### 13.4 重新登记的指纹与 task 规格（`evidence/code_and_input_hashes.txt`、`task_spec_dryrun.json`；**只构造 spec，未创建 task**）

| 项 | 修复前（`run002`，已作废） | **本动作重登记（`run003`）** |
|---|---|---|
| `code_hash` | `927bf1e1d2f60f6f6f19051ee20fa21dff0fa3ebb6295d7becd8b369542e40f9` | **`5bab4f2625a398fec85e9560afe1cf0a7a6a71db80455bcde720973ca6c38015`** |
| `task_id` | `c84281b1f49fc30b9ecd` | **`6de708bbd2d3dd273013`** |
| `output_directory` | `..._run002` | **`.../results/prob03_v001_f001_run003`** |
| 逐文件 sha256（`code/*.py`） | — | `prob03_io.py` `fb8b5eb4d3473f2232ed5a82d9d44c477ef5103df7dc5a90ea1b73f79d0b3980`；`prob03_model.py` `43aa60b7fe0028c5a3ee66e55f0ec9fb4250897441a38a5dbb4428e4a08f5fc9`；`run_prob03.py` `74e5cb6e6b23b2f7cba7048c9ce3fc90b417f3a7c4da5783e00c8a09972fcd7e` |
| `config_hash` / `source_config_hash` / `input_hash` | `fd07c6a574c0fac49eb140451650168bbdbaa4948161c138485db6e3bcaa00a9` / `5ba829f3788b7f28be69fba05ca168bc2b22e207a292138e633fe5eff94bff4e` / `4343d799b5830093d7a61d566219e1d2592f5bc39c8b7a9297286fa9e02d9434` | **三者均未变**（改动只在 `prob03_io.py` / `prob03_model.py`，未动 `task_config.yaml` 与 `data/`） |

- `task_spec.yaml` 与 `task_config.yaml` 无需改动：`output_directory`、`command`、`timeout_seconds=1800`、
  `worker_launch_mode=supervised`、`lp_calls=1460` / `lp_solver_invocations_nominal=5840` 均与 T7/T9 口径一致。
- **未越界**：未调用 `submit_task`、未创建/提交任何 task、未写 `results/`、未运行 365 天计算；未改 `assumptions.md`、
  `version.yaml`、`formulations/`、`code/`（团队已改的呈现层除外，本动作只读复核）与上游 `prob01/`、`prob02/`。

### 13.5 交接给 `computation` / `sanity_check` 的硬要求

1. **只用 `run003`**：`output_directory = .../prob03_v001_f001_run003`（当前不存在、未被占用）；`task_id = 6de708bbd2d3dd273013`。
   若该 task 以 `interrupted/timeout/非零退出` 结束，须以**新 attempt + 新 `output_directory`（`..._run004` 等）**重跑，
   不得复用/覆盖 `run001`/`run002`/`run003`，并把失败指纹登记入账。
2. **`run001`/`run002` 不得作为最终答案文件**：二者保留为审计负对照（`run002` 的 `r9_bad_label_count=874`、
   `storage_out_of_bounds=152` 已由本动作独立复现）。
3. **`sanity_check` 必须对 `run003` 的 `result3.xlsx` 重跑逐格 R9/R10 扫描**：紧急购电区间标签起始小时补零数 = 0、
   小数位 > 6 的单元格数 = 0、储电量越界数 = 0、`format_residuals=[]`；并核对 `delivery_decimals=6` 与
   `storage_projection.max_abs_correction_kwh`。
4. **R11/R12/R13 必须在论文/sanity 落地**：R11 说明问题 3 更贵的成因是「决策用附件 3 预报、结算用附件 2 实际」
   且模型无对冲机制（不得写「更省」）；R12 给出 `periods_with_q_em_and_charge` 的机制解释与最小可复现示例；
   R13 显式区分 prob02/prob03 的 0:00 储电量口径（信息集不同，不可直接互比）。
5. **T7/T9 与 N1–N5、R1/R5、D9/D10 全部口径继续有效**；`lp_calls=1460`（提交解）与
   `lp_solver_invocations_nominal=5840`（T7 四段式名义值）不得混用。
6. **资源纪律**：本问为 CPU HiGHS，不占用单卡 GPU；本动作实测可用内存偏低（<1.5 GB），
   `memory_slots=1`、`max_local_concurrent_tasks=1`，不得安排多 worker 并发；one_shot 唤醒模式下 `queued` 属正常排队，
   不得由 resource-manager 在短命 shell 内代跑 `start_queued`。

## 14. 本次同步动作（`act-55f1e3b44dcf4ddf`）：§13 重登记的独立复核与闭合

### 14.1 Harness 事实（为什么会有本动作）

- 本动作类型：`run_agent`（P5，agent=`implementation-agent`，stage=`implementation`）。它是 **§13 动作
  `act-1d13382f65c349a6` 的续作**：后者的**实质工作已全部落盘**（R9/R10 复核、34 天端到端探针、指纹与 task spec 重登记、
  本文件 §13），但**响应因 payload 纪律问题作废** —— `transition.arguments` 多写了 schema 未登记的键 `target_stage_note`
  （`config/agent_response.schema.json` 对每个 command 的 `arguments` 均为 `additionalProperties: false`），
  `jsonschema.validate` 抛错 → action 判 `harness_invariant` → `recovery_status` 被覆写为 `human_blocked`（自锁）。
- 团队随后以 `python scripts/harness.py control RESUME --source cli` 复位 `recovery_status`/`failure_class`（→ `normal`），
  harness 在本动作重新唤醒 implementation Agent（`runtime/transactions.jsonl` 第 256–257 行、`runtime/recovery.jsonl` 末行）。
- **纪律**：本动作**不重复改代码**（§13 的代码与规格即为当前状态），只做**独立只读复核**并把 §13 的登记**落到 commands**；
  所有备注写进 `findings`/`warnings`，**不写进 `arguments`**。

### 14.2 独立复核结果（全部落盘本动作 `runtime/actions/act-55f1e3b44dcf4ddf/evidence/`）

| 判据 | 证据 | 结果 |
|---|---|---|
| `code/` 逐文件 sha256 与 §13.4 登记值逐位一致 | `verify_state_p03.py` / `state_check.json` / `state_check_out.txt` | `prob03_io.py fb8b5eb4…`、`prob03_model.py 43aa60b7…`、`run_prob03.py 74e5cb6e…` **全一致** |
| harness `code_hash` 与 `task_id` | 同上（真实调用 `make_task_spec`，**只构造 spec**） | `code_hash=5bab4f2625a398fec85e9560afe1cf0a7a6a71db80455bcde720973ca6c38015`、`task_id=6de708bbd2d3dd273013`、`output_directory=..._run003`、`config_hash/source_config_hash/input_hash` 未变、`preflight.compileall=passed`（`ruff=unavailable` 同前） |
| `run003` 未被占用 | 同上 | `results/prob03_v001_f001_run003` **不存在** |
| T7/T9 与 R9/R10 落地符号在位 | 同上 | `_solve_with_tiebreak` / `tiebreak_epsilon` / `throughput_coefficients` / `interval_label`；`_num` / `_state` / `_assign` **全在** |
| 静态检查 | `compileall_out.txt` / `ruff_out.txt` / `cli_help.txt` | compileall `exit 0`；venv ruff 0.16.5 对 `code/` 与 `evidence/` **All checks passed**；`--help` `exit 0` |
| 34 天端到端探针（本动作**重跑**，非沿用） | `probe_run_d34/`、`probe_run_log.txt` | `exit_code=0`、`checks_failed=[]`、`outcome=completed`；`C_total=1,777,452.0714 元`、交付期 `138,892.2618 元`、`Σq_em=17,183.729689 kWh`，与 §13.3 **逐位一致**（R9/R10 修复未改变解） |
| T7-1/T7-2/T7-9 落地 | `probe_run_d34/t7_tiebreak.json`、`run_manifest.json` | `max_primary_relative_change=5.000e-10 ≤ 1e-9`、`all_layers_invariance_passed=true`、**`lexicographic_committed_layers=136`、`fallback_committed_layers=0`**、`total_shrinks=0`、`degenerate_layers=136`、`layers_with_remaining_multiplicity=90`、吞吐量 `3,438,721.6147→3,411,670.3385 kWh` |
| R9/R10 闭合（只读 openpyxl） | `probe_r9r10_scan.py` / `probe_r9r10_scan_out.json` | `run002`（负对照）`874 / 152 / 55,463`（最大 25 位小数）→ 修复后 `0 / 0 / 0`（最大 6 位）；`delivery_decimals=6`、`format_residuals=[]`、`storage_projection.max_abs_correction=2.332e-09 kWh` |
| 响应路径无悬空 | `path_check.py` / `path_check_out.txt` | 26 条逐条 `os.path.isfile`，**缺失 0 条** |
| 资源事实 | `resource_probe.txt` | 可用内存 **1.31 GB**、`effective_workers=1`（被 `memory_per_worker_gb=2` 下限强制），不得多 worker 并发 |

### 14.3 结论与交接

- §13 的代码、规格与指纹登记**经本动作独立复现，全部成立**；`implementation` 逻辑产物登记与
  `implementation → computation` 迁移由本动作的 `commands` 请求（`record_artifact` + `transition` + `append_ledger`）。
- 交接要求与 §13.5 **完全相同**（只用 `run003`、`task_id=6de708bbd2d3dd273013`；`run001`/`run002` 只作审计负对照；
  sanity 必须对 `run003` 重跑 R9/R10 逐格扫描；R11/R12/R13 必须在论文/sanity 落地；T7/T9、N1–N5、R1/R5、D9/D10 口径继续有效；
  `lp_calls=1460` 与 `lp_solver_invocations_nominal=5840` 不得混用）。

## 15. 本次同步动作（`act-37dbefc37c0d4c69`）：sanity 退回后的第三次独立复核与迁移重提

### 15.1 Harness 事实（为什么会有本动作）

- 动作类型：`run_agent`（P5，agent=`implementation-agent`，stage=`implementation`，`runtime/transactions.jsonl` 第 263 行）。
- 触发链（**与 §13/§14 的动作不同**）：§14 动作 `act-55f1e3b44dcf4ddf` 于 `08:01:50` 提交
  `implementation → computation` 迁移**成功**；紧接着 `08:01:51` Runner 因「异步计算已结束」唤醒 `sanity-checker`，
  对**修复前**的 `run002`（task `c84281b1f49fc30b9ecd`，已于 `07:45:24` succeeded）执行
  `inspect_compute_result`（动作 `act-d80f5539ff934699`），于 `08:13:41` 判
  **`NEEDS_REVISION` / `failure_type=code_or_runtime` / `return_stage=implementation`**（`question_manifest.yaml`
  `sanity.level_1_4=NEEDS_REVISION`），阶段被路由回 `implementation`，故本动作存在。
- **冲突点与差异（显式记录，不静默沿用旧登记）**：
  1. `run002` 的**数值与口径经 sanity 独立复核确认正确**（`C_total=16,179,176.145228` 元、
     交付期 `14,540,616.335652` 元；平衡 `3.411e-13`、状态转移 `8.79e-8`、`(I1)/(I2) 7.91e-8`），
     但其 `result3.xlsx` **仍含 R9/R10 缺陷**、且 `code_hash` 已被修复后代码取代（团队勘误 R14）
     ⇒ **不得作为交付口径**。本问交付目录唯一合法值为 `..._run003`。
  2. §13.3/§14.2 登记的 `run002` 计数（`874 / 152 / 55,463`）由本动作**第三次独立复现**，逐位一致（§15.2）。
  3. sanity 补充定位的「`tables.json` 表 3 `slot` 标签起始小时补零 **11 条**」**超出团队勘误 R9 原文范围**
     （R9 只写 `result3.xlsx` 的 `紧急购电量` 工作表）：本动作在 `run001` 与 `run002` 的 `tables.json`
     **各自独立复现 11 条**（如 `2025-03-20 的 06:10-10:10`、`2025-06-21 的 04:10-5:00`），确认属同一
     `interval_label()` 根因、由 `run003` 一并修复；**论文表 3 引用时须以修复后文本为准**。
  4. 上游结转（继续有效、本动作不越界代改）：`prob01/assumption_v003/version.yaml` 的 AS08「必然被激活」措辞
     （C3/E3，待 `cross_question_review`）；D10「5000 kW 作用侧」为 `team_decision`、三池文献无一条涉及，
     不得包装为文献支持；R5 激活阈值 `β ∈ (4218.75, 4375.00] kW`（本问 AS14 无购电上限，不触发）；
     R1 表 2 端点语义（prob03 为多日滚动逐日切片，须与 prob01 单日周期恒 6000 显式区分一次）。
  5. `global_symbols.yaml` 的 `q_dis` 域（750.00）与 `q_spill.first_question`（prob01）已由
     problem-decomposer 回写，U1/U2 已闭合；U3 仍未闭合（见第 4 条）。

### 15.2 本动作的独立只读复核（全部落盘 `runtime/actions/act-37dbefc37c0d4c69/evidence/`）

| 判据 | 证据 | 结果 |
|---|---|---|
| `code/` 逐文件 sha256 与 §13.4 登记值逐位一致 | `verify_state_p03.py` / `state_check.json` | `prob03_io.py fb8b5eb4…`、`prob03_model.py 43aa60b7…`、`run_prob03.py 74e5cb6e…` **全一致** |
| harness `code_hash` / `task_id` / `output_directory` | 同上（真实调用 `make_task_spec`，**只构造 spec，未 `submit_task`**） | `code_hash=5bab4f2625a398fec85e9560afe1cf0a7a6a71db80455bcde720973ca6c38015`、`task_id=6de708bbd2d3dd273013`、`output_directory=..._run003`；`config_hash/source_config_hash/input_hash` 三者**未变**；`preflight.compileall=passed`（`ruff=unavailable` 同前） |
| `run003` 未被占用 / `run001`+`run002` 保留 / `run003` task 未创建 | 同上 | `results/prob03_v001_f001_run003` **不存在**；`run001`、`run002` 均在；`runtime/tasks/6de708bbd2d3dd273013` **不存在** |
| `run002` 的终态已消费（不会被重复路由） | 同上 + `runtime/tasks/c84281b1f49fc30b9ecd/status.json` | `status=succeeded`、`returncode=0`、`consumed=true`（`consumed_at=08:13:41`） |
| T7/T9 与 R9/R10 落地符号在位 | 同上 | `_solve_with_tiebreak` / `tiebreak_epsilon` / `throughput_coefficients` / `interval_label` / `_format_minutes`；`_num` / `_state` / `_assign` / `DELIVERY_DECIMALS = 6` **全在** |
| 静态检查 | `compileall_out.txt` / `ruff_out.txt` / `cli_help.txt` | `compileall exit 0`；venv ruff 0.16.5 对 `code/` 与 `evidence/` **All checks passed**；`--help exit 0` |
| 34 天端到端探针（本动作**重跑**） | `probe_run_d34/`、`probe_run_log.txt` | `exit_code=0`、`checks_failed=[]`、`outcome=completed`；`C_total=1,777,452.071413 元`、交付期 `138,892.261837 元`、`Σq_em=17,183.729689 kWh`、`Σs'=75,270.3522 kWh`，与 §13.3 的**同参数修复前**值**逐位一致** ⇒ R9/R10 呈现层修复**未改变解** |
| T7-1/T7-2/T7-9 落地 | `probe_run_d34/t7_tiebreak.json`、`run_manifest.json` | `max_primary_relative_change=5.000005352071037e-10 ≤ 1e-9`、`all_layers_invariance_passed=true`、`lexicographic_committed_layers=136`、`fallback_committed_layers=0`、`total_shrinks=0`、`degenerate_layers=136`、`layers_with_remaining_multiplicity=90`、吞吐量 `3,438,721.6147→3,411,670.3385 kWh` |
| R9/R10 逐格扫描（只读 openpyxl，**三对象**） | `probe_r9r10_scan.py` / `probe_r9r10_scan_out.json` | `run001`、`run002`（负对照）各 **874 / 152 / 55,463**（最大 25 位小数；储电量最小 `1199.999999997668`）→ 修复后探针 **0 / 0 / 0**（最大 6 位，储电量 min=max=`1200.0`）；表 3 表签负对照各 **11** 条 → 修复后 0 条 |
| `interval_label()` 函数级探针 | 同上 | `(0,1)→0:10-0:20`、`(36,55)→6:10-9:20`（= R9 样例）、`(142,143)→23:50-0:00+1`、`(143,144)→0:00+1-0:10+1`、`(36,60)→6:10-10:10`；旧 `strftime("%H:%M")` 风格确为 `06:10` ⇒ **补零侧已消除**，全部 7 项通过 |
| `run_manifest.workbook_info` | `probe_run_d34/run_manifest.json` | `format_residuals=[]`、`delivery_decimals=6`、`storage_projection={bounds [1200,10800], max_abs_correction 2.3321717890212312e-09 kWh, cells 6}` |
| 响应路径无悬空 | `path_check.py` / `path_check_out.json` | 20 条逐条 `os.path.isfile`，**缺失 0 条** |
| 资源事实 | `resource_probe.txt` | 可用内存 **1.7 GB**、`effective_workers=1`（被 `memory_per_worker_gb=2` 下限强制），不得多 worker 并发 |

> 口径说明（自检纠正，避免误判）：`interval_label(labels, start, stop)` 的 `stop` 是 `merge_interval_labels`
> 返回的**开区间右端**，故单次调用必须满足 `start < stop`；标签区间为 `[10(start+1), 10(stop+1))` 分钟，
> 与 AS01「时段 i 覆盖 [10(i+1), 10(i+2))」一致。本动作初次单元探针误用 `start == stop` 的退化入参，
> 已改正为合法区间；这是探针自身的口径错误，**不是代码缺陷**。

### 15.3 结论与交接

- §13/§14 的代码、规格与指纹登记**经本动作第三次独立复现，全部成立**；`run003` 仍为空目录、`task_id=6de708bbd2d3dd273013` 未被创建。
- 本动作**不改 `code/`、不改 `task_spec.yaml`/`task_config.yaml`、不改 `assumptions.md`/`version.yaml`/`formulations/`，
  不创建/不提交 task、不写 `results/`、不运行 365 天计算**（最长为 34 天端到端探针，4.68 s）。
  对 `implementation.md` 的唯一改动是**追加本节 §15**。
- 请求的 commands：`record_artifact(implementation, true)` + `append_ledger` + `transition(target_stage=computation)`；
  交接要求与 §13.5 / §14.3 **完全相同**。
- **payload 纪律（§13 事故的教训，本动作严格遵守）**：`transition.arguments` 只写 `target_stage` 与 `reason` 两个
  schema 逐字列出的键；其余说明一律进 `findings`/`warnings`。

