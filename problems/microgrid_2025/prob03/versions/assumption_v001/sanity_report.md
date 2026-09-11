# Sanity Check Report（sanity_check 阶段正式复核）

- problem_id: `microgrid_2025`
- question_id: `prob03`（问题 3：0:00 计划 + 6:00/12:00/18:00 调整 + 紧急购电）
- assumption_version: `assumption_v001`（accepted；末尾含「待团队选定的决策点 D1–D12」「团队裁定 B0–B7 / T5–T9」「团队勘误 R9–R17 / E1–E7」，效力高于假设正文）
- formulation_version: `formulation_v001`（accepted）
- 复核对象: task `6de708bbd2d3dd273013`（attempt 1、`succeeded`、`returncode=0`、supervised、CPU HiGHS、`probe_mode=false`、days=365 / periods=52560 / model=M1、wall 41.77 s）
- output_directory: `problems/microgrid_2025/prob03/versions/assumption_v001/results/prob03_v001_f001_run003`
- 动作: `act-354d33342edf4e70`（policy **P3** `run_agent`，agent=sanity-checker，stage=**sanity_check**）
- **overall: `PASS_WITH_WARNING`**
- failure_type: `null`；return_to_stage: `null`（无硬门禁失败）
- 被取代的上游报告: computation 阶段 P2 `inspect_compute_result`（动作 `act-36514ddc575b4bdb`）的 `sanity_report.md` 原文逐字节保留在
  `runtime/actions/act-354d33342edf4e70/evidence/prior_sanity_report_backup.md`（55,794 B，sha256 `24CD903636EC02E1A6D81545D42098E9C5924731AA8EBFE5738F767ABACE3DCF`）。

> 本报告由 `sanity-checker` 出具，是 `sanity_check` 阶段的 **L1–L4 正式结论**。L5（跨小问一致性）需所有小问 `locally_completed`（prob04 未开始）；
> L6（robustness/ablation 后复核）需 `robustness` 完成——本动作均不适用（`not_applicable`）。
>
> **更新（动作 `act-c8604baca00c4d28`）**：`robustness` 阶段已完成并登记为 `completed`（隔离 task `9d890669fb66a1bcc3ae`，
> 156 情景 / 153 成功 / wall 3437.4 s）。**L6 已在本文末尾「附：Level 6 鲁棒性与敏感性复核」正式执行，判定
> `PASS_WITH_WARNING`（`criteria_failed=["S4"]`、`stability_grade=条件稳定（需给出适用边界）`、基线复现闸门 `passed=true`、
> `failure_type=null`）；L5 仍为 `not_applicable`。上方 L1–L4 原文与判定保留不改。**
>
> 本动作 **只读**：不重解 LP、不修改模型/代码/假设/公式/原始数据/任何 `results/` 产物，未创建 task，未占用 GPU，
> 未直接编辑 `runtime/workflow_state.json` 或受保护 manifest 字段；唯一写入是本动作 `evidence/`、本报告与 `machine_sanity.json`。
>
> **独立性**：本动作不复用上一动作的任何探针脚本或输出。`probe_sanity_l1_l4_run003.py` 自行实现全部断言，仅以 `data/` 原始附件 +
> run003 的 `solution.json`/`tables.json`/`result3.xlsx` + prob02 accepted run002 为输入，并对追踪链按 `scripts/automm/common.py`
> 的 `hash_path`/`hash_json` 同名算法复算（只读导入 `common`，不调用 `make_task_spec`，避免写 `__pycache__`）。

---

## 判定摘要

| 层级 | 判定 | 依据（本动作独立复算） |
|---|---|---|
| L1 文件与运行完整性 | **PASS** | 六件产物齐备；`task.json` 与 `attempt-001-task.json` 逐字节相同、stderr 0 字节；输入/模板 md5 未变；`run001`/`run002` 各 6 件且 mtime 早于 run003 创建时间（未被覆盖）；`code_hash`/`config_hash`/`source_config_hash`/`input_hash`/`task_id` 独立重算与 `task.json` 逐位一致；R9/R10 逐格扫描与负对照；E1 附件 3 读取结构 |
| L2 数值范围与约束 | **PASS** | 结算平衡 3.411e-13、状态转移 8.790e-8、跨日边界 1.137e-13、`(I1d)/(I2d)` 7.911e-8/7.910e-8、`c≤833.3333`、`q_dis≤750.0000`、两侧功率 5000.000 kW、`E∈[1200,10800]`、同充放 0、非负性 ≥−6.975e-8（求解器容差）；52560×12 列全 finite；模型自检 33/33、`checks_failed=[]` |
| L3 量纲、公式与实现一致性 | **PASS** | Δt=1/6 与附件 2 残差 0.0、电价与附件 1 残差 0.0；目标不含 Δt，`C_total/C_plan/C_adj/C_em` 独立复算逐位一致、分解恒等式 0.0；`result3.xlsx` 四工作表全量逐格回溯 ≤5.0e-7；表 1/2/3 ↔ 序列 ≤5.0e-7；T7 口径与 LP 计数达标；E6 口径核对；run003↔run002 数值零变化 |
| L4 常识与文献合理性 | **PASS_WITH_WARNING** | 交付期费用落入独立重算解析界 `[6,963,514.20, 16,407,319.63]`、量级 10^7；均价 0.697655 元/kWh ∈ `[p_min, 5·p_max]`；紧急购电单价/同段电价 = 5.000000；储能上下界均激活（7,556/3,887 时段）；Σq_em 非零；关键假设文献门禁独立复算通过（7 条 key 假设、25 条池内来源）；技术债见 §L4 与「warnings」 |
| L5 / L6 | **not_applicable** | L5 需 prob04 `locally_completed`；L6 需 `robustness` 完成（当前 `optional_stages.robustness.decision=pending`） |

