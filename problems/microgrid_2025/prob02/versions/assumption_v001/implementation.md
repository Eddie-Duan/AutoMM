# 实现计划（implementation，prob02）

- 归属：`microgrid_2025` / `prob02`（问题 2：逐日计划购电 + 5 倍价紧急购电）；阶段：`implementation`
- 同步动作：初版 `act-a4b3a442051e4b00`；**修订 `act-56d59165992142b3`**（负责人：implementation-agent）
- 修订原因：sanity `act-ca831716e72246eb` 判 `NEEDS_REVISION`（`result2.xlsx` 残留模板
  `充放电量!A15=2025-12-31`、`!E16='24:00'`，根因 `openpyxl` 的 `cell(row, column, value=None)` 静默 no-op），
  本动作按 `return_stage=implementation` 修复填报清空路径、加硬门禁并把 task spec 切到 `run002`（不覆盖 run001）
- 版本目录：`problems/microgrid_2025/prob02/versions/assumption_v001/`
- 输入依据（只读）：`request/problem.md`（问题 2、附录 1、附件 5）、`data/附件1.xlsx`、`data/附件2.xlsx`、
  `data/附件5/result2.xlsx`、`assumptions.md`（accepted，assumption_v001，**末尾含「团队勘误」R1–R4 与「团队裁定」B0–B5**）、
  `version.yaml`、`formulations/formulation_v001/{formulation,formula_validation}.md`、
  `formulations/formulation_v001/parameters.yaml`、`../../global_symbols.yaml`
- 规则依据：`agents/implementation-agent.md`、`agents/resource-manager.md`、`PROJECT.md`、`RESEARCH_LOOP.md`、
  `config/compute.yaml`、`config/gates.yaml`、`wiki/compute-tasks.md`
- 不覆盖历史：未修改 `assumptions.md`/`version.yaml`/`global_symbols.yaml`、`prob01/` 任何版本目录、`data/`、`request/`；
  本动作只在 `prob02/versions/assumption_v001/code/` 与 `implementation.md` 内工作。
- **本动作未运行 365 天正式计算**（implementation 阶段禁止运行完整数据集）：`--days 365` 只用于
  ①**不求解**的矩阵规模探针与解析可行点探针；②`make_task_spec` 的规格预演。正式数值由 `computation`
  阶段的隔离 task + supervised worker 产出。

---

## 1. 口径落地清单（accepted 假设 / formulation / 团队裁定 → 代码位置）

| 口径 | 取值/要求 | 代码落点 |
|---|---|---|
| **AS01** 左端点对齐 | 位置 `i` ↔ 区间 `[10i−10, 10i)` 分钟；计划窗 `0:10 → 24:10` | `prob02_io.read_attachment1`（按行位置读取，不排序/不插值）、`run_prob02.build_tables` 的双标签校验、`prob02_model.interval_label` |
| **AS02**（A2 的数据面） | 只用附件 1 的**电价列**与附件 2 的**实际**负载/光伏；禁用附件 1 预测列、附件 3、附件 4 | `run_prob02.main` 的 `LpData` 构造；`read_attachment1` 只保留第 2 列数值 |
| **AS03**（A2） | 自 2025-01-01 以 `E_init = 6000 kWh` **滚动递推**，1 月为预热期，交付 2/1–12/31 | `LpData.days = 365`、`prob02_model.E_INIT`、(R2) 首行 RHS；`DAILY_DELIVERY_START = 31` |
| **AS04**（A2 派生） | 终端**不作额外约束**（`E_T` 自由） | `build_lp` 的 `E` 上下界统一 `[1200, 10800]`（**不**固定末时段） |
| **AS05 + D9** | `min Σ (p·b + 5·p·q_em)`（元，**不带 Δt**）；`α_em = 5` | `build_lp` 的 `objective`（`ALPHA_EM * price` 块） |
| **AS06**（A5） | 等式平衡 `b + q_em + PV·Δt + q_dis = L·Δt + c + s`；`q_em` 不得用于储能充电 | (R1) 行的 5 个非零元 |
| **AS07 + AS10**（A17/A14） | 完全信息 + 无购电上限 ⇒ `q_em ≡ 0`；**变量与约束必须保留** | `q_em` 为独立变量块（界 `[0, ∞)`）；`evaluate` 的 `q_em_zero_total` 检查（不是删除变量的依据） |
| **AS08 + D10 + 勘误 E1** | `c ≤ 833.3333`、`q_dis ≤ 750.0000`；`E ∈ [1200,10800]`；两侧功率换算均 ≤ 5000 kW | `C_CAP`、`Q_CAP`、变量界与 `evaluate` 的 `max_side_power_kw` |
| **AS09 + 勘误 E3** | 显式 `s`，`0 ≤ s ≤ PV·Δt`，目标系数 0；变量保留、允许取 0 | (R1) 的 `−s`、变量界 `[0, PV·Δt]` |
| **AS11**（D1 派生） | 365 × 144 = 52,560 时段单一确定性 LP；CPU HiGHS；无随机 | `prob02_model.build_lp/solve_lp`（稀疏 `A_eq`）、`solve_lp` 的 `method="highs"` |
| **AS12 + 勘误 R3/R4** | 表 1/表 2/表 3 与 `result2.xlsx` 三工作表的填报口径 | `run_prob02.build_tables`、`prob02_io.fill_result2_workbook` |
| **团队裁定 B0** | 主结果只以 **M1** 为准 | `code/` 只实现 M1；M2–M7 按 B1/B5 由 `ablation` 在 `ablations/code/` 另建 |
| **团队裁定 B2** | 双路线同解、解析恒等式（含终端项）、退化条件、尺度分离、量级自检 | `evaluate` 的 (I1)/(I2)（全期 + 交付期切片）、解析下界/上界、交付期 10⁷ 量级检查 |
| **团队裁定 B4** | 同数据/同参数/同口径/同预算 | `task_spec.yaml` 的 `inputs_readonly` 与 `task_config.yaml` 的 CPU/seed=null；代码不读取附件 3/4 |

