# prob03 图表视觉复核报告

- 归属：`microgrid_2025` / `prob03`；阶段：`visualization`
- 同步动作：`act-b9f9548c1a8d49e0`（负责人：visualization-agent）
- 接受版本：`assumption_v001` / `formulation_v001`（`active_assumption_version = 1`、`accepted_formulation_version = 1`）
- 结果来源：task `6de708bbd2d3dd273013` / `results/prob03_v001_f001_run003`（succeeded、attempt 1、supervised、CPU HiGHS、
  `probe_mode=false`、365 天 × 144 时段 = 52,560 时段、model = M1、wall 41.77 s；`sanity.level_1_4 = PASS_WITH_WARNING`，
  `act-354d33342edf4e70`；`checks_failed = []`）
- 生成脚本：`problems/microgrid_2025/prob03/versions/assumption_v001/figures/plot_prob03_figures.py`
- 样式来源：`config/visualization.yaml`（字体 Microsoft YaHei，色板 primary/secondary/accent/neutral/warning，DPI 180，PNG）
- 自动质检：`automm.visualization.inspect_png`（分辨率 ≥ 800×480、非空/非纯色、边界暗像素比例）
- 数值审计：`runtime/actions/act-b9f9548c1a8d49e0/evidence/probe_prob03_figure_data_audit.py` →
  `figure_data_audit_out.json`（**77 项只读断言全部通过**；除「视觉复核状态」由本动作写回外无待办）

## 1. 复核方法

1. 脚本自动质检：8/8 张 PNG 均为 `quality_status = passed`（1793×1524 ~ 2477×1764 px，远高于最小值 800×480；边界暗像素比 0.000）。
2. 逐图人工视觉复核：对每张导出 PNG 直接读图，检查字体（无方框/缺字）、标题、轴标签与单位、图例、刻度、曲线方向、
   文本截断与重叠、颜色区分、信息层级与是否误导；三维图额外检查视角、遮挡、透视失真、深度辨识与静态 PNG 可读性。
3. 局部放大复核：对疑似问题区域用 PIL 裁剪后放大复检（`bottom legend` 与右下子图逐像素确认），避免仅凭缩略预览判断。
4. 数值交叉核对：`figure_data_audit_out.json` 用 run003 / prob02 run002 / `t7_tiebreak.json` / 附件 2、3 独立复算图上的
   每个数字（费用分解与恒等式、跨问差额与净负荷、调整量与上调/下调计数、紧急购电总量与时段计数、R12 示例值、SOC 极值与
   日初/日末、降尺度有效区间、tie-break 计数、manifest 完整性）。
5. 发现即修正：首轮复核发现 **8 处缺陷**（含 1 处真实数值口径缺陷、1 处时间轴映射错误、2 处遮挡、1 处字体缺字形），
   修正后重新生成并复检；复核通过后才登记视觉复核结论。

## 2. 逐图复核结论

