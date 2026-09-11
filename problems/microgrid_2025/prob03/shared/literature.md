# prob03 文献研究（问题 3：0:00 计划 + 6:00/12:00/18:00 调整与偏差结算）

- 归属：`microgrid_2025` / `prob03`；阶段：`literature_review`
- 同步动作：`act-838614f11d444ac2`（负责人：`literature-researcher`；策略 P4 / action=run_agent）
- 触发：首次进入 prob03 `literature_review`（`prob03/question_manifest.yaml` 的 `stage=literature_review`、`artifacts.literature=false`；`shared/literature.md` 与 `literature_pool.yaml` 原为占位文件）
- 检索轮次：`rnd-47a81eb16e75`（`dry=true`，`dry_reason=all_candidates_decided`）
- 结构化记录：`shared/literature_pool.yaml`（25 条，**全部** `status=used` 且 `verified=true`、`verification_provider=crossref`）
- 题目引用登记：`problems/microgrid_2025/citations.yaml`（prob01 25 条 + prob02 23 条 + 本批 25 条 = **73 条**；ID 与 DOI 均无重复，本动作未改写 prob01/prob02 已登记条目）
- 规则依据：`wiki/literature-citations.md`、`knowledge/evidence-policy.md`、`skills/literature-research-watch/SKILL.md`、`agents/literature-researcher.md`
- 本次**不固定任何关键数学假设**：只提供可核验依据、适用边界与候选口径；裁定权属 `assumption_definition`。

---

## 0. 前提：上游 accepted 假设与团队裁定的效力（必读）

prob03 尚**没有**本地 accepted 假设版本（`question_manifest.yaml`：`active_assumption_version = 0`、`artifacts.assumptions = false`），
故按 `AGENTS.md` 要求，本动作读取**当前小问可用的最新 accepted 上游**——`../prob02/versions/assumption_v001/assumptions.md`
的末节（「待团队选定的决策点」D1–D8、「团队勘误」R1–R5、「团队裁定（prob02 多模型对比与交叉验证要求）」B0–B5、
「团队裁定（formulation 决策点 D1–D8 与 R5 更正）」），该末节效力**高于** prob02 正文、`formulation.md` 与 `agents/*.md` 默认步骤。
prob01 的 `assumption_v003` 末节（D1–D11、E1–E3）经 prob02 §0 承接，本动作通过 prob02 末节与
`../prob03/shared/problem_understanding.md` §0.1/§0.3 执行。

| 编号 | 团队口径（prob02 accepted 末节） | 本动作（prob03 文献阶段）的执行/影响 | 是否遗留冲突 |
|---|---|---|---|
| **A2** | 已闭合：**D1-B 自 2025-01-01 以 `E_init=6000 kWh` 滚动递推（1 月预热）+ D2-A 终端自由 + D8-A 单一长时域 LP** | 本文件把「多日滚动/跨日状态衔接」按**已裁定**陈述；文献（`ref-bhattacharya-2018-multistage-storage` 等）只作机制旁证，不重新裁定 A2 | 无 |
| **R1** | 表 2 端点储电量语义：prob01 单日周期恒 6000 vs prob02 全年滚动随日变化，论文须显式区分 | 本文件与文献池对「多日滚动」的证据按 prob02 裁定陈述；不涉及表 2 数值 | 无 |
| **R5** | 购电上限的**激活阈值** `β ∈ (4218.75, 4375.00] kW`；`10,325.33 kW` 是**非绑定阈值**，两者不可混为一谈 | 本文件凡涉及购电上限/紧急购电激活处**一律用 β**，不使用旧登记的 10,326 kW 说法 | 无 |
| **A17（prob02 侧）** | prob02 完全信息 ⇒ 最优 `q_em ≡ 0`，属 **prob02 侧**口径 | **不得移植**给 prob03：prob03 的对应问题登记为 **A19**（逐时刻信息集），二者信息结构不同（见 §4 P3） | 无（本动作显式区分） |
| **D10（口径丙）** | 5000 kW 作用于并网点侧与电池侧、取更严者；`q_dis ≤ 750.00 kWh`、`c ≤ 833.33 kWh` | 本文件与文献池按 **750.00 / 833.33** 陈述；并**再次声明：该约定是 `team_decision`，prob01 池 25 条、prob02 池 23 条与本批 25 条均无一条文献支撑**，论文不得包装为文献支持 | **遗留（证据类，已显式声明）** |
| **E3 措辞欠账** | `prob01/assumption_v003/version.yaml` 中 AS08「该变量在部分时段必然被激活」与实测 `Σs_t = 0` 不符 | 属 assumption 阶段产物，`literature-researcher` **无权改写**；本文件按「变量保留、最优解允许取 0」陈述 | **遗留（登记类，待 `cross_question_review` 回写）** |
| **α_em = 5** | 题面硬参数 | 本文件与文献池不用文献标定或替代该值；`ref-shang-2017-emergency-pricing` 只支撑「紧急服务高价结算」的机制存在性 | 无 |

