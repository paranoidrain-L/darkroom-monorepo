# Tech Blog Monitor

`tech_blog_monitor` 是一个面向技术博客与高信噪比技术更新源的聚合器。它负责抓取、过滤、去重、抽取正文、生成结构化理解，并输出 Markdown / JSON / API / 检索与运营数据。

它当前不是一个重交互前端应用，而是一套已经具备持续运行能力的后端型内容管线，重点在：

- RSS 与非 RSS source 聚合与健康状态
- 正文抽取与质量判断
- enrichment / stack relevance / search / QA / insights
- sqlite / PostgreSQL-ready 数据面
- 本地优先的 observability / task / orchestration 底座

## 一眼看懂

当前主链路可以概括为：

`RSS -> 抓取过滤 -> 增量判断 -> 正文提取 -> AI enrichment -> stack relevance -> Markdown/JSON 输出 -> 资产落库 -> search / QA / insights / delivery / feedback / ops`

当前阶段已经完成：

- `P0`：开发底座与最小 API
- `P1`：数据与检索底座现代化
- `P1.5`：正文抽取现代化
- `P2`：运行观测、任务模型与渐进式 orchestration

当前明确还没做完：

- 更强的站点级正文抽取规则
- 更复杂的 retrieval / RAG 排序质量
- Prefect 正式编排主路径与平台级 deployment lifecycle
- 更成熟的操作面与产品化访问入口

## 快速开始

如果你是第一次从公开仓体验这个产品，先看：

- [docs/tech_blog_monitor/quickstart.md](../../docs/tech_blog_monitor/quickstart.md)

推荐使用 `uv`：

```bash
uv sync --group dev
```

最小可运行命令：

```bash
uv run python -m products.tech_blog_monitor.agent --help
uv run pytest -q products/tech_blog_monitor/test
uv run ruff check products/tech_blog_monitor
```

单次执行：

```bash
PYTHONPATH=. python -m products.tech_blog_monitor.agent
```

指定输出路径：

```bash
PYTHONPATH=. python -m products.tech_blog_monitor.agent --output report.md
```

启动定时服务并立刻跑一次：

```bash
PYTHONPATH=. python -m products.tech_blog_monitor.agent serve --run-now
```

启动最小 API：

```bash
uv run uvicorn products.tech_blog_monitor.api.app:app --host 127.0.0.1 --port 8000
```

如果当前环境尚未安装 `uv`，仍可兼容使用：

```bash
pip install -r requirements.txt
PYTHONPATH=. python -m products.tech_blog_monitor.agent --help
pytest -q products/tech_blog_monitor/test
```

## 当前能力边界

已落地能力：

- 多 source 并发抓取
- feed 级 `timeout` / `verify_ssl` / `headers` / `enabled` 配置
- `rss` / `github_releases` / `changelog` adapter
- 重试退避与 feed 健康状态统计
- URL 去重、时效过滤、关键词过滤、全局排序
- 增量状态记录与新增文章视图
- Markdown / JSON 输出
- 历史归档（`day` / `week`）
- sqlite 历史资产存储
- PostgreSQL-ready repository / Alembic / FTS / pgvector 位点
- `Trafilatura` 主路径 + heuristic fallback + 受控 `Playwright` fallback
- 正文质量判断与 `empty` / `low_quality` 状态
- Stack Relevance: stack profile + repo manifest 扫描 + 规则型相关性评分
- Phase 3 enrichment
- Phase 4 search API / CLI
- Phase 5 QA / retrieval 基线
- Phase 6 insights
- Phase 7 delivery / feedback
- P2 observability / task / local scheduler / prefect adapter / ops summary

当前明确未做：

- 更强的站点级正文规则库
- 更复杂的 retrieval / ranking / evaluation
- article-level `reextract_content` / `reenrich_articles` 独立任务化
- 更强的 delivery 闭环与异步 worker 化
- Prefect server / deployment lifecycle 联调

## 运行数据流图

