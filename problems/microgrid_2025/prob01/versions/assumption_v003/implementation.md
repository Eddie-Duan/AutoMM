# 实现计划（implementation，prob01）

- 归属：`microgrid_2025` / `prob01`；阶段：`implementation`
- 同步动作：`act-0f8555fda45b4e1f`（负责人：implementation-agent）
- 版本目录：`problems/microgrid_2025/prob01/versions/assumption_v003/`
- 输入依据（只读）：`request/problem.md`、`data/附件1.xlsx`、`data/附件5/result1.xlsx`、
  `../../assumptions.md`（accepted，assumption_v003，**末尾含「团队勘误」E1–E3**）、`../../version.yaml`、
  `formulations/formulation_v001/{formulation,formula_validation}.md`、`formulations/formulation_v001/parameters.yaml`、
  `../../../../global_symbols.yaml`
- 规则依据：`agents/implementation-agent.md`、`agents/resource-manager.md`、`PROJECT.md`、`RESEARCH_LOOP.md`、`config/gates.yaml`
- **重做记录**：本文件由动作 `act-fd5e1868958f4329` 更新（团队要求「自 implementation 重新走」）。accepted 口径
  （assumption_v003 / formulation_v001 / 团队勘误 E1–E3）未变，初版代码整体复用，但**修复了一处只在 144 时段
  才触发的表 1 标签校验缺陷**（初版会以 exit 4 终止且不写任何产物），并把 task spec 的 `output_directory` 改为
  `..._run002`（attempt-001 以 `interrupted` 结束，重跑不得覆盖旧目录）。详见 §10。
- 不覆盖历史：未修改 `assumption_v001/`、`assumption_v002/`、`assumption_v003/assumptions.md` 及任何既有产物；
  `data/`、`request/` 只读。
- **本动作未运行完整 144 时段计算**（implementation 阶段禁止运行完整数据集）。正式结果由 `computation`
  阶段的隔离 task + supervised worker 产出；本文记录的是静态检查与小型探针。

---

## 1. 口径落地清单（accepted 假设 / formulation → 代码位置）

| 口径 | 取值 | 代码落点 |
|---|---|---|
| AS01 左端点对齐 | 位置 `i` ↔ 区间 `[10i−10, 10i)` 分钟；计划窗 `0:10→24:10` | `prob01_io.read_attachment1`（按行位置读取，不做时间排序/插值）、`run_prob01.TABLE1_SLOTS` 行位置校验 |
| AS02 附件 1 独立代表日 | 只用 `data/附件1.xlsx` | `run_prob01.main` 的 `lp_data` 构造 |
| AS03a + D9 目标量纲 | `min Σ p_t·b_t`（元，**不带 Δt**） | `prob01_model.build_lp` 的 `objective` |
| AS05 两侧 90% 效率 | `E_t = E_{t−1} + 0.9·c_t − q_t/0.9` | `prob01_model.build_lp` 的 (R2) 行 |
| AS06 + D10 + **勘误 E1** | `c_t ≤ 833.3333`（并网点侧紧）、`q_dis_t ≤ 750.0000`（电池侧紧） | `prob01_model.C_CAP` / `Q_CAP` 与变量界 |
| AS07 纯 LP + 事后互补性验证 | 不引入二元变量 | `prob01_model`（LP）+ `evaluate` 的 `complementarity_sum` 检查 |
| AS08 + **勘误 E3** | 显式 `s_t`，`0 ≤ s_t ≤ PV_t·Δt`，目标系数 0 | (R3) 上界与 `evaluate` 的弃光检查 |
| AS09 Δt | `Δt = 1/6 h`；功率列乘 Δt 得 kWh；决策变量本身为 kWh | `DELTA_T`、`load_energy` / `pv_energy` |
| AS10/AS11 日周期 | `E_0 = 6000`、`E_144 = 6000` | (R2) 首行 RHS = `E_INIT`，末时段 `E` 界固定 `(6000, 6000)` |
| AS13 表 1/表 2 | 表 1 行位置 60/72/84/96/108/120；表 2 每 24 行一块、不冲抵；0:00/24:00 = `E_0`/`E_144` | `run_prob01.build_tables`、`prob01_io.fill_result_workbook` |
| AS15 | `b_t ≥ 0` 无上界、无售电（`s_t` 系数 0） | 变量界 `(0.0, None)` |