> **差异声明（AGENTS.md 要求显式记录）**：
> ① 本动作**未**发现团队口径与现行 `global_symbols.yaml` 之间的新冲突（E1/E2 已于先前动作回写，本轮未再改动）；
> ② 唯一未闭合项与 prob02 相同：**E3 的 AS08 措辞欠账**与 **D10「5000 kW 作用侧」的文献缺口**；
> ③ 本阶段**不引用 prob01/prob02 池的 48 条**作为 prob03 关键假设的门禁来源：`automm.research.check_key_assumptions` 只检查**本小问**池，
> 故本批 25 条刻意覆盖 prob03 自身的全部证据义务（§1 的 E1–E7），使 prob03 池**自洽**；
> ④ `../prob03/shared/problem_understanding.md` §0.3 登记的 C3/E3、C1/E1、C2/E2、R5、R1、U1 六项差异，本动作**逐项接收**并按其口径陈述，未静默沿用旧登记。

---

## 1. 检索目标与范围

prob03 的数值输入仍由题面给定（附件 1 电价列、附件 2 实际负载/光伏、附件 3 整点预报、附录 1 储能参数），
文献需要回答的不是数值，而是**建模口径的合法性**。据此设定 7 条证据义务（E1–E7）：

| 编号 | 待支撑的建模问题 | 对应题面/歧义 |
|---|---|---|
| **E1** | 计划量与调整量之差的**双向分段结算**：0.5× 违约（计划高于调整）与 1.5× 超出（调整高于计划）作为「偏差按价格因子结算」的建模合法性；两结算（计划 → 调整）框架 | 题面问题 3、H8；**A7（高优先）** |
| **E2** | 附件 3 的**整点预报 → 10 分钟功率**的降尺度规则；时间分辨率对调度/储能指标的系统性影响 | **A6（高优先）**、H9 |
| **E3** | **逐决策时刻的信息集**（0:00 计划与 6:00/12:00/18:00 调整各「看得到」什么）的确定性/两阶段/多阶段/滚动谱系；并覆盖开放式问题「是否需要引入其他时刻的预报」（A9）的分析先例 | **A19（高优先，新增）**、**A9** |
| **E4** | **紧急购电 / 供电可靠性**：`q_em ≥ 0` 作为补足量、紧急服务高价结算的制度形式与滚动 EMS 实现 | H1、**A5** |
| **E5** | **分段/非线性结算项的线性化**（`(计划−调整)^+`、`(调整−计划)^+`）与可解性 | A7 的 formulation 落点、H7 |
| **E6** | **问题族与模型族定位**：微网 EMS 是否以 LP/MILP 为主流 | 目标与模型族 |
| **E7** | 表 1/表 2/表 3 与 `result3.xlsx` 四工作表的**填报口径**（调整量是「最终量」还是「增量」） | **A20（新增）**、A18、A11 |

**文献不能裁定的事项（显式排除）**：A6 的降尺度规则取哪一条、A7 的结算方向与基准、A19 的信息结构取哪一读、
A9 的对照方案集合、A5 的 `q_em` 作用位置、A20/A18 的填报写法、A13/A14 的界与上限——这些属**题面/数据/团队选择**，
文献只给出可迁移范式、偏差方向与先例，不替代裁定。**E7 无文献可依**（属题面报告口径），本文件只作登记。

检索式由「对象 + 机理 + 方法 + 限制」组成；两路实际检索式见 §6。

## 2. 核验方法与限制

- **元数据核验**：25 条全部通过 harness `automm.research.verify_reference` 的 Crossref 核验
  （`verified=true`、`verification_provider=crossref`、`verification_error=None`），
  写入 `citations.yaml` 的标题、作者、年份、来源以 Crossref 记录为准；本动作另做「写入标题 vs Crossref `verified_title`」逐条比对，
  **25/25 一致**（证据 `evidence/title_check.txt`）。
