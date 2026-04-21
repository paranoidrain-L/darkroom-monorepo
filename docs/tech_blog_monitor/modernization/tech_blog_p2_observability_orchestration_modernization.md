# Tech Blog Modernization P2: Observability and Orchestration Plan

更新时间：`2026-04-20`

## 验收归档

截至 `2026-04-20`，modernization `P2` 可按“已全面完成并归档”处理。

当前验收结论：

- 已完成：`P2.1 ~ P2.5` 各子阶段能力已全部收口
- 已完成：本地优先的 `run / task / stage` 结构化观测骨架
- 已完成：`metrics registry`、`OTLP tracing bridge`、`none/jsonl/otlp` 导出模式与自动降级
- 已完成：`LocalTaskRunner`、`task_records`、`manual_run` / `scheduled_run` 统一任务记录
- 已完成：`local_scheduler.py`、`local|prefect` orchestration mode、渐进式 `Prefect` adapter
- 已完成：`ops summary` 聚合、`agent ops summary`、`GET /ops/summary`、最小运营 runbook 与 P2 regression suite

本地验证结果：

- `uv run ruff check products/tech_blog_monitor`
  通过
- `uv run pytest -q products/tech_blog_monitor/test/test_observability.py`
  `17 passed`
- `uv run pytest -q products/tech_blog_monitor/test/test_tasks.py`
  `9 passed`
- `uv run pytest -q products/tech_blog_monitor/test/test_prefect_adapter.py`
  `4 passed`
- `uv run pytest -q products/tech_blog_monitor/test/test_scheduler.py`
  `4 passed`
- `uv run pytest -q products/tech_blog_monitor/test/test_agent.py`
  `6 passed`
- `uv run pytest -q products/tech_blog_monitor/test/test_config.py`
  `42 passed`
- `uv run pytest -q products/tech_blog_monitor/test/test_ops.py products/tech_blog_monitor/test/test_api.py`
  通过
- `uv run pytest -q products/tech_blog_monitor/test`
  `273 passed, 1 skipped`

补充验收记录：

- 最小 API 冒烟已确认：仅配置 `TECH_BLOG_DATABASE_URL`、不配置 `TECH_BLOG_ASSET_DB_PATH` 时，`GET /ops/summary` 仍返回 `200`
- `P2.1 ~ P2.5` 已分别形成独立 plan / archive 文档，可作为后续回溯与回归基线

当前仍保留的非阻塞尾项：

- `ops summary` 目前仍依赖 `task_records.result_payload.run_summary`
- `reextract_content` / `reenrich_articles` 仍未细化到 article-level 独立任务模型
- `Prefect` 仍是渐进 adapter，尚未做真实 server / deployment lifecycle 联调

归档结论：

- `P2` 作为“运行底座现代化”阶段可以正式关闭
- 后续相关工作不再归入 `P2`，而应进入后续产品化 / Agent 化阶段
- `P2` 主文档保留为总归档，细分实现与验收证据见 `P2_1_PLAN.md` ~ `P2_5_PLAN.md`

## 目标

这份文档描述 modernization 路线中的 `P2`。

P2 的目标不是“换一个调度器”，而是把 `tech_blog_monitor` 从：

- 能跑
- 出问题主要靠日志排查
- 定时执行只有 APScheduler 本地触发

升级为：

- 单次运行可观测
- 失败原因可归因
- 重跑 / backfill / re-extract / re-enrich / reindex 有统一任务模型
- 调度与编排可以逐步从本地 scheduler 演进到正式 orchestration

一句话说，`P2` 要解决的是“如何稳定运营”，而不是“如何再加一个功能”。

## 立项前基线

在 P2 立项前，系统已经具备：

- CLI 单次执行入口
- APScheduler 驱动的本地定时服务
- `loguru` 文本日志
- feed 级健康状态
- 正文抓取状态与质量状态
- sqlite / PostgreSQL-ready 数据面
- JSON 报告与归档

立项前的主问题不是功能缺失，而是运行面仍偏薄：