**路由**：`PASS_WITH_WARNING` → 不退回（`return_stage=null`）；按 `config/gates.yaml` 的 `sanity_check → visualization` 允许迁移推进至 `visualization`。

**交付口径（不变）**：论文与表 1/2/3 一律以 **run003** 为准；`run001`/`run002` 保留为审计负对照（不删除、不覆盖、不作为最终答案文件）。

---

## 复核证据（全部位于 `runtime/actions/act-354d33342edf4e70/evidence/`，只读可复跑）

| 文件 | 内容 |
|---|---|
| `probe_sanity_l1_l4_run003.py` → `sanity_probe_run003.json` | **73 项独立只读断言，73 通过、0 失败** |
| `diag_openpyxl_float.py` | 5 格最小实验：证明 R10 残差为 openpyxl `%.16g` 浮点渲染（§L1.4） |
| `diag_decimal_cells.py` / `diag_decimal_breakdown.py` | run002/run003 工作簿「>6 位小数」字面计数与按列区段拆分 |
| `diag_xml_cells.py` | sheet↔XML 映射与原始存储串抽样（`W2 = 518.3097330000001`） |
| `prior_sanity_report_backup.md` | computation 阶段 P2 报告的逐字节副本（sha256 见上） |
| `probe_stderr.txt` | 本次探针**首跑失败留痕**（`KeyError: 'delivery'`：prob02 无 `delivery` 段）——属**探针自身接口错误**，已改为 `totals.net_load_delivery_kwh` / `delivery_cost_yuan` 后复跑通过；未隐藏失败 |

---

## L1 文件与运行完整性

1. **产物**：`solution.json`、`solver_status.json`、`tables.json`、`t7_tiebreak.json`、`run_manifest.json`、`result3.xlsx` 六件齐备。
2. **任务身份**：`runtime/tasks/6de708bbd2d3dd273013/task.json` 与 `attempt-001-task.json` **逐字节相同**；`attempt-001-stderr.log` **0 字节**；`status.json` 记 `attempt=1 / succeeded / rc=0 / supervised / consumed=true`。
3. **输入未变**：附件 1 `dbe06f92…`、附件 2 `bb3e493f…`、附件 3 `e8dfee65…`、模板 `75be588e…` 与 `run_manifest.input` 逐位一致。
4. **追踪链（独立复算，全部命中）**：
   - `input_hash=4343d799…`、`source_config_hash=5ba829f3…`、`config_hash=fd07c6a5…`、`code_hash=5bab4f2625a398fec85e9560afe1cf0a7a6a71db80455bcde720973ca6c38015`、`task_id=6de708bbd2d3dd273013`（`hash_json(identity)[:20]`）与 `task.json` **逐位一致**；
   - 当前 `code/*.py` 的 sha256 与 `run_manifest.code_sha256` 三文件逐一一致（`prob03_io.py=fb8b5eb4…`、`prob03_model.py=43aa60b7…`、`run_prob03.py=74e5cb6e…`）⇒ **团队勘误 R14 闭合**（run003 代码指纹 = 当前注册代码）。
5. **历史 run 未被覆盖**：`run001`/`run002` 各 6 件、mtime 全部早于 run003 的 `created_at`（2026-09-11T08:22:31Z）。
6. **E1（附件 3 读取）**：原始表 1460 行、`日期` 列 1095 空（前向填充前）；填充后 **365 天 × 4 决策时刻**、每行 **24 个提前量列**（`预报1小时…预报24小时`）**非空 = 0**。
   - 落点复核：`layer_inputs.nan_cells` = 0/13,140/26,280/39,420、`cross_year_dropped_items_per_day` = 0/6/12/18（合计 36/天）与支配规则 `ν(i)=6·floor((i−1)/36)` 自洽；四层 `uses_actual_pv=false` 与 **F2（实际光伏只进结算层）** 一致。
   - **口径纠错留痕**：附件 3 是「1460 行 × 每行 24 个提前量列」，不是「1460×24 行」；本动作首版判据曾按 24 行分组而失败，已改为按 24 列复核（与上一 P2 动作草稿探针 `E1-rows` 失败同类，均属探针口径错误，不是数据/模型缺陷）。
7. **R9（标签风格）**：run003 工作簿内起始小时补零的标签 **0 条**（`run002` 负对照 **874**）；`tables.json` 表 3 同源标签 run003 **0 条**（run002 **11** 条）。样例 `6:10-9:20` 已为不补零风格，与附件 5 模板/题面表 4 一致。
8. **R10 储电量越界**：run003 的 668 个储电量格中 `<1200` **0 格**、`>10800` **0 格**；`run_manifest.workbook_info.format_residuals=[]`、`delivery_decimals=6`、`storage_projection.max_abs_correction_kwh=3.059e-7`。

### L1.4 R10「超 6 位小数」——**口径冲突显式登记（本动作新增技术债）**