- **摘要获取**：本动作用 **OpenAlex** `abstract_inverted_index` 重建摘要，使 **15/25** 条达到 `verification_level=abstract_oa`；
  其余 **10 条**为 `metadata` 级（见 §3 标注）。`authority` 分布 **A=23、B=2**。
- **全文仍未读**：本环境无浏览器级全文抓取能力，**25 条均未逐篇阅读正文**。因此本阶段的引用**只支撑框架级/机制级主张**
  （问题形式、费用/约束结构、方法族、信息结构谱系、降尺度必要性、分辨率影响的**方向**）；
  **任何公式级或定量级引用**（如 `ref-stenzel-2016-temporal-resolution` 的 11.6%、`ref-fusco-2023-multistage-uc` 的 13.58%）
  必须在 `mathematical_formulation` 取得全文后再使用，不得以本文件为据直接引用。
- **分类纪律**：`literature_fact`（来源支持的事实）、`project_assumption`（为本题建立、待验证边界的假设）、
  `agent_inference`（由数据/模型/文献迁移推断）、`team_decision`（团队/题面选择）四类互不冒充。
  本文件所有「建议口径」均为 `agent_inference`，最终裁定属 `assumption_definition`。
- **不得越界**：本动作未修改 `prob01/`、`prob02/` 任何产物，未改 `global_symbols.yaml`、`dependency_graph.yaml`，
  未改任何 accepted 假设/公式/结果/结论；对 `citations.yaml` 只**追加**本批 25 条（`decide_reference` 的既有行为）。
- **跨问查重**：入池前逐条校验，本批 25 条的 ID 与 DOI **均不与 prob01（25 条）、prob02（23 条）重复**
  （证据：`run_literature_round.py` 的查重输出、`evidence/list_pool_ids.py`）。

## 3. 来源清单（按证据义务分组）

等级：A 同行评审期刊；B 权威会议论文（PESGM / ENERGYCON）。本批 25 条**全部为本轮新增**且 `used`（`new → used`）；本轮 `rejected = 0`。
同一条来源可服务多条证据义务（下表按主要义务分组，跨组处在表中注明）。

### 3.1 E1 计划/调整的双向分段结算与偏差惩罚（6 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-zhang-2020-eds-retailers` | A | abstract_oa | 中国远期市场的能量偏差结算（EDS）：偏差是显式成本项、可进入优化目标 |
| `ref-chauhan-2024-dsm-over-under` | A | metadata | 偏差结算区分**超额取电（over-drawl）与欠额取电（under-drawl）**两方向并与市场价挂钩 |
| `ref-matsumoto-2022-imbalance-design` | A | abstract_oa | 不平衡结算设计：**是否/如何对不平衡量施加惩罚激励**、结算价可取自日前参考价 |
| `ref-munhoz-2021-two-settlement` | A | metadata | 两结算（two-settlement）制度：计划先行、偏差在后续以另一价格结算 |
| `ref-asgarpoor-1995-deviation-penalty` | A | abstract_oa | 「偏离经济调度的期望成本惩罚」（EPDED）：偏离计划的显式惩罚项 |
| `ref-danti-2019-intraday-rescheduling` | B | abstract_oa | 仅日前 vs 滚动日内调度：日内再调度改变成本与储能价值；平衡阶段纠正预报误差有成本（**同时服务 E3/A9**） |

### 3.2 E2 光伏整点预报 → 10 分钟降尺度与时间分辨率（6 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-almpantis-2024-minute-downscaling` | A | abstract_oa | 由小时平均合成分钟级 GHI 的降尺度算法；小时平均无法表征快速波动 |
| `ref-grantham-2017-5min-from-hourly` | A | metadata | 由小时观测生成 5 分钟辐照序列 |
| `ref-martins-2021-1min-irradiance` | A | abstract_oa | 由逐时观测生成 1 分钟辐照序列；短时波动来自云过程 |
| `ref-sweeney-2020-forecasting-future` | A | abstract_oa | 可再生预报的分钟—天级时间尺度与「预报使用方式」同等重要（**同时服务 E3/A19**） |
| `ref-barbieri-2017-very-short-term-pv` | A | metadata | 超短期（分钟—小时）PV 预报与云建模综述 |
| `ref-stenzel-2016-temporal-resolution` | B | abstract_oa | 时间分辨率（1–60 分钟）对 PV+BESS 指标的系统性偏差与平滑效应（**方向性证据**） |

