# Tech Monitor Modernization Plan

## 执行状态

截至 `2026-04-20`，当前阶段状态可概括为：

- `P0`：已完成
- `P1`：主体已基本完成
- `P1.5`：已完成
- `P2`：已完成
- modernization 主线：在 `P2` 收口

当前对 `P1` 的判断：

- 已落地：`SQLAlchemy 2` 基础设施、repository 分层、Alembic 基线、PostgreSQL FTS 主路径、`pgvector` 兼容向量路径、sqlite fallback
- 当前仍属于渐进式过渡态：`monitor.py` 写路径仍先写 sqlite，再镜像同步到 `TECH_BLOG_DATABASE_URL`
- 当前机器未提供 PostgreSQL 实例，因此真实 PostgreSQL 集成回归未在本机实跑；代码库内已补可选集成测试

当前对 `P1.5` 的判断：

- 已落地：`Trafilatura` 主抽取器、heuristic fallback、受控 `Playwright` fallback、正文质量门禁
- `content_status` 在保留原有字段结构的前提下，增加了 `empty` / `low_quality` 可观测状态
- `monitor.py`、配置层、README 与回归测试已完成接线
- 当前剩余的是收口项，不影响将 `P1.5` 视为已完成：
  新环境变量 env contract 测试、真实浏览器 smoke test、质量阈值 rebaseline

当前对 `P2` 的判断：

- 已全面落地：本地优先的 `run / task / stage` 结构化观测骨架、metrics registry、OTLP tracing/metrics bridge、`task_records`、`LocalTaskRunner`、`local_scheduler.py`、`local|prefect` orchestration mode、`ops summary`、最小 runbook 与 P2 regression gate
- CLI、API 与现有数据面已接线：`agent ops summary`、`GET /ops/summary`
- `P2.1 ~ P2.5` 已形成独立 plan / archive 文档，P2 主文档已按“全面完成并归档”收口
- 本地验收已通过：`ruff check products/tech_blog_monitor`、`test_observability.py`、`test_tasks.py`、`test_prefect_adapter.py`、`test_scheduler.py`、`test_agent.py`、`test_config.py`、全量 `products/tech_blog_monitor/test`
- 当前剩余的是非阻塞尾项，不影响将 `P2` 视为已全面完成：
  `ops summary` 仍依赖 `task_records.result_payload.run_summary`、article-level `reextract_content` / `reenrich_articles` 尚未独立任务化、`Prefect` 尚未完成真实 deployment lifecycle 联调

## 目标

这份文档用于整理 `tech_blog_monitor` 的现代化升级路径。

目标不是“全面重写”，而是在保留当前可用能力的前提下，逐步把系统从：

- `CLI + sqlite + 启发式正文抽取 + fake retrieval`

升级为：

- `API-first + Postgres-ready + retrieval-ready + extraction-ready`

同时明确一条原则：

- modernization 主线不包含传统浏览器前端
- 先升级运行底座、数据底座和检索底座
- 后续产品化访问面应优先复用 `API / CLI / Agent interface`

## 当前状态

`tech_blog_monitor` 当前已经具备以下基线能力：

- 多 RSS 源并发抓取
- feed 级配置
- 增量状态与归档
- Markdown / JSON 输出
- sqlite 历史资产存储
- 启发式正文抓取
- 单篇文章结构化 enrichment
- 基础 search / QA / insights
- 最小可用 delivery / feedback
- `P0` 现代化底座：`uv` / `Ruff` / `pydantic-settings` / 最小 FastAPI API
- `P1` 数据与检索底座：`SQLAlchemy repository` / `Alembic` / PostgreSQL-ready search / pgvector-compatible retrieval
- `P1.5` 正文抽取底座：`Trafilatura` 主路径 / heuristic fallback / 受控 `Playwright` fallback / 质量门禁
- `P2` 运行底座：结构化 observability / task runner / task records / local scheduler / 渐进式 prefect adapter / ops summary

当前主要结构性和能力性限制：

