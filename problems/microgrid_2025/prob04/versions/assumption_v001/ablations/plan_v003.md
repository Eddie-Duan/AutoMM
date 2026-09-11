# prob04 消融与模型族对照实验方案 · `plan_v003`（跑数前修订，判据不变）

- 归属：`microgrid_2025` / `prob04` · 阶段 `ablation` · 版本目录
  `problems/microgrid_2025/prob04/versions/assumption_v001/ablations/`
- **与 `plan_v001` / `plan_v002` 的关系**：两份原文**保留、一字不改**。
  本文件是**跑 run003 正式对照数值之前**、由 `ablation-analyst` 在其同步动作
  `act-3ec496044d994127`（2026-09-12）中新增的修订案。
- **判据与口径状态**：`plan_v001` §2 的 `C1`–`C9`、§3 的对照矩阵与两条链覆盖、§3.8 的公平性纪律、
  §5 的输出布局、§6 的失败处置**全部不变**，**阈值一个都没有放宽**，§2「事后不得修改判据」的纪律
  **未被触碰**。本文件只做两件事：**(a) 登记 run002 的终态与失败指纹；(b) 登记 run003 的代码缺陷修复
  （实现纠错，不是判据变更）**。
- 触发依据：`AGENTS.md`（「不静默沿用旧登记、冲突时显式记录」）、`agents/ablation-analyst.md` 步骤 0、
  `plan_v001` 文首「事后若发现范围有误，必须新建 `plan_v00x` 并保留旧文件与已跑结果」。

---

## 1. run002 的终态与失败指纹（先登记，再谈修订）

| 链 | task | status | rc | 起止（UTC） | 墙钟 | 已落盘对照 |
|---|---|---|---|---|---|---|
| `4-2` | `6ef360822fc3520116a0` | `succeeded` | 0 | 16:53:08 → 16:55:44 | 156.0 s | **全部 14 个对照**（含 `S-VAR`/`S-VAR-RH`） |
| `4-3` | `4e3e59706fa0888083ec` | **`failed`** | 1 | 16:51:49 → 16:53:04 | 75.0 s | 仅 `BASE-43/` 与 `C-ANCHOR-P03/` |

- `4-3` 的 traceback（`runtime/tasks/4e3e59706fa0888083ec/attempt-001-stderr.log`）：
  `ablation_prob04.py:1771 main → :725 run_rh → :659 window_plan`
  → `prob04_model.LayerFailure: S-RH 窗口 LP 未达最优（day=0, t0=36, H=1, status=2）`。
  `status = 2` 即 HiGHS 判定 **infeasible**，发生在 4-3 的 S-RH 第一个窗口、早于任何 S-VAR/结构消融。
- `4-3` 已落盘的两个对照均通过强制闸门：`BASE-43`（`C2` pass）、`C-ANCHOR-P03`（`C1` pass）
  ⇒ 主口径链路与锚点实现本身正常，失败**局限在 `S-RH`（以及其后的、尚未被执行的 `S-VAR` 分支）**。
- `4-2` run002 的 `criteria.json` 记 `criteria_failed = ["C3"]`，但 `checks_failed = []`、`exit 0`；
  C3 的失败经本轮复核是**闸门实现的缺陷**（见 §2 `D-3`），不是模型缺陷。

---

## 2. 代码缺陷登记与修复（run002 → run003）

**性质声明**：以下 8 项**全部是实现纠错**（`ablations/code/ablation_prob04.py` 与提交脚本），
**不改**任何预注册判据、阈值、比较口径、对照集合、公平性纪律、失败处置，也**不改**
accepted `code/`、`formulations/formulation_v001/`、`assumptions.md`、`results/prob04_v001_f001_*`。
每项给出位置 / 现象 / 根因 / 修复 / 验证。

### D-1（阻断，4-3 `S-RH` 恒不可行）

- **位置**：`run_rh` 的 `t0 = 0 if chain == CHAIN_42 else M.COMMIT_BLOCK`（= 36）配合 `window_plan`
  的「已提交前缀」等式行（`committed_*`）。
