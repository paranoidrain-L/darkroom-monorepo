# P2.3 Task Model And Operational Action Standardization Plan

更新时间：`2026-04-20`

## 执行状态

截至 `2026-04-20`，modernization `P2.3` 可视为已完成并通过验收。

当前结论：

- 建议合入
- 未发现阻塞性问题
- 本文同时作为 `P2.3` 的执行计划与验收归档

## 一句话目标

把“运维动作”从临时脚本调用，提升为：

- 有明确输入输出 contract
- 有幂等键与重试语义
- 有统一 task runner
- 有最小任务记录持久化

第一版必须做到：

- 保留 `monitor.run()` 作为业务核心
- 让任务层只负责包装、记录和标准化结果
- 无 queue / 无外部 orchestration 时也能本地稳定运行

## 验收归档

本轮验收确认，`P2.3` 的核心边界已经满足：

- 已定义 `TaskRetryPolicy`、`TaskRequest`、`TaskExecutionRecord`，并收口稳定的任务输入 / 输出 contract
- 已实现稳定的 `build_task_idempotency_key()` 规则，重复输入可得到稳定幂等键
- 已实现 `TaskRunner` / `LocalTaskRunner`，统一处理 running -> succeeded / failed 生命周期
- 已把 `manual_run`、`scheduled_run`、`rebuild_search_index`、`rebuild_retrieval_index` 纳入正式任务模型
- 已补齐 `task_records` 最小持久化与 repository 读写
- 当主数据库未配置时，仍可回退到 sidecar sqlite 持久化任务记录
- README 已补充 `task_records` 稳定字段、任务语义和回退行为说明

实现与覆盖证据如下：

- `tasks/models.py` 已定义任务 contract、幂等键生成和执行记录模型
- `tasks/runner.py` 已实现本地 task runner、任务状态流转、结果标准化和 sidecar fallback
- `db/repositories/task_repository.py` 已提供 `task_records` 的稳定字段与持久化接口
- `test/test_tasks.py` 已覆盖：
  - 幂等键生成
  - `manual_run` / `scheduled_run` 任务落库
  - `rebuild_search_index` / `rebuild_retrieval_index` 任务化
  - sidecar sqlite fallback
  - failed task 状态与 `retry_count` 行为
- README 已补充 `task_records` 表用途、字段说明与本地回退路径

本轮复验结果归档如下：

- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check products/tech_blog_monitor` 通过
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_tasks.py`：`9 passed`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_agent.py products/tech_blog_monitor/test/test_ops.py`：`7 passed`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test`：`271 passed, 1 skipped`

按当前实现与测试证据，可认为以下验收口径已经满足：

- 已形成稳定任务模型，而不再是临时函数调用集合
- 已明确幂等键、重试、状态流转和结果记录语义
- 已覆盖最小运维动作标准化，并与现有业务主链路保持低侵入
- 已具备无外部 orchestration 前提下的本地稳定运行与追踪能力

剩余非阻塞尾项：

- article-level `reextract_content` / `reenrich_articles` 仍未纳入统一任务模型
- queue / worker / 分布式任务编排仍不在 `P2.3` 范围内
- scheduler / orchestration 的进一步扩展仍属于 `P2.4+`

## 背景

在 `P2.2` 之后，系统已经具备：

- 结构化运行语义
- metrics / tracing bridge
- 本地与 OTLP 导出模式

但运维动作本身仍然需要标准化：

- 单次 run 与定时 run 应该是正式任务，而不是裸函数调用
- 重建索引不应只是工具脚本，而应有正式任务记录
- 幂等键、重试计数、输入参数、输出 artifact 应该可追踪

如果没有 `P2.3`，系统仍然更像“一组可调用函数”，而不是“可运营的任务系统雏形”。

## 范围

本阶段包含：

- 定义任务输入 / 输出 contract
- 定义幂等键生成规则
- 定义重试策略最小模型
- 实现 `TaskRunner` / `LocalTaskRunner`
- 增加最小 `task_records` 持久化
- 将至少这几类动作接入正式任务模型：
  - `manual_run`
  - `scheduled_run`
  - `rebuild_search_index`
  - `rebuild_retrieval_index`
- 补充 README / runbook / 回归测试

本阶段不包含：

