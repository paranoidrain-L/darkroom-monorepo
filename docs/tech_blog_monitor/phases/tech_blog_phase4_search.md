# Tech Blog Phase 4 Search

更新时间：`2026-04-16`

## 目标

Phase 4 的目标是先建立稳定检索能力，而不是直接进入问答。

当前实现是最小可用版，重点解决：

- 基于资产层做历史文章搜索
- 支持关键词搜索
- 支持按来源、分类、主题、标签、时间过滤
- 提供本地 CLI 查询入口

## 当前实现

代码位置：

- `products/tech_blog_monitor/search.py`
- `products/tech_blog_monitor/search_cli.py`
- `products/tech_blog_monitor/repository_provider.py`
- `products/tech_blog_monitor/db/repositories/search_repository.py`
- `products/tech_blog_monitor/db/schema_manager.py`

当前主路径：

- 若配置 `TECH_BLOG_DATABASE_URL`，优先使用 repository provider + PostgreSQL FTS
- 若未配置 `TECH_BLOG_DATABASE_URL`，回退到 sqlite asset DB

## 查询能力

当前支持：

- 关键词查询 `query`
- 来源过滤 `source_name`
- 分类过滤 `category`
- 主题过滤 `topic`
- 标签过滤 `tag`
- 最近 N 天过滤 `days`
- 结果数限制 `limit`

## 排序策略

当前分两条路径：

- sqlite fallback：保持确定性启发式排序
- PostgreSQL 主路径：使用 FTS rank + 时间次排序

相关度分数来源：

- 标题命中
- topic 命中
- tags 命中
- one_line_summary 命中
- clean_text 命中

次排序：

- 发布时间降序
- `updated_at` 降序

## CLI 用法

```bash
PYTHONPATH=. python -m products.tech_blog_monitor.search_cli \
  --db reports/tech_blog/tech_blog_assets.db \
  --query agent \
  --topic 智能体 \
  --days 30 \
  --limit 10
```

## 当前限制

- sqlite fallback 仍不是全文搜索引擎
- 标签过滤当前仍偏 JSON / 文本匹配，不是独立 tag 索引
- 还没有引入更强 reranker
- PostgreSQL FTS 已具备，但排序质量仍需要持续 rebaseline

## 测试

当前已补：

- small golden corpus 风格测试
- 固定查询集
- 时间过滤边界测试
- 来源 / 主题 / 标签过滤测试
- 空结果行为测试
- repository provider 覆盖
- PostgreSQL 主路径可选集成测试

执行命令：

```bash
pytest -q products/tech_blog_monitor/test
```

## 后续建议

当前 P1 之后，建议继续：

1. 继续 rebaseline PostgreSQL FTS 查询集
2. 评估是否需要更细粒度的 tag/topic 结构化索引
3. 与 Phase 5 / P1 retrieval 路径继续协同优化 lexical + vector 混合召回
