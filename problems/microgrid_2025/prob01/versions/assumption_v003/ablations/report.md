# prob01 消融与模型族对照报告

- 归属：`microgrid_2025` / `prob01`；阶段：`ablation`（`config/workflow.yaml` 的 `mandatory_stages`，不得 skipped）
- 汇总动作：`act-b0cec516722840f3`（ablation-analyst）；提交动作：`act-8fc1f3e5e410428c`
- 对象：accepted `assumption_v003` + `formulation_v001`（含团队裁定 D9/D10/D11 与勘误 E1–E3）
  与 computation 产物 `task 1300a936c4d95653f9d1` / `results/prob01_v003_f001_run002`（只读）
- 隔离计算：`task c1faaa09dedfb103c598`（attempt 1，`succeeded`，`supervised`，CPU，exit 0，wall 2.063 s）
  → `ablations/results/prob01_v003_ablation_run001/`
- 预注册：`ablations/plan.md`（**先于任何实验运行写定**，判据 C1–C7 与对照集合 A–F 事后未修改；
  本动作独立复核 `plan.md` mtime < `summary.json` mtime）
- 复核：`runtime/actions/act-b0cec516722840f3/evidence/verify_ablation_independent.py`（56/56 断言通过）

## 0. 适用性与团队裁定遵循

**适用**：本问为 144 时段单日确定性优化，存在明确的模型族选择（LP / MILP 互补 / SOC 离散化 DP）
与可单独开关的结构项（日周期约束、弃光变量、效率作用位置），消融与模型对比均有数值意义。

| 条款 | 要求 | 落实情况 |
|---|---|---|
| A0 | 主结果只以 accepted LP 为准，对照数值只进 `ablations/` | 本实验未写、未改 `results/`、`code/`、`formulation_v001/`、`assumptions.md`（独立复核：run002 `solution.json` sha256 与 mtime 均未变） |
| A1 | A–F 六项全部实跑 | 12 个 case 全部可解、0 不可行；`comparison.json` 的 `unexecuted = []` |
| A2 | 5 个预注册比较维度 | §2 表 1（约束满足度、题目指标）+ 表 2（复杂度、解释性）+ §5（鲁棒性复用） |
| A3 | 同数据/同参数/同预算/同口径/不改动/输出隔离 | §1.2 追踪链：输入 md5、seed、时限、求解器族、每 case 独立子目录 |
| A4 | 对比表 + 2–4 张图 + 结论三问 | §2、§7、§4 |
| A5 | 与 robustness 边界、冲突显式列出 | §5（含上限纪律探针） |

### 0.1 与 `agents/ablation-analyst.md` 默认步骤的差异（显式记录，不静默沿用）

| 默认步骤 | 团队裁定口径（效力更高） | 实际执行 |
|---|---|---|
| 步骤 1：3–4 个结构项 | A1 指定 A–F 共 6 项（2 模型族 + 3 结构 + 1 效率位置） | 全做，未缩减；F 由「时间允许时」转为必做 |
| 步骤 2：内部对照即可 | A0/A1 要求 A 基准复现 run002 | A 升级为**强制闸门** C1（不通过则整批作废 exit 4），实测 6 项相对差全 0 |
| 步骤 4：任务矩阵交 compute-manager | 既有范式：一个隔离 task + `worker_launch_mode=supervised` | 12 个 case 在同一 task、同一环境、同一 60 s 预算内完成，每 case 独立子目录 |
| 步骤 5：汇总关键指标 | A2/A4 要求 5 维度 + 对比表 + 2–4 图 + 结论三问 | 已按 A2/A4 扩展 |
| 「不适用可跳过」 | `mandatory_stages` 明令必做 | 未跳过；`record_optional_stage(ablation, completed)` |

### 0.2 未执行的对照项

无。A–F 全部实跑，`unexecuted = []`，`cases_total = 12`、`cases_infeasible = 0`、无超时、无非零返回。

## 1. 结果与独立复核

### 1.1 判据 C1–C7（预注册，事后未修改）