- **值口径**（团队勘误 R16 / 上一 P2 动作口径）：run003 中「值 ≠ 其 6 位小数舍入（容差 1e-9）」的格数 = **0**（run002 = 49,554）⇒ R10 的**数值修复确实生效**。
- **字面口径**（本动作更严）：直接扫描 `result3.xlsx` 的 XML `<v>` **十进制字符串**，run003 仍有 **4,849 格** 小数位 > 6
  （计划购电量 2,271 / 调整购电量 2,393 / 充放电量 64 / 紧急购电量 121；run002 为 26,095 / 26,733 / 3,288 / 121 = 56,237）。
  例：`计划购电量!W2` 原始串 `518.3097330000001`，而读值 `518.309733 == round(518.309733, 6)`。
- **根因（已用 5 格最小实验复现）**：`openpyxl 3.1.5` 写浮点时用 `%.16g` 渲染；任何**十进制 6 位小数不能精确表示为二进制 double** 的值
  （如 518.309733、78.735667、618.535233）都会被写成 16 位有效数字串。该行为对 `float`、`numpy.float64`、`round(v,6)` 三种写法**完全一致**，
  属**库序列化行为**，不是本问实现缺陷；差值量级 ≤1e-13 kWh，Excel General 显示与任何按值读取（openpyxl/pandas）都等于 6 位小数。
- **处置**：登记为**呈现层技术债**（不是硬失败，**不得据此判失败**），并**显式记录与前序动作「超 6 位小数 = 0 格」的口径差异**：
  两者的差异已逐项归因——上一口径未计入 `紧急购电量` 工作表（本动作测得 121）且对计划/调整表采用不同的舍入判据（本动作测得 +653）。
  若团队要求**字面** 6 位小数，须在实现侧改用字符串写入或对单元格施加数值格式，并在新 output_directory 重出工作簿（本动作不代改）。

---

## L2 数值范围与约束（独立回代，不重解 LP）

| 检查 | 本动作实测 | 阈值/期望 |
|---|---|---|
| 结算层平衡 `max|q+q_em+PV+q_dis−L−c−s|` | **3.411e-13** kWh | ≤1e-6 |
| 状态转移 `max|ΔE−(0.9c−q_dis/0.9)|`（含跨日边界） | **8.790e-8** kWh | ≤1e-6 |
| 跨日边界转移残差（364 日，`i%144==0`） | **1.137e-13** | ≤1e-6 |
| `(I1d)` 逐日残差 max | **7.911e-8** | ≤1e-6 |
| `(I2d)` 逐日残差 max | **7.910e-8** | ≤1e-6 |
| `max c` | **833.3333333333333** kWh | ≤`P_max·Δt`=833.3333 |
| `max q_dis` | **750.0** kWh | ≤`P_max·η_dis·Δt`=750.0（团队 E1/D10） |
| 两侧换算功率（充电并网点/电池侧、放电两侧） | **5000.0** kW | ≤5000（D10 口径丙取交集） |
| `E` 范围 | `[1199.9999999977, 10800.0000000007]` | [1200, 10800]（±1e-8） |
| 非负性 min(`b,q,q_em,c,q_dis,s`) | **−6.975e-8** kWh | ≥−1e-6（HiGHS 容差；交付工作簿只写 4 小时块合计，未外显负值） |
| 同充放时段数 | **0** | 0（N1 登记：T7-1 次目标已使旧口径的 13/19 个时段归零） |
| 有限性 | **52,560 时段 × 12 列全 finite** | 0 NaN / 0 Inf |
| 模型自检 | **33/33、`checks_failed=[]`** | —（求解器侧自检，非独立证据，仅登记） |

> 阈值口径（团队 T9，继续有效）：求解器内部层残差为「绝对 1e-6 + 相对 1e-8」，**层余额判据仍按 1e-8 执行**（实测 1e-13 级）。
> run001 因固定绝对 1e-8 判据 `hard_check_failed`（实测 8.79e-8 落在 HiGHS 默认可行性容差 1e-7 下），**不是模型缺陷**，本报告不据新口径放行任何超限值。

---

## L3 量纲、公式与实现一致性

1. **量纲/对齐**：附件 2 负载/光伏功率 × Δt(1/6 h) 与序列 kWh **残差 0.0**；电价序列与附件 1 单日 144 点曲线 **残差 0.0**；电价 ∈ `[0.3713, 1.3952]` 元/kWh。
2. **目标与费用分解**（独立复算，不乘 Δt）：
   - 全期 `C_total = 16,179,176.145228` 元 = `solution.objective_yuan`；`C_plan = 13,885,669.475555`、`C_adj = 563,098.132533`、`C_em = 1,730,408.537141` 逐项一致；分解恒等式残差 **0.0**。
   - 交付期（334 天）`C_total = 14,540,616.335652` 元、`C_plan = 12,362,860.209641`、`C_adj = 510,208.940910`、`C_em = 1,667,547.185102`（与 `solution.delivery` 逐位一致）。
   - `C_adj` 两段可复算：`0.5·Σp(b−q)⁺` 与 `1.5·Σp(q−b)⁺`（D2-A 主口径）。
3. **交付件 ↔ 序列（全量逐格，非抽样）**：
   - `计划购电量` 48,096 格 + 末两列（`Σb`、`C_total,d`）：max **4.995e-7**；`调整购电量` 48,096 格 + 末两列（`Σq`、`C_total,d`）：max **4.9999e-7**（替代量口径 D3-A/D4-A，AS16/N4）；
   - `充放电量` 2,004 个 4 小时块充电 **4.997e-7** / 放电 **4.9999e-7**、668 个端点储电量格 **3.059e-7**；6 个时段标签全部匹配；
   - `紧急购电量` 2,270 个区间的能量 **4.978e-7**（6 位舍入）、区间数 **0 处不符**、首尾分钟 **0 处不符**、标签风格 **0 处补零**；
   - 表 1 六时段 + 全天四费用分项 **4.980e-7**、表 2 六块与端点 **4.958e-7**、表 3 日合计 **4.444e-7**。
