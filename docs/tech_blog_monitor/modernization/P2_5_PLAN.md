# P2.5 Operational Readiness And Regression Gate Plan

更新时间：`2026-04-20`

## 执行状态

截至 `2026-04-20`，这是一份对 modernization `P2.5` 的补充执行计划文档。

说明：

- `P2.5` 的目标不是继续扩功能，而是把 `P2.1 ~ P2.4` 已有能力收口为可运营底座
- 这份文档用于给 Worker / Tester 提供单独的实施与验收基线
- 本文只覆盖运营收口、回归门禁与 KPI 契约，不重开新的 orchestration 或任务模型需求

## 一句话目标

把当前已经落地的 observability / task / scheduler / ops API 收束为：

- 有稳定回归集
- 有最小 runbook
- 有统一的运营 KPI 口径
- 有 CLI / API 两条最小运维入口

第一版必须做到：

- 出问题时不需要只靠翻文本日志定位
- 运营人员可以通过 `agent ops summary` 或 `GET /ops/summary` 获得最小健康视图
- `P2` 的关键降级路径和回归门禁可被稳定复验

## 背景

在 `P2.4` 之后，系统已经具备：

- `run / task / stage` 结构化观测骨架
- `none / jsonl / otlp` observability exporter
- `LocalTaskRunner` 与 `task_records`
- `local / prefect` orchestration backend
- `agent ops summary` 与 `GET /ops/summary`

但距离“可长期运营”还差最后一层收口：

- 需要固定一组最小回归集，覆盖核心成功路径和降级路径
- 需要固定一份最小 runbook，告诉使用者如何定位与重跑
- 需要固定一组 KPI 口径，避免 CLI / API / 文档对同一指标解释不一致

如果不做 `P2.5`，系统虽然已经能跑、能观测、能调度，但运营面仍然偏散，后续迭代也缺少统一门禁。

## 范围

本阶段包含：

- 收口 `ops.py` 的最小 KPI 聚合契约
- 收口 `agent ops summary` 与 `GET /ops/summary` 的一致性
- 补齐最小运营 runbook
- 收口 P2 regression suite
- 补充 README 中的运营与降级说明
- 明确当前已支持的排障 / 重跑方式

本阶段不包含：

- 新的 observability exporter
- 新的 orchestration backend
- `Prefect` deployment lifecycle
- article-level `reextract_content` / `reenrich_articles` 正式任务化
- dashboard、告警系统、前端运维面板
- 完整 SLO / alert routing 平台建设

这些属于后续产品化 / Agent 化阶段，或更后续阶段。

## 设计原则

### 1. 先固定最小可运营面，再谈更重的平台能力

`P2.5` 不是大而全运营平台。

第一版只要求回答这些问题：

- 最近运行是否健康
- 失败主要出在哪一层
- 本地如何复现一次 run
- 当前有哪些重跑入口

### 2. KPI 必须来自已有稳定数据面

第一版 KPI 只应依赖：

- `task_records`
- `result_payload.run_summary`
- 已有 `run_summary` 里的结构化计数

不要在 `P2.5` 引入新的复杂聚合存储。

### 3. CLI / API / 文档口径必须一致

以下三处必须说同一件事：

- `ops.py`
- `agent ops summary` / `GET /ops/summary`
- README / runbook

如果口径不一致，运营指标就不可信。

### 4. 回归门禁优先覆盖降级路径

`P2.5` 最重要的不是“正常路径又多过几条测试”，而是这些路径必须守住：

- exporter 初始化失败降级
- task runner 成功 / 失败 / 重试
- scheduler 触发任务记录
- `prefect` adapter mock 提交与 fallback

## 目标产物

`P2.5` 第一版交付物应包括：

- `OperationalSummary` / `OperationalKPI` 稳定聚合契约
- `agent ops summary` CLI
- `GET /ops/summary` API
- 最小 runbook
- README 运营章节
- P2 regression suite 文档化与回归命令

## 建议实现方案

### A. Ops Summary Contract

建议收口：

- `products/tech_blog_monitor/ops.py`

要求：

- 固定 `OperationalKPI`、`FailureSample`、`OperationalSummary`
- `to_dict()` 输出字段稳定
- KPI 名称与单位稳定
- 对空窗口、零分母、布尔 / 非 int 噪声值有防御性处理

第一版稳定 KPI：

- `run_success_rate`
- `feed_availability`
- `content_extraction_pass_rate`
- `low_quality_ratio`
- `enrichment_failure_rate`
- `delivery_success_rate`
- `mean_run_duration_ms`

### B. CLI / API 接线

建议收口：

- `products/tech_blog_monitor/agent.py`
- `products/tech_blog_monitor/api/app.py`
- 必要时补 `products/tech_blog_monitor/api/schemas.py`

要求：

- `agent ops summary` 与 `GET /ops/summary` 复用同一聚合逻辑
- `limit` 参数语义一致
- 仅配置 `TECH_BLOG_DATABASE_URL` 时也可工作
- 不把 ops summary 错绑到 sqlite path

### C. Regression Suite

建议覆盖：