### 1.1 与上游产物的不一致（显式记录，未静默沿用）

| # | 冲突/差异 | 本实现采用 |
|---|---|---|
| C1 | `global_symbols.yaml` 把 `q_dis` 域写作 `P_dis_max·Δt`（833.33） | **团队勘误 E1 + D10 效力最高**：取 `750.0000`，代码中 `Q_CAP = P_MAX·Δ_t·η_dis` |
| C2 | `global_symbols.yaml` 登记 `q_spill` 的 `first_question = prob02` | **E2**：prob01 即使用 `s_t`；符号含义不变 |
| C3 | `version.yaml` 中 AS08 措辞「必然被激活」 | **E3**：变量保留、最优解允许取 0；代码不做任何强制 `s_t > 0` 的约束 |
| C4 | AS06「5000 kW 作用侧」为 `team_decision`，无文献支撑 | 代码按 D10 口径丙实现；本文不声称有文献依据 |
| C5 | A2/A6/A7/A8/A9 未裁定 | 均属 prob02–prob04；本实现只处理单日周期口径，不外推 |

---

## 2. 代码结构与职责

目录：`code/`（当前 accepted 版本内，可迭代；输出目录另行保留）

| 文件 | 职责 | 主要接口 |
|---|---|---|
| `prob01_io.py` | 读附件 1（表头/行数/有限性/正电价校验）、读模板标签、把解填入 `result1.xlsx`、写 JSON（禁 NaN/Inf） | `read_attachment1`、`inspect_template`、`fill_result_workbook`、`write_json` |
| `prob01_model.py` | 构造 (P1) 的 `A_eq/b_eq/bounds`、调用 HiGHS、计算指标与恒等式 (I1)/(I2)、逐条硬约束检查 | `LpData`、`build_lp`、`solve_lp`、`evaluate` |
| `run_prob01.py` | CLI 入口：解析参数、组装并求解、按模式写产物、以退出码表达失败语义 | `main`（`--data/--template/--output/--periods/--time-limit`） |
| `task_config.yaml` | task 级配置（`compute`/`solver`），提交时作为 `--config-path` | – |
| `task_spec.yaml` | 隔离计算 task 的完整规格（命令、路径、超时、期望产物、失败条件） | – |

代码文件 sha256（动作 `act-fd5e1868958f4329` 修订后，当前值）：

| 文件 | sha256 |
|---|---|
| `prob01_io.py` | `f1c3ec7d2d74afbb8db00a74c8a242b217b4c39dd8375b3abe518179e20b2f0a` |
| `prob01_model.py` | `55e30e5e6ad329772ebde856048a1062431eaed599f1a17230489ac341e58575` |
| `run_prob01.py` | `ebbf2602c18778ef8304b845359ff4f541a5c3e0f8782f09223bbde72cce120c` |

> 初版（`act-0f8555fda45b4e1f`）的 `run_prob01.py` sha256 为 `1c4326f0b22e0473a5a955f6d2ad84abfd2fdb6bcad679fd4004c3f3e9a0c20f`；
> 本次仅修改该文件的 `build_tables`/`main`（表 1 标签校验），`prob01_io.py`、`prob01_model.py` 未改动。

代码目录的 harness 指纹（`automm.common.hash_path(".../code")`，与 task ID 同源；本次修订后）：
`fcc714bf393c33e8b120a26608c18f2b95b249ba5003c174aeecf866d24f32b5`
（初版为 `81a20d193d5d34fb615521b2997e9d2419a96fa500646a4db1ba852c9873f847`）

### 2.1 模型规模（与 formulation_v001 §3.8 一致）

- 变量 720（`b,c,q,s,E` 各 144；`E` 下标 `t` 表示第 `t` 时段末状态，末时段固定 6000）；
  等式约束 288（144 平衡 + 144 动态）；变量界 720；非零元 1151。
- 目标 `Σ p_t·b_t`；**全文无 `p_t·b_t·Δt`**。

---

## 3. 运行环境与求解器

