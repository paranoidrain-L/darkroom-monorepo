# Tech Blog Modernization P1: Data and Retrieval Plan

更新时间：`2026-04-16`

## 当前状态

结论：

- modernization `P1` 主体已基本完成
- 当前实现已经具备 `Postgres-ready + repository-ready + Alembic-ready + FTS-ready + pgvector-compatible` 的数据与检索底座
- 在当前机器上，sqlite fallback、repository、Alembic、API、search、QA 回归均已通过
- 真实 PostgreSQL 集成路径已有专门测试，但本机未提供 PostgreSQL 实例，因此未完成本地实跑验收

本轮本地验收结果：

- `ruff check` 通过
- `pytest -q products/tech_blog_monitor/test` 通过：`198 passed, 1 skipped`
- sqlite URL 下的 `alembic upgrade head` / `downgrade base` 通过
- CLI 帮助入口正常
- FastAPI app 可导入，核心路由齐全

其中 `1 skipped` 为可选 PostgreSQL 集成测试，依赖：

- `TECH_BLOG_PG_TEST_URL`

## 当前落地结果

已落地的 P1 能力：

- 新增 `db/` 基础设施与 SQLAlchemy ORM models
- 新增 `repositories/` 分层
- 新增 `repository_provider.py`，统一路由 sqlite fallback / `database_url`
- 新增 Alembic 迁移基线
- search 已迁到 repository 层，并具备 PostgreSQL FTS 主路径
- API / insights / feedback / QA 已迁到 repository provider
- `TECH_BLOG_DATABASE_URL` 已接入配置层
- `monitor.py` 在不打断现有 `ArchiveStore.record_run(...)` 语义的前提下，支持把 sqlite 资产镜像同步到 `database_url`
- 已新增 sqlite/Alembic/PostgreSQL 集成测试

当前仍保留的过渡实现：

- `monitor.py` 的主写链路仍以 sqlite `ArchiveStore` 为起点
- PostgreSQL 写入当前通过 `mirror_sqlite_asset_db(...)` 同步，而不是完全原生 repository write path
- retrieval 的向量主路径已经接入 `pgvector` 兼容 schema 和 repository，但 embedding 仍基于 fake embedding，同步写入 `embedding_vector`
- 因此 P1 当前是“检索底座升级完成”，但还不是“真实 embedding 模型全面接管”的终态

这与本阶段的目标是一致的：先把数据与检索底座现代化，再决定是否在后续阶段切换真实 embedding provider。

## 说明

这份文档描述的是 **modernization 路线中的 `P1`**，不是历史文档里的 “Phase 1 sqlite 资产层设计”。

两者关系如下：

- 历史 `Phase 1`：已经完成，用 sqlite 建立最小可用资产层，见 [docs/tech_blog_monitor/phases/tech_blog_phase1_asset_design.md](../phases/tech_blog_phase1_asset_design.md)
- 现代化 `P1`：在当前 sqlite 基线上，把系统演进到 `Postgres-ready + repository-ready + retrieval-ready`

因此，这个 P1 的目标不是回头重做“资产层有没有”，而是升级：

- 数据底座
- schema 管理方式
- 查询抽象方式
- 搜索和 retrieval 能力上限

## 目标

P1 的目标是把当前：

- `sqlite`
- 单文件 `ArchiveStore`
- `LIKE` 型检索
- deterministic fake embedding

升级为：

- `PostgreSQL` 主路径 + sqlite fallback
- `SQLAlchemy 2` repository 分层
- `Alembic` 迁移脚本
- `PostgreSQL Full-Text Search`
- `pgvector` 兼容的向量检索路径

P1 完成后，系统应满足：

- API 和 CLI 不再被 sqlite 单文件实现强绑定
- 写路径和读路径可迁移到 PostgreSQL
- search / insights / QA 有统一的数据访问抽象
- 后续前端、多用户、重建索引、回填任务有稳定底座可依赖

当前实现对上述目标的达成情况：

- `PostgreSQL` 主路径：已具备
- sqlite fallback：已保留
- repository 分层：已具备主要读查询路径
- Alembic：已具备
- PostgreSQL FTS：已具备
- `pgvector` 兼容向量检索路径：已具备
- 原生 PostgreSQL 写路径全面替代 sqlite：尚未完成，属于后续收尾项

