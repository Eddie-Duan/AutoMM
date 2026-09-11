# prob02 文献研究（问题 2：逐日计划购电 + 紧急购电）

- 归属：`microgrid_2025` / `prob02`；阶段：`literature_review`
- 同步动作：`act-187a164154404f6c`（负责人：`literature-researcher`）
- 触发：首次进入 prob02 `literature_review`（`workflow_state.current_stage = literature_review`，`prob02` 的 `shared/literature.md` 与 `literature_pool.yaml` 原为占位文件）
- 检索轮次：`rnd-7881293f6b67`（`dry=true`，`dry_reason=all_candidates_decided`）
- 结构化记录：`shared/literature_pool.yaml`（23 条，**全部** `status=used` 且 `verified=true`，`verification_provider=crossref`）
- 题目引用登记：`problems/microgrid_2025/citations.yaml`（prob01 25 条 + 本批 23 条 = **48 条**，ID/DOI 无重复；本动作未改动 prob01 已登记的 25 条）
- 规则依据：`wiki/literature-citations.md`、`knowledge/evidence-policy.md`、`skills/literature-research-watch/SKILL.md`
- 本次**不固定任何关键数学假设**：只提供可核验依据、适用边界与候选口径，裁定权属 `assumption_definition`。

---

## 0. 前提：团队裁定/勘误的效力与冲突记录（必读）

prob02 尚**没有**本地 accepted 假设版本（`question_manifest.yaml` 中 `active_assumption_version = 0`），
故本动作按 `AGENTS.md` 要求，读取上游 **`../prob01/versions/assumption_v003/assumptions.md`** 的末节
（「待团队选定的决策点」D1–D11、「团队勘误」E1–E3、「团队裁定（ablation 多模型对比设计与预注册判据）」），
该末节效力**高于**假设正文、公式正文与 `global_symbols.yaml` 的旧登记。逐项对本动作的影响如下：

| 编号 | 团队口径（v003 末节） | prob02 文献动作的执行/影响 | 是否遗留冲突 |
|---|---|---|---|
| **D9** | 目标量纲为 `min Σ p_t·b_t`（元，**不乘 Δt**），费用量级应为 10⁴ 元 | 本文件不涉及数值计算；仅要求 prob02 目标中的 `α_em·p_t·q_em_t` 与 `p_t·b_t` 同量纲（元） | 无 |
| **D10 + E1** | 5000 kW 作用于**并网点侧与电池侧、取更严者**（口径丙）；`q_dis ≤ 750.00 kWh`、`c ≤ 833.33 kWh`，prob01–prob04 统一 | 本文件与文献池均按 **750.00 / 833.33** 陈述；不与旧登记 833.33 混用 | 无（`global_symbols.yaml` 第 248 行已由 problem-decomposer 回写为 750.00，本动作已核对） |
| **E2** | `q_spill`/`s` 的 `first_question = prob01`（AS08/D4 已把 s 定为显式变量） | 文献池对 s 的证据按「变量保留、最优解允许取 0」陈述 | 无（`global_symbols.yaml` 第 273 行已回写为 prob01，本动作已核对） |
| **E3** | AS08 措辞「必然被激活」与实测 `Σs_t = 0` 不符，应为「变量必要、取值由优化决定」 | 本文件按新表述陈述；`assumption_v003/version.yaml` 的原措辞**仍未更正**（属 assumption 阶段产物，`literature-researcher` 无权改写），登记为**结转欠账**，权威回写待 `cross_question_review` | **遗留（登记类，不影响本阶段）** |
| **D10 文献缺口** | AS06「5000 kW 作用侧」为 `team_decision`，现有 25 条池无一条涉及，**不得包装为文献支持** | **prob02 本批 23 条同样无一条涉及该约定**（本批聚焦惩罚电价/可靠性/跨日衔接/信息结构）；本文件显式声明：prob02–prob04 的「5000 kW 作用侧」仍无文献支撑，论文不得包装为文献支持 | **遗留（证据类，已显式声明）** |
| **A2/A17/A18/A5/A13/A14** | prob01 未裁定，属 prob02 的 `assumption_definition` | 本文件只提供**候选口径的文献依据与边界**，不替题面/团队裁定；`q_em` 必须保留为变量（`global_symbols.yaml` 第 224–234 行） | 无（本动作未越界裁定） |

