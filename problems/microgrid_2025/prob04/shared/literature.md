# prob04 文献研究（问题 4：波动电价下重算问题 2 与问题 3 —— 4-2 / 4-3 两条链）

- 归属：`microgrid_2025` / `prob04`；阶段：`literature_review`
- 同步动作：`act-1b5df12cf74b4ee3`（负责人：literature-researcher）
- 检索轮次：`rnd-c7c0a57a97ea`，`dry=true`、`dry_reason=all_candidates_decided`
- 投入：24 条来源，全部经 `automm.research.verify_reference` 的 Crossref 元数据核验通过（24/24 `verified=true`、`provider=crossref`），
  全部决策 `used`、0 `rejected`；写入标题 vs Crossref `verified_title` **24/24 一致**（`evidence/title_check.txt`）。
- 定位：本文件只做**文献证据的组织与边界声明**，**不裁定任何建模口径**；A8 等决策点的最终登记属 `assumption_definition`。
- 输入依据（只读）：`../prob04/shared/problem_understanding.md`（本问问题理解，两链结构）、`request/problem.md`、
  `../../problem_understanding.md`、`../../global_symbols.yaml`、`../../dependency_graph.yaml`、
  `../prob01/versions/assumption_v003/assumptions.md`（accepted）、
  `../prob02/versions/assumption_v001/assumptions.md`（accepted，含团队裁定 D1–D8、勘误 R1–R8）、
  `../prob03/versions/assumption_v001/assumptions.md`（accepted，含 B0–B7、T5–T9、R9–R26、E1–E11）、
  `../../citations.yaml`（题目级引用登记）。
- **说明**：`prob04` 尚无 accepted 假设版本（`active_assumption_version=0`、`artifacts.assumptions=false`），
  故本动作读取的「最新 accepted 假设版本末节」为**上游 prob01/prob02/prob03 的 accepted 文档末节**与
  **AGENTS.md 的 prob04 团队裁定**；冲突一律以团队口径为准，并在 §0 显式记录。

---

## 0. 前提：团队裁定/勘误的效力与冲突记录（必读）

### 0.1 效力最高的团队口径（本动作执行依据）

| 来源 | 与本动作相关的口径要点 |
|---|---|
| **AGENTS.md「prob04 交付结构」（2026-09-11）** | 一道小问、两套结果：`4-2`（逐日计划 + 5× 紧急购电）与 `4-3`（0:00 计划 + 6:00/12:00/18:00 调整 + 0.5×/1.5× 分段结算 + 紧急购电）；两链**共用附件 4 电价**；`result4-2.xlsx`/`result4-3.xlsx` 必须新写 |
| **AGENTS.md `A8` 团队裁定（2026-09-11）** | **A8 = `A8-(b)`**：0:00 时**当天实时电价（附件 4）未知**，决策只用**历史价格（≤ 前一日 144 点）+ 其他已有附件**；当天电价**到结算时才可知**。派生口径（强制）：① 价格预测器必须**显式给出**并用 2025 全年**滚动回测**（只用 t 日之前信息）报告 MAE/MAPE/分位数；② **决策—结算分离**（决策层用预测价、结算层用实际价），必须给出「价格预报误差的代价」两套口径差；③ `4-3` 的 6:00/12:00/18:00 调整层用**滚动更新的价格预测**，逐层写明信息集；④ **主口径 = 价格点预测 + 确定性 LP**，鲁棒/场景随机只作 `ablation` 对照；⑤ **禁止**任何「全天电价已知」表述（A8-(a) 已否）；⑥ **两条链共用同一价格预测器与同一结算口径** |
| **prob03 accepted `assumption_v001` 末节** | `B0` 主结果唯一来源 `M1`；`B1` D1–D12 采纳 + `T1` 计划层目标 `min Σ p·b` + `T2` D2-B/D2-C 强制对照 + `T3` 降尺度能量不守恒披露；`B2` `M1`–`M8`；`B3` 交叉验证（含 `D_req`/`D_full` 分报）；`B4` 判据 `C1`–`C9`；`B5` 公平性与隔离（附件 4 属 prob04，prob03 不得使用）；`B7` formulation 阻塞清单；`T5`–`T9`；`E1` 附件 3 日期前向填充、`E2` RMSE 口径、`E3` 不得以 RMSE 作跨时刻比较轴、`E4` 文献证据边界、`E6` `total_*` 字段口径、`E9` 购电上限分问引用、`E10`/`E11` L6 与 C3 FAIL 的处理 |
| **prob02 accepted `assumption_v001` 末节** | A2 = 滚动递推 `D1-B` + 终端自由 `D2-A` + 单一长时域 LP `D8-A`；`R1` 表 2 端点语义（多日滑窗逐日切片，与 prob01 单日周期区分）；`R5` 购电上限激活阈值 `β ∈ (4218.75, 4375.00] kW`（10,326 kW 只是非绑定阈值）；`D10` + 勘误 `E1`：`q_dis ≤ 750.00 kWh`、`c ≤ 833.33 kWh`、两侧功率 ≤ 5000 kW |
| **prob01 accepted `assumption_v003` 末节** | `D1-A` 左端点口径（计划窗 0:10→24:10）；`D9` 目标 `min Σ p·b`（元，**不乘** `Δt`）；`D10` 口径丙；勘误 `E1`–`E3` |