## 不在 P1 做的事

P1 不做：

- 不重写前端
- 不升级正文抽取器
- 不做权限系统或多租户
- 不做复杂任务编排
- 不做大规模 UI/产品交互设计
- 不要求一次性删除 sqlite
- 不要求一次性删除 `ArchiveStore`

P1 也不应做：

- 一步到位替换所有调用点
- 在同一批里同时做 P1.5 正文抽取升级
- 在没有检索回归基线时直接替换 retrieval 排序

## 当前基线

P0 完成后，当前系统基线如下：

- 配置层已拆分并支持 `pydantic-settings`
- 最小 FastAPI API 已存在，见 [products/tech_blog_monitor/api/app.py](../../../products/tech_blog_monitor/api/app.py)
- 当前 API 仍通过 sqlite 资产库读取数据，见 [products/tech_blog_monitor/api/deps.py](../../../products/tech_blog_monitor/api/deps.py)
- 当前查询仍直接依赖 `ArchiveStore`，见 [products/tech_blog_monitor/search.py](../../../products/tech_blog_monitor/search.py)
- 当前数据层核心仍为巨型 [products/tech_blog_monitor/archive_store.py](../../../products/tech_blog_monitor/archive_store.py)
- 当前 retrieval 仍使用 fake embedding，见 [products/tech_blog_monitor/retrieval.py](../../../products/tech_blog_monitor/retrieval.py)

当前主要技术限制：

- 只有 sqlite 主路径，缺少正式 DB backend 抽象
- 读写职责混在 `ArchiveStore`
- schema migration 仍由业务代码内嵌管理
- search 依赖 `LIKE` 和 JSON 字符串匹配
- retrieval 没有真实向量索引
- API 依赖 sqlite 文件路径，不适合服务化部署

## P1 总体原则

### 1. 先引入并行新路径，再迁移调用方

P1 不应直接把 `ArchiveStore` 整体替换成 PostgreSQL 版本，而应按下面顺序演进：

1. 新增 DB backend 抽象
2. 新增 PostgreSQL 实现
3. 让 search / insights / feedback / API 先走 repository 层
4. 再逐步迁移 run 写入
5. 最后把 sqlite 降为 fallback / compatibility path

### 2. 先做 repository 和 migration，再做 FTS / vector

如果底层 session、model、migration 没稳定，直接上 FTS / vector 会导致后面返工。

P1 的正确顺序应是：

1. DB 基础设施
2. repository 抽象
3. PostgreSQL 写入和查询
4. FTS
5. vector retrieval

### 3. 维持 API / CLI 契约稳定

P1 可以升级内部实现，但不应随意改动：

- `search.py` 的查询参数语义
- API 的 response 结构
- `monitor.py` 的主链路行为
- 现有 sqlite 兼容输入输出

### 4. 允许结果排序变化，但必须显式 rebaseline

FTS 和 vector 引入后，搜索和 retrieval 的排序结果几乎一定会变化。

这不是 bug，但必须：

- 明确记录
- 提供评测语料
- 更新 golden tests
- 重新定义“可接受变化”

## 目标结构

P1 完成后，建议至少形成如下结构：

```text
products/tech_blog_monitor/
├── archive_store.py              # 兼容层 / sqlite fallback
├── db/
│   ├── __init__.py
│   ├── engine.py
│   ├── models.py
│   ├── schema_manager.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── run_repository.py
│   │   ├── article_repository.py
│   │   ├── search_repository.py
│   │   ├── feedback_repository.py
│   │   ├── delivery_repository.py
│   │   └── retrieval_repository.py
│   └── backends/
│       ├── __init__.py
│       ├── sqlite_backend.py
│       └── postgres_backend.py
├── search.py
├── retrieval.py
├── qa.py
└── api/
    └── ...
```

Alembic 建议落地为：

```text
alembic.ini
alembic/
├── env.py
└── versions/
```

说明：

- `archive_store.py` 在 P1 内仍可保留，但应逐步退化为 compatibility wrapper
- `db/models.py` 统一承载 SQLAlchemy ORM model
- `repositories/` 承担读写职责，而不是继续把查询堆回 `ArchiveStore`

## 配置设计

P1 建议新增但保持最小的 DB 配置面：

