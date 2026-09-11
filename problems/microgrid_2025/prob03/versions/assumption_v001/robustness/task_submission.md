# prob03 robustness 任务登记（提交动作 `act-7c496fc60d7741c4`）

- 阶段：`robustness`（`config/workflow.yaml: mandatory_stages`，不得 `skipped`）
- 预注册方案：`plan.md`（**适用性决定**、核心结论 K1–K6、稳定性判据 S1–S6、扰动矩阵、样本量、种子、
  失败处理、与 ablation 的边界、口径差异 CF-1–CF-7 在实验批运行前冻结，事后不得修改）
- 实验代码：`code/robustness_prob03.py`（+ `code/task_config.yaml`、`code/task_spec.yaml`）
- 输出目录：`results/prob03_v001_robust_run001/`（提交前不存在）
- 对象：accepted `M1`（`assumption_v001` / `formulation_v001`）；交付口径锚点 `results/prob03_v001_f001_run003`
- 依据：`agents/robustness-analyst.md`、`skills/robustness-study/SKILL.md`、`knowledge/robustness-ablation.md`、
  `AGENTS.md`、本版本 `assumptions.md` 末节（B6 / T7-1/T7-5/T7-6 / T9 / R11–R13 / E6 / E7）、`formulation.md`、
  `implementation.md`、`sanity_report.md`

## 提交的隔离计算 task

| 项 | 值 |
|---|---|
| task_id | `9d890669fb66a1bcc3ae` |
| attempt | 1 |
| stage | `robustness` |
| backend / worker | `local` / `supervised`（Runner 原地运行；detached 在本沙箱会被回收） |
| code_hash | `a0aeee339aadbcee40853be98c773f8c2244c15419234b041e06e6162a0fe5f8` |
| config_hash | `fa34218b766b2b061c7c0a10ae9248a76267a404ff1b5e4087917ba0d3fca3fb` |
| source_config_hash | `8bd56149175972bdbc802ba36dc3769e71eb04e591b061ac4551540b6b6b90d1` |
| input_hash | `4343d799b5830093d7a61d566219e1d2592f5bc39c8b7a9297286fa9e02d9434`（`data/` 全目录，与 `run003` 相同） |
| assumption / formulation | `assumption_v001` / `formulation_v001` |
| seed | `20260911` |
| timeout | 7200 s（整批 `--max-wall-seconds 5400`；预计 45–50 min） |
| device | CPU，**不占 GPU 串行额度**（`gpu_required=false`；本机可用内存 1.19 GB，单 worker 串行） |
| status | `queued`（等待下一次外部唤醒由 Runner 以 supervised 启动） |

命令（与 `code/task_spec.yaml` 逐项一致）：

```text
.venv/Scripts/python.exe problems/microgrid_2025/prob03/versions/assumption_v001/robustness/code/robustness_prob03.py \
  --data data/附件1.xlsx --data2 data/附件2.xlsx --data3 data/附件3.xlsx --template data/附件5/result3.xlsx \
  --reference problems/microgrid_2025/prob03/versions/assumption_v001/results/prob03_v001_f001_run003 \
  --output problems/microgrid_2025/prob03/versions/assumption_v001/robustness/results/prob03_v001_robust_run001 \
  --seed 20260911 --samples 25 --time-limit 30 --days 365 --mode compact --families all --max-wall-seconds 5400
```

## 实验规模（预注册，见 `plan.md` §4）

- 情景总数 **156**：`baseline`（compact）1 + `baseline_full`（未修改四段式）1 + 参数 OAT **39** +
  求解器 **3** + 结构约束 **12** + 输入噪声 **4 族 × 25 = 100**（满足「随机实验 ≥ 100 次」默认）。
- 每个情景为一次全年三层顺序 LP（52,560 时段）；compact 模式每层 2 次 LP、full 模式 4 次。
- 全年实测（本动作证据）：compact **17.5–17.8 s**、full **34.9–35.1 s**；整批预计 **≈ 2,800 s（45–50 min）**。

## 提交前静态检查与小探针（本动作证据，全部只读、只写 `runtime/actions/act-7c496fc60d7741c4/evidence/`）

1. `compileall`：通过；项目 venv `ruff check`：**All checks passed**。
   注：`make_task_spec` 的 PATH 预检记 `ruff=unavailable`（内部只做 `compileall`），两者不矛盾。
2. **3 天接口自检**：`evidence/probe_robust_smoke3/`（9 情景、`exit 4` 为**预期**：34/3 天窗口对 365 天基线闸门必然超差），
   覆盖参数族、求解器、结构族、噪声族的代码路径；compact 与 full 基线在 3 天窗口逐位同值。
3. **34 天全矩阵自检**：`evidence/probe_robust_all34/`（51 情景、`exit 4` 同为预期）。S1 可行率 = 44/44、
   层残差与四条恒等式全部通过；S3 六组 OAT 单调方向**全部成立**（η/α_em/P_max/E_min/E_max/β）；龙卷排名为
   η_both > η_dis > E_max > η_ch > P_max > α_em > β > E_min > E_init。该探针暴露并修复了三处实现问题
   （紧凑 tiebreak 的字段对账、`build_sensitivity` 漏统计失败样本、噪声族分组过滤）。
