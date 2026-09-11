# prob04 sanity 报告 · Level 6（鲁棒性与敏感性独立复核）

- 归属：`microgrid_2025` / `prob04`（波动电价下重算问题 2 与问题 3；交付 `result4-2.xlsx` 与 `result4-3.xlsx` 两个文件）
- 阶段：`sanity_check`，Level 6（`config/sanity_check.yaml: level_6.trigger = after_robustness`）
- 收尾动作：`act-cb24258ea2be418a`（负责人：sanity-checker；策略 P3 / action=run_agent / level=level_6）
- 复核对象（**只读**）：
  - 链 `4-2`：`robustness/results/prob04_v001_robust_4-2_run001/`，task `953eeb1e0b004171cad9`
  - 链 `4-3`：`robustness/results/prob04_v001_robust_4-3_run001/`，task `5713b0a24eedeac9f000`
  - 预注册方案：`robustness/plan.md`（跑数前冻结）；阶段报告：`robustness/report.md`
- 前置 L1–L4：`sanity_report.md` §1–§8（`PASS_WITH_WARNING`，`failure_type = null`），本报告**不改写**该结论
- 本动作**不**：运行完整数据集、新建 task、启动/终止 worker、执行 `reconcile`/`list`/`RESUME`、
  写 `results/prob04_v001_f001_*`、触碰 `data/附件5/`、修改 accepted 代码/`assumptions.md`/`formulation_v001`/`plan.md`

> **范围声明**：Level 6 的触发条件是 `robustness` 完成；`ablation`（`S-VAR`/`S-RH`/`C-ANCHOR-P03` 等）在本动作时
> 仍为 `pending`，**不在本 L6 结论的覆盖范围内**，由后续 `ablation` 阶段独立验收。本结论**不得**替代 `ablation`。

---

## 0. 与团队裁定/勘误的接口（强制项，先读后验）

本动作先读 `assumption_v001/assumptions.md` 文末「团队裁定（R-1/R-2）」「团队勘误 E-F2–E-F5」「团队勘误 E-F6–E-F9」，
以及根 `AGENTS.md` 的 prob04 两链结构与 `A8-(b)` 六条派生口径。效力高于 `plan.md` 默认做法的条目及本动作处置：

| 团队口径 | 本动作处置 |
|---|---|
| **E-F9**（4-3 `S4` 未过 ⇒ 稳定档 =「条件稳定（需给出适用边界）」；**禁止**调参/放宽判据使其"通过"） | 独立复算确认 `S4` FAIL、`failed_criteria=["S4"]`、`stability_grade=条件稳定（需给出适用边界）`；报告已给适用边界。**未**发现任何事后放宽 |
| **E-F6**（`supervised` + `reconcile_tasks()` 会误杀运行中任务；有 `running` 时禁止 `RESUME`/`reconcile`） | 本动作**未**执行 `RESUME`/`reconcile`/`list`；确认 4-3 task 终态为 `succeeded/rc=0`，`status.json` 仅残留过期 `message`（见 §5） |
| **E-F7**（5 条空转 `append_ledger` 不得作为鲁棒性证据） | 本报告**未**引用 `act-6e395f67061f4990`/`act-458dccfaed454c5b`/`act-6141343749294f00`/`act-47b6bc4fe0b44c88`/`act-0a5a93765e2141e7` 作为任何证据 |
| **E-F8**（`trajectories/` 为抽样保存，不得据份数判缺失） | 实测 `4-2 = 62`、`4-3 = 70`，与 E-F8 登记一致；`raw_samples.jsonl` 为 162/198 行 |
| **T7-4**（预注册判据不得为凑结论改判据/统计量/口径；反例如实登记） | 复核 K7（`max` 口径两链反例）、K8（部分反例）均已如实登记 + 机制 + 适用边界；`plan.md` 修改时间**早于**任何结果文件 |
| **CF-10**（S2 机制带与 S4 同 σ 档比较的先导校准，跑数前冻结） | `plan.md` 与产物 `criteria` 规则文本均含冻结措辞；先导探针证据仍在 `runtime/actions/act-6d9ecf00777a4b96/evidence/`（含 34 天全矩阵的 `criteria_cf10_recheck_out.json`） |
| **E-F5**（预测器报告纪律：成对给出 `MAE/MAPE/P50` 与 `RMSE/P90/P99`，禁止据单一指标宣称优劣） | 两链 `forecast_backtest.json` 指标齐全（7 项）；报告 §4 未据单一指标宣称预测器优劣 |