### 3.3 E3 逐时刻信息集与多阶段/滚动决策（6 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-bhattacharya-2018-multistage-storage` | A | abstract_oa | 微网购电—储电—放电的**多阶段**随机规划：逐阶段按新信息调整决策 |
| `ref-shinde-2022-multistage-vpp` | A | abstract_oa | 多阶段随机规划建模日内交易：**依据更新预报修改原计划**（**同时服务 E1/A7**） |
| `ref-haberg-2019-stochastic-uc` | A | abstract_oa | 随机机组组合综述：不确定性表示与问题形式谱系 |
| `ref-li-2016-two-stage-rhc` | A | abstract_oa | **两阶段随机规划 + 滚动时域**（SPRHC）：用最新更新预报的反馈补偿不确定性 |
| `ref-matamala-2021-two-stage-stackelberg` | A | metadata | 两阶段随机 Stackelberg + 机会约束的微网运行 |
| `ref-toubeau-2019-probabilistic-forecast` | A | abstract_oa | 概率预报直接嵌入随机优化：**预报质量影响决策质量** |

### 3.4 E4 紧急购电 / 供电可靠性 / 滚动 EMS（3 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-shang-2017-emergency-pricing` | A | metadata | 紧急动态微网电力服务的**定价**机制 |
| `ref-li-2024-energy-purchase-strategy` | A | metadata | 市场环境下微网的**购电策略**优化（**同时服务 E1/A7**） |
| `ref-elkazaz-2020-convex-mpc-rhc` | A | metadata | 凸规划 + MPC/滚动时域实现微网 EMS（工程先例） |

### 3.5 E5/E6 分段结算的线性化与问题族/模型族（4 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-fusco-2023-multistage-uc` | A | abstract_oa | 含二元回素的多阶段 MILP：调整/回素 + 不确定性的标准建模（**同时服务 E3/A19**） |
| `ref-zhai-2009-linear-approx-uc` | A | metadata | 用线性近似替代非线性成本并做误差分析 |
| `ref-viana-2013-milp-uc` | A | metadata | 机组组合的 MILP 建模方法 |
| `ref-thirunavukkarasu-2022-mg-ems-review` | A | abstract_oa | 微网 EMS 优化技术综述：MILP 为主流（问题族定位） |

> 计数一致性：6 + 6 + 6 + 3 + 4 = 25；跨组服务关系已在表中注明，不重复计数。E7（填报口径）**无来源**，见 §4 P7。

## 4. 候选假设族与来源映射（供 `assumption_definition` 裁定）

以下均为**候选口径**，不是已定假设；每条给出文献依据、与本题差异、裁定要点。文献不替题面裁定。

### 候选口径 P1（E1/A7，高优先）：双向分段结算 `C_adj = Σ_t [β_def·p_t·(计划−调整)^+ + β_over·p_t·(调整−计划)^+]`，`β_def=0.5`、`β_over=1.5`
- **文献依据**：`ref-zhang-2020-eds-retailers`、`ref-chauhan-2024-dsm-over-under`、`ref-matsumoto-2022-imbalance-design`、`ref-munhoz-2021-two-settlement`、`ref-asgarpoor-1995-deviation-penalty`、`ref-danti-2019-intraday-rescheduling`、`ref-shinde-2022-multistage-vpp`、`ref-li-2024-energy-purchase-strategy`。
- **可支撑的主张（机制级）**：①「计划/合约量与实际/调整量之差按价格因子结算」是电力市场与调度的**标准制度形式**；
  ② 偏差结算**区分欠/超两个方向**（`ref-chauhan-2024-dsm-over-under`）；③「是否/如何对偏差量施加惩罚激励」与「结算基准取自日前价还是实时价」是**显式设计变量**（`ref-matsumoto-2022-imbalance-design`）；④ 偏离计划的成本可写成显式惩罚项（`ref-asgarpoor-1995-deviation-penalty`）。
- **差异与边界**：以上来源均面向市场参与者/系统级制度，本题是**单一微网、确定性、无报价决策**；
  `β_def=0.5`、`β_over=1.5`、`α_em=5` 由**题面硬给定**，不得用文献重新标定或替代。
