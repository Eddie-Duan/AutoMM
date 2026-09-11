# 实现计划（implementation，prob04：波动电价下重算问题 2 与问题 3）

- 归属：`microgrid_2025` / `prob04`（**一道小问、两套结果**：链 `4-2` ≙ 重算问题 2 → `result4-2.xlsx`；
  链 `4-3` ≙ 重算问题 3 → `result4-3.xlsx`，两条链**各自独立** `output_directory` 与 `run_manifest`）；阶段：`implementation`
- 同步动作：`act-be9040ad7b264d3e`（负责人：implementation-agent；策略 P5 / `action=run_agent`）
- 版本目录：`problems/microgrid_2025/prob04/versions/assumption_v001/`
- accepted 依据（全部只读）：
  - `assumptions.md`（assumption_v001，23 条假设／9 条关键 AS07–AS12/AS15/AS17/AS18；决策点 D1–D12；
    文末**团队裁定 R-1 `S-VAR` / R-2 `S-RH`**——只追加 `ablation` 预注册对照，不改变主口径）
  - `formulations/formulation_v001/{formulation.md,formula_validation.md,parameters.yaml}`（accepted，945 行）
  - `AGENTS.md`「prob04 交付结构」「`A8` 团队裁定（2026-09-11）」「prob04 预注册 `ablation` 对照项」
  - 上游：`../prob03/versions/assumption_v001/{code,implementation.md}`（三层链 + 降尺度 + tie-break + `result3` 填报模板）、
    `../prob02/versions/assumption_v001/code/`（`result2` 填报几何）、`../prob01/versions/assumption_v003/`
- 输入依据（全部只读）：`request/problem.md`（问题 4）、`data/附件2.xlsx`（`bb3e493f…`）、`data/附件3.xlsx`（`8a61b06c…`）、
  `data/附件4.xlsx`（`cf876237…`）、`data/附件5/result4-2.xlsx`（`b878ce2b…`）、`data/附件5/result4-3.xlsx`（`75be588e…`）
- 规则依据：`agents/implementation-agent.md`、`agents/resource-manager.md`、`PROJECT.md`、`RESEARCH_LOOP.md`、
  `config/{compute,gates,workflow}.yaml`、`wiki/compute-tasks.md`、`knowledge/optimization.md`
- 不覆盖历史：本动作只写 `prob04/versions/assumption_v001/code/`、`implementation.md` 与本 action 的 `evidence/`；
  **未**修改 `assumptions.md`、`version.yaml`、`formulations/`、`data/`、`request/`、`global_symbols.yaml`、`citations.yaml`、
  `question_manifest.yaml`、`runtime/workflow_state.json`，也**未**改动 `prob01/`、`prob02/`、`prob03/` 任何文件；两个模板工作簿只读
- **本动作未运行 365 天正式计算、未创建/提交任何 task、未写 `results/`**（implementation 机械边界）：
  最长探针为 `--days 34` 端到端；`task_spec_dryrun.py` 只**构造** spec（`submitted=false`、`tasks_created=0`）。
  正式数值由 `computation` 阶段的隔离 task + supervised worker 产出

---

## 1. 口径落地清单（accepted 假设 / formulation → 代码位置）

### 1.1 两条链的模型骨架

| 口径 | 取值/要求 | 代码落点 |
|---|---|---|
| **AS01** 左端点相位 | 位置 `i` ↔ 区间 `[10(i−1), 10i)` 分钟；计划窗 `0:10 → 24:10`；表 1 的 `10:00-10:10` 取位置 60 | `prob04_io`（按行位置读取、不排序/不插值）、`run_prob04.build_tables` 双标签校验 |
| **AS02** 输入范围 | `4-2` 用附件 2 + 附件 4；`4-3` 用附件 2 + 附件 3 + 附件 4；**附件 1 全程未读** | `run_prob04` 的 `ChainInputs` 构造；`run_manifest.input.attachment1_used=false` |
| **AS03** 跨日与终端 | 自 2025-01-01 以 `E_init = 6000` 滚动递推（`E_{d,0} = E_{d−1,144}`，1 月预热）、终端自由 | `prob04_model.run_chain_42` / `run_chain_43` 的 `e_real` 链 |
| **AS04** 设备与量纲 | `E_t = E_{t−1} + 0.9c_t − q_dis_t/0.9`；`1200 ≤ E ≤ 10800`；`c ≤ 833.3333`、`q_dis ≤ 750.0000`；`Δt = 1/6`、费用**不乘** `Δt` | `prob04_model` 常量与两层/三层 `bounds`；量纲红线见 §5.2 |
| **AS05**（D9-B） | 各层 `0 ≤ s ≤ max(0, PV^{层}·Δt − L·Δt)`（分层用该层 PV） | 两层/三层 `bounds` 的 `s` 上界 |
| **AS06** | 外网购电无上限、余电不上网；主口径**无购电上限** | `bounds` 中 `b/q` 上界 `np.inf` |
| **AS07**（key）`A8-(b)` | 0:00 **不见**当天任何未来价；决策只用 `≤ d−1` 的实际价；结算一律用附件 4 实际价 | `prob04_predict.available_history`（显式 `H_d` 入参）、`layer_price`、结算块 |
| **AS08**（key） | 主预测器 `PF-PERSIST`；`PF-DUAL`/`PF-HIST` 强制基准；`PF-AR` 归 `ablation`；滚动回测与预注册选择规则 | `prob04_predict.roll_backtest`、`pf_*`、`forecast_backtest.json` |
| **AS09**（key） | 决策—结算分离；`ΔC_price = C^{act} − C^{fc}` 分项给出，两窗口同时报 | `prob04_model.cost_breakdown(use_actual_price=…)`、`evaluate` 的 `belief` 段 |
| **AS10**（key，仅 4-2） | `4-2` **逐日向前递推**（每天 1 个当日 LP + 状态传递 + 终端自由）；**不得**写成单一长时域 LP | `solve_day_plan_42` / `run_chain_42` |
| **AS11**（key，仅 4-3） | 调整层 `κ_m` 水平校正 + 逐层信息集；`i ≤ 6m` 锁定、`R_m` 前视、只提交 `D_m` | `prob04_predict.kappa_schedule`、`solve_adjustment_layer_43`、`run_chain_43` |
| **AS12**（key） | 主口径 = 价格点预测 + 确定性 LP；随机/鲁棒只作 `ablation` | 本 `code/` **只实现主口径**（+ `--model a2-pre` 的下界锚点）；`S-VAR`/`S-RH` 未实现、未跑 |
| **AS13** | 两链共用同一预测器与同一结算口径（`κ_0 ≡ 1` ⇒ 计划层与 4-2 同源） | `prob04_predict` 为两链唯一预测器入口 |
| **AS14**（`A22`） | `α_em = 5`、`β_def = 0.5`、`β_over = 1.5` 的**结算**基数为附件 4 实际价；决策层用该层预测价 | `cost_breakdown` 的两套价格向量；`evaluate` 的 `checks` |
| **AS15**（key，仅 4-2） | 计划层目标 `min Σ \hat p·b + Σ α_em·\hat p·q_em`；费用 `C_total = C_plan + C_em`（无 `C_adj`） | `solve_day_plan_42`；`q_em` 变量**保留** |
| **AS16**（`A23`） | `q_em ≥ 0` 只补缺口、不用于充电；`4-2` 中 `q_em ≡ 0`（定理）；`4-3` 中由光伏预报缺口在结算层产生 | `solve_day_plan_42` 保留 `q_em`；结算闭式 `max(0, ±r)`；`statistics` 落盘实测值 |
| **AS17**（key，仅 4-3） | 读法 A 主口径：计划全额计价 + `0.5×`/`1.5×` 双向偏差（两段均为成本项、不回溯、单次结算） | `solve_adjustment_layer_43` 的 `u⁺/u⁻` 与 `cost_breakdown` 的 `C_adj` |
| **AS18**（key，仅 4-3） | 三层顺序向前递推、不回溯；**实际光伏只进结算层** | `run_chain_43` 的「逐层求解 → 只提交 `D_m`」；`checks` 的逐层信息集项 |
| **AS19** | 附件 3 整点点值 + `k=1` 前向保持 + 整点锚定线性插值；`m` 只支配 `i ≥ 6m+1`；跨年项不消费；`日期` 列前向填充 | `prob04_model.downscale`、`cross_year_dropped_count`、`block_energy_bias` |
| **AS20** | 表 1/2/3 与两个交付工作簿的填报与新写纪律（334 天、末两列、六块、`时刻` 前两行、`—`/0） | `prob04_io.fill_result42_workbook` / `fill_result43_workbook` + 保存前 `_residual_report` 硬门禁 |
| **AS21** | 统一字典序 tie-break：先 `min 该层主目标`，再在主目标最优面上 `min Σ(c + q_dis)` | `prob04_model._solve_with_tiebreak`（四段式，复用 prob03 的语义与 ε 相对化） |
| **AS22** | 派生记号 `p^{act}` / `\hat p^{(m)}` / `κ_m` 的局部声明与接口纪律 | `prob04_predict` 的 `layer_price` / `belief_price` / `kappa_m`；`run_manifest.layer_inputs` |
| **AS23** | 不计静置损耗与自放电 | 状态转移式 |

