# prob01 robustness 任务登记（提交动作 `act-edd4595657bb4bea`）

- 阶段：`robustness`（`config/workflow.yaml: mandatory_stages`，不得 skipped）
- 预注册方案：`plan.md`（核心结论 K1–K3、稳定性判据 S1–S6、扰动矩阵与样本量在跑数前冻结）
- 实验代码：`code/robustness_prob01.py`（+ `code/task_config.yaml`、`code/task_spec.yaml`）
- 输出目录：`results/prob01_v003_robust_run001/`

## 提交的隔离计算 task

| 项 | 值 |
|---|---|
| task_id | `238db2418a6b1aed432b` |
| attempt | 1 |
| stage | `robustness` |
| backend / worker | `local` / `supervised`（Runner 原地运行；detached 在本沙箱会被回收） |
| code_hash | `d52ac271a403a28c1d4c5d7d4846e63ff94aa78a0994a324996e976f68adbd56` |
| config_hash | `af930f08800c5a95e570623be4067492c1ed79b416cb9c50713caeb1e765869a` |
| input_hash | `4343d799b5830093d7a61d566219e1d2592f5bc39c8b7a9297286fa9e02d9434`（`data/` 全目录） |
| seed | `20260910` |
| timeout | 900 s（CPU HiGHS，~900 个 LP，单次 <1 s） |
| device | CPU，**不占 GPU**（`gpu_required=false`） |
| status | `queued`（等待下一次外部唤醒由 Runner 以 supervised 启动） |

命令（与 `code/task_spec.yaml` 一致）：

```text
.venv/Scripts/python.exe problems/microgrid_2025/prob01/versions/assumption_v003/robustness/code/robustness_prob01.py \
  --input data/附件1.xlsx \
  --output problems/microgrid_2025/prob01/versions/assumption_v003/robustness/results/prob01_v003_robust_run001 \
  --seed 20260910 --samples 100 --families all
```

## 提交前静态检查与小探针（本动作证据）

- `compileall`：通过；`ruff check`（项目 venv 显式调用）：**All checks passed**。
  注：`make_task_spec` 的 PATH 预检记 `ruff=unavailable`，故 task spec 的 `preflight` 只覆盖 `compileall`，两者不矛盾。
- 小探针（**不是** robustness 结果，仅验证基线闸门与代码正确性，8 次 LP 求解）：
  `runtime/actions/act-edd4595657bb4bea/evidence/probe_robustness/`。
  - `baseline` 与 accepted `run002` **逐位一致**：`C*=35126.948589`、`Σb=59482.698998`、
    `Σc=20740.666132`、`Σq=16799.939567`、`Σs=0`、`max_side_power=5000`，相对差均为 `0.0`。
  - D10 对照与 `assumptions.md §0.1` 一致：甲 `35126.948589`、乙 `35101.567554`、丙 `35126.948589`。
  - 求解器 `highs / highs-ds / highs-ipm / highs(nopresolve)` 目标值完全一致（相对差 `0.0`）。

## 下一次唤醒（robustness 阶段复审）要做的事

1. 读取 `results/prob01_v003_robust_run001/`：`baseline_check.json`（闸门）、`raw_samples.jsonl`（原始样本）、
   `summary.json`（S1–S6 与 `structural_findings`）、`sensitivity.json`、`figures/`、`run_manifest.json`。
2. 撰写 `robustness/report.md`：稳定性分级、置信区间、情景发现、局限与适用范围。
3. `record_optional_stage(stage="robustness", decision="completed", reason=...)` 收尾，交 sanity Level 6。
4. 若 task 以 `interrupted` / 非零退出结束：按 `agents/resource-manager.md` 用**新 attempt + 新 output_directory**
   重跑（不得覆盖 `..._robust_run001`），并把新 task_id 记入本节。

## 未越界的上游事项

- 上游登记欠账 C1/E1、C2/E2、C3/E3 仍未回写 `global_symbols.yaml` 与 `assumption_v003/version.yaml`，
  本动作按团队勘误 E1–E3 的下游执行口径处理，不改写上游文件。
- A2（结果日期与跨日衔接）、A6（附件 3 降尺度/年末边界）、A7、A8、A9 属 prob02–prob04，本动作不裁定。
- AS06「5000 kW 作用侧」为 `team_decision`（D10），文献池无一条涉及，本实验不把口径选择包装为文献支持。

---

## 任务完成回执（动作 `act-60783d13f784427a`，robustness 阶段复审）

- **恢复关系**：本动作是被中断动作 `act-edd4595657bb4bea` 的续作。后者响应 JSON 因**字符串内未转义
  的双引号**（char 5404）解析失败，记为 `failure_class=agent_transport`；其已落盘的 `plan.md`、
  本文档、`code/`、task 与探针证据**全部复用**，本动作未重复提交 task、未覆盖任何结果目录。
- **task 终态**：`238db2418a6b1aed432b` / attempt 1 / `succeeded`（returncode 0，15.326 s，supervised，CPU）。
  无需新 attempt、无需新 output_directory。
- **产物**：`results/prob01_v003_robust_run001/`（948 样本、5 图、6 个汇总文件）+
  `robustness/report.md`（稳定性分级、S1–S6 判定、结构情景发现、偏差登记、局限）。
- **结果**：`stability_grade = 稳定`，`criteria_failed = []`；K1/K2/K3 均未被推翻；
  947/948 可行（唯一不可行为结构族 `buycap_3000`）。
- **收尾命令**：`record_optional_stage(stage="robustness", decision="completed")` +
  `append_ledger` + `transition(target_stage="sanity_check")`（Level 6，`trigger: after_robustness`）。
- **遗留**：`question_manifest.yaml` 的 `conclusion` 三字段仍为空，须在 `locally_completed` 前补齐
  （否则本地完成门禁会失败）；robustness 图件不登记为交付图表。
