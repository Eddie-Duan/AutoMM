# prob01 消融与模型族对照实验方案（预注册）

- 归属：`microgrid_2025` / `prob01`；阶段：`ablation`（`config/workflow.yaml` 的 `mandatory_stages`，不得 skipped）
- 同步动作：`act-8fc1f3e5e410428c`（负责人：ablation-analyst）
- 版本目录：`problems/microgrid_2025/prob01/versions/assumption_v003/ablations/`
- 对象（只读）：accepted 版本 `assumption_v003` + `formulation_v001`（含团队裁定 D9/D10/D11 与勘误 E1–E3）
  与 computation 产物 `task 1300a936c4d95653f9d1` / `results/prob01_v003_f001_run002`
- 规则依据：`assumptions.md` 末尾「团队裁定（ablation 多模型对比设计与预注册判据，2026-09-10）」、
  `agents/ablation-analyst.md`、`config/workflow.yaml`、`config/gates.yaml`、`skills/compute-manager/SKILL.md`
- 预注册原则：**本文件在看到任何实验结果之前写定**；对照集合、预注册判据、公平性纪律与失败处理在代码运行前冻结。
  事后若发现范围有误，必须新建 `plan_v002` 并保留 `plan_v001` 与已跑结果，不得修改本文判据或口径。

---

## 0. 适用性与团队裁定遵循

### 0.1 适用性决定

**适用**。本问为 144 时段单日确定性优化模型，存在明确的模型族选择（纯 LP / MILP 互补约束 / SOC 离散化 DP）
与可单独开关的结构项（日周期约束、弃光变量、效率作用位置），消融与模型对比均有数值意义。
按团队裁定 A0/A1，`optional_stages.ablation.decision` 钉定为**执行**，本阶段不跳过、
不以「某项不激活」为由缩减对照集合。

### 0.2 团队裁定 A0–A5 的逐项落实

| 条款 | 要求 | 本方案落实位置 |
|---|---|---|
| A0 | 主结果只以 accepted LP 的 run002 为准；对照数值只进 `ablations/` | §3.1、§4（本实验不写 `results/`，不修改 accepted `code/`、`formulation_v001/`、`assumptions.md`） |
| A1 | A–F 六项全部实跑，不得只做定性论证 | §3.1–§3.6（A 基准 + B MILP + C DP + D 去日周期 + E 去弃光 + F 效率作用位置） |
| A2 | 5 个预注册比较维度（约束满足度 / 题目指标 / 复杂度 / 解释性 / 鲁棒性） | §3.8 记录项 + §2 判据 C6/C7 + §3.9（鲁棒性维度复用 robustness run001） |
| A3 | 同数据 / 同参数 / 同预算 / 同口径 / 不改动 / 输出隔离 | §3.7 |
| A4 | 一张模型 × 指标对比表、2–4 张图、结论段三问 | §3.8、§4、§6（结论段在 `ablations/report.md`，即本阶段第二个动作完成） |
| A5 | 与 robustness 边界；冲突显式列出 | §3.9 |

### 0.3 与 `agents/ablation-analyst.md` 默认步骤的差异（显式记录，不静默沿用）

| 默认步骤 | 团队裁定口径 | 差异处理 |
|---|---|---|
| 步骤 1「选择 3–4 个有解释意义的公式项或约束方向」 | A1 指定 A–F 共 6 项（2 项模型族/求解路线 + 3 项结构消融 + 1 项效率作用位置） | 按团队口径全做，不缩减为 3–4 项；F 标记为「时间允许时执行」，本方案执行 |
| 步骤 2「当前完整模型是内部对照，不要求外部 baseline」 | A0/A1 要求 A 基准**复跑并复现 run002**（目标值相对容差 ≤1e-6） | A 基准改为**强制复现闸门**（判据 C1，不通过整批作废） |
| 步骤 4「生成任务矩阵并交 compute-manager」 | `skills/compute-manager` 与既有范式：由本 Agent 用 `scripts/automm/tasks.py` 的 `make_task_spec`/`submit_task` 生成**一个**隔离 task，由 Runner 以 `worker_launch_mode=supervised` 原地执行 | 全部对照在**同一 task、同一 Python/包环境、同一求解预算**下完成（这正是 A3「同预算」的要求）；`ablations/results/<run_id>/` 下**每个对照一个独立子目录**，原始样本与汇总分文件保存，满足 A3「输出隔离」 |
| 步骤 5「汇总关键指标、约束满足度和结论变化」 | A2/A4 要求 5 维度、对比表与 2–4 张图、结论段三问 | 按 A2/A4 扩展（§3.8、§4、§6） |

