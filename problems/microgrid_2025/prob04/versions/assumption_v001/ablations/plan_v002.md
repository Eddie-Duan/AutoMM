# prob04 消融与模型族对照实验方案 · `plan_v002`（跑数前修订，判据不变）

- 归属：`microgrid_2025` / `prob04` · 阶段 `ablation` · 版本目录
  `problems/microgrid_2025/prob04/versions/assumption_v001/ablations/`
- **与 `plan_v001` 的关系**：`plan_v001.md`（2026-09-11 23:54 冻结）**原文保留、一字不改**。
  本文件是**跑正式对照数值之前**、由 `ablation-analyst` 在其同步动作
  `act-9c331bdc27524fcd`（2026-09-12）中新增的修订案。
- **判据与口径状态**：`plan_v001` §2 的 `C1`–`C9`、§3.8 的公平性纪律、§5 的输出布局
  **全部不变**，阈值一个都没有放宽；§2「事后不得修改判据」的纪律**未被触碰**。
  本文件只做两件事：**(a) 记录 run001 的失败与代码修订；(b) 补全 `C-ANCHOR-P03` 的构造细节。**
- 触发依据：`AGENTS.md`「不静默沿用旧登记、冲突时显式记录」；`agents/ablation-analyst.md` 步骤 0；
  `plan_v001` 文首「事后若发现范围有误，必须新建 `plan_v002` 并保留 `plan_v001` 与已跑结果」。

---

## 1. run001 的终态与失败指纹（必须先登记，再谈修订）

| 链 | task | status | failure_class / type | 处置 |
|---|---|---|---|---|
| `4-2` | `639de3861bced76d1b96` | `succeeded`（rc=0，supervised，attempt 1） | — | 产物保留在 `..._4-2_run001/`，**作为对照证据，不作为交付值** |
| `4-3` | `5304b4d42b3953fedf9a` | `failed`（rc=1，attempt 1） | `code_runtime` / `process_exit` | 产物仅 `BASE-43/`；**整批作废**，按 `plan_v001` §6 以新代码 + 新 `output_directory` 重跑 |

- `4-3` 的 traceback（`runtime/tasks/5304b4d42b3953fedf9a/attempt-001-stderr.log`）：
  `ablation_prob04.py:345 read_attachment1_price → InputValidationError: 附件 1 第 2 列表头不是「电价」: '电价'`。
- **根因（已定位，非模型问题）**：`ablation_prob04.py` 的源文件在写入磁盘时经历了一次
  **「UTF-8 文本被按 GB18030 解码后重存」的转码事故**——脚本内所有中文串成了乱码
  （`"电价"` → `"鐢典环"`，129 个私用区码位），因此
  `if header[1] != "鐢典环"` 对真实的表头 `"电价"` 恒为真，锚点在第一行就抛错。
  同一事故还**吃掉了若干换行**（某个 3 字节汉字的后 1 字节 + 紧随的 `\n` 被解码器换成 `?`），
  造成两类次生缺陷（见 §2）。

---

## 2. 代码修订（`ablation_prob04.py`，run001 → run002）

修订**只作用于 `ablations/code/ablation_prob04.py`**；accepted `code/`、`formulations/formulation_v001/`、
`assumptions.md`、`results/prob04_v001_f001_*` 一律未触碰（`plan_v001` §3.8）。

1. **编码修复（逐行逆向映射 + 人工补丁表）**
   - 对每个非 ASCII 连续片段做 `gb18030 编码 → UTF-8 解码` 的逆向映射；用
     「逆向结果是否像中文」的判据区分**乱码片段**与**本来就正确的中文片段**，后者原样保留。
   - 转码时被 `?` 吞掉字节、不可逆的位置（112 行）由人工补丁表按语义重写，
     并在同一处补回被吞掉的换行。
   - **验证**：修复前后 `ast.dump`（字符串常量归一化后）逐节点 diff，差异**只有 3 项**：
     (i) 重新激活被注释掉的 `ub_rows, ub_cols, ub_vals, ub_rhs = [], [], [], []`；
     (ii) 两处 f-string 字段名由乱码标识符（运行时会 `NameError`）恢复为 `exc` / `failed_checks`。
     `ruff`（项目 venv）`All checks passed`、`compileall` 通过。

2. **次生缺陷 1 —— 被注释掉的列表重置（数值相关，必须登记）**
   - 位置：4-3 的 `S-VAR` 不等式块。原文件把
     `ub_rows, ub_cols, ub_vals, ub_rhs = [], [], [], []` 并进了上一行的 `#` 注释，
     导致第二个建块循环**追加**而非重建，`coo_matrix` 对同一 `(row, col)` **求和**，
     生成的 `a_ub` 与 formulation §3.6 的分段线性化 `u^± ≥ max(±(b − q), 0)` 不一致。
   - 修复后**实测数值中性**：4-2 的 `S-VAR` 期望费用与 run001 逐位相同
     （`expected_cost_total_yuan = 394769.6783257871`、`delta_pct = −3.2859882594369387`）。
   - 该缺陷**只影响 `S-VAR`/`S-VAR-RH` 分支**，`BASE`/`S-RH`/`PF-AR`/结构消融不受影响
     （`BASE-42` 与 accepted `run002` 的 `D_req = 13,006,411.0411` 元逐位一致）。

3. **次生缺陷 2 —— 两处会在运行期抛 `NameError` 的诊断打印**
   - `print(f"[ablation] 参考解重放失败…{exc}")` 与 `print(f"[ablation] 硬检查未通过：{failed_checks}")`
     的字段名被乱码污染成未定义标识符。run001 未触发（参考解重放成功、`checks_failed=[]`），
     属潜在故障；本次一并修复。

---

