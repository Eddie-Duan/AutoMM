# prob01 图表视觉复核报告

- 归属：`microgrid_2025` / `prob01`；阶段：`visualization`
- 同步动作：`act-8b2f11ce718043f2`（负责人：visualization-agent）
- 接受版本：`assumption_v003` / `formulation_v001`
- 结果来源：task `1300a936c4d95653f9d1` / `run002`（sanity level_1_4 = `PASS_WITH_WARNING`）
- 生成脚本：`problems/microgrid_2025/prob01/versions/assumption_v003/figures/plot_prob01_figures.py`
- 样式来源：`config/visualization.yaml`（字体 Microsoft YaHei，色板 primary/secondary/accent/neutral/warning，DPI 180，PNG）
- 自动质检：`automm.visualization.inspect_png`（分辨率 ≥ 800×480、非空/非纯色、边界暗像素比例）

## 1. 复核方法

1. 脚本自动质检：9/9 张 PNG 均为 `quality_status = passed`（PNG 实际 1613×1344 ~ 1820×1496 px，远高于最小值）。
2. 逐图人工视觉复核：对每张导出 PNG 直接读图检查字体（无方框/缺字）、标题、轴标签、单位、图例、刻度、数值方向、
   文本截断与重叠、颜色区分、信息层级与是否误导；三维图额外检查视角、遮挡、透视失真、深度辨识与静态 PNG 可读性。
3. 发现即修正：首轮复核发现 4 处问题（见 §4），已修改脚本并重新生成，复检通过后才登记视觉复核结论。

## 2. 逐图复核结论

| # | stable_id | 回答的问题 | 自动质检 | 视觉复核 | 结论 |
|---|---|---|---|---|---|
| 1 | `prob01_fig_input_profile_dc7b2e52af` | 代表性单日的负载/光伏/电价结构如何 | passed | 字体正常；双面板共享 X 轴；单位 kW、元/kWh 明确；图例 2 项；电价区间注记移至左上空白，无重叠 | passed |
| 2 | `prob01_fig_netload_arbitrage_d9700035cd` | 光伏盈余窗口与充放电发生在什么价位 | passed | 盈余区用绿色填充 + 0 基准线；25%/75% 分位虚线直接可比；充/放电三角标记计数正确；图例移至轴下，正文注记置于零线下方空白，无遮挡 | passed |
| 3 | `prob01_fig_dispatch_profile_e1b9b885da` | 最优购电与充放电如何安排 | passed | 上：购电面积；下：充电向上/放电向下，符号语义在图例明示；峰值注记位于中上空白，避开 22:00 后购电尖峰；无同时充放电与序列一致 | passed |
| 4 | `prob01_fig_soc_trajectory_8b40330c06` | SOC 是否在运行区间内并日周期闭合 | passed | E_t 曲线、E_min/E_max/E_0=E_144 三组参考线区分清晰；`E_0`、`E_144` 箭头注记均落在空白区、不压曲线；|E_144−E_0| = 0 | passed |
| 5 | `prob01_fig_energy_balance_5a49223b71` | 逐时段供需构成是否闭合 | passed | 三项供给堆叠 + 需求虚线与堆叠顶端完全重合；残差 5.68e-13 kWh 注记于右上空白；图例 2 列不压 12:00 尖峰 | passed |
| 6 | `prob01_fig_price_action_3d_1e765c22c2` | 时间×电价×净放电的三维轨迹结构 | passed | 视角 elev=20°/azim=−62° 下三轴刻度与标签完整；色标与 Z 轴同义（净放电）；连线给出时序方向；散点密集区存在自遮挡，已由第 7 张二维投影消除歧义 | passed |
| 7 | `prob01_fig_price_action_2d_1075b2c7cb` | 三维轨迹的二维投影：电价—净放电关系 | passed | 面积/色标（时段 h）可读；零线分隔充放电符号；低电价充电、高电价放电的分位结构方向正确 | passed |
| 8 | `prob01_fig_block_summary_5801062f6e` | 表 2 六块充放电量与端点储电量 | passed | 分组柱 + 数值标注（6 位小数舍入到 1 位）；充放电分别列示不冲抵；0:00/24:00 = 6000.0 kWh 注记位于左上空白，不压柱体 | passed |
| 9 | `prob01_fig_cost_bounds_5a1a905c2f` | 最优费用是否落在解析可行区间 | passed | 水平条形 + 区间底纹 + 最优点竖虚线；三个数值均标注；区间宽度与相对位置（52.9%）注记清晰 | passed |

> 计数：接受版本 `assumption_v003` 下通过自动质检与视觉复核的 PNG = **9 张**，满足 `minimum_figures_per_question = 5`。

## 3. 三维图专项

- `price_action_3d` 选择的视角能同时看清「低价长时间充电段」与「高价放电簇」，无明显透视失真；
- 自遮挡仅出现在同一时段内的散点簇，不影响「低电价↔负净放电、高电价↔正净放电」的整体趋势判读；
- 按 `config/visualization.yaml` 的 `require_2d_companion_when_projection_is_ambiguous` 生成了配套二维投影
  `price_action_2d`，两者数值同源（同一 `solution.json`），结论一致。

## 4. 首轮复核发现并修正的问题

| 图 | 首轮问题 | 处理 |
|---|---|---|
| `soc_trajectory` | `E_0` 注释偏移量以「点」为单位误设 1400/1600，导致画布被撑到 1609×7616 px；且 `E_0` 误标为序列首值 6750 | 改为小偏移箭头注记，`E_0` 按题面给定初值 6000 kWh 标注，`E_144` 取序列末值 |
| `dispatch_profile` | 峰值注记（右上）与被 22:00 后购电尖峰压盖 | 注记移到中上空白区，改「第 5 段」表述 |
| `netload_arbitrage` | 盈余时段注记与左上图例重叠 | 注记移到零线下方空白区；图例移到坐标轴外下方 |
| `block_summary` | 端点储电量注记框压到块 3 数值标注 | 注记框移到左上空白区 |

修正后 9 张全部复检通过；`soc_trajectory` 尺寸回到正常区间（1820×1100 px）。

## 5. 口径与追溯说明（须在论文图注中保留）

- X 轴一律为 **位置口径**（AS01 左端点：第 `i` 段 = `[10(i−1), 10i)` min，刻度为附件时间戳），
  计划窗为 `0:10→24:10`，相对自然日整体前移 10 分钟；表 2 的 0:00/24:00 为「计划窗首/末状态」。
- 费用量纲按 AS03a/D9：`C_plan = Σ p_t·b_t`（元），**不乘 Δt**；9 张图的费用数字均出自 `solution.json`。
- `dispatch_profile` 的充放电上限（充电 833.33 kWh、放电 750.00 kWh）按团队裁定 D10/勘误 E1（q_dis ≤ 750.00）。
- 所有图数值均来自 `solution.json` / `tables.json` 序列，无手工抄录；`source_hash` 已登记在题目 figure manifest。