- **裁定要点**：① 调整量是「替代量」还是「相对计划的增量」；② 一天内 6/12/18 **多次调整的比较基准**（对当天 0:00 计划，还是对上一次调整）与**结算顺序**；
  ③ `β_def=0.5` 的方向是**罚金/费用项**还是**退款**；④ 调整是否**只作用于发布时刻之后**的时段（不可回溯）；⑤ 同一时段的计划量、调整量、紧急购电量如何在平衡与费用中并存。
  这些均为 `team_decision`/题面口径，文献只能说明「双向分段结算有制度先例」，不能择一。

### 候选口径 P2（E2/A6，高优先）：整点预报 → 10 分钟功率的降尺度规则
- **文献依据**：`ref-almpantis-2024-minute-downscaling`、`ref-grantham-2017-5min-from-hourly`、`ref-martins-2021-1min-irradiance`、`ref-barbieri-2017-very-short-term-pv`、`ref-stenzel-2016-temporal-resolution`、`ref-sweeney-2020-forecasting-future`。
- **可支撑的主张**：① 小时分辨率数据**不足以**表征 PV 的短时波动，必须显式降尺度或生成高分辨率序列（`ref-almpantis-2024-minute-downscaling`）；
  ②「小时 → 分钟」的生成/降尺度是有成熟方法的独立问题（`ref-grantham-2017-5min-from-hourly`、`ref-martins-2021-1min-irradiance`）；
  ③ **低分辨率会平滑波动**（峰谷被削平、PV 与负荷同时性被高估），并给储能/自消纳指标带来系统性偏差（`ref-stenzel-2016-temporal-resolution`，**仅方向性证据**）；
  ④ 预报具有明确的时间尺度语义、其「使用方式」与预报本身同等重要（`ref-sweeney-2020-forecasting-future`）。
- **差异与边界**：文献处理辐照序列或容量设计，本题是**附件 3 的整点 PV 功率预报 → 144 个 10 分钟时段**的**调度口径**；
  `problem_understanding.md` §2 的初版探针证据（取「发布时刻后第 k 个整点的功率点值」时 RMSE 最小）是**数据事实**，非文献结论，不得包装为文献支持。
- **裁定要点**：① 降尺度规则（分段常数 / 线性插值 / 与附件 2 实际列位置对齐）；② **年末边界**：2025-12-31 18:00 预报跨至 2026-01-01（附件 2/4 无 2026 数据）该段是否被消费；
  ③ 0:00 预报覆盖「当天 24 小时」时第 24 点是否越界到次日 0:00。**文献不裁定取哪一条规则**，只支撑「必须显式裁定且不能默认常数」。

### 候选口径 P3（E3/A19，高优先）：逐时刻信息集
- **文献依据**：`ref-bhattacharya-2018-multistage-storage`、`ref-shinde-2022-multistage-vpp`、`ref-li-2016-two-stage-rhc`、`ref-matamala-2021-two-stage-stackelberg`、`ref-toubeau-2019-probabilistic-forecast`、`ref-haberg-2019-stochastic-uc`、`ref-sweeney-2020-forecasting-future`。
- **可支撑的主张**：①「决策分阶段、每阶段**依据新到信息**调整」是多阶段/两阶段决策的标准结构（`ref-bhattacharya-2018-multistage-storage`、`ref-matamala-2021-two-stage-stackelberg`）；
  ②「**依据更新的预报修改原计划**」正是日内/连续市场调整机制的核心（`ref-shinde-2022-multistage-vpp`）；
  ③「先计划、后用最新预报滚动修正」在微网 EMS 中已有可精确求解的实现（`ref-li-2016-two-stage-rhc`）；
  ④ 预报质量/信息集**直接影响最优决策**（`ref-toubeau-2019-probabilistic-forecast`）。
- **差异与边界**：文献的滚动多由**不确定性/信息更新**驱动，且多为随机优化；本题按 AS16 为**确定性**口径，附件 2 是**实际**功率、附件 3 是**预报**。
  故 A19 候选 (a)「预报驱动 + 实时结算」与 (b)「完全信息」的差别不是「要不要建概率模型」，而是**计划/调整各时刻可用哪一套数据**。
- **裁定要点（关键）**：① 题面**明文要求** 0:00 制定计划且 6/12/18 制定**调整**策略——若取 A19 (b)（0:00 即知全天实际值），调整无信息增益、本问的调整机制将退化；
  这是**题面事实与模型内部推论**，不是文献结论（与 prob02 A17 同构，但 prob03 **不得直接移植** prob02 的「完全信息」口径）；
  ② 无论取哪一读，`q_em` 与调整量**必须保留为变量**，不得因预期为零而删除；
  ③「实际结算依据」（用附件 2 实际光伏还是预报值）必须与信息集一并裁定。**文献不替团队在 (a)/(b)/(c) 之间选择。**