- 求解器：`scipy.optimize.linprog(method="highs")`，`presolve=True`，`time_limit=60 s`（默认，可由 CLI 覆盖）。
- **CPU 求解，不使用 GPU**（`device=cpu`、`gpu_required=false`）；因此不占用单卡 GPU 的串行额度。
  若后续小问引入 GPU 路径，必须单卡串行。
- 确定性 LP，无随机性：`seed=null`，代码不读取任何随机源；同一输入/同一版本必须复现同一目标值。
- 解释器：项目 venv（`.venv/Scripts/python.exe`，Python 3.14.4；numpy 2.5.2、scipy、pandas、openpyxl 已装）。
  已实测相对路径可解析（父进程为 `pip/Scripts/python.exe` 时仍解析到项目 venv）。

---

## 4. I/O 契约

### 4.1 输入（只读）

- `data/附件1.xlsx`：第 1 工作表 145 行（1 表头 + 144 数据）× 4 列，
  表头 `时间 / 电价 / 小区负载 / 光伏发电预测功率`；md5 `dbe06f92517431228efcc26e3e796ef9`（与 AS02 登记一致，本动作独立复核）。
  时间列前 143 行为 `datetime.time`（`0:10`…`23:50`），末行为字符串 `0:00+1`。
- `data/附件5/result1.xlsx`（模板）：md5 `74adc298ba5e1825482464a4ea4e26ec`。
  - `计划购电量`：A1:B145，`A2:A145` 为 `0:10-0:20` … `0:00+1-0:10+1`（144 行，含末行、无 `0:00-0:10`）。
  - `充放电量`：A1:E7，`A2:A7` 为 6 个 4 小时块；`D2='0:00'`、`D3='24:00'`，
    储电量写在 `E2`（0:00）与 `E3`（24:00）。
- `input_path` 取 `data/`（整目录参与 `input_hash`），因此附件 2/3/4 或模板变化会使 task ID 改变。

### 4.2 输出（正式模式，写入 `output_directory`）

| 文件 | 内容 |
|---|---|
| `result1.xlsx` | 按模板填写：`计划购电量` 144 行；`充放电量` 6 块 + 0:00/24:00 储电量 |
| `solver_status.json` | `status/message/iterations/solver/device/gpu_required/seed/mip_gap`、`feasible_incumbent=true`、等式与界残差 |
| `solution.json` | 目标值、总量、储能区间、恒等式 (I1)/(I2) 残差、逐条 `checks`、144 时段 9 列序列 |
| `tables.json` | 表 1（六个时段 + 全天购电量/购电费）、表 2（六块充放电量 + 0:00/24:00 储电量） |
| `run_manifest.json` | 版本/参数/输入 md5/模板/代码 sha256/环境/`task_id`/`checks_failed`/`outcome` |

探针模式（`--periods < 144`）**不写** `result1.xlsx`，改写 `probe_result1.xlsx`，并在 manifest 标 `probe_mode=true`，
以保证交付文件不会被部分时段的试算污染。

---

## 5. 硬约束与失败条件

`solution.json` 中逐条检查（阈值 1e-6），全部为硬检查：等式残差、变量界越界、`E_144=E_0=6000`、
`1200 ≤ E ≤ 10800`、`c ≤ 833.3333`、`q_dis ≤ 750.0000`、`0 ≤ s ≤ PV·Δt`、`b ≥ 0`、
互补性残差 `Σ c·q`、(I1) `Σq = 0.81Σc`、(I2) `Σb = N + Σs + 0.19Σc`、
两侧换算功率（`c/Δt`、`η c/Δt`、`q/Δt`、`q/(ηΔt)`）均 `≤ 5000 kW`；
正式模式另加解析界 `[min(p)·N, 无储能可行解]` 与量级自检（费用须为 10⁴ 元，防 D9 的 Δt 误乘）。

退出码：`0` 成功；`2` solver 非最优（写 `solver_status.json`，`feasible_incumbent=false`）；
`3` 输入/模板结构不符；`4` 硬检查或模板标签校验失败；其余未捕获异常按 `code_runtime`。

---

## 6. 静态检查与小型探针（初版动作 `act-0f8555fda45b4e1f` 实测）