### 1.1 与上游登记/团队勘误的冲突记录（显式，不静默沿用）

| # | 冲突/差异 | 本实现采用 |
|---|---|---|
| **C1/E1** | `global_symbols.yaml` 的 `q_dis` 域曾写 833.33 | 按团队勘误 E1 + D10 口径丙取 **750.0000**（符号表已回写，本动作核对无残留） |
| **C3/E3** | `prob01/assumption_v003/version.yaml` 中 AS08「必然被激活」措辞未更正 | 按「变量保留、最优解允许取 0」实现（不强制 `s > 0`）；权威回写待 `cross_question_review`，本动作不越界代改 |
| **C6（高优先）** | 旧登记「`b` 上限低于 10,326 kW 会**强制** `q_em > 0`」被 formulation 证伪（10,325.33 kW 只是非绑定阈值；真实激活阈值 `β ∈ (4218.75, 4375.00] kW`） | 本实现只实现**主口径 M1（无购电上限）**，不涉及 M6 网格；`q_em ≡ 0` 是模型内推论而非实测断言。M6/M6′ 属 `ablation`，须先由团队裁定 D4 |
| **D10 文献缺口** | 「5000 kW 作用侧」为 `team_decision`，两问文献池均无涉及 | 代码按口径丙实现；本文件不声称文献支撑 |
| **A6/A7/A8/A9** | 附件 3 降尺度与年末边界、prob03 结算口径、prob04 电价可观测性、附加预报时刻分析 | 属 prob03/04；本实现不越界（不使用附件 3/4） |
| **A5/A10/A11/A13/A14/A18** | 紧急购电用途、表 2 同块同充放、全天购电费口径、`s` 的界、购电上限、表 3 填报 | 全部按 accepted 假设的推荐项（D4 A / D7 A / D5 A / D6 A / D7 A + A18 三条细则）落地 |

---

## 2. 代码结构与职责

目录：`problems/microgrid_2025/prob02/versions/assumption_v001/code/`（当前 accepted 版本内，可迭代；输出目录另行保留）

| 文件 | 职责 | 主要接口 |
|---|---|---|
| `prob02_io.py` | 读附件 1（只留电价列 + 表头/行数/正电价校验）、读附件 2（两工作表、日期连续性、非负有限性）、读模板标签、把交付解填入 `result2.xlsx` 三工作表、写 JSON（禁 NaN/Inf） | `read_attachment1`、`read_attachment2`、`inspect_template`、`fill_result2_workbook`、`write_json`、`delivery_dates` |
| `prob02_model.py` | 构造 (P2) 的稀疏 `A_eq/b_eq/lower/upper`、调用 CPU HiGHS、计算全期与交付期指标、(I1)/(I2)（含终端项）、逐条硬约束检查、紧急购电区间合并与标签 | `LpData`、`build_lp`、`solve_lp`、`evaluate`、`state_series`、`emergency_intervals`、`interval_label` |
| `run_prob02.py` | CLI 入口：解析参数、组装并求解、构造表 1/表 2/表 3、按模式写产物、以退出码表达失败语义 | `main`（`--data/--data2/--template/--output/--days/--time-limit`）、`build_tables` |
| `task_config.yaml` | task 级配置（`compute`/`solver`），提交时作为 `--config-path` | – |
| `task_spec.yaml` | 隔离计算 task 的完整规格（命令、路径、超时、期望产物、失败条件） | – |

