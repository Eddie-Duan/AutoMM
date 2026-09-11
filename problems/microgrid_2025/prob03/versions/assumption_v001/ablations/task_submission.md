# prob03 ablation 任务登记（提交动作 `act-21277b914c24422a`）

- 阶段：`ablation`（`config/workflow.yaml: mandatory_stages`，**不得 skipped**）
- 预注册方案：`plan.md`（模型集 `M1`–`M8` + `M8b`、判据 `C1`–`C10` + 补充检查 `C3L`、公平性纪律、
  输出隔离、失败处理在**跑数前冻结**）
- 实验代码：`code/ablation_prob03.py`（+ `code/task_config.yaml`、`code/task_spec.yaml`）
- 输出目录：`ablations/results/prob03_v001_ablation_run001/`（**提交前不存在、未被占用**）
- 依据：`agents/ablation-analyst.md`、`skills/ablation-study/SKILL.md`、`config/workflow.yaml`、
  `config/gates.yaml`、`config/compute.yaml`；prob03 团队裁定 `B0`–`B7` / `T1`–`T9` 与团队勘误 `R9`–`R19`（`E1`–`E9`）

## 1. 执行内容（团队 B2 强制的模型族对照，不缩减）

| case | 定义 | 与 `M1` 的差异（只改一项，`M5`/`M8` 按 B2/T7-5 豁免） |
|---|---|---|
| `M1` | 三层顺序向前递推 + 闭式结算（T1 主口径） | 基准（`C1` 基线闸门 / `C8` 交付一致性） |
| `M2a` | 逐日解耦 + 状态递推（`E_{d,0}` 由前一日实测末端传入） | 实现组织（T8：`C2` 为回归检查） |
| `M2b` | 日初复位 `E_{d,0} = 6000` | 跨日口径（差额 = **跨日携带价值**，结构性发现，非缺陷） |
| `M3` | 完全信息上界：单一 52,560 时段 LP（`q ≡ b`、`q_em ≡ 0`） | 信息结构（`C4` / `C10` 跨问锚点） |
| `M4` | 仅 0:00 计划、无调整（`q ≡ b` 全 144） | 调整机制（`C4`） |
| `M5a` | 决策加密 `{0 + 每 3 小时}`（同一发布集 D5-A） | 决策时刻集合（`C5`，A9） |
| `M5b` | 决策加密 `{0 + 每 1 小时}`（同一发布集 D5-A） | 决策时刻集合（`C5`，A9） |
| `M6` | 偏差项 MILP 精确化：4 个指定日的日尺度 oracle（紧 Big-M 按 F8 推导） | LP 松弛 → 二元精确（`C6`，D6-A 降级须登记） |
| `M7·D2-B` | 结算读法 B（`Σ[p·min(b,q) + 0.5p(b−q)⁺ + 1.5p(q−b)⁺] + C_em`） | 结算读法（`C7`） |
| `M7·D2-C` | 结算读法 C（`Σ[p·b − 0.5p(b−q)⁺ + 1.5p(q−b)⁺] + C_em`） | 结算读法（`C7`；与 B **代数恒等**，作为发现登记） |
| `M7·D5-B` | 降尺度改分段常数（`Π^const`），其余同 `M1` | 降尺度规则（`C7` + T3 能量偏差统计） |
| `M8` | 独立第二实现：变量/行次序重排 + 消去弃光变量 `s`（**同求解器设置**） | 实现路线（`C3`） |
| `M8b` | `M8` + `highs-ds` + `presolve=False` | 求解器设置（诊断，登记不判失败） |
| `M7·PLAN-EXP` | — | **团队 T6 撤销，不执行**（确定性口径下与 `min Σp·b` 恒等退化；角色由 `M5` 承接） |

## 2. 提交的隔离计算 task（规格，由 compute_dispatcher 确定性创建）