> 本节保留初版动作的历史记录；重做动作 `act-fd5e1868958f4329` 的复核结果见 §10（初版的 12/24 时段探针
> 未覆盖表 1 的 144 时段标签分支，故未暴露 §10 修复的缺陷）。

证据目录：`runtime/actions/act-0f8555fda45b4e1f/evidence/`

1. `compileall`：通过（exit 0）。`ruff check code/`：**All checks passed**（exit 0；line-length 120、E/F/I）。
2. `run_prob01.py --help`：exit 0（`cli_help.txt`）。
3. 探针 1（`--periods 12`，`probe_run_p12/`）：exit 0，`C*=2970.1604` 元、`Σb=6928.8918 kWh`、`checks_failed=[]`；
   `probe_result1.xlsx` 填 12 行、下一行留空、未写 0:00/24:00 端点。
4. 探针 2（`--periods 24`，`probe_run_p24/`）：exit 0，`status=0 (Optimal)`、`iterations=57`、`C*=6041.4748` 元、
   等式残差 0.0、界越界 0.0、`checks_failed=[]`；`probe_result1.xlsx` 填 24 行、首块充/放电量写入。
   该截断窗内最优解**未使用储能**（首块充/放电量均为 0），属截断窗与周期约束共同作用的结果，
   **不能**据此推断 144 时段解的结构。
5. task 规格预演（`static_checks.py` 调用真实 `automm.tasks.make_task_spec`，**不创建 task**）：
   - `task_id = b87194aa7fada61ee0d8`；`backend = local`；`timeout_seconds = 300`；`preflight = {compileall: passed, ruff: unavailable}`
     （`make_task_spec` 用 `shutil.which("ruff")` 探测 PATH，项目 venv 的 ruff 不在 PATH，故记 `unavailable`；
     第 1 项的显式 ruff 检查已通过，二者不矛盾）。
   - `code_hash = 81a20d193d5d34fb615521b2997e9d2419a96fa500646a4db1ba852c9873f847`
   - `input_hash = 4343d799b5830093d7a61d566219e1d2592f5bc39c8b7a9297286fa9e02d9434`
   - `config_hash = 30393b527f5fd4e4c38f9adc20f1380199b89979a9f2576e204d5e7668c43d3d`
   - `source_config_hash = a90d2b9d593e95d8528a36dfe7c9b911c618f2cc0e9ec2f96c98dfc38e051c2d`
   - `output_directory` 位于 `assumption_v003/` 内（`make_task_spec` 的目录约束通过）。
6. 矩阵规模复核（`matrix_shape.json`，直接调用 `prob01_model.build_lp` 于 144 时段真实数据）：
   变量 720、等式行 288、变量界 720、`A_eq` 非零元 1151、目标非零元 144，与 formulation_v001 §3.8 逐项一致。
7. 所有探针 JSON 通过 `allow_nan=False` 落盘，且 `NaN/Infinity` 关键字扫描为空。

> 说明：`make_task_spec` 的 dry-run 只构造 spec，不调用 `submit_task`；implementation 阶段未创建任何 task、未写 `results/`。

---

## 7. 交给 computation 阶段的 task 规格

见 `code/task_spec.yaml`（本文件为规格，不由 implementation 执行）。核心命令：

```text
.venv/Scripts/python.exe \
  problems/microgrid_2025/prob01/versions/assumption_v003/code/run_prob01.py \
  --data data/附件1.xlsx \
  --template data/附件5/result1.xlsx \
  --output problems/microgrid_2025/prob01/versions/assumption_v003/results/prob01_v003_f001_run002 \
  --periods 144 --time-limit 60
```

- `output_directory`：`problems/microgrid_2025/prob01/versions/assumption_v003/results/prob01_v003_f001_run002`
  （**已由 `..._run001` 改为 `..._run002`**：attempt-001 / task `b87194aa7fada61ee0d8` 以
  `failure_type=interrupted` 结束，按 `agents/resource-manager.md`「重试必须创建新 attempt 和新
  output_directory，不能覆盖旧结果」执行；`run001` 目录为空，保留不覆盖）