代码文件 sha256（本动作终稿，`act-56d59165992142b3`）：

| 文件 | sha256 |
|---|---|
| `prob02_io.py` | `10ea7e49508d54b72dfdf5e15494f019f9dd8096780afd5acdfc406393631892` |
| `prob02_model.py` | `a1cebf40b41295cda4eae0a5409f5adf70c1342c6d4fb800b2e3af7ebb09d8d2`（未改） |
| `run_prob02.py` | `a3ff906a1493af6bf22e982066dfdf52546eb6b72f0a1812ecff1d817f8f749f` |
| `task_config.yaml` | `ea83fab4abc63da1139dde31185f0e9acde1ed893c8716ca0200507dff589d94`（未改） |
| `task_spec.yaml` | `00a118e08193ced4b7b9ccb6b0b6dafeaab895deb9d101c9ba05a40307f008a9` |

代码目录的 harness 指纹（`automm.common.hash_path(".../code")`，与 task ID 同源；忽略 `__pycache__`）：
`a37eda25aac4c02083bbed0a7ce7c2771794cc69422c1a55e7b89de9af54626f`
（初版为 `b8f88661…`；本次修复 + task spec 修订使 `code_hash` 变化，故 `run002` 为新 task ID）

### 2.1 模型规模（与 formulation_v001 §3.9 一致）

- 变量 `6 × 52560 = 315,360`（`b, q_em, c, q_dis, s, E` 各 52,560；`E_τ` 为第 τ 时段**末**状态）。
- 等式约束 `2 × 52560 = 105,120`（平衡 52,560 + 状态转移 52,560）；变量界 315,360；`A_eq` 非零元 `9T − 1 = 473,039`。
- 目标 `Σ(p·b + 5·p·q_em)`；**全文无 `p·b·Δt` / `5·p·q_em·Δt`**（D9 量纲纪律）。
- `A_eq` 以 `scipy.sparse` 构造（CSR，约 5.7 MB）；变量界用 `np.column_stack((lower, upper))`（约 5 MB），
  两处都**不构造稠密矩阵**（稠密约需 265 GB）。

---

## 3. 运行环境与求解器

- 求解器：`scipy.optimize.linprog(method="highs")`，`presolve=True`，`time_limit=300 s`（CLI `--time-limit` 可覆盖）。
- **CPU 求解，不使用 GPU**（`device=cpu`、`gpu_required=false`）：不占用单卡 GPU 串行额度；本问无 torch/CUDA 依赖，
  未安装或升级任何 GPU 依赖。
- 确定性 LP，无随机性：`seed=null`，代码不读取任何随机源；同输入/同版本必须复现同一目标值。
- 解释器：项目 venv（`.venv/Scripts/python.exe`，Python 3.14.4；numpy 2.5.2、scipy 1.18.1、openpyxl 3.1.5）。
- 资源实测（formulation 探针）：26.8 s、峰值 traced 内存 113.16 MB；本机可用内存 1.7–2.2 GB，
  故 `memory_per_worker_gb = 2`、不安排多 worker 并发。

---

## 4. I/O 契约

### 4.1 输入（只读；md5 由本动作实测）

- `data/附件1.xlsx`：第 1 工作表 145 行（1 表头 + 144 数据）× 4 列，表头
  `时间 / 电价 / 小区负载 / 光伏发电预测功率`；md5 `dbe06f92517431228efcc26e3e796ef9`。
  **本问只用第 2 列（电价，∈ [0.3713, 1.3952] 元/kWh，逐日重复 365 次）**；第 3/4 列仅参与表头结构校验，
  数值不进入模型。时间列前 143 行为 `datetime.time`/`datetime`、末行字符串 `0:00+1`（`_clock_label` 统一为 `H:MM`）。