- `ArchiveStore` 仍保留较多兼容职责
- `monitor.py` 的写路径仍未完全切到原生 PostgreSQL repository write path
- 正文抽取已完成主路径升级，但仍缺少更强的站点级规则与质量阈值 rebaseline
- retrieval 仍使用 fake embedding，只是已经具备 pgvector-compatible 底座
- 运行观测已具备本地 run/task/stage 结构化骨架、metrics registry、OTLP tracing/metrics bridge，并已落地 `task_records` / `LocalTaskRunner` / `manual_run` / `scheduled_run` / `rebuild_*_index` / `local_scheduler.py` / `local|prefect` orchestration mode / `ops summary` / 最小运营 runbook 基线，但尚未接入完整平台级 orchestration lifecycle
- 当前仍缺少更稳定的产品化访问面与 Agent 化入口

## 总体原则

### 1. 先底座，后产品化入口

优先级应当是：

1. 开发与依赖管理
2. 配置与服务化接口
3. 数据层升级
4. 正文抽取与检索质量升级
5. 观测与编排
6. 产品化访问面与 Agent 接口

### 2. 先替换底座，再扩访问面

如果在 API、数据模型、检索模型尚不稳定时过早做重交互访问面，后续返工概率很高。

因此后续产品化访问面应当建立在以下条件基本成立后再推进：

- 查询接口稳定
- run / article / search / insights / feedback 模型稳定
- 正文抽取质量可接受
- 检索质量达到产品可用线

### 3. 逐层替换，不做大爆炸迁移

每一阶段都应遵循：

- 先新增一层能力
- 再逐步迁移调用方
- 最后移除旧实现

避免一次性替换所有运行链路。

## 分阶段方案

## P0：开发底座与最小服务化

### 目标

在不改变核心业务语义的情况下，先把开发环境、配置层和接口层现代化。

### 建议引入

- `uv`
- `Ruff`
- `pydantic-settings`
- `FastAPI`

### 具体工作

#### 1. 使用 `uv` 管理依赖与环境

目标：

- 统一依赖安装方式
- 降低环境漂移
- 为后续拆服务和加前端提供统一工作流

建议动作：

- 增加 `pyproject.toml`
- 用 `uv` 管理依赖和虚拟环境
- 保留对现有 `requirements.txt` 的兼容过渡

#### 2. 使用 `Ruff` 统一 lint / format

目标：

- 控制风格漂移
- 降低多模块扩展后的维护噪音

建议动作：

- 增加 `ruff` 配置
- 统一 import 排序、基础 lint、基础 format
- 暂不做过强规则，先保证项目可平滑接入

#### 3. 使用 `pydantic-settings` 重构配置层

目标：

- 拆解当前过重的 `config.py`
- 让环境变量、默认值、YAML 配置、校验逻辑分层清晰

建议拆分：

- `defaults.py`
- `feed_catalog.py`
- `config_loader.py`
- `config_validator.py`
- `settings.py`

建议结果：

- `TechBlogMonitorSettings`
- 独立的 feed catalog
- 更清晰的配置来源优先级

#### 4. 使用 `FastAPI` 补最小 API 层

目标：

- 不重写当前 pipeline
- 先把已有能力包装成 HTTP 接口

第一批接口建议：