### 0.2 冲突点与差异记录（**不得静默沿用旧登记**）

| 编号 | 冲突/差异 | 旧登记 | 本动作执行 | 去向 |
|---|---|---|---|---|
| **C4-1** | `prob04/shared/problem_understanding.md`（`act-b680a52c76184c4b`）§7 把 **A8 登记为「待裁定、mathematical_formulation 的前置阻塞项」** | 「A8 待裁定」「本阶段未固定」 | **A8 已由团队裁定为 `A8-(b)`**（AGENTS.md，2026-09-11）：0:00 未知当天电价、决策用历史价格、结算用实际价。本文件全文按 `A8-(b)` 陈述，并把 A8-(b) 的六条派生口径列为文献义务 F2 | 文档欠账：`problem_understanding.md` 的 A8 状态与 §10「不阻塞声明」需在 `assumption_definition` 更新；本动作无权改写上游文档 |
| **C4-2** | **A21（两链信息集是否一致）** 在 problem_understanding §7 仍为「必须裁定」 | 候选 (a) 两链共用 / (b) 分链采用 | A8-(b) 派生口径第 ⑥ 条已实质闭合 A21：**两链共用同一价格预测器与同一结算口径**，差异仅在 `4-3` 多出 6/12/18 调整层与 0.5×/1.5× 分段结算；本文件按此陈述 | `assumption_definition` 登记 A21 = 共用 |
| **C4-3** | **A23（`4-2` 在完全信息下 `q_em ≡ 0`？）** 承接 prob02 `A17` 的「完全信息 ⇒ 最优 `q_em ≡ 0`」 | problem_understanding §7 保留该同构问题 | 在 `A8-(b)` 下**前提不再成立**：0:00 只有预测价，结算用实际价，`q_em` 由「计划/预测口径 vs 实际口径」的缺口在结算层产生（与 prob03 `F3` 结构同源）。本文件只给出文献边界，**不裁定其数值是否为 0** | `assumption_definition` 重述 A23；文献不替代 |
| **C4-4** | **A22（结算倍数的价格基数）** | problem_understanding §7 要求「显式登记以免沿用 prob02/prob03 的旧价格输入」 | 与 `H10`（价格来源唯一 = 附件 4）一致，已无冲突；本文件与文献池凡涉 `α_em·p`、`β_def·p`、`β_over·p` 均以**附件 4 的 `p_{d,t}`** 为基数 | 无需裁定，登记即可 |
| **C4-5** | **D9-B（弃光界收紧为物理盈余）** 被 prob03 登记为 **prob04 前置条件** | prob03 主口径取 `D9-A`（`0 ≤ s ≤ PV·Δt`） | prob04 **必须显式裁定**（采纳/不采纳/分链采纳）；**本批 24 条文献无一条涉及弃光界的紧松选择**，文献不替代裁定（且本问 4-2/4-3 均无售电收益，按 prob02 经验 `s` 的上界在最优解处通常不紧，但该判断须由实现/sanity 复核） | `assumption_definition` 裁定；文献侧标记为**无来源** |
| **C4-6** | **`D10`「5000 kW 作用侧」文献缺口** | prob01 池 25 条、prob02 池 23 条、prob03 池 25 条均无一条涉及 | **prob04 本批 24 条同样无一条涉及**；`5000 kW` 作用侧为 `team_decision`（口径丙），论文**不得**包装为文献支持 | 结转 `cross_question_review` |
| **C4-7** | **`E3`（AS08「必然被激活」措辞）** | `prob01/assumption_v003/version.yaml` 中 AS08 仍含该措辞，与实测 `Σs_t=0` 不符 | 本文件按「变量保留、最优解允许取 0」陈述；权威回写待 `cross_question_review`（属 assumption 阶段产物，本 Agent 无权改写） | 结转 |
| **C4-8** | **`R5`（购电上限阈值表述）** / **`R1`（表 2 端点语义）** | prob02 已裁定 | 本文件与文献池一律按 `β ∈ (4218.75, 4375.00] kW` 表述（不得再称「低于 10,326 kW 即强制 `q_em>0`」）；表 2 端点须区分 prob01（单日周期恒 6000）与 prob02/prob04（滚动逐日切片） | 下游论文与图表 |
| **C4-9** | **`E1`（放电上限 750.00 kWh）** 与 `global_symbols.yaml` 的 833.33 历史冲突 | 团队勘误 E1 已裁定 750.00 | 本文件与文献池按 `q_dis ≤ 750.00`、`c ≤ 833.33` kWh 陈述；文献不涉及该口径 | 沿用团队勘误 |
| **C4-10** | **`A18`（表 3/紧急购电填报口径）** | prob02/prob03 已裁定 `D11`/`A18` | 本批 24 条文献**无一条涉及填报口径**（属题面报告口径），不得虚构文献依据 | `assumption_definition` 依题面表 4 示例裁定 |