- `data/附件2.xlsx`：工作表 `小区负载`、`光伏发电实际功率`，各 365 行 × 145 列（1 日期 + 144 个 10 分钟点）；
  md5 `bb3e493f804678de571575116eca1ae6`；日期 2025-01-01…12-31 连续；负载 ∈ [1995.7176, 7978.8849] kW、
  光伏 ∈ [0, 10216.2] kW，无 NaN/负值。日期序列用于交付期切片与 `result2.xlsx` 的行标签。
- `data/附件5/result2.xlsx`（模板）：md5 `b878ce2b016155f49486af25c51e8cab`，**无合并单元格**；
  - `计划购电量`：335 行 × 147 列；`A1 = 日期\时间`，`B1:EO1` 为 144 个区间标签（`0:10-0:20` … `0:00-0:10+1`），
    `EP1 = 全天购电量`、`EQ1 = 全天购电费`；`A2:A335` 为 2025-02-01…12-31（334 天）。
  - `充放电量`：表头 `日期/时间段/充电量/放电量/时刻/储电量`；模板示例仅 3 天 × 6 块（`max_row = 20`），
    交付需展开为 `1 + 334 × 6 = 2005` 行。
  - `紧急购电量`：表头 `日期/购电时间段/购电量`；模板含 `⁝` 压缩行，`max_row = 11`；本问按勘误 R4 展开为 335 行。
- `input_path` 取 `data/`（整目录参与 `input_hash`），因此附件 2/3/4 或模板变化会使 task ID 改变。

### 4.2 输出（正式模式，写入 `output_directory`）

| 文件 | 内容 |
|---|---|
| `result2.xlsx` | 三工作表：`计划购电量`（334 天 × 144 + 全天购电量 + 全天购电费）、`充放电量`（334 天 × 6 块，前两行载 0:00/24:00 储电量）、`紧急购电量`（334 行，`时间段 = —`、`购电量 = 0`）。**保存前经 `_residual_report` 逐格复核「应空却仍有值」，非空即硬门禁失败（exit 4）** |
| `solver_status.json` | `status/message/iterations/solver/objective/delivery_cost/device/gpu_required/seed/mip_gap`、`feasible_incumbent=true`、等式与界残差 |
| `solution.json` | 目标（计划/紧急/合计）、交付期与 1 月费用、`totals`、`identities`（全期与交付期切片）、逐日汇总（365 天）、逐条 `checks`、52,560 时段 9 列序列 |
| `tables.json` | 表 1/表 2/表 3（4 个指定日期）+ 表 1 标签校验结论 + 表 4 属格式示例的说明 |
| `run_manifest.json` | 版本/模型/参数/输入 md5（附件 1、附件 2、模板）/代码 sha256/环境/`task_id`/`matrix_scale`/`checks_failed`/`outcome` |

探针模式（`--days < 365`）**不写** `result2.xlsx`，改写 `probe_result2.xlsx`，并在 manifest 标 `probe_mode=true`
（交付文件不会被部分时段的试算污染）。`--days ≤ 31` 时交付期为空，则不写任何 xlsx。

---

## 5. 硬约束与失败条件

`solution.json` 中逐条检查（默认阈值 `1e-6`；探针模式跳过解析界与量级三项）：

- 结构：`equality_residual_max`、`bound_violation_max`、`cross_day_continuity`；
- 边界：`E ∈ [1200,10800]`、`c ≤ 833.3333`、`q_dis ≤ 750.0000`、`0 ≤ s ≤ PV·Δt`、`b ≥ 0`、`q_em ≥ 0`；
- 物理：`max_side_power_kw ≤ 5000`（并网点侧与电池侧各两次换算）、`complementarity_sum = 0`、
  `q_em_zero_total = 0`（定理 T1，依赖完全信息 + 无购电上限）；
- 恒等式：`Σq_dis = η²Σc − η(E_T − E_0)`、`Σb = N + Σs + 0.19Σc + η(E_T − E_0) − Σq_em`，以及**交付期切片**两条；
- 正式模式另加解析下界 `C ≥ min(p)·[N + η(E_min − E_0)]`、无储能可行解上界 `C ≤ Σ p·max(0, L−PV)`
  与交付期 10⁷ 量级自检（防 D9 的 Δt 误乘）。
- **填报格式（`act-56d59165992142b3` 新增）**：`fill_result2_workbook` 返回值 `format_residuals` 必须为空；
  非空则把 `result2_format_residuals` 计入 `checks_failed` 并以 exit 4 结束（防 `cell(value=None)`
  静默 no-op 让模板残留值进入交付答案文件）。