| 项 | 值 |
|---|---|
| command[0] / 脚本 | `.venv/Scripts/python.exe` / `ablations/code/ablation_prob03.py` |
| stage | `ablation` |
| backend / worker | `local` / `supervised`（Runner 原地运行；detached 在本沙箱会被回收） |
| code_path | `problems/microgrid_2025/prob03/versions/assumption_v001/ablations/code` |
| config_path | 同上 `/task_config.yaml` |
| input_path | `data`（附件 1/2/3/5 只读；附件 4 与 2026 年数据不使用） |
| output_directory | `problems/microgrid_2025/prob03/versions/assumption_v001/ablations/results/prob03_v001_ablation_run001` |
| timeout | 7200 s（整批 `--max-wall-seconds 6600`；单层 LP `--time-limit 60`；M3 `max(60,300)`；M6 单层 MILP `--milp-time-limit 60`） |
| device | CPU，**不占 GPU**（`gpu_required=false`；`max_local_concurrent_tasks=1`） |
| seed | 20260910（模型确定性，seed 只用于记录） |

命令（与 `code/task_spec.yaml` 逐字一致）：

```text
.venv/Scripts/python.exe problems/microgrid_2025/prob03/versions/assumption_v001/ablations/code/ablation_prob03.py \
  --data data/附件1.xlsx --data2 data/附件2.xlsx --data3 data/附件3.xlsx \
  --template data/附件5/result3.xlsx \
  --reference problems/microgrid_2025/prob03/versions/assumption_v001/results/prob03_v001_f001_run003 \
  --output problems/microgrid_2025/prob03/versions/assumption_v001/ablations/results/prob03_v001_ablation_run001 \
  --days 365 --seed 20260910 --time-limit 60 --max-wall-seconds 6600 --milp-time-limit 60
```

**提交回执（动作 `act-b8c0af3431284bf1`，2026-09-11T11:13:22Z，经 `scripts/compute_dispatcher.py submit`）**：

| 项 | 值 |
|---|---|
| task_id / attempt | `ca4f2a45aa49a45236e3` / 1 |
| status / worker | `queued` / `supervised`（`worker_mode` 为 `submit_task` 无条件写入值；启动方式权威来源仍是 `config/compute.yaml: worker_launch_mode`） |
| pid / consumed / group_id | `null` / `false` / `null` |
| code_hash | `33353b13255d25507d881ff034a5d2aa0478ed6aba803dc7ffc8183fa8977629` |
| config_hash / source_config_hash | `4c210b0dbc43cfdb737bf8e20869209690bce1c16502da8e7bad344cff73e729` / `0d2a455c22215df6596f2553dd2d9649527633714e6471e57ca07706b7220433` |
| input_hash | `4343d799b5830093d7a61d566219e1d2592f5bc39c8b7a9297286fa9e02d9434`（与 `run003` 同值 ⇒ `data/` 未被改动） |
| timeout_seconds / seed | 7200 / 20260910 |
| 证据 | `runtime/actions/act-b8c0af3431284bf1/evidence/{precheck_submit.json,submit_receipt_raw.txt,post_submit_snapshot.json,static_checks.txt}` |

提交回执逐项核对（`evidence/post_submit_snapshot.json`，verdict=`POST_SUBMIT_OK`）：提交命令与 `code/task_spec.yaml`
**逐字一致**（含 `data/附件1.xlsx` 等中文路径与 `--output` 一致性）、`task.json ≡ attempt-001-task.json`、
`status.json ≡ attempt-001-status.json`（中文路径未损坏）；提交后 `output_directory` **仍不存在**、
`worker_started.json` **不存在**；`task_id` 由 `make_task_spec` 干跑复算一致（干跑指纹与上一动作
`act-21277b914c24422a` 记录逐位相同）。本动作**未**调用 `start`/`start_queued`、未启动 worker、未写 `results/`、
未跑 365 天计算、未占用 GPU、未使用 `--force`、未执行 `compute_dispatcher reconcile`（避免在途 supervised 任务被误标）。

## 3. 提交前静态检查与小探针（本动作证据）

- `compileall`：**exit 0**；项目 venv 的 `ruff check ablations/code`：**All checks passed**。
  注：`make_task_spec` 的 PATH 预检记 `preflight.ruff=unavailable`，故 task spec 的 `preflight` 只覆盖
  `compileall`，两者不矛盾。
