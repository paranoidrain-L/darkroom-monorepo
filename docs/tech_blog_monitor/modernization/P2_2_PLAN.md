# P2.2 Metrics And OpenTelemetry Bridge Plan

更新时间：`2026-04-22`

## 执行状态

截至 `2026-04-22`，modernization `P2.2` 可视为已完成并通过验收。

当前结论：

- 建议合入
- 未发现阻塞性问题
- 本文同时作为 `P2.2` 的执行计划与验收归档

## 一句话目标

在 `P2.1` 的运行语义和本地 observer 骨架之上，补齐：

- metrics registry
- tracing bridge
- `none / jsonl / otlp` 导出模式
- exporter 初始化失败时的自动降级

第一版必须做到：

- 内部语义仍以 `RunContext / StageEvent / TaskResult` 为真源
- `OpenTelemetry` 只是桥接导出层，不反向绑死业务逻辑
- 无 collector / 无 OTLP endpoint 时系统仍可本地运行

## 验收归档

本轮验收确认，`P2.2` 的核心边界已经满足：

- 已实现 `MetricPoint`、`MetricsRegistry`、`MetricsBridge`、`OpenTelemetryMetricsBridge`
- 已实现 `TracingBridge`、`OpenTelemetryTracingBridge`、`TracingObserver`
- 已实现 `none / jsonl / otlp` 三种导出模式与 OTLP helper
- metrics / tracing 仍桥接在 `P2.1` 的内部事件模型之上，没有把业务逻辑绑死到 OTLP SDK
- exporter 初始化失败、emit 失败、flush / close 失败均保持 fail-open，不阻断主链路

实现与覆盖证据如下：

- `observability/__init__.py` 已明确导出 `P2.2` 级 metrics / tracing 组件
- `observability/metrics.py` 已收口稳定 counters / histograms、registry snapshot、metrics bridge 和默认 registry 配置逻辑
- `observability/tracing.py` 已定义 stage span / task span 生命周期与 run finished flush / shutdown 语义
- `observability/otlp.py` 已提供 OTLP endpoint 解析与 HTTP session helper
- `README.md` 已明确 `none / jsonl / otlp` 配置、稳定指标、稳定 span 边界和降级行为
- `test_observability.py` 已覆盖：
  - metrics registry snapshot
  - metrics bridge fail-open
  - tracing bridge 生命周期
  - OTLP init 失败降级
  - default registry 替换 / 重建
  - OTLP endpoint resolver

本轮复验结果归档如下：

- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check products/tech_blog_monitor` 通过
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_observability.py`：`17 passed`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_search.py products/tech_blog_monitor/test/test_qa.py products/tech_blog_monitor/test/test_insights.py`：`30 passed`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test`：`268 passed, 1 skipped`

按当前测试证据，可认为以下验收口径已经满足：

- 已定义并实现稳定的 metrics registry
- 已定义 tracing bridge，内部事件仍为真源
- 已支持 `none / jsonl / otlp`
- exporter 初始化失败 / emit 失败 / close 失败均不会阻断主链路
- 已覆盖 `feed_fetch_total`、`feed_fetch_failures_total`、`content_fetch_total`、`content_low_quality_total`、`enrichment_failures_total`、`delivery_failures_total`
- 已覆盖 `search_latency_ms`、`qa_latency_ms`、`insights_latency_ms`
- README 已说明配置方式、稳定契约和降级行为

剩余非阻塞尾项：

- 当前 OTLP 路径已具备桥接能力，但仍以本地优先为主，未进入外部 collector / dashboard 运营层
- 指标和 span 口径已经收口为第一版稳定契约，后续新增指标仍应克制推进
- `P2.2` 之后的任务化、scheduler 和 orchestration 仍属于 `P2.3+`

## 背景

`P2.1` 已经解决了“这次 run 发生了什么”这个问题，但还没有解决另一个问题：

- 这些结构化事件如何形成稳定的指标与 trace 信号

如果没有 `P2.2`，系统仍然只能：

- 看 JSONL
- 看本地 summary
- 手工判断运行情况

而不能稳定回答：

- 哪类失败在持续升高
- QA / search / insights 的延迟是否恶化
- OTLP collector 存在时，如何把内部语义桥接到标准 tracing / metrics 通道

因此 `P2.2` 的任务不是“接一个 SDK”，而是定义：

- 哪些指标是稳定契约
- tracing 如何从内部事件桥接出去
- exporter 故障时如何 fail-open

## 范围

本阶段包含：