| # | stable_id | kind | 回答的问题 | 自动质检 | 视觉复核 | 结论 |
|---|---|---|---|---|---|---|
| 1 | `prob03_fig_forecast_chain_78b78a9c24` | forecast_chain | 三层信息结构：谁在什么时候用哪份预报、结算用哪份数据 | passed（2432×1100） | 两个代表日（夏至/冬至）曲线完整，黑=附件 2 实际、蓝虚线=0:00 计划预报、橙=支配预报；6/12/18 时刻竖点线与竖排标签不越界、不压曲线；图例 3 项置于左上空白；冬夏两图的 Y 轴量程分别自适应且标注单位 kW | passed |
| 2 | `prob03_fig_plan_adjust_profile_5815df79b4` | plan_adjust_profile | 计划 $b$、最终 $q$、调整量 $q-b$ 与紧急购电 $q_{em}$ 的日内落地 | passed（2432×1764） | 2×2 布局；上排曲线+填充+红柱层次分明，下排调整量柱以 0 线分隔；图例移到画布底部后不再压住 x 轴标题（首轮缺陷已修）；两个指定日期的当日费用/电量注记置于右上空白 | passed |
| 3 | `prob03_fig_adjust_surface_3d_6b4425cbc5` | adjust_surface_3d | 全年「日期 × 时刻 × 调整量」的三维结构 | passed（1793×1524） | 视角 elev=26°/azim=−58°，三轴与色标标签完整；曲面几乎全在 Z≥0 半空间、无自遮挡；色标与 Z 轴按 99.5 分位 1,692 kWh/h 截断（峰值 3,557，已在图内注明），低幅结构可辨；已配二维配套图 4 | passed |
| 4 | `prob03_fig_adjust_heatmap_2d_4477246233` | adjust_heatmap_2d | 三维曲面的二维投影与逐日总量（定量判读依据） | passed（2180×1568） | 上：日期×时刻热力图色标以 0 为中心并按调整量绝对值的 99 分位 1,256 kWh/h 截断，交付期红线与月份刻度正确；下：逐日调整量柱与交付期日均线 1.44 MWh/日，图例与注记均不压数据 | passed |
| 5 | `prob03_fig_cost_decomposition_3c230c19db` | cost_decomposition | 费用三分解与跨问（R11）交付期费用差 | passed（2360×1208） | 左：交付期/全期堆叠柱与分项数值标注清晰，图例白底不透明、不再与深蓝柱低对比；右：prob02 与 prob03 柱顶数值、Δ=+2,307,565.50 元（+18.863%）白底注记框不压柱顶标签 | passed |
| 6 | `prob03_fig_soc_trajectory_ae5b14c70a` | soc_trajectory | SOC 是否在界内、跨日如何衔接、交付期首日为何处于下界 | passed（2180×1568） | 上：逐日 min–max 带 + 均值 + 上/下界线（图例白底置于左上空白）；下：两个代表日的日内轨迹，红虚线上下界与曲线分离清晰；**2025-02-01 0:00 已按日初状态 $E_{d,0}$ 修正为 1,200.00 kWh**（首轮缺陷已修），R13 注记完整 | passed |
| 7 | `prob03_fig_emergency_profile_c948ccca1e` | emergency_profile | 紧急购电的逐日/日内分布与 R12 的最小可复现示例 | passed（2180×1748） | 上：逐日 $q_{em}$ 柱 + 交付期日均线，图例白底；中：小时块分布（第 6 小时 201.9 MWh / 1,859 时段）柱顶计数不重叠；下：**时间轴按 AS01 位置口径修正（首轮 +5 h 映射错误已修）**，6:20–6:30 高亮带与箭头指向明确 | passed |
| 8 | `prob03_fig_tiebreak_degeneracy_85401e7e5d` | tiebreak_degeneracy | T7-2 不变性、T7-3 退化与多重最优、E7 的如实披露 | passed（2477×1414） | 左：逐层相对变化散点（对数轴）+ 10⁻⁹ 容差线，可见 1,460/1,460 全在窄带内；右：计划层/调整层退化度堆叠直方图，图例白底、不压最高柱；T7-3/E7/T7-6 披露文本移到底部独立文本框，未压缩图面 | passed |

> 计数：接受版本 `assumption_v001` 下通过自动质检与视觉复核的 PNG = **8 张**，满足 `config/visualization.yaml` 的
> `minimum_figures_per_question = 5`，并满足 `gates.required_artifacts_for_local_completion` 对 `visualization` 的要求。
> 8 张均登记 `included_in_summary = true`、`included_in_paper = true`（论文阶段若需裁减，须用官方 `register_figure`
> 同步翻回 `false`，不得只改正文）。

## 3. 三维图专项（`config/visualization.yaml: three_dimensional`）