- **`make_task_spec` 干跑**（`evidence/dryrun_task_spec.py`，**未提交、未创建 task**）：
  `DRY_RUN_OK`；`output_directory` 提交前不存在；`preflight.compileall=passed`。
  干跑指纹（提交时会随最终代码重算）：
  `task_id=ca4f2a45aa49a45236e3`、`code_hash=33353b13255d25507d881ff034a5d2aa0478ed6aba803dc7ffc8183fa8977629`、
  `config_hash=4c210b0dbc43cfdb737bf8e20869209690bce1c16502da8e7bad344cff73e729`、
  `source_config_hash=0d2a455c22215df6596f2553dd2d9649527633714e6471e57ca07706b7220433`、
  `input_hash=4343d799b5830093d7a61d566219e1d2592f5bc39c8b7a9297286fa9e02d9434`（与 `run003` 同值）。
- **通用链等价性探针**（`evidence/probe_chain_equivalence.py 40`）：通用链（`decision_hours=(0,6,12,18)`）
  与 accepted `prob03_model.run_m1` 在 40 天 / 160 层上 **11 个字段逐位相同（max|Δ| = 0.0）**，
  `M2a` 亦逐位相同 ⇒ `C1` 基线闸门与 `C2` 有实现级支撑。
- **`M8` 独立层探针**（`evidence/probe_m8_layers.py`、`probe_m8_matrix.py`）：独立层的
  `a_eq x = b_eq` 残差 ≤ 1.8e-12、transition ≤ 7.4e-13；`plan/adjustment` 目标与 accepted 层**同值**；
  期间定位并修复了 1 处求解器写成错误（消去 `s` 时列索引写为 `0*tau`）与 1 处 MILP RHS 错误
  （`z⁺ + z⁻ ≤ 1` 的 RHS 误写为 0）——两处均在**探针阶段**发现，未进入正式计算。
- **`M6` oracle 探针**（`evidence/probe_m6_oracle.py`）：4 个指定日 × 3 个调整层，MILP 与同层 LP 目标
  相对差 ≤ 3.9e-12、`mip_gap = 0.0`、1 节点、Big-M 紧性残差 0、互补性残差 0 ⇒ `C6` 有实现级支撑。
- **整批小探针**：`evidence/probe_smoke5`（5 天，全 12 case `ok`）、`evidence/probe_run40`（40 天，
  整批 74 s，含交付期切片）、`evidence/probe_run100`（100 天，含 `C3L` 逐层等价 4/4、5 张图）。
  **探针数值不得作为论文或 sanity 的交付数值**；正式数值一律以本 task 的隔离产物为准。
- **纪律**：以上探针在隔离 task 之外运行，只用于代码与闸门自检；未创建 task、未写 `results/`、
  未修改 accepted 代码/数据/formulation/假设与 prob01/prob02/prob03 既有产物。

## 4. 与 `robustness` 的边界（团队 B6）

- 参数扰动、输入噪声、求解器压力、结构约束压力属 `robustness`，本阶段**不重复**；
  `robustness/results/prob03_v001_robust_run001` 的数值只作**带出处引用**，不与本阶段数值混写。
- 购电上限阈值：引述 `robustness` 的**决策层夹逼 (4375, 5000] kW**（E9/R19），本阶段不重跑 b 上限扫描，
  且不得与 prob02 的 `β ∈ (4218.75, 4375.00] kW` 混用。

## 5. 预注册的判据冲突（须团队在 `cross_question_review` 确认）

- `C3`（团队 B4）链级要求 `|ΔC(M8, M1)|/C(M1) ≤ 1e-8`；但团队自己的 **T7-3** 审计
  （`run003/t7_tiebreak.json`）证明 **1024/1460 层**在主目标最优面上**仍有吞吐量多重最优**
  （`throughput_unique = False`），即字典序规则**不能唯一确定提交点**；`M1` 为跨日向前递推（F1），
  故任何落在不同最优面点的独立实现都会经状态传播改变链级总费用（量级与 `T7-6` 的 `2.2566e-04` 同阶）。
