# prob01 文献研究（问题 1：单日计划购电策略）

- 归属：`microgrid_2025` / `prob01`；阶段：`literature_review`
- 同步动作：`act-70ed2cb7c38141fb`（负责人：literature-researcher）
- 检索轮次：`rnd-9cbe3f07562c`（`dry=true`，`dry_reason=all_candidates_decided`）
- 结构化记录：`shared/literature_pool.yaml`（25 条，全部 `used` 且 `verified=true`）
- 题目引用登记：`problems/microgrid_2025/citations.yaml`（25 条，与文献池一致）
- 规则依据：`wiki/literature-citations.md`、`knowledge/evidence-policy.md`；本次**不固定任何关键数学假设**，只提供可核验依据与适用边界。

---

## 1. 检索目标与范围

prob01 是「每天 0:00 制定单日计划购电策略」的确定性优化问题。需要文献回答的不是题面数值（电价、负载、光伏、储能参数均由附件 1 与附录 1 给定），而是**建模口径的合法性**：

| 编号 | 待支撑的建模问题 | 对应题面歧义 |
|---|---|---|
| H1 | 目标函数取「全天计划购电费最小」的线性形式；是否引入电池折旧/退化成本 | A11 |
| H2 | 功率平衡与供电可靠性口径：`购电 + 光伏 + 放电 ≥ 负载`，以及不平衡方向如何处理 | A5 |
| H3 | 储能状态转移中充放电效率的作用位置与常效率简化的边界 | A3 |
| H4 | 容量/功率/日周期约束：`1200 ≤ E ≤ 10800`、充放电功率上界、`E(0)=E(T)` | A15、H2、H3、H6 |
| H5 | 同一时段是否允许同时充放电（互补性）及其处理方式 | A5/A13 |
| H6 | 光伏大于「负载 + 充电」时盈余/弃光的显式建模 | A13 |
| H7 | 时间离散与 `kW → kWh` 的 `Δt` 换算口径 | A12 |
| H8 | 模型族选择：确定性 LP/MILP 是否为该问题的标准方法 | — |

检索式由「对象 + 机理 + 方法 + 限制」组成，实际使用的 Crossref 书目检索式与 `web_search` 关键词见 §6 与 `runtime/actions/act-70ed2cb7c38141fb/evidence/discover_*.py`。

**范围说明（重要）**：`A1`（附件时间戳与模板时间段的 10 分钟错位）、`A2`（结果日期范围）、`A16`（附件 1 是独立代表性单日）属于**题面/数据事实**，文献不能替代裁定，本文件不为其提供也无法提供引用依据。

## 2. 核验方法与限制

- **元数据核验**：25 条全部通过 harness `automm.research.verify_reference` 的 Crossref 核验（`verified=true`，`verification_provider=crossref`），标题、作者、年份、期刊/会议名以 Crossref 记录为准写入 `citations.yaml`。
- **全文可获取性**：本动作环境无浏览器级全文抓取能力，**未逐篇阅读正文**。其中 4 条取得开放摘要并记为 `verification_level=abstract_oa`（`ref-alguhi-2025-bess-operation`、`ref-shen-2026-peak-valley`、`ref-huang-2022-dynamic-efficiency`、`ref-arima-2024-rte-profile`）；其余 21 条只取得元数据与标题，记为 `verification_level=metadata`。
- **主张强度纪律**：因此本阶段的引用只用于「问题形式、约束组成、方法族、简化边界」这类**框架级主张**；不引用任何原文未核验的定量结论、参数值或实验数字。凡涉及具体数值（效率、容量、SOC 区间），一律以题面附录 1 为准。
- **分类纪律**：`literature_fact`（来源支持的事实）、`project_assumption`（为本题建立、待验证边界的假设）、`agent_inference`（由数据/模型推断）、`team_decision`（阈值/权重选择）四类互不冒充；本阶段产出的「建议口径」均为 `agent_inference`，最终裁定属 `assumption_definition` / `mathematical_formulation`。

## 3. 来源清单（按主题分组）

等级：A 同行评审期刊/主要会议；B 权威会议论文/成熟技术文献；C 会议摘要/预印本级。全部 25 条均为**本轮新增**且状态 `used`（`new → used`）；本轮无 `rejected`（一条由检索命中的锌空电池论文因与调度优化无关，在发现阶段即被剔除，未入池）。

### 3.1 目标口径 H1（购电费最小、是否含折旧）