> **差异声明**：本动作只新增 prob04 文献池与引用登记，**未修改** `data/`、`request/`、`global_symbols.yaml`、
> 任何假设/公式/结果/结论历史，**未创建 task、未运行求解器、未产生任何交付数值**。

---

## 1. 检索目标与范围

prob04 的文献义务按**证据义务 `F1`–`F8`** 组织，并标注其归属链（`4-2` / `4-3` / 两链共用）。
`F1`–`F3`/`F7` 服务于 `A8-(b)` 的新情景；`F4` 服务 `4-3` 的结算结构；`F5` 服务 `4-2` 的紧急购电与日前—实时结构。

| 编号 | 待支撑的建模问题 | 归属链 | 对应题面/待决项 |
|---|---|---|---|
| **F1** | **实时电价（RTP）下的储能套利与购电策略**：按逐时段价格做充放电、以购电成本/套利收益为目标，受容量/效率/功率约束 | 4-2（主）/ 4-3 | 题面问题 4；AS05/AS06；`A8-(b)` 派生 ④ |
| **F2** | **价格可观测性与价格预测（`A8-(b)` 的核心）**：F2a 预测器族（历史同时段均值 / 前一日同时段 / 季节+时段双因子 / 回归或 AR）；F2b 预测精度评估与**滚动回测**（MAE/MAPE/分位数、简单基准对照）；F2c **预测误差的经济代价与决策—结算分离**；F2d **滚动更新**（`4-3` 的 6/12/18 时刻） | 两链共用 | **`A8-(b)` 派生 ①②③** |
| **F3** | **价格波动性与尖峰**：波动来源、量级方向及其对储能收益/风险的影响 | 两链共用 | 附件 4 的高日内波动（诊断事实） |
| **F4** | **`4-3` 链的两结算/日内调整与偏差（不平衡）结算惩罚**：计划量 vs 调整量/实际量的偏差按惩罚价双向结算 | 4-3（专用） | 题面问题 3；承 prob03 `B1-D2-A`、`T2`；`D11`/`A18` |
| **F5** | **`4-2` 链的日前—实时结构与紧急购电**：实时价格波动下计划购电 + 缺口紧急购电（`α_em = 5`） | 4-2（专用） | 题面问题 2/4；`H12`；`A23` |
| **F6** | **价格不确定性下的对照口径**：随机 / 鲁棒 / 在线 / 概率预测 ⇒ **只作 `ablation` 对照** | 两链共用 | **`A8-(b)` 派生 ④⑤** |
| **F7** | **问题族定位**：微网 EMS + 可再生 + 储能 + 电价的优化问题族（保证 prob04 池自洽） | 两链共用 | 模型族（LP） |
| **F8** | **填报口径与题面事实**：表 3 / `result4-*.xlsx` 的区间合并、端点标签、`J_d=0` 写法；模板身份（`result4-2≡result2`、`result4-3≡result3`） | 两链共用 | **`A18`（无文献可依）** |

### 1.1 与上游文献池的关系（**不重复登记**）

- `4-3` 链的**偏差结算制度、多阶段/滚动决策、光伏预报降尺度**等口径已在 prob03 池（25 条）有 verified+used 来源；
  `4-2` 链的**紧急购电/可靠性、完全信息价值、跨日衔接/滚动时域**等已在 prob02 池（23 条）有来源；prob01 池（25 条）覆盖基础调度模型族。