> **差异声明（AGENTS.md 要求显式记录）**：
> ① 本动作**未**发现团队口径与 `global_symbols.yaml` 现行登记之间的新冲突（E1/E2 已回写，本动作逐行核对通过）；
> ② 唯一未闭合项是 **E3 的措辞欠账**（在 `assumption_v003/version.yaml`，不属本阶段可写文件）与 **D10 的文献缺口**（本批无法用真实文献补齐）；
> ③ 本阶段**不引用 prob01 池的 25 条**作为 prob02 关键假设的门禁来源：`automm.research.check_key_assumptions` 只检查**本小问**池，
> 故本批 23 条刻意覆盖 prob02 自身的全部证据义务（见 §1 的 E1–E7），使 prob02 池**自洽**，无需依赖 prob01 池绑定。

---

## 1. 检索目标与范围

prob02 的数值输入（电价列、附件 2 实际负载/光伏、附录 1 储能参数）仍由题面给定，文献需要回答的是**建模口径的合法性**。据此设定 7 条证据义务（E1–E7）：

| 编号 | 待支撑的建模问题 | 对应题面/歧义 |
|---|---|---|
| **E1** | 目标中的**惩罚/不平衡电价**项：紧急购电价 = 交易时刻电价 ×5（`α_em = 5`）作为惩罚系数的建模合法性；「偏差按惩罚价结算」的制度依据 | 题面问题 2、H8；A5/A17 |
| **E2** | **紧急购电/供电可靠性**：`q_em ≥ 0` 作为「供给低于负载时的补足量」的显式变量；微网可靠性约束的建模方式 | H1、A5、A17；`q_em` 符号 |
| **E3** | **跨日衔接与终端 SOC**：每日独立（`E_{d,0}=E_{d,144}`）vs 自 2025-01-01 滚动递推（1 月作预热）两读的方法学基础；跨时段状态衔接是标准做法 | **A2（高优先）**；`E_soc` 符号 |
| **E4** | **信息结构**：0:00 制定计划时「已知全天实际负载/光伏（完全信息）」vs「只有预报」对模型与结果的影响；「完美信息价值」的文献概念 | **A17（高优先）** |
| **E5** | **时域组织与规模**：334 天 × 144 时段下，单日小 LP 集合 vs 单一长时域 LP vs 滚动时域；时域组织方式的方法学依据 | A2 的计算规模影响 |
| **E6** | **填报口径**：表 3 / `result2.xlsx`「紧急购电量」的时间段合并与 `J_d=0` 写法 | **A18**（纯报告口径，**无文献可依，属题面事实**） |
| **E7** | **问题族定位**：时间型/分时电价下逐日经济调度 + 储能，是成熟优化问题族（为 prob02 池自洽提供独立来源，不依赖 prob01 池） | 目标与模型族 |

**文献不能裁定的事项（显式排除）**：A2 的「取哪一读」、A17 的「信息结构取哪一读」、A18 的填报写法、A5 的 `q_em` 作用位置、
A13 的 `s` 界松紧、A14 是否引入购电上限——这些是**题面/数据/团队选择**，文献只给出可迁移范式与偏差方向，不替代裁定。

检索式由「对象 + 机理 + 方法 + 限制」组成；两轮实际检索式见 §6。

## 2. 核验方法与限制

- **元数据核验**：23 条全部通过 harness `automm.research.verify_reference` 的 Crossref 核验
  （`verified=true`、`verification_provider=crossref`、`verification_error=None`），写入 `citations.yaml` 的标题、作者、年份、来源以 Crossref 记录为准；
  本动作另做「写入标题 vs Crossref `verified_title`」逐条比对，23/23 一致（证据 `evidence/title_check.txt`）。
- **摘要获取**：本动作用 **OpenAlex** `abstract_inverted_index` 重建摘要，使 **19/23** 条达到 `verification_level=abstract_oa`；
  其余 **4 条**（`ref-cardoso-2013-reliability-slp`、`ref-chazarra-2017-perfect-information`、`ref-zhang-2018-robust-multimg`、`ref-wang-2022-multiagent-time-price`）为 `metadata` 级。
