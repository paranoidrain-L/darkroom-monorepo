# Darkroom

Darkroom 是一个把噪音输入冲洗为结构化信号、知识和可执行结果的 agentic monorepo。

当前公开版 monorepo 聚焦两类资产：

- `runtime/`：多 Runtime Agent 执行底座
- `products/tech_blog_monitor/`：技术情报与技术博客监控产品

配套文档位于：

- `docs/agents/`：Planner / Worker / Tester 协作方法论
- `docs/platform/`：Agentic Platform / VSM 设计文档

这不是内部全集仓的直接公开版本，而是一个经过裁剪的 `public monorepo v1`。当前目标公开仓为 `darkroom-monorepo`。

## 目录结构

```text
repo/
├── runtime/                    # AI runtime 抽象：claude / claude_code / trae / codex
├── docs/
│   ├── agents/                 # 多 Agent 协作方法论
│   ├── platform/               # Agentic platform / VSM 文档
│   └── tech_blog_monitor/      # tech_blog_monitor 专项文档
├── products/
│   └── tech_blog_monitor/      # 当前首个公开产品
├── alembic/                    # tech_blog_monitor 数据迁移
├── LICENSE
├── pyproject.toml
├── requirements.txt
└── uv.lock
```

## 当前公开范围

当前 `v1` 只公开以下四块：

- `runtime/`
- `docs/agents/`
- `docs/platform/`
- `products/tech_blog_monitor/`

当前不包含：

- 企业集成型 products
- 私有配置
- 私有运维文档
- 企业 CI / 部署脚本

后续如果继续开放 `products/feishu_bot/`，仍会放在同一个公开 monorepo 中。

## Runtime

`runtime/` 提供统一的 AI client 接口，当前支持：

- `claude`
- `claude_code`
- `trae`
- `codex`

最常见的调用方式：

```python
from runtime.factory import get_client

client = get_client(backend="codex")
result = client.chat("Explain this module in plain language.")
```

如果你在做 CLI Agent、代码审查 Agent 或内容分析 Agent，这一层就是 Darkroom 的共用执行底座。

## Product: Tech Blog Monitor

`tech_blog_monitor` 是当前公开仓里的首个完整产品样板。它负责：

- 聚合 RSS 与非 RSS 技术更新源
- 抓取正文并做质量判断
- 生成 enrichment / search / QA / insights
- 输出 Markdown / JSON / API / ops summary
- 提供本地优先的 observability / task / orchestration 底座

快速开始：

```bash
uv sync --group dev
uv run python -m products.tech_blog_monitor.agent --help
uv run pytest -q products/tech_blog_monitor/test
uv run ruff check products/tech_blog_monitor
```

单次执行：

```bash
PYTHONPATH=. python -m products.tech_blog_monitor.agent --output report.md
```

启动最小 API：

```bash
uv run uvicorn products.tech_blog_monitor.api.app:app --host 127.0.0.1 --port 8000
```

详细说明见：

- [products/tech_blog_monitor/README.md](products/tech_blog_monitor/README.md)
- [docs/tech_blog_monitor/README.md](docs/tech_blog_monitor/README.md)
- [.env.example](.env.example)

## Docs

如果你关心多 Agent 协作：

- [docs/agents/shared_principles.md](docs/agents/shared_principles.md)
- [docs/agents/planner_methodology.md](docs/agents/planner_methodology.md)
- [docs/agents/worker_methodology.md](docs/agents/worker_methodology.md)
- [docs/agents/tester_methodology.md](docs/agents/tester_methodology.md)
- [docs/agents/collaboration_contract.md](docs/agents/collaboration_contract.md)

如果你关心平台拓扑与 VSM：

- [docs/platform/agentic_platform_topology.md](docs/platform/agentic_platform_topology.md)
- [docs/platform/agentic_platform_topology_review.md](docs/platform/agentic_platform_topology_review.md)

如果你关心产品专项文档：

- [docs/tech_blog_monitor/README.md](docs/tech_blog_monitor/README.md)

## Development

推荐使用 `uv`：

```bash
uv sync --group dev
```

仓库级基本检查：

```bash
uv run pytest -q runtime/test products/tech_blog_monitor/test
uv run ruff check runtime products/tech_blog_monitor
```

协作入口：

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [.github/pull_request_template.md](.github/pull_request_template.md)
- [.github/ISSUE_TEMPLATE/bug_report.md](.github/ISSUE_TEMPLATE/bug_report.md)
- [.github/ISSUE_TEMPLATE/feature_request.md](.github/ISSUE_TEMPLATE/feature_request.md)

## One-Line Summary

Darkroom 当前的目标不是做一个“大而全的企业 Agent 工具箱”，而是公开：

- 一个可复用的 Agent runtime 底座
- 一套多 Agent 协作与平台设计文档
- 一个完整的技术情报产品样板