| 判据 | 阈值 | 实测 | 判定 |
|---|---|---|---|
| C1 基线复现（强制闸门） | 6 项相对差 ≤ 1e-6 | 目标值/Σb/Σc/Σq/Σs/`max_side_power` 相对差 **全 0.0** | passed |
| C2 MILP 无损性 | 相对差 ≤1e-6 且 `mip_gap` ≤1e-6 | 相对差 0.0、`mip_gap` 0.0、方向 `C_B ≥ C_A−1e-6` | passed |
| C3 DP 路线一致性 | h=50 偏差 ∈[0,1%] 且粒度单调 | 偏差 **+0.791%**（余量 0.21 个百分点）；h=400≥200≥100≥50 单调；DP 未优于 LP | passed |
| C4 结构消融方向 | `C_D, C_E ≤ C_A+1e-6` | D −6.312%、E 0.0% | passed |
| C5 效率作用位置 | `C_both ≥ max(其余)` 且各变体 ≤10% | accepted 最贵；最大偏差 **4.869%** | passed |
| C6 约束满足度 | 残差 ≤1e-6；MILP 同充放=0 | 12 case 全部 `checks_failed=[]`，`equality_residual_max ≤ 9.1e-13`、`bound_violation_max ≤ 1.1e-13`；MILP 同充放 0、互补残差 0 | passed |
| C7 解可解释性 | 充电时段电价均值 < 放电时段电价均值；A 同充放=0 | 所有 case 成立（A：0.6425 < 1.0845） | passed |

`criteria_failed = []`。分级：**C1–C7 全通过，模型族与结构对照成立**。

### 1.2 追踪链（独立复核全部通过）

| 项 | 值 | 复核 |
|---|---|---|
| 输入 `data/附件1.xlsx` md5 | `dbe06f92517431228efcc26e3e796ef9` | 重算一致 |
| run002 `solution.json` sha256 | `b083ac3b812c10ff008ad7734b9c774c3e1fb0a57c5ffb17d5c87f82749c7010` | 重算一致；mtime(20:50) < ablation 产物(22:07) ⇒ run002 未被覆盖 |
| ablation 代码 sha256 | `ablation_prob01.py = 03203e01…`；harness `code_hash = d59664d05c…` | 重算一致（代码自 task 运行后未变） |
| accepted 代码 sha256 | `prob01_model.py = 55e30e5e…`、`prob01_io.py = f1c3ec7d…` | 重算一致 |
| seed / 时限 / 口径 | 20260910 / 60 s / `min Σp_t·b_t`（元，不乘 Δt） | 与 A3 一致；费用 3.5×10⁴ 元（非 10³，未误乘 Δt） |
| 输出隔离 | 每 case 独立子目录 `A_*/ … F_*/case.json` + `raw_cases.jsonl`（12 行） | 齐备，无 NaN/Inf |

### 1.3 独立重解（本动作探针，非交付数值）

在不调用 `ablations/code/` 的前提下，直接从 `data/附件1.xlsx` 重建 LP / MILP / SOC-DP 并重解 12 个 case：

- 12/12 目标值与产物报告值一致到 **≤1e-9**（A/B/E/F_both = 35126.94858928963；D = 32909.86525595629；
  F 三变体 = 33416.53070703277 / 34168.609929486105 / 33801.49554222201；DP h400/200/100/50 =
  37616.519994955 / 36203.04214972333 / 35688.91753149555 / 35404.665606788876）；
- 题面指标（Σb、Σc、Σq、Σs、表 1 六时段、表 2 六块、端点储电量）与 `result1.xlsx`/`tables.json` 逐项一致；
- accepted 聚合恒等式按广义式复核（含端点项 $\eta_d(E_{144}-E_0)$）：A/B/E ≤ 4.6e-12，D 的端点项 = −4320.0
  （E_144 放空至 1200 kWh 的必然差值，非数值失败）；
- 60 s 预算、CPU、单卡 GPU 未占用。

## 2. 模型 × 指标对比表（A2 五维度）

### 表 1　约束满足度与题目指标（口径：`min Σp_t·b_t`，元，不乘 Δt）

