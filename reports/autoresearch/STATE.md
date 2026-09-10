# AutoMM STATE

> 本文件由 `runtime/workflow_state.json` 渲染，请勿以手工修改本文件的方式驱动状态。

## 基本状态

- 更新时间：2026-09-10T14:20:39.146936+00:00
- 控制状态：paused
- 活动题目：microgrid_2025
- 当前小问：prob01
- 当前阶段：locally_completed

## 任务

failed=1 | succeeded=3

## 最近动作

控制命令 PAUSE，来源 cli

## 警告

- A1（高优先，待裁定）：附件 1/2/4 的 144 个时间戳为 0:10…0:00+1，而 result 模板的 144 个时间段列为 0:10-0:20…0:00+1-0:10+1，存在 10 分钟错位；按位置一一对应等价于『时间戳=区间左端点（数据覆盖 0:10→24:10）』，按『时间戳=区间右端点』则整体错位一格。该约定直接决定表 1 中 10:00-10:10 等取哪一格。
- A2（高优先，待裁定）：结果日期范围为 2025-02-01～12-31（334 天）而数据覆盖全年 365 天，且附录 1 只给 2025-01-01 0:00 的 6000 kWh；需裁定每日日初储电量取法（每日独立取 6000 kWh 且日初=日末，还是从 1 月 1 日滚动递推、1 月作为预热期）。
- A3（待裁定）：90% 充放电效率在状态转移中的作用位置（充电侧/放电侧/两侧/往返），影响 SOC 轨迹与费用。
- A5（待裁定）：『微网提供的电能』口径（购电+光伏+放电 ≥ 负载，还是净供给 ≥ 负载）以及紧急购电能否用于储能充电。
- A6（高优先，待裁定）：附件 3 整点预报到 10 分钟粒度的降尺度规则；2025-12-31 18:00 预报指向 2026-01-01，超出附件 2/4 数据范围，年末边界需明确处理。
- A7（高优先，待裁定）：问题 3 计划/调整的比较基准（与当天 0:00 计划比还是与上一次调整比）、一天内多次调整的结算顺序、0.5× 违约的电费方向（罚金/退款/费用项）、调整是替代量还是增量、调整是否只作用于发布时刻之后的时段。
- A8（高优先，待裁定）：问题 4 中实时波动电价的可观测性——0:00 制定计划时是否已知全天电价（完全信息）、只能依赖价格预测、还是实时滚动观测；三种解读对应不同的模型与结果。
- A9（待裁定）：问题 3『是否引入其他时刻预报』需先固定评价指标与对照方案集合，该分析可能需要在可选阶段 ablation 执行并写明理由。
- A10/A11/A12（待裁定）：表 2 的 4 小时时段充放电量口径（是否冲抵）、『全天购电费』是否含紧急/调整费用、功率(kW)→电量(kWh) 的 Δt=1/6 h 换算与预报整点功率的积分口径。
- A13/A14（待裁定）：是否引入弃光/盈余变量 q_spill；外网购电是否存在未给出的功率上限。
- A15（待裁定）：问题 1 的 0:00 储电量是否取 6000 kWh（等价于把该日视作 2025-01-01）。
- 本阶段未固定任何关键数学假设；上述 A1–A16 需由 literature_review / assumption_definition / mathematical_formulation 逐项裁定并版本化。截至本动作，不存在人工阻塞条件。
- 21/25 条仅有 Crossref 元数据+标题级证据（verification_level=metadata），4 条取得开放摘要（abstract_oa，ref-alguhi-2025-bess-operation、ref-shen-2026-peak-valley、ref-huang-2022-dynamic-efficiency、ref-arima-2024-rte-profile）；本次未逐篇阅读正文，任何公式级或定量级引用须在 mathematical_formulation 阶段另行获取全文后使用。
- 文献池达 config/research.yaml 的 max_items_per_question=25 上限；一条检索命中的锌空液流电池论文（10.1016/j.est.2022.105786）因主题无关被剔除，但未能在池内登记为 rejected 记录。
- 附录 1 的 90% 充放电效率为附录 1 给定的题面硬参数，无文献标定；文献仅说明效率通常非常数、常效率属工程简化，效率扰动应留待 robustness。
- A1/A2 属题面与数据约定，文献不能替代裁定；若 assumption_definition 判定存在互斥且无法在题面内闭合的建模目标，再按 config/gates.yaml 的 human_model_choice 上报。
- 25 条文献中 21 条仅 Crossref 元数据级、4 条开放摘要，未逐篇阅读正文；本阶段引用只支撑框架级主张，任何公式级/定量级引用须在 mathematical_formulation 取得全文后使用。
- A2（结果日期 2025-02-01～12-31 与储能跨日衔接）本问未裁定；prob01 的 E_0=6000 kWh 周期口径是 prob02 跨日/每日重置裁定的锚点，建议 prob02 启动前单独裁定并登记新版本。
- A6（附件 3 降尺度与年末边界）、A7（问题 3 结算口径）、A8（问题 4 电价可观测性）、A9（附加预报时刻分析）属后续小问，本问仅登记不裁定。
- result1 模板的 144 个时段标签整体为 0:10→24:10；在 AS01 左端点口径下计划窗恰为 24h 但相对自然日相位前移 10 分钟，已在 AS01/AS13 与 D1/D8 中显式记录，属模板固有相位而非数据错误。
- 附录 1 的 90% 充放电效率为题面硬参数，无文献标定；文献仅说明常效率是工程简化，效率扰动留待 robustness。
- AS03（不计折旧）、AS07（不显式强制同时充放电）、AS14（无自放电）、AS15（无购电上限/无售电）均为显式声明的简化，偏差方向已逐条给出，须由 robustness 量化。
- D9 口径修正后，v001 中一切含 p_t·b_t·Δt 的费用公式（AS03、AS13、§5.2 模型骨架、D7 备选 A）对下游失效，不得复用；新口径下全天费用应在约 [20623, 48052] 元（量级 10^4），若实现结果落在 10^3 元即说明误乘了 Δt。
- AS01 的左端点口径使计划窗为 0:10→24:10，相对自然日整体前移 10 分钟（result1 模板固有相位）；表 2 按模板行位置聚合，需在论文中显式说明一次。
- A2（结果日期 2025-02-01～12-31 与储能跨日衔接）本问未裁定，prob01 的 E_0=E_144=6000 kWh 周期口径是其锚点，建议 prob02 启动前单独裁定并登记新版本。
- A6（附件 3 降尺度与年末边界）、A7（问题 3 结算口径）、A8（问题 4 电价可观测性）、A9（附加预报时刻分析）属 prob03/04，本问仅登记不裁定。
- 文献池 25 条均未逐篇阅读正文（21 条仅 Crossref 元数据级、4 条开放摘要）；本版本引用只支撑框架级主张，任何公式级/定量级引用须在 mathematical_formulation 取得全文后使用。
- AS03b（不计折旧）、AS05（常效率 90%）、AS07（不显式强制同时充放电）、AS14（无自放电）、AS15（无购电上限/无售电）、AS16（单日确定性）均为显式声明的简化，偏差方向已逐条给出，须由 robustness 量化。
- 本动作（act-9f35e01ebbdd4a03）为被中断动作 act-2041a266de4043f9 的续作：后者留下同口径探针但未落盘 assumptions.md/version.yaml，本动作已重新独立执行探针并完成 v002 全部内容。
- AS03a 的 evidence_type 为 team_decision 且 key: true，其文献绑定只支撑『购电费最小可线性建模』的形式，不支撑口径选择本身；门禁按已验证来源通过，但不代表文献支持该口径。
- 团队 D10 的多日风险数字（38/365、10.4%）经本动作复核为 249/365、68.2%（根因是 .tmp/probe_b1_365days.py 取价 bug）；prob02–prob04 的口径影响预估必须按更正后的量级重算，不得沿用「约一成工作日」的说法。
- v002 的 AS06 精确陈述与 §5.2 骨架中 0 ≤ q_dis_t ≤ 5000·Δt（放电上限 833.33 kWh）的写法对下游失效，不得复用；新口径为 c_t ≤ 833.33、q_dis_t ≤ 750.00。
- AS06 的「5000 kW 作用侧」属 team_decision（D10），文献池无一条涉及该约定（最贴合的 ref-vykhodtsev-2022-bess-review 为 closed access）；论文若需文献支撑，须在 mathematical_formulation 前补定向检索或取得全文，不得包装为文献支持。
- D10 的取交集会收紧 prob02–prob04 的放电上限，费用上升（附件 2 365 天累计约 6,916.19 元）；该增量需在 prob02 用其实际负载/光伏重算并作为 robustness 情景登记。
- A2（prob02 起的结果日期 2025-02-01～12-31 与储能跨日衔接）本问未裁定，prob01 的 E_0=E_144=6000 kWh 周期口径是其锚点，建议 prob02 启动前单独裁定并登记新版本。
- AS03a 的 evidence_type 为 team_decision 且 key: true；新绑定的 ref-baloyi-2021-tou-arbitrage 只支撑「TOU 套利动机」这一机制级主张，不支撑口径选择本身，门禁通过不代表文献支持该口径。
- AS03b（不计折旧）、AS05（常效率 90%）、AS07（不显式强制同时充放电）、AS14（无自放电）、AS15（无购电上限/无售电）、AS16（单日确定性）与 AS06/D10（功率作用侧取交集）均为显式声明的简化或口径选择，偏差方向已逐条给出，须由 robustness 量化。
- C1（口径冲突）：problems/microgrid_2025/global_symbols.yaml 把 q_dis 域写作 P_dis_max·Δ_t = 833.33 kWh，与团队裁定 D10/AS06 的 750.00 kWh 冲突。本 formulation 按团队裁定（效力最高）取 750.00，符号含义不变；建议 cross_question_review 阶段或 problem-decomposer 更新符号表 domain/notes，并在 prob02–prob04 沿用 750.00。
- C2（登记口径）：global_symbols.yaml 登记 q_spill 的 first_question = prob02 且注明『尚未固定是否引入』，但 AS08/D4 已裁定 prob01 引入 s_t。本 formulation 在 prob01 使用 s_t（含义一致）；首次出现小问的登记需更正。
- C3（措辞不一致）：assumption_v003/version.yaml 中 AS08 的 statement 保留『该变量在部分时段必然被激活』，与 assumptions.md §2/§6 及探针实测 Σs_t = 0 不符。按『变量保留、最优解允许取 0』执行，不影响模型与结果，建议在下一版假设或团队勘误中修正措辞。
- AS06 的『5000 kW 作用侧』为 team_decision（D10），现有 25 条文献池无一条涉及该约定；本 formulation 只对约束集形式引用文献，未把口径选择包装为文献支持。论文若需文献依据，须补定向检索或取得 ref-vykhodtsev-2022-bess-review 全文。
- AS01 左端点口径使计划窗为 0:10→24:10，相对自然日整体前移 10 分钟（result1 模板固有相位）；表 2 的 0:00/24:00 报『计划窗首/末状态』。论文须显式说明一次，不得与严格时钟口径混用。
- LP 最优解可能不唯一（探针中 SOC 上下界两端均活跃：E ∈ [1200.0000, 10800.0000]）。实现阶段须固定并记录求解器与容差；sanity 以约束残差 + 恒等式 (I1)/(I2) + 目标值为准，不比对逐点解的唯一性。
- 候选 C（价格分位启发式）regret = 25.87%，不得作为交付口径；仅在求解器不可用时作为降级路径或对照基线。
- A2（结果日期 2025-02-01～12-31 与储能跨日衔接）、A6（附件 3 降尺度与年末边界）、A7（prob03 结算口径）、A8（prob04 电价可观测性）、A9（附加预报时刻分析）本问均未裁定，prob02 启动前需单独裁定并登记新版本；本 formulation 未越界裁定。
- make_task_spec 的预检在 PATH 中找不到 ruff（记 preflight.ruff=unavailable），因此其内部只做了 compileall；本动作已用项目 venv 的 ruff 显式检查 code/ 并通过，两者不矛盾。若提交环境仍无 ruff，preflight 只覆盖 compileall。
- 截断窗探针（12/24 时段）跳过解析界、量级自检与表 1 六个时段检查，不能替代正式计算；论文与 sanity 只能引用 --periods 144 的结果。
- LP 最优面可能不唯一（formulation 探针记录 SOC 上下界两端均活跃）：sanity 必须比对约束残差 + (I1)/(I2) + 目标值 + 表 1/表 2，不得以逐点解唯一性作为判定条件。
- AS06 的『5000 kW 施加在并网点侧与电池侧、取更严者』是 team_decision（D10），现有文献池无一条涉及该口径，论文不得包装为文献支持。
- 表 2 的 0:00/24:00 是『计划窗首/末状态』（AS01 左端点口径使计划窗为 0:10→24:10，模板固有相位）；论文与图注须显式说明一次，不得与严格时钟口径混用。
- run_manifest.json 中 code_sha256 为脚本自算（仅 *.py，逐文件 + 目录摘要），与 harness code_hash（含 task_config.yaml/task_spec.yaml 等全部 code/ 文件）算法不同；追踪与 task ID 以 harness 值为准。
- 下游 prob02–prob04 必须沿用团队勘误 E1 的放电上限 750.00 kWh；A2（结果日期 2025-02-01～12-31 与跨日衔接）、A6（附件 3 降尺度与年末边界）、A7、A8、A9 仍未裁定，本实现未越界处理。
- 重跑正式计算必须使用新的 output_directory（如 ...run002），不得覆盖 run001 的结果目录。
- 计算 task 的启动必须与调用它的进程同生命周期：当前环境（DSH 沙箱 + 短命 shell 调用）下 detached worker 无法存活（证据 worker_lifetime_heartbeat.txt beat 04 终止、detach_heartbeat.txt 3 拍终止），task b87194aa7fada61ee0d8 因此在启动 1.4 s 后即被判 interrupted。
- 重试预算有限：interrupted 允许 attempt 2、3；若不在重试前改用 supervised 启动或在沙箱外运行 Runner，attempt 2/3 会以同一失败指纹再次失败并最终耗尽重试上限。
- failed/blocked 之外的状态才消费任务：本响应按 warning 返回，以便 Runner 消费该终态 task 并在下一次唤醒把 computation 阶段交回 resource-manager 提交强制重跑（新 attempt + 新 output_directory），避免同一 unconsumed task 被反复路由。
- 初版 12/24 时段探针无法覆盖表 1 的 144 时段标签分支，故初版 implementation 未能暴露该缺陷；sanity_check 必须以 144 时段正式结果为验收依据，不得用截断窗探针替代（截断窗还跳过解析界、量级自检与表 1 六个时段）。
- 修复后的 144 时段表 1/表 2/模板填报路径只做了**不求解**的静态探针；最终仍须由 computation 的 144 时段结果复核 exit 0、checks_failed=[]、(I1)/(I2) 残差与表 1/表 2 数值。
- attempt-001 的失败指纹是 worker interrupted（infrastructure_transient），根因是 detached worker 被沙箱进程树回收；本次已在 task_spec/task_config 记录必须 supervised，且 config_hash 变化会产生新 task_id。若本次仍以同一指纹失败，应先核查是否真的以 supervised（Runner 原地）启动，不得盲目重试。
- make_task_spec 的预检在 PATH 中找不到 ruff（记录 preflight.ruff=unavailable），其内部只做 compileall；本动作已用项目 venv 的 ruff 显式检查 code/ 与 evidence/ 并通过，两者不矛盾。
- LP 最优面可能不唯一（formulation 与既有 implementation 均记录 SOC 上下界两端可能活跃）；sanity 以约束残差 + (I1)/(I2) + 目标值 + 表 1/表 2 为准，不比对逐点解的唯一性。
- status.json 的 worker_mode 字段不可作为启动方式证据：submit_task（scripts/automm/tasks.py L276）无条件写入 worker_mode="supervised"，因此 attempt-001（实际以 detached 方式启动并被沙箱回收）也登记为 supervised。启动方式的权威来源是 config/compute.yaml 的 worker_launch_mode（经 workflow.use_supervised_worker() 读取），本动作已实测为 true。
- supervised 模式下 worker_alive() 的语义存在潜在误判：start_queued(supervised=True) 写入 pid=Runner pid 且不写 worker_create_time，而 worker_alive() 要求进程 cmdline 含 `task_worker.py --task-id <id>`。当前 run_once 单线程、同一时刻仅一个 Runner 持 orchestrator 锁，故不会误判；但若在 supervised worker 运行期间由其他进程执行 compute_dispatcher.py reconcile/list（内部调用 reconcile_tasks），在途任务可能被误标 failure_type=interrupted。建议计算进行中不要手动 reconcile。
- 本环境 orchestrator 为一次性唤醒模式（config/orchestrator.yaml run_mode=one_shot，runtime/daemon/ 下无 daemon.lock/daemon.pid），因此 task 能否执行取决于下一次外部唤醒；若长时间无唤醒，task 将保持 queued（属正常排队，不是失败），不需要、也不得由 resource-manager 自行代跑或在短命 shell 内运行 start_queued。
- 可用内存偏低（总 15.73 GB，实测可用 1.7–2.2 GB），memory_slots 因此仅为 1。本 LP 任务内存 <50 MB 无风险，但不应在本环境安排多 worker 并发（配置上限 1 与之一致）。
- make_task_spec 的预检在 PATH 中找不到 ruff（preflight.ruff=unavailable），其内部只做 compileall；本动作用项目 venv 的 ruff 对 evidence/ 显式检查并通过（All checks passed），两者不矛盾。
- 上游口径事项沿用既有裁定，不在本动作重复处理：AS06+D10+团队勘误 E1 的 q_dis ≤ 750.00 kWh（与 global_symbols.yaml 的 833.33 冲突，按团队勘误执行）、AS01 左端点相位（0:10→24:10）、D9 口径 min Σ p_t·b_t（不带 Δt，费用应落在约 [20623, 48052] 元、量级 10^4）；A2/A6/A7/A8/A9 仍未裁定且属 prob02–prob04。
- 截断窗探针（12/24 时段）跳过解析界、量级自检与表 1 六个时段，不能替代正式计算；本动作未产生任何结果数值，sanity 必须以 run002 的 144 时段产物（exit 0、checks_failed=[]、(I1)/(I2) 残差、表 1 六个时段、表 2 六块与 0:00/24:00=E_0=E_144=6000 kWh）为验收依据。
- prob01 level_1_4: L1-L4 验收 task 1300a936c4d95653f9d1 / run002：L1 产物齐备、输入 md5 未变、追踪链完整；L2 独立回代 68 项全通过（等式残差 4.547e-13、E∈[1200,10800]、c≤833.3333、q≤750.0000、两侧功率≤5000 kW、(I1)/(I2)≤4.6e-12、同充放=0）；L3 目标 min Σp_t·b_t 不带 Δt、矩阵 720/288/720/1151/144 与 formulation §3.8 一致、表 1 六时段与表 2 六块及 result1.xlsx 与序列逐项一致；L4 费用 35126.95 元落在 [20622.73,48052.05]、套利方向合理、关键假设文献门禁 passed=true。技术债：文献仅元数据/摘要级、AS06 口径无文献支撑、C1/C2/C3 登记欠账、表 2 相位说明、LP 最优面非唯一，均已登记为 warnings，无硬门禁失败。
- 文献池 25 条未逐篇读正文（21 条 Crossref 元数据级 + 4 条开放摘要），本问引用只支撑框架级/机制级主张；任何公式级或定量级引用须在取得全文后再使用。
- AS06「5000 kW 作用侧」为 team_decision（D10），现有文献池无一条涉及，论文不得包装为文献支持；若需文献依据须补定向检索或取得 ref-vykhodtsev-2022-bess-review 全文。
- 上游登记/措辞欠账 C1/E1、C2/E2、C3/E3 尚未回写 global_symbols.yaml 与 assumption_v003/version.yaml，待 cross_question_review 更正；下游已按团队勘误 E1/E2/E3 执行，不影响本问结果。
- 表 2 的「0:00-4:00」等为模板行位置聚合（计划窗 0:10→24:10，相位前移 10 分钟），论文与图注须显式说明一次，不得与严格时钟口径混用。
- LP 最优面可能不唯一（E 上下界两端均活跃）；sanity 验收以约束残差 + (I1)/(I2) + 目标值 + 表 1/表 2 为准，不比对逐点解唯一性。
- tables.json 的块和按 6 位小数舍入、result1.xlsx 写入全精度，差 <1e-6，属显示精度问题，不影响数值与交付。
- A2（结果日期 2025-02-01～12-31 与储能跨日衔接）、A6（附件3降尺度与年末边界）、A7（prob03 结算口径）、A8（prob04 电价可观测性）、A9（附加预报时刻分析）仍未裁定且属 prob02–prob04，本问未越界处理。
- prob01 level_1_4: sanity_check 阶段正式复核（act-f01ed23959c44dd4）：对 task 1300a936c4d95653f9d1 / run002 的只读复核与 act-8d27775ff3714942 逐位一致——独立回代 68 项全通过（等式残差 4.547e-13、E∈[1200,10800]、c≤833.3333、q≤750.0000、两侧功率≤5000 kW、(I1)/(I2)≤4.6e-12、同充放=0）、L1 追踪链 17 项全通过（代码 sha256 三方一致、输入 md5 未变、run001 未被复用）、关键假设文献门禁 passed=true；L3 目标 min Σp_t·b_t 不带 Δt、矩阵 720/288/720/1151/144 与 formulation §3.8 一致、表 1/表 2/result1.xlsx 与序列逐项一致；L4 费用 35126.95 元落在 [20622.73,48052.05] 元、套利方向合理。技术债见 warnings，无硬门禁失败。
- A2（结果日期 2025-02-01～12-31 与储能跨日衔接）、A6（附件 3 降尺度与年末边界）、A7（prob03 结算口径）、A8（prob04 电价可观测性）、A9（附加预报时刻分析）仍未裁定且属 prob02–prob04；本问图表未越界处理。
- AS06「5000 kW 作用侧」是 team_decision（D10），现有 25 条文献池无一条涉及该约定；本问图表只呈现按口径丙求解的结果，未把口径选择包装为文献支持。
- C1/E1、C2/E2、C3/E3 三处上游登记/措辞欠账仍未回写 global_symbols.yaml 与 assumption_v003/version.yaml；本动作按下游执行口径出图并在 findings 中显式记录冲突与差异，权威落点仍待 cross_question_review。
- LP 最优面可能不唯一（E 上下界两端可能活跃）；本问图表展示的是 run002 的求解器返回解，引用其数值时不比对各点解的唯一性，结论以约束残差 + (I1)/(I2) + 目标值 + 表 1/表 2 为准。
- 表 2 的「0:00/24:00 储电量」为计划窗首/末状态（AS01 左端点口径使计划窗为 0:10→24:10，模板固有相位），block_summary 与 soc_trajectory 的图注已说明一次；论文引用时不得与严格时钟口径混用。
- 文献池 25 条未逐篇阅读正文（21 条 Crossref 元数据级 + 4 条开放摘要），图表涉及的机制级主张只支撑框架级结论，任何公式级/定量级引用须在取得全文后使用。
- D10 的多日费用增量预估须在 prob02 按其实际负载/光伏重算（团队原报 38/365 已被更正为 249/365，68.2%；附件 2 全期累计约 6916.19 元），不得沿用「约一成工作日」的说法；本问为单日，未涉及该增量。
- AS03b（不计折旧）、AS05（常效率 90%）、AS07（不显式强制同时充放电）、AS14（无自放电）、AS15（无购电上限/无售电）、AS16（单日确定性）均为显式简化，偏差方向已在假设中逐条给出，须由 robustness 量化；本问图表不构成对这些简化的验证。
- price_action_3d 在散点密集段存在自遮挡（同一时段簇），已由配套 price_action_2d 消除投影歧义；三维图不得单独作为定量判读来源。
- prob01 的 conclusion 尚未记录（manifest conclusion 三字段为空），本地完成门禁在 locally_completed 迁移时会要求该字段；需由后续阶段（robustness/ablation 后）补齐。
- DR1（预注册判据实现偏离）：S3 的区间半宽用 (max−min)/2 全距法（0.115132），而 plan.md §2 预注册的是 2.5–97.5 分位半宽（0.096675）。两者都 ≤0.20，S3 判定与 stability_grade 不变；判据不事后修改，作为技术债登记，sanity Level 6 与论文引用时须注明实际统计量。
- DR2（判据覆盖范围偏离）：S2 实际对全部 OAT 网格取最大 |ΔC|/C*（含 E_init ±50%、E_min −50%/+100%，超出预注册的 ±20%），属更保守的超集；最大值仍为 η=0.80 的 +8.885%，判定不变。
- DR3（追踪链欠账）：plan.md §3.3 要求「每个样本记录扰动后输入的摘要指纹」，实现只记录 (source, σ, index) 与三个扰动因子均值，无输入 digest。可复现性由固定 seed 20260910 + 固定样本序 + label 保证，但计划声称的字段缺失，须在后续版本或论文附录说明。
- DR4（图例口径）：robustness_tornado.png 图例写 −20%/+20%，实际取值为 η ±11.1%、E_init ±25%、P_max ±20%；标题已注明 nearest grid point to ±20%、y 轴标签已给实际取值，引用时须按 y 轴标签读，勿按图例读。
- DR5（图缺格）：robustness_scenarios.png 不含唯一不可行情景 buycap_3000（无目标值，无法画柱），图中 buy_cap 少一根柱；图注必须说明「3000 kW 不可行」，否则易被读成该族全部可行。
- DR6（spider 归一化）：spider 图横轴用各参数自身网格半跨度归一化，x=±1 不是统一百分比（E_min/E_max 网格不对称）；定量引用一律以 sensitivity.json 的 relative_change 为准，不可跨曲线按横轴比较幅度。
- DR7（结构族比较口径不对等）：arbitrage_gain = 无储能购电费(扰动数据) − 目标值；depreciation 的目标含吞吐成本而分母不含（对储能偏保守），sell_price 的售电收益只计入含储能的解（对储能偏乐观）。两族的 arbitrage_reversal=[] 因此不作强结论。
- DR8（自放电族恒等式）：self_discharge 族的 I1/I2 残差最大 1.373e3，是改变状态转移后的必然差值（|I1|/(ρΔt)≈ΣE），非数值失败；已与核心族分离统计，sanity 不应据此判失败。
- U1–U3（上游登记欠账）：global_symbols.yaml 的 q_dis 域仍写 833.33（应为 750.00）、q_spill 的 first_question 仍写 prob02（应为 prob01）、assumption_v003/version.yaml 中 AS08 仍含「必然被激活」措辞；下游已按团队勘误 E1–E3 执行，权威回写待 cross_question_review。
- U4（禁止误归因）：团队 D10 原报的 38/365 已由假设阶段更正为 249/365（68.2%）、丙相对甲附件 2 全期增量 6916.19 元；本 robustness run001 是附件 1 单日实验，未重跑 365 天，上述数字不得归因于本次实验，prob02–prob04 须按实际负载/光伏重算。
- U7（结论字段空缺）：question_manifest.yaml 的 conclusion.conclusion_id/version/content_hash 仍为空，locally_completed 门禁会因此报错；须在 ablation 结束或 locally_completed 前由相应阶段补齐，本动作未越界代写结论。
- 噪声分布是诊断性设定（乘性、下界 0.02 截断、独立同分布、固定 seed），不是题面事实（AS16 只声明输入为确定性预测值）；S3 的区间只用于外推边界，不得包装为真实预测误差的概率分布。参数扰动 ±5/10/20% 来自 skills/robustness-study 的默认诊断区间而非文献标定（E_init/E_min 网格更宽）。
- LP 最优面非唯一（E 上下界两端可能活跃）：本实验只验证目标值与约束残差，情景之间调度轨迹的差异不得作为不稳定证据。robustness 的 5 张图不通过 record_figure_review 登记为交付图表（prob01 交付图 9 张已全部通过）。
- prob01 level_6: prob01 Level 6 独立复核（act-4694208eb3ce490d）：对象为 robustness/results/prob01_v003_robust_run001（task 238db2418a6b1aed432b，succeeded/supervised/CPU）。84 项独立只读断言 verdict=PASS、checks_failed=0；预注册 S1–S6 全部通过（S1 核心族 934/934、参数族 34/34；S2 max|ΔC|/C*=0.088848；S3 全距半宽 0.115132、均值偏移 0.065288；S4 934/934 方向不反转；S5 弹性符号全部符合；S6 求解器相对差 0.0），criteria_failed=[]、stability_grade=稳定；基线 6 项与 run002 逐位一致、追踪链（输入 md5/run002 sha256/代码 sha256）全部未变；947/948 可行，唯一不可行 buycap_3000 属结构族且已按预注册保留计入分母；三类『看似越界』量已归因（自放电恒等式残差、各族自身界、d10_yi 被否口径越限复现）。技术债：D-R1 S3 统计量偏离预注册（0.115132 vs 0.096675，均≤0.20）、D-R2 覆盖超集、D-R3 噪声样本缺输入指纹、D-R4/D-R5/D-R6 图件口径、§8.6 售电情景非物理、buy_cap 3000 kW 不可行、结转的文献/AS06/上游登记/A2–A9 warnings。无硬门禁失败，判 PASS_WITH_WARNING 并推进至 ablation。
- D-R1（预注册统计量偏离）：S3 实际用 (max−min)/2 全距半宽 0.115132，plan.md §2 预注册为 C 的 2.5–97.5 分位半宽 0.096675；独立复算两者均 ≤0.20（判定与 stability_grade 不变），实现比预注册更保守。判据不事后修改，作为技术债登记；论文与可视化引用 L6 区间时必须注明实际统计量为全距半宽。
- D-R2（覆盖范围偏离）：S2 实际对全部 OAT 网格取最大 |ΔC|/C*（含 E_init ±50%、E_min −50%/+100%），超出预注册的 ±20%，属更保守的超集；最大值仍为 η=0.80 的 +8.885%，判定不变。
- D-R3（追踪链欠账）：plan.md §3.3 要求『每个样本记录扰动后输入的摘要指纹』，实现只记录 (source, σ, index) 与三个因子均值，无输入 digest；可复现性由固定 seed 20260910 + 固定样本序 + label 保证，但须在论文附录或后续版本说明。
- D-R4（图例口径）：robustness_tornado.png 图例写 −20%/+20%，实际取值为 η 0.8–1.0（±11.1%）、E_init 4500–7500（±25%）、P_max 4000–6000（±20%）；标题已注明 nearest grid point to ±20%、y 轴标签给出实际取值，引用时须按 y 轴标签读，勿按图例读（本动作已图像抽检确认）。
- D-R5（图缺格）：robustness_scenarios.png 不含唯一不可行的 buycap_3000（无目标值，无法画柱），图中 buy_cap 少一根柱；图注必须说明『3000 kW 不可行』，否则易被读成该族全部可行（本动作已图像抽检确认）。
- D-R6（spider 归一化）：spider 图横轴用各参数自身网格半跨度归一化，x=±1 不是统一百分比（E_min/E_max 网格不对称）；定量引用一律以 sensitivity.json 的 relative_change 为准，不可跨曲线按横轴比较幅度。
- D-R7（结构族比较口径不对等）：arbitrage_gain=无储能购电费(扰动数据)−目标值；depreciation 的目标含吞吐成本而分母不含（对储能偏保守），sell_price 的售电收益只计入含储能的解（对储能偏乐观）。两族 arbitrage_reversal=[] 因此不作强结论。
- §8.6 售电情景非物理：sell_price≥0.50 元/kWh 时 LP 售出 12293.617 kWh，超过附件 1 物理盈余上限 6247.963 kWh（多出 6045.65 kWh），根因是 AS08 的 s_t≤PV_t·Δt 界不够紧；accepted 基线 Σs=0 稳健（上网价 ≤0.35 元/kWh 不改变最优解），但该情景收益不得当作真实售电收入，prob02–prob04 若引入售电须先收紧 s_t 的界。
- AS15『无购电上限』是强简化：buy_cap=3000 kW 时 accepted 计划不可行，门槛落在 (3000,4000] kW；accepted 解购电峰值 8458.8273 kW（时段 0:50），>6000/5000/4000/3000 kW 的时段数 12/14/29/71（共 144）。已在 report §8.5 登记，论文须说明。
- LP 最优面非唯一（E 上下界两端可能活跃）：robustness 只验证目标值与约束残差，情景之间调度轨迹的差异不得作为不稳定证据；sanity 验收以约束残差 + (I1)/(I2) + 目标值 + 表 1/表 2 为准。
- 结转 L1–L4 技术债：文献池 25 条未逐篇阅读正文（21 条 Crossref 元数据级 + 4 条开放摘要）；AS06「5000 kW 作用侧」为 team_decision（D10），无文献支撑，论文不得包装为文献支持；C1/E1、C2/E2、C3/E3 三处上游登记/措辞欠账仍待 cross_question_review 回写 global_symbols.yaml 与 assumption_v003/version.yaml；表 2 的 0:00/24:00 为计划窗首/末状态（AS01 左端点相位 0:10→24:10），论文与图注须显式说明一次；A2（结果日期 2025-02-01～12-31）、A6（附件 3 降尺度与年末边界）、A7、A8、A9 仍未裁定且属 prob02–prob04。
- question_manifest.yaml 的 conclusion.conclusion_id/version/content_hash 仍为空，locally_completed 门禁会因此报错；须在 ablation 结束或 locally_completed 前由相应阶段补齐，本动作未越界代写结论。
- 本动作处于 ablation 阶段『提交—执行—汇总』的第二步：task c1faaa09dedfb103c598 为 queued。按团队既有事实，one_shot 唤醒模式下长时间无外部唤醒时 task 保持 queued 属正常排队而非失败，不得由本 Agent 在短命 shell 内代跑 start_queued。若该 task 以 interrupted/timeout/非零退出结束：不得复用同一 output_directory，须按 resource-manager 规程以新 attempt + 新 output_directory（如 _ablation_run002）重跑，并把失败指纹记入 ablations/task_submission.md。
- make_task_spec 的预检在 PATH 中找不到 ruff（spec.preflight.ruff=unavailable），其内部只做 compileall；本动作已用项目 venv 的 ruff 对 ablations/code/ 显式检查并通过（All checks passed），两者不矛盾。若提交环境仍无 ruff，preflight 只覆盖 compileall。
- 探针（12 个 144 时段 case）在隔离 task 之外运行，仅用于验证基线闸门、MILP/DP/结构消融/效率作用位置的代码正确性，不构成 ablation 交付结果；其数值（DP 四档、D 的 2217.08 元、E 的 0、F 的 −4.869%/−3.773%/−2.728% 等）不得作为论文数据引用，正式数值一律以 task c1faaa09dedfb103c598 的产物为准。
- C3 的预注册阈值是『DP(h=50) 相对 C_LP 偏差 ∈[0,1%]』；探针给出 +0.791%，余量约 0.21 个百分点。若正式 task 结果越界，按 plan.md §2 记为技术债并给出粒度-偏差边界，不得事后放宽阈值或更改粒度集合。
- F 族固定 c/q 上限（833.3333/750.0000），与 robustness eta_placement 族按情景重算上限的口径不同；本问因 accepted 解放电峰值 715.653033 kWh 未触及 750，两族数值恰好一致，但跨阶段引用时必须注明口径（plan.md §3.6/§3.9）。
- E（删除弃光变量）在探针下费用与 accepted LP 完全相同（ΔC=0），说明 s_t 的上界在最优解处不紧；该结论只对附件 1 单日成立，prob02–prob04 若引入售电或更紧的盈余约束须重算，不得把『s_t 无贡献』外推到其他小问。
- DP 的转移代价按 (E_{t−1}→E_t) 解析求最优（含 c/q 上限与 s≤PV·Δt 可行域；当盈余超出可弃光上限时沿增大 c 的方向补偿，等价于允许同时充放电，与 LP 一致），是网格受限下的精确最优，因此 DP 结果必然 ≥ LP 最优，粒度偏差属离散化偏差而非求解失败。DP 无求解器迭代，A3 的『同预算 60 s』对其无对应量，已在 task_spec/task_config 与 run_manifest 中声明为确定性遍历。
- LP 最优面可能不唯一（E 上下界两端活跃，formulation/sanity/robustness 均已登记）：本实验只比对目标值、约束残差与题面指标，不比对各点解的唯一性；DP/MILP 与 LP 的调度轨迹差异不得作为不一致或不稳定的证据。
- MILP 的 mip_gap=0.0 是探针在 144 个二元变量下 HiGHS 返回的结果；若正式 task 因 60 s 时限出现 mip_gap>1e-6，按 config/compute.yaml 的 allow_missing_mip_gap_with_incumbent 与 config/gates.yaml 的 allow_pass_with_warning 登记 incumbent、mip_gap 与节点数，不得伪报最优。
- question_manifest.yaml 的 conclusion.conclusion_id/version/content_hash 仍为空，locally_completed 门禁会因此报错，须在 ablation 结束或 locally_completed 前补齐；ablation 图件是实验产物，是否登记为交付图表（figures.yaml + record_figure_review + 自动质检与视觉复核）将在结果就绪后的动作中按 A4.2 决定，本动作不登记、不宣称。
- A-DR1（追踪链欠账）：task 只落盘逐 case 汇总（case.json/raw_cases.jsonl），未落盘逐时段序列，无法从产物直接核对轨迹；已由本动作独立重解 12/12 目标值与汇总指标一致到 ≤1e-9 补齐，论文引用 DP/MILP 轨迹时须说明其逐点可追溯性弱于主结果。
- A-DR2（口径纪律）：F 族固定 c/q 上限（833.3333/750.0000），与 robustness eta_placement 族按情景重算上限的口径不同；探针已证明本数据下不绑定（放电峰值 715.653033 kWh < 750），两族数值逐位一致，但跨阶段引用必须注明上限纪律（plan.md §3.6/§3.9）。
- A-DR3（DP 与 LP 的口径差异）：DP 与 LP 均不禁止同时充放电（AS07 简化），h=400/200/100/50 分别出现 5/4/4/1 个同充放时段；只影响轨迹不影响目标值与可行性，不得作为「模型不一致」或「不稳定」证据。
- A-DR4（规模局限）：MILP 仅 1 节点即证最优、mip_gap=0.0，是 144 时段小规模实例的结论，未验证大规模可解性；prob02–prob04 规模上升时须重估。
- A-DR5（外推边界）：E 族（删除弃光变量 s_t）ΔC=0、Σs_t=0 只对附件 1 单日成立；robustness 已记录 sell_price≥0.50 元/kWh 时 s_t 上界不够紧并出现非物理套利（Σs=12293.617 kWh > 物理盈余 6247.963 kWh），prob02–prob04 若引入售电或更紧盈余约束必须先收紧 s_t 的界并重算。
- A-DR6（图件修正）：task 原始图 ablation_waterfall.png 最左数值标签压 y 轴标签、ablation_complexity_tradeoff.png 点标注相互重叠且 C_dp_h400 标注被上边界截断；本动作已用统一脚本以同一数据重绘为 ablations/figures/ 登记版（中文标注、统一色系/DPI），task 原始图原样保留。
- A-DR7（判据余量）：C3 的 h=50 偏差 +0.791% 距预注册阈值 1% 仅 0.21 个百分点，判据不事后修改；若未来版本放宽/更改 DP 粒度集合须重跑并重新登记。
- A-DR8（结论字段）：question_manifest.yaml 的 conclusion 三字段由本动作补齐（此前为空，会使 locally_completed 门禁报错）；若上游口径再变，本结论的 content_hash 变化将令 prob02–prob04 stale。
- 结转技术债（不在本阶段处理）：文献池 25 条未逐篇阅读正文（21 条 Crossref 元数据级 + 4 条开放摘要）；AS06「5000 kW 作用侧」为 team_decision（D10）无文献支撑、论文不得包装为文献支持；C1/E1、C2/E2、C3/E3 三处上游登记欠账（global_symbols.yaml 的 q_dis 域 833.33→750.00、q_spill 的 first_question prob02→prob01、assumption_v003/version.yaml 中 AS08「必然被激活」措辞）待 cross_question_review 回写；A2/A6/A7/A8/A9 未裁定且属 prob02–prob04；LP 最优面可能不唯一（本阶段只比对目标值、约束残差与题面指标，不比对各点解的唯一性）。

## 阻塞项

- 无

## 下次唤醒

2026-09-10T14:30:30.766779+00:00