### 1.2 `4-2` 链（`M4-2`，formulation §2.2–§2.5）

```
对每个 d ∈ D_full 顺序求解单日 LP：
(PL2-0) min  Σ_i \hat p_{d,i}·b_i + Σ_i α_em·\hat p_{d,i}·q_em_i          （\hat p = PF-PERSIST）
(PL2-1) b_i + q_em_i + PV^act_{d,i}·Δt + q_dis_i = L_{d,i}·Δt + c_i + s_i   ∀i
(PL2-2) 0 ≤ c ≤ 833.3333 ; 0 ≤ q_dis ≤ 750.0000 ; q_em ≥ 0
(PL2-3) 0 ≤ s_i ≤ max(0, PV^act_{d,i}·Δt − L_{d,i}·Δt)                     ∀i
(PL2-4) E_i = E_{i−1} + 0.9c_i − q_dis_i/0.9 ; 1200 ≤ E_i ≤ 10800
(PL2-5) E_0 = E_{d−1,144}（E_{1/1,0}=6000）；E_{12/31,144} 自由
(PL2-6) b_i ≥ 0（无上界）
提交全天 (b, c, q_dis, s)；q := b；结算层闭式 s' = max(0,r)、q_em = max(0,−r)
费用 C_total^act = C_plan^act + C_em^act（4-2 无 C_adj）；对照口径 C_total^fc 用 \hat p
```
- `q_em` 变量与 `α_em·\hat p·q_em` 项**保留**（AS15 明令），实测计划层 `max q_em = 0.0`、结算层 `Σq_em = 0.0`（定理成立）。
- 2025-01-01 的 `H_d = ∅` 回退见 §1.4-C1；该日属预热期，不参与回测、不影响 `D_req` 指标。

### 1.3 `4-3` 链（`M4-3`，formulation §3.2–§3.6）

```
计划层 (PL_d)  m = 0：min Σ_i \hat p^{(0)}_{d,i}·b_i，用 Π_0[PV]；**不含 q_em**；
              提交 D_0 = {1..36}：q_i = b_i、c_i、q_dis_i
调整层 (AD_{d,m})  m ∈ {6,12,18}（顺序求解）：
              b_{d,·} 全天为**参数**；变量定义在 R_m = {i : 6m < i ≤ 144}（前视）；**只提交** D_m = (6m, 6m+36]
              已提交时段 i ≤ 6m 固定，不得回溯；E_{6m} = 上一已提交链末态（参数）
              min Σ_{i∈R_m}[β_def·\hat p^{(m)}_{d,i}·u⁺_i + β_over·\hat p^{(m)}_{d,i}·u⁻_i]
              u⁺ ≥ b − q、u⁻ ≥ q − b、u^± ≥ 0（LP 无损分段线性化）
结算层 (ST-3) 事后闭式：r = q + q_dis + PV^act·Δt − L·Δt − c；s' = max(0,r)；q^em = max(0,−r)
价格口径：(K-1) \hat p^{(0)} = p^{act}_{d−1}；(K-2) \hat p^{(m)}_{i} = p^{act}_{d,i} (i ≤ 6m)
          / κ_m·p^{act}_{d−1,i} (i > 6m)；(K-3) κ_m = clip(mean_{i≤6m}p^{act}_{d,i} / mean_{i≤6m}p^{act}_{d−1,i}, 0.5, 2.0)
```
- `Π_m`（`prob04_model.downscale`）：`k = ⌈i/6⌉ − m`（`k=1` 前向保持 `A_{m,1}`；`2 ≤ k ≤ 24` 整点锚定线性插值）；
  `m = 6/12/18` 分别丢弃 `k = 19..24 / 13..24 / 7..24`（合计 **36** 项，逐个落盘）。
- 两套计价：`C^{act}` 全用 `p^{act}`；`C^{fc}` 用 `\hat p^{fc}_{d,i} = \hat p^{(ν(i))}_{d,i}`（`ν(i) = 6·⌊(i−1)/36⌋`）。

### 1.4 与 upstream / formulation 的**不一致、口径澄清与补充**（显式记录，不静默沿用）

| 编号 | 事项 | 旧登记/formulation 写法 | 本实现执行 | 依据/去向 |
|---|---|---|---|---|
| **C1** | `2025-01-01` 决策价 | §1.3.4 (FB)「取 (PF-HIST) 在该日的扩张窗均值」 | 该式在 `H_d = ∅` 下**无定义**。实现取**常量中性价** `\hat p_{1,i} ≡ 1.0`（`fallback_constant_price`）：平坦价 ⇒ 无套利激励 ⇒ 储能保持 6000 kWh，是最少信息的合法选择；**不使用**未来价或全量均值；该日不参与回测（`D_full` = 364 天）；4-3 调整层未实现段同样按 `κ_m=1 × 1.0` 处理并单独登记 | 登记见 `solution.json.forecast_fallbacks` / `run_manifest.forecast_fallbacks`；建议 formulation 下一版把 (FB) 写实 |
| **C2** | `PF-DUAL` 回测与假设阶段登记值差 **+0.22%** | 登记 `D_req` MAE `0.093183`、P90 `0.2052` | 按 §1.3.1 字面式复算得 MAE `0.093387`、P90 `0.2065`（bias 逐位相同 `−0.000328`）；另试 4 种窗口/形状变体均不吻合（见 `owner_dual_check_out.txt`） | 相对差 ≪ BT-6 的 5% 阈值，且**主口径选择余量为 10.7%** ⇒ 交付数值不受影响；仅登记为诊断口径差 |
| **C3** | `PF-AR` 的最小样本量 | §1.3.1 只给「最小实现」公式 | 逐时段 OLS 在配对样本 < 3 组时斜率无界（实测 2025-01-03 会给出 134 元/kWh 的病态预测）。取 `AR_MIN_PAIRS = 3`，不足时回退 `PF-HIST` 并标记 `pf_ar_regression_undefined` | **仅 `ablation` 对照**，不影响主口径；登记于 `forecast_backtest.fallbacks` |
| **C4** | `PF-AR` 的 `D_req` MAE **低于** `PF-PERSIST` | AS08 登记 `PF-PERSIST` 为 MAE 最小者（0.084326） | 实测 `PF-AR` MAE `0.080664` < `PF-PERSIST` `0.084326`。AS08 **明令** `PF-AR`「登记为 `ablation` 强制对照，**不参与主口径选择**」，故主口径仍为 `PF-PERSIST`；但该事实**必须在论文与 `ablation` 中显式披露**（预测器选择敏感性） | 本实现不改口径；写入响应 `warnings`，建议 `ablation` 的 `PF-ALT` 必跑 |
| **C5** | (BD2-LB) 解析下界 | §2.6 `p_min·(N_W − 8640)` | 该式依赖 (I2-2d) 的 `Σb` 恒等式（4-2 成立，4-3 只有 `Σq`）。两链统一改用弱但**无条件成立**的 `C_total^act ≥ C_plan^act ≥ p_min·Σb`；构造上界按「无储能可行策略」逐层构造（4-3 含 `C_adj`/`C_em` 段） | 落 `solution.json.bounds`；探针实测两链均满足且未乘 `Δt` |
| **C6** | `4-2` 的弃光 `Σs' = 0`（探针窗） | formulation 未预设 | 探针窗（1 月）逐时段 `PV^act − L` 最大仅 467.7 kWh 且计划层用**实际**光伏 ⇒ 计划层不放空、结算 `r = s ≥ 0`，故无弃光；全年窗口才可能非零 | 登记为窗口事实，不得写成「模型恒无弃光」 |
| **C7** | `4-3` 的「`q_em > 0` 且 `c > 0`」时段数 | formulation §7 第 10 条「期望为 0」 | 实测 **596/4896**（34 天探针，12.2%）。机制：决策层用附件 3 降尺度预报、结算层用附件 2 实际 ⇒ 预报高估时段已下达充电而结算出现缺口。结算层互补性仍成立（`q_em>0 ⇒ s'=0`） | 已补预报误差量化（`probe_prob04_structure_out.json.downscale.pv_forecast_error_vs_actual`：`m=0` 每 10 分钟 MAE 21.54 kWh ≈ 129 kW、29% 时段预报高于实际）；sanity 只作统计与归因（承 prob03 `N2`） |
| **C8** | `4-3` 的**同充放**时段数 | formulation §7 第 10 条「最优解处自然不取同充放，期望 0」；prob03 T7 后实测 0 | 实测 **152/4896**（3.1%），全部落在**调整层**：该层主目标为偏差结算（在 `q = b` 处为 0），次目标只覆盖 `R_m`，E 轨迹整形使单时段同时充放仍为最优 | 登记为**退化层的结构性事实**；sanity 不得判为模型失败；禁止为凑 0 改 tie-break（AS21/`T7-4`） |
| **C9** | LP 无损性的判据 | §5-L5「LP 与 MILP 最优值相同」 | 小实例实测 LP `744.7962966687` vs MILP `744.7962962963`：绝对差 `3.72e-7`（相对 `5.0e-10`，且 LP 略高于 MILP ⇒ 无整数间隙）。为给出精确证据，另加「把 MILP 最优解代回 LP 目标」的检查：差 **0.0** | Big-M 由模型界推导（`M⁺ = max b`、`M⁻ = max_i[L_i + C_CAP + max(0, PV_i − L_i)]`），未取大数 |
| **C10** | `b`/`q` 逐位容差的读法 | D7-A 写「逐位差 ≤ 1e-9」 | 小实例实测 `b` 差 `0.0`、`q` 差 `1.19e-9`（绝对；相对 `9.7e-13`）、`C_total` 差 `5.0e-10`（相对 `5.0e-13`）。探针按「**绝对 ≤ 1e-6 且相对 ≤ 1e-9**」判定并同时落盘两值 | 属 HiGHS 可行性容差噪声，非结构差异 |
| **C11** | 两份 task spec 的 `task_id` 冲突（**框架级发现**） | — | `automm.tasks.compute_task_id` 的身份**不含** `output_directory`/`command`。两链共用 code + input ⇒ 若再共用 config，两份 spec 会算出**同一** `task_id`（实测 `5035744a77340d1b467e`），`submit_task` 会按 `runtime/tasks/<task_id>` 互相覆盖/拒绝，task group 的 `expected_tasks=2` 永不满足。修法（**不越权改 `scripts/`**）：新增链专用 `task_config_4-3.yaml`（`chain_scope: "4-3"`）⇒ `config_hash`/`task_id` 均不同 | 见 §7；`resource-manager` **必须**为两链分别传 `--config-path` |
| **C12** | 模板渲染细节 | §8.3 登记模板 `充放电量` `max_row = 20`（4-2）/26（4-3） | openpyxl 清空单元格后仍保留行维度 ⇒ `max_row` 停在模板值，而**非空行**为 `1 + 334×6 = 2005`。`_residual_report` 与独立扫描脚本均按**非空行**判定 | 实测 `format_residuals = []`、独立扫描 `problem_count = 0` |
| **C13** | 两层结构澄清 | §5.1 禁止 `4-2` 定义独立 `q` | `4-2` 只定义 `b`（提交时 `q := b`）；`4-3` 计划层不含 `q_em`、`4-2` 计划层**保留** `q_em` | 见 §1.2/§1.3 |