- **全文仍未读**：本环境无浏览器级全文抓取能力，**23 条均未逐篇阅读正文**。因此本阶段的引用**只支撑框架级/机制级主张**
  （问题形式、约束组成、方法族、简化边界、制度存在性）；**任何公式级或定量级引用**（含 E1 的 4–5 倍量级、E4 的完美信息价值数字）
  必须在 `mathematical_formulation` 取得全文后再使用，不得以本文件为据直接引用。
- **分类纪律**：`literature_fact`（来源支持的事实）、`project_assumption`（为本题建立、待验证边界的假设）、
  `agent_inference`（由数据/模型/文献迁移推断）、`team_decision`（团队/题面选择）四类互不冒充。
  本文件所有「建议口径」均为 `agent_inference`，最终裁定属 `assumption_definition`。
- **不得越界**：本动作未修改 `prob01/` 任何产物、未改 `global_symbols.yaml`、未改任何 accepted 假设；
  对 `citations.yaml` 只**追加**本批 23 条（`decide_reference` 的既有行为），prob01 的 25 条原样保留（本动作已核对）。

## 3. 来源清单（按证据义务分组）

等级：A 同行评审期刊 / 主要会议；B 权威会议论文 / 成熟技术文献；C 会议摘要 / 预印本级。
本批 23 条**全部为本轮新增**且状态 `used`（`new → used`，无 `rejected`）；`authority` 分布 A=21、B=2。

### 3.1 E1 惩罚电价 / 不平衡结算 / 偏差惩罚（6 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-vanderveen-2016-balancing-market-design` | A | abstract_oa | 平衡市场设计框架：偏差按不平衡价结算是制度变量 |
| `ref-herre-2020-imbalance-settlement` | B | abstract_oa | 「不平衡 = 实际 − 计划」与结算制度决定偏差成本 |
| `ref-botterud-2011-wind-lmp-deviation` | A | abstract_oa | 偏差惩罚系数是日前计划建模的显式参数，且会改变最优计划 |
| `ref-joos-2018-integration-costs` | A | abstract_oa | 不平衡价格信号强度的现实制度存在性（英德对比） |
| `ref-silva-2022-multistage-bidding` | A | abstract_oa | 日前 + 日内 + 平衡多结算框架；偏差是可决策处理量 |
| `ref-poplavskaya-2020-balancing-design` | A | abstract_oa | 平衡价高于常规价的机制与 4–5 倍量级（**仅量级旁证，不用于标定**） |

### 3.2 E2 紧急购电 / 供电可靠性 / 失负荷（4 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-wang-2011-spinning-reserve-microgrid` | A | abstract_oa | 微网备用/可靠性约束；「供给不低于负载」的确定性极限 |
| `ref-xie-2019-storage-reliability` | A | abstract_oa | 储能与可靠性/韧性在微网优化中显式耦合 |
| `ref-hirsch-2018-microgrids-review` | A | abstract_oa | 可靠性是微网首要驱动（背景级） |
| `ref-cardoso-2013-reliability-slp` | A | metadata | 可靠性与电池调度在同一优化框架内 |

### 3.3 E3 跨日衔接 / 滚动时域 / 终端 SOC（6 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-silvente-2015-rolling-horizon` | A | abstract_oa | 多时段耦合 + 滚动时域更新的标准范式 |
| `ref-deng-2020-interhours-rolling` | A | abstract_oa | 跨小时滚动调度；跨时段状态衔接是常规组成 |
| `ref-holjevac-2017-receding-horizon` | A | abstract_oa | 日前计划 + 滚动修正；近似对日尺度结果影响可观 |
| `ref-finnah-2021-da-intraday-adp` | A | abstract_oa | 跨市场/跨时段储能状态决策 |
| `ref-bao-2014-multiscale-mg` | A | abstract_oa | 日前/实时两层时域结构 |
| `ref-hu-2020-mpc-overview` | A | abstract_oa | 状态跨时段传递的预测控制范式（框架级） |

