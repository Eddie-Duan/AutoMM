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