---

## 1. 被检验的核心结论（实验前固定）

- **K1（主结果不依赖模型族）**：accepted LP 的最优全天购电费 `C* = 35126.948589 元`
  （`Σb = 59482.698998 kWh`、`Σc = 20740.666132 kWh`、`Σq = 16799.939567 kWh`、`Σs = 0`、
  `max_side_power = 5000 kW`）可被 B（MILP）与 C（DP）在各自口径内**复现**（同一目标值与同量级调度结构）。
- **K2（结构项有可量化经济贡献）**：日周期约束 `E_0 = E_144` 与弃光变量 `s_t` 都在 accepted 解中
  起作用；放松/删除它们会改变最优费用，方向为**放松约束不增加费用**（`C_D`, `C_E` ≤ `C*`）。
- **K3（效率作用位置与模型族无关的偏差）**：AS05 的「两侧各 0.9」是四种作用位置中最保守（费用最高）的口径，
  其余口径按物理效率从低到高给出可量化偏差；该偏差与模型族选择无关。

---

## 2. 预注册判据（实验前固定，事后不得修改）

| 判据 | 定义 | 通过阈值 | 不通过的处置 |
|---|---|---|---|
| **C1 基线复现（强制闸门）** | A 基准的 `C`、`Σb`、`Σc`、`Σq`、`Σs`、`max_side_power` 六项与 run002 `solution.json` 的相对差 | 六项全部 ≤ 1e-6 | **整批作废**（exit 4），按 `needs_revision` 回 implementation/ablation 复核口径；不得引用其余对照数值 |
| **C2 MILP 无损性** | `\|C_B − C_A\| / C_A` 与 MILP 的 `mip_gap` | 相对差 ≤ 1e-6 且 `mip_gap` ≤ 1e-6 | 记「AS07 显式二元约束对 LP 最优值有 ≥1e-6 影响」为技术债并按 `allow_pass_with_warning` 登记；若 `C_B < C_A − 1e-6`（MILP 是 LP 的收紧，理论上不应出现）判实现错误 |
| **C3 DP 路线一致性** | `(C_C(h=50) − C_A)/C_A`（DP 是网格受限，理论应 ≥ 0）；粒度曲线 `C_C(h)` 随步长 h 减小的单调性 | 相对差 ∈ [0, 1%]；`C_C(400) ≥ C_C(200) ≥ C_C(100) ≥ C_C(50)`（数值容差 1e-6） | 记数值/离散化技术债，报告粒度-偏差边界；若出现 `C_C < C_A − 1e-6` 判 DP 实现错误（DP 不应优于 LP） |
| **C4 结构消融方向** | `C_D ≤ C_A + 1e-6`（放松日周期不增加费用）且 `C_E ≤ C_A + 1e-6`（去掉 `s_t` 改用不等式平衡属放松不增加费用） | 两条同时成立 | 方向反转 ⇒ 判实现口径错误，回 implementation 定位（不得把反转当作发现发布） |
| **C5 效率作用位置** | `C_both ≥ max(C_charge_only, C_discharge_only, C_round_trip) − 1e-6`；各变体 `\|ΔC\|/C_A` | 关系成立且各变体偏差 ≤ 10% | 记方向异常项并复核；超 10% 需在报告中给出边界 |
| **C6 约束满足度** | 每个对照 case 的 `equality_residual_max`、`bound_violation_max`；MILP 的 `c_t·q_t` 残差与同时充放电时段数 | 残差 ≤ 1e-6；MILP 同充放时段数 = 0 且 `c·q` 残差 ≤ 1e-6 | 该 case 作废并逐项登记（不得以「目标值更好」为由保留越界解） |
| **C7 解可解释性** | A/B/C 的「充电时段电价均值 < 放电时段电价均值」（套利方向）；A 的同时充放电时段数 | 全部成立 | 记符号异常项并给出调度反例 |