- 定义 metrics registry
- 定义 metrics bridge
- 定义 tracing bridge
- 接入 `none / jsonl / otlp` 导出模式
- OTLP endpoint 解析与 HTTP session 封装
- exporter 初始化 / emit / flush / close 自动降级
- README / 配置说明与最小 smoke 验证

本阶段不包含：

- 任务记录落库
- `LocalTaskRunner`
- `task_records`
- `local_scheduler.py`
- `Prefect` orchestration
- dashboard / 前端 / 外部告警系统

这些属于 `P2.3+` 或更后续阶段。

## 设计原则

### 1. 内部事件优先，OTLP 只是桥

`P2.2` 里真正稳定的契约是：

- `StageOutcome`
- `TaskResult`
- run summary

而不是某个 OTLP SDK 的对象模型。

### 2. 本地优先，远端增强

必须保留：

- `none`
- `jsonl`

`otlp` 只能是增强路径，不能成为系统唯一运行模式。

### 3. exporter 故障不能阻断主链路

必须覆盖：

- import 失败
- endpoint 无效
- collector 不可达
- flush / close 报错

这些都应该降级为：

- warning
- 本地 registry / observer 继续工作

### 4. 指标名与维度要克制

第一版不追求大而全。

只保留确实稳定、可解释、和当前主链路直接相关的指标。

## 目标产物

`P2.2` 第一版交付物应包括：

- `MetricPoint`
- `MetricsRegistry`
- `MetricsBridge`
- `OpenTelemetryMetricsBridge`
- `TracingBridge`
- `OpenTelemetryTracingBridge`
- `MetricsObserver`
- `TracingObserver`
- OTLP endpoint resolver / HTTP session helper
- `none / jsonl / otlp` 导出模式说明
- 回归测试与最小 smoke 测试

## 建议实现方案

### A. Metrics Registry

建议放入：

- `products/tech_blog_monitor/observability/metrics.py`

建议收口的 counters：

- `feed_fetch_total`
- `feed_fetch_failures_total`
- `content_fetch_total`
- `content_low_quality_total`
- `enrichment_failures_total`
- `delivery_failures_total`

建议收口的 histograms：

- `run_duration_ms`
- `stage_duration_ms`
- `search_latency_ms`
- `qa_latency_ms`
- `insights_latency_ms`

要求：

- 本地可 snapshot
- 可作为默认 registry
- bridge emit 失败时不抛出到主链路

### B. Metrics Bridge

建议放入：

- `products/tech_blog_monitor/observability/metrics.py`

建议结构：

- `MetricsBridge`
- `NoopMetricsBridge`
- `OpenTelemetryMetricsBridge`

要求：

- 默认 `Noop`
- `OpenTelemetryMetricsBridge` 只负责把 `MetricPoint` 桥接到 OTLP HTTP exporter
- `flush / close` 必须可单独测试

### C. Tracing Bridge

建议放入：

- `products/tech_blog_monitor/observability/tracing.py`

建议结构：

- `TracingBridge`
- `NoopTracingBridge`
- `OpenTelemetryTracingBridge`
- `TracingObserver`

要求：

- `StageEvent(started)` 打开 span
- `StageOutcome` 结束 span
- `TaskResult` 单独形成 task span
- run finished 时尝试 flush / shutdown

### D. OTLP Helper

建议放入：

- `products/tech_blog_monitor/observability/otlp.py`

至少负责：

- `build_otlp_http_session()`
- `resolve_otlp_endpoint()`

要求：

- 支持 base endpoint 自动补全到 `/v1/metrics` 或 `/v1/traces`
- 已给 signal-specific endpoint 时也能稳定解析
- HTTP session 配置应偏保守，避免阻塞主链路

### E. 导出模式与配置

建议配置面：

- `TECH_BLOG_OBSERVABILITY_EXPORTER`
- `TECH_BLOG_OBSERVABILITY_JSONL`
- `TECH_BLOG_OTLP_ENDPOINT`

支持模式：

- `none`
- `jsonl`
- `otlp`

建议行为：

- `none`：只保留内存 / 本地 registry，不做外部导出
- `jsonl`：输出本地 JSONL
- `otlp`：尝试启用 metrics + tracing bridge；初始化失败自动降级

### F. 主链路接线

建议保持：

- `RunContext` 仍是唯一运行真源
- `monitor.py` 内只通过 `_build_observer()` / 默认 registry 配置接 OTLP

不要在业务逻辑里直接操作 OTLP span / metric SDK。

### G. README 与 Smoke

至少说明：

