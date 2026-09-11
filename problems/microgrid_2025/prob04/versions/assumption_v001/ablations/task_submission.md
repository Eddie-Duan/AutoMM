# prob04 `ablation` 隔离计算 task 提交与失败处置记录

- 归属：`microgrid_2025` / `prob04` · 阶段 `ablation`（`config/workflow.yaml: mandatory_stages`）
- 负责人：`ablation-analyst`
- 依据：`ablations/plan_v001.md`（预注册，判据 `C1`–`C9`）、`ablations/plan_v002.md`（编码事故修订）、
  `ablations/plan_v003.md`（run003 实现纠错修订，判据不变）
- 纪律：`plan_v001` §3.8（同数据/同参数/同预算/同口径）、§6（失败处理：新 attempt + 新 `output_directory`、
  不覆盖旧结果、不静默替换）；`config/compute.yaml` 的 `worker_launch_mode=supervised`
- **本文件覆盖 run001 → run003 三个批次**；§1 表中 run002 两行的 `status` 是**提交时**的状态，
  其**终态**见 §5（run002 4-2 succeeded / 4-3 failed），run003 见 §6。

---

## 1. 批次总览

| 批次 | 链 | task_id | attempt | attempt 目录 | output_directory | status | 结果 |
|---|---|---|---|---|---|---|---|
| run001 | `4-2` | `639de3861bced76d1b96` | 1 | `runtime/tasks/639de3861bced76d1b96/` | `..._ablation_4-2_run001` | `succeeded`（rc=0） | 12 个对俱全，墙钟 154.90 s |
| run001 | `4-3` | `5304b4d42b3953fedf9a` | 1 | `runtime/tasks/5304b4d42b3953fedf9a/` | `..._ablation_4-3_run001` | **`failed`（rc=1）** | 仅 `BASE-43/` 落盘 |
| run002 | `4-2` | `6ef360822fc3520116a0` | 1 | `runtime/tasks/6ef360822fc3520116a0/` | `..._ablation_4-2_run002` | `queued` | 待 Runner 以 supervised 执行 |
| run002 | `4-3` | `4e3e59706fa0888083ec` | 1 | `runtime/tasks/4e3e59706fa0888083ec/` | `..._ablation_4-3_run002` | `queued` | 同上 |

- 两条链的 `code_hash`（run002）= `d0e8c771f0a298ae1b33346766ba98386f0fb108eb61b49ad2c8c7df9647c691`
  （run001 = `d33ee2ef409f6755402343b44f059ea359830ccca01b566ffd36be5b28e963b1`）。
- 两链 `input_hash` 相同 = `4343d799b5830093d7a61d566219e1d2592f5bc39c8b7a9297286fa9e02d9434`（同数据）。
- `config_hash` 两链不同（`chain_scope: 4-2` / `4-3`，避免 `compute_task_id` 撞号）。
- `preflight`：两 task 均 `compileall: passed`；`ruff: unavailable`（PATH 无 ruff），
  本动作改用项目 venv 的 ruff 显式检查 `ablations/code/ablation_prob04.py` → `All checks passed!`
  （与既有登记一致：PATH 缺 ruff 不等于代码未检查）。

---

## 2. run001 的 `4-3` 失败：指纹、根因、处置

### 2.1 失败指纹

```
File ".../ablations/code/ablation_prob04.py", line 2071, in <module>   raise SystemExit(main())
File ".../ablations/code/ablation_prob04.py", line 1674, in main       one_day = read_attachment1_price(_resolve(args.data1))
File ".../ablations/code/ablation_prob04.py", line 345,  in read_attachment1_price
prob04_io.InputValidationError: 附件 1 第 2 列表头不是「电价」: '电价'
```

- `status.json`：`status=failed`、`returncode=1`、`failure_class=code_runtime`、`failure_type=process_exit`、
  `attempt=1`、`feasible_incumbent=false`、`worker_mode=supervised`。
- 失败发生在 `C-ANCHOR-P03`（强制闸门 `C1`）的第一步，**早于任何对照求解**；
  `BASE-43` 已完成，其 `D_full=17,181,202.515506398`、`D_req=15,289,050.714737598`
  与 accepted `run002` 逐位一致（`baseline_check.BASE.pass=true`，相对差 ≤2.6e-14）⇒ 主口径链路正常。

### 2.2 根因（编码事故，非模型/数值问题）

- `ablation_prob04.py` 的源文件经历了一次 **「UTF-8 文本被按 GB18030 解码后重存」** 的转码事故：
  脚本自身的中文串全部变成乱码（`"电价"` → `"鐢典环"`；全文 129 个私用区码位），
  故 `if header[1] != "鐢典环":` 对真实表头 `"电价"` 恒为真。