---

## 2. 代码结构与职责

目录：`problems/microgrid_2025/prob04/versions/assumption_v001/code/`（8 个文件，本动作**全部新建**）

| 文件 | 职责 | 主要接口 |
|---|---|---|
| `prob04_io.py` | 读附件 2（两工作表、日期连续、非负有限）、附件 3（`日期` 前向填充 + `2025-1-1` 规范化 → `(365,4,24)`）、**附件 4**（`Sheet1` 366×145 → `(365,144)`，与附件 2 同相位校验）；只读实测两个模板几何；把交付解填入 `result4-2.xlsx`（三表）/`result4-3.xlsx`（四表）并做保存前逐格残留硬门禁；JSON 落盘 `allow_nan=False` | `read_attachment2/3/4_price`、`inspect_template42/43`、`fill_result42_workbook`、`fill_result43_workbook`、`write_json`、`interval_label` |
| `prob04_predict.py` | `PF-PERSIST`/`PF-HIST`/`PF-DUAL`/`PF-AR`；`H_d` 显式入参；滚动回测（两窗口、全指标、夺冠计数、预注册选择）；`κ_m` 与截断登记；`(K-2)` 分层价与 `(G-4)` 信念价；2025-01-01 常量中性价回退 | `available_history`、`predict(_day)`、`roll_backtest`、`kappa_m`、`kappa_schedule`、`layer_price`、`belief_price` |
| `prob04_model.py` | `Π_m` 降尺度、支配映射、跨年丢弃计数、块能量偏差统计；**AS21 共享 tie-break 四段式**；`solve_day_plan_42` / `solve_plan_layer_43` / `solve_adjustment_layer_43`；`run_chain_42` / `run_chain_43`；`solve_a2_pre`；`cost_breakdown(use_actual_price)`；`evaluate`（恒等式、硬检查、统计量、量级带） | 见左列 |
| `run_prob04.py` | CLI：`--chain {4-2,4-3}`、`--model {main,a2-pre}`、`--days`、`--time-limit`、`--max-wall-seconds`；探针模式改写 `probe_result4-*.xlsx` 并跳过四项正式模式硬检查；退出码 `0/2/3/4/1` | `main`、`build_tables` |
| `task_config.yaml` | 链 **4-2** 的 task 级配置（`compute`/`solver` + 资源与 tie-break 说明） | – |
| `task_config_4-3.yaml` | 链 **4-3** 的 task 级配置（**`chain_scope: "4-3"` 使 `config_hash`/`task_id` 与 4-2 不同**，见 C11） | – |
| `task_spec.yaml` | 链 4-2 的完整隔离计算 task 规格（另含 `companion_task_spec` 指向 4-3） | – |
| `task_spec_4-3.yaml` | 链 4-3 的完整隔离计算 task 规格 | – |

### 2.1 代码指纹（本动作终稿，`act-be9040ad7b264d3e`）

| 文件 | sha256 |
|---|---|
| `prob04_io.py` | `c2bdab84b908c58006c0118d76773d93929ed88b5137b37d2c5374a3e628ab8e` |
| `prob04_model.py` | `c367367de2af14f2660f224329fc793822fb64d9ee270e23d0df8d7105e7fb56` |
| `prob04_predict.py` | `87a801a8848e2997afc9f188010db7d00947d5cf7839204d8d4fedfaad8e2ba3` |
| `run_prob04.py` | `b8b40d9884ab4632554cb31b82f004dd380680ef3112baaf8aab01bb39d4ca02` |
| `task_config.yaml` | `a7792f931c96efba8e6776c096d7219fe9939a97e4aa70d989d4047479f55678` |
| `task_config_4-3.yaml` | `729f4ebce883ce1f712b68cfbbf0113194f0f8794a74bd3567aa34c3205341c2` |
| `task_spec.yaml` | `5a81a0c3b76f10874d74e2b5588df5108360b2b8d0131e6c1b2522746e244cac` |
| `task_spec_4-3.yaml` | `31b7a57ccd0985b35619f00c6db967178dd9e85c786635badc04af63da033283` |

- 代码目录 harness 指纹（`automm.common.hash_path`，忽略 `__pycache__`）：
  **`7fbc9610f5adc85d4ec65acb949f01afa7739a918d2131496b751f2206f1360e`**；`hash_path("data")` = `4343d799…`（与 prob01/02/03 相同，`input_path = data` 未变）。
- 逐文件 sha256、目录哈希、输入 md5 与全部证据 sha256 见 `evidence/code_and_input_hashes.txt`（由 `code_and_input_hashes.py` 生成，可复现）。

### 2.2 模型规模（与 formulation §8.6 逐项一致，`run_manifest.matrix_scale` 落盘）

| 链 / 层（每日） | 连续变量 | 等式 | 不等式 | 说明 |
|---|---|---|---|---|
| `4-2` 计划层 | 864 | 288 | 0 | `b, c, q_dis, s, E, q_em` 各 144；`q_em` 保留（实测恒 0） |
| `4-3` 计划层（`m=0`） | 720 | 288 | 0 | `b, c, q_dis, s, E` 各 144；**不含 `q_em`** |
| `4-3` 调整层 `m=6` | 756 | 216 | 216 | 追加 `u⁺, u⁻` 各 108 |
| `4-3` 调整层 `m=12` | 504 | 144 | 144 | 同上 |
| `4-3` 调整层 `m=18` | 252 | 72 | 72 | 同上 |
| **`4-3` 单日合计** | **2,232** | **720** | **432** | 4 次层求解/日 |
| `4-2` 全年层求解 / 名义 LP | 365 / **1,460** | — | — | 1 层/日 × 4 段式 |
| `4-3` 全年层求解 / 名义 LP | 1,460 / **5,840** | — | — | 4 层/日 × 4 段式 |
| 整数变量（主口径） | **0** | — | — | LP，无 Big-M |

> 「名义 LP」= AS21 四段式（① 纯主目标基线 ② 字面 ε 加权诊断 ③ 主目标最优面上的字典序提交解 ④ 退化/多重最优探测）；
> T7-2 式不变性每触发一次 ε 收缩另加 1 次（有界于 `T7_MAX_SHRINKS`）。实测探针 `total_shrinks = 0`。

---

## 3. 运行环境、求解器与资源实测

- 求解器：`scipy.optimize.linprog(method="highs")`，**CPU 求解、不使用 GPU**（`device = cpu`、`gpu_required = false`）：
  不占用单卡 GPU 串行额度；本问无 torch/CUDA 依赖，**未安装或升级任何依赖**，也未调用 `nvidia-smi`。