### 3.4 E4 信息结构 / 完全信息价值 / 确定性 vs 随机（5 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-chazarra-2017-perfect-information` | B | metadata | 「完美现货价格信息」的价值是储能调度的标准分析对象 |
| `ref-liang-2014-stochastic-survey` | A | abstract_oa | 确定性模型 vs 随机模型的方法谱系 |
| `ref-shuai-2018-adp-dispatch` | A | abstract_oa | 不完美信息下需显式预测误差模型 |
| `ref-toubeau-2020-da-real-time` | A | abstract_oa | 日前计划与实时偏差的「裕度 vs 经济性」权衡 |
| `ref-zhang-2018-robust-multimg` | A | metadata | 不确定性下的鲁棒路线（方法谱系补充） |

### 3.5 E5/E7 时域组织与问题族定位（2 条）

| ID | 等级 | 核验级别 | 支持对象 |
|---|---|---|---|
| `ref-wang-2022-multiagent-time-price` | A | metadata | 时间型电价下的微网经济调度（prob02 池自洽的独立来源） |
| `ref-hu-2023-empc-review` | A | abstract_oa | 经济目标 + 多时段调度是微网主流范式（综述） |

## 4. 候选假设族与来源映射（供 `assumption_definition` 裁定）

以下均为**候选口径**，不是已定假设；每条给出文献依据、与本题差异、裁定要点。文献不替题面裁定。

### 候选口径 P1（E1）：紧急购电费 = `Σ α_em · p_t · q_em_t`，`α_em = 5`
- **文献依据**：`ref-vanderveen-2016-balancing-market-design`、`ref-herre-2020-imbalance-settlement`、`ref-botterud-2011-wind-lmp-deviation`、`ref-joos-2018-integration-costs`、`ref-silva-2022-multistage-bidding`、`ref-poplavskaya-2020-balancing-design`。
- **可支撑的主张（框架/机制级）**：①「偏差（= 实际/紧急量 − 计划量）按高于常规价的惩罚价结算」是电力市场与微网调度中的标准制度形式；
  ②惩罚系数是显式建模参数，且**会改变最优计划**（`ref-botterud-2011-wind-lmp-deviation` 摘要明确：有惩罚时申报向期望出力靠拢）；
  ③惩罚/平衡价显著高于常规价是现实量级（`ref-poplavskaya-2020-balancing-design` 摘要给出 4–5 倍，**仅量级旁证**）。
- **差异与边界**：以上来源均面向市场参与者（报价、风险、多市场结算），本题是**单一微网、确定性、无报价决策**；
  `α_em = 5` 由题面**硬给定**，不得用文献重新标定或用文献替代题面值。
- **裁定要点**：目标中惩罚项的**形式**（`α_em·p_t·q_em_t`，元，不带 Δt）可由文献支撑为 `literature_fact`；
  但「本题取 α_em = 5」本身是题面事实，应标 `project_assumption`/题面事实而非文献结论。

### 候选口径 P2（E2）：`q_em_{d,t} ≥ 0` 为显式变量，用于补足「微网供电 < 负载」
- **文献依据**：`ref-wang-2011-spinning-reserve-microgrid`、`ref-xie-2019-storage-reliability`、`ref-hirsch-2018-microgrids-review`、`ref-cardoso-2013-reliability-slp`。
- **可支撑的主张**：微网优化中「供电可靠性」通常写成备用/可靠性约束（概率或确定性），其**确定性硬约束极限**即本题「供给不低于负载」；
  储能与可靠性在微网优化中显式耦合。
- **差异与边界**：文献多为概率可靠性/备用容量，本题为**确定性 + 不足即紧急购电**，不建概率模型。
- **裁定要点（关键）**：`global_symbols.yaml` 已把 `q_em` 登记为 prob02 决策变量并注明「**必须保留，不得因预期恒零而删除**」；
  **A17 的「完全信息 + 无购电上限 ⇒ 最优 q_em ≡ 0」是数学推论，不是文献结论**，不得包装为文献支持；
  文献只支撑「把不平衡量显式建模」这一形式。A5（`q_em` 能否用于储能充电）同样属团队裁定。

