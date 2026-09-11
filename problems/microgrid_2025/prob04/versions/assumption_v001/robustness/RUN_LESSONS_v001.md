# prob04 robustness 探针阶段问题台账与正式跑规避清单（v001）

- 归属：`microgrid_2025` / `prob04` / `robustness`（`assumption_v001` / `formulation_v001`）
- 记录时间：2026-09-11 22:0x（记录人：人工复核，VS Code 会话）
- 关联动作：`act-6d9ecf00777a4b96`（负责人：robustness-analyst）
- **性质与边界**：本文是**运行期问题台账**。`plan.md` 按自身第 14 行冻结声明「跑数前冻结、事后不得修改」，故本文**不修改** `plan.md`、
  不修改任何假设/公式/结果/日志/结论历史，也不回写 prob02/prob03 任何产物。仅记录探针阶段实测到的问题与正式跑的规避措施。
- 证据指针（全部只读）：
  - `runtime/actions/act-6d9ecf00777a4b96/evidence/probe_smoke3_42|_43`（3 天 smoke）
  - `.../probe_all34_42|_43`（34 天全矩阵探针，含 `baseline_check.json` / `summary.json` / `sensitivity.json`）
  - `.../probe_baseline365_42|_43`（365 天基线闸门探针）
  - `runtime/tasks/953eeb1e0b004171cad9`（4-2 正式跑 task）、`runtime/tasks/5713b0a24eedeac9f000`（4-3 正式跑 task）

---

## 1. 探针阶段实测的三项问题

| # | 现象（探针产物） | 根因 | 是否模型/实现错误 | 处置 |
|---|---|---|---|---|
| **P-1** | `probe_all34_*` 的 `baseline_check_passed = false`；4-3 全量指标 `relative_diff` 落在 0.88–0.99 | **时域口径错配**：34 天探针的总量与 **334 天交付期 / 365 天全期** 的 `run002` 参考直接对比，未做天数归一化 | **否**（模型无错） | 不重算。已由 `probe_baseline365_42|_43` 证伪：365 天口径下 `base_ok = True`、**全部指标 `relative_diff = 0.0`**（逐位复现），墙钟 20.5 s / 63.7 s |
| **P-2** | `probe_all34_43` 有 3 个样本 `ok = false`（`solved 80/83`）：`buy_cap_4500kW` / `buy_cap_4000kW` / `buy_cap_3500kW`，`type = solver_not_optimal`（HiGHS `status = 2`） | **预期不可行**：决策层购电上限低于 4-3 的可行分界 ⇒ LP 无可行解 | **否**（是结论） | 不重算。S6 判据已正确登记 `buy_cap_infeasible = [3500, 4000, 4500]`、分界 `bracket_kw = [4500, 5000]`，且 **S6 = PASS**；`plan.md` §4.9 明文此为预期结果、不计入 S1 受判子集 |
| **P-3** | `failed_criteria = ["S2", "S4"]`，`stability_grade = 脆弱` | **S2**：`noise_white_10_001/002` 的 `Σq_em` 越出基准 `[0.5×, 2×] = [9,590.2, 38,360.8] kWh` 带（实测最大 **52,398.3 kWh**）<br>**S4**：`noise_*:n<25` —— 探针命令为 `--samples 2`，每族仅 2 个样本，而 S4 冻结要求 **n ≥ 25/族** | **否**（S2 为统计发现；S4 为采样量不足） | **S2**：补机制解释即可（`plan.md` §3 S2 处置为「越界须给机制解释」，未要求重跑）<br>**S4**：**必须用正式全量跑覆盖**（`--samples 25`），非纠错 |

> 结论：**P-1、P-2、P-3(S2) 均无需重算**（证据已闭合）；**只有 P-3(S4) 需要正式全量跑**，而该跑本就是 `plan.md` §4.7/§4.8 预注册的交付动作。

---

## 2. 正式跑的规避措施（已在冻结 task 规格中生效，已逐项核对）

| 问题 | 正式跑的规避 | 核对证据 |
|---|---|---|
| P-1 时域错配 | 正式跑 `--days 365`（全期），基线闸门在**同一时域**与 `run002` 对账 ⇒ 19 项总量相对差 ≤ `1e-6` | task `953eeb1e0b004171cad9` / `5713b0a24eedeac9f000` 的 `--days 365` |
| P-2 buy_cap 不可行 | 保留全部 12 档（含 3500/4000/4500 kW），按 `plan.md` §4.9 记为 `infeasible` 状态、不计入 S1 受判子集、不静默删除 | `--families all`（含 structural 族） |
| P-3(S4) 采样不足 | `--samples 25` ⇒ 4-2 噪声 4 族 × 25 = 100、4-3 噪声 5 族 × 25 = 125，满足 S4 的 `n ≥ 25/族` 与 plan 的「随机实验 ≥ 100 次」 | `--samples 25` |
| 预算不确定性 | 4-2 `timeout 5400` / `--max-wall-seconds 3000`；4-3 `timeout 12600` / `--max-wall-seconds 10800`（≥ 2× 余量） | task 规格 |
| 两链混淆 | 4-2 与 4-3 **分别提交、分别传参、独立 output_directory**（`..._robust_4-2_run001` / `..._robust_4-3_run001`） | task 规格 `output_directory` |
| 单价过高致单层超时 | `--time-limit 60`（单层 LP 时限） | task 规格 |

