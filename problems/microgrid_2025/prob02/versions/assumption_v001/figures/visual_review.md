# prob02 图表视觉复核报告

- 归属：`microgrid_2025` / `prob02`；阶段：`visualization`
- 同步动作：`act-7d4e0b542a9c4039`（负责人：visualization-agent）
- 接受版本：`assumption_v001` / `formulation_v001`（`active_formulation_version = 1`、`accepted_formulation_version = 1`）
- 结果来源：task `dc8afc3deb5477641b99` / `prob02_v001_f001_run002`（succeeded、supervised、CPU HiGHS、`probe_mode=false`、365 天 × 144 时段；sanity level_1_4 = `PASS_WITH_WARNING`，act-847e8cb12a844527）
- 生成脚本：`problems/microgrid_2025/prob02/versions/assumption_v001/figures/plot_prob02_figures.py`
- 样式来源：`config/visualization.yaml`（字体 Microsoft YaHei，色板 primary/secondary/accent/neutral/warning，DPI 180，PNG）
- 自动质检：`automm.visualization.inspect_png`（分辨率 ≥ 800×480、非空/非纯色、边界暗像素比例）
- 数值审计：`runtime/actions/act-7d4e0b542a9c4039/evidence/probe_prob02_figure_data_audit.py` → `figure_data_audit_out.json`（37 项只读断言，除「视觉复核状态」待本动作写回外全部通过）

## 1. 复核方法

1. 脚本自动质检：11/11 张 PNG 均为 `quality_status = passed`（1613×1344 ~ 2540×1316 px，远高于最小值 800×480；边界暗像素比 0.000）。
2. 逐图人工视觉复核：对每张导出 PNG 直接读图，检查字体（无方框/缺字）、标题、轴标签与单位、图例、刻度、曲线方向、
   文本截断与重叠、颜色区分、信息层级与是否误导；三维图额外检查视角、遮挡、透视失真、深度辨识与静态 PNG 可读性。
3. 像素级交叉验证：对可疑图用「受控参考线 + 颜色像素聚类」反推曲线在画布上的实际位置
   （`evidence/probe_prob02_fig1_axis_control.py`、`probe_png_pixel_audit.py`、`probe_png_green_cluster_audit.py`），
   避免仅凭缩略预览判断。
4. 发现即修正：首轮复核发现 4 处缺陷（含 1 处真实数值缺陷、1 处坐标轴单位缺陷），修正后重新生成并复检；
   复核通过后才登记视觉复核结论。

## 2. 逐图复核结论

| # | stable_id | kind | 回答的问题 | 自动质检 | 视觉复核 | 结论 |
|---|---|---|---|---|---|---|
| 1 | `prob02_fig_year_energy_flow_ed77b9f928` | year_energy_flow | 全年日能量构成与代表日功率平衡是否闭合 | passed | 上：日电量堆叠（光伏+购电）与负载、净负荷曲线逐日可比，1 月预热期与 2–12 月交付期连续；下：代表日 2025-06-21 三曲线（负载/kW、光伏、购电）峰谷完整，购电尖峰出现在凌晨与 21:00 后，无文本遮挡 | passed |
| 2 | `prob02_fig_cost_price_rhythm_74725a2a9b` | cost_price_rhythm | 全年日费用与购电加权均价的季节结构 | passed | 上图日费用填充 + 交付期日均线；下图加权均价散点按日费用着色，色标与标题语义一致；Y 轴单位（元/日、元/kWh）明确；无遮挡 | passed |
| 3 | `prob02_fig_temporal_heatmap_2aa0a5f976` | temporal_heatmap | 全年「日期 × 时段」的购电与储电量结构 | passed | 双热力图色标量纲明确（MW、kWh），色标上限按 99.5 分位防压色；4 个指定日期红圈 + 日期标签（白底）在深色条纹上仍可读、不越界；「行=自然日」与 0:10→24:10 相位已在轴标签说明 | passed |
| 4 | `prob02_fig_soc_trajectory_eb0f77c2a5` | soc_trajectory | SOC 是否在运行区间内、跨日连续、年末放空 | passed | 左：全年轨迹与 E_min/E_max/E_1/1,0 参考线区分清晰（参考线语义移到图内注记条）；右：年末 14 天放大，E→1200 的期末放空可读，放空注记不压数据；图例带半透明底在密集尖峰上可读 | passed |
| 5 | `prob02_fig_energy_balance_b86f1c6e8b` | energy_balance | 全年供需三项与弃光是否闭合 | passed | 左：三项供给堆叠与需求虚线逐月重合，闭合残差注记 4.657e-16 GWh（修正后）；右：逐月弃光率条形带数值标注，1/12 月 0% 与说明框一致 | passed |
| 6 | `prob02_fig_rhythm_3d_9748be3c4f` | rhythm_3d | 全年「日期 × 时刻 × 净放电」节律结构 | passed | 视角 elev=22°/azim=−52°，三轴刻度与标签完整；色标以 0 为中心（红=放电、蓝=充电、近白=不动作）与标题图例一致；按 1/12 抽样（4,380 点）后充电/放电脊线连续，无遮挡歧义；已配 2D 投影图 7 | passed |
| 7 | `prob02_fig_rhythm_2d_a0abf87c17` | rhythm_2d | 三维节律的二维投影与季节结构 | passed | 左：对数色标联合密度 + 白色零线分隔充放电，低电价区集中充电、高电价区分放电两支；右：逐日净负荷与购电均价（颜色），交付起点虚线标注正确 | passed |
| 8 | `prob02_fig_spec_dates_a8ffbf1f32` | spec_dates | 题面 4 个指定日期的日内功率与表 1/表 2 摘要 | passed | 2×2 四联，各日曲线完整；标题两行（日期/费用/购电量/端点储电量）不截断；表 1 六时段购电量与表 2 端点语义集中放在图底独立文本框，不与任何子图重叠 | passed |
| 9 | `prob02_fig_daily_coupling_3d_55ed1b8ea2` | daily_coupling_3d | 滚动递推下「日期 × 日初储电量 × ΔE」耦合结构 | passed | 视角 elev=24°/azim=−64°，三轴与色标（日费用）可读；日初取值的 96 个水平与 Σ ΔE = −4800 kWh 注记正确；已配 2D 配套图 10 | passed |
| 10 | `prob02_fig_daily_coupling_2d_3069395b29` | daily_coupling_2d | 日初储电量—日费用关系与滚动闭合检验 | passed | 左：散点按月份着色，Pearson r 注记与图例不遮挡；右：(E_{d,0}, E_{d,144}) 散点 + 对角参考线，连续性残差 0 与期末放空注记清晰 | passed |
| 11 | `prob02_fig_cost_bounds_ad7c3c0cc0` | cost_bounds | 费用量级与解析可行区间（含 (I2) 恒等式） | passed | 上：全期/交付期/1 月三柱与 10⁷ 元门禁线分离可读；下：解析下界 7,525,691.13 元、C* 13,758,182.57 元、无储能上界 18,298,592.37 元的水平条与竖虚线位置正确（修正后），注记给出区间宽度与相对位置 57.9% | passed |

