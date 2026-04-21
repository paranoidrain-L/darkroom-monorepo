# P2.1 Run Semantics And Local Observability Plan

更新时间：`2026-04-21`

## 执行状态

截至 `2026-04-21`，modernization `P2.1` 可视为已完成并通过验收。

当前结论：

- 建议合入
- 未发现阻塞性问题
- 本文同时作为 `P2.1` 的执行计划与验收归档

## 一句话目标

把“这次 run 发生了什么”从零散日志，提升为：

- 有统一运行语义
- 有本地可断言的结构化事件
- 有最小 run summary

第一版必须做到：

- 无外部基础设施也能运行
- 单元测试能直接验证
- 不改变主业务链路语义

## 验收归档

本轮验收确认，`P2.1` 的核心边界已经满足：

- 已定义 `RunContext` / `TaskContext` / `StageEvent` / `StageOutcome` / `TaskResult` 这一组运行语义
- 已提供 `NoopObserver` / `InMemoryObserver` / `JsonlObserver` 本地 observer 抽象
- 主链路已覆盖 `fetch_feeds`、`fetch_content`、`analyze_articles`、`write_report`、`archive_assets`、`mirror_database`、`dispatch_deliveries` 阶段打点
- run 结束后已能产出最小 `run summary`，包含 `stage_timings`、`feed_stats` 与各状态分布
- 观测层保持 fail-open，observer 失败不会拖垮主链路

实现与覆盖证据如下：

- `observability/__init__.py` 已明确导出 `P2.1` 级运行语义与 observer
- `monitor.py` 已构建 `stage_timings` / `feed_stats` / 状态分布，并在主链路接入阶段上下文
- `test_observability.py` 已覆盖：
  - 运行模型字段
  - package export 边界
  - `JsonlObserver` 记录写出
  - failed / skipped stage
  - run summary 结构
  - observer 失败时的 fail-open 语义
- `README.md` 已补充 `P2` 运行观测与阶段覆盖说明

本轮复验结果归档如下：

- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check products/tech_blog_monitor` 通过
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_observability.py`：`9 passed`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_monitor.py`：`21 passed`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test`：`260 passed, 1 skipped`

按当前测试证据，可认为以下验收口径已经满足：

- 已定义结构化 `run / task / stage` 运行模型
- 已提供 `NoopObserver`、`InMemoryObserver`、`JsonlObserver`
- 主链路最小阶段打点已落地
- run 结束后可输出稳定 `run summary`
- 失败路径可定位到 stage 级
- 不依赖 OTLP / Prefect / 外部 collector
- 未看到对既有业务主流程语义的回归

剩余非阻塞尾项：

- 当前仍是本地优先观测骨架，还未进入 `P2.2` 的 metrics / tracing bridge 范围
- `P2.1` 的 summary 结果后续仍可继续与 `task_records` / `ops summary` 做更深层复用
- 现阶段阶段覆盖已经足够作为骨架，但 article-level 运维任务与更强编排仍属于 `P2.3+`

## 背景

在 `P2.1` 之前，`tech_blog_monitor` 已经能跑，但运行面存在几个问题：

- run 失败主要靠文本日志排查
- 没有统一的 `run / task / stage` 语义模型
- 很难稳定回答“这次失败卡在抓取、正文、AI、落库还是 delivery”
- 无法直接为后续 metrics / tracing / task / orchestration 打底

因此 `P2.1` 不是“接一个 tracing SDK”，而是先把运行语义定义清楚。

## 范围

本阶段包含：

- 定义运行事件与结果模型
- 定义本地 observer 抽象
- 在主链路增加阶段化打点
- 生成最小 run summary
- 增加本地可回归测试

本阶段不包含：

- OTLP metrics / tracing exporter
- `task_records`
- `LocalTaskRunner`
- `local_scheduler.py`
- `Prefect` adapter
- dashboard / 前端

这些属于 `P2.2+` 或后续子阶段。

## 设计原则

### 1. 先语义，后工具

`P2.1` 的核心是：

- `RunContext`
- `StageEvent`
- `StageOutcome`
- `TaskContext`
- `TaskResult`

没有这些内部语义，后续再接 metrics / tracing / orchestration 只会变成工具先行。

### 2. 本地优先

第一版必须支持：

- `NoopObserver`
- `InMemoryObserver`
- `JsonlObserver`

不能把外部 collector 当作唯一运行方式。

### 3. 不改变主链路业务语义

`P2.1` 只补运行语义和观测，不改：

- feed 抓取逻辑
- 正文抽取算法
- AI enrichment 语义
- search / retrieval / API 数据面

### 4. summary 必须直接服务排障

最小 run summary 至少要回答：

- 哪些 stage 成功 / 失败 / 跳过
- 每个 stage 花了多久
- feed 成功 / 失败数
- content / enrichment / delivery 的状态分布

## 目标产物

`P2.1` 第一版交付物应包括：

- 统一运行模型
- 本地 observer 抽象与实现
- 主链路阶段化打点
- 最小 run summary
- 回归测试

## 建议实现方案

### A. 运行模型

建议放入：

- `products/tech_blog_monitor/observability/events.py`

至少定义：

- `StageEvent`
- `StageOutcome`
- `TaskResult`

建议字段：

- `run_id`
- `task_id`
- `task_type`
- `stage_name`
- `started_at`
- `finished_at`
- `duration_ms`
- `status`
- `error_code`
- `error_message`
- `dimensions`