| ID | 等级 | 支持对象 |
|---|---|---|
| `ref-lee-2020-purchase-cost-lp` | B | 「购电费用最小」可直接写成线性目标 |
| `ref-lin-2024-tou-industrial` | A | TOU 电价下光伏-储能的经济性优化 |
| `ref-wongwut-2017-tou-prosumer` | B | TOU 下逐时段储能运行优化 |
| `ref-baloyi-2021-tou-arbitrage` | B | TOU 峰谷套利的储能运行动机 |
| `ref-olivieri-2020-residential-bess` | A | 储能逐时段调度 + 成本最小是标准问题 |
| `ref-rawa-2023-mg-stochastic` | A | 微网运行调度 + 储能的成本最小模型族 |
| `ref-zhang-2015-dayahead-degradation` | A | 反向证据：日前调度中常把电池折旧纳入目标 |
| `ref-arima-2024-rte-profile` | C | 效率非恒定，支撑「常效率」为简化 |

### 3.2 功率平衡与可靠性 H2

| ID | 等级 | 支持对象 |
|---|---|---|
| `ref-moradi-2018-standalone` | A | 微网能量管理以供需平衡为基本约束 |
| `ref-csee-2023-mg-ems-review` | A | 含储能的微网 EMS 综述（目标/约束/方法族） |
| `ref-heydari-2016-lpsp` | A | 供电可靠性可显式约束（LPSP；确定性硬约束是其特例） |
| `ref-zeinalzadeh-2017-loadshed-curtail` | B | 供电不足与出力盈余两个方向的不平衡建模 |

### 3.3 储能动态与效率 H3

| ID | 等级 | 支持对象 |
|---|---|---|
| `ref-vykhodtsev-2022-bess-review` | A | 电力系统技术经济分析中 BESS 的建模方法综述（效率/SOC/退化表征） |
| `ref-jamroen-2023-soc-sizing` | A | SOC 管理对储能经济性与可靠性的作用 |
| `ref-huang-2022-dynamic-efficiency` | A | 常效率模型会误判运行状态；动态效率的函数关系 |
| `ref-arima-2024-rte-profile` | C | 往返效率取决于 SOC/退化/逆变器，逐台不同 |

### 3.4 容量/功率/日周期约束 H4

| ID | 等级 | 支持对象 |
|---|---|---|
| `ref-shen-2026-peak-valley` | A | 显式约束集：功率限值 + SOC + 充放电状态 + **日能量平衡** |
| `ref-alguhi-2025-bess-operation` | A | 24h MILP：充放电动态 + SOC 约束 + 电价信号 |
| `ref-valibeygi-2020-battery-dispatch-soc` | B | SOC 作为显式状态变量参与调度 |

### 3.5 充放电互补性 H5

| ID | 等级 | 支持对象 |
|---|---|---|
| `ref-wang-2024-complementarity` | A | 储能互补约束的精确松弛方法 |
| `ref-nazir-2023-realizable-dispatch` | A | 不引入互补（二元）约束也能保证调度物理可实现的条件 |

### 3.6 弃光/盈余 H6

| ID | 等级 | 支持对象 |
|---|---|---|
| `ref-grimaldi-2025-arbitrage-curtail` | A | 套利优化中显式处理可再生弃电 |
| `ref-qing-2025-pv-curtailment` | B | 以「弃光率」为约束/指标的微网优化 |
| `ref-zeinalzadeh-2017-loadshed-curtail` | B | 弃电与切负荷的同时最小化 |

### 3.7 方法族 H8（日前调度 = LP/MILP）

| ID | 等级 | 支持对象 |
|---|---|---|
| `ref-csee-2023-mg-ems-review` | A | 微网 EMS 方法综述 |
| `ref-carpinelli-2013-dayahead-ilp` | B | 日前微网调度用（整数）线性规划 |
| `ref-ignat-2019-cost-dayahead` | B | 可再生微网成本优化 + 日前调度 |
| `ref-alamir-2025-dayahead-multimg` | B | 多微网最优日前调度 |
| `ref-rawa-2023-mg-stochastic` | A | 确定性运行 vs 随机调度的谱系 |

## 4. 候选假设族与来源映射（供 `assumption_definition` 裁定）

以下均为**候选口径**，不是已定假设；每条给出文献依据、与本题的差异和裁定要点。