- 确定性：`seed = null`，代码不读取任何随机源；同输入/同版本必须复现同一目标值。
- 解释器：项目 venv（`.venv/Scripts/python.exe`，Python 3.14.4；numpy 2.5.2、scipy 1.18.1、openpyxl 3.1.5、ruff 0.16.5）。
- **本动作实测（`--days 34` 端到端，`probe_mode=true`）**：

| 链 | 层求解 | 名义 LP | 层求解耗时 | 端到端 wall | 预期全年 |
|---|---|---|---|---|---|
| `4-2` | 34 | 136 | 0.277 s | **1.059 s** | < 40 s |
| `4-3` | 136 | 544 | 1.003 s | **3.619 s**（`task_config_4-3.yaml` 记 8.0 s，含首次落盘抖动） | < 150 s |

- 预算：单层 LP 时限 `--time-limit 60`；整链墙钟预算 `--max-wall-seconds 1500`；task `timeout_seconds = 1800`
  ⇒ 余量 ≥ 1 个数量级。内存：单层 LP ≤ 756 变量 / 288 等式的稀疏矩阵，常驻 < 400 MB（< `memory_per_worker_gb = 2`）。
- **单卡 GPU 串行约束不适用**（两链均 CPU）；`config/compute.yaml` 的 `max_local_concurrent_tasks = 1` 使两链必须**串行**提交。

---

## 4. I/O 契约

### 4.1 输入（只读；md5 由本动作实测，见 `evidence/code_and_input_hashes.txt` 与 `run_manifest.input`）

| 文件 | md5 | 用途与实测结构 |
|---|---|---|
| `data/附件2.xlsx` | `bb3e493f804678de571575116eca1ae6` | 两链的负载与**实际**光伏：`小区负载` / `光伏发电实际功率` 各 366 行 × 145 列（365 天 × 144 点） |
| `data/附件3.xlsx` | `8a61b06c52bd0d639a1cc37c61a7d9f5b75edcbca718f64c1bd3498ec9f9d843`（sha256；md5 `e8dfee653d53a78c82198f657a01feb4`） | **仅 4-3**：1461 行 × 26 列（365 天 × 4 发布时刻 × 24 提前量）；`日期` 列 1095 行为空 ⇒ **前向填充**；`2025-12-31 18:00` 的 `k=7..24` 为跨年项（不消费） |
| `data/附件4.xlsx` | `cf8762375436b281dc33b6432e441a6a` | **两链的价格唯一来源**：`Sheet1` 366 行 × 145 列；实测 `p ∈ [0.0076, 1.7936]`、均值 `0.766198`、零价 **0** 个 |
| `data/附件5/result4-2.xlsx` | `b878ce2b016155f49486af25c51e8cab` | 4-2 交付模板（只读）：三表 `计划购电量`(335×147) / `充放电量`(20×6) / `紧急购电量`(11×3) |
| `data/附件5/result4-3.xlsx` | `75be588e714646dde3102aa102382347` | 4-3 交付模板（只读）：四表（多 `调整购电量` 335×147） |
| `data/附件1.xlsx` | — | **两链均未读取**（`run_manifest.input.attachment1_used = false`） |

- 模板实测与 formulation §8.3 登记值**无差异**（`run_manifest.input.template_differences = []`）：列标签首末 `0:10-0:20` / `0:00-0:10+1`、
  末两列 `全天购电量`/`全天购电费`、`充放电量` 六块与 `时刻` 前两行 `00:00:00`/`24:00`、`紧急购电量` 含 `⁝` 压缩行。
- `input_path = data`（整目录参与 `input_hash`），故附件 2/3/4 或模板变化会使 task ID 改变。

### 4.2 输出（正式模式，写入各链**独立**的 `output_directory`）

| 文件 | 内容 |
|---|---|
| `result4-2.xlsx` / `result4-3.xlsx` | 按模板填报；**保存前** `_residual_report` 逐格复核「应空却仍有值」，非空即硬门禁失败（exit 4） |
| `solver_status.json` | `status/message/solver/chain/model/objective_yuan/delivery_cost_yuan/feasible_incumbent/lp_calls/lp_solver_invocations_nominal/layer_status_max/layer_*_residual*/layer_seconds_total/wall_seconds/device/gpu_required/seed/probe_mode` |
| `solution.json` | `objective_yuan`、`cost_plan/adj/em_yuan`、`belief`（两套计价与 `ΔC_price` 分项）、`delivery`、`totals`、`identities`、`bounds`、`statistics`、`daily`、`checks`/`checks_failed`、`t7_tiebreak`、`forecast_fallbacks`、`layer_summary`、5,256/4,896 时段 `series` |
| `tables.json` | 表 1（六时段 + 双标签校验）/表 2（六块、端点语义、相位）/表 3（合并区间 + 左端点标签）；含「表 4 是格式示例」与「与 prob01 单日周期区分」的注记 |
| `forecast_backtest.json` | 预测器滚动回测（两窗口全指标、夺冠计数、选择规则、信息集纪律、失败回退计数） |
| `tiebreak_audit.json` | AS21 审计：`policy/rule/epsilon_definition` + `summary` + `per_layer`（逐层 `primary_before/after`、`primary_relative_change`、`throughput_*`、`degeneracy_degree`、`boundary_state_kwh`、`committed_solution`） |
| `run_manifest.json` | 版本/链/模型/参数/输入 md5/`code_sha256`/环境/`task_id`（正式模式由 Runner 注入）/`matrix_scale`/`layer_inputs`（逐层价格与预报指纹）/`naming`/`total_*_kwh`（**`D_req` 口径**，`total_purchase_kwh` 装 `Σq`）/`delivery`/`statistics`/`checks_failed`/`outcome`/`probe_mode` |

- `run_manifest.total_*_kwh` 为 `D_req`（334 天）口径且 `total_purchase_kwh` 装的是 `Σq`（`4-2` 中 `q ≡ b`）；
  **stdout 摘要为 `D_full` 口径**（承 prob03 勘误 `E6`，sanity 引用时必须标注窗口）。
- 探针模式（`--days < 365`）**不写** `result4-2.xlsx`/`result4-3.xlsx`，改写 `probe_result4-2.xlsx`/`probe_result4-3.xlsx`，
  置 `run_manifest.probe_mode = true`，跳过「解析界/量级带」四项硬检查（仍计算并打印诊断值，`bounds.hard_checks_applied = false`），
  且 stdout 首行显式声明「本产物不是交付结果」。

---

## 5. 硬约束、失败条件与退出码

### 5.1 `solution.json.checks`（阈值：层内求解器残差**绝对** `1e-6` + **相对** `1e-8`；余额残差 `1e-8`；其余 `1e-6`）

- **求解**：`layer_status_max = 0`（全部层求解 Optimal）、各层等式/不等式/界残差（含相对量）。
- **结构**：逐时段结算平衡、状态转移闭合、跨日状态闭合 `|E_{d,0} − E_{d−1,144}| ≤ 1e-6`、层内弃光上下界（双向）、
  计划层余额（重算口径 `BALANCE_TOL = 1e-8`）。
- **边界**：`E ∈ [1200, 10800]`、`c ≤ 833.3333`、`q_dis ≤ 750.0000`、`0 ≤ s' ≤ PV^act·Δt`、`b/q/q_em ≥ 0`、
  两侧功率 ≤ 5000 kW（并网点侧/电池侧四路换算）、`4-3` 的 `i ≤ 36 ⇒ q = b` 与逐层不回溯。
- **恒等式**：`(I2-1d)…(I2-7d)` / `(I3-1d)…(I3-8d)` 的逐日最大残差 + `D_req`/`D_full` 双窗口切片 + 费用分解恒等式 ≤ `1e-6`。
- **AS21/T7 式 tie-break 硬检查**：逐层 `primary_relative_change ≤ 1e-9`、全层 `invariance_passed`、ε 为无量纲相对权重 < 1。
- **正式模式另加**：解析下界、构造上界（无储能可行策略，逐层构造）与**量级带**（交付期 `C_total^act ∈ [3e6, 5e7] 元`、
  日均 `∈ [5e3, 2e5] 元`，防 `Δt` 误乘）。
- **不作硬失败的量（落 `statistics`）**：同充放时段数与电量、`q_em > 0` 且 `c > 0` 的时段数、`Σq_em`、
  收购电峰值、`κ_m` 截断事件数、弃光时段数。

### 5.2 量纲红线

禁止出现 `p·b·Δt`、`α_em·p·q_em·Δt`、`β·p·Δq·Δt`（乘 `Δt` 使费用整体偏 6 倍）；禁止把 `5000 kW` 直接当电量上界
（漏乘 `Δt` 放大可行域 6 倍）。`c ≤ min(833.3333, 5000·Δt/…) = 833.3333`、`q_dis ≤ min(833.3333, 833.3333·0.9) = 750.0000`。