> 计数：接受版本 `assumption_v001` 下通过自动质检与视觉复核的 PNG = **11 张**，满足 `config/visualization.yaml` 的 `minimum_figures_per_question = 5`。

## 3. 三维图专项（`config/visualization.yaml: three_dimensional`）

| 图 | 视角 | 遮挡/透视/深度辨识 | 配套二维图 | 结论 |
|---|---|---|---|---|
| `rhythm_3d` | elev=22°、azim=−52° | 抽样 1/12（4,380 点）后充电脊线（蓝，Z<0）与放电脊线（红，Z>0）分离清晰；近白点为净放电 = 0 的 26,058 个时段，已在图内注记说明，不构成误读 | `rhythm_2d`（对数密度 + 逐日净负荷） | passed |
| `daily_coupling_3d` | elev=24°、azim=−64° | 三轴数据边界与色标（日费用）可读；日初储电量呈 96 个离散水平、ΔE 分布较宽，结构清晰无自遮挡 | `daily_coupling_2d`（日初—费用、初—末闭合） | passed |

- 两图均**未**用于定量判读：定量结论以配套二维图、`soc_trajectory`、`energy_balance` 与 `tables.json` 为准，已在图注中写明。

## 4. 首轮复核发现并修正的问题

| # | 图 | 首轮问题 | 处理 | 复检 |
|---|---|---|---|---|
| 1 | `year_energy_flow` | **真实缺陷**：下面板时刻轴误写成 `arange(144)+0.5`（0.5→143.5 h），而 `xlim=(0,24)`，导致只画出前 24 个时段——光伏曲线呈 0 水平线、购电尖峰几乎不可见（像素审计：绿色仅 144 px，且集中在 y=1071–1073 的图例色块） | 改为 `(arange(144)+0.5)·Δt`（0.083→23.92 h）；像素复检后绿色像素 13,142、覆盖 y=1027–1512（对应 8.6→0 MW），蓝色购电尖峰同样恢复 | passed |
| 2 | `cost_bounds` | **真实缺陷**：`analytic_lower_bound/upper_bound` 的 `check.value/threshold` 语义与 prob01 相反（本问 `lower` 的 value=cost、threshold=下界；`upper` 的 value=上界、threshold=cost），直接取 `threshold` 会把上界写成 13,758,182.57 元、并把 C* 标成落在 100.0% 处 | 按 `prob02_model.evaluate` 的 `record` 语义改取 `lower=lower.threshold`、`upper=upper.value`，并加入三条断言（value/threshold 与 optimum 一致、lower<C*<upper）防回归 | passed |
| 3 | `energy_balance` | 月度 (I2) 闭合残差写成 6.750e-04 GWh：窗口前状态误用窗口内首点 E，引入 0.9·(E_before−E_first) 的边界项 | 改用「该月第一个时段之前」的状态（1 月用题面初值 6000 kWh），残差降为 **4.657e-16 GWh**（独立复算 12 个月最大 4.66e-10 kWh） | passed |
| 4 | `temporal_heatmap` | 指定日期标签置于标记下方，`2025-12-21` 落到面板底边被裁切 | 标签改到标记右侧并加半透明白底，四个日期标签在深浅条纹上均可读、不越界 | passed |
| 5 | `spec_dates` | 四联各图的「表 1/表 2 摘要」注记框压住下一行标题 | 注记集中到图底预留文本框（`subplots_adjust(bottom=0.215)`），子图标题改两行避免超宽截断 | passed |
| 6 | `soc_trajectory` | 左面板图例压住 E_min 虚线；右面板图例压住 E_max 虚线与数据 | 参考线语义移到图内顶部注记条；右面板图例移至左下并加半透明底、注记盒移至右下 | passed |
| 7 | manifest 卫生 | 诊断运行（复跑单图校准）经 `register_figure` 留下 2 条 `prob02` 条目（`source_hash` 为占位符 `diag`/`x`，PNG 已删除），使 manifest 出现「已登记但文件不存在」的条目 | 用与 `register_figure` 相同的 `read_yaml`/`write_yaml` 只删除这 2 条（`evidence/cleanup_stray_figure_entries.py`），prob02 正式条目由 13 条恢复为 **11 条**，未触碰 prob01 与其它 manifest 字段 | passed |

