# prob04 可视化视觉复核报告（`visualization` 阶段）

- 动作：`act-a752e4172fdd43b4`（policy P5 / `run_agent`；agent = `visualization-agent`；stage = `visualization`）
- 小问：`microgrid_2025` / **prob04**（问题 4：**波动电价下重算问题 2 与问题 3**，交付 `result4-2.xlsx` 与 `result4-3.xlsx`）
- 版本：假设 `assumption_v001`（accepted）/ 公式 `formulation_v001`（accepted）
- 数据源（**两链分别**，均为隔离 task、attempt 1、supervised、CPU HiGHS、`rc=0`、`probe_mode=false`、365 天 / 52,560 时段）：
  - 链 `4-2`：task `892351beefa2bc5f7804` → `results/prob04_v001_f001_4-2_run002`
  - 链 `4-3`：task `eca261e1d516ab2867d9` → `results/prob04_v001_f001_4-3_run002`
- 入口 sanity：`level_1_4 = PASS_WITH_WARNING`（`act-d7fa5a1e75ac4428`，`checks_failed=[]`、`blocking_reasons=[]`）
- 出图脚本：`problems/microgrid_2025/prob04/versions/assumption_v001/figures/plot_prob04_figures.py`
- 本动作**只读**：不重解 LP、不改代码/模型/假设/公式/结果/原始数据、未创建或提交 task、未安装依赖、未占用 GPU。
  写入仅限本版本 `figures/` 目录、`problems/microgrid_2025/figures.yaml` 的 prob04 登记项与 `runtime/actions/act-a752e4172fdd43b4/evidence/**`。

## 1. 结果概览

| # | stable_id | 链 | kind | 自动质检 | 视觉复核 | 收录论文 |
|---|---|---|---|---|---|---|
| 1 | `prob04_fig_price_belief_chain_0f0c113ea4` | 两链 | price_belief_chain | passed 2468×1718（暗比 0.000） | passed | 是 |
| 2 | `prob04_fig_forecast_backtest_33ec6918c7` | 两链共用 | forecast_backtest | passed 2396×1208 | passed | 是 |
| 3 | `prob04_fig_kappa_rolling_correction_562118434e` | `4-3` | kappa_rolling_correction | passed 2396×1172 | passed | 是 |
| 4 | `prob04_fig_dispatch_profile_42_6cef29f9f5` | `4-2` | dispatch_profile_42 | passed 2468×1718 | passed | 是 |
| 5 | `prob04_fig_plan_adjust_profile_43_14d05cff1e` | `4-3` | plan_adjust_profile_43 | passed 2468×1756 | passed | 是 |
| 6 | `prob04_fig_cost_decomposition_21e04b722c` | 两链 | cost_decomposition | passed 2540×1316 | passed | 是 |
| 7 | `prob04_fig_soc_trajectory_7a09b8f02b` | 两链 | soc_trajectory | passed 3106×1208 | passed | 是 |
| 8 | `prob04_fig_emergency_profile_43_ee87fab821` | `4-3`（`4-2` 对照） | emergency_profile_43 | passed 2468×1604 | passed | 是 |
| 9 | `prob04_fig_adjust_surface_3d_71403364a6` | `4-3` | adjust_surface_3d | passed 1837×1487 | passed（三维专项） | 否（配套 2D 承担定量判读） |
| 10 | `prob04_fig_adjust_heatmap_2d_faadb9f50e` | `4-3` | adjust_heatmap_2d | passed 2036×1568 | passed | 是 |
| 11 | `prob04_fig_tiebreak_degeneracy_a22f550697` | 两链 | tiebreak_degeneracy | passed 2468×1208 | passed | 否（披露图） |

11 张图全部通过 `automm.visualization.inspect_png`（`errors=[]`、`warnings=[]`、边界暗像素比 0.000）与逐图人工视觉复核；
`config/visualization.yaml` 的 `minimum_figures_per_question = 5` 与 `require_automated_pass`/`require_visual_review` 均已满足。
字体自动探测取 `Microsoft YaHei`（首选命中），无方框缺字（唯一缺字形 `⇒`(U+21D2) 已在出图前替换为 `→`）。

## 2. 出图前数据审计（只读探针，未求解）

`runtime/actions/act-a752e4172fdd43b4/evidence/`：

