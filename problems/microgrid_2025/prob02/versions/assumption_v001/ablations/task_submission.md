# prob02 ablation 任务登记（提交动作 `act-d2b711aa1991482f`）

- 阶段：`ablation`（`config/workflow.yaml: mandatory_stages`，不得 skipped）
- 预注册方案：`plan.md`（模型集合 M1–M7 + M6′、判据 C1–C7、公平性纪律、输出隔离、失败处理在跑数前冻结）
- 实验代码：`code/ablation_prob02.py`（+ `code/task_config.yaml`、`code/task_spec.yaml`）
- 输出目录：`ablations/results/prob02_v001_ablation_run001/`
- 依据：`agents/ablation-analyst.md`、`skills/ablation-study/SKILL.md`、
  prob02 团队裁定 B0–B5 / D1–D8 与勘误 R1–R5

## 提交的隔离计算 task

| 项 | 值 |
|---|---|
| task_id | `5b87ce0a8d9e4706c82c` |
| attempt | 1 |
| stage | `ablation` |
| backend / worker | `local` / `supervised`（Runner 原地运行；detached 在本沙箱会被回收） |
| code_hash | `0d5ef6c6fe8704b39b606792782f455cba17f666b4cae996e2199227d856586f` |
| config_hash | `b601a034cd776dcae2a1bf2e6486879f84b1ecc12d3e0710821b672d68a4d094` |
| source_config_hash | `5b6b797eb8664546afba525466c997e5d6414af984403261b7159c8d0024e8cb` |
| input_hash | `4343d799b5830093d7a61d566219e1d2592f5bc39c8b7a9297286fa9e02d9434`（`data/` 全目录，与 run002 相同） |
| assumption / formulation | `assumption_v001` / `formulation_v001` |
| seed | `20260910` |
| timeout | 7200 s（13 个全年 LP + 3×365 日规模 LP + 全规模 MILP ≤300 s + 4 个日规模 MILP） |
| device | CPU，**不占 GPU**（`gpu_required=false`；本机可用内存偏低，单 worker 串行） |
| status | `succeeded`（attempt 1、supervised、CPU、rc=0、`wall_clock_seconds=401.33643270000175`、17/17 case 可行；见下方执行回执） |

命令（与 `code/task_spec.yaml` 一致）：

```text
.venv/Scripts/python.exe problems/microgrid_2025/prob02/versions/assumption_v001/ablations/code/ablation_prob02.py \
  --data data/附件1.xlsx --data2 data/附件2.xlsx \
  --reference problems/microgrid_2025/prob02/versions/assumption_v001/results/prob02_v001_f001_run002 \
  --output problems/microgrid_2025/prob02/versions/assumption_v001/ablations/results/prob02_v001_ablation_run001 \
  --seed 20260910 --days 365 --milp-time-limit 300
```

## 实验规模（预注册，见 `plan.md` §3）

- **全年 LP（52,560 时段 / 315,360 变量）13 次**：M1、M7（独立实现）、M5（终端=6000）、
  M6 原网格 4 档、M6′ 6 档。
- **逐日 LP 3 × 365 次**（864 变量 / 288 等式/日）：M2a（耦合序列外生固定）、M2b（日终自由递推）、
  M4（`E_{d,0}=E_{d,144}=6000`）。
- **互补 MILP**：全规模 1 次（52,560 个二元，限时 300 s，**独立子进程**以隔离内存，D5 允许降级）+
  4 个指定日期的日规模 MILP（各 144 个二元，共 576 个二元，作独立数值 oracle）。

## 提交前静态检查与小探针（本动作证据）

- `compileall`：通过；项目 venv 的 `ruff check`：**All checks passed**。
  注：`make_task_spec` 的 PATH 预检记 `ruff=unavailable`，故 task spec 的 `preflight` 只覆盖 `compileall`，两者不矛盾。
- **矩阵同一性探针**：`runtime/actions/act-d2b711aa1991482f/evidence/probe_matrix_identity.py`
  —— ablation 的 `build_full_lp` 与 accepted `prob02_model.build_lp` 在 3 天窗上逐项相同
  （objective 全同、`A_eq` 最大差 0.0、`b_eq`/界/nnz 全同，`MATRIX_IDENTICAL`），
  降低 C1 基线复现闸门风险。
- **3 天接口自检**：`evidence/probe_ablation_smoke3/`（17 个 case，`exit 0`）——
  覆盖 M1/M7/M5/M6/M6′/M2a/M2b/M4/M3_full 全部代码路径与 4 张图；M7≡M1、M2a≡M1、M3≡M1（`mip_gap=0`）。
- **80 天端到端自检**：`evidence/probe_ablation_smoke80/`（17 个 case，31.7 s，`exit 0`）——
  覆盖交付期切片（2/1 起）、指定日期 2025-03-20（含日规模 MILP oracle：LP=MILP，相对差 3.98e-16、
  1 节点证最优、`mip_gap=0`）、`β` 夹逼与单调性（80 天窗下夹逼为 (4000, 4218.75]）。