- `jsonl` 模式怎么用
- `otlp` 模式怎么配
- collector 不存在时会怎样降级
- 哪些指标和 span 名称是当前稳定契约

## 推荐改动文件

建议新增或重点修改：

- `products/tech_blog_monitor/observability/metrics.py`
- `products/tech_blog_monitor/observability/tracing.py`
- `products/tech_blog_monitor/observability/otlp.py`
- `products/tech_blog_monitor/observability/__init__.py`
- `products/tech_blog_monitor/monitor.py`
- `products/tech_blog_monitor/defaults.py`
- `products/tech_blog_monitor/settings.py`
- `products/tech_blog_monitor/config.py`
- `products/tech_blog_monitor/config_loader.py`
- `products/tech_blog_monitor/config_validator.py`
- `products/tech_blog_monitor/README.md`
- `products/tech_blog_monitor/test/test_observability.py`
- `products/tech_blog_monitor/test/test_search.py`
- `products/tech_blog_monitor/test/test_qa.py`
- `products/tech_blog_monitor/test/test_insights.py`

## 分步计划

### Step 1：收口指标契约

目标：

- 固定第一版 counters / histograms 名称与维度口径

交付：

- `MetricPoint`
- `MetricsRegistry`
- snapshot 接口

完成标准：

- 本地测试可断言 counters / histograms
- 指标名不依赖外部 SDK

### Step 2：实现 metrics bridge

目标：

- 把 registry 内部 point 桥接到 OTLP metrics exporter

交付：

- `MetricsBridge`
- `NoopMetricsBridge`
- `OpenTelemetryMetricsBridge`

完成标准：

- bridge emit / flush / close 报错不会阻断主链路

### Step 3：实现 tracing bridge

目标：

- 把 `StageEvent / StageOutcome / TaskResult` 桥接为 trace span

交付：

- `TracingBridge`
- `NoopTracingBridge`
- `OpenTelemetryTracingBridge`
- `TracingObserver`

完成标准：

- stage span 生命周期正确
- task span 可独立输出

### Step 4：接入导出模式与自动降级

目标：

- 让 `none / jsonl / otlp` 三种模式都能本地稳定运行

交付：

- 配置接线
- OTLP helper
- `_build_observer()` / 默认 registry 配置逻辑

完成标准：

- `otlp` 初始化失败会 warning 并降级
- 不影响单次 run 成功与失败语义

### Step 5：补测试与 README

目标：

- 让 `P2.2` 从“能接 SDK”变成“可持续守门”

交付：

- observability 单测
- search / qa / insights latency 指标测试
- README 更新

完成标准：

- 无真实 collector 也能跑完整回归

## 验收标准

`P2.2` 合入前至少满足：

- 已定义并实现稳定的 metrics registry
- 已定义 tracing bridge，内部事件仍为真源
- 支持 `none / jsonl / otlp` 三种模式
- exporter 初始化失败 / emit 失败 / close 失败均不会阻断主链路
- 至少覆盖 `feed_fetch_total`、`feed_fetch_failures_total`、`content_fetch_total`、`content_low_quality_total`、`enrichment_failures_total`、`delivery_failures_total`
- 至少覆盖 `search_latency_ms`、`qa_latency_ms`、`insights_latency_ms`
- README 明确配置方法与降级行为

## 建议测试面

至少覆盖以下测试：

- registry snapshot 测试
- OTLP endpoint resolver 测试
- metrics bridge fail-open 测试
- tracing bridge 生命周期测试
- exporter 模式切换测试
- search / qa / insights latency 指标测试
- collector 缺失或 bridge 初始化失败时的降级测试

建议最少复验命令：

- `uv run ruff check products/tech_blog_monitor`
- `uv run pytest -q products/tech_blog_monitor/test/test_observability.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_search.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_qa.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_insights.py`
- `uv run pytest -q products/tech_blog_monitor/test`

## 非目标与风险提醒

这一轮最容易失控的点有三个：

- 直接把业务代码绑进 OTLP SDK
- 为了“全观测”一次性加很多不稳定指标
- 让 collector / exporter 成为默认运行前提

如果出现这些倾向，应回到 `P2.2` 边界：

- `P2.2` 是 metrics / tracing bridge
- 不是任务系统
- 不是 scheduler / orchestration
- 不是 dashboard 项目

## 结论

`P2.2` 最合理的落地顺序是：

- `指标契约 -> registry -> metrics bridge -> tracing bridge -> exporter mode -> fail-open 测试`

先把内部运行语义稳定桥接出去，再进入 `P2.3` 的任务模型与运维动作标准化。