- 同一事故还**吞掉了若干换行**（某个 3 字节汉字的后 1 字节 + 紧随的 `\n` 被解码器替换为 `?`），
  造成两处次生缺陷：
  1. **数值相关**：4-3 `S-VAR` 不等式块中 `ub_rows, ub_cols, ub_vals, ub_rhs = [], [], [], []`
     被并进上一行的 `#` 注释而**失效**，两个建块循环叠加、`coo_matrix` 对同 `(row,col)` 求和，
     `a_ub` 偏离 formulation §3.6 的分段线性化。
  2. **潜在故障**：两处诊断 `print` 的 f-string 字段名被污染成未定义标识符（`{exc}` / `{failed_checks}`），
     运行到即 `NameError`（run001 未触发）。
- **该事故不影响 run001 的 `BASE`/`S-RH` 数值**（`BASE-42` 与 accepted `D_req = 13,006,411.0411` 元逐位一致），
  但使 run001 的 JSON 产物同样含乱码，且 `S-VAR` 分支口径不可信。

### 2.3 处置（按 `plan_v001` §6）

1. 修复编码（逐行逆向映射 + 112 行人工补丁表）；**结构等价校验**：
   修复前后 `ast.dump`（字符串常量归一化）逐节点 diff，差异**只有 3 项**：
   (i) 重新激活上述列表重置；(ii) /(iii) 两个 f-string 字段名恢复。`ruff` + `compileall` 通过。
2. `code_hash` 变化 ⇒ 新 task_id ⇒ **必须使用新 `output_directory`**（`_run002`），
   `run001` 的目录与产物**原样保留、不覆盖、不删除**。
3. **两条链同时重跑**（不只重跑 4-3）：`plan_v001` §3.8 要求同代码修订、同参数、同预算可比；
   run001 的 4-2 JSON 亦含乱码。
4. `C-ANCHOR-P03` 构造补全（见 `plan_v002.md` §3）：锚点运行期间把「无前一日」的中性回退项
   替换为锚点自身的单日曲线（只补数据、不改模型方程），`finally` 恢复。
   未补时 `D_full` 的 `C_adj` 残差 `+1,777.290337` 元、`ΔC_price(D_full) = −30,558.377455` 元，
   六项中两项超 `1e-9`；补全后六项 ≤`4.9e-13`、`C1 pass=true`、脚本 exit 0。
   **判据阈值与六项清单未改。**

---

## 3. 本动作的只读探针证据（**非交付结果**）

> 以下均在**隔离 task 之外**运行，只用于定位与修复验证；按既有纪律，
> 其数值**不得**作为论文、`sanity` 或 `ablations/report.md` 的交付/对照数值，
> 正式数值一律以 run002 两个 isolation task 的产物为准。

| 探针目录 | 内容 | 结论 |
|---|---|---|
| `results/_probe_fix42_v2/` | 4-2 `--cases BASE`，365 天 | `D_req=13,006,411.0411` 元，与 accepted 逐位一致 ⇒ 修复未改变主口径链路 |
| `results/_probe_fix42_v3_svar/` | 4-2 `--cases SVAR`，365 天 | 期望费用 `394,769.6783257871` 元、`Δ=−3.2859882594369387%`，与 run001 **逐位相同** ⇒ 列表重置对 4-2 的 S-VAR **数值中性** |
| `results/_probe_fix43_anchor/` | 4-3 `--anchors-only`，补全前 | `C1 pass=false`：`D_full_C_total` 1.0985e-4、`D_full_C_adj` 3.1563e-3，其余四项 ≤1e-13 |
| `results/_probe_anchor_seed/` | 4-3 `--anchors-only`，外部 monkeypatch 验证假设 | 六项 ≤`4.9e-13` ⇒ 残差**唯一来源**即 `d=0` 的中性回退 |
| `results/_probe_final43_anchor/` | 4-3 `--anchors-only`，**补全后的正式代码** | `C1 pass=true`、`C2 pass=true`、exit 0；`C-ANCHOR-P03 D_req=14,540,616.3357` 元 |

- 修复前代码备份：`.tmp/ablation_prob04.before_repair.py`（sha256 `7e16a90c…`）。
- 修复后（已安装）代码：`ablations/code/ablation_prob04.py`（sha256 见 run002 `task.json` 的 `code_hash`）。
- 探针目录均以 `_` 前缀落在 `ablations/results/` 下，**不属于** `plan_v001` §5 的交付布局；
  保留目的仅为审计留痕。

---

## 4. 下一步（本动作不代做）

1. 由 Runner 以 `worker_launch_mode=supervised` 原地执行 `6ef360822fc3520116a0` 与 `4e3e59706fa0888083ec`
   （单卡/单 worker 串行；`max_local_concurrent_tasks=1`）。
2. 两 task 达到终态后，由 `ablation-analyst` 在后续唤醒中：
   读取产物 → 汇总 `comparison.json` / `criteria.json` → 出 2–4 张图（`plan_v001` §4）→
   写 `ablations/report.md`（回答 `plan_v001` §7 的三问）→
   `record_optional_stage(stage="ablation", decision="completed")`。