### 5.3 退出码

`0` 成功；`2` 某层 LP 非最优或整链墙钟预算耗尽（写 `solver_status.json`、`feasible_incumbent = false`，**不伪报最优**）；
`3` 附件/模板结构与 accepted 假设不符；`4` 硬检查或工作簿填报残留失败（**仍写出全部产物**便于 sanity 定位）；
`1` 未捕获异常（`code_runtime`）。

---

## 6. 静态检查与小型探针（本动作实测，全部落盘 `runtime/actions/act-be9040ad7b264d3e/evidence/`）

1. **静态检查**：`compileall` exit 0（`compileall_out.txt`）；venv `ruff 0.16.5` 对 **`code/` 与 `evidence/` 两者**
   均 *All checks passed!*（`ruff_out.txt`，exit 0）；`run_prob04.py --help`（两链参数）exit 0（`cli_help_42.txt`、`cli_help_43.txt`）。
   注：`make_task_spec` 内置预检在 PATH 中找不到 ruff（记 `preflight.ruff = unavailable`），其内部只做 `compileall`，两者不矛盾。
2. **输入/模板结构探针**（`probe_prob04_inputs.py` / `_out.json`，**28/28 PASS**）：附件 2/3/4 行列数、日期连续性与前向填充一致性、
   附件 4 与附件 2 同相位、4 个指定日期索引 `78/171/265/354`、两个模板的工作表集合/列标签/六块/`时刻` 前两行、
   `2025-12-31 18:00` 的 `k=7..24` 跨年实证。
3. **预测器探针**（`probe_prob04_predictors.py` / `_out.json` / `_stdout.txt`，**13/13 PASS**）：
   - `D_req`（334 天）：`PF-PERSIST` MAE **0.084326** / MAPE 13.7801% / RMSE 0.123837 / bias −0.000595 /
     P50/P90/P99 = 0.0500/0.2294/0.3773；`PF-DUAL` 0.093387 / 15.2904% / 0.121566 / −0.000328 / 0.0723/0.2065/0.3359；
     `PF-HIST` 0.100231 / 16.3301% / 0.136878 / +0.013161 / 0.0710/0.2411/0.3963；`PF-AR`（ablation）0.080664 / 13.4993% / 0.109836。
   - `PF-PERSIST` 与 `PF-HIST` 的 `D_req` MAE **与假设阶段登记值逐位相同**；`PF-DUAL` 差 **+0.22%**（见 C2）。
   - 选择规则（BT-5，**仅 3 个强制基准参与**）：`PF-PERSIST` 比次优低 **10.7%**（> 1% 不并列）⇒ 选定 `PF-PERSIST`。
   - **信息集边界**：把 `d' ≥ d` 的价格整行置换并缩放后，四个预测器在 `d ∈ {1,2,31,100,200,364}` 的预测
     **逐位不变**（`max_abs_difference = 0.0`）⇒ 无信息集越界。
   - `2025-01-01` 回退为常量中性价 `1.0`（四预测器一致，该日不参与回测）；`κ_0 ≡ 1` 成立；
     `κ_m ∈ [0.681046, 1.354619] ⊂ [0.5, 2.0]`、**截断事件 0**（登记机制已就绪并抽检字段完整）。
4. **结构探针**（`probe_prob04_structure.py` / `_out.json`，**16/16 PASS**，小实例 `T = 4`、探针专用终端固定以消退化）：
   - `4-2` 计划层 `q_em ≡ 0`（`max|q_em| = 0.0`）、计划余额残差 `0.0`；
   - **退化同构 P2**：`b` 逐位差 `0.0`、`q` 差 `1.19e-9`（相对 `9.7e-13`）、`C_total` 差 `5.0e-10`（相对 `5.0e-13`）、`cost_adj = 5.0e-10`、`q_em ≡ 0`；
   - **LP 无损性**：LP `744.7962966687` vs MILP `744.7962962963`，绝对差 `3.72e-7`（相对 `5.0e-10`，LP ≥ MILP）；
     MILP 最优解代回 LP 目标差 `0.0`（见 C9）；
   - **降尺度**：`m=0/6/12/18` 的 `k=1` 前向保持（块首值 = `A_{m,1}`）、`nan_before_release = 0/36/72/108`、
     跨年丢弃 `0/6/12/18`（合计 36）；块能量偏差（插值 vs 分段常数）逐层统计已落盘；
   - 光伏预报误差量化（1 月 30 天）：`m=0` 每 10 分钟 MAE `21.54 kWh`（≈129 kW，相对 ~8%）、29% 时段预报高于实际（支撑 C7）。
5. **34 天端到端探针**（`probe_run_d34_42/`、`probe_run_d34_43/`，`--days 34 --time-limit 60 --max-wall-seconds 1500`）：
   两链均 **exit 0、`checks_failed = []`、`layer_status_max = 0`**。关键数值见 §7.3。
6. **工作簿独立扫描**（`probe_run_d34_scan.py` / `_out.json`，33 项检查）：列标签/行位置/端点/超行残留/`⁝` →
   **`problem_count = 0`、`ALL_PASS = true`**（与 `prob04_io._residual_report` **独立实现**）。
7. **task 规格预演**（`task_spec_dryrun.py` / `.json`）：真实调用 `automm.tasks.make_task_spec` 为**两份 spec** 各构造一次
   （**只构造、不 submit**），`submitted = false`、`tasks_created = 0`。指纹见 §7.2。
8. **哈希清单与路径自检**：`code_and_input_hashes.py` → `code_and_input_hashes.txt`（代码逐文件 + 目录哈希 + 输入 md5 + 全部证据 sha256）；
   `owner_path_check.py` → `path_check_out.txt`（**`checked = 72`、`missing = 0`**）。
9. 所有探针 JSON 通过 `allow_nan = False` 落盘；`NaN/Infinity` 关键字扫描为空；探针脚本本身也通过 `compileall` 与 `ruff`。
10. **owner-side 独立复算**（第二套实现，见 §11）：`owner_indep_42/43`、`owner_bridge_43`、`owner_a2pre`、`owner_predict_check`、`owner_dual_check`。

> **探针纪律**：以上数值**只作接口、口径与结构自检**，**不是交付数值**；正式数值一律以 `computation` 阶段隔离 task
> （supervised worker、独立 `output_directory`、可核验 `run_manifest`）的产物为准。

---

## 7. 交给 `computation` 的 task 规格

### 7.1 两份 task（**必须都提交**：`AGENTS.md` 阶段级强制要求两链各出交付件）

| | 链 `4-2` | 链 `4-3` |
|---|---|---|
| spec 文件 | `code/task_spec.yaml` | `code/task_spec_4-3.yaml` |
| config 文件 | `code/task_config.yaml` | `code/task_config_4-3.yaml`（**不得合并**，见 C11） |
| `output_directory` | `.../results/prob04_v001_f001_4-2_run001` | `.../results/prob04_v001_f001_4-3_run001` |
| 交付件 | `result4-2.xlsx`（三表） | `result4-3.xlsx`（四表） |
| 数据 | `--data2` + `--data4` + `--template42` | 另加 `--data3` + `--template43` |

核心命令（`--output` 必须与 `output_directory` **逐字一致**，`make_task_spec` 强校验）：

```text
.venv/Scripts/python.exe problems/microgrid_2025/prob04/versions/assumption_v001/code/run_prob04.py \
  --chain 4-2|4-3 --data2 data/附件2.xlsx --data4 data/附件4.xlsx [--data3 data/附件3.xlsx] \
  --template42 data/附件5/result4-2.xlsx --template43 data/附件5/result4-3.xlsx \
  --output <对应 output_directory> --days 365 --time-limit 60 --max-wall-seconds 1500
```

- `input_path = data`；`assumption_version = assumption_v001`；`formulation_version = formulation_v001`；`backend = local`；
  `timeout_seconds = 1800`；`seed = null`；`gpu_required = false`；**`worker_launch_mode = supervised`**
  （`config/compute.yaml`；`detached` 在本 DSH 沙箱会被进程树回收）。
- **必须串行**（`max_local_concurrent_tasks = 1`，本机可用内存偏低）；两者均不占 GPU。
- 重跑纪律：若某 task 以 `timed_out`/`interrupted`/非零退出结束，须用**新** `output_directory`（如 `..._run002`）重跑，
  **不得**复用/覆盖既有目录（`code_hash` 改变时 `task_id` 亦随之改变）。

### 7.2 预演指纹（真实调用 `make_task_spec`，只构造未提交）