### B. RunContext / TaskContext

建议放入：

- `products/tech_blog_monitor/observability/context.py`

要求：

- 提供 `with run_context.stage("...")` 这类最小阶段上下文
- 自动记录开始、结束、耗时、状态
- 允许记录 skipped stage
- 允许 run 结束时统一输出 summary

### C. Observer 抽象

建议放入：

- `products/tech_blog_monitor/observability/sinks.py`

第一版建议实现：

- `NoopObserver`
- `InMemoryObserver`
- `JsonlObserver`

要求：

- `NoopObserver` 允许最小开销运行
- `InMemoryObserver` 便于单元测试断言
- `JsonlObserver` 便于本地排障与回放

### D. 主链路阶段打点

建议最先覆盖：

- `fetch_feeds`
- `fetch_content`
- `analyze_articles`
- `write_report`
- `archive_assets`
- `mirror_database`
- `dispatch_deliveries`

建议接线文件：

- `products/tech_blog_monitor/monitor.py`
- 必要时少量补到 `fetcher.py`
- 必要时少量补到 `content_fetcher.py`
- 必要时少量补到 `analyzer.py`
- 必要时少量补到 `delivery.py`

### E. 最小 run summary

建议包含：

- `stage_timings`
- `feed_stats`
- `content_status_counts`
- `enrichment_status_counts`
- `delivery_status_counts`

要求：

- 结构化 JSON 兼容
- 可被任务层或后续 `ops summary` 复用
- 不依赖外部 metrics 系统

## 推荐改动文件

建议新增：

- `products/tech_blog_monitor/observability/__init__.py`
- `products/tech_blog_monitor/observability/events.py`
- `products/tech_blog_monitor/observability/context.py`
- `products/tech_blog_monitor/observability/sinks.py`
- `products/tech_blog_monitor/test/test_observability.py`

建议修改：

- `products/tech_blog_monitor/monitor.py`
- `products/tech_blog_monitor/fetcher.py`
- `products/tech_blog_monitor/content_fetcher.py`
- `products/tech_blog_monitor/analyzer.py`
- `products/tech_blog_monitor/delivery.py`
- `products/tech_blog_monitor/README.md`

如果现有仓库已经把这些模块进一步拆分，可在不改变边界的前提下调整落点。

## 分步计划

### Step 1：定义运行事件模型

目标：

- 固定 `run / stage / task` 的结构化语义

交付：

- 事件 dataclass
- outcome dataclass
- 最小字段与序列化能力

完成标准：

- 测试可以直接断言字段结构
- 不依赖真实 collector

### Step 2：实现 observer 抽象

目标：

- 提供本地可运行、可测试的观测落点

交付：

- `NoopObserver`
- `InMemoryObserver`
- `JsonlObserver`

完成标准：

- `InMemoryObserver` 能用于测试断言
- `JsonlObserver` 能产出稳定 JSONL

### Step 3：在主链路补阶段化打点

目标：

- 让一次运行的关键阶段可观测

交付：

- `monitor.py` 阶段上下文接线
- skipped / failed / success 的状态记录

完成标准：

- 至少覆盖 6 个核心 stage
- 失败能定位到具体 stage

### Step 4：输出最小 run summary

目标：

- 给后续 task / ops / debugging 提供统一摘要

交付：

- `stage_timings`
- `feed_stats`
- 状态分布统计

完成标准：

- run 结束后可拿到稳定 summary 结构
- 不要求引入外部 metrics backend

### Step 5：补测试与 README

目标：

- 让 `P2.1` 具备可持续回归能力

交付：

- observability 单测
- monitor 集成测试
- README 最小说明

完成标准：

- 无需外部基础设施即可跑通回归

## 验收标准

`P2.1` 合入前至少满足：

- 已定义结构化 `run / task / stage` 运行模型
- 已提供 `NoopObserver`、`InMemoryObserver`、`JsonlObserver`
- 主链路至少覆盖 `fetch_feeds`、`fetch_content`、`analyze_articles`、`write_report`、`archive_assets`、`dispatch_deliveries`
- run 结束后能产出最小 `run summary`
- 失败路径可定位到 stage 级
- 不依赖 OTLP / Prefect / 外部服务
- 不改变既有业务主流程语义

## 建议测试面

至少覆盖以下测试：

- event / outcome 模型测试
- observer 行为测试
- JSONL 输出测试
- monitor 阶段打点测试
- failed / skipped stage 测试
- run summary 结构测试

建议最少复验命令：

- `uv run ruff check products/tech_blog_monitor`
- `uv run pytest -q products/tech_blog_monitor/test/test_observability.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_monitor.py`
- `uv run pytest -q products/tech_blog_monitor/test`

## 非目标与风险提醒

这一轮最容易失控的点有三个：

- 直接把 `P2.1` 做成 metrics / tracing 接入项目
- 只接日志或 tracing，不定义内部运行语义
- 在观测改造里顺手改业务主链路

如果出现这些倾向，应回到 `P2.1` 边界：

- `P2.1` 是运行语义与本地观测骨架
- 不是完整 observability 平台
- 不是 orchestration 项目
- 不是任务系统全量实现

## 结论

`P2.1` 最合理的落地顺序是：

- `run/task/stage 模型 -> observer 抽象 -> monitor 阶段接线 -> run summary -> 回归测试`

先把本地可运行、可回归、可排障的骨架搭好，再进入 `P2.2` 的 metrics / tracing bridge 与更完整的运行底座演进。