- 没有统一的 `run trace / task trace / stage timing` 数据结构
- 失败主要体现在文本日志里，难以做稳定统计
- `serve --run-now` 和单次 `run` 共用主链路，但缺少正式任务记录
- backfill / re-extract / re-enrich / reindex 还没有统一入口
- 还没有“本地轻量模式”和“正式编排模式”的清晰分层

补充状态：

- `P2.1`：已落地本地结构化 run/task/stage 观测骨架与 JSONL observer
- `P2.2`：已落地 metrics registry、OTLP tracing bridge、OTLP metrics exporter、`none/jsonl/otlp` 导出模式与自动降级
- `P2.3`：已落地 `LocalTaskRunner`、`task_records`、`manual_run` / `scheduled_run` 统一任务记录，以及 `rebuild_search_index` / `rebuild_retrieval_index` 两个标准化运维任务
- `P2.4`：已落地 `local_scheduler.py`、`local/prefect` orchestration mode、`PrefectOrchestrationBackend` 渐进 adapter 与自动降级；正式平台级 deployment 生命周期管理仍在后续阶段
- `P2.5`：已落地 `ops summary` 聚合、最小 runbook、P2 regression suite 收口与 KPI 口径定义

## P2 不做的事

P2 不做：

- 不重写 P1 / P1.5 数据层与正文抽取主逻辑
- 不做前端
- 不做多租户权限系统
- 不直接引入复杂分布式 worker 集群
- 不把 `Prefect` 当作替代所有内部运行模型的“大爆炸迁移”

P2 也不应做：

- 只有 tracing SDK 接入，没有任务模型
- 只有 scheduler 替换，没有观测闭环
- 只有 dashboard 截图，没有回归测试和验收门槛

## 核心原则

### 1. 先定义运行语义，再接观测和编排工具

正确顺序应是：

1. 定义 `run / task / stage / outcome`
2. 定义内部事件与指标模型
3. 接入 trace / metrics 导出
4. 接入正式 orchestration

不要反过来先上 `OpenTelemetry` 或 `Prefect`，再临时拼语义。

### 2. 本地优先，平台兼容

P2 必须保留：

- 无外部基础设施时仍可本地运行
- 无 collector / 无 Prefect server 时仍可测试
- 所有关键行为都能通过 fixture / mock / sqlite 回归

也就是说：

- `Noop / file / local` 路径必须先存在
- `OTLP / Prefect` 只能是增强路径，不应成为唯一运行方式

### 3. 观测必须服务于排障与运营

P2 的观测不是为了“好看”，而是为了稳定回答：

- 这次 run 为什么失败
- 卡在 feed 抓取、正文提取、AI enrichment 还是 DB / delivery
- 哪个源经常失败
- 哪类任务最常超时
- 哪些重跑值得做，哪些没有价值

### 4. 编排必须建立在幂等任务之上

如果任务没有稳定输入、输出和 side-effect 边界，引入 orchestration 只会放大混乱。

因此 P2 必须先把以下动作建模为受控任务：

- run
- backfill
- re-extract content
- re-enrich
- rebuild index

## 推荐目标结构

P2 完成后，建议至少形成以下结构：

```text
products/tech_blog_monitor/
├── observability/
│   ├── __init__.py
│   ├── events.py
│   ├── metrics.py
│   ├── tracing.py
│   ├── sinks.py
│   └── context.py
├── tasks/
│   ├── __init__.py
│   ├── models.py
│   ├── runner.py
│   ├── backfill.py
│   ├── reextract.py
│   ├── reenrich.py
│   └── reindex.py
├── orchestration/
│   ├── __init__.py
│   ├── local_scheduler.py
│   └── prefect_adapter.py
└── ...
```

这不是要求一次性全部落地，而是给出演进方向：

- `observability/` 负责运行信号
- `tasks/` 负责任务语义
- `orchestration/` 负责调度接线

## 分阶段执行

## Phase 2.1：运行语义与本地观测骨架

### 目标

先把“这次运行发生了什么”变成结构化数据，而不是散落在日志里。

