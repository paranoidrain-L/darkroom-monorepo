# Public Monorepo V1 Delete Manifest

更新时间：`2026-04-21`

## 用途

这份文档是 `public monorepo v1` 的实际删除清单。

它只回答三个执行问题：

1. 哪些路径应当从公开仓中直接删除
2. 哪些目录应整目录排除，不必逐文件判断
3. 哪些文件不要删除，但必须先人工脱敏

本文默认作用对象是：

- 从当前内部仓导出一个公开 monorepo `V1`

而不是：

- 直接在当前内部仓里执行 destructive delete

## V1 保留范围

最终公开仓只保留：

- `runtime/`
- `docs/agents/`
- `docs/platform/`
- `products/tech_blog_monitor/`
- `docs/tech_blog_monitor/` 的公开文档
- 必要根文件：`README.md`、`LICENSE`、`pyproject.toml`、`requirements.txt`、`uv.lock`、`.gitignore`
- 如 `tech_blog_monitor` 迁移仍依赖：`alembic/`、`alembic.ini`

## A. 直接整目录排除

以下目录在导出公开仓时应直接整目录排除：

```text
.gitlab/
.traecli/
bot/
capabilities/
common/
config/
deploy/
docker/
infra/
prompts/
reports/
products/code_review_ci/
products/feishu_bot/
products/issue_monitor/
products/lint_fix_mr/
products/pre_occ_agent/
docs/agents/        # 保留，勿删
docs/platform/      # 保留，勿删
docs/process/       # 默认整目录排除，见后文例外
```

说明：

- `docs/process/` 默认排除
- 但其中有少数“公开仓导出说明”文档例外，需要单独保留，见后文 `C`

## B. 直接删除的根级文件

以下根级文件不应进入公开仓：

```text
.gitlab-ci.yml
CHANGE_LOG.md
CLAUDE.md
agent_deploy.sh
deploy.sh
gitlab-ci.jsonnet
lint_fix_report.md
pre_occ_agent_process.md
verify.sh
```

如存在以下临时产物，也不要导出：

```text
ai_review_report.md
diagnosis_753249.md
investigation_753249.md
```

## C. `docs/process/` 例外保留文件

虽然 `docs/process/` 默认整目录排除，但以下文件应保留到公开仓：

```text
docs/process/open_source_scope_v1.md
docs/process/open_source_split_plan.md
docs/process/public_monorepo_v1_checklist.md
docs/process/public_monorepo_v1_delete_manifest.md
```

以下文件应删除：

```text
docs/process/agent-development-pipeline.md
docs/process/plan.md
docs/process/refactor-roadmap.md
```

## D. `docs/tech_blog_monitor/operations/` 删除清单

`docs/tech_blog_monitor/operations/` 不应整体公开。

当前建议：

直接删除：

```text
docs/tech_blog_monitor/operations/tech_blog_monitor_session_risk.md
docs/tech_blog_monitor/operations/tech_blog_monitor_todo.md
```

保留但需人工复核：

```text
docs/tech_blog_monitor/operations/tech_blog_monitor_operations_runbook.md
```

## E. `config/` 删除清单

`config/` 整目录不进入公开仓。

其中包括：

```text
config/feishu_config.json
config/feishu_config.template.json
config/mcp/s3_config.template.json
config/mcp/trae_cli.yaml
config/ones_wiki_config.template.json
```

说明：

- 即使是 template，也先不进入 `V1`
- 后续如公开仓需要示例配置，应在公开仓里重建更中性的 `.env.example` 或 product-local example files

## F. `products/` 删除清单

以下 products 整目录删除：

```text
products/code_review_ci/
products/feishu_bot/
products/issue_monitor/
products/lint_fix_mr/
products/pre_occ_agent/
```

`products/__init__.py` 可保留，也可删除后在公开仓中重新生成一个更简洁版本。
如果保留，建议确认其中没有对私有 products 的显式导入或说明。

## G. `tech_blog_monitor` 不删除但必须人工脱敏的文件

以下文件属于 `V1` 保留范围，但不应直接原样公开：