- 本批**不把上游池条目复制进 prob04 池**（跨小问查重通过：24 条候选的 ID 与 DOI 与 prob01/prob02/prob03 池、`citations.yaml` **均无重复**），
  以避免 `decide_reference` 覆写已登记条目。承接关系在 §4 以「承 probNN 池 `<id>`」的形式**带出处引用**。
- 但 **prob04 池必须自洽**：`check_key_assumptions` 只读本小问池，故本批 24 条**独立覆盖** `A8-(b)` 的价格预测与决策—结算分离、
  `4-3` 的两结算/偏差惩罚、`4-2` 的日前—实时结构，以及微网 EMS 问题族定位（`F7`）。

---

## 2. 核验方法与限制

- **发现**：两轮检索——第一轮 Crossref 书目式 15 式 + OpenAlex 定向 6 式（`evidence/discover_prob04.py`，去重后 125 个 DOI），
  第二轮定向 8 式（`evidence/discover_round2.py`，去重后 103 个 DOI），合计原始候选 228 条；经标题/摘要筛选后保留 24 条候选。
- **核验**：全部经 `automm.research.verify_reference`（Crossref 优先、OpenAlex 兜底），结果 24/24 `verified=true`、`provider=crossref`、`verification_error=None`；
  响应缓存于 `runtime/research_cache/`。
- **摘要来源**：`evidence/fetch_candidate_metadata.py` 逐条取回 Crossref 记录与 OpenAlex `abstract_inverted_index` 重建摘要
  （`evidence/candidate_abstracts.txt`、`candidate_metadata.json`）。**15 条取得开放摘要（`abstract_oa`）、9 条仅达元数据级（`metadata`）**：
  `ref-antweiler-2021-storage-microeconomics`、`ref-campillo-2016-rtp-residential`、`ref-tschora-2022-da-price-forecasting-ml`、
  `ref-myttenaere-2016-mape-regression`、`ref-mathaba-2014-price-forecast-benefit`、`ref-hodge-2018-forecast-value-storage`、
  `ref-akbari-2019-stochastic-robust-arbitrage`、`ref-scharff-2016-elbas-intraday`、`ref-hai-2025-microgrid-price-ems`（共 9 条）。
- **限制（必须随引用一起陈述）**：**24 条均未逐篇阅读正文**，本阶段引用只支撑**框架级/机制级**主张；
  任何**公式级或定量级**引用（含预测误差量级、收益提升百分比、阈值）须在 `mathematical_formulation` 或更晚阶段取得全文后再使用。
  特别地：`ref-staffell-2016-maximising-storage-value` 的「无预知可得最优利润 75–95%」、`ref-kapoor-2023-nz-price-forecasting` 的「sMAPE/MASE 改善 2%–3%」、
  `ref-ibebuchi-2025-daep-endogenous-predictors` 的「MAE 6.26 USD/MWh」均为**该文案例数值**，**不得**引用为本问结论或用于标定。
- **权威分级**：A = IEEE TPWRS/TSG、Applied Energy、Energy、Energy Economics、Energy Policy、Neurocomputing、INFORMS Journal on Computing、Energy and AI；
  B = Batteries / Energy Reports / EPSR / Forecasting / J Energy Storage / Sustainable Cities and Society。本批 **A 级 17 条、B 级 7 条**。

---

## 3. 来源清单（按证据义务分组）

> 每条均含 ID、等级、核验级别与支持对象；完整字段（作者、摘要、适用条件、差异、决策理由）见 `shared/literature_pool.yaml`。

### 3.1 F1 实时电价下的储能套利与购电策略（5 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-krishnamurthy-2018-arbitrage-da-rt` | A | abstract_oa | 日前+实时价格双重不确定性下的储能套利收益最大化；随机方法优于确定性基准 |
| `ref-staffell-2016-maximising-storage-value` | A | abstract_oa | 套利收益最大化算法；**完美预知 vs 无预知**的对照设计 |
| `ref-paulauskas-2024-battery-scheduling-arbitrage` | B | abstract_oa | 按价格曲线做充放电调度、显式含容量/效率/功率界（与 AS05/AS06 同构） |
| `ref-zhang-2021-arbitrage-technologies` | B | abstract_oa | 「价格曲线 → 充放电时段 → 收益」的确定性优化范式；往返效率是关键参数 |
| `ref-komorowska-2024-liion-price-arbitrage` | A | abstract_oa | 长历史价格下的充放电时段集合、循环次数与套利利润（价格波动来源） |

