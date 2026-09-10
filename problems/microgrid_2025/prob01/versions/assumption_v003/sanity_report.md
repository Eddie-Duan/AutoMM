# Sanity Check Report

- problem_id: microgrid_2025
- question_id: prob01
- assumption_version: assumption_v003（accepted；末尾含团队勘误 E1–E3）
- formulation_version: formulation_v001（accepted）
- task_id: 1300a936c4d95653f9d1（attempt 1，status=succeeded，returncode=0）
- output_directory: problems/microgrid_2025/prob01/versions/assumption_v003/results/prob01_v003_f001_run002
- overall: **PASS_WITH_WARNING**
- checked_at: 2026-09-10T12:55:00+00:00

> 本报告由 `sanity-checker`（动作 `act-8d27775ff3714942`，action=`inspect_compute_result`，stage=`computation`）出具。
> 自动项由 `scripts/run_sanity_check.py` 运行（`machine_sanity.json`，automated_status=PASS_WITH_WARNING，failures=0）；
> 语义项由独立只读复核脚本 `evidence/independent_sanity.py` 回代验证（status=PASS，failures=[]，见
> `evidence/independent_sanity_out.json`）。检查过程不重解 LP、不修改模型或代码、不修改任何原始数据。

---

## Level 1：文件和运行完整性

| 检查项 | 方法 / 证据 | 阈值 | 实测 | 判定 |
|---|---|---|---|---|
| 任务终态 | `runtime/tasks/1300a936c4d95653f9d1/status.json` | status=succeeded, returncode=0 | succeeded, 0, feasible_incumbent=true | PASS |
| 必需产物 | 结果目录 5 个文件存在 | 全部存在 | solution/solver_status/tables/run_manifest/result1.xlsx | PASS |
| 输入未被修改 | 附件 1 md5 vs run_manifest | 相等 | `dbe06f92517431228efcc26e3e796ef9`（两侧一致） | PASS |
| 模板未被修改 | `data/附件5/result1.xlsx` md5 | 登记值 | `74adc298ba5e1825482464a4ea4e26ec` | PASS |
| 运行口径 | run_manifest | periods=144, probe_mode=false | 144 / false | PASS |
| 追踪链 | run_manifest / task.json | code_hash、config_hash、input_hash、task_id 齐备 | code_hash `fcc714bf…`、config_hash `331a6ba8…`、input_hash `4343d799…` | PASS |
| 代码指纹 | run_manifest.code_sha256 vs implementation.md §2 | 逐文件一致 | prob01_io/prob01_model/run_prob01 三个 sha256 一致 | PASS |
| 实现自检 | solution.json `checks` / `checks_failed` | 全 passed；checks_failed=[] | 17/17 passed；[] | PASS |
| worker 日志 | attempt-001 stdout/stderr | 存在且 rc=0 | stdout 记录 `C*=35126.9486 元，sum_b=59482.6990 kWh，sum_spill=0.0000 kWh，失败检查=[]`；stderr 空 | PASS |

- **历史隔离**：本次为 `run002`；前序 attempt-001 / task `b87194aa7fada61ee0d8` 以 `failure_type=interrupted` 结束、
  `results/..._run001` 为空，未被复用或覆盖；本次以 `worker_launch_mode=supervised` 启动并正常退出。
- L1 结论：**PASS**。

## Level 2：数值范围和约束

自动项：结果目录 4 个数值文件（solution/tables/solver_status/run_manifest）全部 `finite=true`，NaN/Inf 计数 0。

独立回代（不重解，只把 `solution.json` 的 144 时段序列代回原始附件 1）：