4. **34 天结构/噪声自检**：`evidence/probe_robust_struct34/`、`evidence/probe_robust_noise34/`。
   - 购电上限扫掠：**4375 kW 及以下决策层不可行（status=2，`LayerFailure`）**，5000–10326 kW 可行 →
     34 天窗口的可行/不可行分界落在 **(4375, 5000] kW**（与 prob02 勘误 R5 的 `q_em` 激活阈值
     `β ∈ (4218.75, 4375.00] kW` 属**不同物理量**，已在 `plan.md` CF-2 显式登记口径差异）。
   - 噪声 34 天相对标准差：白噪声 5% 0.97%、白噪声 10% 2.11%、按日持续 5% 7.06%、按日持续含电价 5% 8.06%——
     该量级被 34 天窗口仅 3 个交付日放大；全年 334 个交付日按 `1/√n` 缩放后预计 0.1%–0.8% 量级，
     故 S4 的 5% 阈值对全年窗口是有意义且可达的（阈值已在 `plan.md` 冻结，不受探针结果影响）。
5. **全年基线闸门自检（权威版本）**：`evidence/probe_robust_baseline365b/`（2 情景，**`exit 0`**）。
   - `baseline`（compact）与 `run003` 的 **9 项总量相对差全部为 0.0**：全期 `C_total = 16,179,176.145228 元`、
     交付期 `= 14,540,616.335652 元`、`C_plan = 13,885,669.475555`、`C_adj = 563,098.132533`、
     `C_em = 1,730,408.537141`、`Σq(交付期) = 20,842,142.600809 kWh`、`Σq_em(交付期) = 391,274.485914 kWh`、
     `Σs'(交付期) = 2,087,727.847547 kWh`、`storage_final = 1200.0 kWh`。
   - `baseline_full`（未修改四段式）表 1 四日期 × 六时段与 `run003/tables.json` **最大绝对差 0.0 kWh**；
     T7 审计与 `run003/t7_tiebreak.json` 一致：`layers=1460`、`lexicographic=1460`、`fallback=0`、
     `degenerate_layers=1460`、`remaining_multiplicity=1024`、`unknown_multiplicity=1`、
     `max_primary_relative_change=5.0000409e-10`。
   - ⇒ **compact 模式与 T7 字典序提交解逐位同解**，且 full 模式复现 `run003` 的 T7 审计；`baseline_check.passed=true`。
   - 说明：`evidence/probe_robust_baseline365/` 为修复 `t7` 字段命名前的同名探针，已被 `..._baseline365b/` 取代，
     保留作审计痕迹（两者 9 项总量一致，仅 `t7` 键名不同）。
6. 纪律：以上探针在隔离 task 之外运行，**只用于代码与闸门自检**，其数值不得作为论文或 sanity 的交付数值；
   正式数值一律以本 task 的隔离产物（`results/prob03_v001_robust_run001/`）为准。

## 与 ablation 的边界（团队裁定 B6 / T2 / T3 / T6 / T8）

- `M4`（仅 0:00 无调整）、`M5`（加密预报时刻族）、`M7·D2-B/D2-C/D5-B`（结算读法与降尺度口径对照）、
  `M2b`（日初复位）、`M3`（完全信息上界）**本阶段不重跑**，报告只引用并注明出处。
- R11 建议的「给定误差分布量化对冲收益」诊断性 sensitivity **属 ablation**（需新增误差分布假设），
  本阶段不做；本阶段只量化输入噪声与参数扰动。

## 下一次唤醒（robustness 阶段复审）要做的事

1. 读取 `results/prob03_v001_robust_run001/`：`baseline_check.json`、`solver_status.json`、`raw_samples.jsonl`、
   `trajectories/`、`summary.json`、`sensitivity.json`、`figures/`、`run_manifest.json`。
2. 撰写 `robustness/report.md`：S1–S6 判定与 `stability_grade`、参数 OAT 弹性与龙卷排名、四族噪声的 95% 置信区间、
   求解器压力量级（与 T7-6 的 `1e-4` 对照）、购电上限可行性分界与终端情景差额、适用边界、技术债与披露项
   （含 CF-1–CF-7）。
3. `record_optional_stage(stage="robustness", decision="completed", reason=...)` + `append_ledger` 收尾，
   `transition(target_stage="sanity_check")` 触发 Level 6。
4. 若 task 以 `timed_out` / 非零退出结束：按 `agents/resource-manager.md` 用**新 attempt + 新 output_directory**
   （`..._robust_run002`）重跑（不得覆盖 `..._robust_run001`），并把新 `task_id` 记入本节。

## 未越界的上游事项（继续结转，不在本动作处理）

- `question_manifest.yaml` 的 `conclusion.conclusion_id/version/content_hash` 仍为空，须在 `locally_completed`
  前由相应阶段补齐。
- `prob01/assumption_v003/version.yaml` 的 AS08「必然被激活」措辞（C3/E3）、D10「5000 kW 作用侧」文献缺口、
  R5/R1 的论文落点、R10 值口径 vs xlsx XML 字面口径、R13 跨问初始状态不可比，继续结转至
  `cross_question_review` 或论文阶段。
- robustness 图件不登记为交付图表（不调用 `record_figure_review`）。