```mermaid
flowchart TD
    A[RSS / Releases / Changelog] --> B[fetch_all<br/>抓取/重试/去重/过滤]
    B --> C[Article 列表]
    C --> D{state_path?}
    D -- yes --> E[ArticleStateStore<br/>计算 new_urls]
    D -- no --> F[跳过增量判断]
    E --> G[确定 report_articles]
    F --> G

    G --> H{fetch_content?}
    H -- yes --> I[fetch_contents<br/>抓正文/提 clean_text]
    H -- no --> J[跳过正文抓取]
    I --> K[正文增强后的 articles]
    J --> K

    K --> L{AI backend 可用?}
    L -- yes --> M[analyze<br/>单篇 enrichment + 趋势分析]
    L -- no --> N[降级:<br/>标记 enrichment 失败 + trend fallback]
    M --> O[evaluate_relevance<br/>规则型 stack relevance]
    N --> O
    O --> O1[report_articles]

    O1 --> P[build_report<br/>生成 Markdown]
    O1 --> Q[_build_json_payload<br/>生成结构化 JSON]

    P --> R[report.md]
    Q --> S[report.json]

    Q --> T{asset_db_path?}
    T -- yes --> U[ArchiveStore.record_run]
    T -- no --> V[跳过资产入库]

    U --> U1[(runs)]
    U --> U2[(articles)]
    U --> U3[(run_articles)]
    U --> U4[(article_contents)]
    U --> U5[(article_enrichments)]
    U --> U6[(article_chunks)]

    U6 --> W[search / retrieval / QA / insights]
    U --> X{delivery 配置开启?}
    X -- yes --> Y[analyze_insights + maybe_dispatch_deliveries]
    Y --> Y1[(deliveries)]
    Y --> Z[Webhook]
    X -- no --> AA[跳过分发]

    U --> AB[feedback_cli / feedback API]
    AB --> AC[(feedback)]

    Q --> AD{archive_dir?}
    AD -- yes --> AE[daily/weekly archive<br/>latest.json + latest.md]
    AD -- no --> AF[跳过归档]
```

## 目录结构

当前目录已经从早期的单文件脚本，演进为“主链路 + 数据层 + 抽取器 + 运行底座 + API”的分层结构：

```text
products/tech_blog_monitor/
├── agent.py                 # 统一 CLI 入口：run / serve / task / ops / feedback
├── monitor.py               # 主执行链路：fetch -> content -> analyze -> report -> archive
├── fetcher.py               # source adapter 调度、抓取、去重、feed 健康状态
├── content_fetcher.py       # 正文抓取调度与 fallback 链
├── analyzer.py              # AI enrichment 与趋势分析
├── reporter.py              # Markdown 报告渲染
├── state.py                 # 增量状态存储
├── archive_store.py         # sqlite 资产写入兼容层
├── repository_provider.py   # sqlite / database_url 统一读取入口
├── search.py                # 搜索能力
├── retrieval.py             # retrieval / embedding 相关逻辑
├── qa.py                    # QA 主逻辑
├── insights.py              # insights 聚合分析
├── delivery.py              # 分发与 webhook
├── feedback.py              # feedback 读写逻辑
├── ops.py                   # 运行 KPI / ops summary 聚合
├── local_scheduler.py       # APScheduler 本地调度实现
├── scheduler.py             # 调度兼容 facade
├── defaults.py              # 默认值常量
├── settings.py              # 环境变量设置模型
├── config.py                # 对外配置兼容层
├── config_loader.py         # 环境变量 / YAML 加载
├── config_validator.py      # 配置校验
├── feed_catalog.py          # 默认 feed catalog
├── content_quality.py       # 正文质量判断
├── search_cli.py            # 搜索 CLI
├── qa_cli.py                # QA CLI
├── insights_cli.py          # insights CLI
├── feedback_cli.py          # feedback CLI
├── api/                     # FastAPI 接口层
├── db/                      # SQLAlchemy / schema / repository 数据层
├── extractors/              # 正文抽取器实现
├── source_adapters/         # source adapter 协议与 RSS adapter
├── observability/           # run / task / stage 结构化观测与 exporter bridge
├── orchestration/           # local / prefect orchestration backend
├── tasks/                   # 标准化任务模型与 runner
└── test/                    # 回归测试与 fixtures
```

理解方式：

- 主链路入口：`agent.py`、`monitor.py`、`local_scheduler.py`
- 抓取与内容理解：`fetcher.py`、`source_adapters/`、`content_fetcher.py`、`extractors/`、`analyzer.py`
- 数据与查询：`archive_store.py`、`db/`、`repository_provider.py`、`search.py`、`retrieval.py`、`qa.py`、`insights.py`
- 产品化输出：`delivery.py`、`feedback.py`、`ops.py`、`api/`
- 运行底座：`observability/`、`tasks/`、`orchestration/`
- 配置系统：`defaults.py`、`settings.py`、`config.py`、`config_loader.py`、`config_validator.py`、`feed_catalog.py`

## 模块与技术映射

下面这张表描述“每个模块主要用了哪些技术”，方便把代码结构和依赖对应起来。