3. 若 run002 任一 task 以 `interrupted`/`timeout`/非零退出结束：**不得复用同一 `output_directory`**，
   按 §6 以新 attempt + 新 `output_directory`（`_run003`）重跑，并把新指纹记入本文件。
4. `E-F6` 纪律：本地 task 处于 `running` 期间禁止 `RESUME` / `reconcile_tasks()`。

---

## 5. run002 终态与失败指纹（2026-09-12 更新，生效于 §1 表中 run002 两行）

| 链 | task | status | rc | 起止（UTC） | 墙钟 | 已落盘对照 |
|---|---|---|---|---|---|---|
| `4-2` | `6ef360822fc3520116a0` | `succeeded` | 0 | 16:53:08 → 16:55:44 | 156.0 s | 14 个对照（`case_counts` 见 §6 注） |
| `4-3` | `4e3e59706fa0888083ec` | **`failed`** | 1 | 16:51:49 → 16:53:04 | 75.0 s | 仅 `BASE-43/`、`C-ANCHOR-P03/` |

- `4-3` traceback：`ablation_prob04.py:1771 main → :725 run_rh → :659 window_plan`
  → `prob04_model.LayerFailure: S-RH 窗口 LP 未达最优（day=0, t0=36, H=1, status=2）`；
  `status=2` = HiGHS infeasible。失败**早于** S-VAR/结构消融，故 `4-3` 的 `run002` 只完成了
  `BASE`（`C2` pass）与 `C-ANCHOR-P03`（`C1` pass）两个强制闸门。
- `4-2` run002 报 `criteria_failed = ["C3"]`（`checks_failed = []`、`exit 0`）：经复核是**闸门实现缺陷**
  （`state_gap` 误取 `H = 14` 的结果），不是模型缺陷，见 `plan_v003.md` §2 `D-3`/`D-4`。

## 6. run003 提交（实现纠错版，判据不变）

| 链 | task_id | output_directory | `--cases` | timeout | wall | code_hash |
|---|---|---|---|---|---|---|
| `4-2` | `e54f83cea3e31a1c0879` | `..._ablation_4-2_run003` | `all`（14 对照） | 5400 s | 3000 s | `84142798754a3d5c…` |
| `4-3` | `20906d684ca14f498047` | `..._ablation_4-3_run003` | `all`（9 对照） | 12600 s | 10800 s | `84142798754a3d5c…` |

- 两链 **同一 `code_hash`**（`84142798754a3d5c…`）、**同一 `input_hash`**
  （`4343d799b5830093…`，即同附件 2/3/4）、`config_hash` 因 `chain_scope` 不同而不同（避免 task_id 撞号）。
- 提交前状态：`runtime/tasks/` 下**无 running/queued** 任务（`E-F6`：本地任务运行期间禁止 RESUME/reconcile）。
- 本轮修的是 `plan_v003.md` §2 登记的 8 项**实现缺陷**（`S-RH` 窗口 `t0`/`include_q_em`、`plan_*` 全量落盘、
  `C3` 比对对象、`C4` 方向、`S-VAR(4-3)` 不等式方向与逐场景行偏移、`C8` 残差证据与 `case_counts`）；
  **判据 `C1`–`C9`、阈值、对照集合、公平性纪律一字未改**。
- `case_counts` 口径修正后：`4-2` = 14、`4-3` = 9（与 `plan_v001` §3 的对照矩阵一致；
  旧版把无 `D_full`/`D_req` 的 `S-VAR`/`S-VAR-RH` 漏计）。
- `run001`/`run002` 的目录与产物**原样保留**，仅作审计对照，**不作交付值或对照值**。
- 提交前的修复验证探针：`results/_probe_run003_fix42/`、`results/_probe_run003_fix43b/`
  （60 天小窗口，`C3` pass、`C4` expectation 成立、S-VAR 残差 ≤ 1e-12、`exit 0`）；
  探针数值**不得**作为论文/报告/交付证据，详见 `plan_v003.md` §3。

## 7. run003 之后的下一步（本动作不代做）

1. 由 Runner 以 `worker_launch_mode=supervised` 原地串行执行两个 queued task。
2. 终态后由 `ablation-analyst` 读取 `results/prob04_v001_ablation_4-{2,3}_run003/`：
   汇总 `comparison.json` / `criteria.json` → 出 2–4 张图（`plan_v001` §4）→
   写 `ablations/report.md`（回答 `plan_v001` §7 的三问）→
   `record_optional_stage(stage="ablation", decision="completed")`。
3. 若 run003 任一 task 以非零/超时结束：仍按 §6 以**新 attempt + 新 `output_directory`**（`_run004`）重跑，
   不覆盖 `_run003`，并把新指纹记入本文件。