- `worker_launch_mode`：`supervised`（`config/compute.yaml`，Runner 原地运行 worker）。`detached` 在本
  DSH 沙箱环境会被进程树回收（初版两次心跳探针：`worker_lifetime_heartbeat.txt` 至 beat 04、
  `detach_heartbeat.txt` 3 拍即止），故必须 supervised。
- `input_path`：`data`；`config_path`：`code/task_config.yaml`；`code_path`：`code`
- `--output` 必须与 `output_directory` 完全一致（`make_task_spec` 强校验，dry-run 已通过）
- 资源：CPU、<1 s 求解、内存 <50 MB、超时 300 s；`seed=null`；**不占 GPU**
- 重跑必须使用新的 `output_directory`（`run003`…），不得覆盖既有结果
- 本次 dry-run：`task_id = 1300a936c4d95653f9d1`、`code_hash = fcc714bf…`、`config_hash = 331a6ba8…`、
  `input_hash = 4343d799…`（`runtime/actions/act-fd5e1868958f4329/evidence/task_spec_dryrun.json`）

---

## 8. 下游要求（sanity / visualization / robustness）

1. **不比对逐点解唯一性**：LP 最优面可能不唯一（formulation 探针记录 SOC 上下界两端均活跃），
   sanity 以「约束残差 + (I1)/(I2) + 目标值 + 表 1/表 2」为准。
2. sanity 必须**两次换算功率**核对两侧 `≤ 5000 kW`（E1 要求），并独立复核 `q_dis_t ≤ 750.00`。
3. `result1.xlsx` 的 0:00/24:00 是**计划窗首/末状态**（AS01 左端点口径，模板相位前移 10 分钟），
   论文与图注须显式说明一次，不得与严格时钟口径混用。
4. 禁止复用 v001 的 `p_t·b_t·Δt` 口径；禁止把 5000 kW 直接当电量上限（漏乘 Δt 会放大可行域 6 倍）。
5. prob02–prob04 沿用 `q_dis ≤ 750.00`（E1），跨日/日期范围（A2）与降尺度（A6）须另行裁定后建模。

---

## 9. 遗留风险与已知限制

- 截断窗探针不能替代正式计算：`--periods < 144` 时解析界、量级检查与表 1 六个时段均被跳过。
- `make_task_spec` 的 ruff 预检依赖 PATH；若提交环境的 PATH 中没有 ruff，则只做 `compileall`
  （本动作已用 venv 内 ruff 显式检查通过，风险已知且不阻塞）。
- `run_manifest.json` 的 `code_sha256` 由脚本自算（按 `*.py` 文件），与 harness 的 `code_hash`
  （含 `task_config.yaml`/`task_spec.yaml`）算法不同，两者用途不同，论文/追踪以 harness 值为准。

---

## 10. 重做动作 `act-fd5e1868958f4329`：复核、缺陷修复与 task spec 修订

- 触发：团队要求「`assumption_v003` 与 `formulation_v001` 已 accepted 且不再改动，自 implementation 重新走」；
  `config/compute.yaml` 改为 `worker_launch_mode=supervised`（修复 detached worker 被沙箱进程树回收导致的
  `interrupted`）。
- 采用的 accepted 口径（与 §1 一致，逐项复核）：AS01 左端点对齐；AS03a `min Σ p_t·b_t`（不带 Δt）；
  AS05 两侧 0.9；AS06 + D10 + **勘误 E1** `c ≤ 833.3333`、`q_dis ≤ 750.0000`；AS08 + **勘误 E3**
  变量保留、允许取 0；AS10/AS11 `E_0 = E_144 = 6000`；AS13 表 1 行位置 60/72/84/96/108/120、
  表 2 每 24 行一块且不冲抵。**本动作不新增、不更改任何建模口径**。

### 10.1 修复的缺陷（只在 144 时段触发）

初版 `run_prob01.py` 的 `build_tables` 用「附件 1 时间戳」（如 `10:00`）去比对「result1 模板区间标签」
（如 `10:00-10:10`），`label_matches` 恒为 False；`main` 的 `if not all(label_checks)` 因此在
**144 时段（6 个时段全在窗口内）必然触发**，程序在求解后以 exit 4 终止且**不写 `result1.xlsx` 等任何产物**。
12/24 时段探针因 `position > periods` 不进入该分支，故初版静态检查未暴露此缺陷。