| 图 | 视角 | 遮挡/透视/深度辨识 | 配套二维图 | 结论 |
|---|---|---|---|---|
| `adjust_surface_3d` | elev=26°、azim=−58° | 曲面 Z 值几乎全部 ≥0（下调仅 86 时段、总量 −2.87e-7 kWh），不存在上下表面互相遮挡；沿日期轴每 3 天抽 1 条网格线后尖峰仍连续可辨；色标与 Z 轴按 99.5 分位（1,692 kWh/h）截断以保留低幅结构，峰值 3,557 kWh/h 在图内注明，透视缩短不影响「峰集中在日间与傍晚」的判读 | `adjust_heatmap_2d`（日期×时刻热力图 + 逐日总量） | passed |

- 该三维图**不用于定量判读**：所有数值结论以配套二维图、`cost_decomposition`、`soc_trajectory`、`emergency_profile`
  与 `tables.json` 为准，已在图注中写明。

## 4. 首轮复核发现并修正的问题

| # | 图 | 首轮问题 | 处理 | 复检 |
|---|---|---|---|---|
| 1 | `soc_trajectory` | **真实数值/口径缺陷**：`2025-02-01 0:00` 的储电量误用平坦序列 `series.storage_kwh[31×144]`（该点是当日**第 1 个时段末**状态 = 1,950.00 kWh），与团队勘误 R13 的 **1,200 kWh（日初 $E_{d,0}$）** 不符，且与同句「（下界）」自相矛盾 | 改用 `daily.state_start_kwh[31]`，图内显式写「0:00（日初，$E_{d,0}$）」；并把逐日区间改为含日初状态的 min/max；审计新增两条断言（prob03 = 1,200.00、prob02 = 7,950.00） | passed |
| 2 | `emergency_profile` | **真实缺陷**：R12 示例面板的时刻标签按 `5 + 10j/60` 生成（多加 5 h），把 6:20–6:30 标成 12:00–12:50 | 改为 AS01 位置口径 `10j` 分钟；加 6:20–6:30 高亮带与箭头标注，并写明该时段 $c=0.256$、$q_{em}=0.515$ kWh/10min | passed |
| 3 | `plan_adjust_profile` | 图例（4–5 项）压在曲线与 x 轴标题上；右面板所选 2025-09-23 当日 $\Sigma(q-b)=0$，曲线完全重合、调整量不可见 | 改为 2×2（上排剖面、下排调整量柱），图例移出坐标轴到画布底部；代表日改为 2025-03-20 与 2025-12-21，并在图注说明全年另有 27 天（含 2025-09-23）无调整 | passed |
| 4 | `adjust_surface_3d` | 色标/Z 轴按未截断峰值（3,557 kWh/h）铺满，低幅结构被压成一片浅色 | 色标与 Z 轴按 99.5 分位截断并在图内注明截断值与峰值 | passed |
| 5 | `cost_decomposition` | 左面板图例 `frameon=False` 叠在深蓝柱上，黑色文字与 `#1F4E79` 对比不足 | 图例改白底不透明（`facecolor=white`、`framealpha=0.96`）并移到左上空白 | passed |
| 6 | `tiebreak_degeneracy` | 左面板原直方图只有一根柱（全部值落在 5.0e-10 ± 3e-15），信息量低；右面板长披露文本与柱体争夺空间 | 左面板改为「逐层相对变化 vs 层序号」散点 + 10⁻⁹ 容差线（并注明窄带跨度）；T7-3/E7/T7-6 披露文本移到画布底部独立文本框 | passed |
| 7 | 全部图 | 渲染文本使用 `⇒`（U+21D2），**Microsoft YaHei 缺该字形**（`UserWarning: Glyph 8658 missing`），PNG 中会显示为方框 | 三处渲染文本改为中文表述；重跑后 `UserWarning` 归零（matplotlib 全量 stderr 为空） | passed |
| 8 | manifest 卫生 | 图定义变更（Y 轴字段列表/布局）会改变 `stable_id`，旧登记项成为「已登记但语义已被取代」的孤儿条目（本轮出现 `prob03_fig_plan_adjust_profile_846594a9cd`） | 生成脚本新增 `prune_stale_figures()`：只清理 `question_id = prob03` 且不在本次生成集合内的登记项及其 PNG/质检文件，不触碰 prob01/prob02 与其它 manifest 字段；本轮已清理 1 条，`removed_stale_registrations = []`（复跑无残留） | passed |