| 检查项 | 阈值 | 实测 | 判定 |
|---|---|---|---|
| R1 功率平衡残差 `b+PV·Δt+q−L·Δt−c−s` | ≤1e-6 kWh | max 残差 0.0 | PASS |
| R2 SOC 动态残差 `E_t−E_{t−1}−0.9c_t+q_t/0.9` | ≤1e-6 kWh | max 残差 0.0 | PASS |
| 等式残差（实现自报） | ≤1e-6 | 4.547e-13 | PASS |
| 变量界越界 | ≤1e-6 | 0.0 | PASS |
| `E_t ∈ [1200, 10800]` | 双侧 | E∈[1200.0000, 10800.0000]（**两端均活跃**） | PASS |
| 周期端点 `E_144=E_0=6000` | ≤1e-6 | gap 0.0 | PASS |
| 充电上限 `c_t ≤ 833.3333`（并网点侧紧） | ≤1e-6 | c_max = 833.333333（顶到上限） | PASS |
| 放电上限 `q_dis_t ≤ 750.0000`（E1，电池侧紧） | ≤1e-6 | q_max = 715.653033（**未顶到上限**，余地 34.35 kWh） | PASS |
| 弃光 `0 ≤ s_t ≤ PV_t·Δt` | ≤1e-6 | Σs = 0.0，逐点满足 | PASS |
| 购电非负 `b_t ≥ 0` | ≤1e-6 | min ≥ 0 | PASS |
| 互补性 `Σ c_t·q_dis_t` | ≤1e-6 | 0.0；同时充放时段数 0 | PASS |
| (I1) `Σq = 0.81Σc` | ≤1e-6 | −3.638e-12 | PASS |
| (I2) `Σb = N + Σs + 0.19Σc` | ≤1e-6 | 4.547e-12 | PASS |
| 两侧换算功率 ≤ 5000 kW（E1 要求） | ≤5000 kW | max = 5000.0（充电并网点侧紧）；充电电池侧 4500.0；放电并网点侧 4293.92；放电电池侧 4771.02 | PASS |

- 汇总：`C* = 35126.948589 元`、`Σb = 59482.698998 kWh`、`Σc = 20740.666132 kWh`、`Σq = 16799.939567 kWh`、
  `Σs = 0`、净负荷 `N = 55541.972433 kWh`；表格与序列逐项一致。
- L2 结论：**PASS**。

## Level 3：量纲和公式

1. **目标量纲（D9）**：目标实现为 `min Σ p_t·b_t`（`p_t` 元/kWh × `b_t` kWh = 元），全文无 `p_t·b_t·Δt`；
   独立复核 `Σ p_t·b_t = 35126.948589`，而被否变体 `Σ p_t·b_t·Δt = 5854.49` 元（约 1/6），二者差异显著，
   确认未误乘 Δt；费用量级 10⁴ 元通过 `magnitude_10k` 自检。
2. **电量/功率换算（AS09）**：`Δt = 1/6 h`；平衡式两侧同为 kWh；功率上限以 `5000·Δt = 833.3333`（充电，并网点侧）
   与 `5000·Δt·0.9 = 750.0000`（放电，电池侧）落在电量域，功率换算复核见 L2 末行。无 kW/kWh 或 kWh/元 混用。
3. **formulation 与实现一致（formulation_v001 §3.8 ↔ code/prob01_model.py）**：以真实 144 时段数据
   **只构造矩阵、不求解**，实测 `x=(b,c,q,s,E)∈R^720`、等式 288、变量界 720、`A_eq` 非零元 1151、
   目标非零元 144，与 §3.8/候选 A 登记逐项一致；代码常量 `Δt=1/6、η_ch=η_dis=0.9、E_init=6000、
   E∈[1200,10800]、C_CAP=833.3333、Q_CAP=750.0（团队勘误 E1）、P_MAX=5000` 与 accepted 口径一致。
4. **表 1 / 表 2 / result1.xlsx**：表 1 六个时段（10:00/12:00/14:00/16:00/18:00/20:00-…:10）
   同时通过「附件时间戳=区间左端点」与「模板标签=完整区间」双重校验，取值与序列第 60/72/84/96/108/120 项
   逐一相等；表 2 六块（行 1–24…121–144）充放电量与序列块和一致、充放电**分别列示不冲抵**；
   0:00/24:00 = `E_0`/`E_144` = 6000 kWh。写出的 `result1.xlsx`：144 行购电量与序列逐点一致（max |Δ|=0）、
   6 块充放电量一致（|Δ|≤1e-6）、E2/E3 端点 = 6000、模板标签原样保留。
5. **相位说明**：AS01 左端点口径使计划窗为 `0:10→24:10`（模板固有相位）。表 2 标注的「0:00-4:00」按模板行位置
   聚合的是物理区间 `0:10-4:10`。此为团队裁定 D8/AS13 的记录口径，**不是数据错误**，但论文与图注须显式说明一次，
   不得与严格时钟口径混用。
6. 次要瑕疵：`tables.json` 的块和按 6 位小数舍入，而 `result1.xlsx` 写入全精度（差 < 1e-6）；属显示精度问题，
   不影响数值与交付。
- L3 结论：**PASS**。

## Level 4：常识与文献合理性