- **H1 目标与折旧**
  - 文献依据：`ref-lee-2020-purchase-cost-lp`、`ref-lin-2024-tou-industrial`、`ref-wongwut-2017-tou-prosumer`、`ref-olivieri-2020-residential-bess`（购电/运行费用最小可线性建模）。
  - 差异与边界：`ref-zhang-2015-dayahead-degradation`、`ref-rawa-2023-mg-stochastic` 显示日前调度常把折旧/退化纳入目标；本题附录 1 未给循环寿命与折旧参数，**无法标定折旧系数**。
  - 裁定要点：prob01 目标是否仅取购电费；若仅取购电费，必须写成显式 `project_assumption`（「不计电池折旧」），并在 robustness 中说明该省略的影响方向（会高估充放电频次）。
- **H2 功率平衡与可靠性**
  - 文献依据：`ref-moradi-2018-standalone`、`ref-csee-2023-mg-ems-review`、`ref-heydari-2016-lpsp`、`ref-zeinalzadeh-2017-loadshed-curtail`。
  - 裁定要点：采用「购电 + 光伏 + 放电 + 盈余 ≥ 负载 + 充电」的不等式形式，其中供电可靠性方向写成 `购电 + 光伏 + 放电 ≥ 负载`（充电不得挤占负载，A5 候选 (a)）；文献支持「可靠性可显式约束」，但不直接决定本题的充电可行性口径。
- **H3 效率作用位置**
  - 文献依据：`ref-vykhodtsev-2022-bess-review`（效率建模综述）、`ref-jamroen-2023-soc-sizing`（SOC 管理）、`ref-huang-2022-dynamic-efficiency` 与 `ref-arima-2024-rte-profile`（常效率是简化）。
  - 裁定要点：附录 1 只给「充放电效率 90%」。建议状态转移取 `E_t = E_{t-1} + η_ch·c_t − q_dis_t/η_dis`、`η_ch = η_dis = 0.9`（两侧 90%，往返 81%），并做量纲与极限检验；文献明确支持「常效率是简化」，故须在假设中声明并在 robustness 中扰动效率。
- **H4 容量/功率/日周期约束**
  - 文献依据：`ref-shen-2026-peak-valley`（SOC + 功率限值 + 充放电状态 + 日能量平衡）、`ref-alguhi-2025-bess-operation`、`ref-valibeygi-2020-battery-dispatch-soc`。
  - 裁定要点：`1200 ≤ E_t ≤ 10800`；每段充/放电量上界 `5000·Δt`；prob01 的 `E_0 = E_144`（A15：是否取 6000 kWh 等价于把该日视作 2025-01-01）。
- **H5 同时充放电（互补性）**
  - 文献依据：`ref-wang-2024-complementarity`（精确松弛）、`ref-nazir-2023-realizable-dispatch`（不显式加互补约束的实现条件）。
  - 裁定要点：在常效率 `η<1` 且购电价为正的线性目标下，同时充放电通常被支配；但必须在模型中**显式确认或声明为可省约束**，并在 sanity 中检查 `c_t·q_dis_t` 残差，而不是默认成立。
- **H6 弃光/盈余**
  - 文献依据：`ref-grimaldi-2025-arbitrage-curtail`、`ref-qing-2025-pv-curtailment`、`ref-zeinalzadeh-2017-loadshed-curtail`。
  - 数据事实（`problem_understanding.md` §2）：附件 1 光伏峰值 7612.32 kW 超过负载峰值 5958.97 kW；附件 2 有 10130 个 10 分钟点光伏 > 负载，单点最大盈余 6601.99 kW。
  - 裁定要点：是否引入弃光/盈余变量 `q_spill ≥ 0`（A13）；题面未给售电渠道，故盈余不应产生收益。
- **H7 时间离散与单位**
  - 文献依据：`ref-lin-2024-tou-industrial`、`ref-wongwut-2017-tou-prosumer`（逐时段运行优化）；仅为口径旁证。
  - 裁定要点：`Δt = 1/6 h`，`功率(kW) × Δt → 电量(kWh)`；表 2 的 4 小时时段为分段求和（A12）。
- **H8 模型族**
  - 文献依据：`ref-csee-2023-mg-ems-review`、`ref-carpinelli-2013-dayahead-ilp`、`ref-ignat-2019-cost-dayahead`、`ref-alamir-2025-dayahead-multimg`。
  - 裁定要点：prob01 为 144 段线性优化，原则上**纯 LP** 即可；是否引入整数变量取决于 H5 的互补性处理决定。文献中 LP/MILP 均为标准选择，`ref-nazir-2023-realizable-dispatch` 提示不必急于整数化。