退出码语义：`0` 成功；`2` solver 非最优（写 `solver_status.json`、`feasible_incumbent=false`，**不伪报最优**）；
`3` 输入/模板结构不符；`4` 硬检查或表 1 标签校验失败（**仍写出全部产物**再返回，便于 sanity 定位）；
其余未捕获异常按 `code_runtime`。

---

## 6. 静态检查与小型探针（本动作实测，全部只写 action evidence 目录）

证据目录：`runtime/actions/act-a4b3a442051e4b00/evidence/`

1. **静态检查**：`compileall`（exit 0）；项目 venv 的 `ruff check code/` → *All checks passed*（line-length 120、E/F/I）；
   `run_prob02.py --help` → exit 0。evidence 内三个探针脚本同样通过 `compileall` 与 `ruff`。
2. **输入/模板结构探针**（`probe_inputs.py` / `probe_inputs_out.json`）：附件 1 md5 `dbe06f92…`、144 行、
   六个时段的时间戳 `10:00/12:00/14:00/16:00/18:00/20:00`；附件 2 md5 `bb3e493f…`、365 × 144；
   `result2.xlsx` md5 `b878ce2b…`、三工作表 147/6/3 列、**无合并单元格**、`计划购电量` 日期 2025-02-01…12-31。
3. **小型求解探针 1**（`--days 3`，432 时段 → `probe_run_d03/`）：exit 0、`checks_failed=[]`、
   `C = 148,027.316505 元`、`Σq_em = 0`、(I1)/(I2) 残差 0.0、`max c = 833.3333`、`max q_dis = 750.0000`、
   两侧功率 5000.0 kW、同充放 0。该截断窗的终端自由使 `E_T = 1200`（**属截断窗效应，不能外推到 365 天**）。
4. **小型求解探针 2**（`--days 32`，4608 时段，含 1 个交付日 → `probe_run_d32/`）：exit 0、`checks_failed=[]`、
   交付期费用 `16,618.967436 元`；`probe_result2.xlsx` 填 1 天 × 144 列、6 个 4 小时块、1 行紧急购电；
   `matrix_scale`（该规模）27,648 变量 / 9,216 等式 / 41,471 非零元（与公式 `9T−1` 一致）。
5. **全时域静态探针（不求解任何 LP）**（`probe_static_full.py` / `probe_static_full_out.json`）：把解析可行解
   `c = q_dis = q_em = 0、E ≡ 6000、b = max(0, L·Δt − PV·Δt)、s = max(0, PV·Δt − L·Δt)` 喂入
   `evaluate(full_horizon=True)`、`build_tables` 与 `fill_result2_workbook`，**25/25 检查通过**：
   - 矩阵规模：变量 **315,360**、等式行 **105,120**、非零元 **473,039**（与 formulation §3.9 逐项一致）；
   - 解析点残差 0；`checks_failed=[]`；全期费用 `18,298,592.366275 元` = formulation §3.10(b) 的构造上界
     `18,298,592.37`；交付期 `16,407,319.631981 元`（= 构造上界 `16,407,319.63`），10⁷ 量级自检通过；
   - (I2) 全期残差 `3.73e-09`、交付期切片 `−3.73e-09`（浮点舍入级），跨日连续性 0；
   - 区间标签：位置 78–80 → `13:00-13:30`（AS12 例子）、末时段 → `0:00+1-0:10+1`；连续段合并
     （`[77,80) ∪ [90,95)` → `13:00-13:30 / 15:10-16:00`）；`q_em = 0` → 无区间（表 3 写「无（0 kWh）」）；
   - 表 1 四个指定日期（3-20 / 6-21 / 9-23 / 12-21）全部 `label_matches = true`（附件时间戳 = 左端点、
     模板标签 = 完整区间）；表 2 每日 6 块；表 3 四日合计均为 0；
   - `result2.xlsx` 往返核对：`计划购电量` 335 × 147、`充放电量` 2005 行、`紧急购电量` 335 行；
     首日 144 个购电量与解的最大绝对差 `5.7e-14`；`充放电量` 第 1/2 行的 `时刻 = 00:00:00 / 24:00` 且储电量写在
     第 5/6 列、第 3–6 行两列留空；紧急购电 `时间段 = —`、`购电量 = 0`（勘误 R3/R4 落地）。
