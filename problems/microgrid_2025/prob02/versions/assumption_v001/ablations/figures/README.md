# prob02 ablation 图件（实验产物，非交付图表）

- 来源 task：`5b87ce0a8d9e4706c82c`（`succeeded`、supervised、CPU、rc=0、seed=20260910）
- 原始目录：`ablations/results/prob02_v001_ablation_run001/figures/`
- 本目录为**逐字节副本**（未重绘）；数据来源与图注见 `../report.md` §10。

| 文件 | 内容 | 数据来源 |
|---|---|---|
| `ablation_model_cost.png` | 17 模型全期总费用 + 相对 M1 偏差（双面板） | `comparison.json` |
| `ablation_b_cap_curve.png` | M6/M6′ `B`–`Σq_em`–总费用双轴曲线 + β 区间带 | `summary.json.C5.grid`、`comparison.json.purchase_cap` |
| `ablation_structure_waterfall.png` | 跨日/终端/模型族结构对照（全期） | `comparison.json` |
| `ablation_complexity_tradeoff.png` | 求解时间（对数轴）–费用偏差散点 | `comparison.json[].solve_time_seconds` |

## 登记纪律

按 `ablations/plan.md` §4 与团队裁定 **B5**，ablation 图件属**实验产物**，**不调用 `record_figure_review`**、
不写入 `problems/microgrid_2025/figures.yaml`；prob02 的交付图表仍为 visualization 阶段登记的 11 张图件。
（与 prob01 `act-b0cec516722840f3` 将 4 张 ablation 图登记进 `figures.yaml` 的做法不同，冲突点已在
`../report.md` §1.3 显式记录。）

## 已知技术债

- `ablation_complexity_tradeoff.png`：`x≈6–7 s / y≈0–0.7%` 的低偏差簇标签相互靠近；定量判读以 `comparison.json` 为准。
- `ablation_model_cost.png`：最右侧 5 个柱的 x 轴标签较密。
- 图注引用时须保留：①`β ∈ (4218.75, 4375.00] kW`（勘误 R5）；②表 2 端点语义区分 prob01/prob02（勘误 R1）；
  ③终端自由的期末放空（`E_T=1200 kWh`）与价格套利显式区分。