- `TECH_BLOG_DATABASE_URL`
- 保留 `TECH_BLOG_ASSET_DB_PATH`

建议规则：

- 若配置了 `TECH_BLOG_DATABASE_URL`，优先使用 PostgreSQL 主路径
- 若未配置 `TECH_BLOG_DATABASE_URL`，继续走 sqlite fallback
- `TECH_BLOG_ASSET_DB_PATH` 继续作为本地开发和兼容路径

推荐不要在 P1 一开始就引入过多 DB 配置项。

最小可接受配置：

- `TECH_BLOG_DATABASE_URL=postgresql+psycopg://...`

若进入向量阶段，可再增加：

- `TECH_BLOG_EMBEDDING_PROVIDER`
- `TECH_BLOG_EMBEDDING_MODEL`

但这类 embedding 配置不应阻塞 P1 前半段的数据层落地。

## 建议依赖

P1 建议引入：

- `SQLAlchemy>=2`
- `Alembic`
- `psycopg[binary]`
- `pgvector`

可选：

- `sqlalchemy-utils`
- `tenacity`（如果要为 embedding/index build 增加重试）

注意：

- 不要在 P1 直接引入过重的搜索中间件
- PostgreSQL 已足够承接 FTS + vector 的第一版实现

## 分阶段执行方案

## Phase 1.1：DB 基础设施与 ORM 模型

### 目标

建立 PostgreSQL 可用的数据访问基础设施，但不立即切换所有调用方。

### 具体任务

1. 增加 SQLAlchemy 2 基础设施

新增：

- `db/engine.py`
- `db/models.py`
- `db/backends/postgres_backend.py`
- `db/backends/sqlite_backend.py`

要求：

- 支持从 `TECH_BLOG_DATABASE_URL` 构建 engine / session
- sqlite backend 继续可用
- Postgres 和 sqlite 至少在核心字段上共享同一套领域模型定义

2. 抽象 schema manager

新增：

- `db/schema_manager.py`

职责：

- 启动期 schema 检查
- 本地开发下的最小 bootstrap
- 与 Alembic 的协作入口

3. 迁移 `runs / articles / run_articles / article_contents / article_enrichments / article_chunks / feedback / deliveries`

要求：

- 先完成现有实体在 SQLAlchemy 中的映射
- 保持现有主键语义和关键唯一约束不变
- 不在这一阶段修改业务字段语义

### 涉及文件

- 新增 `products/tech_blog_monitor/db/...`
- 更新 [pyproject.toml](../../../pyproject.toml)
- 更新 [products/tech_blog_monitor/settings.py](../../../products/tech_blog_monitor/settings.py)
- 更新 [products/tech_blog_monitor/config.py](../../../products/tech_blog_monitor/config.py)

### 验收

- 能创建 sqlite / postgres engine
- SQLAlchemy model 与当前核心 schema 对齐
- 新测试可在 sqlite in-memory 或临时 DB 上通过

## Phase 1.2：Alembic 迁移体系

### 目标

把 schema 演进从 `ArchiveStore` 内嵌版本迁移逻辑，迁到显式 migration 脚本。

### 具体任务

1. 新增 Alembic 基础结构

新增：

- `alembic.ini`
- `alembic/env.py`
- `alembic/versions/*`

2. 生成初始迁移

要求：

- 以当前 SQLAlchemy model 为基线生成初始 migration
- Postgres 作为主路径
- sqlite 保持最小兼容测试，不要求所有高级索引特性等价

3. 分离 backfill 和 schema migration

要求：

- chunk backfill、历史 payload ingest 等数据修复逻辑，不继续藏在 schema init 里
- 如必须保留回填，单独提供显式 backfill 命令或函数入口

### 替换点

- 减少 `ArchiveStore` 中对 schema version 的主导职责
- 新 schema 升级以 Alembic 为准

### 验收

- 新环境可通过 Alembic 初始化
- 现有测试能覆盖至少一次迁移到最新版本
- 迁移失败时有明确错误而不是静默 fallback

## Phase 1.3：Repository 分层与读路径迁移

### 目标

先把 search / API / insights / feedback 的读取和写入，从 `ArchiveStore` 迁到 repository 层。

### 具体任务

1. 拆分 repository

新增：

- `run_repository.py`
- `article_repository.py`
- `search_repository.py`
- `feedback_repository.py`
- `delivery_repository.py`
- `retrieval_repository.py`