- **纪律**：以上探针在隔离 task 之外运行，**只用于代码与闸门自检**，其数值不得作为论文或 sanity 的交付数值；
  正式数值一律以本 task 的隔离产物为准。

## 与 robustness 的边界（团队裁定 B5 / D8-A）

- M4（逐日独立）与 M5（终端 = 6000）在本阶段出数；robustness 只可带出处引用，不得混写。
- `b` 上限网格（M6 原网格 + M6′）在 robustness 与 ablation **各独立计算一次**，数值不得互相替代；
  若 `β` 夹逼或 `Σq_em` 量级不一致，须在 `ablations/report.md` 与 `robustness/report.md` 显式登记冲突点。

## 下一次唤醒（ablation 阶段复审）要做的事

1. 读取 `ablations/results/prob02_v001_ablation_run001/`：`baseline_check.json`、`solver_status.json`、
   `comparison.json`、`identities.json`、`raw_cases.jsonl`、`summary.json`、`M*/case.json`、`figures/`、`run_manifest.json`。
2. 撰写 `ablations/report.md`：模型 × 指标对比表、4 张图的登记版、C1–C7 判定与 K1–K6 结论、
   结论段三问（①核心结论是否依赖模型族；②被消融项的经济贡献；③论文主表推荐模型）、
   与 robustness 的冲突登记、技术债。
3. `record_optional_stage(stage="ablation", decision="completed", reason=...)` + `append_ledger` 收尾；
   若 `question_manifest.conclusion` 仍为空，须在 `locally_completed` 前补齐。
4. 若 task 以 `timed_out`/非零退出结束：按 `agents/resource-manager.md` 用**新 attempt + 新 output_directory**
   重跑（不得覆盖 `..._ablation_run001`），并把新 task_id 记入本节；全规模 MILP 单独降级不使整批失败（D5）。

## 执行回执（由汇总动作 `act-9caed04b70814fff` 于 2026-09-11 填写）

| 项 | 值 |
|---|---|
| task_id / attempt | `5b87ce0a8d9e4706c82c` / 1 |
| status / rc | `succeeded` / `returncode=0`、`worker_mode=supervised`、`feasible_incumbent=true` |
| wall_clock_seconds | `401.33643270000175`（`run_manifest.json`） |
| model_count | 17（M1、M7、M5、M6×4、M6′×6、M2a、M2b、M4、M3_full） |
| 基线闸门 | **通过**（`baseline_check.json.passed=true`；8 项总量最大相对差 `3.21e-14`；spec 项最大绝对差 `3.79e-07`） |
| 预注册判据 | `criteria_failed=[]`：C1–C7 全通过；C3 技术债为「全规模 MILP 300 s 未证明最优」（`mip_gap=3.1655e-07`），4/4 日规模 oracle 精确同值 |
| 结论报告 | `report.md`（对比表 + C1–C7 + K1–K6 + 结论三问 + robustness 边界 + 技术债 + 追踪链）；图件副本见 `figures/` |
| 结论字段 | `question_manifest.conclusion` 三字段已由本动作 `record_conclusion` 补齐（此前为空，会使 `locally_completed` 门禁报错） |
| 阶段收尾 | `record_optional_stage(stage="ablation", decision="completed")` + `append_ledger` + `transition(locally_completed)` |

## 结果消费登记（`act-9caed04b70814fff`）

1. 已读取 `ablations/results/prob02_v001_ablation_run001/` 全部产物：`baseline_check.json`、`solver_status.json`、
   `comparison.json`、`identities.json`、`raw_cases.jsonl`、`summary.json`、`run_manifest.json`、17 个 `M*/case.json` 与 `figures/`。
2. 独立复核：17/17 case 可行、`checks_failed=[]`；(I1)/(I2) 残差 ≤ `5.59e-09`、平衡残差 ≤ `2.27e-13`、跨日连续性 `0`；
   M1 复现值与 run002 逐位一致；`β ∈ (4218.75, 4375.00] kW` 与 formulation 定理 T2 / 团队独立复跑 / robustness L6 一致。
3. 已撰写 `report.md`、另存 `figures/`（4 张，逐字节副本 + `README.md`），**未调用 `record_figure_review`**（`plan.md` §4 / 团队裁定 B5）。
4. task `5b87ce0a8d9e4706c82c` 与 prob01 的 `c1faaa09dedfb103c598` 同类：`ablation` 阶段的 `run_agent` 动作不带
   `task_id`，Runner 只消费 computation 阶段终态 task，故该 task 仍 `consumed=false`，属登记欠账（A-DR7），
   可在 `cross_question_review` 或归档时统一闭合；不影响本阶段推进。
5. 未发生 `timed_out`/`interrupted`/非零退出，**无需新 attempt 或新 `output_directory`**；`..._ablation_run001` 未被覆盖。