| 模块 | 主要文件 | 使用技术 |
| --- | --- | --- |
| CLI 与本地调度 | `agent.py`、`local_scheduler.py`、`scheduler.py` | Python `argparse` 子命令 CLI、`APScheduler` 定时调度、`pathlib` 文件路径管理、`loguru` 日志 |
| 主执行链路 | `monitor.py`、`reporter.py`、`state.py` | Python dataclass / dict 序列化、`json` 结构化输出、Markdown 字符串渲染、增量状态文件、阶段化 run context |
| Source 抓取层 | `fetcher.py`、`source_adapters/`、`feed_catalog.py` | `requests` HTTP 抓取、`feedparser` RSS/Atom 解析、`ThreadPoolExecutor` 并发抓取、重试退避、source adapter 抽象 |
| 非 RSS 扩源 | `source_adapters/github_releases_adapter.py`、`source_adapters/changelog_adapter.py` | GitHub Releases API、结构化 JSON/HTML 解析、统一 `Article` 归一化、source type 健康统计 |
| 正文抽取层 | `content_fetcher.py`、`extractors/`、`content_quality.py` | `trafilatura` 主抽取器、heuristic HTML/正文清洗、`Playwright` 浏览器兜底、`requests` 抓正文、规则型质量门禁 |
| AI enrichment | `analyzer.py` | `pydantic` schema 校验、结构化 JSON prompt、运行时 AI backend 适配、失败降级与部分成功隔离 |
| Stack Relevance | `internal_relevance/`、`config/stack_profile.example.yaml` | `PyYAML` 读取 stack profile、`tomllib`/JSON/requirements manifest 扫描、规则型匹配打分、可解释 reasons / matched signals |
| 资产存储兼容层 | `archive_store.py`、`state.py` | `sqlite3` 本地资产库、JSON 字段序列化、兼容旧资产写入路径、归档与 run/article 记录 |
| 统一数据库层 | `db/`、`repository_provider.py`、`alembic/` | `SQLAlchemy 2.x` ORM / repository、SQLite + PostgreSQL 双后端、`Alembic` 迁移、`psycopg` PostgreSQL 驱动 |
| 搜索与检索 | `search.py`、`retrieval.py`、`db/repositories/search_repository.py`、`db/repositories/retrieval_repository.py` | SQLite FTS / SQL 文本检索、hybrid lexical + embedding ranking、fake embedding fallback、`pgvector` 向量位点 |
| QA 与 Insights | `qa.py`、`insights.py`、`qa_cli.py`、`insights_cli.py` | retrieval 召回、规则型答案拼接、主题聚类/时间线/热度聚合、CLI 查询接口 |
| API 与产品化输出 | `api/`、`delivery.py`、`feedback.py`、`ops.py` | `FastAPI` + `uvicorn`、Pydantic response schema、webhook delivery、feedback 写入、运行 KPI / ops summary 聚合 |
| 配置系统 | `defaults.py`、`settings.py`、`config.py`、`config_loader.py`、`config_validator.py` | `pydantic-settings` 环境变量读取、YAML feed 配置、默认值常量、配置校验与兼容 facade |
| 运行观测 | `observability/` | `RunContext` / `TaskContext` 运行语义、`NoopObserver` / `InMemoryObserver` / `JsonlObserver` 本地 observer、stage/task/run 级结构化事件与 run summary |
| 任务与编排 | `tasks/`、`orchestration/` | 标准化 task record、local task runner、幂等与重试语义、Prefect adapter 渐进式接入 |
| 测试与质量守门 | `test/`、`test/fixtures/` | `pytest` 单测/集成测试、fixture corpus、retrieval eval、stack relevance eval、`ruff` 静态检查 |

第一次读代码，推荐顺序：

1. `agent.py`
2. `monitor.py`
3. `fetcher.py` / `content_fetcher.py` / `analyzer.py`
4. `archive_store.py` + `db/` + `repository_provider.py`
5. `observability/` + `tasks/` + `orchestration/`
6. `api/app.py`

`P1.3` 起，抓取主链路不再把 RSS 细节硬编码在主调度里。`FeedSource` 现在显式带有
`source_type` 和 `metadata`，`fetch_all()` 会通过 `source_adapters/` 解析到对应 adapter。
当前内置 adapter 包括：

- `rss`
- `github_releases`
- `changelog`

默认 catalog 现在已经启用一组高信噪比非 RSS source：

- `uv Releases`
- `OpenAI Agents Python Releases`
- `browser-use Releases`
- `Gemini CLI Releases`
- `Goose Releases`
- `FastAPI Release History`

其中前四个 GitHub Agent 项目用于长期跟踪 Agent framework / tooling 生态的 release 节奏，
`FastAPI Release History` 继续承担基础服务栈 changelog 监控。`Pydantic Releases` 仍保留为默认关闭的候选扩展源。
这样默认运行面不再是 RSS-only，但仍把非 RSS 扩源控制在一小批结构稳定、技术价值直接的 source 上。