4. **N1/N2 统计（按团队口径只作统计与归因，不判失败）**：`simultaneous_charge_discharge_periods=0`；`periods_with_q_em_and_charge=5,070`（R12 见 §L4）。
5. **T7 口径（团队 T7/T9）**：`layers=1460`、`max_primary_relative_change=5.0000409e-10 ≤ 1e-9`、`lexicographic_committed_layers=1460`、`fallback_committed_layers=0`、`total_shrinks=0`。
   - **LP 计数语义（不得混用）**：`lp_calls=1460`（提交解口径 = 层数）与 `lp_solver_invocations_nominal=5840`（T7 四段式名义值，含基线）是两个不同口径。
6. **E6 口径**：`run_manifest.total_purchase_kwh=20,842,142.600809`（= 交付期 **Σq**，不是 Σb）、`total_q_em_kwh=391,274.485914`、`total_spill_kwh=2,087,727.847547` 与 `solution.delivery` 逐位一致；stdout 摘要为**全期 365 天**口径，引用时必须同时指明 `b`/`q` 与天数口径。
7. **run003 ↔ run002（R9/R10 只改呈现的证明）**：七列序列（`b,q,q_em,c,q_dis,s',E`）**逐位差 0.0**；四费用字段逐位相同；工作簿逐格差异分类 = **874 标签 + 55,463 舍入（≤5e-5）+ 0 其他**（与团队勘误 R16 逐位一致）。

---

## L4 常识与文献合理性

1. **解析界（独立复算，B3-5/§3.12/(I2req)）**：
   - 下界 `p_min·[N_req + 0.19·Σc_req − Σq_em_req] = 6,963,514.20` 元（`N_req=17,939,189.494967`、`Σc_req=6,349,998.653729`、`Σq_em_req=391,274.485914`）；
   - 上界（构造：`c=q_dis=0`、`E≡1200`、计划即实际）`Σ_{D_req} p·max(0,(L−PV)·Δt) = 16,407,319.63` 元；
   - 实测交付期 `C_total = 14,540,616.34` 元，落在区间内（自下界起 **80.23%** 处），量级 **10^7 元**，与 prob02 交付期 `12,233,050.83` 元同阶。
   - **口径差异登记**：上一 P2 动作报告的上界为 `19,109,190.33` 元（更宽）。两者都是有效上界，`C_total` 同时落在两者之内，判定不受影响；引用解析界时须注明所用构造。
2. **经济常识**：交付期均价 `C_total/Σq = 0.697655` 元/kWh ∈ `[p_min, 5·p_max] = [0.3713, 6.9760]`；逐日 `C_total` ∈ `[16,614.26, 66,529.25]` 元且全为正（单日 10^4 元；误乘 Δt 会落到 10^3）。
3. **α_em 精确成立**：`Σ(5p·q_em)/Σ(p·q_em) = 5.000000`（`q_em>0` 时段 12,164 个），说明紧急购电项未误乘 Δt、未与偏差项串味。
4. **储能边界**：`E==1200` 7,556 时段、`E==10800` 3,887 时段（上下界均激活，属 LP 最优面特征；**不比对逐点解唯一性**）。
5. **Σq_em = 391,274.49 kWh（交付期）非零**：结算用附件 2 实际光伏、决策用附件 3 预报，预报误差必产生缺口（与 F2/F3 一致；**论文不得写成「购电上限激活了紧急购电机制」**，勿与 prob02 R5 混淆）。
6. **文献门禁（独立复算）**：`version.yaml` 共 18 条假设，其中 `key=true` **7 条**，全部绑定池内来源、无悬空 id；文献池 25 条全部 `status=used`，
   等级 **abstract_oa 15 + metadata 10、0 条全文**（E4）。据此 `hard_gates.key_assumption_citation` 通过，但**证据强度只到框架级/机制级**。
7. **R11/R12/R13 披露义务（sanity 必落地，本报告已核）**：
   - **R11**：prob03 交付期比 prob02 贵 **+2,307,565.50 元（+18.863%）**，两问交付期净负荷**逐位相同**（17,939,189.49 kWh）⇒ 差额是**预报误差的代价**；论文**不得**声称「问题 3 比问题 2 更省」，并须写明模型无对冲机制（T6 撤销 PLAN-EXP 的直接后果）。
   - **R12**：`periods_with_q_em_and_charge=5,070`（9.6%），最小可复现示例 = **2025-01-01 6:20–6:30**（period_index 37）；机制为「决策层用预报定下 `(q,c)` + 结算层用实际算缺口」，`c` 由普通购电 `q` 支付、`q_em` 只补负载缺口，**不违反 D7-A**。
   - **R13**：2025-02-01 0:00 储电量 `prob03 = 1200.00 kWh` vs `prob02 = 7950.00 kWh`（均为 2025-01-31 末时段状态），成因是**信息集不同**，论文与 sanity 均须显式写明一次，**不可直接互比**。