| 对照 | 族/变动 | 可行 | 等式残差 | 界越界 | $C$（元） | ΔC vs $C^*$ | Σb (kWh) | Σc (kWh) | Σq (kWh) | Σs (kWh) | E_144 (kWh) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **A_baseline_LP** | accepted 完整 LP | 是 | 8.3e-13 | 0 | **35126.948589** | 0.000% | 59482.699 | 20740.666 | 16799.940 | 0.000 | 6000.0 |
| **B_milp** | +144 互补二元 | 是 | 8.3e-13 | 0 | **35126.948589** | 0.000% | 59482.699 | 20740.666 | 16799.940 | 0.000 | 6000.0 |
| **C_dp_h400** | SOC-DP 步长 400 | 是 | 1.1e-13 | 1.1e-13 | 37616.519995 | **+7.087%** | 60732.739 | 18349.922 | 14863.437 | 1704.282 | 6000.0 |
| **C_dp_h200** | 步长 200 | 是 | 1.1e-13 | 1.1e-13 | 36203.042150 | **+3.063%** | 60134.585 | 20328.180 | 16465.825 | 730.259 | 6000.0 |
| **C_dp_h100** | 步长 100 | 是 | 1.1e-13 | 1.1e-13 | 35688.917531 | **+1.600%** | 59817.922 | 20328.180 | 16465.825 | 413.595 | 6000.0 |
| **C_dp_h050** | 步长 50 | 是 | 1.1e-13 | 0 | 35404.665607 | **+0.791%** | 59618.201 | 20522.879 | 16623.532 | 176.882 | 6000.0 |
| **D_no_periodic** | 去日周期 $E_{144}$ 自由 | 是 | 8.3e-13 | 0 | 32909.865256 | **−6.312%** | 54149.366 | 15407.333 | 16799.940 | 0.000 | **1200.0** |
| **E_no_spill** | 删 $s_t$，改不等式平衡 | 是 | 8.3e-13 | 0 | **35126.948589** | **0.000%** | 59482.699 | 20740.666 | 16799.940 | —（无变量） | 6000.0 |
| **F_place_both** | $\eta_{ch}=\eta_{dis}=0.9$（accepted） | 是 | 8.3e-13 | 0 | **35126.948589** | 0.000% | 59482.699 | 20740.666 | 16799.940 | 0.000 | 6000.0 |
| **F_place_charge_only** | $\eta_{ch}=0.9,\eta_{dis}=1.0$ | 是 | 8.0e-13 | 0 | 33416.530707 | **−4.869%** | 57580.981 | 20390.089 | 18351.080 | 0.000 | 6000.0 |
| **F_place_discharge_only** | $\eta_{ch}=1.0,\eta_{dis}=0.9$ | 是 | 9.1e-13 | 0 | 34168.609929 | **−2.728%** | 57472.095 | 19301.224 | 17371.101 | 0.000 | 6000.0 |
| **F_place_round_trip** | 两侧 $\sqrt{0.9}$ | 是 | 9.1e-13 | 0 | 33801.495542 | **−3.773%** | 57526.243 | 19842.710 | 17858.439 | 0.000 | 6000.0 |

注：$C^* = 35126.948589$ 元（全文精度 35126.94858928963）；ΔC 一律定义为「对照 − $C^*$」（负=更省）；
表 2 采用模板行位置口径（计划窗 0:10→24:10，AS01 左端点相位）。12 个 case 的表 1 六时段与表 2 六块见各
`*/case.json` 与 `raw_cases.jsonl`。

### 表 2　复杂度、解释性与鲁棒性参考