### 候选口径 P4（E3/A9）：是否需要引入其他预报时刻
- **文献依据**：`ref-danti-2019-intraday-rescheduling`、`ref-shinde-2022-multistage-vpp`、`ref-li-2016-two-stage-rhc`、`ref-sweeney-2020-forecasting-future`。
- **可支撑的主张**：日内再调度**可以**降低运行成本并改变储能调度与估值（`ref-danti-2019-intraday-rescheduling` 摘要明确「单一日前计划 + 平衡调度不再必然最省」）；
  更频繁的信息更新对应更多的调整机会（`ref-shinde-2022-multistage-vpp`、`ref-li-2016-two-stage-rhc`）。
- **差异与边界**：文献的对比对象是**含风电的系统级仿真**，本问是单微网且 6/12/18 三个时刻由题面给定；其数值不可引用。
- **裁定要点**：必须先固定**评价指标**（全年总购电费下降幅度、紧急购电量/次数、计算成本）与**对照方案集合**（仅 0:00；0:00+6/12/18；追加更多时刻如每 1–3 小时），否则结论不可信；
  该分析按 `config/workflow.yaml` 属**必做 `ablation`**（须在 `optional_stages` 记录 decision + reason），文献只提供「机制存在且可能有收益」的依据。

### 候选口径 P5（E4/A5）：`q_em ≥ 0` 为显式补足变量、紧急服务高价结算
- **文献依据**：`ref-shang-2017-emergency-pricing`、`ref-li-2024-energy-purchase-strategy`、`ref-elkazaz-2020-convex-mpc-rhc`（并与 prob02 池的可靠性来源呼应，但**本问池已自洽**）。
- **可支撑的主张**：① 紧急电力服务存在**独立定价**机制（`ref-shang-2017-emergency-pricing`）；② 购电策略是微网运行优化的核心决策（`ref-li-2024-energy-purchase-strategy`）；
  ③ 滚动时域/MPC 是微网 EMS 的工程主流实现、与可靠性约束兼容（`ref-elkazaz-2020-convex-mpc-rhc`）。
- **差异与边界**：文献多为概率可靠性/服务定价；本题为**确定性 + 不足即紧急购电**，`α_em = 5` 由题面给定，不建概率模型。
- **裁定要点**：① `q_em` 是否仅补足负载缺口、**能否用于储能充电**（prob02 推荐 D4-A 但**团队未正式裁定**，prob03 不得默认沿用为已裁定）；
  ② 「微网提供的电能」口径（等式平衡 vs 净供给）。文献只支撑「把不平衡量显式建模并配独立价格」的形式。

### 候选口径 P6（E5/A7 formulation）：分段结算与调整量的线性化
- **文献依据**：`ref-zhai-2009-linear-approx-uc`、`ref-viana-2013-milp-uc`、`ref-fusco-2023-multistage-uc`、`ref-thirunavukkarasu-2022-mg-ems-review`。
- **可支撑的主张**：① 分段/非线性成本用线性近似或 MILP 表达是成熟做法（`ref-zhai-2009-linear-approx-uc`、`ref-viana-2013-milp-uc`）；
  ② 含**回素（调整）**的多阶段 MILP 可解（`ref-fusco-2023-multistage-uc`）；③ 微网 EMS 以 MILP/LP 为主流（`ref-thirunavukkarasu-2022-mg-ems-review`，同时服务 E6）。
- **裁定要点**：`(计划−调整)^+`、`(调整−计划)^+` 可用辅助非负变量线性化（目标是 `min`，两段价格因子均为正，故辅助变量在最优解处取紧）；
  若 A7 取「多次调整 / 增量叠加」，可能需引入二元变量或状态量，须在 `mathematical_formulation` 记录变量/约束规模与求解代价。
  **不得**用文献的 13.58% 等数值预测本题收益。

### 候选口径 P7（E7/A20/A18/A11）：填报口径——**无文献可依**
- **文献依据：无**。`调整购电量` 工作表每格是「最终购电量」还是「增量」、多次调整的覆盖/叠加规则、表 1/表 2/表 3 报「计划量」还是「最终量」、
  以及表 1「全天购电费」是否含紧急/调整费用，均属**题面报告口径**（`result3.xlsx` 模板与题面表 1–表 4 为唯一依据），文献不参与也不得替代。本文件只作登记。