- `GET /health`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /articles`
- `GET /articles/{article_id}`
- `GET /search`
- `GET /insights`
- `POST /feedback`

可选但不建议立刻做的接口：

- `POST /run`
- `POST /qa`

原因：

- 写接口和异步任务触发接口更容易牵动运行模型
- 应在读接口稳定后再引入

### 替换点

- 替换手工配置解析为 settings model
- 增加 API 层，但保留 CLI
- 暂不替换 sqlite 与主 pipeline

### 风险

- 配置兼容性回归
- CLI 与 API 同时存在时，可能出现配置语义不一致

### 预期收益

- 降低配置层复杂度
- 为前端和外部集成提供稳定入口
- 为后续数据层升级打基础

## P1：数据层和检索层升级

### 目标

把当前 sqlite + 巨型 `ArchiveStore` 演进为更正式的数据底座，并提升搜索和 RAG 的可用性。

### 建议引入

- `PostgreSQL`
- `SQLAlchemy 2`
- `Alembic`
- `PostgreSQL Full-Text Search`
- `pgvector`

### 具体工作

#### 1. 从 sqlite 迁向 PostgreSQL

目标：

- 提升并发、查询和演进能力
- 让数据层更适合 API 和后续产品化

建议策略：

- 第一阶段保留 sqlite 作为本地 fallback
- 新增 PostgreSQL repository 实现
- 逐步迁移查询接口与 run 写入

#### 2. 用 SQLAlchemy 2 重构 repository

目标：

- 替代当前的 God object 型 `ArchiveStore`
- 让查询和写入职责分层

建议拆分：

- `schema_manager.py`
- `run_repository.py`
- `article_repository.py`
- `search_repository.py`
- `feedback_repository.py`
- `delivery_repository.py`

#### 3. 用 Alembic 管理 migration

目标：

- 替代当前内嵌在代码中的 schema version 迁移逻辑
- 让 schema 升级更显式、更可审计

建议：

- 迁移脚本版本化
- 明确 upgrade / downgrade 策略
- 将数据 backfill 从 schema 初始化代码中分离

#### 4. 用 PostgreSQL Full-Text Search 提升搜索

目标：

- 替代当前主要基于 `LIKE` 的全文检索
- 让标题、正文、摘要、topic、tags 检索更可控

建议：

- title / summary / clean_text 建搜索向量
- topic / tags 提供 boost
- 支持 `websearch_to_tsquery` 一类的自然搜索语法

#### 5. 用 `pgvector` 替换 fake embedding

目标：

- 让 retrieval / QA / mixed retrieval 进入真实可用状态

建议：

- 先保持当前 chunk 结构
- 用真实 embedding 替换 deterministic fake embedding
- 先做检索层兼容，不急着重写上层 QA

### 替换点

- 从 `ArchiveStore` 逐步迁移到 repositories
- 从 sqlite-only 查询迁移到 PostgreSQL 查询
- 从 fake retrieval 迁移到真实向量检索

### 风险

- 数据迁移复杂度上升
- 旧测试用例依赖 sqlite 语义
- search / retrieval 排序结果会与旧基线发生变化

### 预期收益

- 数据层不再被单文件卡死
- search / QA / insights 的质量上限明显提高
- 为前端和多用户场景提供更稳的数据基础

## P1.5：正文抽取能力升级

### 当前状态

截至 `2026-04-16`，`P1.5` 已完成并通过本地验收。

本地验收结果：

- `test_content_fetcher.py`：`12 passed`
- `products/tech_blog_monitor/test`：`203 passed, 1 skipped`
- `ruff check products/tech_blog_monitor`：通过

剩余非阻塞尾项：

- 新配置项 env contract 测试
- 安装浏览器二进制后的真实 `Playwright` smoke test
- 基于真实站点样本的质量阈值 rebaseline

### 目标

提升单篇文章的正文质量，因为这会直接影响 enrichment、search、QA、insights。

### 建议引入

- `Trafilatura`
- `Playwright` 作为 fallback

### 具体工作

#### 1. 用 `Trafilatura` 作为主抽取器

目标：

- 替代当前纯启发式正则方案
- 提升正文完整度与稳定性

建议策略：

- 主路径先尝试 `Trafilatura`
- 当前启发式逻辑作为 fallback

#### 2. 用 `Playwright` 处理 JS-heavy 页面

目标：

- 解决客户端渲染页面或复杂站点抽取失败问题

建议策略：

- 默认不用浏览器
- 仅当普通请求失败或正文为空时进入浏览器 fallback
- 严格限制超时和并发

### 替换点

- 替换正文抽取主路径
- 保留原有状态字段，避免上层逻辑大改

### 风险

- 浏览器依赖会增加运行复杂度
- 正文提取结果变化可能影响现有评测基线

### 预期收益

- 正文质量提升
- enrichment 更稳定
- search / QA 的证据质量提升

## P2：观测与任务编排

执行规划文档见：

- [docs/tech_blog_monitor/modernization/tech_blog_p2_observability_orchestration_modernization.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/docs/tech_blog_monitor/modernization/tech_blog_p2_observability_orchestration_modernization.md)

### 当前状态

截至 `2026-04-17`，`P2` 已完成并通过本地验收。

本地验收结果：

- `uv run ruff check products/tech_blog_monitor`：通过
- `uv run pytest -q products/tech_blog_monitor/test/test_ops.py products/tech_blog_monitor/test/test_api.py products/tech_blog_monitor/test/test_agent.py`：`16 passed`
- `uv run pytest -q products/tech_blog_monitor/test`：`240 passed, 1 skipped`

补充冒烟结果：

- 仅配置 `TECH_BLOG_DATABASE_URL` 时，`GET /ops/summary` 仍返回 `200`

剩余非阻塞尾项：

- `ops summary` 仍依赖 `task_records.result_payload.run_summary`
- article-level `reextract_content` / `reenrich_articles` 尚未独立任务化
- `Prefect` 仍是渐进 adapter，未完成真实 server / deployment lifecycle 联调

### 目标

让系统从“能跑”进入“可观测、可恢复、可持续运营”状态。

### 建议引入

- `OpenTelemetry`
- `Prefect`

### 具体工作

#### 1. 用 OpenTelemetry 建运行观测

建议打点：

- 单次 run trace
- feed 抓取 span
- 正文抽取 span
- AI enrichment span
- DB 查询 span
- delivery span
- search / insights API latency

建议指标：

- feed 成功率
- 正文抽取成功率
- enrichment 失败率
- delivery 成功率
- search latency
- QA latency

#### 2. 用 Prefect 管理调度与重跑

适合接管的任务：

- 定时 run
- backfill
- 重新抽取正文
- 重新 enrichment
- 重建索引

### 替换点

- 从简单 scheduler 演进到正式任务编排
- 从纯日志诊断演进到 trace + metrics

### 风险

- 运维复杂度上升
- 本地开发链路需要更明确的轻量模式

### 预期收益

- 运行问题更容易定位
- 大规模重跑和回填更可控
- 更适合长期产品化运营

## Modernization 主线收口说明

`tech_blog_monitor` 的 modernization 主线在 `P2` 收口。

这意味着：

- `P0 ~ P2` 负责把系统从脚本集合升级为现代化、可观测、可运营的后端底座
- 传统浏览器前端不再作为 modernization 主线阶段单独规划
- 后续工作改由产品化 roadmap 和 Agent roadmap 单独承接

后续仍可能推进的方向包括：

- 更稳定的产品化访问面
- 更强的内部操作面
- 面向技术情报场景的 Agent 接口

但这些不再记作 modernization `P3`。

## 阶段优先级总表

| 阶段 | 主要目标 | 建议工具 | 优先级 |
|---|---|---|---|
| `P0` | 开发底座、配置层、最小 API | `uv` / `Ruff` / `pydantic-settings` / `FastAPI` | 最高 |
| `P1` | 数据层、migration、搜索与检索升级 | `PostgreSQL` / `SQLAlchemy 2` / `Alembic` / `FTS` / `pgvector` | 高 |
| `P1.5` | 正文抽取升级 | `Trafilatura` / `Playwright` | 高 |
| `P2` | 观测与编排 | `OpenTelemetry` / `Prefect` | 中 |

## 如果只做三件事

如果当前资源有限，只建议优先做下面三件事：

1. `uv + Ruff`
2. `pydantic-settings`
3. `FastAPI + 最小 API`

原因：

- 风险最低
- 不会强行改写主链路
- 能立即让系统从“脚本集合”向“可服务化系统”过渡

## 不建议现在做的事

以下工作不建议立刻做：

- 单独启动传统浏览器前端项目
- 一次性重写所有数据层
- 同时替换正文、检索、数据库、API 与访问面
- 先做复杂多租户权限体系

原因：

- 当前最大收益不在这些地方
- 它们会显著增加改造耦合度
- 会让回归和问题定位变得困难

## 一句话结论

`tech_blog_monitor` 的现代化升级重点，不是做传统浏览器前端，而是先把它升级为：

**一个 API-first、Postgres-ready、retrieval-ready、extraction-ready 的系统。**