- `probe_prob04_figure_data_audit.py` → `figure_data_audit_out.json`：从两链落盘序列独立复算全部拟绘制数值，
  并与 `run_manifest.delivery` / `solution.daily` 逐位比对（容差 1e-6）：
  - 交付期 `C_plan / C_adj / C_em / C_total / C_total^fc / ΔC_price` 两链全部一致；
  - 结算层缺口恒等式 `q_em = max(0, −(q + q_dis + PV^act·Δt − L·Δt − c))`：两链全期最大偏差 **0.0 kWh**；
  - 费用分解恒等式 `C_total = C_plan + C_adj + C_em`：残差 0.0；
  - 两链差额三分项归因恒等式残差 −9.31e-10 元（6 位小数舍入）。
- `probe_prob04_kappa_rebuild.py` → `kappa_rebuild_out.json`：按 `AS11` 从附件 4 实际价独立重建 `κ_m` 与逐层信念价，
  与落盘 `series.price_belief_yuan_per_kwh` **逐位一致（差 0.0）**；`κ_m` 范围 `[0.6623297807778713, 1.5493928472727483]`、
  最小值在 0-based day 135 的 `m=18`、**截断 0 次** —— 与 `sanity_report.md` §3.2 的 **N1 更正**一致
  （上游旧登记 `[0.50133, 1.54939]` 下界不可复现，本动作图件与响应一律采信更正后范围）。

出图脚本 `derive()` 内置同样的自检（任一失败即中止出图）：结算层缺口恒等式 ≤1e-6、`κ_m` 重建差 ≤1e-12、
六项费用字段与 `run_manifest.delivery` 差 ≤1e-6。

## 3. 逐图视觉复核意见

1. **`price_belief_chain`（两链）**：上排两个代表日（2025-02-01 交付期首日、2025-06-21 夏至）给出附件 4 实际价、
   计划层信念价（= 前一日同时段，两链共用）与链 `4-3` 逐层信念价（`κ_m` 滚动校正），6:00/12:00/18:00 竖点线齐全；
   下排左为链 `4-3` 全部 52,560 时段散点（每 7 时段抽 1 点）按支配层 `m` 着色 + 45° 参考线，下排右为两链交付期绝对价格误差直方图。
   图例 3 项置于画布底部（不压曲线）、注记框在空白区；**无任何「当天电价已知」类表述**（`A8-(b)` 派生⑤）。
   复核通过（首轮即通过）。
2. **`forecast_backtest`（两链共用）**：左为 MAE（主判据）与 MAPE 双轴分组柱，右为 RMSE/P90/P99；
   两链 `forecast_backtest.json` 逐字节相同，图注已声明「两链共用同一预测器与同一回测协议」。
   **首轮缺陷**：`E-F5` 注记框压住 P99 柱（已把右轴上限由 1.42× 提至 1.78×，并把注记移到右上空白并缩短 1 行）。
   复核通过：90° 旋转的柱内数值标注完整不重叠；`E-F5` 的「成对给指标、禁止只报单一指标」文字可读。
3. **`kappa_rolling_correction`（仅 `4-3`）**：左为 `κ_6/κ_12/κ_18` 的 365 天序列 + `κ=1` 与截断界 `[0.5,2.0]` 横线，
   右为三条分布叠加直方图；注记给出范围、最小值位置、截断 0 次与「重建差 0.0」，并显式登记 `N1` 更正。
   **首轮缺陷**：x 轴标签沿用了通用模板的「红虚线为 2025-02-01 交付期起点」，但该面板并未画交付期线（已补画红虚线，
   并把轴标签改为纯日期区间）。复核通过。
4. **`dispatch_profile_42`（仅 `4-2`）**：2025-03-20 / 2025-12-21 的计划购电（`q≡b`）、充电（向上）、放电（向下）
   与附件 4 实际价（右轴），下排为同日完整日内储电量轨迹 `E_{d,0}…E_{d,144}` 与运行上下界。
   **首轮缺陷两处**：① 下排两个子图标题完全相同（已按日期区分）；
   ② **SOC 日初口径错误** —— 落盘 `series.storage_kwh` 的日切片为 `E_{d,1}…E_{d,144}`（时段末状态），
   首轮误把其首元素当作 `E_{d,0}`，导致标注「日初 1,724.6 kWh（= 前一日末态）」；
   已改为前置 `daily.state_start_kwh`（`E_{d,0}`）并采用时段端点 x 轴（145 点），
   修正后两日 `E_{d,0} = E_{d,144} = 1,200.0 kWh`，与 `E_{d,0}=E_{d-1,144}` 的滚动递推一致。复核通过。