修复内容：
- `build_tables` 新增 `template_info` 入参，`label_matches` 同时校验
  「附件时间戳 == 区间左端点」与「模板行标签 == 完整区间」；
- `main` 的失败分支打印具体不匹配项后返回 exit 4；
- `tables.json` 的表 1 行新增 `template_label` 字段（附加字段，不改变既有键语义）。

### 10.2 本动作实测（**未运行 144 时段完整计算**）

证据目录：`runtime/actions/act-fd5e1868958f4329/evidence/`

1. `compileall`（exit 0）、`ruff check code/`（All checks passed）、`run_prob01.py --help`（exit 0）；
   静态检查脚本 `static_checks.py`、探针汇总 `probe_summary.py` 本身也通过 ruff。
2. 小型探针（`probe_run_p12/`、`probe_run_p24/`）：均 exit 0、`checks_failed=[]`；
   `C*(12) = 2970.1604 元`、`C*(24) = 6041.4748 元`（与初版逐位一致，说明本次修复未改变求解路径）；
   两者只写 `probe_result1.xlsx`，**未写 `result1.xlsx`**（`probe_summary.json` 断言通过）。
3. `static_checks_result.json`（33 项断言，`passed=true`、`failures=[]`）：
   - 常量口径：`Δt=1/6`、`η_ch=η_dis=0.9`、`E_init=6000`、`E∈[1200,10800]`、`C_CAP=833.3333`、`Q_CAP=750.0`；
   - 输入/模板：附件 1 md5 `dbe06f92…`、144 行、首/末时间戳 `00:10`/`0:00+1`；模板 144 行、首/末标签
     `0:10-0:20`/`0:00+1-0:10+1`、6 个 4 小时块、0:00/24:00 端点；
   - 表 1 的 6 个位置（60/72/84/96/108/120）**同时**通过「附件时间戳=左端点」与「模板标签=完整区间」；
   - **不求解**的 144 时段 `build_tables` 路径（6 个 slot 全部 `label_matches=true`）与模板填报路径
     （144 行 + 6 块 + 0:00/24:00 端点）均通过；
   - 矩阵规模：变量 720、等式 288、界 720、`A_eq` 非零元 1151、目标非零元 144（与 formulation_v001 §3.8 一致）；
   - 全日电量：负载 111024.81 kWh、光伏 55482.84 kWh、净负荷 55541.97 kWh（与 assumptions §6 一致）；
   - `full_horizon=True` 的 `evaluate` 分支喂入解析可行解（无储能）得 `C = 48052.0466 元`、
     `checks_failed=[]`、`(I1) = 0.0`、`(I2) = 7.3e-12`、等式残差 0.0（与 formulation §3.9(b) 一致）。
4. `make_task_spec` dry-run（`task_spec_dryrun.py`，**未创建 task、未调用 `submit_task`**）：
   新 `task_id = 1300a936c4d95653f9d1`、`code_hash = fcc714bf…`、`config_hash = 331a6ba8…`
   （`compute.yaml` 的 supervised 改动生效）、`input_hash = 4343d799…`；`output_directory` 位于
   assumption_v003 版本目录内且与 `--output` 完全一致。

### 10.3 task spec / task 配置修订

- `code/task_spec.yaml`：`output_directory` 与 `--output` 改为 `..._run002`；新增
  `worker_launch_mode: supervised` 与修订记录（缺陷修复、attempt-001 interrupted、`config_hash` 变化
  导致新 `task_id`）。
- `code/task_config.yaml`：求解参数不变，仅在 `compute.resource_notes` 补注 supervised 口径与生成者信息。
- 旧 task `b87194aa7fada61ee0d8`（attempt-001）状态与 `results/..._run001` 原样保留，不覆盖。

### 10.4 仍未决 / 未越界事项

- A2/A6/A7/A8/A9 均属 prob02–prob04，本动作不裁定；prob01 只处理单日周期口径。
- AS06「5000 kW 作用侧」为 `team_decision`（D10），本实现不声称文献支撑。
- 本动作未创建任何 task、未写 `results/`；正式结果由 computation 阶段的隔离 task + supervised worker 产出。
