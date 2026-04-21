# P2.4 Scheduler Refactor And Orchestration Backend Plan

更新时间：`2026-04-20`

## 执行状态

截至 `2026-04-20`，modernization `P2.4` 可视为已完成并通过验收。

当前结论：

- 建议合入
- 未发现阻塞性问题
- 本文同时作为 `P2.4` 的执行计划与验收归档

## 一句话目标

把当前调度入口标准化为：

- 默认走 `local` orchestration
- 可切换到 `prefect` orchestration
- 两条路径复用同一任务 contract
- backend 初始化或提交失败时仍可安全降级

第一版必须做到：

- 保留 `serve` / `serve --run-now` 的本地开发体验
- `scheduler` 不再直接依赖裸业务函数，而是通过 orchestration backend 提交正式任务
- `Prefect` 只作为渐进 adapter，不要求平台级 deployment lifecycle

## 验收归档

本轮验收确认，`P2.4` 的核心边界已经满足：

- 已定义稳定的 `SubmittedTask` / `OrchestrationBackend` contract
- 已实现 `LocalOrchestrationBackend`，并明确复用 `LocalTaskRunner`，没有旁路主业务逻辑
- 已实现 `PrefectOrchestrationBackend` 最小 adapter，支持注入 `submitter`、awaitable 返回值与 deployment name 快速校验
- 已实现 `build_orchestration_backend()`，默认 `local`，`prefect` 初始化失败时自动降级
- 已将 `local_scheduler.py` 收口到 orchestration backend，`run_job()` 通过 backend 提交 `scheduled_run`
- 已保留 `scheduler.py` 兼容 facade，`serve` / `serve --run-now` 语义未破坏
- 已接入 `orchestration_mode` / `prefect_deployment_name` 配置加载与校验
- README 已说明当前 orchestration 边界、降级行为与未覆盖项

实现与覆盖证据如下：

- `orchestration/backend.py` 已定义 `SubmittedTask` 与 `OrchestrationBackend`
- `orchestration/local_backend.py` 已通过 `LocalTaskRunner` 提交正式任务，并返回稳定的 local backend metadata
- `orchestration/prefect_adapter.py` 已实现最小 `Prefect` submit adapter，不把 runtime 绑死到主路径
- `orchestration/__init__.py` 已提供 backend builder 与 `prefect -> local` 自动降级
- `local_scheduler.py` 已通过 backend 提交 `scheduled_run`，并在非 local backend 提交失败时回退 `local`
- `scheduler.py` 已保留旧导入路径与 CLI facade
- `agent.py` 已保持 `serve` / `serve --run-now` 的兼容调用路径
- `config.py`、`config_loader.py`、`config_validator.py` 已完成 orchestration 配置接线
- `README.md` 已明确当前不包含正式 `Prefect` deployment lifecycle

本轮复验结果归档如下：

- `uv run ruff check products/tech_blog_monitor` 通过
- `uv run pytest -q products/tech_blog_monitor/test/test_prefect_adapter.py`：`4 passed`
- `uv run pytest -q products/tech_blog_monitor/test/test_scheduler.py`：`4 passed`
- `uv run pytest -q products/tech_blog_monitor/test/test_agent.py`：`6 passed`
- `uv run pytest -q products/tech_blog_monitor/test/test_config.py`：`42 passed`
- `uv run pytest -q products/tech_blog_monitor/test`：`273 passed, 1 skipped`

按当前实现与测试证据，可认为以下验收口径已经满足：

- backend contract 已稳定，而不是临时 facade
- `local` 与 `prefect` 只改变提交方式，不改变核心任务语义
- 调度层已经从“直接触发函数”升级为“通过 orchestration backend 提交正式任务”
- `Prefect` 路径仍保持渐进 adapter 定位，没有越界成平台生命周期项目

剩余非阻塞尾项：

- `test_agent.py` 当前主要守住 `serve` CLI 的兼容调用路径，还没有单独断言 `prefect mode` 下 CLI 端的 backend 选择链路
- README 已说明当前不含 `Prefect` deployment lifecycle；后续进入 `P2.5+` 时，建议把“scheduler trigger”与“平台原生调度”差异写得更显式

## 背景

在 `P2.3` 之后，系统已经具备：

- `TaskRequest` / `TaskExecutionRecord`
- `LocalTaskRunner`
- `task_records` 持久化
- `manual_run` / `scheduled_run` / `rebuild_*` 标准任务语义

但调度层仍需要单独收口：

- CLI `serve` 的触发路径需要明确落到 orchestration backend
- 本地 scheduler 和 `prefect` 路径需要共享同一任务语义
- backend 选择、降级与配置边界需要固定
- README 和测试需要明确说明什么属于“已支持的 orchestration”，什么仍未进入范围