6. **task 规格预演**（`task_spec_dryrun.py`，调用真实 `automm.tasks.make_task_spec`，**不创建 task**）：
   `task_id = d5e2384e3128dd2a0649`、`backend = local`、`timeout_seconds = 900`、`seed = null`；
   `code_hash = b8f88661…`、`config_hash = ebd08796…`、`source_config_hash = f781f7f6…`、
   `input_hash = 4343d799…`（与 prob01 相同：`input_path = data` 未变）；
   `preflight = {compileall: passed, ruff: unavailable}`（`make_task_spec` 用 `shutil.which("ruff")` 探测 PATH，
   项目 venv 的 ruff 不在 PATH；第 1 项的显式 ruff 检查已通过，两者不矛盾）；
   `output_directory` 位于 `assumption_v001/` 内且与 `--output` 完全一致。
7. 所有探针 JSON 通过 `allow_nan=False` 落盘；`NaN/Infinity` 关键字扫描为空。

> 说明：`make_task_spec` 的预演只构造 spec，不调用 `submit_task`；implementation 阶段未创建任何 task、
> 未写 `results/` 目录（`problems/.../prob02/versions/assumption_v001/results/` 仍为空）。

### 6.1 修订动作 `act-56d59165992142b3`：交付格式缺陷修复与验证

1. **根因复现**（`probe_result2_format_fix.py`）：对模板副本执行 `ws.cell(row=15, column=1, value=None)` 后
   `充放电量!A15` 仍为 `2025-12-31` —— 证实 openpyxl 的 `value=None` 是静默 no-op，无法清空模板残留。
2. **修复点**（只改 `prob02_io.py` / `run_prob02.py`，不动模型与口径）：
   - 新增 `_assign(sheet, *, row, column, value)`：直接设置 `cell.value`，**含 `None` 也真正清空**；
   - `_clear_rows` 与 `fill_result2_workbook` 的全部写入改走 `_assign`，禁止再用 `cell(..., value=None)`；
   - 新增 `_residual_report`：保存前逐格复核「应空却仍有值」（充放电量日期/时刻/储电量行位、超出行数的
     计划/紧急/充放电残留、全簿 `⁝`），经返回值 `format_residuals` 暴露；
   - `run_prob02.main`：`format_residuals` 非空即把 `result2_format_residuals` 计入 `checks_failed`（exit 4）。
3. **探针 1（纯静态、假造 3 个交付日、不求解、不写 `results/`）**：`evidence/probe_result2_format_fix.py`
   → **11/11 通过**：根因复现、`format_residuals=[]`、旧缺陷单元 `充放电量!A15`/`!E16` 为空、
   每日 6 块 R3 版式成立、超出行数的模板残留清除（计划 `row5..335`、紧急 `row5..11`、充放电 `row20`）、
   全簿无 `⁝`、写入值与紧急购电行抽查通过（三日分别 `— / 10:00-10:30 / —`）。
4. **探针 2（端到端 `--days 34`、交付 3 日、probe 模式，只写 evidence）**：exit 0、`checks_failed=[]`、
   2.34 s、`C=1,646,320.8861 元`、`Σq_em=0`；`evidence/probe_run_d34_scan.py` 独立只读扫描 0 问题
   （该探针数值只是接口自检，**不是交付数值**）。
5. **静态检查**：`compileall` exit 0；venv 的 `ruff` 对 `code/` 与 evidence 均 *All checks passed*；
   `run_prob02.py --help` exit 0。
6. **task 规格预演**（真实 `automm.tasks.make_task_spec`，**不创建 task**）：新 `task_id=dc8afc3deb5477641b99`、
   `code_hash=a37eda25…`、`config_hash=ebd08796…`、`input_hash=4343d799…`、
   `output_directory=.../results/prob02_v001_f001_run002`、`preflight={compileall: passed, ruff: unavailable}`
   （`evidence/task_spec_dryrun.json`）。

### 6.2 恢复动作 `act-a3f8a085f60b42ee`：重试并复核（复用 §6.1 产物）

背景：`act-56d59165992142b3` 的响应被 Harness 在 `_validate_response_context` 阶段拒绝
（`FileNotFoundError: runtime/actions/act-56d59165992142b3/evidence/compileall_out.txt`——该响应把未落盘的
`compileall_out.txt` 写进了 `artifacts_created`，命令批次从未应用、阶段未迁移，代码与 `implementation.md`
的修订已落盘）。本次恢复动作不重复修改代码，只**在自身 evidence 目录重跑全部静态检查与小型探针**：

1. `compileall`（`code/`）exit 0 → `evidence/compileall_out.txt`；`ruff check` 对 `code/` 与 `evidence/`
   均 *All checks passed*（ruff 0.16.5）→ `evidence/ruff_out.txt`；`run_prob02.py --help` exit 0 → `evidence/cli_help.txt`。