| 对照 | 变量数 | 等式/不等式 | 求解时间 (s) | 迭代/节点 | `mip_gap` | 等效循环 | 同充放时段 | 充电时段均价 (元/kWh) | 放电时段均价 (元/kWh) | 鲁棒性参考（robustness run001） |
|---|---|---|---|---|---|---|---|---|---|---|
| A_baseline_LP | 720 | 288 / 0 | 0.0112 | 364 iter | — | 1.750 | 0 | 0.6425 | 1.0845 | 稳定（S1–S6 全通过，$\lvert\Delta C\rvert/C^* \le 8.885\%$） |
| B_milp | 864（144 二元） | 288 / 288 | 0.0483 | 1 node | 0.0 | 1.750 | 0 | 0.6425 | 1.0845 | 同上（solver 族相对差 0.0） |
| C_dp_h400 | 25（网格点） | 0 / 0 | 0.0095 | 90 000 转移 | — | 1.548 | 5 | 0.5790 | 1.1345 | DP 为确定性遍历，无求解器噪声 |
| C_dp_h200 | 49 | 0 / 0 | 0.0153 | 345 744 | — | 1.715 | 4 | 0.6504 | 1.1041 | 同上 |
| C_dp_h100 | 97 | 0 / 0 | 0.0387 | 1 354 896 | — | 1.715 | 4 | 0.6708 | 1.0967 | 同上 |
| C_dp_h050 | 193 | 0 / 0 | 0.3308 | 5 363 856 | — | 1.732 | 1 | 0.6440 | 1.0876 | 同上 |
| D_no_periodic | 720 | 288 / 0 | 0.0096 | 374 iter | — | 1.750 | 0 | 0.6841 | 1.0845 | 结构项，robustness 未覆盖（本阶段负责） |
| E_no_spill | 576 | 144 / 144 | 0.0081 | 364 iter | — | 1.750 | 0 | 0.6425 | 1.0845 | 结构项，同上 |
| F_place_both | 720 | 288 / 0 | 0.0105 | 364 iter | — | 1.750 | 0 | 0.6425 | 1.0845 | eta_placement 族 4/4 可行，$\Delta C/C^* \in [-4.869\%, 0]$ |
| F_place_charge_only | 720 | 288 / 0 | 0.0099 | 359 iter | — | 1.912 | 0 | 0.6425 | 1.0757 | 同上 |
| F_place_discharge_only | 720 | 288 / 0 | 0.0100 | 364 iter | — | 1.809 | 0 | 0.6526 | 1.0710 | 同上 |
| F_place_round_trip | 720 | 288 / 0 | 0.0102 | 364 iter | — | 1.860 | 0 | 0.6425 | 1.0710 | 同上 |

注：表 2 的鲁棒性列**直接复用** robustness run001 的结论（A5：robustness 负责参数扰动/置信区间，
本阶段负责模型族/结构项），本阶段未重跑参数扰动。DP 的 `max_side_power` 为 4978.94–5000 kW，
其余 case 均为 5000.0 kW，全部 ≤ 5000 kW。

## 3. 逐个对照的发现

1. **A（基准）**：复现 run002 的 6 项指标，相对差全 0；与 accepted `prob01_model.py` 的独立实现交叉检查
   相对差 0.0、`checks_failed=[]`。C1 闸门通过，故本批全部对照数值可引用。
2. **B（MILP 互补二元）**：`C_B = C_LP`（差 0.0）、`mip_gap = 0.0`、1 节点、288 条不等式、耗时 0.0483 s
   （LP 的 4.3 倍）。**结论：AS07「不显式强制同时充放电」在 LP 中无损**——最优解本身同充放时段为 0，
   显式互补约束不改变最优值。
3. **C（SOC 离散化 DP）**：四档粒度全部可行、随步长减小单调下降且恒 ≥ $C^*$（网格受限 ⇒ DP 是精确最优，
   偏差纯属离散化）；h=50 时 +0.791%（预注册阈值 1%，余量 0.21 个百分点）。
   **结论：换求解路线可复现同一最优费用的 0.8% 以内；粒度-偏差曲线给出量化边界**。
   DP 在 144 步遍历 5.36×10⁶ 次转移仅 0.33 s，说明本问规模下 DP 与 LP 均无计算瓶颈。
4. **D（去日周期约束）**：$E_{144}$ 由 6000 放开到 [1200,10800] 后最优解把末状态放空到 **1200 kWh**，
   费用降至 32909.865256 元，**日周期约束的经济价值 = 2217.083333 元（占 $C^*$ 的 6.312%）**；
   Σc 由 20740.666 降至 15407.333 kWh（少充 5333.333 kWh），Σq 不变、Σb 少购 5333.333 kWh。
   方向符合「放松约束不增加费用」（C4）。