### 候选口径 P3（E3）：跨日衔接取「每日独立（`E_{d,0}=E_{d,144}`）」或「自 2025-01-01 滚动递推（1 月预热）」
- **文献依据**：`ref-silvente-2015-rolling-horizon`、`ref-deng-2020-interhours-rolling`、`ref-holjevac-2017-receding-horizon`、`ref-bao-2014-multiscale-mg`、`ref-hu-2020-mpc-overview`、`ref-finnah-2021-da-intraday-adp`。
- **可支撑的主张**：①跨时段/跨日**状态衔接**（SOC 连续性）是储能调度的常规建模组成；②「滚动时域/预测控制」是有文献基础的长时域组织方式；
  ③`ref-holjevac-2017-receding-horizon` 摘要提示**近似对日尺度结果影响可观**，故 A2 两读的全年费用差异**必须实算**，不能凭直觉认为可忽略。
- **差异与边界**：文献的滚动多由**不确定性/信息更新**驱动；本题电价逐日相同、附件 2 为已知实际值，
  两读差异主要来自**1 月预热期与 2/1 起始状态**及计算规模，而非价格不确定性。**文献不裁定取哪一读**。
- **裁定要点（关键）**：若取「每日独立」，须显式声明 `E_{d,0}` 的取值（是否取 6000 kWh）与合理性；
  若取「滚动递推」，计算规模从 334 个 144 时段小 LP 变为单一 48096 时段（或逐日耦合），须在 `implementation`/`computation` 重估求解器与时限（属 E5）。
  **prob01 的 `E_0 = E_144 = 6000` 只是 prob01 的周期口径，不得直接外推为 prob02 每日初值**（`E_soc` 符号 notes 已明确）。

### 候选口径 P4（E4）：计划信息结构取「完全信息（0:00 已知当日附件 2 实际值）」或「不完美信息（预报）」
- **文献依据**：`ref-chazarra-2017-perfect-information`、`ref-liang-2014-stochastic-survey`、`ref-shuai-2018-adp-dispatch`、`ref-toubeau-2020-da-real-time`、`ref-zhang-2018-robust-multimg`。
- **可支撑的主张**：①「信息结构的价值」是储能调度文献中的标准分析对象（完美信息价值）；
  ②当计划信息不完美时，需引入预测误差模型（随机/机会约束/鲁棒）来修正计划；③确定性模型是「信息已知/忽略不确定性」时的特例。
- **差异与边界**：本题附件 2 是**实际**功率，题面未给其配套预报；附件 3（预报）属 prob03，附件 1 的预测列属 prob01/代表日语义。
  故 A17 候选 (b)「不完美信息」**缺少题面数据接口**，须先裁定预报来源与语义（实质是把 prob03 的信息结构提前）。
- **裁定要点（关键）**：若取完全信息，则由「`α_em = 5 > 1` ⇒ 任何 `q_em > 0` 都被改为计划购电严格改进」推出最优 `q_em ≡ 0`——
  这是**本题模型内的数学结论**（文献不提供该结论），必须在论文中说明「完全信息下紧急购电机制不被激活」并裁定全零的填报写法（A18 联动）。
  若取不完美信息，文献（`ref-shuai-2018-adp-dispatch`、`ref-toubeau-2020-da-real-time`）支持「需先固定预测误差模型」，属**新增假设**，不得由实现自选。

### 候选口径 P5（E5）：时域组织与计算规模
- **文献依据**：`ref-silvente-2015-rolling-horizon`、`ref-hu-2020-mpc-overview`、`ref-hu-2023-empc-review`、`ref-holjevac-2017-receding-horizon`。
- **可支撑的主张**：「经济目标 + 多时段调度」是微网调度主流范式；单日 LP 集合与长时域/滚动 LP 均有文献先例。
- **裁定要点**：P5 是 P3 的**下游结果**，不单独裁定；但须在 `assumption_definition`/`mathematical_formulation` 记录所选时域的**求解可行性依据**
  （334 个 144 时段小 LP 可用 HiGHS/CPU；长时域 48096 时段须重估时间与内存）。

### 候选口径 P6（E6）：表 3 / `result2.xlsx` 的填报口径
- **文献依据：无**。A18（连续时段是否合并、端点标签、`J_d=0` 写法、是否给每日合计）属**题面报告口径**，
  题面表 4 的非等长区间示例是唯一依据，文献不参与也不得替代。本文件只作登记。

