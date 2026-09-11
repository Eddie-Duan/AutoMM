# prob02 robustness 任务登记（提交动作 `act-4bfd13cab5c9404f`）

- 阶段：`robustness`（`config/workflow.yaml: mandatory_stages`，不得 skipped）
- 预注册方案：`plan.md`（核心结论 K1–K6、稳定性判据 S1–S6、扰动矩阵、样本量、种子与失败处理
  在实验批运行前冻结，事后不得修改）
- 实验代码：`code/robustness_prob02.py`（+ `code/task_config.yaml`、`code/task_spec.yaml`）
- 输出目录：`results/prob02_v001_robust_run001/`
- 依据：`agents/robustness-analyst.md`、`skills/robustness-study/SKILL.md`、
  `knowledge/robustness-ablation.md`、prob02 团队裁定 B5/D8-A 与勘误 R2/R5

## 提交的隔离计算 task

| 项 | 值 |
|---|---|
| task_id | `f7a4e670b91ad469d771` |
| attempt | 1 |
| stage | `robustness` |
| backend / worker | `local` / `supervised`（Runner 原地运行；detached 在本沙箱会被回收） |
| code_hash | `1e98c31054dcbbcd6a2398269fdfa9203a984424db5817af7e627ff23e0ef51e` |
| source_config_hash | `25dd65854200a9322482d7a446799b27f202f89150425a2147facb7209c05355` |
| input_hash | `4343d799b5830093d7a61d566219e1d2592f5bc39c8b7a9297286fa9e02d9434`（`data/` 全目录，与 run002 相同） |
| assumption / formulation | `assumption_v001` / `formulation_v001` |
| seed | `20260910` |
| timeout | 5400 s（149 次全年 LP；小探针实测单次 5.1–7.9 s，预计 25–45 min） |
| device | CPU，**不占 GPU**（`gpu_required=false`；本机可用内存偏低，单 worker 串行） |
| status | `queued`（等待下一次外部唤醒由 Runner 以 supervised 启动） |

> **提交前撤销与重提（同一动作内，未产生任何结果）**：首次提交 `7fef7c0ee67aafc2f850`
> （`code_hash=61927ad2…`，status=queued）后，小探针发现噪声生成器在「按日持续 + 电价因子」分支
> 对 144 点电价与「天×144」因子做广播（`shapes (144,) (4608,)`），会在正式批的第 4 个噪声族中断。
> 已在本动作内修复为「先按天展开电价、再叠加因子」，用 `compute_dispatcher cancel-queued` 撤销该
> queued task（其 `output_directory` 未被创建、未被运行、无任何产物），并以修复后代码重新提交为本表
> 的 `f7a4e670b91ad469d771`。撤销记录：`runtime/tasks/7fef7c0ee67aafc2f850/status.json`
> 的 `status=cancelled`。


命令（与 `code/task_spec.yaml` 一致）：

```text
.venv/Scripts/python.exe problems/microgrid_2025/prob02/versions/assumption_v001/robustness/code/robustness_prob02.py \
  --data data/附件1.xlsx --data2 data/附件2.xlsx \
  --reference problems/microgrid_2025/prob02/versions/assumption_v001/results/prob02_v001_f001_run002 \
  --output problems/microgrid_2025/prob02/versions/assumption_v001/robustness/results/prob02_v001_robust_run001 \
  --seed 20260910 --samples 25 --time-limit 120 --families all
```

## 实验规模（预注册，见 `plan.md` §3）

- 矩阵情景 **49** 个：`baseline` 1 + 参数 OAT 25（`eta` 6、`eta_asym` 4、`init` 6、`alpha` 6、`pmax` 6、
  `ewin` 3，含基线网格点）+ `solver` 3 + `s_bound` 1 + `s_sell` 2 + `alpha_lt1` 1 + `b_cap` 10。
- 噪声样本 **100** 个：4 族 × 25（逐时段白噪声 σ=5%/10%、按日持续 σ=5%、按日持续含电价 σ=5%）。
- 合计 **149** 次全年 LP（52,560 时段 / 315,360 变量 / 105,120 等式）。

## 提交前静态检查与小探针（本动作证据）

- `compileall`：通过；`ruff check`（项目 venv 显式调用）：**All checks passed**。
  注：`make_task_spec` 的 PATH 预检记 `ruff=unavailable`，故 task spec 的 `preflight` 只覆盖 `compileall`，两者不矛盾。
- 3 天接口自检：`runtime/actions/act-4bfd13cab5c9404f/evidence/probe_robust_smoke3/`（17 情景、`exit 0`），
  覆盖参数族、`b_cap` 全档、`s_bound`、`s_sell`、`alpha_lt1` 的代码路径与产物结构。
- 32 天端到端与出图自检（修复后代码）：`runtime/actions/act-4bfd13cab5c9404f/evidence/probe_robust_fig32/`
  （51 情景，含 `noise_white_5` 与 `noise_joint_day_5` 两族各 3 样本；`criteria_failed=[]`、`exit 0`；
  6 张 PNG 全部落盘）。该探针同时暴露并关闭了噪声生成器的广播缺陷（见上）。