## 5. 结论与对下游阶段的移交

1. **prob03 的问题族在文献中是成熟的**：含储能的经济调度 + 「计划—调整」两阶段/多阶段偏差结算 + 预报驱动的滚动修正
   （E1+E3+E6 来源）。这为 `mathematical_formulation` 采用确定性 LP（分段线性结算，必要时 MILP）提供框架级依据。
2. **三条最需要显式声明、且文献只能部分支撑的口径选择**：
   - **P1 双向分段结算（A7）**——文献支撑形式与「欠/超两方向分别计价」，**0.5×/1.5× 与结算方向是题面/团队口径**；
   - **P2 整点预报降尺度（A6）**——文献支撑「必须显式降尺度、不能默认常数」，**取哪条规则是团队裁定**；
   - **P3 信息集（A19）**——文献支撑「多阶段/滚动/预报更新」是标准范式，**取 (a)/(b)/(c) 是团队裁定**，且题面要求调整机制必须有意义。
3. **文献未解决、必须由假设裁定的事项**：**A6、A7、A19、A20（高优先）**，A9、A5、A10/A11、A13、A14、A18。本阶段**未固定任何假设**。
   其中 **A2 已由 prob02 裁定、本问承接**，不在 prob03 重复裁定（`problem_understanding.md` §0.3 U1）。
4. **门禁可用性**：prob03 池 25/25 `verified=true` 且 `status=used`，覆盖 E1–E6，`assumption_definition` 可为 prob03 的关键假设
   （双向结算目标项、降尺度规则的形式、储能状态转移与约束集、信息结构、模型族）绑定本池来源，**无需跨小问引用**。
   **E7（A20/A18 填报）与 D10「5000 kW 作用侧」无文献支撑，必须标 `team_decision`/题面事实，不得绑定文献。**
5. **两处结转欠账（不得视为已解决）**：① `prob01/assumption_v003/version.yaml` 的 AS08「必然被激活」措辞（待 `cross_question_review` 回写）；
   ② D10「5000 kW 作用侧」的文献缺口（本轮 25 条同样无一条涉及）。
6. **与 prob01/prob02 池的关系**：三池 ID 与 DOI 完全不重复。prob03 引用已 accepted 的上游口径（AS01/AS04/AS05/AS06+E1/AS09/AS13 等）时，
   应在公式阶段引用 **prob01/prob02 池**的对应文献，或使用本批的对应来源（§3、§4 P5），**不得把未读正文的文献用于公式级引用**。

## 6. 检索式与证据

实际执行的检索（Crossref 书目 16 式 + OpenAlex 定向 16 式；**与 prob01/prob02 已用检索式不重复**）：

Crossref 书目检索（`evidence/discover_prob03.py` → `evidence/discovery_crossref.json`，16 式 × 6 条）：

1. deviation settlement mechanism power market scheduling penalty
2. two price deviation settlement electricity market
3. generator schedule deviation penalty cost power system
4. intraday adjustment day-ahead schedule settlement power
5. imbalance price single price two price settlement market
6. solar photovoltaic forecast temporal downscaling sub-hourly
7. solar irradiance disaggregation minute resolution
8. photovoltaic forecast temporal resolution dispatch impact
9. multistage stochastic programming unit commitment forecast update
10. value of intraday forecast update power system dispatch
11. model predictive control microgrid forecast rolling horizon
12. two-stage stochastic microgrid dispatch uncertainty
13. unserved energy penalty microgrid emergency purchase
14. loss of power supply probability microgrid dispatch optimization
15. piecewise linear cost linearization scheduling optimization
16. mixed integer linear programming microgrid day-ahead scheduling

OpenAlex 定向检索（`evidence/discovery_openalex.json` / `discovery_prob03_digest.txt`，16 式 × 8 条，含摘要重建）：

1. deviation settlement mechanism electricity market penalty schedule
2. deviation penalty cost power generation scheduling market
3. intraday market adjustment day-ahead schedule settlement
4. two-price imbalance settlement electricity market
5. photovoltaic forecast downscaling sub-hourly temporal resolution
6. solar power forecast time resolution dispatch impact
7. solar irradiance disaggregation sub-hourly generation
8. multistage stochastic programming unit commitment forecast
9. value of forecast update renewable energy dispatch
10. rolling horizon model predictive control microgrid forecast
11. two-stage stochastic optimization microgrid energy storage
12. emergency purchase unserved energy microgrid penalty
13. loss of power supply probability microgrid energy management
14. piecewise linear cost function unit commitment linearization
15. hourly solar forecast interpolation dispatch storage
16. value of perfect forecast information energy scheduling