### 候选口径 P7（E7）：prob02 池的独立问题族定位
- **文献依据**：`ref-wang-2022-multiagent-time-price`、`ref-hu-2023-empc-review`（并与 prob01 池的 TOU/日前调度族呼应，但**不依赖 prob01 池**）。
- **裁定要点**：保证 prob02 的关键假设门禁可在**本小问池内**闭合（`check_key_assumptions` 只读本小问池）。

## 5. 结论与对下游阶段的移交

1. **prob02 的问题族在文献中是成熟的**：时间型电价下、给定负荷/光伏曲线、含储能的逐日经济调度，叠加「偏差/紧急量按惩罚价结算」的多结算框架
   （E1+E7 来源）。这为 `mathematical_formulation` 采用确定性 LP（每集合计或长时域）提供框架级依据。
2. **三条最需要显式声明的口径选择，文献只能部分支撑**：
   - 惩罚项形式（P1）——文献支撑形式，**`α_em = 5` 是题面事实**；
   - 跨日衔接（P3）——文献支撑「两种时域组织都合理」，**取哪一读必须由团队按题面/数据裁定**；
   - 信息结构（P4）——文献支撑「信息结构是显式建模维度」，**取完全信息还是不完美信息必须由团队裁定**，且不完美信息缺题面数据接口。
3. **文献未解决、必须由假设裁定的事项**：**A2**（逐日独立 vs 跨日滚动、2/1 起始储电量）、**A17**（信息结构与 `q_em` 是否恒零）、
   **A5**（`q_em` 作用位置/能否充电）、**A13**（多日 `s` 的界）、**A14**（购电上限）、**A18**（填报口径）。本阶段**未固定任何假设**。
4. **门禁可用性**：prob02 池 23/23 `verified=true & status=used`，覆盖 E1–E5、E7；`assumption_definition` 可为 prob02 的
   关键假设（惩罚项目标、可靠性/`q_em` 形式、储能状态转移与约束集、模型族）绑定本池来源，无需跨小问引用。
   **E6（A18 填报）与 D10「5000 kW 作用侧」无文献支撑，必须标为 `team_decision`/题面事实，不得绑定文献**。
5. **prob01 池与 prob02 池的关系**：两池 ID 与 DOI **完全不重复**；prob01 的 25 条仍保留在 `citations.yaml`，
   本动作只追加不改写。prob02 引用 prob01 已 accepted 的口径（AS01/AS04/AS05/AS06/AS09/AS13 等）时，应在公式阶段引用**prob01 池**的对应文献，
   或在 prob02 池内选取本批对应来源（§4 P7），不得把未读正文的文献用于公式级引用。

## 6. 检索式与证据

实际执行的检索（Crossref 书目检索 + OpenAlex 定向检索，两轮；**与 prob01 已用检索式不重复**）：

第一轮（Crossref，`evidence/discover_crossref.py` → `discovery_raw.json`，15 式 × 6 条）：

1. emergency power purchase penalty price microgrid optimization
2. imbalance settlement deviation penalty electricity market battery storage
3. real-time imbalance price penalty renewable microgrid dispatch
4. unserved energy penalty microgrid emergency generation optimization
5. penalty cost load shedding microgrid energy storage scheduling
6. rolling horizon optimization multi-day battery energy storage scheduling
7. multi-day look-ahead energy storage scheduling terminal state of charge
8. day-ahead and real-time market battery storage bidding optimization
9. perfect information forecast error day-ahead scheduling energy storage
10. deterministic versus stochastic day-ahead scheduling energy storage
11. time-of-use pricing battery storage deviation penalty optimization
12. end-of-horizon state of charge constraint energy storage optimization
13. microgrid emergency demand response penalty electricity price
14. multi-period energy storage optimization horizon coupling state of charge
15. reserve penalty imbalance cost storage arbitrage optimization

第二轮（OpenAlex 定向 + 按 DOI 取回摘要，`evidence/discover_openalex.py` / `discover_round2.py` / `fetch_extra_abstracts.py`）：