### 3.2 F2a/F2b 价格预测器族与滚动回测/误差指标（6 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-chitsaz-2018-price-forecast-btm-storage` | A | abstract_oa | 实时市场价格预测：**多步长模型 + 小时内滚动更新 + 尖峰检测**，并接入储能调度 |
| `ref-tschora-2022-da-price-forecasting-ml` | A | metadata | 日前价格预测的机器学习模型族定位 |
| `ref-lago-2018-spot-price-deep-learning` | A | abstract_oa | 27 种预测器的**公平基准比较**；简单模型常不劣于复杂模型 |
| `ref-kapoor-2023-nz-price-forecasting` | A | abstract_oa | 统计 vs ML + 特征选择；以 **sMAPE/MASE** 评估并设基准对照 |
| `ref-ibebuchi-2025-daep-endogenous-predictors` | B | abstract_oa | **滚动窗口交叉验证（逐日滑动）** + 只用预测时点可得信息；预测接入投标决策 |
| `ref-myttenaere-2016-mape-regression` | A | metadata | MAPE 在回归预测中的偏置与局限 ⇒ 应同时报绝对误差指标 |

### 3.3 F2c 预测误差的经济代价与决策—结算分离（5 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-staffell-2016-maximising-storage-value` | A | abstract_oa | 无预知 vs 完美预知的收益差（信息价值的可核验对照） |
| `ref-antweiler-2021-storage-microeconomics` | A | metadata | 套利上限 + 价格预测在储能价值中的作用（框架） |
| `ref-mathaba-2014-price-forecast-benefit` | B | metadata | 以**调度成本/收益增量**度量价格预测的经济价值 |
| `ref-hodge-2018-forecast-value-storage` | A | metadata | 预测改进的价值必须与储能**联合评估**（本问价格误差 + 光伏预报误差并存） |
| `ref-khani-2015-online-adaptive-rtod` | A | abstract_oa | **预测价决策 / 事后价结算**；预测不准确显著降低收益；在线修正可提升收益 |

### 3.4 F2d 滚动更新与序贯信息揭示（3 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-chitsaz-2018-price-forecast-btm-storage` | A | abstract_oa | 小时内滚动时域的价格预测更新（`4-3` 6/12/18 时刻的最近先例） |
| `ref-jiang-2015-hour-ahead-bidding-adp` | A | abstract_oa | 信息在时间上逐步揭示时的序贯/小时前决策；以完全信息最优为基准 |
| `ref-khani-2015-online-adaptive-rtod` | A | abstract_oa | 用滚动可得的历史价格在线修正目标（对照口径） |

### 3.5 F3 价格波动性与 RTP 适用性（2 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-komorowska-2024-liion-price-arbitrage` | A | abstract_oa | 可再生渗透提高电价波动 → 放大套利机会（方向性事实） |
| `ref-campillo-2016-rtp-residential` | A | metadata | RTP 的收益/风险取决于主体是否具备主动调度能力（本问即储能+购电优化） |

### 3.6 F4 `4-3` 链：两结算/日内调整/偏差惩罚（4 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-scharff-2016-elbas-intraday` | A | metadata | 连续日内市场可在信息更新后**修正日前头寸**（调整层的制度存在性） |
| `ref-bottieau-2020-imbalance-settlement-forecast` | A | abstract_oa | 不平衡/偏差量显式建模并按结算价计价；偏差结算机制的成熟范式 |
| `ref-yang-2023-da-rt-shared-storage` | B | abstract_oa | **日前计划 → 实时偏差结算**两阶段；储能可降低实时偏差惩罚 |
| `ref-yang-2020-deviation-penalty-distribution` | A | abstract_oa | 对「实时量 vs 成交量」偏差施加**惩罚电价**的制度与建模形式 |

### 3.7 F5 `4-2` 链：日前—实时结构与紧急购电（2 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-krishnamurthy-2018-arbitrage-da-rt` | A | abstract_oa | 日前与实时两个价格阶段的决策结构 |
| `ref-yang-2023-da-rt-shared-storage` | B | abstract_oa | 日前中标量 + 实际量 → 实时市场偏差惩罚 |

### 3.8 F6 价格不确定性对照口径（3 条，**仅 ablation**）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-akbari-2019-stochastic-robust-arbitrage` | B | metadata | 随机—鲁棒混合优化作为价格不确定下的对照口径 |
| `ref-jiang-2015-hour-ahead-bidding-adp` | A | abstract_oa | ADP/无分布策略与完全信息最优基准的对比 |
| `ref-oconnor-2025-conformal-price-forecast` | A | abstract_oa | 概率/区间价格预测（分位数）及其对储能交易收益的影响 |

### 3.9 F7 问题族定位（1 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-hai-2025-microgrid-price-ems` | B | metadata | 微网 EMS + 可再生 + 储能 + 电价的问题族定位（保证本池自洽） |