证据目录：`runtime/actions/act-838614f11d444ac2/`
- `evidence/discover_prob03.py` / `discover_prob03_stdout.txt`：两路发现（Crossref + OpenAlex）；
- `evidence/discovery_crossref.json`、`evidence/discovery_openalex.json`、`evidence/discovery_prob03_digest.txt`：原始候选清单与可读摘要；
- `evidence/fetch_candidate_metadata.py` / `candidate_metadata.json` / `candidate_abstracts.txt`：按 DOI 取回的 Crossref 权威元数据 + OpenAlex 重建摘要；
- `evidence/retry_missing_metadata.py` / `retry_missing_metadata_stdout.txt`：三条瞬时 SSL 失败条目的重取记录（最终 25/25 元数据齐全）；
- `evidence/build_candidates.py` / `candidates.json`：候选构建（元数据全部取自 Crossref 记录，人工只补证据义务映射与决策理由）；
- `evidence/list_pool_ids.py`：跨小问 ID/DOI 查重证据；
- `run_literature_round.py` / `literature_round_stdout.txt`：调用 `automm.research` 完成「查重 → 开始轮次 → 候选入池 → Crossref 核验 → used 决策 → 结束轮次」；
- `verification_report.json`：逐条核验结果（`verified` / `provider` / `verified_title` / `error`；本例 25/25 `verified=true, provider=crossref`，`failures=[]`）；
- `evidence/title_check.txt`：写入标题 vs Crossref `verified_title` 逐条比对（25/25 一致）；
- `runtime/research_cache/`：Crossref 核验响应缓存（可追溯每条的原始元数据记录）。

## 7. 风险与缺口

- **全文未读（最大缺口）**：25 条均只到摘要/元数据级（15 abstract_oa + 10 metadata）。若 `mathematical_formulation` 需要具体公式、约束写法或参数，
  必须在该阶段另行获取全文；**不得**以本文件为据直接引用公式或定量结论。特别地：
  `ref-stenzel-2016-temporal-resolution` 的 11.6% 与 `ref-fusco-2023-multistage-uc` 的 13.58% 均为摘要级数值，**不得**用于支撑或质疑本题的任何结论。
- **A6/A7/A19 无文献裁定**：三者都有文献先例，但都**不能在题面/数据内由文献闭合选择**；若 `assumption_definition` 判定互斥项无法在题面内闭合
  （例如 A19 的 (a)/(b) 两读且题面调整机制的解释不唯一），按 `config/gates.yaml` 的 `human_model_choice` 上报，而不是用文献强行裁定。
- **D10「5000 kW 作用侧」文献缺口结转**：本批 25 条**无一条**涉及该团队约定；论文若需文献依据，须补定向检索或取得全文，**不得包装为文献支持**。
- **E3 措辞欠账结转**：`prob01/assumption_v003/version.yaml` 中 AS08「必然被激活」仍未更正（非本阶段可写文件）。
- **10 条为 metadata 级**（`ref-chauhan-2024-dsm-over-under`、`ref-munhoz-2021-two-settlement`、`ref-grantham-2017-5min-from-hourly`、
  `ref-barbieri-2017-very-short-term-pv`、`ref-matamala-2021-two-stage-stackelberg`、`ref-shang-2017-emergency-pricing`、
  `ref-li-2024-energy-purchase-strategy`、`ref-elkazaz-2020-convex-mpc-rhc`、`ref-zhai-2009-linear-approx-uc`、`ref-viana-2013-milp-uc`）：
  其 `supports` 只写到「框架/机制存在」的强度；不得据此推断其模型细节。
- **不引用同题竞赛衍生论文**：未检索、未引用任何解题/赛题衍生来源，避免循环论证。
- **无 rejected 条目**：本批 25 条全部核验通过并 `used`；两路检索命中的无关条目（经济增长、住房市场、深度学习图像识别、区域气候降尺度、
  医学手术排程等）在筛选阶段即被剔除，**未入池**（池内无 `rejected` 记录，与 prob01/prob02 的处理方式一致）。