5. **E（删弃光变量 $s_t$，改不等式平衡）**：仍可行，$C_E = C^*$（ΔC = 0.000000）。
   **结论：$s_t$ 在 prob01 最优解处完全不激活（Σs = 0，盈余全部被储能吸收），其上界
   $s_t \le PV_t\Delta t$ 在最优解处不紧**；删除该变量只减少 144 个变量与 144 条等式（720→576），
   不改变最优费用。变量保留的意义在于闭合功率平衡与容纳不可行盈余，属「必要但取值为 0」。
6. **F（效率作用位置）**：accepted 的两侧 0.9 是四种口径中**最保守（最贵）**：
   仅充电侧 0.9 省 1710.42 元（−4.869%）、往返整体 0.9 省 1325.45 元（−3.773%）、
   仅放电侧 0.9 省 958.34 元（−2.728%）。偏差随物理往返效率降低而增大，与模型族选择无关（K3）。

## 4. 结论段（A4.3 三问）

### 4.1 核心结论是否依赖模型族？

**不依赖。** 三条证据：

1. **同解**：B（互补二元 MILP）与 accepted LP 目标值完全相同（相对差 0.0，`mip_gap = 0.0`）；
2. **换路线同量级**：C（SOC 离散化 DP）四档粒度全部给出 ≥ LP 的目标值，最细网格（h=50）偏差
   **+0.791%**（预注册阈值 1% 以内），且偏差随粒度单调收敛，说明差异来自离散化而非模型结构；
3. **轨迹可比**：A/B 的逐项指标（Σb/Σc/Σq/Σs/表 1/表 2/端点储电量）逐位相同；DP 族轨迹不同但
   同样满足全部约束（残差 ≤1.1e-13）且套利方向一致（充电时段均价 < 放电时段均价）。

唯一需注意的口径：DP 与 LP 均**不禁止**同时充放电（AS07 是显式简化），DP h=400 出现 5 个同充放时段、
h=50 出现 1 个；这不影响目标值与可行性，但引用轨迹时须注明。

### 4.2 日周期约束与弃光变量的经济贡献？

- **日周期约束 $E_0 = E_{144} = 6000$ kWh：经济价值 2217.083333 元（$C^*$ 的 6.312%）**。
  放松后最优解在末时段把储能放空至下界 1200 kWh，等价于把「日初 6000 kWh 的存量电能」在当日变现。
  该数字是**单日、无跨日衔接**口径下的上界性质贡献；prob02 起若改为滚动/逐日独立递推，须按其裁定重算。
- **弃光变量 $s_t$：本日贡献为 0（$\Delta C = 0.000000$，$\Sigma s_t = 0$）**。
  在 accepted 解与 MILP 解中盈余均被储能完全吸收，且 $s_t$ 上界 $PV_t\Delta t$ 不紧。
  变量**必须保留**（用于在光伏盈余超出储能吸收能力时闭合功率平衡），但其在本问的取值恒为 0。
  该结论**只对附件 1 单日成立**，不得外推到 prob02–prob04：若引入售电或收紧盈余约束，须重算
  （robustness 已记录 sell_price ≥0.50 时 $s_t$ 界不够紧、出现非物理套利）。

### 4.2.1 论文主表推荐采用的模型及理由

**推荐 accepted LP（`formulation_v001`，A 基准）作为主结果与表 1/表 2/`result1.xlsx` 的唯一口径**，理由：

1. **最优性**：HiGHS 证明最优（`status=0`，364 迭代），$C^*$ 是全局最优值；
2. **无损**：显式补齐 AS07（B，MILP）不改变最优值（`mip_gap = 0.0`），说明 LP 松弛在此问题上无损失，
   不必付出 144 个二元变量与 4.3 倍耗时的代价；
3. **精度**：DP 路线（C）受网格限制只能逼近（h=50 仍差 +0.791%），不适合作为数值交付口径；
4. **可解释性**：LP 解的套利方向清晰（充电均价 0.6425 < 放电均价 1.0845）、同充放 0 时段、
   日周期精确闭合（E_144 = E_0 = 6000 kWh），便于论文叙述与图表追溯；