---

## 1. 独立复算的总量与方法

本动作自建**只读**探针 `runtime/actions/act-cb24258ea2be418a/evidence/probe_l6_verify.py`，
对两链权威产物（`summary.json`/`sensitivity.json`/`baseline_check.json`/`run_manifest.json`/
`solver_status.json`/`raw_samples.jsonl`/`trajectories/`/`figures/`）、`runtime/tasks/<id>/status.json`、
accepted 交付锚点 `results/prob04_v001_f001_<链>_run002/solution.json` 与 `result<链>.xlsx`、
模板 `data/附件5/result<链>.xlsx`、`robustness/plan.md`/`report.md` mtime、`figures.yaml` 做**第一手重算**。

- **结果：`270/270 PASS`，`0 FAIL`**（输出 `evidence/probe_l6_verify_out.txt`）。
- 另用通用脚本在**逐字节副本**上跑自动 L1/L2-有限性扫描（副本位于
  `runtime/actions/act-cb24258ea2be418a/evidence/auto_scope_l6/4-2`、`.../4-3`，**不写 accepted 目录**）：
  `144` 个数值文件、`0 NaN / 0 Inf`、`failures = []`、`automated_status = PASS_WITH_WARNING`
  （输出 `evidence/machine_sanity_l6_autocheck.json`，其内 144 条路径全部可回溯、无悬空）。

---

## 2. Level 1（输入/追踪/完整性，L6 前置）：PASS

| 项 | `4-2` | `4-3` |
|---|---|---|
| task 终态 | `953eeb1e0b004171cad9`：`succeeded` / `rc=0` / `attempt=1` / `supervised` | `5713b0a24eedeac9f000`：`succeeded` / `rc=0` / `attempt=1` / `supervised` |
| 产物齐备 | 7 件（`raw_samples.jsonl`/`summary`/`sensitivity`/`baseline_check`/`solver_status`/`run_manifest`/`forecast_backtest`）+ `trajectories/` + `figures/` | 同左 |
| 情景数 | `scenario_count = 162`，`solved = 162`，`failed = 0` | `scenario_count = 198`，`solved = 195`，`failed = 3` |
| `raw_samples.jsonl` | 162 行（每情景一条） | 198 行 |
| `trajectories/` | 62 份（抽样，E-F8） | 70 份（抽样，E-F8） |
| `figures/*.png` | 7 张，文件名带链号 `_42_` | 7 张，文件名带链号 `_43_` |
| `probe_mode` | `false` | `false` |
| `budget_exceeded` | `false` | `false` |
| 独立输出目录 | `..._robust_4-2_run001`（与 4-3 不同） | `..._robust_4-3_run001` |
| `code_sha256` | `a2493790…f91a499`，与磁盘 `robustness/code/robustness_prob04.py` 逐位一致 | 同左（同一实验代码） |
| accepted 代码指纹 | `prob04_io/prob04_model/prob04_predict/run_prob04` 四个 sha256 与 `code/` 磁盘逐位一致 | 同左 |
| 输入 md5 | 附件2 `bb3e493f…`、附件4 `cf876237…`；**无附件 3**（`AS18`） | 附件2/附件4 同上 + 附件3 `e8dfee65…` |
| `forecast_backtest.json` | 两链 sha256 **逐位相同**（同一预测器与回测协议，`AS13`） | 同左 |

时间序：`plan.md` mtime **早于**两链任一结果文件；`report.md` mtime **晚于**最后一个结果文件；
`assumptions.md`（团队勘误 E-F6–E-F9 追加）早于 `report.md`。⇒ **预注册先于跑数、报告后于跑数**。

`robustness/` 与 `results/` 下**无任何 `.xlsx`**；`results/prob04_v001_f001_<链>_run002/` 保持既有
（无 `run003`），模板 `data/附件5/result<链>.xlsx` 的 md5 仍为 `b878ce2b…` / `75be588e…`
（**≠** 两链新写工作簿 md5 `3df5cd3c…` / `7397029f…`）。

**结论：L1 PASS** —— 追踪链完整、两链隔离、代码/输入指纹可复算、不存在交付值污染。

---