## 5. 结论与对下游阶段的移交

1. prob01 的问题族在文献中是成熟的：**日前/单日、给定价格与负荷曲线、含储能的成本最小调度**（`ref-csee-2023-mg-ems-review` 等）。这为 `mathematical_formulation` 采用确定性 LP 提供了框架级依据。
2. 三条最需要**显式声明**的简化（均有文献提示其为简化而非事实）：
   - 效率取常数 90%（`ref-huang-2022-dynamic-efficiency`、`ref-arima-2024-rte-profile`）；
   - 目标不计电池折旧（`ref-zhang-2015-dayahead-degradation`）；
   - 不计同时充放电（`ref-wang-2024-complementarity`、`ref-nazir-2023-realizable-dispatch`）。
3. 关键约束（供电可靠性、SOC 区间、日能量平衡、弃光盈余）在文献中均有对应的标准写法，本阶段已把来源与适用边界登记到 `citations.yaml`，`assumption_definition` 可在关键假设上绑定对应 `reference_ids`。
4. **文献未解决、必须由假设裁定的事项**：A1（时间戳错位）、A2（结果日期范围与跨日衔接）、A3 的具体作用位置、A5 的充电可行性口径、A13 是否引入 `q_spill`、A15 的 0:00 储电量取值。文献只提供「可迁移的建模范式」，不替题面裁定。
5. 本阶段**未固定任何关键假设**；`problem_understanding.md` §9 的 A1–A16 全部保持待裁定状态。

## 6. 检索式与证据

实际执行的检索（Crossref 书目检索 + DSH `web_search` 交叉发现）：

1. microgrid energy management system optimization battery storage scheduling
2. battery energy storage arbitrage time-of-use pricing optimization
3. optimal scheduling microgrid photovoltaic battery state of charge
4. peak shaving valley filling battery energy storage optimization
5. photovoltaic curtailment energy storage microgrid optimization
6. energy storage charge discharge efficiency state of charge optimal dispatch
7. day-ahead scheduling microgrid linear programming cost minimization
8. energy storage degradation cost scheduling optimization MILP
9. review microgrid energy management systems optimization methods
10. optimal operation battery energy storage microgrid distribution network
11. lithium-ion battery round trip efficiency energy storage system review
12. complementarity constraints charge discharge mutually exclusive battery optimization exact relaxation
13. microgrid power balance constraint renewable energy storage economic dispatch
14. photovoltaic self-consumption battery residential optimization
15. energy storage daily scheduling terminal state of charge constraint
16. energy storage technology cost and performance characterization battery round trip efficiency
17. lithium-ion battery energy storage system techno-economic parameters efficiency lifetime review

证据目录：`runtime/actions/act-70ed2cb7c38141fb/`
- `evidence/discover_crossref.py` / `discovery_raw.json`：第一轮发现（10 组检索式 × 6 条）；
- `evidence/discover_round2.py` / `discovery_round2.json`：第二轮补齐（摘要 + 互补性 + 自消纳）；
- `evidence/discover_round3.py` / `discovery_round3.json`：第三轮补齐（效率参数来源、可靠性、SOC 区间）；
- `run_literature_round.py` / `finish_literature_round.py`：调用 `automm.research` 完成「开始轮次 → 候选入池 → Crossref 核验 → used/rejected 决策 → 结束轮次」，核验结果全部 `verified=True, provider=crossref`，无核验失败。
- `runtime/research_cache/`：Crossref 核验响应缓存（可追溯每条的原始元数据记录）。

## 7. 风险与缺口

- **全文未读**：21 条仅标题级证据。若 `mathematical_formulation` 需要某条来源的具体公式或参数，必须在该阶段另行获取全文，不得以本文件为据直接引用公式。
- **缺中国赛题/中文规范类来源**：未找到且不应引用同题竞赛衍生论文（构成循环论证，参见 crop_2024 文献池对 D 级同题文献的处理先例）。题面事实优先于通用文献。
- **效率 90% 的来源**：该数值由附录 1 直接给定，属题面硬参数，不需要文献标定；文献仅提供「典型效率非恒定、常效率是简化」的边界说明。
- **A1/A2 无文献依据**：属题面与数据层面的约定，若假设阶段无法闭合，按 `config/gates.yaml` 判断是否 `human_model_choice`，而不是用文献强行裁定。
