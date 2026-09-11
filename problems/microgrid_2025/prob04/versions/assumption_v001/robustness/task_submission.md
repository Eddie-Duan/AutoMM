# prob04 robustness 任务登记（提交动作 `act-6d9ecf00777a4b96`）

- 阶段：`robustness`（`config/workflow.yaml: mandatory_stages`，**不得 skipped**）
- 预注册方案：`plan.md`（**适用性决定**、核心结论 `K1–K8`、稳定性判据 `S1–S7`、扰动矩阵、样本量、种子、失败处理、
  与 `ablation` 的边界、口径差异 `CF-1`–`CF-10` 在实验批开始运行前冻结，事后不得修改）
- 实验代码：`code/robustness_prob04.py`（+ `code/task_config.yaml`、`code/task_config_4-3.yaml`、`code/task_spec.yaml`、`code/task_spec_4-3.yaml`）
- 对象：accepted 主口径 `4-2`（逐日向前递推计划层 + 闭式结算层）与 `4-3`（0:00 计划 + 6:00/12:00/18:00 调整 + `0.5×`/`1.5×` 双向偏差结算）
- 交付口径锚点（只读）：`results/prob04_v001_f001_4-2_run002`（task `892351beefa2bc5f7804`）与
  `results/prob04_v001_f001_4-3_run002`（task `eca261e1d516ab2867d9`）
- 依据：`agents/robustness-analyst.md`、`skills/robustness-study/SKILL.md`、`knowledge/robustness-ablation.md`、`AGENTS.md`、
  `config/workflow.yaml`、`config/compute.yaml`、本版本 `assumptions.md`（文末「团队裁定」`R-1`/`R-2` 与勘误 `E-F2`–`E-F5`、决策点 `D1`–`D12`）、
  `formulations/formulation_v001/formulation.md`（§6.2 / §8.7 黑名单 / §8.8）、`implementation.md`（§8 第 11 条、`C7`/`C8`/`C11`/`C12`）、
  `sanity_report.md`（`N1`–`N5`）、`figures/visual_review.md`（`V1`–`V6`）

## 提交的隔离计算 task（**两链分别提交、分别传参、独立 output_directory**）

| 项 | 链 `4-2` | 链 `4-3` |
|---|---|---|
| task_id | `953eeb1e0b004171cad9` | `5713b0a24eedeac9f000` |
| attempt | 1 | 1 |
| stage | `robustness` | `robustness` |
| backend / worker | `local` / `supervised` | `local` / `supervised` |
| code_hash | `1b2e3e26c606969ff39128fa68cf2193e60c1eb335605dc64121cdcd2f357569` | 同左（同一份代码） |
| config_hash | `ed45a161f7cd25e74a951bad56d2e531518b769afbd9afc61c2b980ef8539879` | `48c69830470f837839e446bcd98d0fd65a667ed9ce387bace77f05021b2ec44a` |
| source_config_hash | `a6ab5c145dd96dd207f89bef09452a37aee6fd90b65806fa9d810892a7f6f23e` | `bbf8231f3a01e947f3003c9794046c85a6426398c3c82b4505daccd705b5fe1a` |
| input_hash | `4343d799b5830093d7a61d566219e1d2592f5bc39c8b7a9297286fa9e02d9434`（`data/` 整目录，与 `run002` 相同） | 同左 |
| assumption / formulation | `assumption_v001` / `formulation_v001` | 同左 |
| config_path | `code/task_config.yaml` | `code/task_config_4-3.yaml` |
| seed | `20260911` | `20260911` |
| timeout | 5,400 s（整批 `--max-wall-seconds 3000`） | 12,600 s（整批 `--max-wall-seconds 10800`） |
| device | CPU HiGHS，**不占 GPU 串行额度**（`gpu_required=false`） | 同左；与 `4-2` 由 `max_local_concurrent_tasks=1` 强制串行 |
| status | `queued`（等待下一次外部唤醒由 Runner 以 supervised 启动） | `queued` |

> **`chain_scope` 的必要性**：`automm.tasks.compute_task_id` 的身份**不含** `output_directory`/`command`，
> 两链共用同一份 `code` + 同一份 `config` 会算出**同一** `task_id`（`implementation.md` 的 `C11` 框架级发现）。
> 本批用两份**链专用** config（`chain_scope: "4-2"` / `"4-3"`）使 `config_hash`/`task_id` 不同 —— 实测
> `ed45a161…` vs `48c69830…`、`953eeb1e…` vs `5713b0a2…`，**未发生撞号**。

