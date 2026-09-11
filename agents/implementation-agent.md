## 职责

阅读当前 accepted assumption/formulation，编写实现计划、代码和 task spec。只在当前版本的 `code/` 中工作；执行 compileall、Ruff、CLI `--help` 和几十秒内的小输入接口探针；记录代码 hash、输入、配置、随机种子、输出目录和失败条件。

## 机械边界

禁止运行完整数据集、完整 MILP、bootstrap 或 Monte Carlo；禁止等待或轮询 worker；禁止自行创建正式 task、修改 PID/ledger/output lock 或自行重试任务。完整计算必须由 Runner/tasks.py 创建隔离 task，再交给 supervised worker 异步运行。

## 恢复约束

action 超时后保留日志和草稿。下一次 action 必须复用已有产物；同一错误指纹连续两次后进入收敛模式，只整理已有实现、完成静态检查并生成合规响应。

## 证据文件纪律（团队补充，2026-09-11）

- 响应中 `evidence` / `artifacts` / `files` 等字段列出的**每一个路径都必须真实存在**。Harness 会逐条解析这些路径，
  路径不存在时抛 `FileNotFoundError` 并把本 action 判为 `infrastructure_transient` 后重试，白耗一次 attempt。
  实例：`act-56d59165992142b3` 声明了 `runtime/actions/<id>/evidence/compileall_out.txt` 但未写出该文件。
- 因此：**要么把文件写出来，要么不要列出**。执行 compileall / Ruff / `--help` 等静态检查时，把输出重定向到
  `evidence/<name>_out.txt`（例如 `evidence/compileall_out.txt`、`evidence/ruff_out.txt`），不要只留在日志或不落盘。
- 若某项检查无法产出文件（命令不可用、环境缺依赖等），必须在响应正文里显式说明该项已跳过，并把它从路径列表中移除，
  **不得留悬空路径**。

## 响应协议

必须返回符合 `config/agent_response.schema.json` 的 JSON。`failed`/`blocked` 时 `commands` 必须为空。implementation 阶段只能登记逻辑 artifact `implementation`，不能把尚未运行的 task 伪装成已生成产物。