2. 探针 1 复跑：`evidence/probe_result2_format_fix_out.json` → **11/11 通过**，与 §6.1 逐项一致
   （根因复现、旧缺陷单元 `A15`/`E16` 为空、`format_residuals=[]`、超出行数清除、全簿无 `⁝`）。
3. 探针 2 复跑：端到端 `--days 34` exit 0、`checks_failed=[]`、`Σq_em=0`、`C=1,646,320.8861 元`，
   独立扫描 `evidence/probe_run_d34_scan.py` 0 问题（`format_residuals=[]`）。
4. `make_task_spec` dry-run 复跑：`task_id=dc8afc3deb5477641b99`、`code_hash=a37eda25…`、
   `config_hash=ebd08796…`、`input_hash=4343d799…`，与 §6.1 **逐位一致**（确定性验证）。
5. 输入未变：附件 1 `dbe06f92…`、附件 2 `bb3e493f…`、模板 `b878ce2b…`（`evidence/input_md5_check.txt`）；
   run001 复扫仍为 `deviation_count=2`（`evidence/run001_rescan_out.json`），证明 run001 未被就地修补。
6. 本动作**未创建 task、未写 `results/`**（`results/` 仍只有 `run001`）、未改任何口径与数值。

---

## 7. 交给 computation 阶段的 task 规格

见 `code/task_spec.yaml`（本文件为规格，不由 implementation 执行）。核心命令：

```text
.venv/Scripts/python.exe \
  problems/microgrid_2025/prob02/versions/assumption_v001/code/run_prob02.py \
  --data data/附件1.xlsx \
  --data2 data/附件2.xlsx \
  --template data/附件5/result2.xlsx \
  --output problems/microgrid_2025/prob02/versions/assumption_v001/results/prob02_v001_f001_run002 \
  --days 365 --time-limit 300
```

- `output_directory`：`problems/microgrid_2025/prob02/versions/assumption_v001/results/prob02_v001_f001_run002`
  （**修订后的重跑目录**：run001 已 succeeded 但其 `result2.xlsx` 有填报残留缺陷，按重跑纪律换新目录，
  不得覆盖 run001；run001 产物保留供对照）
- `worker_launch_mode`：`supervised`（`config/compute.yaml`，Runner 原地运行 worker）。`detached` 在本 DSH 沙箱
  环境会被进程树回收（prob01 的两次心跳探针与 task `b87194aa7fada61ee0d8` 的 `interrupted` 已记录），故必须 supervised。
- `input_path`：`data`；`config_path`：`code/task_config.yaml`；`code_path`：`code`
- `--output` 必须与 `output_directory` 完全一致（`make_task_spec` 强校验，预演已通过）
- 资源：CPU、formulation 探针 26.8 s（预算 ≤ 300 s）、峰值内存 113 MB（预算 ≤ 2 GB）、超时 900 s；
  `seed=null`；**不占 GPU**；单卡 GPU 串行约束不适用
- 本次预演（`act-56d59165992142b3`）：`task_id = dc8afc3deb5477641b99`、`code_hash = a37eda25…`、
  `config_hash = ebd08796…`、`input_hash = 4343d799…`（`evidence/task_spec_dryrun.json`；
  run001 的 `task_id = d5e2384e3128dd2a0649` / `code_hash = b8f88661…` 已随代码修复失效）

---

## 8. 下游要求（sanity / ablation / robustness / visualization）

1. **不比对逐点解唯一性**：LP 最优面可能不唯一（formulation 探针记录 `E` 上下界两端均活跃、`c`/`q_dis`
   上界均被顶到）。sanity 以「约束残差 + (I1)/(I2)（含终端项）+ 目标值 + 表 1/表 2/表 3 + `result2.xlsx`」为准。
2. sanity 必须**两次换算功率**核对两侧 `≤ 5000 kW`（E1），并独立复核 `q_dis ≤ 750.00`、`c ≤ 833.3333`。
3. `result2.xlsx` 的 0:00/24:00 是**计划窗首/末状态**（AS01 左端点口径使计划窗为 `0:10 → 24:10`，模板固有相位），
   prob02 为全年滚动切片（`E_{d,0}` 随日变化，**不恒为 6000**）；论文与图注须显式区分 prob01（单日周期、端点恒 6000）
   与 prob02（勘误 R1）。