### 非 RSS Source 配置

非 RSS source 仍然沿用 `FeedSource`/`TECH_BLOG_FEEDS_YAML` 配置入口，只额外使用
`source_type` 和可选 `metadata`。

示例：

```yaml
feeds:
  - name: uv Releases
    url: https://api.github.com/repos/astral-sh/uv/releases
    category: AI Agent/工程实践
    source_type: github_releases
    enabled: true

  - name: FastAPI Release History
    url: https://pypi.org/pypi/fastapi/json
    category: AI Agent/工程实践
    source_type: changelog
    enabled: true
    metadata:
      format: pypi
```

约定：

- `github_releases` 读取 GitHub Releases API，默认跳过 draft 和 prerelease
- `changelog` 用于结构化 JSON changelog；当前内置支持通用 `items` 列表和 `metadata.format=pypi`
- 非 RSS source 与 RSS 一样会进入 `FeedHealth`，保留 `source_type` / `error` / `article_count`

### Stack Relevance

`P1.5` 引入了第一版 Stack Relevance Layer，用于回答“外部技术动态是否和当前关注的技术栈相关”。

输入来源：

- 手工 stack profile：`TECH_BLOG_STACK_PROFILE_PATH`
- repo manifest 扫描：`TECH_BLOG_STACK_REPO_ROOTS`

当前支持：

- `requirements*.txt`
- `pyproject.toml`
- `package.json`

评分是规则型、可解释的：

- `relevance_score = dependency_match_score + topic_match_score + source_priority_score`
- 输出到文章级字段：`relevance_score`、`relevance_level`、`relevance_reasons`、`matched_signals`
- 输出到 run 级字段：`relevance_report`

未配置这两个输入时，run 会稳定跳过 `evaluate_relevance` 阶段，不影响主流程。
如果路径不存在、profile 解析失败或 manifest 扫描异常，当前策略也是运行时 warning + fail-open 跳过，
不会让整次 run 失败。

## 常用工作流

### 1. 单次报告

```bash
PYTHONPATH=. python -m products.tech_blog_monitor.agent --output report.md
```

### 2. 增量模式与归档

双视图增量：

```bash
PYTHONPATH=. \
TECH_BLOG_STATE_PATH=reports/tech_blog/seen_articles.json \
python -m products.tech_blog_monitor.agent --output reports/tech_blog/report.md
```

只输出新增：

```bash
PYTHONPATH=. \
TECH_BLOG_STATE_PATH=reports/tech_blog/seen_articles.json \
TECH_BLOG_INCREMENTAL_MODE=new_only \
python -m products.tech_blog_monitor.agent --output reports/tech_blog/report_new_only.md
```

启用 JSON 输出和历史归档：

```bash
PYTHONPATH=. \
TECH_BLOG_STATE_PATH=reports/tech_blog/seen_articles.json \
TECH_BLOG_JSON_OUTPUT=reports/tech_blog/report.json \
TECH_BLOG_ARCHIVE_DIR=reports/tech_blog/archive \
TECH_BLOG_ARCHIVE_GRANULARITY=day \
python -m products.tech_blog_monitor.agent --output reports/tech_blog/report.md
```

### 3. 数据层

sqlite fallback：

```bash
TECH_BLOG_ASSET_DB_PATH=reports/tech_blog/tech_blog_assets.db \
uv run python -m products.tech_blog_monitor.agent --help
```

database URL 主路径：

```bash
TECH_BLOG_DATABASE_URL=postgresql+psycopg://user:pass@127.0.0.1:5432/tech_blog \
uv run python -m products.tech_blog_monitor.agent --help
```

Alembic migration：

```bash
TECH_BLOG_DATABASE_URL=postgresql+psycopg://user:pass@127.0.0.1:5432/tech_blog \
./.venv/bin/python3 ./.venv/bin/alembic -c alembic.ini upgrade head
```

当同时配置 `TECH_BLOG_DATABASE_URL` 时，系统会在保持 `ArchiveStore.record_run(...)` 语义不变的前提下，把 sqlite 资产镜像同步到 `database_url`，并一并维护：

- `article_search_documents`
- `chunk_embedding_records`

### 4. API

启动：

```bash
uv run uvicorn products.tech_blog_monitor.api.app:app --host 127.0.0.1 --port 8000
```

当前接口：

- `GET /health`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /articles`
- `GET /articles/{article_id}`
- `GET /search`
- `GET /insights`
- `GET /ops/summary`
- `POST /feedback`

数据读取规则：

- 若配置了 `TECH_BLOG_DATABASE_URL`，API / search / insights / feedback / QA 优先走该 DB
- 若未配置 `TECH_BLOG_DATABASE_URL`，则回退到 `TECH_BLOG_ASSET_DB_PATH` 指向的 sqlite 资产库
- 若两者都未配置，会返回明确错误：`asset db not configured`

### 5. Search / QA / Insights CLI

检索：

```bash
PYTHONPATH=. python -m products.tech_blog_monitor.search_cli \
  --db reports/tech_blog/tech_blog_assets.db \
  --query agent \
  --days 30