8. **T7-3/T7-6/E7 结构性披露（如实报告、不得判失败）**：`degenerate_layers=1460`、`layers_with_remaining_multiplicity=1024`、`layers_with_unknown_multiplicity=1`、`max_degeneracy_degree=228`、`max_baseline_trajectory_change=4527.57 kWh`；唯一未定论层为 `adjustment/day_index=284（2025-10-12）/hour=18`（主目标 0.0 ⇒ ε=1.754e-11 低于 HiGHS 对偶分辨率，属**探测能力问题**）；tie-break 量级敏感性约 **1e-4 相对量级**（14 天链 761,150.711525→761,322.475606 元）。**禁止**为制造唯一性调 ε 或换 tie-break 规则。
9. **新增技术债（登记，不影响数值）**：模型自检 `continuity_residual_max=0.0` 是构造性恒等（`state_starts[1:] ≡ E[:-1,-1]`），不构成独立证据；实质跨日连续性由 `(I5d)` 转移残差（8.79e-8）与本动作的边界残差（1.137e-13）承担。建议 formulation 下一版修正或删除该字段。
10. **上游结转（本动作不越界代改，继续有效）**：`prob01/assumption_v003/version.yaml` 的 AS08「该变量在部分时段必然被激活」措辞与实测 `Σs_t=0` 不符（C3/E3），权威回写待 `cross_question_review`；`D10「5000 kW 作用侧」`为 team_decision、prob01/02/03 三池文献无一条涉及，**论文不得包装为文献支持**；R5 购电上限阈值须表述为 `β ∈ (4218.75, 4375.00] kW`（本问 AS14 无购电上限，不触发）；R1 表 2 端点语义须与 prob01（单日周期恒 6000 kWh）显式区分；A5/A9/A10/A11/A13/A14/A18 仍为推荐口径并保留决策点。

---

## 结论

`run003` 在 accepted `assumption_v001` + `formulation_v001` 下**满足题面硬约束、团队 R9/R10 填报纪律与追踪链要求**，可作为本问最终交付口径：
交付期 `C_total=14,540,616.335652` 元落于独立解析界、量级正确、恒等式/映射/追踪链全部通过、`checks_failed=[]`、658,245 个数值 0 NaN/0 Inf。
无硬门禁失败；技术债与披露义务见「warnings」。**推荐下一阶段 `visualization`**（`sanity_check → visualization`）。

---

## 附：Level 6 鲁棒性与敏感性复核（动作 `act-c8604baca00c4d28`）

- **调用背景**：`robustness` 阶段完成（`record_optional_stage(stage="robustness", decision="completed")`，动作 `act-93a3075a9a494876`）后，
  Runner 按 `config/sanity_check.yaml` 的 `level_6.trigger = after_robustness` 迁移到 `sanity_check` 并调用 sanity-checker
  （policy **P3** `run_agent`、`level=level_6`）。这是 **L6 的正式执行**，不是重跑 robustness。
- **对象（只读）**：`robustness/results/prob03_v001_robust_run001`（task `9d890669fb66a1bcc3ae`，attempt 1、`succeeded`、
  `returncode=0`、`supervised`、CPU HiGHS、`probe_mode=false`、`mode=compact`、`days=365/periods=52560`、`seed=20260911`、
  156 情景 = `baseline` 1 + `baseline_full` 1 + 参数 39 + 求解器 3 + 结构 12 + 噪声 100，153 成功 / 3 不可行（全属结构族）、
  `wall_seconds=3437.37`、`budget_exceeded=false`）；交付锚点仍为 accepted `results/prob03_v001_f001_run003`（task `6de708bbd2d3dd273013`）。
- **复核方式（全部只读；不修改模型/代码/假设/公式/原始数据/既有 `results/`；不创建 task；不占用 GPU）**：
  1. `evidence/verify_level6.py` → `verify_level6_report.json`：**56 项独立断言，56 通过、0 失败（verdict=PASS）**，
     覆盖追踪链、基线闸门、S1–S6 重算、报告口径一致性、图件口径（DR-2/3/4/5/6）与计划冻结时序；
  2. `evidence/compare_probe.py` → `compare_probe_report.json`：**在隔离 task 之外以新 output_directory 独立重解 12 个情景**
     （`baseline`、`baseline_full`、`eta_both_0.990`、`solver_highs_ipm`、`terminal_e_6000`、`buy_cap_5000kW`、
     `buy_cap_4375kW`、`noise_white_10_007`、`e_init_4800`、`e_init_7200` 及重复基线），与 `raw_samples.jsonl` 的
     9 个关键字段**逐位相同（max|Δ|=0.0）**，不可行端点的失败指纹（计划层 status=2）亦逐字相同；
  3. `scripts/run_sanity_check.py` 在 `evidence/auto_scope/`（158 个数值文件的**副本**，未触碰版本目录）跑 L1/L2-finite：
     `automated_status=PASS_WITH_WARNING`、`failures=[]`、448,220 个数值 **0 非有限值**；
  4. `evidence/cross_question_check.py` → `cross_question_check.json`：R11/E9 跨问口径抽查 3/3 通过；
  5. `evidence/make_level6_machine_sanity.py` → 版本目录 `machine_sanity_level6.json`（机器可读摘要，与本节同源）。

### L6.1 追踪链与运行完整性 — **PASS**

- task 终态 `succeeded` / `returncode=0` / `attempt=1`；`task.json` 与 `attempt-001-task.json` **逐字节相同**；`attempt-001-stderr.log` **0 字节**；
  stdout 末行 `完成：153/156 情景成功，3437.4 s，稳定性分级 = 条件稳定（需给出适用边界）`。
