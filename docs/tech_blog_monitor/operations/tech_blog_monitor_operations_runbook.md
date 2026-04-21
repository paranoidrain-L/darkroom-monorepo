# Tech Blog Monitor Operations Runbook

更新时间：`2026-04-17`

## 目标

这份 runbook 面向 P2.5 的本地优先运营场景，回答四类问题：

1. 本地如何复现一次 run
2. 结构化事件文件怎么查看
3. 常见失败路径怎么快速判断
4. 正文 / enrichment / index 如何重跑

## 本地调试

最小单次执行：

```bash
PYTHONPATH=. \
TECH_BLOG_MAX_ARTICLES=1 \
python -m products.tech_blog_monitor.agent --output /tmp/tech_blog_report.md
```

启用结构化事件文件：

```bash
PYTHONPATH=. \
TECH_BLOG_MAX_ARTICLES=1 \
TECH_BLOG_OBSERVABILITY_EXPORTER=jsonl \
TECH_BLOG_OBSERVABILITY_JSONL=/tmp/tech_blog_observability.jsonl \
python -m products.tech_blog_monitor.agent --output /tmp/tech_blog_report.md
```

查看最近运营汇总：

```bash
PYTHONPATH=. \
TECH_BLOG_ASSET_DB_PATH=reports/tech_blog/tech_blog_assets.db \
python -m products.tech_blog_monitor.agent ops summary --limit 50
```

## 事件文件查看

JSONL 文件按 record_type 落盘，最常用的几类记录：

- `run_started`
- `stage_event`
- `stage_outcome`
- `task_result`
- `run_finished`

快速查看最近 run：

```bash
tail -n 20 /tmp/tech_blog_observability.jsonl
```

只看失败阶段：

```bash
rg '"status": "failed"' /tmp/tech_blog_observability.jsonl
```

只看 run summary：

```bash
rg '"record_type": "run_finished"' /tmp/tech_blog_observability.jsonl
```

## 常见失败路径

### 1. 配置校验失败

现象：

- CLI 直接返回 `exit code 1`
- `run_summary.error_code = ConfigValidationError`

优先检查：

- `TECH_BLOG_ASSET_DB_PATH`
- `TECH_BLOG_DATABASE_URL`
- `TECH_BLOG_OBSERVABILITY_EXPORTER`
- `TECH_BLOG_ORCHESTRATION_MODE`

### 2. 没有抓到文章

现象：

- `run_summary.error_code = NoArticles`
- `fetch_content` / `analyze_articles` / `write_report` 被标记为 `skipped`

优先检查：

- RSS 源是否可访问
- feed 是否被 `enabled: false`
- 过滤条件是否过严

### 3. OTLP / Prefect 初始化失败

现象：

- 日志出现 warning
- 主链路仍继续运行

说明：

- `OTLP` 失败会自动降级为本地 observer
- `prefect` backend 失败会自动降级为 `local` backend

### 4. delivery 失败

现象：

- `run_summary.delivery_status_counts` 中出现非 `delivered`
- `delivery_failures_total` 增加

优先检查：

- `TECH_BLOG_DELIVERY_WEBHOOK`
- `TECH_BLOG_DELIVERY_ROLES`
- webhook 接口是否限流 / 鉴权失败

## 重跑方式

### 重跑正文 / enrichment

当前 P2.5 还没有 article-level `reextract_content` / `reenrich_articles` 独立任务。

现阶段推荐方式：

```bash
PYTHONPATH=. \
TECH_BLOG_FETCH_CONTENT=true \
python -m products.tech_blog_monitor.agent --output /tmp/tech_blog_rerun.md
```

如果只想验证正文链路，可配合不可用 AI backend 或测试环境 backend 做局部冒烟。

### 重建 search index

```bash
PYTHONPATH=. \
python -m products.tech_blog_monitor.agent task rebuild-search-index --db reports/tech_blog/tech_blog_assets.db
```

### 重建 retrieval index

```bash
PYTHONPATH=. \
python -m products.tech_blog_monitor.agent task rebuild-retrieval-index --db reports/tech_blog/tech_blog_assets.db
```

## 最小看板定义

`agent ops summary` 和 `GET /ops/summary` 当前输出第一批运营指标：

- `run_success_rate`
- `feed_availability`
- `content_extraction_pass_rate`
- `low_quality_ratio`
- `enrichment_failure_rate`
- `delivery_success_rate`
- `mean_run_duration_ms`

口径说明：

- `run_success_rate`：最近窗口内 `manual_run + scheduled_run` 成功任务占比
- `feed_availability`：`feed_stats.success / (success + failure)`，不计 disabled
- `content_extraction_pass_rate`：`fetched / 所有非 not_fetched 正文状态`
- `low_quality_ratio`：`low_quality / 所有非 not_fetched 正文状态`
- `enrichment_failure_rate`：`failed / 全部 enrichment 状态`
- `delivery_success_rate`：`delivered / 全部 delivery 状态`
- `mean_run_duration_ms`：最近窗口 run summary 的平均 duration

空窗口和零分母处理：

- 最近窗口没有任务时，各 ratio KPI 返回 `null`
- 某一类分母为 0 时，该 KPI 返回 `null`，而不是伪造 `0.0`

## P2 regression gate

建议把下面这组命令作为 `P2.1 ~ P2.4` 的最小回归门禁：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_observability.py
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_tasks.py
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_scheduler.py
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_prefect_adapter.py
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_ops.py
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_api.py
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_agent.py
```

如果只做一次全量复验，可直接运行：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test
```