- `products/tech_blog_monitor/test/test_observability.py`
- `products/tech_blog_monitor/test/test_tasks.py`
- `products/tech_blog_monitor/test/test_scheduler.py`
- `products/tech_blog_monitor/test/test_prefect_adapter.py`
- `products/tech_blog_monitor/test/test_ops.py`
- `products/tech_blog_monitor/test/test_api.py`
- `products/tech_blog_monitor/test/test_agent.py`

要求：

- 至少能证明 `P2.1 ~ P2.4` 的关键能力仍可工作
- 至少有一条 ops API smoke
- 至少有一条 CLI ops summary 测试

### D. Runbook And README

建议收口：

- `docs/tech_blog_monitor/operations/tech_blog_monitor_operations_runbook.md`
- `products/tech_blog_monitor/README.md`

至少明确：

- 本地单次运行
- JSONL 事件文件查看
- 常见失败路径
- 当前可用的重跑方式
- `ops summary` 指标口径
- 当前未覆盖项，例如 article-level 重抽与正式 `Prefect` lifecycle

## 推荐改动文件

建议新增或重点修改：

- `products/tech_blog_monitor/ops.py`
- `products/tech_blog_monitor/agent.py`
- `products/tech_blog_monitor/api/app.py`
- `products/tech_blog_monitor/api/schemas.py`
- `products/tech_blog_monitor/README.md`
- `docs/tech_blog_monitor/operations/tech_blog_monitor_operations_runbook.md`
- `products/tech_blog_monitor/test/test_ops.py`
- `products/tech_blog_monitor/test/test_api.py`
- `products/tech_blog_monitor/test/test_agent.py`
- 作为 P2 regression gate 明确引用：
  - `products/tech_blog_monitor/test/test_observability.py`
  - `products/tech_blog_monitor/test/test_tasks.py`
  - `products/tech_blog_monitor/test/test_scheduler.py`
  - `products/tech_blog_monitor/test/test_prefect_adapter.py`

## 分步计划

### Step 1：固定 ops summary 契约

目标：

- 收口最小 KPI 聚合与返回结构

交付：

- `OperationalSummary`
- `OperationalKPI`
- `FailureSample`
- `build_operational_summary()`

完成标准：

- 空窗口、零分母、失败样本、均值计算行为稳定

### Step 2：收口 CLI / API 运营入口

目标：

- 让 CLI / API 能稳定复用同一 ops 聚合逻辑

交付：

- `agent ops summary`
- `GET /ops/summary`

完成标准：

- CLI / API 输出字段一致
- 仅配置 `database_url` 时仍可工作

### Step 3：补最小 runbook 与 README

目标：

- 让排障、查看事件、最小重跑方式有统一说明

交付：

- runbook
- README 的运营章节 / orchestration 降级说明 / KPI 口径

完成标准：

- 至少能覆盖本地调试、事件查看、常见失败、重建索引、已知边界

### Step 4：收口 P2 regression suite

目标：

- 把 `P2.1 ~ P2.4` 的核心路径固化成回归门禁

交付：

- regression tests
- 推荐复验命令

完成标准：

- 核心成功路径与降级路径都有回归覆盖

## 验收标准

`P2.5` 合入前至少满足：

- 已定义稳定的 `OperationalSummary` / `OperationalKPI` 契约
- `agent ops summary` 与 `GET /ops/summary` 已接入且口径一致
- 已覆盖最小 KPI：
  - `run_success_rate`
  - `feed_availability`
  - `content_extraction_pass_rate`
  - `low_quality_ratio`
  - `enrichment_failure_rate`
  - `delivery_success_rate`
  - `mean_run_duration_ms`
- README / runbook 已明确本地调试、事件查看、常见失败、重跑方式和已知边界
- P2 regression suite 已覆盖 observability、task runner、scheduler、prefect adapter、ops summary
- 至少确认一条 API smoke：仅配置 `TECH_BLOG_DATABASE_URL` 时 `GET /ops/summary` 返回成功

## 建议测试面

至少覆盖以下测试：

- `build_operational_summary()` 聚合 KPI 测试
- ops summary 空窗口 / 零分母测试
- recent failures 排序与截断测试
- `GET /ops/summary` API 测试
- `agent ops summary` CLI 测试
- observability exporter fail-open 测试
- task runner 成功 / 失败 / 重试测试
- scheduler 触发任务记录测试
- prefect adapter mock / fallback 测试

建议最少复验命令：

- `uv run ruff check products/tech_blog_monitor`
- `uv run pytest -q products/tech_blog_monitor/test/test_ops.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_api.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_agent.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_observability.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_tasks.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_scheduler.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_prefect_adapter.py`
- `uv run pytest -q products/tech_blog_monitor/test`

## 非目标与风险提醒

这一轮最容易失控的点有三个：

- 把 `P2.5` 做成 dashboard / 告警平台项目
- 为了做 KPI 再引入新的复杂聚合存储
- 把 article-level 运维任务化或 `Prefect` lifecycle 一起塞进来

如果出现这些倾向，应回到 `P2.5` 边界：

- `P2.5` 是运营收口与回归门禁
- 不是新的平台能力扩张
- 不是新的 orchestration 项目
- 不是新的数据层重构

## 结论

`P2.5` 最合理的落地顺序是：

- `ops contract -> CLI/API 接线 -> runbook/README -> regression gate`

先把最小可运营面做稳，再进入后续更高层的产品化或平台化工作。