**分级**：C1–C7 全通过 ⇒ 模型族与结构对照成立；C1 不通过 ⇒ 整批作废；
C2–C7 中任一非关键项不通过 ⇒ 按 `config/gates.yaml` 的 `allow_pass_with_warning` 记技术债，
不得事后修改阈值、不得超过一次修复后重跑同一 `output_directory`。

**预注册的比较口径（防止事后挑选）**：费用比较一律用「相对 `C*` 的百分比」；
`ΔC` 一律定义为「对照模型费用 − `C*`」（负数=更省）；表 1/表 2 一律按 accepted 模板行位置口径聚合。

---

## 3. 对照集合与实验矩阵（A1）

### 3.1 A（基准）：完整 LP

accepted `code/prob01_model.py` 的模型 (P1)（`formulation_v001`），自包含复刻，口径：
`min Σ p_t·b_t`（元，不乘 Δt，D9）、`E_t = E_{t−1} + η_ch c_t − q_t/η_dis`、
`E_0 = E_144 = 6000 kWh`、`E_t ∈ [1200, 10800]`（t < 144）、`c_t ≤ 833.3333`、`q_t ≤ 750.0000`（E1/D10 口径丙）、
`0 ≤ s_t ≤ PV_t·Δt`、`b_t ≥ 0`（AS15 无购电上限）。求解器 HiGHS（`scipy.optimize.linprog`），时限 60 s。

### 3.2 B（模型族对照）：MILP 互补二元变量

在 A 上追加 144 个二元变量 `u_t ∈ {0,1}` 与约束 `c_t ≤ C_CAP·u_t`、`q_t ≤ Q_CAP·(1 − u_t)`
（`C_CAP = 833.3333`、`Q_CAP = 750.0000`），显式强制 AS07 的「不同时充放电」。
求解器 HiGHS（`scipy.optimize.milp`），时限 60 s、`mip_rel_gap = 0`；记录 `mip_gap`、节点数、求解时间、变量/约束规模。

### 3.3 C（求解路线对照）：SOC 离散化 DP

状态 `E_t` 离散到 `[1200, 10800]` 上步长 `h ∈ {400, 200, 100, 50} kWh` 的等距网格
（`E_0 = E_144 = 6000` 均在网格上）；逐时段转移代价按给定 `(E_{t−1}=a, E_t=b)`（`ΔE = b−a`）解析求最优：

- `ΔE ≥ 0` 时取 `c = ΔE/η_ch, q = 0`；`ΔE < 0` 时取 `c = 0, q = η_dis·|ΔE|`；
- 购电量 `b = max(0, net_e + c − q)`，弃光 `s = max(0, −(net_e + c − q))`，`net_e = (L_t − PV_t)·Δt`；
- 可行性要求 `c ≤ C_CAP`、`q ≤ Q_CAP`、`s ≤ PV_t·Δt`；当 `s` 超限时沿 `c` 增大方向（等价于同时充放电）
  补偿到 `s ≤ PV_t·Δt`（DP 与 LP 一样不显式禁止同时充放电）；
- 区间代价 `p_t·b`（元，不乘 Δt）。

DP 无求解器迭代，确定性遍历；记录网格点数、转移次数与耗时。**粒度-偏差曲线**（`C_C` vs `h`，含相对 `C*` 的偏差）
是 A1 要求必须回答的「离散粒度对费用偏差的影响」。

### 3.4 D（结构消融 1）：去掉日周期约束