- article-level `reextract_content`
- article-level `reenrich_articles`
- queue / worker 集群
- `Prefect` deployment lifecycle
- 多租户权限系统
- 自动重试调度器

这些属于 `P2.4+` 或更后续阶段。

## 设计原则

### 1. `monitor.run()` 仍然是业务核心

`P2.3` 不重写主业务逻辑。

正确分层应是：

- `monitor.run()` 负责业务执行
- `LocalTaskRunner` 负责任务包装、记录和标准化输出

### 2. 任务 contract 必须先于编排

如果输入 / 输出 / 幂等 / 错误语义都不稳定，后面再接 scheduler / Prefect 只会放大混乱。

### 3. 先记录，再自动化

第一版重心是：

- 有记录
- 能追踪
- 可重放

而不是：

- 自动队列
- 自动重试
- 分布式并发任务系统

### 4. sidecar sqlite 仍然要保留

当 `TECH_BLOG_DATABASE_URL` / `TECH_BLOG_ASSET_DB_PATH` 都未配置时，仍应允许本地通过 sidecar sqlite 记录任务。

## 目标产物

`P2.3` 第一版交付物应包括：

- `TaskRequest`
- `TaskRetryPolicy`
- `TaskExecutionRecord`
- `build_task_idempotency_key()`
- `TaskRunner` protocol
- `LocalTaskRunner`
- `task_records` repository / schema
- `manual_run` / `scheduled_run` / `rebuild_*` 标准任务化
- README / runbook / 测试

## 建议实现方案

### A. 任务 contract

建议放入：

- `products/tech_blog_monitor/tasks/models.py`

建议最小对象：

- `TaskRetryPolicy`
- `TaskRequest`
- `TaskExecutionRecord`

要求：

- `TaskRequest` 自动生成幂等键
- contract 字段可序列化、可落库
- `TaskExecutionRecord` 能表达完整执行结果

### B. 幂等键

建议使用：

- `task_type`
- `trigger_source`
- `scope`
- `input_payload`

组合后生成稳定哈希。

要求：

- 相同输入重复触发时，幂等键稳定
- 重放时不覆盖旧记录，而是生成新 attempt 并累加 `retry_count`

### C. TaskRunner

建议放入：

- `products/tech_blog_monitor/tasks/runner.py`

建议分层：

- `TaskRunner` protocol
- `LocalTaskRunner`

要求：

- 包装任务上下文
- 写入 running -> succeeded / failed 状态
- 允许定制 `result_builder`
- 允许定制 `result_status_resolver`
- 保持对 `monitor.run()` 的最小侵入

### D. 最小持久化

建议复用现有数据库层：

- `task_records` 表
- `TaskRepository`

建议字段至少包括：

- `task_id`
- `task_type`
- `task_status`
- `trigger_source`
- `requested_by`
- `idempotency_key`
- `scope`
- `artifact_uri`
- `input_payload`
- `result_payload`
- `max_retries`
- `retry_count`
- `started_at`
- `finished_at`
- `error_code`
- `error_message`

### E. 任务类型收口

第一版至少标准化这些任务：

- `manual_run`
- `scheduled_run`
- `rebuild_search_index`
- `rebuild_retrieval_index`

这些任务的 contract 必须明确：

- 输入参数
- scope
- artifact_uri
- result_payload

### F. 存储策略

建议行为：

- 若配置了 `TECH_BLOG_DATABASE_URL` 或 `TECH_BLOG_ASSET_DB_PATH`，优先写现有数据库
- 若两者都未配置，则回退到报告目录下的 `tech_blog_tasks.db` sidecar sqlite

要求：

- sidecar 路径稳定
- schema 能自动 bootstrap

### G. README 与运维说明

至少明确：

- 当前已标准化哪些任务
- `task_records` 稳定字段有哪些
- sidecar sqlite 回退行为是什么
- 当前 retry 语义是什么

## 推荐改动文件

建议新增或重点修改：