| | 链 `4-2` | 链 `4-3` |
|---|---|---|
| `task_id` | **`b7c0357c902c9baba412`** | **`95c3e582cff888957496`** |
| `code_hash` | `7fbc9610f5adc85d4ec65acb949f01afa7739a918d2131496b751f2206f1360e` | 同左 |
| `config_hash` | `8e779d8411abc9abdc011c146c8c649f6dde45de6004d7dcd82232bfdb29d2c1` | `2f40e2c804cfcab3cd42a260e4718a66999001debd03b6e7c5d44ccd5b546668` |
| `source_config_hash` | `49790ae0c492ca200e19e0d6dc2fa5decac01bd3a09dd88c4fa40146abd144ed` | `17ce597da4bfe14da88d3fc76c9e389a2f50c42d0d07289a1e92c6951c8964ca` |
| `input_hash` | `4343d799b5830093d7a61d566219e1d2592f5bc39c8b7a9297286fa9e02d9434` | 同左 |
| `preflight` | compileall passed / ruff unavailable（PATH） | 同左 |

> **两链 `task_id` 必须不同**（否则 `runtime/tasks/<task_id>` 互相覆盖、task group 的 `expected_tasks=2` 永不满足）——
> 这正是新增 `task_config_4-3.yaml` 的原因（C11）。若团队改用「单 task 跑两链」，须先确认 `submit_task` 的目录语义。
>
> ⚠️ **本表指纹已于 2026-09-11 作废**：首次 `computation`（task `b7c0357c902c9baba412` / `95c3e582cff888957496`）
> 因 `table1_label_checks` 硬检查失败（详见 **§12**），修复后重登记指纹见 §12.4（`892351beefa2bc5f7804` / `eca261e1d516ab2867d9`）。
> 本表保留为审计轨迹，**不得**再用于提交。

### 7.3 34 天端到端探针实测（接口自检值，**非交付数值**）

| 指标（`probe_mode = true`） | `4-2` | `4-3` |
|---|---|---|
| `C_total^act`（`D_full` 34 天） | 1 883 064.252289 元 | 2 044 809.487213 元 |
| ↳ `C_plan` / `C_adj` / `C_em` | 1 883 064.252289 / **0** / **0** | 1 885 470.573754 / 66 987.904086 / 92 351.009373 |
| `C_total^act`（`D_req` = 3 天） | 133 590.971401 元 | 152 657.686444 元 |
| ↳ `C_plan` / `C_adj` / `C_em`（`D_req`） | 133 590.971401 / 0 / 0 | 137 847.688958 / 2 165.227202 / 12 644.770285 |
| `C_total^fc` / `ΔC_price`（`D_req`） | 118 297.659019 / **+15 293.312382** | 145 589.086046 / **+7 068.600399** |
| `Σq_em`（`D_full` / `D_req`） | **0.0** / **0.0**（定理） | **19 180.411994** / 2 752.456817 |
| `Σb` / `Σq`（`D_full`） | 2 675 480.337091 / 同左 | 2 678 699.849817 / 2 715 703.051299 |
| `Σs'`（`D_full` / `D_req`） | 0.0 / 0.0（见 C6） | 45 145.845316 / 4 787.844970 |
| `E` 端点 | `E_{1/1,0} = 6000` → `E_T = 1200`；`D_req` 内 1200 → 1200 | 同左 |
| 恒等式最大残差（逐日 / 切片） | I1 7.3e−12 / −1.5e−11、I2 1.5e−11 / 0.0、跨日 0.0、状态 2.2e−12、结算 3.4e−13、层余额 2.3e−13 | I1 4.4e−09 / +6.0e−09、I2 4.4e−09 / −6.0e−09、跨日 0.0、状态 4.1e−09、结算 3.4e−13、层余额 2.3e−13 |
| tie-break `max_primary_relative_change`（阈值 1e−9） | **5.000006e−10**，全层通过、`total_shrinks = 0` | **5.000006e−10**，全层通过、`total_shrinks = 0` |
| 提交解来源 | 34 lexicographic / 0 fallback | 136 lexicographic / 0 fallback |
| 退化层数 / 总层数；仍多重最优 | 33/34；34/34 | 135/136；80/136 |
| 统计量 | 同充放 0；`q_em&c>0` 0；弃光 0 时段；`κ_m` 截断 0 | 同充放 **152**；`q_em&c>0` **596**；弃光 1 378 时段；紧急购电 1 173 时段/34 天；`κ_m` 截断 0 |

- `--days 34` 时 `D_req` 只覆盖 2025-02-01…02-03（3 天），故表 1/2/3 的 4 个指定日期与「交付期量级带」
  **不在探针覆盖范围**（探针模式已按规则跳过并在 stdout 显式说明）；**交付期完整 334 天的量级带只能在 365 天正式计算中检验**。
- 探针量级诊断（正式模式才作硬检查）：`4-2` 下界 50 173.68 ≤ 133 590.97 ≤ 构造上界 165 700.86；`4-3` 51 365.71 ≤ 152 657.69 ≤ 180 832.14。
- **`4-3` 探针 3 天的交付期费用高于 `4-2`（152 658 vs 133 591 元）不得据此下结论**：差额同时含
  「价格预报误差的代价 / 光伏预报误差的代价 / 偏差结算制度」三项，须按 formulation §4.3 分项归因（链条级结论留给 `computation` 的全期结果）。

---

## 8. 下游要求（`sanity_check` / `visualization` / `robustness` / `ablation`）

1. **两链必须分别验收**：`result4-2.xlsx`（三表）与 `result4-3.xlsx`（四表）各自的 `output_directory`、`run_manifest`、
   费用分项与判据**必须分别指明是哪条链的结论**（团队阶段级强制要求）；**禁止**用一条链的数值充当另一条链。
2. **不比对逐点解唯一性**：AS21 已在主目标最优面上冻结取点规则（吞吐量最小者），但实测仍有大量层存在
   **同一主目标最优面下的多重最优**（4-2 34/34、4-3 80/136）。sanity 以「约束残差 + 恒等式 + 目标值 + 交付表」为准；
   同 `code_hash` 同输入的重跑必须逐位复现，否则按 `code_runtime` 路由。
3. **`4-3` 的两项统计量（C7/C8）**：`q_em>0 且 c>0`（596/4896）与同充放（152/4896）**只作统计与机制归因**，
   **不得**判为模型失败或 AS16/AS23 违反；归因材料见 `probe_prob04_structure_out.json` 的预报误差量化。
4. **信息集审计（AS07/AS22/H10/H11）**：`run_manifest.layer_inputs` 给出逐层价格与预报指纹、锁定时段与初始状态来源，
   并明确 `future_price_used_in_decision = false`；`series` 区分 `plan_purchase_kwh`（`b`）与 `final_purchase_kwh`（`q`）；
   结算层是 `PV^act` 与 `p^act` 的**唯一**入口；论文/图注/验收脚本**不得**出现「全天电价已知」类表述（`A8-(b)` 派生 ⑤）。
5. **口径引用纪律（承 E6）**：`run_manifest.total_*_kwh` 为 `D_req` 口径且 `total_purchase_kwh` 装 `Σq`（`4-2` 中 `q ≡ b`）；
   stdout 摘要为 `D_full` 口径。任何费用/kWh 引用必须标注窗口与链。
6. **`E` 端点语义**：两个工作簿的 `0:00`/`24:00` 是**计划窗首/末状态**（左端点口径使计划窗为 `0:10 → 24:10`，模板固有相位）；
   本问为**多日滚动切片**（`E_{d,0} = E_{d−1,144}` 随日变化，**不恒为 6000**），须与 prob01 的单日周期显式区分一次（勘误 R1）。
7. **论文必须写入**：题面表 4 的 `2025/3/1` 与三个区间及其数值是**格式示例**，不是本问答案；`4-2` 的紧急购电全零须给**机制说明**
   （定理 + 平衡残差），不能只报空表。
8. **`ablation` 接口**：按 formulation §8.8 与 `AGENTS.md` 的预注册清单在 `ablations/code/` 另建对照
   （`A2-PRE`（本 `code/` 已提供 `--model a2-pre`）、`M3-ter`、`M4-ter`、`PF-ALT`、`κ1`、`D2-B/D2-C`、`M6`、`M8`、
   以及团队预注册的 `S-VAR`/`S-RH`/`S-VAR-RH`/`R-CAP`/`R-KAPPA`/`R-TIE`）；**不得改动本 `code/`**；
   **所有对照模型必须复用 `prob04_model._solve_with_tiebreak` 的 ε 与次目标系数**（否则 `M8 ≡ M1` 的比较失效）。
9. **`ablation` 的必答项**（本动作实测支撑）：
   - `PF-ALT`：`PF-AR` 的 `D_req` MAE **低于** `PF-PERSIST`（C4）⇒ 预测器选择敏感性必须给出 `ΔC_total` 并披露；
   - `ΔC_foresight`：`A2-PRE` 作信息价值上界（§11.4 给出 34 天的方向性实测）；
   - `4-3` 的 `C_adj`/`C_em` 存在 ~1e-4 相对量级的**最优面取点敏感性**（§11.3），须作为已知口径敏感性披露，
     **禁止**用不同 tie-break/求解器设置的结果互相比对（承 `T7-4`/`T7-5`）。
10. **`S-RH` 的登记前置**（formulation §8.8 结转）：其「超 24 h 的光伏预期（附件 2 同季节/同月历史均值，
    第二口径 = 最近 7 天实测）」属**新增假设**，须先按「团队勘误」通道追加到 prob04 的 `assumptions.md`；
    **登记完成前该对照不得跑数**。