### 具体任务

1. 定义内部运行模型

至少定义：

- `RunContext`
- `StageEvent`
- `StageOutcome`
- `TaskContext`
- `TaskResult`

建议最小字段：

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

2. 增加本地 observer 抽象

建议实现：

- `NoopObserver`
- `InMemoryObserver`
- `JsonlObserver`

要求：

- 不依赖外部 collector
- 可被单元测试直接断言
- 支持后续桥接到 `OpenTelemetry`

3. 在主链路补最小阶段打点

优先覆盖：

- `fetch_feeds`
- `fetch_content`
- `analyze_articles`
- `write_report`
- `archive_assets`
- `mirror_database`
- `dispatch_deliveries`

4. 输出最小 run summary

建议产出：

- 本次 run 的 stage timing 汇总
- feed 成功 / 失败数
- 正文抓取状态分布
- enrichment 状态分布
- delivery 状态分布

### 建议改动范围

- `products/tech_blog_monitor/monitor.py`
- `products/tech_blog_monitor/fetcher.py`
- `products/tech_blog_monitor/content_fetcher.py`
- `products/tech_blog_monitor/analyzer.py`
- `products/tech_blog_monitor/delivery.py`
- 新增 `observability/`

### 验收

- 单次 run 结束后可得到结构化 run summary
- 不接外部系统也能保留本地 trace / event 文件
- 失败路径可以在结构化事件中被直接识别

## Phase 2.2：指标收口与 OpenTelemetry 接线

### 目标

在已有内部事件模型上接入 tracing / metrics 导出，而不是直接把业务逻辑绑死在某个 SDK 上。

### 具体任务

1. 建立 metrics registry

至少覆盖：

- `feed_fetch_total`
- `feed_fetch_failures_total`
- `content_fetch_total`
- `content_low_quality_total`
- `enrichment_failures_total`
- `delivery_failures_total`
- `search_latency_ms`
- `qa_latency_ms`

2. 建立 tracing bridge

建议策略：

- 内部仍以 `RunContext / StageEvent` 为真源
- `OpenTelemetry` 作为导出桥
- 默认允许 `OTEL` 关闭

3. 增加导出模式

建议支持：

- `none`
- `jsonl`
- `otlp`

4. 补 observability 文档和 smoke 验证

至少明确：

- 本地如何看事件文件
- collector 不存在时如何降级
- 哪些字段是稳定契约

### 风险控制

- 不要求本地开发默认起 collector
- 不要求所有测试依赖真实 exporter
- exporter 初始化失败时必须自动降级为本地 observer

### 验收

- 本地模式和 OTEL 模式都能跑通
- exporter 故障不会阻断主链路
- 指标命名、维度和 trace span 边界稳定

## Phase 2.3：任务模型与运维动作标准化

### 目标

把“运维动作”从临时脚本升级为正式任务。

### 任务类型建议

- `scheduled_run`
- `manual_run`
- `backfill_runs`
- `reextract_content`
- `reenrich_articles`
- `rebuild_search_index`
- `rebuild_retrieval_index`

### 具体任务

1. 定义任务输入 / 输出 contract

每类任务至少定义：

- 输入参数
- 幂等键
- 影响范围
- 产出 artifact
- 失败重试语义

2. 抽出 task runner

建议：

- 保留当前 `monitor.run()` 作为核心业务函数
- 新增 `TaskRunner` 负责包装任务上下文、观测和结果落库

3. 增加最小任务记录存储

建议字段：

- `task_id`
- `task_type`
- `task_status`
- `trigger_source`
- `requested_by`
- `input_payload`
- `result_payload`
- `started_at`
- `finished_at`

可选实现：

- Phase 2.3 先用 sqlite / PostgreSQL 现有数据库落表
- 不要求一开始就做复杂 queue

### 验收

- 至少 `manual_run` 和 `scheduled_run` 有统一任务记录
- 至少一种“非 run 任务”被标准化，例如 `reextract_content`
- 重试 / 幂等 / 失败状态有清晰定义