命令（与 `code/task_spec.yaml` / `code/task_spec_4-3.yaml` 逐项一致）：

```text
# 链 4-2
.venv/Scripts/python.exe problems/microgrid_2025/prob04/versions/assumption_v001/robustness/code/robustness_prob04.py \
  --chain 4-2 --data2 data/附件2.xlsx --data3 data/附件3.xlsx --data4 data/附件4.xlsx \
  --reference problems/microgrid_2025/prob04/versions/assumption_v001/results/prob04_v001_f001_4-2_run002 \
  --output problems/microgrid_2025/prob04/versions/assumption_v001/robustness/results/prob04_v001_robust_4-2_run001 \
  --seed 20260911 --samples 25 --time-limit 60 --days 365 --mode compact --families all --max-wall-seconds 3000

# 链 4-3
.venv/Scripts/python.exe problems/microgrid_2025/prob04/versions/assumption_v001/robustness/code/robustness_prob04.py \
  --chain 4-3 --data2 data/附件2.xlsx --data3 data/附件3.xlsx --data4 data/附件4.xlsx \
  --reference problems/microgrid_2025/prob04/versions/assumption_v001/results/prob04_v001_f001_4-3_run002 \
  --output problems/microgrid_2025/prob04/versions/assumption_v001/robustness/results/prob04_v001_robust_4-3_run001 \
  --seed 20260911 --samples 25 --time-limit 60 --days 365 --mode compact --families all --max-wall-seconds 10800
```

## 首次提交的取消记录（审计轨迹，不得静默）

首次提交的两个 task（`4-2 = e47fb8e85a4dac704970`、`4-3 = 5feb24bf28c15ae3facd`，`code_hash = c2858e01…`）
在本动作内被 **`compute_dispatcher.py cancel-queued` 取消**，原因是：**在批次开始运行前**，依 34 天先导探针的
证据对 `S2`（`4-3`）与 `S4` 的阈值作了 `CF-10` 改写（详见 `plan.md` §3/§7 与 `evidence/recheck_criteria_cf10_out.json`），
脚本 `sha256` 随之变化；若不取消，磁盘代码将与 task 记录的 `code_hash` 不一致（可复现性受损）。
取消时两个 `output_directory` 均**不存在**（未产生任何产物），故**无覆盖风险**；重新提交用**新 attempt + 新 task_id**。

## 实验规模（预注册，见 `plan.md` §4）

| 链 | 情景总数 | 构成 | 单情景实测（365 天 compact） |
|---|---|---|---|
| `4-2` | **162** | 2 基线 + 34 参数 OAT + 2 预测机制 + 8 输入扰动 + 3 求解器 + 13 结构约束 + 4 族 × 25 = 100 噪声 | `baseline` 6.26 s；`baseline_full`（四段式）13.05 s |
| `4-3` | **198** | 2 基线 + 40 参数 OAT + 3 预测机制 + 12 输入扰动 + 3 求解器 + 13 结构约束 + 5 族 × 25 = 125 噪声 | `baseline` 22.11 s；`baseline_full`（四段式）39.44 s |

- `4-3` 专属族：`β_def/β_over`（4）、`κ_m` 截断界放宽/收紧（2）、`κ_m ≡ 1`（1）、附件 3 预报偏差（2）、附件 3 预报噪声（2）、`noise_pvfc_5`（25）。
- 每情景为一次全年 LP（52,560 时段）：`4-2` 每日 1 层、`4-3` 每日 4 层；`compact` 每层 2 次 LP、`full` 每层 4 次。
- 整批预计：`4-2` ≈ 1,100–1,300 s、`4-3` ≈ 4,400–5,000 s，**串行合计 ≈ 90–105 min**。

## 提交前静态检查与小探针（本动作证据，全部只读输入、只写 `runtime/actions/act-6d9ecf00777a4b96/evidence/`）

1. `compileall`：通过；项目 venv `ruff check`：**All checks passed**（脚本含文件级 `# ruff: noqa: E501`，理由：判据原文为长中文字符串，
   折行会损害「与 `plan.md` 逐字一致」的可审计性；其余规则全部启用）。
   注：`make_task_spec` 的 PATH 预检记 `ruff=unavailable`（其内部只做 `compileall`），两者不矛盾。