如果不做 `P2.4`，系统虽然已经有任务模型，但调度入口仍不够清晰，也难以继续往正式平台编排演进。

## 范围

本阶段包含：

- 定义 `OrchestrationBackend` 最小 contract
- 定义 `SubmittedTask` 提交结果模型
- 实现 `LocalOrchestrationBackend`
- 实现 `PrefectOrchestrationBackend` 的最小 adapter
- 实现 backend builder 与自动降级
- 将 `local_scheduler.py` 接到 orchestration backend
- 保留 `scheduler.py` 作为兼容 facade
- 接入配置项：
  - `TECH_BLOG_ORCHESTRATION_MODE`
  - `TECH_BLOG_PREFECT_DEPLOYMENT_NAME`
- 补充 README 与回归测试

本阶段不包含：

- `Prefect` server / worker / deployment lifecycle 联调
- distributed queue / worker 集群
- article-level `reextract_content` / `reenrich_articles` 编排
- dashboard / 告警系统 / ops summary
- 对 `monitor.run()` 主业务逻辑做大改

这些属于 `P2.5+` 或更后续阶段。

## 设计原则

### 1. 本地优先，平台兼容

第一版默认仍应是：

- 本地开发走 `local`
- 无 `Prefect` 运行时也能工作
- backend 初始化失败时自动回退 `local`

### 2. backend 只负责提交，不重写任务语义

稳定契约仍然应是：

- `task_type`
- `trigger_source`
- `requested_by`
- `input_payload`
- `task_records` / `run_summary`

也就是说：

- `local` 与 `prefect` 只改变“如何提交”
- 不改变“任务是什么、结果怎么记录”

### 3. scheduler 负责触发，不负责业务执行细节

正确分层应是：

- `local_scheduler.py` 负责时间触发和调度注册
- `orchestration/` 负责 backend 选择与任务提交
- `LocalTaskRunner` 负责实际任务执行和记录

### 4. fail-open 优先

必须覆盖：

- `prefect` 依赖不可用
- deployment name 缺失
- submitter 抛错

这些错误不应破坏 `local` 主路径。

## 目标产物

`P2.4` 第一版交付物应包括：

- `SubmittedTask`
- `OrchestrationBackend`
- `LocalOrchestrationBackend`
- `PrefectOrchestrationBackend`
- `build_orchestration_backend()`
- `local_scheduler.py` 调度接线
- `scheduler.py` 兼容 facade
- `serve` 路径的 orchestration mode 接线
- README / 测试

## 建议实现方案

### A. Orchestration Contract

建议放入：

- `products/tech_blog_monitor/orchestration/backend.py`

建议最小对象：

- `SubmittedTask`
- `OrchestrationBackend`

要求：

- `SubmittedTask` 至少包含 `task_id`、`task_type`、`backend_name`、`accepted`、`metadata`
- `submit_monitor_run()` 的输入字段与现有任务模型保持一致

### B. Local Backend

建议放入：

- `products/tech_blog_monitor/orchestration/local_backend.py`

要求：

- 内部复用 `LocalTaskRunner`
- 返回稳定的 `SubmittedTask`
- 在 `metadata` 中至少保留：
  - `exit_code`
  - `task_status`

### C. Prefect Adapter

建议放入：

- `products/tech_blog_monitor/orchestration/prefect_adapter.py`

建议行为：

- 只做最小提交封装
- 允许注入 `submitter` 便于测试
- deployment name 为空时快速失败
- 支持同步或 awaitable 提交返回值

要求：

- 不把 `prefect` runtime 作为硬依赖
- 缺运行时或初始化失败时，可由 builder 层降级

### D. Scheduler Refactor

建议放入：

- `products/tech_blog_monitor/local_scheduler.py`
- `products/tech_blog_monitor/scheduler.py`

要求：

- APScheduler 继续保留在 `local_scheduler.py`
- `run_job()` 通过 backend 提交 `scheduled_run`
- `scheduler.py` 继续保留旧导入路径和 CLI 兼容行为

### E. Config Wiring

建议接线：

- `products/tech_blog_monitor/config.py`
- `products/tech_blog_monitor/config_loader.py`
- `products/tech_blog_monitor/config_validator.py`
- `products/tech_blog_monitor/agent.py`

要求：

- `orchestration_mode` 只允许 `local` / `prefect`
- `prefect_deployment_name` 作为可选增强配置
- `serve` / `serve --run-now` 路径复用相同 backend 选择逻辑

### F. README And Runbook

至少明确：

- 当前支持的 orchestration mode
- `local` 与 `prefect` 的语义区别
- 自动降级行为
- 当前不包含真正的 `Prefect` deployment lifecycle

## 推荐改动文件

建议新增或重点修改：