1. **经济/物理常识（硬门禁）**：
   - 费用 `C* = 35126.95 元` 落在解析区间 `[20622.73, 48052.05]` 元内且为 10⁴ 量级（解析下界由 D9 口径给出）；
     全天购电量 `59482.70 kWh ≥` 净负荷 `55541.97 kWh`（多出部分为储能循环损耗 0.19·Σc，量纲闭合）。
   - 套利方向合理：最便宜 20% 电价时段承担了 **55.4%** 的充电量；最贵 20% 电价时段承担了 **63.7%** 的放电量；
     `corr(电价, 充电) = −0.446`、`corr(电价, 放电) = +0.592`，符合「低价充、高价放」的题面动机。
   - 弃光 `Σs = 0`：附件 1 光伏峰值 7612.32 kW > 负载峰值 5958.97 kW，盈余在最优解中全部被储能吸收而未弃，
     与 assumption_v003 §6 探针结论一致；变量保留以闭合平衡。
   - 极端/退化：`E_t` 上下界 1200 与 10800 **两端均活跃**，印证 formulation 关于「LP 最优面可能不唯一」的登记；
     本 sanity 以**约束残差 + (I1)/(I2) + 目标值 + 表 1/表 2** 为验收依据，不比对逐点解唯一性（符合 implementation §8.1）。
2. **关键假设文献门禁（硬门禁）**：真实调用 `automm.research.check_key_assumptions('microgrid_2025','prob01')`
   → `passed=true, errors=[], assumption_version=assumption_v003`；10 条关键假设各自绑定 ≥1 条
   `verified=true & status=used` 来源；团队勘误 D11/E1/E2 在下游执行口径中均已落地。
3. **证据强度限制（警告）**：文献池 25 条全部未逐篇读正文（21 条 Crossref 元数据级、4 条开放摘要）；
   本问引用只支撑框架级/机制级主张，任何公式级或定量级引用仍须取得全文后方可使用。
4. **口径文献缺口（警告）**：AS06 的「5000 kW 作用侧」为团队裁定 D10（`team_decision`），现有文献池无一条涉及，
   实现与本文均未包装为文献支持；论文若需文献依据须补定向检索或取得 `ref-vykhodtsev-2022-bess-review` 全文。
5. 题面硬约束逐条满足：0:00/24:00 储电量相同（AS10/AS11）、SOC ∈ [1200,10800]（AS06）、效率 90%（AS05）、
   「微网提供的电能不低于负载」（AS04：供给 = `L·Δt + c_t ≥ L·Δt`）。
- L4 结论：**PASS_WITH_WARNING**（技术债见「路由」的 warnings）。

## Level 5：跨小问一致性

- **本阶段不适用（not_applicable）**：L5 的触发条件是「所有小问 locally completed」，当前仅 prob01 完成计算，
  prob02–prob04 尚未进入假设/公式阶段。
- 已登记的跨小问欠账（待 `cross_question_review` 回写，属于登记同步而非结果缺陷）：
  - **C1/E1**：`problems/microgrid_2025/global_symbols.yaml` 仍把 `q_dis` 域登记为 `P_dis_max·Δt = 833.33`，
    与团队勘误 E1 的 `750.00` 冲突；下游已按 750.00 执行，符号表本身待更新（prob02–prob04 沿用 750.00）。
  - **C2/E2**：符号表登记 `q_spill` 的 `first_question = prob02`，但 AS08/D4 已裁定 prob01 即引入 `s_t`。
  - **C3/E3**：`version.yaml` 中 AS08 的 statement 仍含「必然被激活」，与实测 `Σs_t = 0` 不符（措辞待更正）。

## Level 6：鲁棒性和敏感性

> **更新（动作 `act-4694208eb3ce490d`，2026-09-10T13:52Z）**：robustness 阶段已完成
> （`record_optional_stage(stage="robustness", decision="completed")`，task `238db2418a6b1aed432b`）。
> L6 已在本报告末尾「附：Level 6 鲁棒性与敏感性复核」正式执行，判定 **PASS_WITH_WARNING**。
> 以下为 L1–L4 阶段（robustness 尚未执行时）的原始记录，**保留不改**以维持审计轨迹。

- **当时状态（not_applicable）**：L6 的触发条件是 `after_robustness`。manifest 的
  `optional_stages.robustness/ablation` 仍为 `pending`，尚未裁定是否执行；按 `config/sanity_check.yaml`
  与 workflow 顺序，robustness/ablation 与 L6 由后续阶段（visualization → robustness → sanity_check L6）处理。