- 独立重算：harness `code_hash=a0aeee339aadbcee40853be98c773f8c2244c15419234b041e06e6162a0fe5f8`（对 `robustness/code/` 用
  `scripts/automm/common.py: hash_path`）与 `task.json` **逐位一致**；`input_hash=4343d799…` 与 `task.json` 及 **run003 的 task 一致**
  ⇒ `data/` 未被改动；`config_hash=fa34218b…`、`source_config_hash=8bd56149…` 与 `task.json` 一致；`run_manifest.code_sha256=9f55ddb1…`
  = `robustness_prob03.py` 的 sha256（脚本自算算法，与 harness 算法不同，不矛盾）。
- **登记瑕疵（不构成失败）**：`status.json` 终态为 worker 自身写入的 `succeeded/rc=0`，但仍保留
  `message="worker PID 不存在且未写入终态"`——该 message 由 supervised 模式下的另一次 `reconcile_tasks()` 误写（`worker_alive()`
  要求进程 cmdline 含 `task_worker.py --task-id`，而 supervised 模式写 `pid=Runner pid`），随后被 worker 终态覆盖；属既有登记的
  harness 语义问题，权威证据为 stdout 与全套产物。`consumed=false` 属既有「robustness 阶段的 run_agent 动作不消费终态 task」登记欠账。

### L6.2 基线复现闸门 — **PASS（独立复现两次）**

- 任务产物 `baseline_check.json`：`passed=true`、`worst_relative_diff=0.0`；9 项总量相对差全为 `0.0`
  （全期 `16,179,176.145228`、交付期 `14,540,616.335652`、`C_plan/C_adj/C_em = 13,885,669.475555/563,098.132533/1,730,408.537141`、
  `Σq=20,842,142.600809`、`Σq_em=391,274.485914`、`Σs'=2,087,727.847547`、`E_final=1200.0`）；表 1 四日期 × 六时段 **24/24 格最大绝对差 0.0 kWh**；
  T7 审计 `layers=1460`、`max_primary_relative_change=5.0000409e-10`、`lexicographic=1460`、`fallback=0`、`degenerate=1460`、
  `remaining_multiplicity=1024`、`unknown_multiplicity=1` 与 run003 的 `t7_tiebreak.json` 逐项一致。
- **本动作独立复现**：以新 output_directory 重跑 `baseline`（compact）与 `baseline_full`（full 模式，四段式 T7），
  9 项总量相对差 `0.0`、表 1 24 格最大绝对差 `0.0 kWh`、T7 审计七项与 run003 相同 ⇒ `compact` 提交解与 T7 字典序解逐位同解，
  本阶段所有情景与 run003 同源同口径。

### L6.3 预注册判据 S1–S6 独立复算 — **S1/S2/S3/S5/S6 PASS，S4 FAIL（唯一）**

| 判据 | 阈值（`plan.md` §3，跑数前冻结） | 本动作独立复算 | 判定 |
|---|---|---|---|
| **S1** 受判样本可行率 | 100%、层残差 ≤1e-6（相对 ≤1e-8）、界越界 ≤1e-6、恒等式残差 ≤1e-6 | 受判 **144/144** 可行、`layer_status_max=0`、`identity_failed=[]`；残差 max：结算平衡 0.0、状态转移 1.0e-7、跨日连续 0.0、费用分解 0.0、层等式 1.0e-7（相对 2e-12）、层不等式 9.9e-8（相对 5e-12）、界越界 1.0e-7 | **PASS** |
| **S2** 机制监控量 | `Σq_em>0`、`q=b (i≤36)`、同充放 0、交付期费用 ∈[3e6,5e7]、`q_em&c` 占比 ≤15% | 144/144 通过；`Σq_em` 最小 **364,259.065** kWh；`max|q−b|(i≤36)=0.0`；同充放 **0**；`q_em&c` 占比 max **0.106906393** | **PASS** |
| **S3** 六组 OAT 单调方向 | 端点对不反转（相对容差 1e-6） | 8 个族（含单侧 `η_ch`/`η_dis`）**全部不反转**，`violations=[]` | **PASS** |
| **S4** 噪声族统计 | n≥25、std ≤5%、95% CI ≤5%、`max|z|` ≤4、族间均值差 ≤3%、无失败 | 五项通过（n=25/25；std ≤0.9236%；CI ≤0.3621%；`max|z| ≤2.5502`；0 失败）；**唯一违反 = 族间均值差 7.2946% > 3%** | **FAIL** |
| **S5** 求解器可行性与链级差异 | 3/3 可行、残差合格、相对差 ≤1%（>1e-3 登记 warning） | 3/3 可行；`highs-ds` 0.0、`highs-ipm` **−1.3515e-3**、`presolve=False` **+1.1073e-4**，max 1.3515e-3 ≤1% | **PASS** |
| **S6** 结构情景完整性 | 购电上限给出夹逼；终端情景产出数值 | `buy_cap` 11 档全产出状态（8 可行 / 3 不可行），夹逼 **(4375, 5000] kW**；`terminal_e_6000` 交付期 **14,543,941.960654** 元（Δ=**+3,325.625 元 = +0.0228713%**，`E_T=6000`） | **PASS** |