## 3. Level 2/3/6-数值：预注册判据 S1–S7 与基线闸门（独立复算）

### 3.1 基线闸门（只读对账，不反向写入）

| 项 | `4-2` | `4-3` |
|---|---|---|
| `baseline_check.json` | `passed = true`，`worst_relative_diff = 0.0`，全部条目 `reference == value` | 同左 |
| 交付期 `C_total`（robust 基线） | `13,006,411.041148` = accepted `run002/solution.json` **逐位相等** | `15,289,050.714738` = 锚点**逐位相等** |
| 全期目标 | `14,755,884.322036` = 锚点**逐位相等** | `17,181,202.515506` = 锚点**逐位相等** |

⇒ 两链在**未扰动**情景下逐位复现 accepted 主口径；`EXIT_BASELINE_GATE_FAILED` 未触发。

### 3.2 S1–S7（分链；阈值取自 `plan.md` §3 冻结文本，本动作未改）

| 判据 | `4-2` | `4-3` |
|---|---|---|
| `S1` 可行性 | **PASS**：受判 `judged = 139`（独立重算 139）、`feasible_rate = 1.0`、`identity_failed = []` | **PASS**：受判 `judged = 170`（独立重算 170）、`feasible_rate = 1.0`、`identity_failed = []` |
| `S2` `q_em` 机制 | **PASS**：受判样本 `max|Σq_em| ≤ 1e-9`、`days_with_emergency = 0` | **PASS**：`Σq_em ∈ [404,201.44, 837,192.51]` 落在宽带 `[102,613.50, 1,641,815.98]`（`[0.25×,4×]`），`out_of_band = []`；窄带越界样本**逐条披露** |
| `S3` OAT 方向不反转 | **PASS**：8 个 OAT 组、有方向组 `reversals = []` | **PASS**：10 个组、有方向组 `reversals = []` |
| `S4` 输入噪声 | **PASS**：4 族 × 25 = 100 样本，逐族统计独立重算与落盘一致（见 §3.3） | **FAIL**：5 族 × 25 = 125 样本；`noise_white_10` 族均值 `+10.5919%` > 预注册 5% |
| `S5` 求解器 | **PASS**：三设置全可行；全期口径 `1.25189e-4`、交付期口径 `4.969e-6`（均 ≤ 1%） | **PASS**：三设置全可行；全期口径 `4.36256e-4`、交付期口径 `6.10152e-4`（均 ≤ 1%） |
| `S6` 结构情景 | **PASS**：`buy_cap` 12/12 全域可行；`terminal_e_6000` 有数值（`13,008,590.707803`，`+0.0168%`） | **PASS**：`buy_cap` 不可行 `[3500,4000,4500] kW`、可行 `≥5000 kW`、分界 `(4500,5000]`；`terminal_e_6000` = `15,292,320.214739`（`+0.0214%`） |
| `S7` 预测机制 | **PASS**：`PF-DUAL`/`PF-HIST` 跑通，7 项指标齐全 | **PASS**：`PF-DUAL`/`PF-HIST`/`kappa_frozen_1` 跑通，7 项指标齐全 |

分级（`plan.md` §3 冻结规则）：`4-2` 全 PASS ⇒ **稳定**；`4-3` 恰 1 项非 PASS 且 `S1` PASS ⇒ **条件稳定（需给出适用边界）**。
独立验证「分级 = f(非 PASS 项数, S1)」的映射在产物 `stability_grade` 上逐链成立。

### 3.3 输入噪声族统计的独立重算（交付期 `C_total`，`n = 25`/族）

