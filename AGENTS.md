# AutoMM Agent 规则

> 完整项目指南见 `PROJECT.md`；自动研究循环见 `RESEARCH_LOOP.md`。两者是本文档的补充规范，冲突时以更具体的阶段/响应约束为准。

- 使用简体中文；公式、代码标识符和参考文献标题可保留原文。
- 先读取题面、配置和已有产物，再修改当前阶段的文件。
- 不直接编辑 `runtime/workflow_state.json` 或受保护的 manifest 字段，状态变更必须通过响应 `commands`。
- 不覆盖假设、公式、结果、日志和结论历史；当前假设版本内的工作代码可以更新。
- implementation Agent 只做静态检查和小型探针，不运行完整数据集或等待 worker。
- 计算必须使用隔离 task、独立输出目录和 supervised worker。
- 任何 Harness invariant 都必须严格失败；模型计算的非关键故障应按 failure class 恢复或降级审查。
- 最终响应必须是符合 `config/agent_response.schema.json` 的 JSON。

## 运行环境（团队提供的事实）

- CPU：32 逻辑核；内存：15.7 GB。
- GPU：NVIDIA GeForce RTX 5070 Laptop（8 GB 显存，Blackwell 架构），驱动 582.05，单卡。
- Python：3.14.4；torch 2.11.0+cu128 已安装并验证 CUDA 可用（`cuda.is_available()=True`，2026-09-10 实测）。

## GPU 使用规则

- 训练/推理/大规模矩阵类模型优先使用 GPU；代码内用 `torch.cuda.is_available()` 动态选择 device，不得硬编码 `cuda:0`。
- 显存预算 8 GB：batch_size 必须按显存预算设置；显存不足时用梯度累积或降 batch，禁止直接 OOM。
- 单卡 GPU：GPU 计算任务必须串行（同一时间最多 1 个 GPU 任务），task spec 中须注明该约束。
- 求解器（HiGHS 等）默认 CPU；只有数据规模大到 CPU 不可行时才考虑 GPU 路径。
- RTX 50 系（Blackwell）需要 CUDA ≥ 12.8：torch 必须装 cu128 及以上构建，否则 `cuda.is_available()` 为 False。

## GPU 依赖自装规则（torch CUDA 版）

- 当某阶段（实现、计算、鲁棒性等）确实需要 torch 且环境未装（或未装 CUDA 构建）时，允许 Agent 自行安装，不必等待人工；这是对「小型探针」约束的环境准备例外。
- 安装前先执行 `nvidia-smi` 确认驱动支持的 CUDA 版本；按 https://pytorch.org/get-started/locally/ 选择官方命令（RTX 50 系用 `--index-url https://download.pytorch.org/whl/cu128` 或更新）。
- Python 3.14 需要 torch ≥ 2.9。安装后必须运行 `python -c "import torch; print(torch.__version__, torch.cuda.is_available())"` 验证 CUDA 可用，并把验证输出写入当前动作目录作为安装证据。
- 只在确实需要 GPU 的步骤安装；不得在每次动作中重复安装；安装失败（网络/无匹配轮子）时记录证据并按 failure_class 路由，不得伪报安装成功，也不得因此人工 blocked。
- 不得卸载或升级与当前任务无关的依赖。