- **现象**：`day = 0, t0 = 36, H = 1` 的窗口 LP `status = 2`（infeasible）。
- **根因**：窗口把变量的第 `0..35` 个位置用等式钉到 `committed_*`，而 `4-3` 走这条路径时
  `plan_*`、`q` 尚为全零矩阵 ⇒ 等式要求 `E = 0`，与下界 `lb[E] = E_MIN = 1200` 直接冲突。
  （`4-2` 因 `t0 = 0` 跳过该分支，所以从未暴露。）
- **修复**：两条链的 S-RH 计划窗口**一律 `t0 = 0`**。语义上这与 `plan_v001` §3.3.4 的冻结边界一致：
  `4-3` 的计划层同样是 **0:00 对全天决策、只提交前 `COMMIT_BLOCK` 个时段**；`H` 只作用在计划窗口的
  纵向跨度上，`6:00/12:00/18:00` 调整层仍只支配当天。

### D-2（数值，4-3 `S-RH` 计划量尾部留零）

- **位置**：`run_rh` 只把**提交切片**写进 `plan_*`（`plan_b[day, commit] = window["b"][:36]`）。
- **现象/根因**：`4-3` 的调整层以**整日** `plan_b` 作为偏差结算基准（`solve_adjustment_layer_43`
  取 `plan_b[global_index - 1]`），而 `S-RH` 只填了前 36 个时段、其余为 0 ⇒ 即便 `H = 1` 也
  **不可能**复现主口径。
- **修复**：`plan_b/plan_c/plan_q_dis/plan_s/plan_E` **全量落盘**，仅 `q/c/q_dis/state` 取提交切片
  ——与 accepted `run_chain_43` 的结构逐行一致。

### D-3（闸门实现，`C3` 比对对象错取 `H = 14`）

- **位置**：`if want("SRH")` 分支的 `state_gap` 计算沿用了 for 循环结束后的 `outcome`。
- **现象**：`4-2` run002 的 `C3.state_trajectory_max_abs_difference_kwh = 9600.0`（恰为
  `E_MAX − E_MIN` 满量程），而同一判据的 `D_full`/`D_req` 相对差仅 `2.5e-16` / `5.7e-16`。
- **根因**：循环结束后 `outcome` 是 **`H = 14`** 的结果，被拿去与主口径比对储能轨迹。
- **修复**：显式保存 `rh_outcomes[horizon]`，`C3` 的轨迹比对改用 `rh_outcomes[1]`。
  **`plan_v001` §2 对 `C3` 的定义（`H = 1` 的费用相对差 + `E` 轨迹）与阈值 `1e-9` / `1e-6` 一字未改。**

### D-4（闸门实现，`C4` 单调方向写反）

- **现象**：`4-2` run002 报 `monotone_nondecreasing_cost = false`、`counterexample_registered = true`，
  而实测 `D_full` 费用随 `H` 为 `14,755,884 → 14,726,404`（单调**下降**）。
- **根因**：预注册期望是「`H` 增大 ⇒ 费用**不增**」（更多前瞻 ⇒ 不劣），实现判的却是「非减」。
- **修复**：改为 `nonincreasing`（`ordering[i] ≥ ordering[i+1] − 1e-6·max(|·|,1)`）。
  容差、口径、`T7-4` 的「出现**增**即如实登记反例、禁止强凑单调性」纪律均不变。

### D-5（数值，`S-VAR(4-3)` 偏差两段方向写反）

- **位置**：`_svar43_equivalent` 的不等式块。
- **现象/根因**：实现取 `u⁺ ≥ q − b`、`u⁻ ≥ b − q`，而 accepted `solve_adjustment_layer_43`、
  formulation `(AD-3)`、`plan_v001` §3.2.2（`u^± ≥ max(±(b − q), 0)`）与 `C_adj` 定义
  （`β_def·u⁺ + β_over·u⁻`，`β_def = 0.5`、`β_over = 1.5`）一律是 `u⁺ ≥ b − q`、`u⁻ ≥ q − b`
  ⇒ 旧实现把 **`0.5×` 段与 `1.5×` 段整体互换**，`S-VAR(4-3)` 的期望费用不可信。
- **修复**：与 accepted 逐字对齐（`u⁺` 配 `β_def`、`u⁻` 配 `β_over`）。
- **附加修复（同块，第二次探针发现）**：旧实现把每个场景的 `N` 个时段压到**同一行号**
  （整数 `row`），既把逐时段约束聚合成一条和式约束，又使 `A_ub` 行数与 `b_ub` 长度不一致
  （`linprog` 直接报 `b_ub must be a 1-D array`）。现改为**逐时段一行**
  （每场景 `2N` 行，`A_ub` 形状 `(2N·s_count, total)`、`b_ub = 0`）。