| 链 | 族 | 独立重算均值（元） | 样本 `std`（ddof=1） | `CI95` 半宽相对（1.96） | `max|z|` | 族均值相对基线 |
|---|---|---|---|---|---|---|---|
| `4-2` | `noise_white_5` | 13,018,406.155519 | 8,517.765992 | 0.00025648 | 1.9731 | +0.0922% |
| `4-2` | `noise_white_10` | 13,048,181.446324 | 17,121.160431 | 0.00051436 | 2.0116 | +0.3212% |
| `4-2` | `noise_day_5` | 13,022,289.961922 | 82,762.181344 | 0.00249133 | 2.0082 | +0.1221% |
| `4-2` | `noise_joint_day_5` | 13,076,598.592175 | 92,727.328603 | 0.00277971 | 1.9354 | +0.5396% |
| `4-3` | `noise_white_5` | 15,861,642.262613 | 17,474.767071 | 0.00043187 | 2.2941 | +3.7451% |
| `4-3` | **`noise_white_10`** | 16,908,452.788088 | 35,102.191668 | 0.00081380 | 2.2112 | **+10.5919%（越界）** |
| `4-3` | `noise_day_5` | 15,850,391.964695 | 132,922.671128 | 0.00328734 | 2.5429 | +3.6715% |
| `4-3` | `noise_joint_day_5` | 15,906,188.168431 | 141,695.602054 | 0.00349202 | 2.1824 | +4.0365% |
| `4-3` | `noise_pvfc_5` | 15,816,519.292038 | 12,934.913521 | 0.00032058 | 2.4332 | +3.4500% |

- 每族的 `mean` / `std`(ddof=1) / `CI95` 半宽（代码口径为 1.96 倍标准误，见 `robustness_prob04.py:1171`）/
  `max|z|` / 族均值相对基线**逐项与 `sensitivity.json` 一致**（容差 1e-9）；`std_rel ≤ 5%`、`CI95 ≤ 5%`、
  `max|z| ≤ 4`、`failures = []` 全部达标。
- σ=5% 档内族间均值差（代码归一化基准 = 各档族均值的均值，`robustness_prob04.py:1541`）：
  `4-2 = 0.4463%`、`4-3 = 0.5654%`，均 ≤ 3%。
- **唯一越界**是 `4-3` 的 `noise_white_10` 族均值 `+10.5919% > 5%`，与 E-F9 登记一致；机制为
  `Σq_em` 的 `max(0,·)` 泛函在 σ=10% 下系统性抬高紧急购电（凸性），属**结构性**而非实现缺陷
  （`identity_failed = 0`、受判样本全部可行）。

### 3.4 求解器、买电上限与 `κ_m` 截断

- **求解器（S5）**：`highs-ds`/`highs-ipm`/`presolve=False` 三设置**两链全部可行**。链级最大口径敏感性：
  全期目标 `4-2 = 1.25189e-4`、`4-3 = 4.36256e-4`；交付期 `4-2 = 4.969e-6`、`4-3 = 6.10152e-4`。
  两类口径均 ≤ 1%，与 `T7-6`（prob03 实测 ≈1e-4）同量级 ⇒ `S5` PASS（口径标注问题见 §6 `L6-W1`）。
- **买电上限（S6）**：由 `raw_samples.jsonl` 独立重算的可行/不可行集合与 `structural_findings` 逐项一致；
  `4-2` 全域可行，`4-3` 分界 `(4500, 5000] kW`。两链分界**各自实测**，未引用 prob02/prob03（`CF-7`）。
- **`κ_m` 截断**：`kappa_clip_events_total = 196`（仅 `4-3`）**全部来自刻意收紧的 `kappa_bounds_tight`（[0.75,1.25]）**；
  登记界 `[0.5,2.0]` 与放宽界 `[0.25,4.0]` 均 **0 次**截断，且 `kappa_bounds_tight` 情景费用相对差为 `0.0`；
  `kappa_frozen_1`（`κ_m ≡ 1`）与基线费用**逐位相同**。⇒ 截断机制在登记口径下未被触发，且在成本上非紧。

### 3.5 K7/K8 反例的独立重算（`T7-4` 合规性）

- **K7（价格预报误差是否为第一不确定性源）**：`max` 口径下**两链均不成立**（如实登记反例）——
  价格类最大 `|ΔC_total|/C = 10.0000%`（`price_level`，独立重算）< `eta_both` 的 `13.3453%`（4-2）/ `11.7004%`（4-3）；
  预测机制族仅 `0.2261%` / `0.1711%`，价格白噪声 σ=10% 仅 `1.9724%` / `1.7593%`；
  `mean` 口径成立（input 均值 `2.8677% / 7.6289%` > param 均值 `1.5532% / 1.3740%`）。