4. 表 3 主口径全为「无（0 kWh）」；论文必须写入**题面表 4 是格式示例（其 2025/3/1 与三个区间不是本问答案）**，
   否则评阅人会以表 4 比对答案。
5. `ablation` 按 B1/B5 在 `ablations/code/` 另建 M2–M7（不得改动本 `code/`）；M6 网格与建议的 M6′ 须先由团队裁定
   **D4**，并按预注册判据 C1–C7（C2 只判 M2a）在跑数前冻结于 `ablations/plan.md`。本实现不提供 M2–M7 代码。
6. `robustness` 负责参数扰动与置信区间（η、E_init、α_em、负载/光伏噪声、`s` 的界、购电上限情景），
   与 ablation 的数值不得互相替代（B5）；D10 的多日增量须按 prob02 实际负载/光伏重算，不得沿用「约一成工作日」。
7. 禁止复用任何 `p_t·b_t·Δt` 口径；禁止把 5000 kW 直接当电量上界（漏乘 Δt 会放大可行域 6 倍）；
   禁止使用附件 1 的负载/光伏预测列、附件 3、附件 4。

---

## 9. 遗留风险与已知限制

- 截断窗探针（`--days < 365`）只验证接口与求解路径，**不能替代正式计算**：它跳过解析界与量级检查，
  且 `--days ≤ 31` 时交付期为空、不写 xlsx。
- 全时域静态探针喂入的是**解析可行点**（无储能），只覆盖「约束/恒等式/表映射/xlsx 填报」路径，
  不覆盖最优解的结构（`E` 轨迹、储能套利、`Σs` 等）；正式数值一律以 computation 产物为准。
- `solution.json` 含 52,560 时段 × 9 列序列（预计 10 MB 量级），是 sanity 复核 (I1)/(I2) 与跨日连续性的需要；
  若下游只需交付数值，可只读 `totals/identities/daily`、`tables.json` 与 `result2.xlsx`。
- `make_task_spec` 的 ruff 预检依赖 PATH；若提交环境 PATH 无 ruff，则只做 `compileall`（本动作已用 venv 内 ruff
  显式检查通过，风险已知且不阻塞）。
- `run_manifest.json` 的 `code_sha256` 由脚本自算（按 `*.py` 逐文件 + 目录摘要），与 harness 的 `code_hash`
  （含 `task_config.yaml`/`task_spec.yaml`）算法不同；追踪与 task ID 以 harness 值为准。
- 需团队裁定后才能跨阶段引用的事项：**C6/D4**（M6 网格与 M6′）、**D2**（C2 只判 M2a）、**D3**（M4 时域 365 天）、
  **D5**（M3 预算处置）、**D8**（M5 是否进 robustness）——本实现只实现 M1，不受这些未决项影响。
- **交付格式缺陷（已修复，`act-56d59165992142b3`）**：run001 的 `result2.xlsx` 残留 `充放电量!A15`/`!E16`
  属 `openpyxl` `cell(value=None)` 静默 no-op；修复只影响填报清空路径与新增硬门禁，**不改动任何数值**。
  run001 目录整体保留（其数值仍可用于对照），但其 `result2.xlsx` **不得作为最终答案文件**；
  正式交付以 `run002` 的 `result2.xlsx` 为准，sanity 须对 run002 重跑逐格扫描。
- 本修订动作的探针数值（`--days 34` 的 `C=1,646,320.8861 元` 等）只是接口自检，**不得作为论文/sanity 数值**。

---

## 10. 未越界声明

- 未修改 `assumptions.md`、`version.yaml`、`global_symbols.yaml`、`citations.yaml`、`question_manifest.yaml`、
  `runtime/workflow_state.json`、`data/`、`request/` 与 `prob01/` 任何产物。
- 未创建/提交任何计算 task、未写 `results/`、未运行 365 天完整计算或完整 MILP。
- 本修订动作（`act-56d59165992142b3`）只在 `code/` 与 `implementation.md` 内改动，探针与产出一律写
  `runtime/actions/act-56d59165992142b3/evidence/`；**未覆盖 run001 任何文件**（run001 的
  `result2.xlsx`、`run_manifest.json`、`solver_status.json`、`solution.json`、`tables.json` 保持原样）。
- A6/A7/A8/A9 属 prob03/04，本实现不裁定、不使用附件 3/4。
- 未把 `α_em = 5`、`q_em ≡ 0` 包装为文献结论；未把 D10「5000 kW 作用侧」包装为文献支持。