- 本阶段**不修改 `C3` 阈值**：如实报告链级判定；并新增**补充检查 `C3L`**（非团队 `C1`–`C10` 之一，
  明确标注）——把 `M1` 的提交输入喂入独立实现，**逐层**比较主目标最优值（`≤1e-9`）与残差，
  以隔离「实现/公式正确性」与「最优面选择非唯一」。探针实测 `C3L` 逐层相对差 **0.0**。

## 6. 下一次唤醒（ablation 阶段复审）要做的事

1. 读取 `ablations/results/prob03_v001_ablation_run001/`：`baseline_check.json`、
   `delivery_consistency.json`、`anchor_check.json`、`milp_oracle.json`、`reading_deltas.json`、
   `d5b_energy_stats.json`、`explainability.json`、`layer_equivalence.json`、`comparison.json`、
   `identities.json`、`criteria.json`、`solver_status.json`、`raw_cases.jsonl`、`summary.json`、
   `run_manifest.json`、`M*/case.json`、`figures/`。
2. 撰写 `ablations/report.md`：模型 × 指标对比表、`C1`–`C10` + `C3L` 判定与结论（三问：①核心结论是否
   依赖模型族；②被消融项的经济贡献；③论文主表推荐模型）、与 `robustness` 的冲突登记、技术债与强制披露项。
3. `record_optional_stage(stage="ablation", decision="completed", reason=…)` + `append_ledger` 收尾；
   若 `question_manifest.conclusion` 仍为空，须在 `locally_completed` 前补齐（`C8` 门禁要求）。
4. 若 task 以 `timed_out`/`interrupted`/非零退出结束：按 `agents/resource-manager.md` 用**新 attempt +
   新 `output_directory`**（如 `..._ablation_run002`）重跑，**不得**覆盖 `..._ablation_run001`，
   并把失败指纹记入本节。`M6` 的 MILP 失败/超时只使 `C6` 降级（D6-A 已允许），不使整批失败。

## 7. 执行回执（由汇总动作 `act-7173c11061af4805` 填写）

| 项 | 值 |
|---|---|
| task_id / attempt | `ca4f2a45aa49a45236e3` / 1（2026-09-11T11:13:22Z 提交） |
| status / rc | **`succeeded` / `0`**（`supervised`、CPU HiGHS、`rc=0`、`failure_type=null`；2026-09-11T11:15:00Z 起、11:24:48Z 止） |
| wall_clock_seconds | **584.94 s**（`solver_status.wall_seconds`；`summary.wall_seconds`=586.34 s 为含收尾写盘口径；整批预算 6600 s） |
| cases | 12/12 `ok`，`cases_failed=[]`（`M1`/`M2a`/`M2b`/`M3`/`M4`/`M5a`/`M5b`/`M7_D2B`/`M7_D2C`/`M7_D5B`/`M8`/`M8b`）；`M7·PLAN-EXP` 按 T6 撤销未执行 |
| baseline_passed / C1 | **true**（89 项全通过、`label_check=true`；`M1` 与 `run003` 9 项总量 + 表 1 24 格 + 表 2 逐项相对差 0.0） |
| criteria_failed | **`['C3']`**（`M8` 链级 2.1672146e-05、`M8b` 1.6756115e-05，阈值 1e-8 未改；归因 T7-3 最优面多重最优 + 跨日状态传播） |
| C3L | **PASS**（16/16 层主目标最优值相对差 0.0，阈值 1e-9） |
| 结论报告 | `report.md`（已落盘；含模型×指标总表、C1–C10+C3L 判定、A9 结论、与 robustness 的边界、冲突与披露项） |
| 阶段收尾 | `record_optional_stage(stage="ablation", decision="completed")` + `question_manifest.conclusion` 三字段补齐（本动作） |
| 独立复核 | `runtime/actions/act-7173c11061af4805/evidence/probe_verify_ablation.py` 54 项只读断言 **全通过** |
| 新增技术债 | ① `M5a`/`M5b` 的 `fallback_committed_layers=1/6` 未落盘逐层 provenance（T9-② 说明义务未闭合）；② `figures/ablation_identities.png` 字段口径错误（`identities` vs `residuals`）⇒ 已另出修正版 `ablations/figures/ablation_identities_fixed.png`；③ `M3` 的 `t7.all_layers_invariance_passed=false` 属空集语义 |