11. **`robustness`**：参数扰动（`η`、`E_init`、`E` 界、`α_em`、`β_def/β_over`、降尺度规则、负载/光伏扰动）
    与 `κ_m` 截断敏感性，**判据必须分别指明链**；与 `ablation` 的数值不得互相替代。

---

## 9. 遗留风险与已知限制

- **探针窗 ≠ 交付窗**：`--days 34` 只验证接口与求解路径，跳过解析界/量级带四项硬检查，`D_req` 仅 3 天，
  且表 1/2/3 的 4 个指定日期不在窗内（表结构为空）；**表 1 的 144 时段标签分支只能由 365 天结果覆盖**。
- **`4-3` 的解析下界较松**（C5）：`p_min·Σb` 只用于排除「乘 `Δt`」类硬错误，**不得**当作「费用应接近下界」的判据。
- **`4-2` 的弃光在探针窗为 0**（C6）：全年窗口才可能出现非零，论文不得写成「模型恒无弃光」。
- **`4-3` 的最优面取点敏感性**（§11.3）：两套独立实现在 34 天全窗的 `C_total` 相对差 `8.8e−5`（`C_em` 差异为主），
  但 `D_req` 3 天窗只差 `1.4e−3` 元；须作为**已知口径敏感性**披露，不得当作实现缺陷。
- **`κ_m` 截断在探针窗为 0**：全年是否触发须由正式计算落盘（机制已就绪，触发即逐个登记）。
- **模板渲染行维度**（C12）：openpyxl 清空后仍保留行维度，下游扫描必须按**非空行**判定。
- **`S-VAR`/`S-RH` 未实现**：按 `A8-(b)` 派生 ④ 与 `AS12`，它们**只进 `ablation`**；本动作未做（也**不得**做主口径）。
- **`4-2` 的 `C^fc` 不是真实支出**：`ΔC_price` 的符号**不可预先断言**（formulation §5-P3）；
  探针窗两条链的 `ΔC_price` 均为正，但**不得**推广为「误差代价恒正」。
- 结转技术债（不在本动作处理）：`prob01/assumption_v003/version.yaml` 的 AS08 措辞（C3/E3）、
  「5000 kW 作用侧」的文献缺口（`D10`）、上游 `shared/problem_understanding.md` §7 仍把 A8 记为「待裁定」（C4-1）、
  prob04 文献池 24 条均未逐篇阅读正文（引用只支撑框架级/机制级）。
- `run_manifest.json` 的 `code_sha256.__code_dir__` 由脚本自算（与 harness `hash_path` 算法不同）；
  追踪与 task ID 一律以 harness 值 **`7fbc9610…`** 为准。

---

## 10. 未越界声明

- 未修改 `assumptions.md`、`version.yaml`、`formulations/` 任何文件、`global_symbols.yaml`、`citations.yaml`、
  `question_manifest.yaml`、`runtime/workflow_state.json`、`data/`、`request/`，以及 `prob01/`、`prob02/`、`prob03/` 的任何产物。
- **未创建/提交任何 task**（`task_spec_dryrun.json` 记 `submitted = false`、`tasks_created = 0`；未调用 `submit_task`、
  未调用 `scripts/compute_dispatcher.py submit`）；**未写 `results/`**（该目录仍为空）；**未运行 365 天计算**、
  未跑 bootstrap/Monte Carlo/场景随机/鲁棒。
- 本动作只在 `prob04/versions/assumption_v001/code/`、`implementation.md` 与本 action 的 `evidence/` 内改动；
  探针一律只读 `data/`；两个模板工作簿只读打开。
- 未安装/升级任何依赖；未调用 `nvidia-smi`；未硬编码 `cuda:0`。
- 未把 `α_em = 5`、`β_def/β_over`、`κ_m` 截断区间、附件 4 价格结构与预测误差量级、`D9-B`、填报口径、
  `5000 kW` 作用侧、`4-2` 的 `q_em ≡ 0` 包装为文献支持（承 prob03 勘误 E4）。
- 交付件为**两份**：`result4-2.xlsx` 与 `result4-3.xlsx`，各自独立 `output_directory`；**未**把 prob02/prob03 的
  `result2.xlsx`/`result3.xlsx` 当作 prob04 的结果或模板写入。

---

## 11. owner-side 独立复算（第二套实现，**不进入交付口径**）

> 为给「同一模型、两种实现」提供独立证据，本 Agent 另写了一套**独立实现**与解析探针，落在
> `evidence/owner_*`（说明见 `owner_xcheck_NOTE.md`）。它们**不是交付代码**，只作交叉验证。

### 11.1 与交付实现的数值对账（`--days 34`，同一数据、同一口径）

| 指标 | `code/`（交付实现） | owner 独立实现 | 绝对差 | 相对差 |
|---|---|---|---|---|
| `4-2` `C_total^act`（34 天） | 1 883 064.252289 | 1 883 064.216467 | 0.036 元 | **1.9e−8** |
| `4-2` `C_total^act`（`D_req` 3 天） | 133 590.971401 | 133 590.970926 | 4.8e−4 元 | 3.6e−9 |
| `4-2` `Σq_em` | 0.0 | 0.0 | 0 | — |
| `4-3` `C_total^act`（34 天） | 2 044 809.487213 | 2 044 629.544856 | 179.94 元 | 8.8e−5 |
| ↳ `C_plan` | 1 885 470.573754 | 1 885 470.535733 | 0.038 元 | 2.0e−8 |
| ↳ `C_adj` | 66 987.904086 | 66 987.890698 | 0.013 元 | 2.0e−7 |
| ↳ `C_em` | 92 351.009373 | 92 171.118425 | 179.89 元 | 1.9e−3（见 §11.3） |
| `4-3` `C_total^act`（`D_req` 3 天） | 152 657.686444 | 152 657.685081 | 1.4e−3 元 | **8.9e−9** |
| `4-3` `Σq_em`（34 天 / `D_req`） | 19 180.412 / 2 752.456817 | 19 160.364 / 2 752.456817 | 20.05 kWh / 0 | 1.0e−3 / 0 |

- 两套实现的**交付窗（`D_req`）**、`C_plan`、`Σq_em(4-2)`、`E` 端点与全部恒等式残差一致到 1e−3 元以内。
- owner 侧独立复算的逐日最大残差：结算平衡 `3.4e−13`、计划层余额 `3.4e−13`、`i ≤ 36 ⇒ q = b` 差 `0.0`、
  `κ_m` 截断 0、`κ_m ∈ [0.739, 1.359]`。

### 11.2 退化同构命题 P2（formulation §4.3 (AT-1) / §5-P2）

`owner_bridge_43.py` 在 **34 天全窗**上令 `Π_m ≡ PV^act`、`κ_m ≡ 1`、`β_def = β_over = 1` 后复算 4-3：

```
4-3(BRIDGE) C_total^act(34 天) = 1 883 064.216467199
4-2 链      C_total^act(34 天) = 1 883 064.216466558
绝对差 6.41e−7 元 ⇒ 相对差 3.40e−13；C_adj = 1.07e−7、C_em = 5.36e−7；max|q − b| = 8.22e−9
```

⇒ **P2 的退化同构在链级全窗上成立**（与 `code/` 结构探针的小实例结果 `5.0e−13` 一致）。

### 11.3 `4-3` 全窗差异的归因（**已知口径敏感性，不是缺陷**）

`C_plan` 与 `C_adj` 两套实现几乎逐位相同（≤ 0.04 元），差异集中在 `C_em`（179.89 元 / 1.9e−3）：
调整层主目标在「复现计划轨迹」处取 0，**主目标最优面下 `q` 的取点不被 AS21 的次目标 `min Σ(c+q_dis)` 约束**，
故不同最优面取点会改变结算层 `Σq_em`（20.05 kWh / 19 180 kWh = 0.1%）——与 prob03 实测的 tie-break 敏感性同源
（prob03 `T7-6` 约 `1e−4` 相对量级）。**交付窗 3 天只差 1.4e−3 元**，说明该敏感性主要落在预热/早期窗口。
`sanity` 与 `ablation` 必须把它登记为**已知口径敏感性**，禁止用不同 tie-break 设置的结果互相比对（承 `T7-4`/`T7-5`）。

### 11.4 `A2-PRE` 完全预知下界锚点（formulation §4.2 / §5-L6 / 决策点 D8-A）

```
A2-PRE 下界（单一长时域 LP，34 天，实际价 + 实际光伏、无 q_em）= 1 844 344.770235 元
4-2 逐日递推链 C_plan^act（34 天）                            = 1 883 064.216467 元
差额 +38 719.446232 元（+2.056%） ⇒ 锚点方向成立（C^act ≥ C^pre）、未出现方向反转
```

⇒ `--model a2-pre` 可直接作为 `sanity` 的硬下界门与 `ablation` 的 `ΔC_foresight` 输入（本动作只做 34 天探针）。

