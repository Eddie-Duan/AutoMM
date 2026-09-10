---
name: robustness-study
description: 对已通过基础检查的模型运行扰动、敏感性和替代求解器实验。
---

# Robustness Study

本阶段在本题配置下为**必做**（`config/workflow.yaml: mandatory_stages`），不得跳过，不得写 decision=skipped。

先预注册核心结论、变量、扰动范围、样本数和稳定性阈值。默认 95% 置信区间、±5/10/20% 参数扰动、至少 100 次随机实验。生成任务矩阵交 compute-manager；结果写入版本 `robustness/`；生成敏感性图；最后触发 sanity Level 6。

若某类扰动不适用，写入产物的「适用性决定」一节并在其余类别中完成实验，不得整阶段返回 skipped。

不能看完结果后修改稳定性标准。原始样本、汇总统计和图表必须分开保存并可追溯到 task ID。