> 修正后 8 张全部复检通过；审计 77/77 项断言通过。

## 5. 口径与追溯说明（须在论文图注中保留）

- **X 轴口径**：全年图用自然日索引/日期（0 = 2025-01-01，竖点线为月初，红虚线为 2025-02-01 交付期起点）；
  日内图用 **AS01 位置口径**（第 $i$ 时段 = $[10(i-1), 10i)$ min，计划窗 **0:10 → 24:10**，与严格自然日相差 10 分钟相位）；
  小时块按位置口径（第 $h$ 小时 = $[h{:}00, h{+}1{:}00)$ 共 6 个时段）。
- **两套期间口径（E6/B3-4）**：交付期 $D_{req}$ = 2025-02-01…12-31（**334 天**）为论文主口径；
  全期 $D_{full}$ = 365 天（含 1 月预热期）用于诊断对账。图 5 左右两柱**显式区分**两者；
  凡引用 kWh 类总量必须同时指明 $b$（计划购电量）或 $q$（最终购电量）与期间口径。
- **量纲**：目标 $\min \Sigma(p b + 5p\,q_{em}) + \Sigma[0.5p(b-q)^+ + 1.5p(q-b)^+]$（元，**不乘 $\Delta t$**，团队裁定 D9 承接）。
- **预报精度的引用纪律（团队勘误 E3）**：图 1 只展示信息结构，**不比较**四个发布时刻的预报精度——各时刻可用样本的
  提前量窗口与日内时段不同；E3 明确禁止把不同样本口径的 RMSE 横排成「某时刻更准」，也不得把 18:00 的「RMSE 0」
  （全夜间样本）包装为「18:00 预报最优」。假设 §6 的诊断数值一律不作为交付数值（T3）。
- **跨问披露（R11/R13）**：图 5 右面板披露 prob03 交付期比 prob02 贵 **+2,307,565.50 元（+18.863%）**，两问交付期净负荷
  **逐位相同**（17,939,189.49 kWh），差额为**预报误差的代价**，论文不得声称「问题 3 更省」；
  图 6 披露 2025-02-01 0:00（日初）储电量 prob03 = 1,200 kWh、prob02 = 7,950 kWh，**信息集不同、不可直接互比**；
  表 2 端点语义为**逐日切片**，与 prob01 单日周期恒 6,000 kWh 显式区分一次（R1）。
- **R12 机制**：图 7 下排给出「2025-01-01 6:20–6:30 时段 $q_{em}>0$ 与 $c>0$ 同时成立」的最小可复现示例，
  机制为「决策层用预报定 $(q,c)$ + 结算层用附件 2 实际算缺口」，全期此类时段 5,070 个（9.6%），不违反 D7-A。
- **T7 披露**：图 8 披露 T7-2 不变性（1,460/1,460 层、最大相对变化 5.000e-10 ≤ 1e-9）、T7-3 退化（1,460 层全退化，
  最大退化度 228；最优面吞吐量唯一性 True 435 / False 1,024 / None 1）、E7 唯一 `None` 层（2025-10-12 18:00 调整层，
  主目标 0 致 $\varepsilon = 1.754\times10^{-11}$ 低于 HiGHS 对偶分辨率，属探测边界、不构成缺陷）、
  T7-6 主结果对 tie-break 的量级敏感性约 $10^{-4}$ 相对量级；提交解取 T9 字典序（1,460 层、fallback = 0），
  不得用不同 tie-break 的结果互相比对。