- 全年基线闸门自检（修复后代码，与提交的重提 task 同一 `code_hash`）：
  `runtime/actions/act-4bfd13cab5c9404f/evidence/probe_robust_baseline365_final/`
  - `C = 13,758,182.573724 元`、交付期 `12,233,050.830708 元`、`Σb = 22,657,938.157435 kWh`、
    `Σq_em = 0`、`Σs = 990,168.090312 kWh`、`E_T = 1200.00`、`max 两侧功率 = 5000 kW`，与 run002
    **8 项总量相对差均为 0.0**；
  - 4 个指定日期的全天购电量/购电费相对差 ≤ 2e-11；表 1 六时段最大绝对差 3.33e-7 kWh
    （来自参考 `tables.json` 的 6 位小数舍入）；
  - `baseline_check.passed = true`，单次求解 **5.07 s**，`exit 0`（首次计时探针 7.89 s，机器负载差异）。
- 纪律：以上探针在隔离 task 之外运行，**只用于代码与闸门自检**，其数值不得作为论文或 sanity 的交付数值；
  正式数值一律以本 task 的隔离产物为准。

## 与 ablation 的边界（团队裁定 B5 / D8-A）

- M4（逐日独立）与 M5（终端 = 6000）**本阶段不重跑**，报告只引用：M4 交付期 −17,803.27 元、
  M5 交付期 +2,217.08 元（+0.018%），并注明「数值以 ablation 为准」。
- `b_cap` 网格（R2 原网格 + M6′）在 robustness 与 ablation 各独立计算一次，数值不得互相替代；
  若 `β` 夹逼或 `Σq_em` 量级不一致，须在两份报告中显式登记冲突点。

## 下一次唤醒（robustness 阶段复审）要做的事

1. 读取 `results/prob02_v001_robust_run001/`：`baseline_check.json`、`solver_status.json`、
   `raw_samples.jsonl`、`trajectories/`、`summary.json`、`sensitivity.json`、`figures/`、`run_manifest.json`。
2. 撰写 `robustness/report.md`：稳定性分级、置信区间、参数/噪声响应、`b_cap` 阈值与结构情景发现、
   局限与适用范围（含期末放空与价格套利的区分、LP 最优面非唯一的验收口径）。
3. `record_optional_stage(stage="robustness", decision="completed", reason=...)` + `append_ledger` 收尾，
   `transition(target_stage="sanity_check")` 触发 Level 6。
4. 若 task 以 `timed_out` / 非零退出结束：按 `agents/resource-manager.md` 用**新 attempt + 新 output_directory**
   重跑（不得覆盖 `..._robust_run001`），并把新 task_id 记入本节。

## 未越界的上游事项

- `question_manifest.yaml` 的 `conclusion` 三字段仍为空，须在 `locally_completed` 前由相应阶段补齐（A-DR8/U7 结转）。
- `prob01/assumption_v003/version.yaml` 中 AS08「必然被激活」措辞、C1/E1、C2/E2 回写欠账与 A6–A9（prob03/04）
  仍待 `cross_question_review` 或后续小问处理；本动作不改写上游文件。
- robustness 图件不登记为交付图表（不调用 `record_figure_review`）。

---

## 执行回执（动作 `act-8cc1221dc1d54633`，2026-09-11）

| 项 | 值 |
|---|---|
| task_id / attempt | `f7a4e670b91ad469d771` / 1 |
| status / rc | `succeeded` / 0（`supervised`、CPU、`seed=20260910`、`probe_mode=false`） |
| 起止 | `2026-09-11T03:03:05Z` → `2026-09-11T03:18:13Z` |
| `wall_clock_seconds` | 907.269（149 次全年 LP；预估 25–45 min，落在预算内） |
| 产物 | `results/prob02_v001_robust_run001/` 五件套 + `trajectories/` 52 件 + `figures/` 6 张 |
| 基线闸门 | `baseline_check.passed = true`（8 项总量相对差 0.0；4 个指定日期 ≤2e-11；表 1 六时段 ≤3.33e-7 kWh） |
| 预注册判据 | `criteria_failed = ["S1", "S5"]`；`stability_grade = 脆弱（需缩小适用范围）` |
| 结论报告 | `robustness/report.md`（本动作产出） |
| 阶段决定 | `record_optional_stage(robustness, completed)` + `transition(target_stage=sanity_check)` |

- **S1 FAIL（仅 `solver_highs-ipm`）**：该样本目标值与基线**逐位相同**、等式残差 2e-12、界越界 0.0，仅
  `complementarity_sum = 4.41358e8`（1136 个同充放时段）失败；AS07 不禁止同时充放电、引理 L1 只保证
  「存在互补最优解」，故属**返回解选择**问题，非模型不可行（报告 §5.1、§9 D-R3）。
- **S5 FAIL（`eta_both_0.99@2025-06-21`）**：全天购电量 **−19.10%**、购电费 **−19.62%**（有利方向；
  实现用绝对相对偏差触发）；反向的 η=0.81 在部分日期购电费 **+13.0%**。年度/交付期总量仍稳健（报告 §5.2、§9 D-R1）。
- 本动作另登记 D-R1–D-R10 技术债（tornado `e_max` 匹配错误、`monotone_q_em_non_increasing` 方向反、
  `threshold_bracket` 字段命名误导、结构族解析界前提失效、task 未置 `consumed` 等），**判据未事后修改**。
- 本 task 已 `succeeded` 但 `consumed=false`（robustness 的 `run_agent` 动作不带 `task_id`，Runner 只在
  computation 阶段消费终态 task）；与 prob01 robustness/ablation 的同类欠账一并留待
  `cross_question_review` 或归档时闭合。
