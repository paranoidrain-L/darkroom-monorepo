# Tech Blog Monitor 5-Minute Quickstart

这份 quickstart 面向第一次接触 `tech_blog_monitor` 的外部用户，目标是在 5 分钟内跑通一条最小链路：

1. 安装依赖
2. 生成一份 Markdown / JSON 报告
3. 启动最小 API
4. 知道下一步该看哪里

## 0. 前提

建议环境：

- Python `3.10+`
- `uv`

如果你还没有 `uv`：

```bash
pip install uv
```

仓库根目录下执行以下命令。

## 1. 安装依赖

```bash
uv sync --group dev
```

## 2. 准备最小配置

复制公开示例配置：

```bash
cp .env.example .env
```

这一步不是强制的，但推荐这样做，后续命令会更稳定。

`tech_blog_monitor` 的默认路径已经是本地优先：

- 报告输出到 `reports/tech_blog/`
- 资产默认落在本地 sqlite
- retrieval 默认使用 `fake` embedding
- 没有配置 AI runtime 时，系统会降级而不是直接崩掉

如果你只想做一次最小跑通，可以不用再改 `.env`。

## 3. 先看 CLI 是否正常

```bash
uv run python -m products.tech_blog_monitor.agent --help
```

如果这条命令能正常输出帮助信息，说明基本环境已经就绪。

## 4. 跑一次最小报告

为了缩短首次运行时间，建议先限制抓取量：

```bash
PYTHONPATH=. \
TECH_BLOG_MAX_ARTICLES=3 \
uv run python -m products.tech_blog_monitor.agent --output reports/tech_blog/quickstart_report.md
```

如果你希望同时输出结构化 JSON：

```bash
PYTHONPATH=. \
TECH_BLOG_MAX_ARTICLES=3 \
TECH_BLOG_JSON_OUTPUT=reports/tech_blog/quickstart_report.json \
uv run python -m products.tech_blog_monitor.agent --output reports/tech_blog/quickstart_report.md
```

跑完后先看这两个产物：

- `reports/tech_blog/quickstart_report.md`
- `reports/tech_blog/quickstart_report.json`

## 5. 启动最小 API

```bash
uv run uvicorn products.tech_blog_monitor.api.app:app --host 127.0.0.1 --port 8000
```

启动后可以先访问：

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

如果你在前一步已经生成了本地资产库，API 会直接基于这些数据工作。

## 6. 可选：跑最小测试基线

如果你想确认仓库状态是健康的，先跑这两条：

```bash
uv run ruff check runtime products/tech_blog_monitor
uv run pytest -q runtime/test products/tech_blog_monitor/test --ignore=products/tech_blog_monitor/test/test_postgres_integration.py
```

## 常见情况

### 没有配置 AI runtime

这是允许的。系统会继续完成抓取、正文抽取、报告生成和本地数据落库，只是 enrichment 会降级。

### 没有 PostgreSQL

这也是允许的。首次体验默认就是 sqlite 本地模式。

### 没有 Playwright 浏览器

这不会阻塞最小 quickstart。Playwright 只是正文抽取的受控 fallback，不是最小运行前提。

### 首次运行时间偏长

把 `TECH_BLOG_MAX_ARTICLES` 设小一些，例如 `1` 或 `3`，就能显著缩短时间。

## 跑通之后看哪里

如果你想继续深入，建议按这个顺序：

1. 看 [products/tech_blog_monitor/README.md](../../products/tech_blog_monitor/README.md)
2. 看 [docs/tech_blog_monitor/feeds/rss-feeds.md](feeds/rss-feeds.md)
3. 看 [docs/tech_blog_monitor/operations/tech_blog_monitor_operations_runbook.md](operations/tech_blog_monitor_operations_runbook.md)
4. 看 [docs/tech_blog_monitor/roadmap/tech_blog_long_term_roadmap.md](roadmap/tech_blog_long_term_roadmap.md)