### 11.5 预测器口径的独立复核

`owner_predict_check.py` 独立复算：`PF-PERSIST` `D_req` MAE `0.084326`、`PF-HIST` `0.100231`
**与假设阶段登记值逐位相同**；`PF-DUAL` `0.093387`（登记 `0.093183`，+0.22%，见 C2）。
`owner_dual_check.py` 的 8 个变体扫描（形状取全历史 vs 最近 W 日 × W ∈ {5,6,7,8}）显示登记值不落在任一
字面变体上（最接近者 `W=7 形状=全历史` 为 `0.093387`），故该差异判为**假设阶段探针的实现细节差**，不影响主口径选择。

---

## 12. 首次 `computation` 失败（`table1_label_checks`）与修复登记

> 动作 `act-372994bf952044b0`（`route_compute_failure`，agent = `implementation-agent`，2026-09-11）。
> 本动作**在 `code/` 内修复**并重登记 spec，**未创建 task、未写 `results/`、未运行 365 天正式计算**。

### 12.1 失败事实

| | 链 `4-2` | 链 `4-3` |
|---|---|---|
| `task_id`（作废） | `b7c0357c902c9baba412` | `95c3e582cff888957496` |
| `output_directory`（作废，结果保留为审计负对照） | `.../results/prob04_v001_f001_4-2_run001` | `.../results/prob04_v001_f001_4-3_run001` |
| `status` / `returncode` | `failed` / **4** | `failed` / **4** |
| `failure_class` / `failure_type` | `code_runtime` / `process_exit` | 同左 |
| `feasible_incumbent` | `true` | `true` |
| stdout 末行 | `失败检查=['table1_label_checks']` | 同左 |

两条链的 **LP 全部求解成功**（`solver_status.status=0`、`layer_status_max=0`、恒等式残差 1e−11 / 1e−8 量级、
AS21 不变性 5.000e−10 ≤ 1e−9），失败**只**来自 `tables.json` 的表 1 位置口径硬检查（`exit_code=4` 语义）。

### 12.2 根因（已由只读探针逐条证实）

`prob04_io._read_power_sheet` 与 `read_attachment4_price` 用 `str(openpyxl 原始表头值)` 构造 `time_labels`，
而附件 2/附件 4 的表头时刻在 `openpyxl` 中是 **`datetime.time`**，其 `str()` 带秒：

```
datetime.time(10, 0)  →  str() = "10:00:00"      # 修复前（错误）
datetime.time(10, 0)  →  H:MM  = "10:00"         # AS01 左端点口径 / 模板列标签风格（正确）
```

`run_prob04.build_tables` 的表 1 判据是 `attachment_label == slot_name.split("-")[0]`（`"10:00-10:10"` → `"10:00"`）
且 `template_label == slot_name`；`"10:00:00" != "10:00"`，故 **4 个指定日期 × 6 个时段 = 24/24 全部 `label_matches=false`**，
`table1_label_checks_passed=false` → 追加 `failed` → 退出码 4。**数值与模型无任何缺陷**（表 1 的 `final_purchase_kwh`
与行位置 60/72/84/96/108/120 均正确）。

旁证（只读探针 `probe_label_rootcause.py`）：附件 1 表头是 `str`（故 prob01/02/03 用附件 1 时得 `"10:00"`、检查通过），
附件 2/附件 4 表头是 `datetime.time`（故只有本问、只有走附件 2/4 标签路径的实现暴露该缺陷）。

### 12.3 修复（唯一代码改动；不改任何目标/约束/界/tie-break/解）

1. `prob04_io._clock_label` 由 `value.strftime("%H:%M")` 改为 `f"{value.hour}:{value.minute:02d}"`，
   使实现与其 docstring 的 `H:MM` 及 `AS01` 左端点/模板列标签风格（小时不补零）一致；
2. `_read_power_sheet`（附件 2 两个工作表）与 `read_attachment4_price`（附件 4）的表头构造改为
   `"" if item is None else _clock_label(item)`，即**时刻列统一规范为 `H:MM`**。
   字符串列（如末列 `"0:00+1"`）原样保留，日期列首表头 `"日期\时间"` 不受影响。

修复后标签（实测）：位 1 `0:10`、位 60 `10:00`、位 72 `12:00`、位 84 `14:00`、位 96 `16:00`、
位 108 `18:00`、位 120 `20:00`、位 144 `0:00+1`；附件 4 与附件 2 的 `time_labels` **逐列相等**（相位核对仍成立）。

### 12.4 修复验证与重登记指纹

| 检查 | 结果 | 证据 |
|---|---|---|
| 表 1 位置口径（**生产函数** `build_tables`，4 日期 × 6 时段） | `4-2` **24/24 通过**、`4-3` **24/24 通过** | `probe_table1_label_fix_out.json`（`verdict=PASS`） |
| 负对照：逐字复现修复前标签（`str(datetime.time)`） | **`passed=false`**（两链一致）| 同上（`negative_control_legacy_labels_passed=false`，样例 `10:00:00`） |
| 34 天端到端回归（两链，`exit 0`、`checks_failed=[]`） | `4-2` C_total 1 883 064.2523 元、`4-3` 2 044 809.4872 元，**与修复前逐位相同** | `probe_run_d34_42_afterfix_stdout.txt` / `probe_run_d34_43_afterfix_stdout.txt` |
| 修复前后产物逐字段数值对比（忽略墙钟耗时） | `solver_status/solution/tables/tiebreak_audit/forecast_backtest` **0 处超 1e−9 差异** | `cmp_d34_afterfix_vs_prior_out.json`（`verdict=PASS`） |
| `compileall` / venv `ruff` / `--help` | exit 0 / all checks passed / exit 0 | `compileall_out.txt`、`ruff_out.txt`、`cli_help.txt` |

重登记指纹（真实调用 `make_task_spec`，**只构造未提交**）：

| | 链 `4-2` | 链 `4-3` |
|---|---|---|
| `task_id`（新） | **`892351beefa2bc5f7804`** | **`eca261e1d516ab2867d9`** |
| `code_hash` | `e50ae1323cd83ec5ca058a134ad12064d2d1ae5a5ac9420de07c0e337bd6bb64` | 同左 |
| `config_hash` | `8e779d8411abc9abdc011c146c8c649f6dde45de6004d7dcd82232bfdb29d2c1` | `2f40e2c804cfcab3cd42a260e4718a66999001debd03b6e7c5d44ccd5b546668` |
| `source_config_hash` | `49790ae0c492ca200e19e0d6dc2fa5decac01bd3a09dd88c4fa40146abd144ed` | `17ce597da4bfe14da88d3fc76c9e389a2f50c42d0d07289a1e92c6951c8964ca` |
| `input_hash` | `4343d799b5830093d7a61d566219e1d2592f5bc39c8b7a9297286fa9e02d9434`（**未变**） | 同左 |
| `output_directory`（新） | `.../results/prob04_v001_f001_4-2_run002`（**提交前不存在**） | `.../results/prob04_v001_f001_4-3_run002` |
| `preflight` | compileall passed / ruff unavailable（PATH，既有登记项） | 同左 |

证据：`task_spec_dryrun_afterfix.json`（`no_task_created=true`、`distinct_task_ids=true`、
`output_equals_command_output=true`）。

### 12.5 重跑纪律与探针盲区（**下游必读**）

1. `..._run001`（两条链）**作废但保留**为审计负对照，**不得复用/覆盖**；重跑必须用 `..._run002`
   （`submit_task` 亦强制：强制重跑必须换 `output_directory`）。
2. 重跑须由 `computation` 阶段的 `resource-manager` 用**新的 task group（`expected_tasks=2`）**提交两份新 spec
   （旧 group `grp-edc544938859148c` 已消费）；两链仍**串行**（`max_local_concurrent_tasks=1`）。
3. ⚠️ **34 天探针（`--days 34`）在结构上无法覆盖表 1 标签检查**：`build_tables` 对 `day_index >= days` 的指定日期
   `continue`，4 个指定日期（日序 78/171/265/354）全部被跳过 ⇒ `table1_label_checks_passed` 恒为 trivially true、
   `table1` 为空对象（实测两链 `tables.json` 修复前后 **byte-identical**）。这正是首轮实现未能暴露本缺陷的原因。
   **因此**：本修复的验收证据是 §12.4 的**专用标签探针**（真实附件 + 真实模板 + 生产函数），
   而 34 天端到端探针只用于证明「修复不改变任何数值」；`sanity_check` 必须以 **365 天正式产物**复核
   表 1（含 `attachment_timestamp` 为左端点、`template_label` 为完整区间）。
4. 本修复**不触碰** formulation / assumptions / `data/`，不新增或修改任何口径；`AS21`、`A8-(b)`、
   `D9-B`、`E1`（`q_dis ≤ 750.00` / `c ≤ 833.33`）、`D10`（5000 kW 作用侧）与团队裁定 `R-1`/`R-2` 全部不变。