- `products/tech_blog_monitor/tasks/models.py`
- `products/tech_blog_monitor/tasks/runner.py`
- `products/tech_blog_monitor/tasks/__init__.py`
- `products/tech_blog_monitor/db/models.py`
- `products/tech_blog_monitor/db/repositories/task_repository.py`
- `products/tech_blog_monitor/db/schema_manager.py`
- `products/tech_blog_monitor/repository_provider.py`
- `products/tech_blog_monitor/agent.py`
- `products/tech_blog_monitor/local_scheduler.py`
- `products/tech_blog_monitor/README.md`
- `products/tech_blog_monitor/test/test_tasks.py`
- 必要时补：
  - `products/tech_blog_monitor/test/test_agent.py`
  - `products/tech_blog_monitor/test/test_ops.py`
  - `products/tech_blog_monitor/test/test_api.py`

## 分步计划

### Step 1：定义任务 contract

目标：

- 固定任务模型字段与幂等键规则

交付：

- `TaskRequest`
- `TaskRetryPolicy`
- `TaskExecutionRecord`
- `build_task_idempotency_key()`

完成标准：

- contract 可序列化、可测试
- 幂等键生成稳定

### Step 2：实现 `LocalTaskRunner`

目标：

- 给现有动作套上统一任务包装层

交付：

- `run()`
- `_execute_request()`
- `_create_task_record()`
- `_finish_task_record()`

完成标准：

- running -> succeeded / failed 状态完整
- 重放时 `retry_count` 行为清晰

### Step 3：接入 `manual_run` / `scheduled_run`

目标：

- 让核心 run 动作有正式任务记录

交付：

- `agent.py` / `local_scheduler.py` 接线
- `run_summary` 回写到任务结果

完成标准：

- `manual_run` / `scheduled_run` 都可落 task record
- result_payload 至少包含 `exit_code` 与 `run_summary`

### Step 4：接入 `rebuild_*` 运维任务

目标：

- 让最小“非 run 任务”也进入标准模型

交付：

- `rebuild_search_index`
- `rebuild_retrieval_index`

完成标准：

- 至少一种非 run 任务成功标准化
- 当前实际建议两种都接上

### Step 5：补测试与 README

目标：

- 让 `P2.3` 具备可回归和可运维说明

交付：

- task runner 单测
- CLI / scheduler 接线测试
- README 更新

完成标准：

- 无外部基础设施也能跑通测试

## 验收标准

`P2.3` 合入前至少满足：

- 已定义 `TaskRequest` / `TaskRetryPolicy` / `TaskExecutionRecord`
- 已实现稳定幂等键生成规则
- 已实现 `LocalTaskRunner`
- `manual_run` 与 `scheduled_run` 均有统一任务记录
- 至少一种非 run 任务已标准化，建议覆盖 `rebuild_search_index`
- `task_records` 至少包含稳定字段：`task_id`、`task_type`、`task_status`、`trigger_source`、`requested_by`、`idempotency_key`、`input_payload`、`result_payload`、`started_at`、`finished_at`、`retry_count`
- sidecar sqlite 回退路径可工作
- retry / 幂等 / 失败状态定义清晰

## 建议测试面

至少覆盖以下测试：

- 幂等键生成测试
- `manual_run` 持久化任务测试
- `scheduled_run` 任务类型与 trigger_source 测试
- `rebuild_search_index` / `rebuild_retrieval_index` 任务测试
- sidecar sqlite 回退测试
- failed task 状态记录测试
- retry_count 累加测试

建议最少复验命令：

- `uv run ruff check products/tech_blog_monitor`
- `uv run pytest -q products/tech_blog_monitor/test/test_tasks.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_agent.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_ops.py`
- `uv run pytest -q products/tech_blog_monitor/test`

## 非目标与风险提醒

这一轮最容易失控的点有三个：

- 把 `P2.3` 直接做成 queue / worker 系统
- 在任务层重写 `monitor.run()` 业务逻辑
- 过早把 article-level `reextract_content` / `reenrich_articles` 一起塞进来

如果出现这些倾向，应回到 `P2.3` 边界：

- `P2.3` 是任务模型与最小运维动作标准化
- 不是分布式任务平台
- 不是 scheduler / Prefect deployment 项目
- 不是 article-level 运维任务全面收口

## 结论

`P2.3` 最合理的落地顺序是：

- `task contract -> idempotency -> local task runner -> task_records -> manual/scheduled/rebuild_* 接线 -> 测试`

先把任务模型做稳，再进入 `P2.4` 的调度层重构与 Prefect 渐进接入。
