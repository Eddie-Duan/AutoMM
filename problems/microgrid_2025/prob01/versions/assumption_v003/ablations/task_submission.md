# prob01 ablation 隔离计算 task 提交登记

- 归属：`microgrid_2025` / `prob01`；阶段：`ablation`（`config/workflow.yaml` 的 `mandatory_stages`，不得 skipped）
- 提交动作：`act-8fc1f3e5e410428c`（ablation-analyst）
- 预注册：`ablations/plan.md`（**先于任何实验运行写定**，判据 C1–C7 与对照集合 A–F 事后不得修改）
- 依据：`assumptions.md` 末尾「团队裁定（ablation 多模型对比设计与预注册判据）」A0–A5、
  `agents/ablation-analyst.md`、`config/gates.yaml`、`skills/compute-manager/SKILL.md`

## 1. task 标识与追踪

| 项 | 值 |
|---|---|
| task_id | `c1faaa09dedfb103c598` |
| attempt | 1（status=queued） |
| stage / backend | `ablation` / `local` |
| worker_launch_mode | `supervised`（继承 `config/compute.yaml`；detached 在本环境会被沙箱回收） |
| 设备 | CPU（`gpu_required=false`，不占单卡 GPU 串行额度） |
| timeout | 900 s（单次 LP 上限 60 s，与 A3 同预算一致） |
| seed | 20260910（本实验确定性，无随机采样） |
| code_hash | `d59664d05c434ca580340d3a77dc209655fd5f2fb209377880917410c863637d` |
| config_hash | `78947a5ff271ebd267f013cd1cb15dbb67b1745204d43cc0ca1ed8aca8bd6ff9` |
| input_hash | `4343d799b5830093d7a61d566219e1d2592f5bc39c8b7a9297286fa9e02d9434`（`input_path=data`） |
| output_directory | `problems/microgrid_2025/prob01/versions/assumption_v003/ablations/results/prob01_v003_ablation_run001` |
| task 目录 | `runtime/tasks/c1faaa09dedfb103c598/`（task.json / attempt-001-task.json / status.json） |

命令（`task_spec.yaml` 同）：

```
.venv/Scripts/python.exe \
  problems/microgrid_2025/prob01/versions/assumption_v003/ablations/code/ablation_prob01.py \
  --input data/附件1.xlsx \
  --output problems/microgrid_2025/prob01/versions/assumption_v003/ablations/results/prob01_v003_ablation_run001 \
  --seed 20260910 --time-limit 60 --dp-steps 400,200,100,50
```

提交后 `status=queued`。按 `config/orchestrator.yaml` 的 `run_mode=one_shot`，
由下一次外部唤醒的 Runner 以 supervised worker 原地执行；本 Agent 不自行代跑、不调用 `start_queued`。

## 2. 对照集合（A1，全部实跑）

| 编号 | 子目录 | 说明 |
|---|---|---|
| A | `A_baseline_LP/` | accepted 完整 LP（C1 复现闸门 + 独立实现交叉检查） |
| B | `B_milp/` | 互补二元变量 MILP（`c_t ≤ C_CAP·u_t`、`q_t ≤ Q_CAP·(1−u_t)`） |
| C | `C_dp_h400/ … C_dp_h050/` | SOC 离散化 DP，状态步长 400/200/100/50 kWh |
| D | `D_no_periodic/` | 去掉日周期约束 `E_0=E_144` |
| E | `E_no_spill/` | 删除 `s_t`，R1 改不等式 `b+q−c ≥ 净负荷` |
| F | `F_place_*/` | 效率作用位置（两侧/仅充电侧/仅放电侧/往返整体） |

## 3. 预期产物

`baseline_check.json`、`solver_status.json`、`comparison.json`、`dp_granularity.json`、
`raw_cases.jsonl`、`summary.json`、`run_manifest.json`、各对照子目录 `case.json`、
`figures/`（4 张：费用对比、DP 粒度-偏差、消融瀑布、复杂度-费用）。

## 4. 失败与重试

- exit 4 = C1 基线复现失败 → **整批作废**，按 `needs_revision` 路由，不引用任何对照数值；
- exit 3 = 输入结构或 DP 粒度参数非法 → 修代码；
- exit 1 = 未捕获异常 → `code_runtime`，修复后**新 attempt + 新 output_directory**，不覆盖既有结果；
- MILP 未证明最优（`mip_gap > 1e-6`）：按 `gates.yaml` 的 `allow_pass_with_warning` 登记 incumbent 与 gap。

## 5. 提交前探针（非交付数值）

`runtime/actions/act-8fc1f3e5e410428c/evidence/probe_ablation/` 下的 12 个 case 为**代码正确性探针**
（在隔离 task 之外运行），仅用于验证：C1 基线闸门 6 项相对差 0.0、`prob01_model.py` 独立实现交叉检查 0.0、
MILP 与 LP 同值、DP 四档粒度可行、D/E/F 方向。**正式数值只允许引用 task `c1faaa09dedfb103c598`
在 `ablations/results/prob01_v003_ablation_run001/` 下的产物。**

## 6. 后续

结果就绪后的下一个动作：只读复核 → 撰写 `ablations/report.md`（对比表、5 维度、结论三问、技术债与冲突）→
按 A4.2 登记图表 → `record_optional_stage(stage=ablation, decision=completed)`。
`question_manifest.yaml` 的 conclusion 三字段与 E1–E3 的权威回写仍待后续处理。

## 7. 结果消费与汇总（act-b0cec516722840f3）

| 项 | 值 |
|---|---|
| task 终态 | `succeeded`；attempt 1；`supervised`；CPU；exit 0；started 14:07:22.6 → finished 14:07:25.9（≈3.3 s）；`feasible_incumbent=true` |
| 消费动作 | `act-b0cec516722840f3`（ablation-analyst，`run_agent`） |
| 判据 | C1–C7 全通过，`criteria_failed=[]`；`cases_total=12`、`cases_infeasible=0` |
| 独立复核 | `runtime/actions/act-b0cec516722840f3/evidence/verify_ablation_independent.py`：**56/56 断言通过**；独立重解 12 case 目标值与产物一致到 ≤1e-9；追踪链（输入 md5、run002 sha256、ablation/accepted 代码 sha256、harness code_hash、run002 未被覆盖）全部一致 |
| A5 上限纪律探针 | `evidence/a5_cap_discipline_probe.py`：F 族固定上限 vs 按情景重算上限在本数据下目标值逐位一致（放电峰值 715.653033 kWh 未触及差异区间），与 robustness `eta_placement` 无冲突 |
| 报告 | `ablations/report.md`（对比表、5 维度、结论三问、§5 边界与冲突、§6 技术债） |
| 图件登记 | `ablations/figures/plot_ablation_figures.py` 重绘 4 张（同数据、统一风格），`inspect_png` 4/4 passed，登记 `figures.yaml` 并 `record_figure_review` passed；task 原始图保留不改动 |
| 未改动 | `results/prob01_v003_f001_run002/`、accepted `code/`、`formulation_v001/`、`assumptions.md` 均未写 |