**正式跑实测标定（来自 P-1 的 365 天探针）**：单情景 compact 全年 4-2 = 6.26 s、4-3 = 22.11 s；整批预期 4-2 ≈ 1,100–1,300 s、4-3 ≈ 4,400–5,000 s；**两 task 串行（`max_local_concurrent_tasks = 1`）合计 ≈ 5,500–6,300 s（约 90–105 min）**。

---

## 2b. 正式跑实际执行记录（2026-09-11 晚，实测追加）

| 链 | task_id | 启动 | 结果 | 用时 | 备注 |
|---|---|---|---|---|---|
| **4-2** | `953eeb1e0b004171cad9` | 22:09:30 | ✅ **succeeded**（rc=0，`probe_mode=false`） | **966.9 s** | `scenario_count=162 / solved=162 / failed=0`；`baseline_check.passed=true`、`worst_relative_diff=0.0`；**S1–S7 全 PASS、`failed_criteria=[]`、`stability_grade=稳定`**；输出 `results/prob04_v001_robust_4-2_run001/`（9 件产物 + 7 图 + 70 条轨迹） |
| **4-3** | `5713b0a24eedeac9f000` | 22:08:09 | ⏳ **worker 仍在运行**（22:27 时 55/198） | 预计 ≈ 4,160 s | 输出 `results/prob04_v001_robust_4-3_run001/` 仍在增长 |

> **P-3(S4) 已被正式跑消解**：4-2 在 `--samples 25`（噪声 4 族 × 25 = 100）下 **S4 = PASS、`violations = []`**，
> 证明探针阶段的 `n<25` 与 std/CI 超限确实是小窗口（34 天）放大效应，不是真实不稳健。

### 新增问题 P-4（本次正式跑暴露，须规避）

- **现象**：4-3 的 worker 明明在跑（输出目录持续增长、22:27 已 55/198），但 task 登记为
  `status=failed`、`failure_class=infrastructure_transient`、`failure_type=interrupted`、
  `message="worker PID 不存在且未写入终态"`。
- **根因（pid 复用导致 liveness 假阴性）**：`status.json` 记录的 `pid=37212` 与真实 worker 进程不一致；
  复查时该 pid 已被另一个进程（`scripts/harness.py next-action --json`）复用 ⇒ 存活探测判「worker 不存在」⇒ 误记 `interrupted`。
  与 `compute.yaml` 已登记的「supervised worker 被回收」是**不同**机理：这次进程没死，是**判活判错**。
- **规避**：
  1. 判「worker 是否死亡」**不能只看 `status.json` 的 pid**，必须同时看**输出目录 mtime / `raw_samples.jsonl` 行数是否在增长**；
  2. 本机同时跑多个 `.venv\Scripts\python.exe` 时 pid 复用概率高，任何「PID 不存在」结论都要用
     `Get-CimInstance Win32_Process` 核对**完整命令行**，而不是只比对 pid；
  3. **不要因这条假 failed 就立即补提 `..._run002`** —— 会在同一 `max_local_concurrent_tasks = 1` 的单 worker 上
     叠一个重复的 ~70 min 跑，并可能污染 `run001` 目录。先确认 worker 是否真的死了。

## 3. 仍未消解的风险（必须进入 `report.md` 的分析与披露项）

1. ~~**S4 的 `std_relative > 5%` 可能不会被重跑修好**~~ → **已被 4-2 正式跑消解**（§2b）：`--samples 25` 下 4-2 的
   **S4 = PASS、`violations = []`**，此前 5.55% / 7.09% 的超限确认为 34 天小窗口放大效应。
   **仍待验证的是 4-3**：4-3 的噪声族为 5 族 × 25 = 125，且多一族 `noise_pvfc_5`（光伏预报噪声），
   正式跑完成后须核对 `summary.json` 的 `criteria.S4.detail.violations` 是否为空；若非空，
   按 `plan.md` §3 如实登记「该族不稳健」并缩小适用范围，**不得**再重跑凑过、不得删除不利样本（`T7-4` 纪律）。
2. **S2 越界须给机制归因**：`noise_white_10` 下 `Σq_em` 放大到基准的 2.73×，需按 `plan.md` §1.9（`AS16`）说明其为
   「决策层光伏预报 vs 结算层实际」缺口驱动，属统计归因，不作模型失败。
3. **阶段完成门禁依赖 `baseline_check_passed`**：`plan.md` §4.9 规定 compact 基线与 `run002` 的总量相对差 > `1e-6` 则整批 `exit 4`；
   正式跑务必核对 `baseline_check.json` 的 19 项总量 + 表 1 四日期六时段 + 7 个 T7 审计键，而非只看顶层布尔值。