- 已知需在 robustness 中量化的显式简化（不在本阶段判失败）：常效率 90%（AS05）、不计折旧（AS03b）、
  不显式强制同时充放（AS07，本解互补性已成立）、无自放电（AS14）、无购电上限/无售电（AS15）、单日确定性（AS16）、
  5000 kW 作用侧取交集（AS06/D10，多日费用增量已在假设阶段量化为全期约 6916.19 元）。

---

## 路由

- failure_type: `null`
- return_to_stage: `null`
- blocking_reasons: `[]`
- recommended_next_stage: `visualization`（由下一唤醒在 `sanity_check` 阶段执行阶段迁移）
- 命令：`record_artifact(sanity_check)`、`record_sanity(level_1_4, PASS_WITH_WARNING)`、`append_ledger`
- 机器报告：`machine_sanity.json`；独立复核：`runtime/actions/act-8d27775ff3714942/evidence/independent_sanity_out.json`

**warnings（技术债，允许推进但须登记/后续处理）**

1. 文献池 25 条未逐篇读正文（21 元数据级 + 4 摘要级），引用只支撑框架级主张；公式级/定量级引用须取得全文后再用。
2. AS06「5000 kW 作用侧」为 team_decision（D10），无文献支撑；论文不得包装为文献支持。
3. C1/E1、C2/E2、C3/E3 三处上游登记/措辞尚未回写（`global_symbols.yaml`、`version.yaml`），待 `cross_question_review` 更正；
   下游执行口径已按团队勘误 E1/E2/E3，不影响本问结果。
4. 表 2 的「0:00-4:00」等为模板行位置聚合（物理窗 `0:10→24:10` 相位前移 10 分钟），论文/图注须显式说明一次。
5. LP 最优面可能不唯一（E 上下界两端均活跃）；sanity 以约束残差 + (I1)/(I2) + 目标值 + 表 1/表 2 为验收依据，
   不比对逐点解唯一性。
6. `tables.json` 块和按 6 位小数舍入、`result1.xlsx` 为全精度，差 < 1e-6，属显示精度问题。
7. A2（结果日期 2025-02-01～12-31 与储能跨日衔接）、A6、A7、A8、A9 仍未裁定且属 prob02–prob04；本问未越界处理。

---

## 附：`sanity_check` 阶段的复核补充（动作 `act-f01ed23959c44dd4`）

- **调用背景**：上一动作 `act-8d27775ff3714942` 在 `stage=computation`（`inspect_compute_result`）完成了 L1–L4 并触发 Runner 的确定性迁移；本动作是 **`sanity_check` 阶段**对 sanity-checker 的正式调用（policy P3 `run_agent`），
  用于阶段级复核与阶段迁移。两者对象、口径、结果完全一致，非新版本、非重算。
- **复核方式（全部只读，不重解 LP、不修改模型/代码/假设/原始数据、不覆盖既有产物）**：
  - `evidence/independent_sanity.py`：从附件 1 + run002 产物独立回代，68 项断言；
  - `evidence/verify_l1_trace.py`：17 项 L1/追踪链复核，含 **代码 sha256 三方一致**（实际文件 = `run_manifest.code_sha256` = `implementation.md` §2）；
  - `automm.research.check_key_assumptions('microgrid_2025','prob01')`：关键假设文献门禁复跑。
- **复核结果（与上一动作逐位一致，可复现）**：
  - independent `status=PASS`、`failures=[]`、`warnings=[]`；
  - automated `automated_status=PASS_WITH_WARNING`、`failures=0`、4 个数值文件全 finite；
  - L1 追踪链 `status=PASS`、`failures=[]`（输入 md5、模板 md5、代码 sha256、task 终态/日志、run001 未被复用、run002 五产物齐备）；
  - 关键假设文献门禁 `passed=true`、`errors=[]`、`assumption_version=assumption_v003`；
  - 关键数值：`C*=35126.948589 元`、`Σb=59482.698998 kWh`、`Σc=20740.666132 kWh`、`Σq=16799.939567 kWh`、`Σs=0`、
    净负荷 `55541.972433 kWh`、`c_max=833.333333`、`q_max=715.653033`、两侧换算功率 `max=5000.0 kW`、
    等式残差 `4.547e-13`、`E∈[1200.0000,10800.0000]`、`E_144=E_0=6000`。