## 3. `C-ANCHOR-P03` 构造补全（**只补数据、不改模型方程，判据 `C1` 不动**）

### 3.1 事实（实测，非推断）

- 修复后锚点可以跑通，但 `C1` 的六项中**两项超限**：

  | 项 | 观测 | 参考（prob03 `run003` M1） | 相对差 |
  |---|---|---|---|
  | `D_full_C_total` | 16,180,953.435565 | 16,179,176.145228 | 1.0985e-4 |
  | `D_req_C_total` | 14,540,616.335652 | 14,540,616.335652 | 1.2e-14 ✔ |
  | `D_full_C_plan` | 13,885,669.475554 | 13,885,669.475555 | 2.7e-14 ✔ |
  | `D_full_C_adj` | 564,875.422873 | 563,098.132533 | 3.1563e-3 |
  | `D_full_C_em` | 1,730,408.537138 | 1,730,408.537141 | 6.8e-14 ✔ |
  | `D_req_sum_q_em` | 391,274.485914 | 391,274.485914 | 5.3e-14 ✔ |

- **残差可完全归因到 `d = 2025-01-01` 这一天**：`D_req`（2025-02-01…12-31）的五项全部 ≤1e-13；
  `D_full` 与 `D_req` 的 `C_plan`/`C_em` 逐位一致 ⇒ 差额只可能落在 1 月；
  而 `D_full` 的 `ΔC_price = −30,558.377455` 元、`D_req` 的 `ΔC_price = 0`，正是该日的量级。
  `C_adj` 残差 = `C_total` 残差 = **+1,777.290337 元**。

### 3.2 根因

- 锚点序的性质：价格序列是**同一单日曲线 × 365 天**。对 `d ≥ 1`，`PF-PERSIST` 精确、
  `κ_m = A_m/B_m ≡ 1`、`layer_price` 逐项等于当日实际价 ⇒ `4-3` 精确退化为 `M1`。
- **对 `d = 0`（2025-01-01）不成立**：accepted 模块对「无前一日」取
  `fallback_price() = 常量中性价 1.0`（`prob04_predict.layer_price` / `belief_price` 的已登记回退，
  带完整 `fallback_constant_price` 登记与理由），于是调整层的**未实现部分**（`i > 6h`）
  在 `d = 0` 用平坦价，而 prob03 `M1` 当日全天都用那条曲线。
- `plan_v001` §3.5 写的「该构造下 `4-3` 的 `layer_price` 逐项等于当日实际价」
  **对 `d = 0` 不成立** —— 这是**构造描述的不完整**，不是 accepted 模型的错误
  （该回退是 4-3 在 `A8-(b)` 下的合法且已登记的信息集约定）。

### 3.3 补全方式

- 在 `ablations/code/ablation_prob04.py` 的 `run_chain_variant` 增加**仅锚点使用**的
  `fallback_seed` 形参：锚点运行期间把「无前一日」的中性回退项替换为**锚点自身的单日曲线**
  （即 `2024-12-31` 的价格，按「同一曲线 × 365」的构造它本就等于该曲线），`finally` 中恢复。
- **性质界定**：这是**补数据**（把构造已经隐含的前一日价格喂给模型），**不改任何模型方程**、
  不改 accepted `code/`、`κ`/效率/弃光界/tie-break 全部不变；`d ≥ 1` 完全不受影响。
- **效果（实测）**：六项相对差变为
  `1.4e-14 / 1.2e-14 / 2.7e-14 / 4.9e-13 / 6.8e-14 / 5.3e-14`，
  `C1` **pass = True**、脚本 exit code = 0。判据 `C1` 的阈值 `1e-9` 与六项清单**一字未改**。
- **强制登记**：`summary.anchor_construction.fallback_seed` 逐项写明该替换、其理由、
  以及未替换时的残差（+1,777.290337 元 / −30,558.377455 元），论文与 `report.md` 必须披露。

---

## 4. 本次执行修订（run002）

| 项 | run001 | run002（本次） |
|---|---|---|
| `code_hash` | `d33ee2ef…`（乱码版） | 见 `task.json`（编码修复版） |
| `output_directory` | `..._ablation_4-2_run001` / `..._4-3_run001` | `..._ablation_4-2_run002` / `..._4-3_run002` |
| 对照集合 | `--cases all` | **不变**（`--cases all`，两链分别提交） |
| 求解器/时限/种子 | HiGHS / 60 s 每层 / 20260911 | **不变** |
| `run001` 产物 | — | **原样保留**，不覆盖、不删除；只作对照证据 |

- 两条链**同时重跑**（而不是只重跑 4-3），理由：`code_hash` 一致才能满足 `plan_v001` §3.8 的
  「同代码修订、同参数、同预算」可比性；且 run001 的 4-2 JSON 产物同样含乱码。
- 预注册判据 `C1`–`C9`、比较口径（`ΔC = 对照 − 主口径`、分链报告、`D_full`/`D_req` 分列）
  与 `plan_v001` §2 完全一致。

---

## 5. 本文件不改变的事项（明确声明）

1. 不改变 `plan_v001` 的任何判据、阈值、对照集合、公平性纪律与失败处置。
2. 不改变 accepted `assumption_v001`、`formulations/formulation_v001` 与同版本 `code/`。
3. 不把 `run001` 的任何数值引作交付值或对照值（`run001` 的 4-2 分支数值仅作 §2.2 的
   数值中性证据，且该证据只针对「列表重置」这一处差异）。
4. 不把 `C-ANCHOR-P03` 的任何数值写回 prob03、不进入 `result4-2.xlsx` / `result4-3.xlsx`。
5. 主口径仍是 `PF-PERSIST` 点预测 + 确定性 LP；`S-VAR`/`S-RH`/`S-VAR-RH`/`PF-AR` 只进 `ablation`。