- `products/tech_blog_monitor/orchestration/backend.py`
- `products/tech_blog_monitor/orchestration/__init__.py`
- `products/tech_blog_monitor/orchestration/local_backend.py`
- `products/tech_blog_monitor/orchestration/prefect_adapter.py`
- `products/tech_blog_monitor/local_scheduler.py`
- `products/tech_blog_monitor/scheduler.py`
- `products/tech_blog_monitor/agent.py`
- `products/tech_blog_monitor/config.py`
- `products/tech_blog_monitor/config_loader.py`
- `products/tech_blog_monitor/config_validator.py`
- `products/tech_blog_monitor/README.md`
- `products/tech_blog_monitor/test/test_scheduler.py`
- `products/tech_blog_monitor/test/test_prefect_adapter.py`
- 必要时补：
  - `products/tech_blog_monitor/test/test_agent.py`
  - `products/tech_blog_monitor/test/test_config.py`

## 分步计划

### Step 1：定义 orchestration contract

目标：

- 固定 backend 提交接口和返回结果模型

交付：

- `SubmittedTask`
- `OrchestrationBackend`

完成标准：

- backend contract 稳定、易 mock、可测试

### Step 2：实现 local backend

目标：

- 让本地调度路径正式走 `LocalTaskRunner`

交付：

- `LocalOrchestrationBackend`

完成标准：

- `scheduled_run` 可通过 local backend 提交
- 返回 `task_id`、`task_status`、`exit_code`

### Step 3：实现 prefect adapter 与 builder

目标：

- 提供最小 `prefect` 提交能力与自动降级

交付：

- `PrefectOrchestrationBackend`
- `build_orchestration_backend()`

完成标准：

- 配置 `prefect` 时可构建 backend
- 缺依赖或 deployment 配置异常时可降级 `local`

### Step 4：重构 scheduler 接线

目标：

- 让 `serve` / `run-now` 通过 orchestration backend 提交正式任务

交付：

- `local_scheduler.py`
- `scheduler.py` facade 兼容
- `agent.py` 接线

完成标准：

- `serve` 仍可正常工作
- 旧 `products.tech_blog_monitor.scheduler` 导入路径不破

### Step 5：补测试与文档

目标：

- 让 `P2.4` 具备回归和说明文档

交付：

- scheduler / prefect adapter 测试
- config contract 测试
- README 更新

完成标准：

- 无 `Prefect` runtime 的环境也能完整跑测试

## 验收标准

`P2.4` 合入前至少满足：

- 已定义 `SubmittedTask` 与 `OrchestrationBackend`
- 已实现 `LocalOrchestrationBackend`
- 已实现 `PrefectOrchestrationBackend` 最小 adapter
- 已实现 `build_orchestration_backend()` 与自动降级
- `local_scheduler.py` 已通过 backend 提交 `scheduled_run`
- `scheduler.py` 仍保留兼容 facade
- `serve` / `serve --run-now` 路径未破坏既有使用方式
- `TECH_BLOG_ORCHESTRATION_MODE` 与 `TECH_BLOG_PREFECT_DEPLOYMENT_NAME` 已接入配置体系
- backend 不同不应改变核心任务语义与 `run_summary` 口径

## 建议测试面

至少覆盖以下测试：

- backend builder 默认走 `local`
- `prefect` 配置异常时降级 `local`
- `PrefectOrchestrationBackend` 正常提交测试
- `run_job()` 默认走 local backend
- `run_job()` 支持注入 fake prefect backend
- `start_local_scheduler()` 注册 jobs 测试
- `serve` CLI 接线测试
- config env contract 测试：
  - `TECH_BLOG_ORCHESTRATION_MODE`
  - `TECH_BLOG_PREFECT_DEPLOYMENT_NAME`

建议最少复验命令：

- `uv run ruff check products/tech_blog_monitor`
- `uv run pytest -q products/tech_blog_monitor/test/test_prefect_adapter.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_scheduler.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_agent.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_config.py`
- `uv run pytest -q products/tech_blog_monitor/test`

## 非目标与风险提醒

这一轮最容易失控的点有三个：

- 把 `P2.4` 做成完整的 `Prefect` 平台接管项目
- 在 orchestration 层重写 `monitor.run()` 或任务执行逻辑
- 把 article-level 运维任务和 queue / worker 系统一起塞进来

如果出现这些倾向，应回到 `P2.4` 边界：

- `P2.4` 是调度层重构与 backend 抽象
- 不是完整平台编排生命周期项目
- 不是分布式执行系统
- 不是 `P2.5` 的运营收口与 ops summary

## 结论

`P2.4` 最合理的落地顺序是：

- `orchestration contract -> local backend -> prefect adapter -> scheduler 接线 -> config / README / tests`

先把 backend 边界和调度接线做稳，再进入 `P2.5` 的运营收口与回归门禁。