- **判定与路由不变**：`overall=PASS_WITH_WARNING`；`failure_type=null`、`return_to_stage=null`、`blocking=[]`；
  warnings 同上（文献证据等级、AS06 口径无文献支撑、C1/E1·C2/E2·C3/E3 登记欠账、表 2 相位说明、
  LP 最优面非唯一、`tables.json` 6 位舍入、A2/A6/A7/A8/A9 未裁定）。
- **本动作请求**：`record_sanity(level_1_4, PASS_WITH_WARNING)` + 阶段迁移 `sanity_check → visualization`。
- 证据目录：`runtime/actions/act-f01ed23959c44dd4/evidence/`
  （`independent_sanity.py` / `independent_sanity_out.json` / `verify_l1_trace.py` / `verify_l1_trace_out.json` /
  `automated_sanity_out.json` / `key_assumptions_out.json`）。

---

## 附：Level 6 鲁棒性与敏感性复核（动作 `act-4694208eb3ce490d`）

- **调用背景**：robustness 阶段完成（`record_optional_stage(stage="robustness", decision="completed")`）后，
  Runner 按 `config/sanity_check.yaml` 的 `level_6.trigger = after_robustness` 迁移到 `sanity_check` 并调用 sanity-checker
  （policy P3 `run_agent`，`level=level_6`）。这是 **L6 的正式执行**，不是重跑 robustness。
- **对象（只读）**：`assumption_v003`（accepted，含团队裁定 D9/D10/D11、团队勘误 E1–E3）+ `formulation_v001`（accepted）
  + `robustness/results/prob01_v003_robust_run001`（task `238db2418a6b1aed432b` / attempt 1 / `succeeded` / rc=0 / supervised / CPU）。
- **复核方式（全部只读，不重解 LP、不修改模型/代码/假设/结果/原始数据，不覆盖任何版本目录文件）**：
  - `evidence/verify_level6.py`：从 `raw_samples.jsonl`（948 行）独立重算 S1–S6、硬检查统计、基线闸门、追踪链与结构族发现，
    共 **84 项断言**，`verdict=PASS`、`checks_failed=0`（`evidence/verify_level6_out.json`）；
  - `scripts/run_sanity_check.py`：自动 L1/L2-finite 范围（输出重定向到 `evidence/auto_scope/`，**未覆盖版本目录**），
    `automated_status=PASS_WITH_WARNING`、`failures=0`、5 个汇总 JSON 全 `finite=true`；
  - `automm.research.check_key_assumptions('microgrid_2025','prob01')`：`passed=true`、`errors=[]`（`evidence/key_assumptions_L6_out.json`）；
  - 图件抽检：`robustness_tornado.png`（确认 D-R4 图例 ±20% 与轴标签实际取值不一致）、
    `robustness_scenarios.png`（确认 D-R5 缺 `buycap_3000` 一格）。

| 判据 | 预注册阈值 | 实测（独立重算） | 判定 |
|---|---|---|---|
| S1 核心族可行率 | ≥0.95 | 1.000（934/934，含 900 噪声样本） | PASS |
| S1 参数族可行率 | ≥0.99 | 1.000（34/34） | PASS |
| S2 OAT 最大 `\|ΔC\|/C*` | ≤0.25 | 0.088848（η=0.80 → +8.885%） | PASS |
| S3 联合 σ=20% 区间半宽 | ≤0.20 | 0.115132（全距法）；**预注册分位法 0.096675** | PASS（含 D-R1） |
| S3 联合 σ=20% 均值偏移 | ≤0.10 | 0.065288 | PASS |
| S4 排序稳定 `C_opt<C_nostorage` | 100% | 934/934，最小套利比 0.204032 | PASS |
| S5 敏感性符号与弹性 | 三条同时成立 | `∂C/∂η≤0`、`∂C/∂P_max≤0`、`\|弹性(E_init)\|≤1.5` | PASS |
| S6 求解器一致性 | ≤1e-6 | 0.0（`highs`/`highs-ds`/`highs-ipm`/`highs(nopresolve)`） | PASS |

- **数值健康度（独立复算）**：948 样本中 947 可行，唯一不可行点 `buycap_3000`（结构族，`checks_failed=[no_solution]`，
  `objective_yuan=null`）保留在原始样本并计入该族分母（可行率 0.75），未删除、未进均值；`NaN`/`Inf` 0 次；
  可行样本 `max equality_residual=3.638e-12`、`max bound_violation=1.819e-12`、同时充放时段数 0、
  `|E_144−E_0|≤1e-6`、`checks_failed` 并集仅 `no_solution`；`E` 界与单侧功率按**各族自己的参数**核对全部通过
  （`d10_yi` 的 5555.5556 kW 是**被否口径**越限的独立复现，非实现缺陷；`d10_bing ≡ d10_jia` 且两侧功率 ≤5000 kW）。