```

QA：

```bash
PYTHONPATH=. python -m products.tech_blog_monitor.qa_cli \
  --db reports/tech_blog/tech_blog_assets.db \
  --question "最近哪些文章在讨论 agent memory？"
```

Insights：

```bash
PYTHONPATH=. python -m products.tech_blog_monitor.insights_cli \
  --db reports/tech_blog/tech_blog_assets.db \
  --days 14 \
  --top-k 5
```

### 6. 任务与调度

本地定时服务：

```bash
PYTHONPATH=. python -m products.tech_blog_monitor.agent serve --run-now
```

切到 `prefect` orchestration 模式：

```bash
PYTHONPATH=. \
TECH_BLOG_ORCHESTRATION_MODE=prefect \
TECH_BLOG_PREFECT_DEPLOYMENT_NAME=demo/tech-blog \
python -m products.tech_blog_monitor.agent serve --run-now
```

执行标准化运维任务：

```bash
PYTHONPATH=. python -m products.tech_blog_monitor.agent task rebuild-search-index --db reports/tech_blog/tech_blog_assets.db
PYTHONPATH=. python -m products.tech_blog_monitor.agent task rebuild-retrieval-index --db reports/tech_blog/tech_blog_assets.db
```

当前任务模型至少覆盖：

- `manual_run`
- `scheduled_run`
- `rebuild_search_index`
- `rebuild_retrieval_index`

### 7. Delivery / Feedback / Ops

启用 webhook 分发：

```bash
PYTHONPATH=. \
TECH_BLOG_ASSET_DB_PATH=reports/tech_blog/tech_blog_assets.db \
TECH_BLOG_DELIVERY_WEBHOOK=https://example.com/webhook \
TECH_BLOG_DELIVERY_ROLES=executive,engineer \
python -m products.tech_blog_monitor.agent --output reports/tech_blog/report.md
```

当前 delivery 是最小可用版本，已具备：

- 幂等
- 重试
- 限流
- 角色化 digest

当前尚未接入平台专有通知适配器，也未做 push queue / worker 分离部署。

写入反馈：

```bash
PYTHONPATH=. python -m products.tech_blog_monitor.feedback_cli add \
  --db reports/tech_blog/tech_blog_assets.db \
  --run-id <run_id> \
  --role engineer \
  --type like \
  --text "这期 infra 总结可保留"