5. **`plan_adjust_profile_43`（仅 `4-3`）**：上排 2025-03-20 / 2025-12-21 的计划购电 `b`、最终购电 `q`、
   上调/下调填充与紧急购电 `q_em` 柱；下排为同日逐时段调整量 `q−b`。
   **首轮缺陷**：左上角局部图例与画布底部总图例重复且压住曲线（已删除局部图例）；下排标题已按日期区分。复核通过。
6. **`cost_decomposition`（两链）**：左为交付期与全期 × 两链的费用堆叠（`C_plan/C_adj/C_em`）与主值、`ΔC_price` 标注；
   右为两链交付期差额瀑布（`ΔC_plan` → `C_adj` → `C_em`）。
   **首轮缺陷**：右图注记框压住绿色/橙色台阶（已移到左上角空白并缩小字号）。
   复核通过：右面板纵轴虽从 0.94×`C^{act}` 起，但两端的「主值」柱仍完整可读，注记给出差额三分项与「`ΔC_price` 不是差额分项」的
   口径区分（`D7`/`D11`）。
7. **`soc_trajectory`（两链）**：(a) 全年逐日 min–max 带 + 日内均值 + 上下界；(b) 交付期首日与夏至的完整日内轨迹（4 条线）；
   (c) 交付期 334 天的日初/日末储电量均值 + min–max 误差棒。
   **首轮缺陷两处**：① (c) 原设计为 `(E_{d,0}, E_{d,144})` 散点，实测两点几乎全部落在 `E_{d,144}=1200` 的水平线上，
   被坐标轴下界与 `E_min` 参考线遮挡、信息量近零（已改为 4 组柱 + 误差棒 + 数值标注，直接读出「全部 = 1200 kWh」）；
   ② (b) 存在与图 4 相同的 SOC 日初口径错误（已修）。修正后 `E_{d,0}` 曲线自 1200 kWh 起，与日末闭合。
   复核通过：日边界「不携带电量、跨日无对冲」的结论在 (c) 中直接可读（直面 prob03 `E8`/`R18`）。
8. **`emergency_profile_43`（`4-3` 主，`4-2` 对照）**：左上逐日 `Σq_em`（`4-3` 填充 + `4-2` 恒零线 + 交付期日均 1,179.7 kWh/日）；
   右上小时块分布（柱顶为触发时段数）；左下 2025-02-01 结算层缺口与落盘 `q_em` 逐时段重合（恒等式核对）；
   右下触发时段价格分布 + `E-F2` 深谷披露。
   **首轮缺陷两处**：① 左上纵轴上限过低致图例压住尖峰（已加 1.42× 留白）；② 右上 6:00 块的柱顶计数标签贴顶（已加 1.16× 留白）。
   复核通过。
9. **`adjust_surface_3d`（仅 `4-3`，三维专项）**：`elev=26°`、`azim=−58°`；三轴与色标标签完整、无自遮挡。
   **首轮缺陷**：Z 轴按 0.5/99.5 分位截断，把个别尖峰切成竖直墙面（**不忠实于数据**）；
   已改为 **Z 轴取完整值域 [−2,821, 3,532] kWh/h、仅色标按 99.5 分位 1,604 截断**，
   并**新增底面同数据等高线投影**（12 层）以读出低幅结构（改为完整值域后低幅结构在曲面上不可辨，正需该投影）。
   三维专项复核通过：投影歧义由二维配套图 `adjust_heatmap_2d` 消除，图注已写明「定量判读以二维配套图为准」，
   该图 `included_in_paper=false`，不单独作为定量判读来源。
10. **`adjust_heatmap_2d`（仅 `4-3`）**：上为 365×24 调整量热力图（|·| 99 分位 1,196 kWh/h 截断，交付期起点黑虚线），
    下为逐日调整量柱与交付期日均 1.186 MWh/日。首轮即通过；注记给出全期调整量合计 432,817.2 kWh、上调 5,772 / 下调 974 时段。
11. **`tiebreak_degeneracy`（两链，披露图）**：左为 `AS21` 次目标加入前后**主目标**的逐层相对变化（对数轴 + 1e-9 容差线），
    右为逐层 LP 退化度密度（两链）。
    **首轮缺陷三处**：① 左面板纵轴下限 1e-16 把真实窄带（5e-10 附近）压成一条细线、且注记框压住容差线
    （已把下限改为 1e-10，注记移到左下并补「全部层落在 [5.0000e-10, 5.0001e-10]，距容差约 1 个数量级余量」）；
    ② 右面板图例压住蓝色峰值（已加 1.32× 上限留白）；③ 右面板注记压住橙色尾部（已移到右上空白）。
    复核通过：`D11`（不以逐点解唯一性作判据）与 `T7-6`（统一 tie-break）文字完整可读。