- **K8（两链同号且 4-3 不低敏）**：「同号」在**排除 4-2 交付期空参数族**后成立——
  共同情景 44 个，其中 `alpha_em_*(6)` 与 `e_init_*(6)` 共 12 个在 `4-2` 上 `Δ ≡ 0`（`R4-4` 已登记 α_em 空参数、
  e_init 交付期零响应），属 **vacuous**、不构成符号冲突；其余 32 个共同情景**符号 32/32 一致**。
  「`4-3` 不低于 `4-2`」仅在 `price_level` 与 `pv_act_noise` 族成立，在价格噪声/负载/预测器/设备参数族**不成立**
  （如实登记 `R4-2`）；`pv_act_noise_w10` 上 `4-3` 为 `4-2` 的 **64.5×**（`10.2238%` vs `0.1584%`）。

⇒ K7/K8 的反例**已登记、已给机制、已给适用边界，且未修改判据/统计量/口径**，符合 `T7-4` 与 E-F9 的披露义务。

---

## 4. Level 6 判定本体：robustness 设计是否充分、结论是否依赖脆弱参数

### 4.1 适用性与覆盖（不得 returning `skipped`）

- 阶段为 `config/workflow.yaml: mandatory_stages`；`question_manifest` 记
  `optional_stages.robustness.decision = completed`、`artifacts.robustness = true`，**未** `skipped`。
- 五类适用扰动**全部产出数值**：参数 OAT（`4-2` 34 / `4-3` 40）、输入扰动（8 / 12）、预测机制（2 / 3）、
  求解器压力（3 / 3）、结构情景（13 / 13），另加输入噪声（4×25 / 5×25 ⇒ **100 / 125 次**，满足「随机实验 ≥ 100 次」）。
- 不适用类别**逐条给出理由**并登记：静置损耗/自放电（`AS23`，改写状态转移属建模口径变更）、随机初始化
  （确定性 LP 无随机源）、Sobol/Morris（无输入分布证据，`AS12`）、「价格预报误差缩放因子」类
  （会使决策价依赖当天实际价，违反 `A8-(b)` 派生⑤，**禁止**）。实测两链情景清单中**无** `self_discharge`/`AS23` 情景
  ⇒ 执行与 §0/§1.8 的「不做」一致。
- 边界纪律成立：`S-VAR`/`S-RH`/`C-ANCHOR-P03`/`A2-PRE`/`PF-AR` 等 `ablation` 项**未**在本阶段重跑
  （情景名扫描为 0 命中）；robustness 图件**未**登记为交付图表（`figures.yaml` 全文无 `robust`）。

### 4.2 结论稳定性（分链，必须分别给出，不得只报一条链）

- **`4-2`：稳定。** 主结论（费用量级、`q^em ≡ 0`、参数方向、可行率）在五类扰动下均不反转；
  对**价格预报误差不敏感**（预测器替换 `0.2261%`、价格白噪声 σ=10% `1.9724%`），对**价格水平近线性**
  （`±10% ⇒ ∓/±10.0000%`）。敏感源是题面硬参数往返效率 `η_both`（`−20% ⇒ +13.35%`，`+1,953,341.06` 元）
  与容量上界 `E_max`（`−20% ⇒ +5.14%`）。
- **`4-3`：条件稳定（需给出适用边界）。** 适用边界：
  1. **σ ≤ 5% 的输入扰动**下结论稳健（族均值偏移 `+3.45% ~ +4.04%`，`std`/`CI`/`max|z|` 全部达标）；
  2. **σ = 10% 的价格白噪声属超设计工况**（`+10.5919%`，S4 越界），机制 = `Σq^em` 的 `max(0,·)` 凸性；
  3. **对光伏侧误差不稳健**（`pv_forecast_bias +10% ⇒ +23.25%`、`pv_forecast_noise σ=20% ⇒ +22.81%`、
     `pv_act_noise σ=10% ⇒ +10.22%`），对价格侧（预测器替换 `0.1711%`、`κ_m` 冻结 `0.0%`）稳健；
  4. 计划层低购电上限（`≤ 4500 kW`）**结构不可行**，该档仅作结构诊断，不进入费用结论。
- **两链差异**：`4-2 = 162/162` 全成功、**稳定**；`4-3 = 195/198`、**条件稳定**。3 个不可行样本
  （`buy_cap_3500/4000/4500 kW`，`HiGHS status=2`）是 `plan.md` §4.9 的**预注册预期结果**，
  保留在产物中、计入可行率分母但不计入 S1 受判子集；`S6` 正据此定出分界。