```

运营汇总：

```bash
PYTHONPATH=. \
TECH_BLOG_ASSET_DB_PATH=reports/tech_blog/tech_blog_assets.db \
python -m products.tech_blog_monitor.agent ops summary --limit 50
```

`GET /ops/summary` 和 `agent ops summary` 当前提供的最小 KPI 包括：

- `run_success_rate`
- `feed_availability`
- `content_extraction_pass_rate`
- `low_quality_ratio`
- `enrichment_failure_rate`
- `delivery_success_rate`
- `mean_run_duration_ms`

当前这两条入口复用同一套 `ops.py` 聚合逻辑，`limit` 都表示“最近多少条 task_records 进入窗口”。若只配置 `TECH_BLOG_DATABASE_URL` 而未配置 `TECH_BLOG_ASSET_DB_PATH`，CLI 与 API 仍会直接走数据库 URL 工作。

## 关键设计说明

### 正文抽取链

当前正文抓取采用分层 extractor 链：

- 主路径优先 `Trafilatura`
- 主路径为空或失败时回退到现有 heuristic extractor
- 页面疑似 JS-heavy、正文为空或正文质量不足时，再受控尝试 `Playwright` fallback

正文结果继续写回既有字段：

- `content_status`
- `content_source`
- `clean_text`
- `content_error`
- `content_http_status`
- `content_fetched_at`
- `content_final_url`

`content_status` 在原有 `fetched` / `fetch_error` / `http_error` 基础上，允许出现：

- `empty`
- `low_quality`

这些状态只表示正文结果更可观测，不改变 JSON / sqlite / PostgreSQL / API 的字段结构。

### 运行观测与导出模式

P2 为主链路增加了本地优先的结构化运行观测、任务与调度骨架：

- `RunContext`
- `TaskContext`
- `StageEvent`
- `StageOutcome`
- `TaskResult`
- `NoopObserver`
- `InMemoryObserver`
- `JsonlObserver`
- `MetricPoint`
- `MetricsRegistry`
- `MetricsObserver`
- `TracingBridge`
- `TracingObserver`
- `LocalTaskRunner`
- `task_records`
- `LocalOrchestrationBackend`
- `PrefectOrchestrationBackend`

当前最小阶段打点覆盖：

- `fetch_feeds`
- `fetch_content`
- `analyze_articles`
- `write_report`
- `archive_assets`
- `mirror_database`
- `dispatch_deliveries`

单次 run 结束后：

- 若配置了 `TECH_BLOG_JSON_OUTPUT`，`run_summary` 会写入 JSON payload
- 若配置了 `TECH_BLOG_OBSERVABILITY_JSONL`，run/task/stage 事件会落到本地 JSONL 文件

`P2.2` 在 `P2.1` 结构化事件之上补了三种导出模式：

- `none`
- `jsonl`
- `otlp`

推荐配置：

- 本地调试：`TECH_BLOG_OBSERVABILITY_EXPORTER=jsonl`
- 接 collector：`TECH_BLOG_OBSERVABILITY_EXPORTER=otlp`
- 全关闭导出：`TECH_BLOG_OBSERVABILITY_EXPORTER=none`

当前稳定指标：

- counters: `feed_fetch_total`、`feed_fetch_failures_total`、`content_fetch_total`、`content_low_quality_total`、`enrichment_failures_total`、`delivery_failures_total`
- histograms: `run_duration_ms`、`stage_duration_ms`、`search_latency_ms`、`qa_latency_ms`、`insights_latency_ms`

当前稳定 span 边界：

- stage span: `stage:<stage_name>`
- task span: `task:<task_type>`

如果配置了 `TECH_BLOG_OBSERVABILITY_JSONL`，run/task/stage 事件会落到本地 JSONL；如果配置了 `TECH_BLOG_OBSERVABILITY_EXPORTER=otlp`，系统会尝试桥接 metrics + tracing 到 OTLP HTTP exporter。collector 不存在、endpoint 无效、exporter 初始化失败、emit/flush/close 失败都只会记录 warning 并降级，不会阻断主链路。

### task_records 与幂等

任务记录优先写入 `TECH_BLOG_DATABASE_URL` / `TECH_BLOG_ASSET_DB_PATH` 对应数据库；如果两者都未配置，`manual_run` 会回退到报告目录下的 `tech_blog_tasks.db` sidecar sqlite。

当前已标准化的任务类型：

- `manual_run`
- `scheduled_run`
- `rebuild_search_index`
- `rebuild_retrieval_index`

`task_records` 当前至少包含这些稳定字段：

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
- `started_at`
- `finished_at`
- `retry_count`
- `error_code`
- `error_message`

当前 retry 语义是“记录并显式重放”，不做自动重试；相同幂等键重复执行时会累加 `retry_count`。

### orchestration mode

当前支持两种 orchestration mode：

- `local`：默认模式。`serve` / `serve --run-now` 通过 `APScheduler` 触发，并由 `LocalOrchestrationBackend` 复用 `LocalTaskRunner` 执行 `scheduled_run`。
- `prefect`：渐进增强模式。scheduler 只负责提交 `scheduled_run` 到 `PrefectOrchestrationBackend`，不改变 `task_type`、`trigger_source`、`requested_by`、`run_summary` 语义。

自动降级行为：

- `TECH_BLOG_ORCHESTRATION_MODE=prefect` 但 `prefect` 依赖不可用，builder 会 warning 并降级到 `local`
- `TECH_BLOG_PREFECT_DEPLOYMENT_NAME` 为空，builder 会 warning 并降级到 `local`
- `prefect` backend 在提交时抛错，`run_job()` 会 warning 并回退到 `LocalOrchestrationBackend`

当前明确未支持：

- `Prefect` server / worker / deployment lifecycle 联调
- distributed queue / worker
- article-level `reextract_content` / `reenrich_articles` 编排

### P2 Regression Gate

P2.5 收口后的最小回归门禁建议固定为：

- `uv run pytest -q products/tech_blog_monitor/test/test_observability.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_tasks.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_scheduler.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_prefect_adapter.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_ops.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_api.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_agent.py`

这些用例共同覆盖 `P2.1 ~ P2.4` 的核心成功路径与关键降级路径：observer fail-open、OTLP/exporter 降级、task runner 成功/失败/重试、scheduler 触发任务记录、prefect mock 提交与 fallback、ops summary CLI/API 口径一致性。

## 关键环境变量

### 抓取与正文

| 环境变量 | 用途 |
|---------|------|
| `TECH_BLOG_MAX_ARTICLES` | 每个 feed 抓取文章数上限 |
| `TECH_BLOG_MAX_AGE_DAYS` | 文章时效过滤天数 |
| `TECH_BLOG_MAX_TOTAL` | 报告文章总数上限 |
| `TECH_BLOG_MAX_PER_SOURCE` | 单个源的保留文章上限 |
| `TECH_BLOG_FETCH_WORKERS` | 并发抓取线程数 |
| `TECH_BLOG_FETCH_CONTENT` | 是否抓取文章正文，默认 `true` |
| `TECH_BLOG_CONTENT_TIMEOUT` | 正文抓取超时秒数 |
| `TECH_BLOG_CONTENT_WORKERS` | 正文抓取并发数 |
| `TECH_BLOG_CONTENT_MAX_CHARS` | 清洗正文最大保留字符数 |
| `TECH_BLOG_CONTENT_EXTRACTOR` | 主抽取器，支持 `trafilatura` 或 `heuristic` |
| `TECH_BLOG_PLAYWRIGHT_FALLBACK` | 是否启用受控 `Playwright` 兜底 |
| `TECH_BLOG_PLAYWRIGHT_TIMEOUT` | `Playwright` 兜底超时秒数 |
| `TECH_BLOG_PLAYWRIGHT_WORKERS` | `Playwright` 兜底并发数 |
| `TECH_BLOG_FEEDS_YAML` | 外置 RSS 源配置路径 |

### 输出与增量

| 环境变量 | 用途 |
|---------|------|
| `TECH_BLOG_OUTPUT` | Markdown 报告输出路径 |
| `TECH_BLOG_VIEW` | 报告展示方式，`by_category` 或 `by_time` |
| `TECH_BLOG_STATE_PATH` | 增量状态文件路径 |
| `TECH_BLOG_STATE_MAX_AGE_DAYS` | 状态条目保留天数 |
| `TECH_BLOG_INCREMENTAL_MODE` | `split` 或 `new_only` |
| `TECH_BLOG_JSON_OUTPUT` | JSON 输出路径 |
| `TECH_BLOG_ARCHIVE_DIR` | 历史归档目录 |
| `TECH_BLOG_ARCHIVE_GRANULARITY` | `day` 或 `week` |

### 数据层

| 环境变量 | 用途 |
|---------|------|
| `TECH_BLOG_ASSET_DB_PATH` | sqlite 资产库路径 |
| `TECH_BLOG_DATABASE_URL` | PostgreSQL / sqlite SQLAlchemy URL，存在时优先于 `TECH_BLOG_ASSET_DB_PATH` |
| `TECH_BLOG_STACK_PROFILE_PATH` | 手工 stack profile YAML 路径 |
| `TECH_BLOG_STACK_REPO_ROOTS` | repo root 列表，逗号分隔，用于扫描 manifest 构造 stack signal |
| `TECH_BLOG_EMBEDDING_PROVIDER` | retrieval embedding backend，默认 `fake`，可选 `openai_compatible` |
| `TECH_BLOG_EMBEDDING_MODEL` | `openai_compatible` backend 的 embedding model 名称 |
| `TECH_BLOG_EMBEDDING_API_KEY` | `openai_compatible` backend 的 API key |
| `TECH_BLOG_EMBEDDING_BASE_URL` | `openai_compatible` backend 地址，默认 `https://api.openai.com/v1` |