- **基线闸门（独立复核）**：`C*=35126.948589 元`、`Σb=59482.698998 kWh`、`Σc=20740.666132 kWh`、
  `Σq=16799.939567 kWh`、`Σs=0`、`max_side_power=5000 kW` 与 accepted `run002` 逐位一致（相对差 0.0）；
  追踪链：`data/附件1.xlsx` md5 `dbe06f92517431228efcc26e3e796ef9` 未变、`run002/solution.json` sha256 `b083ac3b…9c7010`
  未被修改、accepted 代码与 robustness 代码 sha256 与 `run_manifest` 一致。
- **独立归因复核**：`self_discharge` 族 `|I1|` 残差（最大 1.373e3）按 `|I1|/(ρΔt)` 换算为 824,021 / 895,715 / 941,122 kWh，
  与「144 时段储电量和」量级一致，确认是**改变状态转移后的必然差值**而非数值失败（与核心族分离统计，D-R8）；
  `deg_0.50` 的 `Σc=6,247.963 kWh` 恰等于附件 1 的逐时段物理盈余上限 `Σmax(0,PV−L)·Δt`，为独立量级交叉验证。
- **判定：`PASS_WITH_WARNING`（L6）**。理由：S1–S6 全部通过且 `stability_grade=稳定`、`criteria_failed=[]`；
  三条硬门禁（关键假设引用、物理/经济常识、跨小问一致性[本阶段不触发]）无失败；存在下列**技术债**，
  均已在 `robustness/report.md` §9/§10 显式登记，不构成硬门禁失败：
  1. **D-R1（预注册统计量偏离）**：S3 实际用 `(max−min)/2` 全距半宽（0.115132），预注册为 2.5–97.5 分位半宽（0.096675）；
     两者均 ≤0.20、判定不变，实现更保守，但判据不事后修改，论文引用 L6 区间时必须注明实际统计量。
  2. **D-R2**：S2 对全部 OAT 网格取最大（含 `E_init ±50%`、`E_min −50%/+100%`），是预注册的超集（更保守）。
  3. **D-R3（追踪链欠账）**：噪声样本未记录 plan §3.3 声称的「扰动后输入摘要指纹」，仅有 `(source, σ, index)` 与因子均值；
     可复现性由固定 seed 20260910 + 固定样本序保证，须在论文/后续版本说明。
  4. **D-R4/D-R5/D-R6（图件口径）**：龙卷风图图例名义 ±20% 而实际取值为 η 0.8–1.0、`E_init` 4500–7500、`P_max` 4000–6000；
     结构情景图缺 `buycap_3000`（不可行、无目标值）；spider 图横轴按各参数自身网格半跨度归一化。引用这些实验图时须按 y 轴标签/实际取值读。
  5. **§8.6 售电情景非物理**：`sell_price ≥0.50 元/kWh` 时 LP 售出 12,293.617 kWh，超过附件 1 的物理盈余上限 6,247.963 kWh，
     根因是 AS08 的 `s_t ≤ PV_t·Δt` 未收紧到 `(PV_t−L_t)·Δt`。accepted 基线（无售电、`Σs=0`）不受影响，
     但该情景结论**不得**用作论文售电收入；prob02–prob04 若引入售电，须先收紧 `s_t` 的界。
  6. **结构族不可行点**：`buy_cap=3000 kW` 下 accepted 计划不可行（accepted 解购电峰值 8,458.83 kW），
     说明 AS15「无购电上限」是强简化；已按预注册记为情景发现而非模型脆弱。
  7. **结转警告**：文献池 25 条未逐篇读正文、AS06「5000 kW 作用侧」无文献支撑、C1/E1·C2/E2·C3/E3 登记欠账、
     表 2 相位说明、LP 最优面非唯一、A2/A6/A7/A8/A9 未裁定，均沿用 L1–L4 的 warnings。
- **路由**：`failure_type=null`、`return_to_stage=null`、`blocking=[]`；`recommended_next_stage=ablation`。
- **机器摘要**：`machine_sanity_level6.json`；证据目录 `runtime/actions/act-4694208eb3ce490d/evidence/`
  （`verify_level6.py` / `verify_level6_out.json` / `verify_level6_stdout.txt` / `key_assumptions_L6_out.json` /
  `auto_scope/machine_sanity.json`）。