建议职责：

- `run_repository`
  run 列表、run detail、run articles
- `article_repository`
  article detail、article list、按 URL/ID 查询
- `search_repository`
  search query 与 filter 组装
- `feedback_repository`
  add/list feedback
- `delivery_repository`
  delivery create/list/update
- `retrieval_repository`
  chunk candidate select、vector query

2. 引入 DB 访问 facade

建议新增统一入口，例如：

- `storage_router.py`
- `repository_provider.py`

职责：

- 根据配置决定使用 postgres 还是 sqlite backend
- 给 API、search、insights、QA 提供统一 repository provider

3. 迁移现有调用点

优先迁移：

- [products/tech_blog_monitor/api/deps.py](../../../products/tech_blog_monitor/api/deps.py)
- [products/tech_blog_monitor/search.py](../../../products/tech_blog_monitor/search.py)
- `insights.py`
- `feedback.py`

暂时不要求立即迁移：

- `monitor.py` 全量写路径

### 验收

- API 不再强绑定 `ArchiveStore`
- search / insights / feedback 能通过 repository 层工作
- sqlite fallback 仍可跑通

## Phase 1.4：PostgreSQL Full-Text Search

### 目标

把当前 `LIKE` 查询升级为可用的全文搜索。

### 具体任务

1. 在 PostgreSQL 中建立搜索向量

建议字段：

- `title`
- `rss_summary`
- `ai_summary`
- `clean_text`
- `topic`
- `tags`

建议：

- `title`、`topic` 权重更高
- `clean_text` 权重次之
- `tags`、`summary` 作为补充信号

2. 新增 FTS 索引

要求：

- 使用 `GIN` + `tsvector`
- 支持 `websearch_to_tsquery`
- 支持来源、分类、时间窗 filter

3. 保持查询契约不变

`SearchQuery` 结构尽量不变：

- `query`
- `source_name`
- `category`
- `topic`
- `tag`
- `days`
- `limit`

但底层实现从 sqlite `LIKE` 换为 PostgreSQL FTS。

### 测试要求

- 固定 golden corpus
- 查询集 rebaseline
- 至少验证：
  - 标题命中优先
  - topic / tags 有 boost
  - 时间过滤有效
  - 空查询 + filter 有效

### 验收

- PostgreSQL search 结果可重复
- 与旧 `LIKE` 路径相比，召回和排序有明确提升或至少不退化到不可用
- sqlite fallback 路径仍可保留旧实现

## Phase 1.5：Vector Retrieval

### 目标

用真实向量检索替换 deterministic fake embedding，但尽量不改上层 QA 契约。

### 具体任务

1. 保留现有 chunk 结构

不要在 P1 里重写 chunk 粒度逻辑。

重点是替换：

- chunk embedding 生成方式
- chunk 检索方式

2. 引入 `pgvector`

要求：

- chunk 表支持 vector 列
- 支持 nearest neighbor 查询
- 保留基础 metadata filter

3. 保持 mixed retrieval

推荐策略：

- lexical / FTS candidate select
- vector recall
- 统一 rerank

P1 不必追求复杂 reranker，但要保证：

- citation 还能稳定回溯
- QA 还保持保守回答策略

4. 兼容现有 QA

优先保持：

- `qa.py` 接口语义
- 无证据拒答
- citation URL 仍来自检索命中 chunk

### 测试要求

- embedding 存储与读取测试
- retrieval ranking 测试
- citation consistency
- 无证据拒答
- 向量缺失 / 回填未完成时的降级路径

### 验收

- retrieval 有真实向量主路径
- QA 不因底层替换而失去稳定性
- sqlite fallback 至少还能保留 fake embedding 测试路径

## 写路径迁移策略

P1 的高风险点不在读路径，而在写路径。

建议写路径分两步：

### Step A

保留当前 `monitor.py -> ArchiveStore.record_run(...)` 主路径不变，同时让新 repository 层先承担读查询。

### Step B

当 Postgres schema、repositories、API、search 都稳定后，再把：

- `record_run`
- article upsert
- chunk upsert
- feedback / delivery write

逐步迁到 repository 层。

要求：

- 不要一上来就把 `monitor.py` 全改掉
- 每迁一段，先补兼容测试