- **主口径未被替换**：`result4-2.xlsx`/`result4-3.xlsx` 仍为 accepted 主口径产物（md5 与 `run002` 登记值一致），
  robustness 数值未混入交付值（`AS12`/`E-F4`）。

### 4.3 预注册完整性与「不得为通过而放宽」的核查

- `plan.md` 修改时间**早于**两链任一结果文件；`report.md` 后于结果 ⇒ 事后未改方案。
- `criteria` 内 `S2`/`S4` 的规则文本含 `CF-10` 冻结措辞（`[0.25×, 4×]`、`同一 σ 档内`、
  `每族均值相对基线 ≤ 5%`），与 `plan.md` §3/§7 一致。
- `CF-10` 的纠偏方向**不是单向放宽**：`S2` 的 4-3 判据由窄带硬门禁改为宽带 + 窄带逐条披露（放宽），
  同时**新增**「每族均值相对基线 ≤ 5%」的锚定检查（收紧）。该新增锚定正是**最终判出 4-3 S4 不通过**的项
  ⇒ 阈值校准并非为凑 PASS 而设；4-3 的 FAIL 即为最好证据。
- 失败样本**未删除**：`4-3` 的 3 个不可行样本留在 `raw_samples.jsonl` 与 `summary.failures` 中，
  记入可行率分母；未使用 `--samples 2` 的探针口径替代正式 25 样本。

---

## 5. Level 4/6-披露：技术债与强制披露义务（本动作登记，不越界改写上游）

### 5.1 本动作新登记（`L6-W*`，均**不构成硬门禁失败**）

- **`L6-W1`（口径标注不一致，S5）**：`summary.criteria.S5.detail.solver_max_relative` 取**全期目标**口径
  （`4-2 = 1.25189e-4`、`4-3 = 4.36256e-4`），而 `report.md` §2.2/§4.5 对 `4-3` 的「链级最大相对差」取
  **交付期**口径（`6.10152e-4`）、对 `4-2` 又取全期（`1.25189e-4`，表内已注 `D_full`）。
  两者均 ≤ 1% ⇒ `S5` PASS 不变。**论文/下游引用「求解器口径敏感性」时必须标明所用口径**，
  不得跨口径比较（与 `R4-10` ①、`N2`、`E6` 同类纪律）。
- **`L6-W2`（预注册归一化基准未逐字定义，S4）**：`plan.md` §3 `S4` 只写「同一 σ 档内族间均值差 ≤ 3%」，
  未写明归一化基准；实现用 `(max−min) / mean(该档各族均值)`（`robustness_prob04.py:1541`）：
  `4-2 = 0.4463%`、`4-3 = 0.5654%`；若改为「除以基线」则为 `0.4474%` / `0.5865%`。
  两种口径均 ≤ 3% ⇒ 判定不变。建议 `formulation` 下一版或 `ablation` 计划中**明确基准**。
- **`L6-W3`（计划内部措辞冲突，执行已按 §0/§1.8）**：`plan.md` §0 表与 §1.8 声明静置损耗/`AS23`
  「不适用/本阶段不做」，而 §7 `CF-3` 写「本阶段采纳（只作结构情景）」；实际执行 = **不做**
  （两链情景清单无 `self_discharge`/`AS23`）。承 `R4-C1`，权威回写待 `ablation` 或 `formulation` 下一版。
- **`L6-W4`（计数纪律）**：`trajectories/` 为抽样（`4-2 = 62`、`4-3 = 70`），`raw_samples.jsonl` 每情景一条；
  `RUN_LESSONS_v001.md` §2b 的「`4-2` … 70 条」为笔误（承 `R4-7`/`E-F8`），**不得**据此判产物缺失。
- **`L6-W5`（Harness 缺陷痕迹，承 `E-F6`）**：`4-3` task `5713b0a24eedeac9f000` 的 `status.json` 仍残留过期
  `message = "worker PID 不存在且未写入终态"`，而实际 `status = succeeded` / `returncode = 0` /
  `finished_at = 2026-09-11T15:15:47.8Z`（自愈写入为 patch 语义、未删旧键）。**不判失败**；
  纪律不变：**有本地任务 `running` 时禁止 `RESUME`/`reconcile_tasks()`**。本动作未执行二者。
- **`L6-W6`（`E-F7` 证据纪律）**：5 条空转 `append_ledger` 动作（`act-6e395f67061f4990` 等）**未被本报告引用**
  为任何鲁棒性证据或结论。