```text
README.md
docs/README.md
docs/tech_blog_monitor/README.md
products/tech_blog_monitor/README.md
products/tech_blog_monitor/delivery.py
products/tech_blog_monitor/internal_relevance/__init__.py
products/tech_blog_monitor/internal_relevance/manifest_scanner.py
products/tech_blog_monitor/internal_relevance/models.py
products/tech_blog_monitor/internal_relevance/profile_loader.py
products/tech_blog_monitor/internal_relevance/report.py
products/tech_blog_monitor/internal_relevance/scorer.py
```

处理要求：

- 改掉“内部技术栈画像”“内部平台”“企业 webhook”这类私有语义
- 保留通用 stack relevance / webhook notification 语义
- 不带任何真实企业 URL、真实 webhook、真实 repo roots

## H. `runtime/` 不删除但需复核的文件

`runtime/` 整体保留，但以下文件建议在公开前复核：

```text
runtime/clients/claude.py
runtime/clients/claude_code.py
runtime/clients/trae.py
runtime/clients/codex.py
runtime/factory.py
runtime/launcher.py
```

复核重点：

- 是否引用本地私有路径约定
- 是否默认依赖某个私有 CLI 安装位置
- 是否在报错信息中暴露私有环境假设

## I. 可直接保留的 `tech_blog_monitor` 公开核心

以下属于公开仓的主产品核心，可以按当前结构保留：

```text
products/tech_blog_monitor/agent.py
products/tech_blog_monitor/analyzer.py
products/tech_blog_monitor/api/
products/tech_blog_monitor/archive_store.py
products/tech_blog_monitor/chunking.py
products/tech_blog_monitor/config.py
products/tech_blog_monitor/config/
products/tech_blog_monitor/config_loader.py
products/tech_blog_monitor/config_validator.py
products/tech_blog_monitor/content_fetcher.py
products/tech_blog_monitor/content_quality.py
products/tech_blog_monitor/db/
products/tech_blog_monitor/defaults.py
products/tech_blog_monitor/extractors/
products/tech_blog_monitor/feed_catalog.py
products/tech_blog_monitor/feedback.py
products/tech_blog_monitor/feedback_cli.py
products/tech_blog_monitor/fetcher.py
products/tech_blog_monitor/insights.py
products/tech_blog_monitor/insights_cli.py
products/tech_blog_monitor/local_scheduler.py
products/tech_blog_monitor/monitor.py
products/tech_blog_monitor/observability/
products/tech_blog_monitor/ops.py
products/tech_blog_monitor/orchestration/
products/tech_blog_monitor/qa.py
products/tech_blog_monitor/qa_cli.py
products/tech_blog_monitor/reporter.py
products/tech_blog_monitor/repository_provider.py
products/tech_blog_monitor/retrieval.py
products/tech_blog_monitor/scheduler.py
products/tech_blog_monitor/search.py
products/tech_blog_monitor/search_cli.py
products/tech_blog_monitor/settings.py
products/tech_blog_monitor/source_adapters/
products/tech_blog_monitor/state.py
products/tech_blog_monitor/tasks/
products/tech_blog_monitor/test/
```

注意：

- `products/tech_blog_monitor/config/stack_profile.example.yaml` 可以保留
- 这属于公开示例配置，不是私有配置

## J. 导出执行顺序

建议按下面顺序执行：

1. 复制保留范围
2. 应用本清单中的整目录删除
3. 应用本清单中的根级文件删除
4. 恢复 `docs/process/` 的 4 个例外保留文件
5. 处理 `docs/tech_blog_monitor/operations/` 的选择性保留
6. 人工脱敏 `README`、`runtime`、`tech_blog_monitor/internal_relevance`、`delivery.py`

## K. 最终验收

导出完成后，公开仓应满足：

- 不包含任何私有 product
- 不包含任何企业配置
- 不包含任何运维私有文档
- 仍能解释清楚：
  - `runtime/` 是平台层
  - `products/tech_blog_monitor/` 是首个公开产品

## 一句话结论

真正执行 `public monorepo v1` 时：

- 大部分私有内容应按目录直接排除
- 少量文档和文件需要精确删除
- 少量保留文件必须先人工脱敏，不能直接公开