### 观测与编排

| 环境变量 | 用途 |
|---------|------|
| `TECH_BLOG_OBSERVABILITY_EXPORTER` | 导出模式，支持 `none`、`jsonl`、`otlp` |
| `TECH_BLOG_OBSERVABILITY_JSONL` | 本地结构化运行观测 JSONL 输出路径 |
| `TECH_BLOG_OTLP_ENDPOINT` | OTLP HTTP collector 地址或 signal endpoint |
| `TECH_BLOG_ORCHESTRATION_MODE` | 调度 / 编排模式，支持 `local`、`prefect` |
| `TECH_BLOG_PREFECT_DEPLOYMENT_NAME` | `prefect` deployment 名称 |

### 产品化输出

| 环境变量 | 用途 |
|---------|------|
| `TECH_BLOG_DELIVERY_WEBHOOK` | webhook 分发地址 |
| `TECH_BLOG_DELIVERY_ROLES` | 推送角色，支持 `executive,engineer,researcher` |
| `TECH_BLOG_DELIVERY_CADENCE` | 推送周期，`daily` 或 `weekly` |
| `TECH_BLOG_DELIVERY_RATE_LIMIT` | 每分钟成功推送上限 |
| `TECH_BLOG_DELIVERY_MAX_RETRIES` | 失败重试上限 |
| `AGENT_RUNTIME` | AI 后端，如 `trae` / `codex` / `claude_code` |

