# Tech Blog Phase 1 Asset Design

更新时间：`2026-04-14`

## 目标

Phase 1 的目标不是做搜索或 RAG，而是把当前运行产物升级为可检索、可持续积累的历史文章资产。

当前实现选择：

- 存储介质：`sqlite`
- 模块位置：`products/tech_blog_monitor/archive_store.py`
- 配置项：`TECH_BLOG_ASSET_DB_PATH`

## 为什么选择 sqlite

- 比散落的 JSON 归档更适合后续查询
- 不需要额外服务依赖
- 适合当前单机 / cron / 本地工具形态
- 能较低成本承接后续 `Search / Retrieval / RAG`

## 实体设计

### 1. `runs`

记录一次 monitor 执行批次。

关键字段：

- `run_id`
- `generated_at`
- `generated_at_iso`
- `output_path`
- `view`
- `incremental_mode`
- `article_count`
- `all_article_count`
- `new_article_count`

### 2. `articles`

记录去重后的文章主记录，是后续检索和 enrichment 的基础实体。

关键字段：

- `article_id`
- `normalized_url`
- `url`
- `source_id`
- `source_name`
- `category`
- `title`
- `published_ts`
- `first_seen_at`
- `last_seen_at`
- `latest_fetched_at`
- `rss_summary`
- `ai_summary`
- `content_hash`
- `last_run_id`

### 3. `run_articles`

记录某次运行中观测到的文章快照，用于区分：

- 文章主记录
- 某次运行里是否出现
- 某次运行里是否属于新增
- 某次运行里是否进入报告

关键字段：

- `run_id`
- `article_id`
- `normalized_url`
- `url`
- `title`
- `source_name`
- `category`
- `published_ts`
- `fetched_at`
- `is_new`
- `in_report`
- `report_position`
- `rss_summary`
- `ai_summary`
- `content_hash`

## 唯一标识与去重

### URL 规范化

当前使用 `normalized_url` 作为文章去重依据：

- scheme 小写
- host 小写
- 去掉 fragment
- 保留 path 和 query

### `article_id`

- 由 `normalized_url` 做 `sha256`
- 用于 sqlite 主键和后续引用

### `content_hash`

当前基于以下字段计算：

- `title`
- `source_name`
- `published_ts`
- `rss_summary`

说明：

- Phase 1 还没有正文，因此这里的 `content_hash` 只是“元数据 + RSS 摘要”的稳定 hash
- 到 Phase 2 做正文抓取后，应升级为正文语义更强的 hash

## 兼容策略

当前已实现两类兼容入口：

### 1. 旧 state 文件

支持导入：

- 旧格式：`url -> timestamp`
- 新格式：`version + articles`

入口：

- `ArchiveStore.import_state_file()`

### 2. 现有归档 JSON payload

支持导入当前 monitor 输出的 JSON 结构。

入口：

- `ArchiveStore.ingest_archive_payload()`

## 查询接口

Phase 1 只提供最小查询能力，不提供完整搜索 CLI。

已实现：

- `get_article_by_url()`
- `list_recent_articles()`
- `list_articles(source_name=..., category=...)`
- `get_run()`
- `list_run_articles()`

## 集成策略

在 `products/tech_blog_monitor/monitor.py` 中：

1. 先抓取与分析
2. 构建 JSON payload
3. 如果配置了 `TECH_BLOG_ASSET_DB_PATH`，写入 sqlite 资产层
4. 将 `run_id` 回填到 JSON payload
5. 再继续写 JSON 文件、历史归档、增量状态

这样能保证：

- 不破坏当前 Markdown / JSON / state / archive 行为
- 新资产层与现有归档产物能通过 `run_id` 对齐

## 后续衔接

Phase 1 完成后，下一阶段应直接进入：

- Phase 2：正文抓取与正文清洗

而不是继续扩展更多 JSON 归档格式。