## Phase 2.4：调度层重构与 Prefect 渐进接入

### 目标

在已有任务模型基础上，把当前 APScheduler 本地定时能力升级为可扩展的 orchestration 入口。

### 为什么不直接替换

因为当前 `scheduler.py` 很轻，但它背后没有正式任务模型、运行记录和回填语义。

如果此时直接接 `Prefect`，得到的只是“换了个触发器”，不是可运营系统。

### 具体任务

1. 保留本地 scheduler

建议把当前 APScheduler 路径重命名为：

- `local_scheduler`

并把它改成触发 `TaskRunner`，而不是直接调用裸 `_job()`

2. 增加 Prefect adapter

建议只接第一批 flow：

- `scheduled_run`
- `backfill_runs`
- `reextract_content`

3. 明确双模式运行

至少区分：

- local mode
- prefect mode

要求：

- 本地开发默认 local
- 平台环境可切到 prefect
- 两条路径复用同一任务 contract

### 验收

- APScheduler 路径仍可用
- Prefect 路径可以触发至少一条正式任务
- 任务状态、日志和 run summary 不因 orchestration backend 不同而语义漂移

## Phase 2.5：运营收口与回归门禁

### 目标

让 P2 不是“代码接上了”，而是真的能用于长期运营。

### 具体任务

1. 增加 P2 回归集

至少覆盖：

- observer 关闭 / 本地 / otlp 三种模式
- exporter 初始化失败降级
- task runner 成功 / 失败 / 重试
- scheduler 触发任务记录
- Prefect adapter mock 集成

2. 补最小运营文档

至少包括：

- 本地调试方式
- 事件文件查看方式
- 常见失败路径
- 如何重跑正文 / enrichment / index

3. 建立最小验收看板定义

建议第一批核心运营指标：

- run success rate
- feed availability
- content extraction pass rate
- low_quality ratio
- enrichment failure rate
- delivery success rate
- mean run duration

### 验收

- 出问题时可根据结构化事件快速定位阶段
- 至少一条回填任务可重复执行且结果可追踪
- P2 不依赖人工翻日志才能判断系统是否健康

## 推荐实施顺序

建议按以下顺序推进：

1. `P2.1` 先做运行语义与本地 observer
2. `P2.2` 再接 `OpenTelemetry`
3. `P2.3` 抽任务模型
4. `P2.4` 最后接 `Prefect`
5. `P2.5` 做运营收口

不要采用以下顺序：

1. 先上 `Prefect`
2. 再补任务模型
3. 最后才补观测

这个顺序看起来快，实际上返工最大。

## Worker 拆分建议

如果要并行推进，建议这样拆：

- Worker A：`observability/` 抽象、事件模型、本地 observer
- Worker B：主链路阶段打点与 run summary 接线
- Worker C：task model / task runner / 任务记录表
- Worker D：APScheduler 重构与 Prefect adapter
- Worker E：回归测试、降级路径、运营文档

## 测试基线

P2 合入前，至少应运行：

```bash
uv run pytest -q products/tech_blog_monitor/test
uv run ruff check products/tech_blog_monitor
```

P2 新增测试建议至少包括：

- `test_observability.py`
- `test_task_runner.py`
- `test_scheduler.py`
- `test_prefect_adapter.py`

## 完成定义

满足以下条件，可认为 modernization `P2` 完成：

- 主链路已有结构化运行观测，而不只依赖文本日志
- run / task / stage 语义稳定
- 至少 `manual_run` 与 `scheduled_run` 有正式任务记录
- 至少一类运维动作被任务化，例如 `reextract_content`
- 本地 scheduler 与 Prefect path 共存且复用同一任务 contract
- exporter / orchestration backend 故障不会阻断主链路

## 给 Worker Agent 的一句话任务描述

在不破坏当前 CLI、scheduler 和主链路语义的前提下，为 `tech_blog_monitor` 增加本地优先的结构化观测、任务模型和渐进式 orchestration 接口，使系统具备可定位、可重跑、可运营的运行底座。