**分级**：`S1 PASS` 且恰有 1 项非 PASS ⇒ 按 `plan.md` §3 预注册规则 `stability_grade = 条件稳定（需给出适用边界）`
（与 `summary.json`/`run_manifest.json` 登记一致）。3 个失败情景（`buy_cap_3500/4218.75/4375 kW`）**全属结构族**，
按预注册保留在 `raw_samples.jsonl` 与 `summary.failures` 中、**未静默删除**，且不计入 S1 受判子集（144）。

### L6.4 S4 失败的精确归因（判据不事后修改，DR-1）

- **事实**：五项子判据通过，唯一违反的是**跨 σ 档的族间均值一致性**：含 σ=10% 的 `noise_white_10`（均值 +11.2241% 于基线）
  与三个 σ=5% 族（≈ +3.93%）并列比较 ⇒ `(16,172,668.76 − 15,111,994.80)/14,540,616.34 = 7.2946% > 3%`；
  **仅比较三个 σ=5% 族则均值极差 = 0.0641% ≪ 3%**（本动作独立复算：0.0729455989 vs 0.0006405434）。
- **性质**：预注册的 S4/K4 把「**族内离散度**」与「**跨 σ 档族间均值一致性**」绑在同一条判据，而两档 σ 的设计扰动幅度
  本不相同 ⇒ 该违反是**判据口径设计债**，不是模型脆弱性证据；判据**不修改、不重算**，FAIL 与 `条件稳定` 原样进入论文。
- **引用纪律**：① 不得表述「模型对噪声不稳定」；② 应表述为「族内离散度 <1%，但期望费用随预测偏差幅度系统性上移
  （σ=5% ≈ +3.9%、σ=10% ≈ +11.2%）」；③ 引「7.29%」时必须同时给出同 σ 子集 **0.0641%**。
- **材料口径**：σ=5%/10% 是**诊断性设定**（非题面事实、非文献标定）；本阶段只扰动**结算层实际值**（附件 2 负载/光伏，joint 族另加电价），
  决策层仍用未扰动的附件 3 预报 ⇒ 噪声族等价于「实现值 − 预报」的偏差测试，**不构成真实预测误差分布**，95% CI 只用于外推边界。

### L6.5 独立重解探针（隔离 task 之外，仅作判据证据）

| 情景 | 本动作重解（元 / kWh） | 原始样本 | 差 |
|---|---|---|---|
| `baseline`（compact） | 全期 16,179,176.145228 / 交付期 14,540,616.335652 | 同 | **0.0** |
| `baseline_full`（full） | 全期 16,179,176.145228 | 同 | **0.0** |
| `eta_both_0.990` | 全期 15,236,811.519523 | 同 | **0.0** |
| `solver_highs_ipm` | 全期 16,157,309.823962 | 同 | **0.0** |
| `terminal_e_6000` | 交付期 14,543,941.960654 | 同 | **0.0** |
| `buy_cap_5000kW` | 全期 16,532,714.0285 / 交付期 14,811,903.8023 | 同 | **0.0** |
| `buy_cap_4375kW` | 计划层 LP `status=2` 不可行 | 同（含失败指纹文字） | 一致 |
| `noise_white_10_007`（seed 20260911） | 全期 17,927,253.6217 | 同 | **0.0** |
| `e_init_4800` / `e_init_7200` | 全期 16,179,747.178562 / 16,178,606.328561；**交付期均为 14,540,616.335652**、`E_T=1200.0` | 同 | **0.0** |

⇒ 结论：批次**可确定性复现**（含固定 seed 的噪声样本），原始样本**未被事后编辑**，且 E_init 交付期零效应（E8/DR-7）
由独立重解再次确认（仅 2025-01-01 当日全期目标 ±571/570 元）。

### L6.6 本动作新增的独立发现与技术债

1. **`buy_cap_10326kW` 档「非绑定却低于基线」（新增）**：基线计划购电峰值 1,670.663617 kWh（= 10,023.98 kW）< 上限 1,721 kWh（10,326 kW）
   ⇒ 上限**不绑定**，但该档目标比无上限基线低 **139.32 元**（相对 **−8.6e-6**）、交付期费用低 103.20 元。机制是 LP 最优面选择
   经跨日初值传播（同 T7-6/CF-1，量级远小于 1.3515e-3），**不得**读成「购电上限降低费用」；`report.md` §3.4 的单调下降表述在该端点需注明。
2. **统计量命名债（新增）**：`sensitivity.json` 的 `ci95_half_width_t` 实际用**正态 1.96** 乘子（实测隐含乘子 1.960000），
   而非 t(24)=2.0639；两种读法都远低于 5% 阈值，S4 判定不变，引用时须注明。
3. **文档/实现不一致（新增，仅登记）**：`plan.md` §6 与 `report.md` §10 把 `trajectories/` 描述为「非噪声情景轨迹」，
   实现按 `family != 'noise'` 判断而噪声族名为 `noise_*`，故实际落盘 **153 个**（= 全部成功情景，含 100 个噪声样本）——
   可追溯性强于声明，但论文引用噪声样本轨迹时须说明口径。
4. **图件与统计量口径（DR-2/3/4/5/6，代码 + 图像抽检确认）**：tornado 图例写「负向/正向扰动最大 ΔC」而柱值为
   `delta_min/delta_max`（η/P_max/E_max 族参数方向与 ΔC 符号相反）；排名统计量 `spread_relative=max|ΔC|` 与图中条形跨度
   `delta_max−delta_min` **不同源**（按跨度排序 = η_both > η_dis > E_max，与登记的 η_both > E_max > η_dis 不同）；
   spider 径向为单侧 `max|ΔC|/C_total`；相对标准差以族自身均值为分母；龙卷/OAT 用**全期** `C_total`，响应曲线/ECDF/箱线/
   购电上限曲线与 S2/S6 用**交付期** `D_req`（E6 口径必须随数字标注）。6 张图**不登记为交付图表**（未调用 `record_figure_review`）。