---

## 4. 候选口径与来源映射（供 `assumption_definition` 裁定，**本阶段不裁定**）

> 每组给出：`A8-(b)` 团队口径下的**候选实现选择**、可绑定来源、与本题差异、裁定要点。
> **凡标 `<无来源>` 的组，必须由题面事实或 `team_decision` 承担，不得绑定文献。**

### P1（F1，4-2 主 / 4-3 共用）：`4-2` 的确定性 LP 目标
- **候选**：`min Σ_t p̂_t·b_t`（购电成本，元，不乘 `Δt`；`p̂` 为**预测价**）＋紧急购电项 `Σ α_em·p̂_t·q_em,t`。
- **来源**：`ref-paulauskas-2024-battery-scheduling-arbitrage`、`ref-zhang-2021-arbitrage-technologies`、`ref-staffell-2016-maximising-storage-value`。
- **差异**：这些文献以收益最大化/套利为目标、无「紧急购电」项；本问为微网购电成本最小化。
- **裁定要点**：目标量纲（承 prob01 `D9`，不乘 `Δt`）与费用分项（`C_plan`/`C_em`）必须在 `formulation` 写清。

### P2（F2a/F2b，两链共用，**`A8-(b)` 强制项**）：显式价格预测器 + 滚动回测
- **候选**：历史同时段均值 / 前一日同时段 / 季节+时段双因子 / 回归或 AR；**必须**用 2025 全年做滚动回测（只用 t 日之前信息），报告 MAE/MAPE/分位数。
- **来源**：`ref-chitsaz-2018-price-forecast-btm-storage`、`ref-lago-2018-spot-price-deep-learning`、`ref-kapoor-2023-nz-price-forecasting`、`ref-ibebuchi-2025-daep-endogenous-predictors`、`ref-myttenaere-2016-mape-regression`。
- **差异**：文献多为小时级、以精度为唯一目标；本问为 10 分钟粒度、以**决策费用**为最终目标，且预测器族由团队指定。
- **裁定要点**：必须选定**唯一主预测器**（主口径只出一个）并保留简单基准对照；预测器族的比较结果只作证据。
- **边界**：文献支撑「必须显式预测 + 滚动回测 + 基准对照 + 报告相对与绝对误差」；**不支撑**任何具体的 MAPE 数值或预测误差分布假设。

### P3（F2c，两链共用，**`A8-(b)` 强制项**）：决策—结算分离与「价格预报误差的代价」
- **候选**：决策层（计划层与 4-3 调整层）用**预测价**、结算层用**附件 4 实际价**；费用分解**同时**给出按预测价与按实际价两套口径之差。
- **来源**：`ref-khani-2015-online-adaptive-rtod`（预测价决策/事后价结算，预测不准显著降低收益）、`ref-staffell-2016-maximising-storage-value`（完美预知 vs 无预知的对照设计）、`ref-mathaba-2014-price-forecast-benefit`、`ref-antweiler-2021-storage-microeconomics`、`ref-hodge-2018-forecast-value-storage`。
- **差异**：文献的误差代价多以市场收益差表征；本问以**微网购电总费用差**表征，且与 prob03 的「光伏预报误差代价」并存（两类误差必须分开归因）。
- **裁定要点**：两套口径的**分解方式**（哪些项按预测价、哪些项按实际价）必须在 `formulation` 逐项写明，避免「部分用预测价、部分用实际价」的含糊陈述。

### P4（F2d，4-3 专用）：6:00/12:00/18:00 调整层的滚动价格预测
- **候选**：每个调整时刻的信息集 = 截至该时刻**已实现的实际价** + 历史价格（≤ 前一日）+ 该时刻的**附件 3 光伏预报**（承 prob03 `D5-A`/`D6-A`）。
- **来源**：`ref-chitsaz-2018-price-forecast-btm-storage`（小时内滚动更新）、`ref-jiang-2015-hour-ahead-bidding-adp`。
- **差异**：文献的滚动更新多为等间隔多小时；本问只有题面给定的 3 个调整时刻。
- **裁定要点**：**逐层**写明信息集（这是 `B7-2` 的同款要求）；「当天电价到结算时才可知」不得被调整层违反。