2. **3 天 smoke 探针**：`evidence/probe_smoke3_42/`（11 情景）、`evidence/probe_smoke3_43/`（12 情景）。
   覆盖参数族、预测机制族、输入族、求解器族、结构族（含 `buy_cap` 不可行与 `terminal_e_6000`）、噪声族全部代码路径；
   `4-3` 的 `buy_cap_4000kW` 如实记录为**决策层不可行**（`LayerFailure` 被就地捕获成失败样本，未中断整批）。
   `exit 4` 为**预期**（3 天窗口对 365 天基线闸门必然超差）；compact 与 full 基线在 3 天窗口逐位同值。
3. **34 天全矩阵探针（4-2）**：`evidence/probe_all34_42/`（70 情景、`exit 4` 同为预期）。
   `S1` 可行率 = 47/47、层残差与恒等式全部通过；`S3` OAT 方向**全部成立**、无反转；`S5` 求解器最大相对差 0.10%；`S6` 12 档 `buy_cap` 全域可行、`terminal_e_6000` 末端储电量恰为 6000 kWh。
4. **34 天全矩阵探针（4-3）**：`evidence/probe_all34_43/`（83 情景、80 成功、3 个 `buy_cap` 决策层不可行、`exit 4` 预期）。
   `S3` 全部成立；`S6` 给出 **4-3 专属**分界：`4500 kW` 及以下不可行、`5000 kW` 及以上可行 ⇒ 分界落在 `(4500, 5000] kW`，
   与 `4-2` 在同一窗口的「全域可行（≥3500 kW）」**不同** ⇒ 直接支撑 `D10`/`E9` 的「**分链重新扫描、禁止跨链互写**」纪律
   （**登记的 prob02 `β ∈ (4218.75, 4375.00] kW` 与 prob03 `[4375.0, 5000.0] kW` 均未被引用**）。
5. **365 天 compact 基线闸门探针（权威版本）**：`evidence/probe_baseline365_42/`、`evidence/probe_baseline365_43/`（各 2 情景，**`exit 0`**）。
   - **19 项总量相对差全部为 0.0**：`D_full` 9 项取 accepted `solution.json`（`4-2` 全期 `C_total = 14,755,884.322036` 元；
     `4-3` 全期 `17,181,202.515506` 元 = `C_plan 14,854,264.372169 + C_adj 587,335.465660 + C_em 1,739,602.677677`）；
     `D_req` 10 项取 accepted `run_manifest.json`（`4-2` 交付期 `13,006,411.041148` 元；`4-3` 交付期 `15,289,050.714738` 元；
     `4-3` 交付期 `Σq_em = 394,026.040750 kWh`）。
   - 表 1 四日期 × 六时段 = **24/24 行最大绝对差 0.0 kWh**（由 `baseline_full` 的未修改四段式与 `run002/tables.json` 对账）。
   - T7 审计 7 键与 `run002/tiebreak_audit.json` 的 `summary` **逐项一致**（`t7_mismatch_keys = []`）。
   - ⇒ **compact 与四段式的提交解逐位同解**：`4-3` 的 `throughput_primary_only_kwh = 37,143,089.109777`、
     `throughput_tiebreak_kwh = 35,313,228.984743`、`max_degeneracy_degree = 263` 与 `run002` 完全相同；
     `4-2` 同结论。`baseline_check.passed = true`（两链）。
6. **CF-10 判据改写的复核**：`evidence/recheck_criteria_cf10.py` / `evidence/criteria_cf10_recheck_out.json`
   在**已落盘的 34 天样本**上重算判据（不重跑任何 LP）：改写后 `4-3` 的 `S2` 由 FAIL 变为 **PASS**
   （宽带 `[0.25×, 4×]` 内越界 0 个；窄带 `[0.5×, 2×]` 的 2 个越界样本逐条披露为 `noise_white_10_001/002`），
   两链 `S4` 仍 FAIL 且失败项**全部来自探针窗口本身**（`n<25`、3 天交付窗导致的 `std/CI > 5%`、
   `noise_white_10` 均值相对基线 +12.2%）。⇒ 判据在 365 天窗口的可用性由正式批次给出，**阈值不得再改**。
7. 纪律：以上探针在隔离 task 之外运行，**只用于代码与闸门自检**，其数值**不得**作为论文或 sanity 的交付数值；
   正式数值一律以两个隔离 task 的产物（`results/prob04_v001_robust_4-2_run001/`、`..._4-3_run001/`）为准。