5. **一致性**：computation/sanity/robustness/本阶段四处的基线复现均为 $C^*$，追踪链完整。

**论文「模型对比」章节**建议采用本报告的 12 行对照表 + 图 `prob01_fig_model_cost_comparison_4c21fa4ed1`
与 `prob01_fig_dp_granularity_bias_32d09e54b4`，并明确披露：MILP 与 LP 同解；DP 的目标值偏差为
离散化代价（+0.79% ~ +7.09%）；D/E/F 为结构/口径敏感性。

## 5. 与 robustness 的边界及冲突处理（A5）

- **分工**：robustness run001（948 情景 / 947 可行）负责参数扰动（$\eta$、$E_0$、$E_{\min}$、
  $P_{\max}$、购电上限、折旧、售电、自放电、噪声、求解器）与置信区间；本阶段负责**模型族与结构项**
  （A/B/C/D/E/F）。两者结论不互相替代，本节不重复参数扰动数值。
- **潜在冲突 1（效率作用位置的上限纪律）**：robustness 的 `eta_placement` 族按情景**重算**功率上限
  （$c^{cap}=\min(P\Delta t, P\Delta t/\eta_{ch})$、$q^{cap}=\min(P\Delta t, P\Delta t\,\eta_{dis})$），
  本阶段 F 族**固定** 833.3333/750.0000 以做到「每次只改一项」。
  **处理**：本动作专门探针（`evidence/a5_cap_discipline_probe.py`）在两种纪律下重解
  charge_only（q 上限 750 vs 833.33）、round_trip（750 vs 790.57）、discharge_only（同为 750）：
  三者的放电峰值均为 **715.653033 kWh**，未触及任一纪律的差异区间，目标值逐位相同
  （33416.53070703277 / 33801.49554222201 / 34168.609929486105）。
  robustness `eta_placement` 的 `relative_delta` 区间 $[-0.048692, 0.0]$ 与本阶段 F 族逐位一致。
  **结论：无数值冲突**；但两族口径不同，跨阶段引用时**必须注明上限纪律**（plan §3.6/§3.9）。
- **潜在冲突 2（L6 稳定性 vs 结构项幅度）**：robustness 判「稳定」（主导参数 $\eta$，
  $\lvert\Delta C\rvert/C^* \le 8.885\%$），而本阶段发现 **D（去日周期）−6.312%**、
  **F（效率作用位置）−2.728% ~ −4.869%** 属同量级。
  **处理**：两者不矛盾——robustness 的「稳定」指**在 accepted 结构内的参数扰动**不改变结论方向与量级；
  本阶段改变的是**模型结构/口径**，因此这些幅度必须作为**结构性口径敏感性**在论文中显式披露
  （尤其 AS05 常效率 90% 与 $E_0=E_{144}$），不得包装为「模型稳健」。

## 6. 技术债与失败处理