16. imbalance settlement energy storage bidding electricity market
17. deviation penalty electricity market scheduling
18. penalty price microgrid energy management emergency
19. value of lost load microgrid reliability optimization
20. unserved energy microgrid emergency purchase optimization
21. rolling horizon energy storage scheduling optimization
22. multi-day battery energy storage scheduling optimization
23. look-ahead dispatch energy storage state of charge terminal
24. end of horizon state of charge constraint battery optimization
25. weekly scheduling battery storage optimization microgrid
26. deterministic day-ahead scheduling perfect forecast energy storage
27. value of perfect information energy storage scheduling
28. day-ahead forecast error battery storage dispatch
29. stochastic programming versus deterministic microgrid scheduling
30. loss of power supply probability microgrid optimization
31. load shedding penalty microgrid scheduling optimization
32. penalty for deviating from scheduled power microgrid
33. emergency purchase price microgrid optimization
34. imbalance penalty energy storage arbitrage optimization
35. unserved load penalty day-ahead scheduling microgrid
36. value of lost load demand curtailment penalty electricity
37. state of charge continuity across days battery scheduling
38. coupled multi-day optimal scheduling microgrid storage
39. day-ahead scheduling penalty cost load imbalance storage

证据目录：`runtime/actions/act-187a164154404f6c/`
- `evidence/discover_crossref.py` / `discovery_raw.json`：第一轮发现（Crossref）；
- `evidence/discover_openalex.py` / `discovery_openalex.json` / `discovery_openalex_digest.txt`：第一轮 OpenAlex 定向检索与摘要重建；
- `evidence/discover_round2.py` / `discovery_round2.json` / `discovery_round2_digest.txt`：第二轮补齐 + 按 DOI 精确取回；
- `evidence/openalex_by_doi.json`、`evidence/selected_abstracts.txt`、`evidence/extra_abstracts.txt`：入选条目的来源信息与重建摘要（人工筛选依据）；
- `candidates.json`：23 条候选（含 evidence 义务映射、适用边界、差异、决策理由）；
- `run_literature_round.py` / `literature_round_stdout.txt`：调用 `automm.research` 完成「开始轮次 → 候选入池 → Crossref 核验 → used 决策 → 结束轮次」；
- `verification_report.json`：逐条核验结果（`verified` / `provider` / `verified_title` / `error`；本例 23/23 `verified=true, provider=crossref`，`failures=[]`）；
- `evidence/title_check.txt`：写入标题 vs Crossref `verified_title` 的逐条比对（23/23 一致）；
- `runtime/research_cache/`：Crossref 核验响应缓存（可追溯每条的原始元数据记录）。

## 7. 风险与缺口

- **全文未读（最大缺口）**：23 条均只到摘要/元数据级。若 `mathematical_formulation` 需要某条来源的具体公式、约束写法或参数，
  必须在该阶段另行获取全文；**不得**以本文件为据直接引用公式或定量结论。
  - 特别地：**P1 的 4–5 倍量级**（`ref-poplavskaya-2020-balancing-design`）与**E4 的完美信息价值数字**（`ref-chazarra-2017-perfect-information`）
    均为摘要/标题级，只能说明机制存在，**不得**用于支撑或质疑题面 `α_em = 5`。
- **A2/A17 无文献裁定**：两读都「有文献先例」，文献无法在题面/数据内闭合选择；若 `assumption_definition` 判定两读互斥且都无法在题面内闭合，
  按 `config/gates.yaml` 的 `human_model_choice` 上报，而不是用文献强行裁定。
- **D10「5000 kW 作用侧」文献缺口结转**：prob02 本批 23 条**无一条**涉及该团队约定；论文若需文献依据，须补定向检索或取得全文，**不得包装为文献支持**。
- **E3 措辞欠账结转**：`assumption_v003/version.yaml` 中 AS08「必然被激活」仍未更正（非本阶段可写文件），权威回写待 `cross_question_review`。
- **不引用同题竞赛衍生论文**：未检索、未引用任何解题/赛题衍生来源，避免循环论证。
- **无 rejected 条目**：本批 23 条全部核验通过并 `used`；第一轮 Crossref 命中的若干无关条目（如区块链/无功优化/DC 微网控制/储能材料等）
  在筛选阶段即被剔除，**未入池**（池内无 `rejected` 记录，与 prob01 的处理方式一致）。