> 修正后 11 张全部复检通过；`cost_bounds`（1820×1532）与 `year_energy_flow`（1820×1640）尺寸正常。

## 5. 口径与追溯说明（须在论文图注中保留）

- **X 轴口径**：全年图一律用自然日日期（1 月 1 日起，竖虚线为月初），日内图用**位置口径 AS01**
  （第 `i` 段 = `[10(i−1), 10i)` min，计划窗 `0:10→24:10`，相对自然日整体前移 10 分钟）。
  热力图的「行 = 自然日，列 = 时段」因此每行首末相差 10 分钟相位，已在轴标签显式说明。
- **量纲**：目标 `min Σ(p·b + 5·p·q_em)`（元，**不乘 Δt**，团队裁定 D9）；`cost_bounds` 上图的 10⁷ 元门禁与
  下图的解析界（下界 `p_min[N+η(E_min−E_0)]`、上界 `Σp·max(0,L−PV)Δt`）均取自 `solution.json` 的 checks。
- **终端自由（AS04/D2-A）**：`E_{12/31,144} = 1200.00 kWh`（期末放空 4320 kWh，等价少购），
  已在 `soc_trajectory` 与 `daily_coupling_*` 的图注中显式披露，并明确「须与价格套利区分」。
- **`q_em ≡ 0`（AS07 定理 T1）**：本问主口径下紧急购电未激活，故**不单独出表 3 图**（避免把全零数据画成误导性图）；
  图注中给出 `Σq_em = 0` 并说明其依赖「完全信息 + 无购电上限 + α_em = 5」，机制演示由 ablation 的 M6/M6′ 承接。
  题面表 4 的示例数值与 2025/3/1 日期只在图注/表说明中标注为**格式示例**。
- **功率上限口径**：`c ≤ 833.3333 kWh`、`q_dis ≤ 750.0000 kWh`（团队裁定 D10 口径丙 + 勘误 E1）；
  图上的购电峰值 10,325.33 kW 与两侧换算功率 5000.00 kW 均出自 `solution.json` 的 totals。
- **表 2 端点语义（勘误 R1）**：prob02 为全年滚动的逐日切片（例：2025-03-20 = 8550.00 → 4352.87 kWh），
  与 prob01 的单日周期（恒 6000 kWh）**语义不同**，已在 `spec_dates` 图底说明与图注中显式区分一次。
- **追溯链**：11 图的 `source_hash` 分别等于 `solution.json` 现 hash（`4bcf7025…`）或
  `sha256(solution_hash + tables_hash)`（`spec_dates`，`229330b7…`），`task_id = dc8afc3deb5477641b99`，
  `script` 指向同一生成脚本；`figure_data_audit_out.json` 已逐项复核图上每个数字与 `solution.json`/`tables.json` 的一致性
  （4 日期 6 时段 + 全天量/费用 + 6 块充放电 + 端点储电量最大偏差 3.79e-07；月度 (I2) 残差 ≤ 4.66e-10 kWh）。

## 6. 遗留与边界（不影响本次出图验收）

- 本报告只覆盖 `prob02` accepted 版本的交付图；`robustness` / `ablation` 图件须另行生成与登记（团队裁定 B5：两者数值不得互相替代）。
- 文献门禁层面的技术债（prob02 池 23 条均未逐篇读正文、D10「5000 kW 作用侧」与 A18 填报无文献支撑）
  与本轮图件无关，但论文引用这些机制级主张时仍须遵守原有纪律；本报告未把任何口径选择包装为文献支持。
- LP 最优面可能不唯一（`E` 上下界两端活跃、日初取 96 个水平）：图件展示的是 run002 的求解器返回解，
  引用其数值时不比对逐点解的唯一性，结论以约束残差 + (I1)/(I2) + 目标值 + 表 1/表 2/表 3 为准。