| 编号 | 内容 | 影响与处置 |
|---|---|---|
| A-DR1 | `raw_cases.jsonl`/`case.json` 只落盘逐 case 汇总，**未落盘逐时段序列**，无法从产物直接核对轨迹 | 已由本动作独立重解（12/12 目标值与汇总指标一致到 ≤1e-9）补齐；论文引用轨迹时应注明该图来自 task 的原始解，逐点可追溯性弱于主结果 |
| A-DR2 | F 族上限纪律与 robustness `eta_placement` 不同（见 §5） | 已证明不绑定；引用须注明口径 |
| A-DR3 | DP 允许同时充放电（与 LP 相同），h=400/200/100/50 分别出现 5/4/4/1 个同充放时段；DP 的转移代价按解析最优 | 只影响轨迹不影响目标值；不作为「模型不一致」证据 |
| A-DR4 | B（MILP）仅 1 节点即证最优（本实例小），未验证大规模可解性 | 作为规模局限登记；prob02–prob04 若规模上升需重估 |
| A-DR5 | E 族（删 $s_t$）的 ΔC = 0 **只对附件 1 单日成立** | 不得外推到 prob02–prob04；售电/紧盈余约束下须重算 |
| A-DR6 | task 原始图 `ablation_waterfall.png`、`ablation_complexity_tradeoff.png` 存在文字遮挡/截断（最左数值标签压轴标签、点标注相互重叠、`C_dp_h400` 标注被上边界截断） | 本动作按统一脚本 `ablations/figures/plot_ablation_figures.py` 用**同一数据**重绘为登记版（中文标注、统一色系/DPI），task 原始图保留不改动 |
| A-DR7 | `question_manifest.yaml` 的 conclusion 三字段原为空（locally_completed 门禁会报错） | 本动作以 `record_conclusion` 补齐 |
| A-DR8 | C3 余量仅 0.21 个百分点（+0.791% vs 1% 阈值） | 判据不事后修改；若未来版本放宽粒度集合须重跑 |
| 结转 | 文献池 25 条未逐篇读正文；AS06「5000 kW 作用侧」无文献支撑；C1/E1、C2/E2、C3/E3 上游登记欠账待 `cross_question_review` 回写；A2/A6/A7/A8/A9 未裁定（属 prob02–prob04） | 见 `workflow_state.warnings`，本阶段未越界处理 |

失败处理（未触发）：单 case 不可行/超时 → 保留并计入失败计数；C1 不通过 → 整批作废 exit 4。
本次 12 case 全部成功，无失败注入。

## 7. 图件登记（A4.2）

task 原始图（`ablations/results/prob01_v003_ablation_run001/figures/`，4 张）为实验产物，原样保留；
登记进 `problems/microgrid_2025/figures.yaml` 的 4 张为**同一数据的统一重绘版**
（脚本 `ablations/figures/plot_ablation_figures.py`，只读 `comparison.json`/`dp_granularity.json`，
不重新求解），自动质检 `inspect_png` 全部 `passed`，视觉复核全部 `passed`：

| stable_id | 文件 | 自动质检 | 入论文 |
|---|---|---|---|
| `prob01_fig_model_cost_comparison_4c21fa4ed1` | `ablations/figures/ablation_model_cost.png` | passed（2046×876） | 是 |
| `prob01_fig_dp_granularity_bias_32d09e54b4` | `ablations/figures/ablation_dp_granularity.png` | passed（1488×876） | 是 |
| `prob01_fig_ablation_waterfall_3ff46a5abd` | `ablations/figures/ablation_waterfall.png` | passed（1740×876） | 是 |
| `prob01_fig_complexity_tradeoff_abc05773af` | `ablations/figures/ablation_complexity_tradeoff.png` | passed（1596×948） | 否（支撑性分析） |

`included_in_paper = false` 的 1 张（复杂度-费用）为支撑性技术图，论文可按需引用；
其余 3 张按 A4.2 供论文「模型对比」章节按 `stable_id` 引用。

## 8. 产物清单

```
ablations/plan.md                              # 预注册（跑数前冻结）
ablations/task_submission.md                   # 隔离 task 登记
ablations/code/{ablation_prob01.py,task_config.yaml,task_spec.yaml}
ablations/results/prob01_v003_ablation_run001/
  baseline_check.json solver_status.json comparison.json dp_granularity.json
  raw_cases.jsonl summary.json run_manifest.json
  {A_baseline_LP,B_milp,C_dp_h400..h050,D_no_periodic,E_no_spill,F_place_*}/case.json
  figures/{ablation_model_cost,ablation_dp_granularity,ablation_waterfall,ablation_complexity_tradeoff}.png   # task 原始图
ablations/figures/plot_ablation_figures.py + 4 张登记版 PNG + *.quality.json
ablations/report.md                            # 本文件
```

下一阶段：`locally_completed`（需 conclusion 三字段，已由本动作补齐）→ prob02。E1–E3 的权威回写
（`global_symbols.yaml` 的 $q_{dis}$ 域 833.33→750.00、$s_t$ 的 `first_question` prob02→prob01、
`assumption_v003/version.yaml` 中 AS08 措辞）仍待 `cross_question_review`。