- **结构性发现（须与团队核对后写入论文）**：① 主口径下调整方向恒为上调（$q \ge b$）——下调只增加 $0.5p(b-q)$ 成本而不减少
  已全额沉没的计划费 $\Sigma p b$，盈余又可零成本弃光；实测上调 5,810 时段 / 下调 86 时段（总量 −2.87e-7 kWh）。
  ② 逐日末端 $E$ 一律落在下界 1,200 kWh（365/365 天），是 AS04 终端自由在**逐日分层求解**下的结构性后果，
  也是交付期首日 0:00 处于下界的原因。两条均由 run003 数值与审计独立复现，非缺陷，但属**方法层解释项**。
- **追溯链**：8 图的 `source_hash` 分别为 `solution.json` 现 hash、`sha256(solution_hash + tables_hash)`（无）、
  `sha256(solution + 附件2 + 附件3)`（图 1）、`sha256(prob03 solution + prob02 solution)`（图 5）、
  `sha256(solution + t7_tiebreak.json)`（图 8）；`task_id = 6de708bbd2d3dd273013`；`script` 均指向同一生成脚本。
  `figure_data_audit_out.json` 逐项复核图上每个数字与 accepted 产物一致（77 项全通过）。

## 6. 遗留与边界（不影响本次出图验收）

- 本报告只覆盖 `prob03` accepted 版本的**可视化阶段**交付图。`robustness` 与 `ablation` 图件须在各自阶段另行生成与登记
  （`config/workflow.yaml` 把两者列为 `mandatory_stages`）；本动作**未**创建 task、未改模型/代码/假设/公式/原始数据。
- 团队裁定 T2 要求的 `M7·D2-B`/`M7·D2-C` 口径对照、T3 要求的 `M7·D5-B` 降尺度对照、以及 A9 的
  `M4`/`M5` 加密时刻族对照尚未跑数（属必做 `ablation`）：因此**本动作不出**「是否需要引入其他时刻预报」的收益曲线，
  图 1 仅提供信息结构证据。E3 的纪律（不得用预报 RMSE 作为跳发布时刻的比较轴）已在本报告 §5 与图注中落地。
- LP 最优面可能不唯一（T7-3 结构性事实）：图件展示的是 run003 的**字典序提交解**，论文引用其数值时不比对逐点解唯一性，
  结论以约束残差 + 四条恒等式 + 目标值 + 表 1/2/3 + `result3.xlsx` 为准；本动作未为求唯一性调 $\varepsilon$ 或更换规则。
- 上游结转（继续有效，不在本动作处理）：C3/E3（prob01 `assumption_v003` 的 AS08 措辞待 `cross_question_review` 权威回写）、
  D10（「5000 kW 作用侧」为 `team_decision`，三池文献无一条涉及，论文不得包装为文献支持）、
  R5（购电上限激活阈值须表述为 $\beta \in (4218.75, 4375.00]$ kW；本问 AS14 无购电上限故不触发）、
  prob03 文献池 25 条**0 条全文**（公式级/定量级引用须取得全文后使用）。
- 记录到的假设文本内部不一致（**未静默沿用**）：`assumptions.md` §5.3 的伪代码仍写
  「计划层（0:00 预报；全天可行，**不入目标成本**，只决定 `b`）」，而文件末尾的**团队裁定 T1**（效力更高）要求
  「计划层主口径定为 $\min \Sigma_t p_t b_{d,t}$」。run003 实测 hour-0 层目标之和 = `C_plan` = 13,885,669.475555 元
  （与 `solution.json.cost_plan_yuan` 逐位一致），证明实现**按 T1 执行**；本动作按 T1 陈述，建议 `formulation`
  下一版把 §5.3 的旧措辞改为与 T1 一致（登记为文本技术债，不影响本问数值）。