### P5（F4，4-3 专用）：`0.5×`/`1.5×` 双向分段结算
- **候选**：`C_adj = Σ[β_def·p_t·(b_t−q_t)^+ + β_over·p_t·(q_t−b_t)^+]`，`β_def=0.5`、`β_over=1.5`，`p` **= 附件 4 实际价**。
- **来源**：`ref-bottieau-2020-imbalance-settlement-forecast`、`ref-yang-2020-deviation-penalty-distribution`、`ref-yang-2023-da-rt-shared-storage`、`ref-scharff-2016-elbas-intraday`。
- **承 prob03 池**：偏差结算制度与多结算参照另见 prob03 池 `ref-zhang-2020-eds-retailers`、`ref-chauhan-2024-dsm-over-under`、`ref-matsumoto-2022-imbalance-design`、`ref-munhoz-2021-two-settlement`（**不重复登记**）。
- **差异**：文献的偏差价多由市场出清内生决定；本问 `β_def/β_over` 是**题面硬给定**，文献**只支撑形式、不支撑系数**。
- **裁定要点**：`T2` 的读法 A（主口径）与读法 B/C（强制对照）属 prob03 团队裁定，prob04 承接时须一并承接；填报口径 `A18` `<无来源>`。

### P6（F5，4-2 专用）：紧急购电 `α_em = 5` 与缺口
- **候选**：`q_em,t ≥ 0` 仅补足「负载 − (购电 + 光伏 + 放电)」缺口，结算价 `α_em·p_t`（`p` = 附件 4 实际价）。
- **来源**：`ref-krishnamurthy-2018-arbitrage-da-rt`、`ref-yang-2023-da-rt-shared-storage`；机制级另承 prob02 池的紧急服务定价与可靠性来源。
- **差异**：`α_em = 5` 为**题面硬参数**，文献**不得用于标定或质疑**；文献只支撑「高价补足缺口」这一制度形式。
- **裁定要点**：`A23`（`q_em` 是否恒零）在 `A8-(b)` 下须**重新论证**：预测价决策 + 实际价结算会产生计划—实际缺口，`q_em` 是否被激活取决于缺口与储能可行域，**不得**直接移植 prob02 `A17` 的「完全信息 ⇒ 恒零」。

### P7（F6，两链共用，**仅 ablation**）：不确定性对照口径
- **候选**：随机规划（场景）/ 鲁棒优化 / 概率（区间）预测 / 在线或 ADP 策略；**只作 `ablation` 对照**，不得成为主口径。
- **来源**：`ref-akbari-2019-stochastic-robust-arbitrage`、`ref-jiang-2015-hour-ahead-bidding-adp`、`ref-oconnor-2025-conformal-price-forecast`。
- **裁定要点**：主口径 = **点预测 + 确定性 LP**（`A8-(b)` 派生 ④）；对照口径的数值只能在 `ablation` 出现并标明口径差异。

### P8（F8，两链共用）：填报口径与模板身份 `<无来源>`
- **候选**：表 3 / `result4-2.xlsx` / `result4-3.xlsx` 的工作表集合、区间合并、端点标签、`J_d=0` 写法。
- **来源**：**无**（属题面报告口径）。`result4-2.xlsx ≡ result2.xlsx`、`result4-3.xlsx ≡ result3.xlsx`（逐字节相同）为**附件 5 的发放方式**，非文件损坏；prob04 必须**新写**这两个文件。
- **裁定要点**：`A18`/`D11` 承接 prob02/prob03 团队裁定；**严禁**把 prob02/`result2.xlsx`、prob03/`result3.xlsx` 的数值当作 prob04 结果。

---

## 5. 结论与对下游阶段的移交

### 5.1 文献能支撑什么（框架级/机制级）

1. **`A8-(b)` 的建模要素在文献中是成熟范式**：价格预测器显式建模（F2a）、滚动回测与基准对照（F2b）、
   预测误差的经济代价（F2c）、滚动更新（F2d）均有 A/B 级先例。
2. **`4-2` 与 `4-3` 的确定性 LP 主口径**与「按价格曲线调度 + 容量/效率/功率约束」的结构一致（F1），
   且「预测价决策 + 实际价结算」的分离口径有直接先例（`ref-khani-2015-online-adaptive-rtod`）。
3. **`4-3` 的偏差/不平衡分段结算**在制度与建模形式上均有先例（F4），但**具体系数（0.5×/1.5×）与 `α_em=5` 只由题面给定**。
4. **不确定性对照口径**（随机/鲁棒/概率预测/在线）有充分先例（F6），可在 `ablation` 中作为对照，且不改变主口径。

### 5.2 文献不能支撑什么（**必须由题面或 `team_decision` 承担**）