## 4. 纪律符合性自查

| 强制项 | 出处 | 本动作执行 |
|---|---|---|
| 两链分别标注、不得混为一条 | `AGENTS.md`「prob04 交付结构」阶段级要求 5 | 11 张图中 7 张为两链并列（各面板/图例分色并标注链 ID），4 张为单链专属（kind 名与图内文字均显式写出 `4-2` / `4-3`） |
| 不得出现「全天电价已知」类表述 | `A8-(b)` 派生⑤ | 脚本与全部图内文字、图注已逐一自查（仅出现「当天电价尚不可知」的正面表述）；出图脚本 docstring 亦登记该纪律 |
| 引用预报误差须成对给出指标 | `E-F5` | `forecast_backtest` 同图给出 MAE/MAPE 与 RMSE/P90/P99；价格误差直方图注记给出 MAE/P90/P99 |
| `κ_m` 范围用更正后值 | `sanity` `N1` | 图内与图注均为 `[0.6623297807778713, 1.5493928472727483]`，并显式登记旧值不可复现 |
| `E-F2` 极松下界与深谷披露 | 团队勘误 `E-F2` | `emergency_profile_43` 右下注记给出 `min 0.0076`、`<0.10` 仅 28 格、深谷 5× 紧急价 0.038 元/kWh 与解析下界 155,129.41 元 |
| 3D 图须有视角/遮挡/透视检查与二维配套 | `config/visualization.yaml` | 第 9 项已逐条检查并配 `adjust_heatmap_2d` 二维定量配套 |
| 不得修改数据或筛除不利结果 | 角色约束 | 图件全部由落盘 accepted 产物与只读重建量生成；未删任何时段/样本；下调时段（974 个）如实呈现 |

## 5. 技术债与披露

- **V1（口径修正，已修）**：落盘 `series.storage_kwh` 的日切片为 `E_{d,1}…E_{d,144}`，**不含** `E_{d,0}`；
  日内 SOC 图必须前置 `daily.state_start_kwh` 并改用时段端点 x 轴。首轮两张图（`dispatch_profile_42`、`soc_trajectory`(b)）曾误标日初值，
  已修正并复检通过。后续任何引用 SOC 日初值的图件必须沿用该约定。
- **V2（登记）**：`adjust_surface_3d` 的 Z 轴为完整值域（含 3,532 kWh/h 的尖峰），故曲面低幅结构不可辨，
  定量判读**必须**改用配套二维图；色标仍按 99.5 分位截断（图内已注明「Z 轴不截断、色标截断」的差异）。
- **V3（登记，承 `D11`/`D12`）**：`tiebreak_degeneracy` 的左面板逐层相对变化全部落在约 `5.0e-10` 的窄带内（带宽 ~1e-14），
  图面呈近似水平带属**真实结果**（不是绘图退化）；`4-3` 存在 ±1e-8 kWh 级求解器容差噪声（`D12`），
  图件与响应中的储电量引用一律按 6 位小数规整。
- **V4（披露，承 `D4`）**：`4-3` 调整层 `m=6/12` 的层目标含前视尾巴，本动作未据其做任何图面数值标注。
- **V5（待办，非本阶段）**：`robustness`/`ablation`（均为 `config/workflow.yaml` 的 `mandatory_stages`）完成后的图件
  将另行登记；本动作未登记任何 robustness/ablation 图，也未执行其计算。
- **V6（口径边界）**：本动作图件中的 `Σq_em`、`E_{d,144}`、`ΔC_price` 等数值一律来自 **run002（accepted）**；
  `run001` 仅作审计负对照，未被任何图件引用。

## 6. 结论

prob04 accepted 版本（`assumption_v001` / `formulation_v001` / 两链 `run002`）的正式图件已生成、登记并通过
**自动质检 + 逐图视觉复核**双重门禁，覆盖「价格可观测性与决策—结算分离」「主预测器回测纪律」「`4-3` 滚动价格校正」
「`4-2` 日内调度」「`4-3` 计划/调整/紧急购电」「两链费用分解与差额归因」「SOC 与日边界行为」
「紧急购电机制与 `E-F2` 事实」「`4-3` 调整量 3D+2D」「AS21 退化披露」十个主题，且两条链在每张图内均被显式指明。
追溯链（`stable_id` / `source_hash` / `task_id` / `script` / `quality_report`）完整，全部数值与 accepted 产物逐位一致。

- 报告生成：`act-a752e4172fdd43b4`（2026-09-11）