A 的基础上把 `E_144` 的界由固定 `6000` 改为 `[1200, 10800]`（`E_0 = 6000` 的 AS11 初值保留，只放松末状态），
其余完全不变。**该约束的经济价值 `= C_A − C_D`**（放空/充满套利的量），并报告 `E_144`、`Σc`、`Σq` 的变化。

### 3.5 E（结构消融 2）：去掉弃光变量 `s_t`

A 的基础上删除 `s_t`，把逐时段电量平衡由等式 `b + q − c − s = net_e` 改为不等式
`b + q − c ≥ net_e`（余电自由丢弃、不再有 `s_t ≤ PV_t·Δt` 的上界），变量数由 5n 降为 4n，其余不变。
必须回答：**是否仍可行**、费用口径变化与偏差方向（理论上该变体移除了一条上界，属放松，`C_E ≤ C_A`）。

### 3.6 F（结构消融 3）：效率作用位置

A 的基础上只改 `(η_ch, η_dis)`，`c/q` 上限**固定为 accepted 的 833.3333 / 750.0000**（只改效率一项）：

| 标签 | `η_ch` | `η_dis` | 说明 |
|---|---|---|---|
| `place_both` | 0.9 | 0.9 | accepted（AS05 两侧） |
| `place_charge_only` | 0.9 | 1.0 | 仅充电侧 0.9 |
| `place_discharge_only` | 1.0 | 0.9 | 仅放电侧 0.9 |
| `place_round_trip` | √0.9 | √0.9 | 往返整体 0.9 |

**与 robustness `eta_placement` 族的差异（须在报告显式登记）**：robustness 族按各情景重算功率上限
（`c_cap = min(P·Δt, P·Δt/η_ch)`、`q_cap = min(P·Δt, P·Δt·η_dis)`），本对照**固定上限**以做到「每次只改一项」。
两者数值不可直接互换引用；若结论冲突，按 A5 在 `ablations/report.md` 列出。

### 3.7 公平性纪律（A3，违反即结果作废）

- **同数据**：只用 `data/附件1.xlsx`（md5 `dbe06f92517431228efcc26e3e796ef9`）；不读、不写模板与原始数据。
- **同参数**：`Δt = 1/6 h`、`η_ch = η_dis = 0.9`（除 F 的显式变体外）、`c_t ≤ 833.3333`、`q_t ≤ 750.0000`、
  `E ∈ [1200, 10800]`、`E_0 = E_144 = 6000 kWh`。
- **同预算**：每个求解器 case 时限 60 s；全部 case 在同一 Python/包环境、同一 HiGHS 族内完成；
  `seed = 20260910`（本实验确定性，无随机采样；DP/结构消融亦为确定性）。
- **同口径**：目标一律 `min Σ p_t·b_t`（元，不乘 Δt）；费用量级应为 10^4 元，出现 10^3 即误乘 Δt。
- **不改动**：不修改 accepted `code/`、`formulation_v001/`、`assumptions.md`、`results/prob01_v003_f001_run002/`；
  对照实现只存在于 `ablations/code/`。
- **输出隔离**：全部产物写入 `ablations/results/prob01_v003_ablation_run001/`，
  每个对照一个独立子目录（§4），主结果目录 `results/` 不被覆盖。

### 3.8 A2 五维度的记录项

1. **约束满足度**：`equality_residual_max`、`bound_violation_max`、`periodic_endpoint_gap`、
   `max_side_power_kw`、同充放时段数、`c·q` 残差、`checks_failed`。
2. **题目指标**：全天费用 `C`（元）、全天购电量 `Σb`（kWh）、表 1 六个时段（位置 60/72/84/96/108/120）
   购电量、表 2 六段（每段 24 时段）充放电量与 0:00/24:00 储电量。
3. **复杂度**：变量数、等式/不等式约束数、求解时间（s）、迭代次数、MILP `mip_gap` 与节点数、DP 网格点数与转移数。
4. **解释性**：充电/放电时段电价均值（套利方向）、同充放时段数、`E_144` 与储能区间、等效循环次数。
5. **鲁棒性**：**直接复用** robustness run001 的 S1–S6 与 OAT 弹性（η、`E_0`）作为统一参考，
   本阶段不重跑参数扰动（A5：robustness 负责参数扰动/置信区间，ablation 负责模型族/结构项）。