- `α_em = 5`、`β_def = 0.5`/`β_over = 1.5` 的**具体数值**；附件 4 的价格分布与预测误差**量级**。
- `5000 kW` 作用侧（`D10`，team_decision）；`A18` 填报口径；`D9-B` 弃光界裁定。
- 任何「0:00 全天电价已知」的表述（A8-(a) 已被团队否定，`sanity`/图表/论文**不得**出现该类表述）。
- `q_em` 在 `4-2` 的 `A8-(b)` 下是否恒零：属模型内推论 + 团队裁定，**不得**包装为文献结论。

### 5.3 门禁可用性（`check_key_assumptions`）

- prob04 池 **24/24 `verified=true` 且 `status=used`**，覆盖 F1–F7；`assumption_definition` 可在**本小问池内**为 prob04 的关键假设
  （价格输入与预测器、决策—结算分离、`4-2` 目标与约束、`4-3` 分段结算形式、模型族）绑定 `verified+used` 来源。
- **`F8`（`A18` 填报）与 `D9-B`、`D10` 必须标 `team_decision`/题面事实**，不得绑定文献。
- 上游承接项的文献义务已由 prob01/02/03 池清偿；prob04 若把某承接项标为 `key=true`，须在 prob04 池内能找到对应来源，
  否则应标 `inherited` 且 `key=false`（prob02 处理 AS01/AS08/AS09/AS13 的同款做法）。

---

## 6. 检索式与证据

- 第一轮 Crossref 书目 15 式：实时电价储能套利、实时电价下储能调度、动态定价与需求响应、电价预测（日前/实时/ML）、
  完美信息价值、滚动时域 MPC、随机优化与价格不确定性、价格波动与套利价值、TOU vs RTP、微网 EMS + RTP + MILP、
  居民 RTP + 储能、日前—实时价差、在线算法与竞争比、工业负荷 RTP 调度、价格尖峰与储能收益。
- 第二轮定向 8 式：不平衡结算与风功率预报误差惩罚、两结算市场储能投标、连续日内市场与预报更新、
  确定性最优储能调度与完美预视基准、价格预测误差的经济影响、MAPE 等误差指标比较、RTP 波动与储能收益、
  偏差结算机制与可再生预报惩罚。
- 证据文件（`runtime/actions/act-1b5df12cf74b4ee3/`）：
  - `evidence/discover_prob04.py`、`discovery_crossref.json`、`discovery_openalex.json`、`discovery_digest.txt`（第一轮）
  - `evidence/discover_round2.py`、`discovery_round2.json`、`discovery_round2_digest.txt`（第二轮）
  - `evidence/fetch_candidate_metadata.py`、`candidate_metadata.json`、`candidate_abstracts.txt`（选定候选的元数据与摘要）
  - `evidence/candidates.json`（24 条候选的完整字段）
  - `evidence/title_check.txt`（写入标题 vs Crossref `verified_title` 逐条比对，24/24 一致）
  - `run_literature_round.py`、`literature_round_stdout.txt`、`verification_report.json`（轮次执行记录与核验报告）
- 引用登记：`problems/microgrid_2025/citations.yaml` 由 **73 条增至 97 条**（本批新增 24 条，ID 与 DOI 均无重复），
  对 `citations.yaml` 的操作**仅为 `decide_reference` 的追加**，未改写 prob01/prob02/prob03 已登记条目。

---

## 7. 风险与缺口

1. **全文未读**：24 条均只到摘要/元数据级（15 `abstract_oa` + 9 `metadata`；含 `ref-hai-2025-microgrid-price-ems` 等），
   引用只支撑框架级/机制级主张；公式级/定量级引用须取得全文后再用。
2. **价格预测器与误差量级无文献标定**：附件 4 的预测误差必须由 `assumption_definition`/`implementation` 用 2025 全年滚动回测**自行给出**，
   文献不能替代；本批文献只支撑「必须回测 + 基准对照 + 报告相对与绝对指标」。
3. **`D9-B` 弃光界**：prob03 登记为 prob04 前置条件，本批文献**无一条**涉及，须由团队显式裁定。
4. **`D10` 5000 kW 作用侧与 `A18` 填报**：无文献支撑，论文不得包装为文献支持。
5. **`A23` 的重述风险**：若 `assumption_definition` 直接沿用 prob02 `A17` 的「完全信息 ⇒ `q_em≡0`」，将与 `A8-(b)` 冲突；
   必须在 prob04 语境下重新论证。
6. **跨池引用纪律**：本批对 prob02/prob03 池的承接是**带出处引用**（§4），未复制登记；`cross_question_review` 时应核对两处口径一致。
7. **上游文档欠账**：`problem_understanding.md` 的 A8 状态（C4-1）、prob01 `AS08` 措辞（C4-7）等仍在，属上游阶段产物。