## Worker 拆分建议

如果拆多个 Worker，建议按下面切：

### Worker A：DB 基础设施

负责范围：

- `db/engine.py`
- `db/models.py`
- `db/backends/*`
- `settings.py` 中 DB 相关配置
- `pyproject.toml` 新依赖

禁止修改：

- search 排序逻辑
- QA 生成逻辑

### Worker B：Alembic 与 schema

负责范围：

- `alembic.ini`
- `alembic/env.py`
- `alembic/versions/*`
- `schema_manager.py`

禁止修改：

- API 路由契约
- retrieval 逻辑

### Worker C：Repository 与 API 读路径

负责范围：

- repositories
- `api/deps.py`
- `search.py`
- `insights.py`
- `feedback.py`

禁止修改：

- `monitor.py` 主写链路大重构

### Worker D：FTS 与 Retrieval

负责范围：

- `search_repository.py`
- `retrieval_repository.py`
- `retrieval.py`
- `qa.py`
- 对应回归测试

禁止修改：

- 前端或无关功能

### 集成人员

负责范围：

- 合并 DB backend / repository / API 三类改动
- 执行 rebaseline
- 更新 README 和 phase 文档

## 测试与回归门禁

P1 合入前至少满足：

- sqlite fallback 测试通过
- PostgreSQL 主路径测试通过
- Alembic migration 测试通过
- search regression tests 通过
- retrieval / QA regression tests 通过
- 现有 API 契约测试继续通过

最低测试矩阵建议：

1. sqlite compatibility

- 旧 `ArchiveStore` 兼容测试
- 旧 asset payload ingest
- 旧 state import

2. postgres repository

- session/engine init
- repository CRUD
- migration up/down

3. search

- FTS rank
- filter correctness
- golden corpus rebaseline

4. retrieval / QA

- vector retrieval
- citation consistency
- no-evidence refusal

## 建议命令

最终命令以实现时为准，但 P1 至少应支持类似下面的工作流：

```bash
uv run pytest -q products/tech_blog_monitor/test
uv run alembic upgrade head
uv run alembic downgrade -1
uv run ruff check products/tech_blog_monitor
```

如有 PostgreSQL 本地容器，建议补充：

```bash
docker compose up -d postgres
TECH_BLOG_DATABASE_URL=postgresql+psycopg://... uv run pytest -q products/tech_blog_monitor/test
```

## 明确不允许的做法

P1 不应出现以下做法：

- 把 `ArchiveStore` 整体删除后再重做
- 没有 migration 就直接手写生产 schema
- 没有评测基线就直接改 search / retrieval 排序
- 在 P1 顺手把正文抽取一起重做
- 在没有 sqlite fallback 的情况下强制所有开发者本地依赖 PostgreSQL

## 完成定义

满足以下条件，可认为 modernization P1 完成：

- PostgreSQL 主路径已存在且可用
- repository 层已承接主要查询职责
- Alembic 已成为 schema 演进主路径
- search 已具备 PostgreSQL FTS 主路径
- retrieval 已具备 pgvector 兼容主路径
- sqlite 保留为本地 fallback / compatibility path
- API / CLI 对外契约没有被无序破坏

## 本轮验收判断

按上述完成定义评估：

- 已满足：PostgreSQL 主路径、repository 层、Alembic、FTS、pgvector 兼容路径、sqlite fallback、API/CLI 契约稳定
- 未完全闭合的部分：`monitor.py` 仍未完全切到原生 PostgreSQL write path；真实 PostgreSQL 集成测试在当前机器上没有实库验证

因此，本阶段判断为：

- `P1 基本完成，可进入下一阶段或后续收尾`

建议作为 P1 收尾项保留两件事：

1. 在 CI 或本地容器环境中执行一次真实 PostgreSQL 集成回归
2. 评估是否需要在下一阶段把 `mirror_sqlite_asset_db(...)` 继续演进为原生 repository write path

## 给 Worker Agent 的一句话任务描述

在不打断当前 CLI/API 契约和 sqlite 兼容路径的前提下，把 `tech_blog_monitor` 从 sqlite + `ArchiveStore` + `LIKE`/fake embedding，演进为 PostgreSQL + SQLAlchemy repository + Alembic + FTS + pgvector 的渐进式数据与检索底座。