### 3.9 与 robustness 的边界

robustness 结论：分级「稳定」、S1–S6 全通过、η 为主导参数（`|ΔC|/C*` ≤ 8.885%）、
`E_init` 几乎不敏感、购电峰值 8458.8273 kW、D10 甲≡丙、效率作用位置偏差 2.7%–4.9%（按各情景重算上限）。
本阶段只做模型族与结构项对照。若本阶段结果与 robustness 的稳定性结论冲突
（例如 F 族在固定上限下给出与 robustness `eta_placement` 明显不同的偏差量级），
须在 `ablations/report.md` 中显式列出冲突点、根因（上限是否随情景重算）与处理方式，不得混写。

---

## 4. 输出隔离与文件布局

`ablations/results/prob01_v003_ablation_run001/`（隔离 task 的输出目录）：

```
baseline_check.json      # C1 基线复现闸门（与 run002 逐项对比）
solver_status.json       # 求解器/环境/可行解/计数（供 task_worker 判定 feasible_incumbent）
comparison.json          # 模型 × 指标对比表（A–F 全条目 + 复杂度 + 解释性）
dp_granularity.json      # DP 粒度-偏差曲线原始数据
raw_cases.jsonl          # 每个对照 case 一行（原始指标，失败 case 保留、不删除）
summary.json             # 判据 C1–C7 判定 + 结论 K1–K3 + 技术债
figures/                 # 2–4 张图（费用对比、DP 粒度-偏差、消融瀑布、复杂度-费用）
run_manifest.json        # task_id、代码 sha256、输入 md5、seed、计数、耗时、追踪链
A_baseline_LP/case.json  # 每个对照一个独立子目录（原始样本与汇总分开）
B_milp/case.json
C_dp_h050/case.json 等
D_no_periodic/case.json
E_no_spill/case.json
F_eta_*/case.json
```

图件为**实验产物**；是否登记为交付图表按 A4.2 在结果就绪后的动作中决定
（登记须含 `stable_id`、`included_in_paper`、`question_id`，并通过 `config/visualization.yaml` 的自动质检与视觉复核）。

## 5. 失败处理

- 单 case 不可行 / 超时 / 非零返回：保留在 `raw_cases.jsonl` 并计入该族的失败计数，**不删除、不静默替换**；
  在 `comparison.json` 中该格写「不可行/未执行 + 原因」，并按 `allow_pass_with_warning` 登记技术债。
- C1 基线复现失败：**整批中止**（exit 4），按 `needs_revision` 路由，不引用任何对照数值。
- 输出含 NaN/Inf：`allow_nan=False` 直接失败，不落盘。
- MILP 未证明最优（`mip_gap > 1e-6`）：按 `config/compute.yaml` 的
  `allow_missing_mip_gap_with_incumbent` 与 `gates.yaml` 的 `allow_pass_with_warning` 处理，
  记录 incumbent、`mip_gap` 与节点数，不得伪报最优。
- 计算必须经隔离 task、独立输出目录与 supervised worker；本 Agent 不自行代跑、不调用 `start_queued`。
  代码修复只允许在新 attempt + 新 `output_directory` 下重跑，不覆盖既有结果。

## 6. 交付物（A4）

1. 一张**模型 × 指标**对比表（A–F 全部条目，含未执行项与理由）——`comparison.json`，
   并在 `ablations/report.md` 中排版为 Markdown 表；
2. 2–4 张图（模型费用对比、DP 粒度-偏差、消融瀑布、复杂度-费用）——`figures/`；
3. `ablations/report.md` 结论段必须回答：
   ①核心结论是否依赖模型族（LP/MILP/DP 是否同解）；
   ②日周期约束与弃光变量的经济贡献；
   ③论文主表推荐采用的模型及理由。
4. 完成后以 `record_optional_stage(stage=ablation, decision=completed)` 收尾（不得 `skipped`）。