5. **E9/R5 分问口径**：prob03 的 **(4375, 5000] kW** 是**决策层**（0:00 预报、无 `q_em` 变量）可行上界夹逼，与 prob02 的
   `q_em` 激活阈值 `β∈(4218.75, 4375.00] kW` 是**不同物理量**，不得混用或宣称一致（本问 AS14 无购电上限，R5 不触发）。
6. **适用边界**：参数网格 `η∈[0.72,0.99]`、`α_em∈[4,6]`、`β` 同比例 ±20%、`P_max∈[4000,6000] kW`、`E∈[960,12000] kWh`、
   `E_init∈[4800,7200] kWh`；噪声结论限于「实现值相对预报的乘性偏差 ≤10%」；**不覆盖**自放电（AS17）、`s` 的更紧界（A13）、
   预报误差分布假设与对冲收益量化（R11④ 属 ablation）。本阶段不改变 `M1` 任何主结果，**`run003` 仍是唯一交付口径**。

### L6.7 跨问抽查（R11 / E9，独立复算）

- **R11**：prob02 交付期 `12,233,050.830708` 元、prob03 `14,540,616.335652` 元 ⇒ 差额 **+2,307,565.504944 元 = +18.863%**；
  两问交付期净负荷由 `data/附件2.xlsx` 独立复算 = **17,939,189.494967 kWh**（334 天，与 L4 登记的 17,939,189.49 一致）
  ⇒ 差额来自预报误差与无对冲机制（T6 撤销 `PLAN-EXP`），论文**不得**声称问题 3 更省。
- **E9**：两个分界（prob02 `[4218.75, 4375.0]` vs prob03 `[4375.0, 5000.0]`）并存且已分问标注，不重叠、不混用。

### L6.8 与 accepted 团队裁定/勘误的接口（显式记录，不静默沿用旧登记）

| 编号 | 团队口径（效力最高） | 本动作执行 / 证据 | 状态 |
|---|---|---|---|
| **E8**（团队编号 R18） | 日边界储电量恒为下限是**结构性事实**；prob03 终端口径价值 +3,325.625 元 / +0.0228713%；**不新建** `assumption_v002`、不重跑 | 独立复现 `terminal_e_6000` = 14,543,941.960654 元（Δ=+0.0228713%）与 E_init 交付期零效应 ⇒ 一致 | **一致** |
| **E9**（团队编号 R19） | prob03 述为「决策层可行上界夹逼 (4375, 5000] kW」；与 prob02 阈值分问、不得混用 | 独立复算夹逼 = [4375.0, 5000.0] kW；报告 §3.4/§7-CF-2 已按 E9 表述 | **一致** |
| **E6** | `run_manifest.total_*_kwh` = 交付期 `D_req`，`total_purchase_kwh` 装 `Σq`；stdout 摘要为 `D_full` | 本报告与 L6 摘要**逐处标注口径**（§L6.3 的 S2/S6 用交付期，§L6.2 的 T7/OAT 用全期） | **一致** |
| **E7 / T7-3** | `layers_with_unknown_multiplicity=1`（`adjustment/day=284(2025-10-12)/hour=18`）须如实披露；compact 的 `probe_coverage=0.0` 不得当结论 | 退化类指标只以 `baseline_full`（full 模式）的 **1460/1024/1** 为准（本动作独立复现一致）；`report.md` §6-F7/§7-CF-6 已披露 | **一致（技术债披露）** |
| **CF-1 / T7-6** | 求解器最优面敏感性属已登记机制，>1e-3 登记 warning、不判缺陷 | `highs-ipm` 全年 −1.3515e-3，S5 PASS + warning；引用须成对给出目标值与 `Σq_em` | **一致（warning）** |
| **DR-1（本阶段）** | S4 判据口径设计债，判据不事后修改 | S4 FAIL 与 `条件稳定` 原样保留，并给出同 σ 子集 0.0641% | **一致（技术债）** |
| **C3/E3、D10、R10、A5/A9/A10/A11/A13/A14/A18** | 上游结转项 | 本动作不越界代改，继续结转至 `cross_question_review`/论文/`ablation` | 结转 |

### L6.9 判定与路由

- `status`：**warning**（`PASS_WITH_WARNING`；`failure_type=null`、`return_stage=null`）。
- **无硬门禁失败**：无 NaN/Inf（448,220 个数值全 finite）、约束/单位/追踪链通过、原始数据未改、基线闸门通过、
  关键假设文献门禁沿用 L4 的 `passed=true`；S4 的 FAIL 为预注册判据的口径设计债，按规则判 `条件稳定` 而非脆弱。
- `recommended_next_stage`：**`ablation`**（`config/workflow.yaml: mandatory_stages`，`optional_stages.ablation.decision=pending`、
  `artifacts.ablation=false`；`config/gates.yaml` 允许 `sanity_check → ablation`）。
- 机器摘要：`machine_sanity_level6.json`（本版本目录）；证据目录：`runtime/actions/act-c8604baca00c4d28/evidence/`。