### 5.2 承接上游欠账（本动作无权改写，指向 `ablation` / `cross_question_review` / 论文）

`C4-1`/`C4-2`/`C4-3`/`C4-6`/`C4-7`/`C4-10`、`D8`（`shared/problem_understanding.md` §7/§10 仍把 `A8` 记为
「待裁定」；`prob01/assumption_v003/version.yaml` 的 `AS08`「必然被激活」措辞）；`D10`「5000 kW 作用侧」为
`team_decision`，`prob01`–`prob04` 四池文献无一条涉及，**论文不得包装为文献支持**；`N1`–`N5`/`V1`–`V10`
（sanity/visualization 技术债，含 `κ_m ∈ [0.66233, 1.54939]`、`C^fc` 备选读法、`q_em` 措辞、`c` 上限字面值、
交付工作簿 md5）；`D1`–`D12` 继续结转；文献池 24 条未逐篇阅读正文（15 `abstract_oa` + 9 `metadata`），
本报告只引用框架级/机制级主张；`question_manifest.yaml` 的 `conclusion` 三字段仍为空
（`locally_completed` 门禁会报错，须在 `ablation` 结束或 `locally_completed` 前补齐）。

---

## 6. Level 6 判定与路由

| Level | 对象 | 结论 |
|---|---|---|
| L1（前置） | 两链 robustness task / 产物 / 指纹 / 输入 / 隔离 | **PASS** |
| L2（前置，已由 L1–L4 覆盖 + 本动作有限性扫描） | 144 个数值文件 `0 NaN / 0 Inf` | **PASS** |
| L3（前置，已在 `sanity_report.md` §3） | 量纲 / 逐层目标 / 填报表 | **PASS** |
| L4（含披露） | 常识 / 极端行为 / 文献 / `E-F2`–`F3` | **PASS_WITH_WARNING**（承 L1–L4 结论） |
| **L6** | **robustness 设计充分性 + 数值独立复算 + 预注册合规 + 反例披露** | **PASS_WITH_WARNING** |

**总判定：`PASS_WITH_WARNING`**（`failure_type = null`、`return_stage = null`、`blocking_reasons = []`）。

- 硬门禁（`config/sanity_check.yaml`：关键假设来源、物理/经济常识、题目硬约束）在 L1–L4 已通过；
  L6 未发现硬失败：数值全有限、`S1` 可行率 100%、基线闸门逐位通过、主口径未被替换、
  预注册判据未被事后放宽、失败样本未被删除、追踪链完整。
- **PASS_WITH_WARNING 的依据**：`4-3` 的 `S4` 预注册越界（σ=10% 价格白噪声）属**结构性条件不稳定**，
  已由团队勘误 `E-F9` 定档为「条件稳定（需给出适用边界）」，报告已给出边界与机制；
  叠加 `L6-W1`/`L6-W2`/`L6-W3` 三项口径/措辞技术债。以上均不改变主交付值、不影响 `ablation` 的独立性。
- **路由**：`PASS_WITH_WARNING` ⇒ **不退回**；按 `config/gates.yaml` 的 `sanity_check → ablation` 推进至
  `ablation`（`robustness`/`ablation` 同属 `mandatory_stages`，`ablation` 完成后才可 `locally_completed`）。

---

## 7. 证据清单（本动作，全部只读）

- `probe_l6_verify.py` / `probe_l6_verify_out.txt`（**270/270 PASS, 0 FAIL**）：产物与追踪完整性、预注册冻结、
  噪声族逐族重算（`n`/`mean`/`ddof=1 std`/1.96-CI/`max|z|`/族均值相对基线）、求解器双口径、买电上限分界、
  `κ_m` 截断来源、`K7`/`K8` 重算、报告引用值对账、交付件与模板 md5、任务终态与代码指纹、
  `figures.yaml` 未登记 robustness 图件。
- `machine_sanity_l6_autocheck.json` / `machine_sanity_l6_autocheck_out.txt`：通用脚本在**逐字节副本**
  （`evidence/auto_scope_l6/4-2`、`.../4-3`）上的 L1/L2-有限性扫描（`144` 数值文件、`failures = []`、`PASS_WITH_WARNING`）。
- 报告生成：`act-cb24258ea2be418a`（2026-09-11）。