## 测试与验证

本地测试基线：

```bash
uv run pytest -q products/tech_blog_monitor/test
uv run ruff check products/tech_blog_monitor
```

专项回归：

```bash
uv run pytest -q products/tech_blog_monitor/test/test_retrieval_eval.py
uv run pytest -q products/tech_blog_monitor/test/test_qa.py
uv run pytest -q products/tech_blog_monitor/test/test_content_fetcher.py
uv run pytest -q products/tech_blog_monitor/test/test_observability.py
uv run pytest -q products/tech_blog_monitor/test/test_tasks.py
uv run pytest -q products/tech_blog_monitor/test/test_scheduler.py
uv run pytest -q products/tech_blog_monitor/test/test_prefect_adapter.py
uv run pytest -q products/tech_blog_monitor/test/test_ops.py
```

`test_retrieval_eval.py` 使用 `products/tech_blog_monitor/test/fixtures/retrieval_eval_*.json`
中的离线小型 corpus、query set 和 golden relevance labels，基于现有
`rank_chunks()` 输出稳定的 `hit@k`、`recall@k`、`mrr` 基线，并在测试中显式校验每条 query 的
`first_relevant_rank`，不依赖网络或真实 embedding provider。

如需启用真实 embedding backend，可配置：

```bash
export TECH_BLOG_EMBEDDING_PROVIDER=openai_compatible
export TECH_BLOG_EMBEDDING_MODEL=text-embedding-3-small
export TECH_BLOG_EMBEDDING_API_KEY=...
```

若 provider 缺配置或请求失败，retrieval / QA 会明确回退到默认 `fake` embedding，不会阻断本地运行或测试。

本地 JSONL smoke：

```bash
PYTHONPATH=. \
TECH_BLOG_OBSERVABILITY_EXPORTER=jsonl \
TECH_BLOG_OBSERVABILITY_JSONL=/tmp/tech_blog_observability.jsonl \
python -m products.tech_blog_monitor.agent --output /tmp/tech_blog_report.md
```

OTLP smoke：

```bash
PYTHONPATH=. \
TECH_BLOG_OBSERVABILITY_EXPORTER=otlp \
TECH_BLOG_OTLP_ENDPOINT=http://127.0.0.1:4318 \
TECH_BLOG_OBSERVABILITY_JSONL=/tmp/tech_blog_observability.jsonl \
python -m products.tech_blog_monitor.agent --output /tmp/tech_blog_report.md
```

如果 collector 不存在，系统会保留本地 registry / observer，并继续输出 JSONL（若配置）。

数据库与 migration 验证：

```bash
UV_CACHE_DIR=/tmp/uv-cache ~/.local/bin/uv run ruff check products/tech_blog_monitor alembic
TECH_BLOG_DATABASE_URL=sqlite+pysqlite:////tmp/tech_blog_alembic.db \
./.venv/bin/python3 ./.venv/bin/alembic -c alembic.ini upgrade head
TECH_BLOG_DATABASE_URL=sqlite+pysqlite:////tmp/tech_blog_alembic.db \
./.venv/bin/python3 ./.venv/bin/alembic -c alembic.ini downgrade base
```

真实 PostgreSQL 集成回归：

```bash
TECH_BLOG_PG_TEST_URL=postgresql+psycopg://user:pass@127.0.0.1:5432/tech_blog_test \
uv run pytest -q products/tech_blog_monitor/test/test_postgres_integration.py
```

正文抽取主路径依赖 `trafilatura`。`Playwright` 仅用于兜底路径，普通单元测试不要求本地浏览器；如需手动验证浏览器 fallback，可额外执行：

```bash
uv run playwright install
```

## 相关文档

文档索引：

- `docs/tech_blog_monitor/README.md`
- `docs/README.md`

优先阅读：

- `docs/tech_blog_monitor/roadmap/tech_blog_long_term_roadmap.md`
- `docs/tech_blog_monitor/roadmap/tech_blog_execution_roadmap.md`
- `docs/tech_blog_monitor/roadmap/tech_blog_quality_iteration_plan.md`

现代化归档：

- `docs/tech_blog_monitor/modernization/tech_monitor_modernization_plan.md`
- `docs/tech_blog_monitor/modernization/tech_blog_p1_data_retrieval_modernization.md`
- `docs/tech_blog_monitor/modernization/tech_blog_p1_5_content_extraction_modernization.md`
- `docs/tech_blog_monitor/modernization/tech_blog_p2_observability_orchestration_modernization.md`

运行与配置：

- `docs/tech_blog_monitor/feeds/rss-feeds.md`
- `docs/tech_blog_monitor/operations/tech_blog_monitor_operations_runbook.md`