8. 脚本内置**输出路径自证断言**：正式模式只允许写 `robustness/results` 之下；任何模式都禁止写 `data/`、
   accepted `code/` 与 `results/prob04_v001_f001_*`（`_assert_output_scope`）。故本动作**未写**任何交付值、
   未写 `data/附件5/`、未改 accepted 代码与 `runtime/workflow_state.json`。

## 与 ablation 的边界（团队裁定 `R-1`/`R-2`、`AS12`、`D10`、`E-F4`）

- `S-VAR`（24 场景两阶段随机）、`S-RH`（前瞻深度 `H ∈ {1,3,7,14}`）、`S-VAR-RH`、`C-ANCHOR-P03`（附件 1 价格退化锚点）、
  `A2-PRE`、`P2`/`BRIDGE` 退化同构、`M7·D2-B`/`M7·D2-C` 结算读法、`PF-AR` **本阶段一律不跑**，报告中只引用并注明出处与口径。
- `D2-B` 的「滚动多日窗（MPC）」与团队 `R-2` 的 `S-RH` 指派冲突 ⇒ 本阶段**不跑**跨日 MPC，登记为 `CF-1` 并指向 `ablation`。
- `D6-C`（`κ_m ≡ 1`）由 `AS11` 的验证方式明文授权 `robustness`/`ablation` 两侧 ⇒ 本阶段**跑**（`CF-2`）。
- `AS23` 的静置损耗属「可加（非必做）」且需改写状态转移 ⇒ 本阶段**不增设**，在 `report.md` 的技术债中登记并指向 `formulation` 下一版（`CF-3`）。
- `PF-AR` 的 `D_req` MAE 低于主口径（0.080664 < 0.084326）⇒ 按 `AS08`/`E-F5` **只进 `ablation`**，本阶段不跑、也不据单一指标宣称任一预测器「更优」。

## 下一次唤醒（robustness 阶段复审）要做的事

1. 读取两个产物目录：`baseline_check.json`、`solver_status.json`、`raw_samples.jsonl`、`trajectories/`、
   `summary.json`、`sensitivity.json`、`figures/`、`run_manifest.json`、`forecast_backtest.json`。
2. 撰写 `robustness/report.md`：**分链**给出 `S1–S7` 判定与 `stability_grade`；参数 OAT 龙卷排名与方向；
   四/五族噪声的 95% 置信区间；求解器压力量级（与 `T7-6` 的 `1e-4` 对照）；**分链**购电上限可行/不可行分界；
   `terminal_e_6000` 差额；预测机制（`PF-DUAL`/`PF-HIST`/`κ_m ≡ 1`）与输入扰动族的 `ΔC_total` 与 `ΔC_price`；
   `K7`（价格预报误差是第一不确定性源）与 `K8`（两链同号、`4-3` 敏感度不低于 `4-2`）的判定；
   适用边界、技术债与披露项（含 `CF-1`–`CF-10` 与 `N1`–`N5`/`V1`–`V10` 的承接）。
3. `record_optional_stage(stage="robustness", decision="completed", reason=...)` + `append_ledger` 收尾，
   `transition(target_stage="sanity_check")` 触发 Level 6。
4. 若任一 task 以 `timed_out` / 非零退出（`4`/`5`/`1`）结束：按 `agents/resource-manager.md` 用**新 attempt +
   新 output_directory**（`..._run002`）重跑（**不得**覆盖 `..._run001`），并把新 `task_id` 记入本节；
   **不得**通过删减冻结的扰动矩阵来「凑完成」。

## 未越界的上游事项（继续结转，不在本动作处理）

- `question_manifest.yaml` 的 `conclusion.conclusion_id/version/content_hash` 仍为空，须在 `locally_completed` 前由相应阶段补齐。
- `shared/problem_understanding.md` §7/§10 仍把 `A8` 记为「待裁定」（`C4-1`）；`prob01/assumption_v003/version.yaml` 的
  `AS08`「必然被激活」措辞（`C4-7`/`E3`）；`D10`「5000 kW 作用侧」文献缺口（`C4-6`）；`N1`/`N2`/`N5` 对上一版登记数值的更正
  （**下游引用一律以 `sanity_report.md` 为准**）；`V1`–`V10` 的图件口径登记。以上继续结转至 `cross_question_review` 或论文。
- prob04 池 24 条文献**均未逐篇阅读正文**，本阶段不引用任何公式级/定量级文献主张。
- robustness 图件**不登记**为交付图表（不调用 `record_figure_review`）。