- 对 `4-2` 的 `S-VAR` 无影响（走 `_svar42_equivalent`）。

### D-6（阻断，`S-VAR(4-3)` 恒不可行）`_svar_common_equalities` 缺逐场景行偏移

- **根因**：每个场景都复用行号 `0..2N−1`，`coo_matrix` 把不同场景的系数**求和**进同一行，
  而 `b_eq` 仍是 `2N·s_count` 长度 ⇒ 第 `2N` 行之后是**零行配非零右端**，LP 恒 infeasible。
- **修复**：逐场景行偏移 `row0 = 2*N*s`（列偏移本就正确）。
- **为何此前未暴露**：`4-3` 在 S-RH 即失败，`S-VAR(4-3)` 从未被执行；`4-2` 的 `S-VAR` 走另一实现。

### D-7（`C8` 证据缺口 + 对照计数）

- **现象**：`S-VAR`/`S-VAR-RH` 摘要不含 `D_full`/`D_req`，而 `_walk` 只认这两键 ⇒ 其**约束残差不进**
  `checks_failed`，且 `case_counts` 少计 2 个对照（`4-2` 记 12，实为 14）。
- **修复**：(i) `S-VAR` 的两阶段 LP 逐 case 复算**等式 / 不等式 / 边界**残差并落盘
  `residuals`（阈值沿用 `TOL_STATE_ABS = 1e-6`）；`S-VAR-RH` 由窗口返回量复算同四项。
  (ii) `_walk` 同时接受带 `checks_failed` 的摘要 ⇒ `case_counts`：`4-2` 12 → **14**、`4-3` 7 → **9**
  （与 `plan_v001` §3 的对照矩阵一致）。

### D-8（口径对齐，使 `H = 1` 在两条链上**逐位**复现）

- **做法**：`window_plan` 增加 `include_q_em`：`4-2` 的**当天块**补入 `q_em` 变量（目标系数 `α_em·p`、
  界 `[0, ∞)`、平衡式 `+1`），使 `t0 = 0, H = 1` 时窗口 LP 与 accepted `solve_day_plan_42` 的
  **矩阵逐元素相同**；`4-3` 的当天块不含 `q_em`，与 `solve_plan_layer_43` 相同。
  `boundary_index` 统一为**当天块最后一个 `E` 的下标** `5·n_fine − 1`。
- **理由**：`plan_v001` §0.2/§2 要求 `H = 1` **逐位等于主口径**；D-3 把比对对象改回 `H = 1` 后，
  仍须保证 `4-2` 的窗口 LP 与主口径层**结构等价**（旧版的 `5n` 变量 vs 主口径 `6n` 会在退化最优面上
  给出不同的内部取点）。本项使 `C3` 在**最严读法**（整条 `E` 轨迹逐位）下通过，**无需**援引
  `D11`（「不比对各点解唯一性」）来放宽。

---

## 3. 修复验证（小型只读探针，**非交付数值**）

> 探针均在**隔离 task 之外**、`--days 60` 的小窗口上运行，只作修复有效性与可行性的自检。
> 按既有纪律，其数值**不得**作为论文、`report.md`、`sanity` 或交付表的证据；
> 正式数值一律以 run003 两个 isolation task 的产物为准。

| 探针目录 | 链 | `--cases` | 关键判定 |
|---|---|---|---|
| `results/_probe_run003_fix42/` | `4-2` | `BASE,SRH,SVAR,SVAR-RH` | `C3` **pass**（`D_full`/`D_req` 相对差 `0.0`、`state_trajectory_max_abs_difference_kwh = 0.0`）；`C4` `expectation_nonincreasing_cost = true`、`counterexample_registered = false`；`S-VAR` 残差 `≤ 1.8e-12`、`S-VAR-RH` 残差 `≤ 4.6e-13`、`checks_failed = []`；`exit 0`；`case_counts = 7` |
| `results/_probe_run003_fix43b/` | `4-3` | `BASE,SRH,SVAR,SPILL,KAPPA1` | `C3` **pass**（相对差与状态轨迹差均 `0.0`）；四条 `S-RH` 深度全部可行（`day=0, t0=0, H=1` 不再 infeasible），`H=1` 的 `D_req` 与 `BASE-43` 相对差 `0.0`；`S-VAR(4-3)` 残差 `≤ 9.1e-13`、`checks_failed = []`；`exit 0`；`case_counts = 8`；整批墙钟 **49.25 s / 60 天** |

- `C2` 在两份探针中**预期失败**（`--days 60` 的总量与全年参考 `BASE_RUN002` 直接相比，未做天数归一化）
  ——这与 `robustness/RUN_LESSONS_v001.md` 的 `P-1` 同类，属时域口径错配，**不是模型错误**。
- `C-ANCHOR-P03`（强制闸门 `C1`）本轮未重跑：其代码路径（`run_chain_variant` + `fallback_seed`）
  在本次修订中未被触碰，且已由前一动作的 365 天探针 `_probe_final43_anchor` 实测 `C1 pass = true`
  （六项相对差 `≤ 4.9e-13`）；run003 会以全年口径正式复跑并落盘 `C1` 判定。
- **探针暴露的结构性发现（必须写入 `report.md`，不得包装为模型缺陷）**：`S-VAR(4-3)` 的追索层按
  `plan_v001` §3.2.2 让 `q^{(s)}` 自由 ⇒ 最优处 `u^{±} ≡ 0`（实测逐场景 `cost_adj_yuan` 合计
  `3.2e-12` 元），偏差惩罚在实际可行域上**不构成成本** ⇒ `S-VAR(4-3)` 的期望费用与 `S-VAR(4-2)`
  逐位相近（60 天探针：`18,672.573387575` vs `18,672.573387573`，差 `1.9e-9` 元）。该对照的结论应表述为
  「**若允许调整层完全自由追索，`0.5×/1.5×` 偏差结算就不产生期望成本**」，**不得**与主口径 4-3
  的 `C_adj` 混写；**也不得**据此修改 `plan_v001` 预注册的第二阶段变量集合（事后改模型 = 判据污染）。

---

## 4. 批次修订（run002 → run003）

| 链 | run002 task | run003 output_directory | `--cases` | task timeout | 整批 wall |
|---|---|---|---|---|---|
| `4-2` | `6ef360822fc3520116a0` | `..._ablation_4-2_run003` | `all`（14 对照） | 5400 s | 3000 s |
| `4-3` | `4e3e59706fa0888083ec` | `..._ablation_4-3_run003` | `all`（9 对照） | 12600 s | 10800 s |

- 代码修订改变 `code_hash` ⇒ 新 `task_id` ⇒ **新 `output_directory`**；`run001` 与 `run002` 的目录与产物
  **原样保留、不覆盖、不删除**，仅作审计对照，**不作交付值或对照值**（`plan_v001` §6）。
- **两条链同批重跑**：`plan_v001` §3.8 要求同数据、同参数、同预算、**同代码修订**可比。
- 对照集合、求解器（HiGHS）、每层时限 60 s、`seed = 20260911`、`Δt`、`η`、`α_em`、`β_def/β_over`、
  终端自由、`E ∈ [1200, 10800]` 等**全部不变**。

---

## 5. 本文件不改变的事项（明确声明）

1. 不改变 `plan_v001` 的任何判据、阈值、对照集合、公平性纪律与失败处置；
2. 不改变 `plan_v002` 登记的编码修复与 `C-ANCHOR-P03` 构造补全（`fallback_seed`）；
3. 不改变 accepted `assumption_v001`、`formulations/formulation_v001` 与同版本 `code/`；
4. 不把 `run001`/`run002`/任何探针的数值引作交付值或对照值；
5. 主口径仍是 `PF-PERSIST` 点预测 + 确定性 LP；`S-VAR`/`S-RH`/`S-VAR-RH`/`PF-AR`/`C-ANCHOR-P03`
   只进 `ablation`，**不进入** `result4-2.xlsx`/`result4-3.xlsx`；
6. `4-3` 的 `S-RH` 显式边界（`plan_v001` §3.3.4：深度只作用于计划层）不变；
7. 不写回 prob03、不改 `data/附件5/`、不改 `results/prob04_v001_f001_*`。
