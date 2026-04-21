# P1.4 High-Signal Source Expansion Plan

更新时间：`2026-04-19`

## 执行状态

截至 `2026-04-19`，`P1.4` 可视为已完成并通过验收。

当前结论：

- 建议合入
- 未发现阻塞性问题

## 验收归档

本轮验收确认，`P1.4` 的核心边界已经满足：

- 已接入两类高信噪比非 RSS source：`github_releases` 与 `changelog`
- 默认 catalog 已启用两个非 RSS 高价值源：`uv Releases` 与 `FastAPI Release History`
- 非 RSS source 通过独立 adapter 接入，而不是回退到 RSS 特例路径
- `source_type` / `health` / `error` 在主抓取链路和 observability 中保留

实现与覆盖证据如下：

- `fetcher.py` 已将 `github_releases` 和 `changelog` 注册到默认 adapter 集合
- `feed_catalog.py` 已启用两个非 RSS source，并保留一个默认关闭的候选源 `Pydantic Releases`
- `test_source_adapters.py` 覆盖了：
  - adapter 注册
  - 默认 catalog 非 RSS source 启用状态
  - GitHub Releases 归一化
  - changelog / PyPI release history 归一化
  - 非 RSS source 在 `fetch_all()` 中的聚合行为
  - 非 RSS source 日增文章占比阈值
  - 非 RSS source 正文抽取成功率与 RSS baseline 对比

本轮复验结果归档如下：

- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check products/tech_blog_monitor` 通过
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_fetcher.py`：`23 passed`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_monitor.py`：`19 passed`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_retrieval_eval.py`：`2 passed`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_source_adapters.py`：`10 passed`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test`：`259 passed, 1 skipped`

按当前测试证据，可认为以下验收口径已经满足：

- 至少接入 `2` 个非 RSS 高价值 source
- 新源贡献的日增文章量占比达到至少 `20%`
- 新源正文抽取成功率不低于现有主源平均水平的 `95%`
- `P1.2` retrieval eval 守门测试未回归
- 未看到 `HN` / `Reddit` / `P1.5` 等范围漂移

剩余非阻塞尾项：

- 当前默认启用的新 source 仍偏少，后续可在 `P1.4` 后续轮次继续扩到第 `3` 个高价值源
- `README` 和配置说明当前已覆盖最小必要信息，如后续 source type 增多，可再补一个更完整的非 RSS source runbook

## 目标

`P1.4` 的目标是在 `P1.3 Source Adapter` 基础上，接入第一批高信噪比非 RSS 新源，扩大信息覆盖面，同时不明显拉低当前正文质量、检索质量和系统可控性。

这一阶段要解决的问题是：

- 当前系统虽然已经完成 adapter 抽象，但主生产数据面仍然几乎是 RSS-only
- 如果长期停留在 RSS，技术情报覆盖面会受限
- 如果一开始就接入高噪音社区流量源，会过早放大抽取误差、检索误差和审计负担

一句话目标：

- `在不牺牲质量底座的前提下，先把高信噪比非 RSS 信号接进来`

## 范围

本阶段包含：

- 接入 `2-3` 个高信噪比非 RSS source
- 为这些 source 实现独立 adapter
- 将新 source 统一归一化到现有 `Article` 模型
- 保持 source health / source_type / observability 可观测
- 补 fixture、测试和最小文档说明

本阶段不包含：

- `Hacker News`
- `Reddit`
- 社区讨论型高噪音源
- `P1.5 Internal Relevance`
- 新前端 / 新 API 面
- 重型图谱或自动动作闭环

## 输入原则

第一批 source 必须满足至少两个条件：

- 官方或半官方
- 页面结构稳定
- 信息密度高
- 噪音低
- 与技术选型、依赖升级、平台演进高度相关

## 建议首批来源

建议从下面三类中选择 `2-3` 个落地：

### 1. GitHub Releases

价值：

- 对内部依赖升级、breaking change、版本演进最直接
- 结构化程度高
- 很适合作为未来 internal relevance 的上游信号

适合作为：

- 第一个非 RSS 重点 source type

### 2. 官方 Changelog / Release Notes

例如：

- Python
- Kubernetes
- Go
- PostgreSQL
- Cloudflare / major platform changelog

价值：

- 信号密度高
- 噪音低
- 对 infra / language / runtime 团队价值直接

### 3. 结构化项目公告页

例如：

- 官方 blog index
- 官方 release archive
- vendor announcement pages

价值：

- 比社区讨论更稳定
- 比纯 RSS 更广

## 不建议第一批优先做的来源

本阶段不建议优先投入：

- `Hacker News`
- `Reddit`
- `GitHub Discussions`
- 无结构聚合站

原因：

- 噪音高
- 重复高
- 摘要和正文边界弱
- 对当前 `Understand / Retrieve / Audit` 负担过大

## 建设原则

### 1. 先高信噪比，再高覆盖

这一阶段优先追求：

- 质量可控的新增信号

而不是：

- 名义上的 source 数量增长

### 2. 保持 `Article` 统一归一化

第一版新增 source 仍统一落到现有 `Article`：

- `title`
- `url`
- `source_name`
- `category`
- `source_id`
- `rss_summary`
- `published`
- `published_ts`
- `fetched_at`

说明：

- 即使不是 RSS，第一版也先复用 `rss_summary` 字段承接归一化摘要
- 本阶段不做大字段重命名

### 3. 每种新 source 都要有独立 adapter

不能把非 RSS source 再塞回 RSS 抓取器逻辑里。

### 4. 可观测优先

新增 source 必须保留：

- `source_type`
- health
- error
- article_count

否则后续无法评估扩源收益与成本。

## 建议设计

### 1. Source Type

建议第一版至少引入下面这类 source type：

- `github_releases`
- `changelog`
- 如有必要，`announcement_page`

### 2. Adapter 结构

建议每个新 source type 对应一个独立 adapter，例如：

- `GitHubReleasesAdapter`
- `ChangelogAdapter`

要求：

- 不共享过多隐式逻辑
- 每个 adapter 自己负责抓取和最小归一化
- 统一输出 `Article`

### 3. 配置方式

建议第一版保持和 `FeedSource` 同风格：

- 在 source catalog 中声明
- 支持 `source_type`
- 支持 `enabled`
- 按 source type 补最少必要字段

不要一开始上复杂动态配置系统。

### 4. 归一化策略

对于非 RSS source，第一版建议：

- `title`：使用原始标题
- `url`：唯一内容 URL
- `source_name`：人类可读名称
- `category`：沿用现有分类体系
- `source_id`：保持稳定唯一
- `rss_summary`：填归一化摘要或页面摘要
- `published/published_ts`：尽量从源页面结构提取

## 实施步骤

### Step 1：选定 2-3 个首批 source

要求：

- 都是高信噪比
- 都有稳定可抓取页面结构
- 至少一个是 `github_releases`

产出：

- source shortlist
- 每个 source 的抓取入口与字段映射草案

### Step 2：实现 adapter

为每个选定 source 实现独立 adapter，要求：

- 可独立测试
- 输出 `Article`
- 不依赖前端、不依赖外部运行平台

### Step 3：接到 source catalog 和主链路

完成：

- 新 source 在 catalog 中可配置
- `fetch_all()` 可通过 adapter 统一抓取
- `source_type` 在 health / observability 中可见

### Step 4：补 fixture 和测试

至少覆盖：

- adapter 抓取成功路径
- 失败路径
- 归一化字段完整性
- 新 source 在 `fetch_all()` 中的聚合行为

### Step 5：最小质量回归

至少检查：

- 正文抽取成功率
- 对 retrieval eval 的影响
- 日增文章覆盖占比

## 文件范围

建议主要修改：

- `products/tech_blog_monitor/feed_catalog.py`
- `products/tech_blog_monitor/fetcher.py`
- `products/tech_blog_monitor/source_adapters/`
- `products/tech_blog_monitor/test/test_fetcher.py`
- 如有必要新增：
  - `products/tech_blog_monitor/test/test_source_adapters.py`
  - `products/tech_blog_monitor/test/fixtures/source_adapters/*`
- `products/tech_blog_monitor/README.md`
- 如 source 配置说明需要同步，可更新：
  - `docs/tech_blog_monitor/feeds/rss-feeds.md`

## 完成标准

`P1.4` 完成至少需要满足：

- 至少接入 `2` 个非 RSS 高价值 source
- 新 source 贡献的日增文章量占比达到至少 `20%`
- 新 source 正文抽取成功率不低于现有主源平均水平的 `95%`
- 新 source 接入后，retrieval eval 核心指标相对 `P1.2` 不出现超过 `5%` 的回退
- 新 source 的 `source_type` / health / error 可观测
- 未发生 `P1.5` 或高噪音扩源的范围漂移

## 建议验证命令

```bash
uv run ruff check products/tech_blog_monitor
uv run pytest -q products/tech_blog_monitor/test/test_fetcher.py
uv run pytest -q products/tech_blog_monitor/test/test_monitor.py
uv run pytest -q products/tech_blog_monitor/test/test_retrieval_eval.py
```

如新增 adapter 测试文件，可补跑：

```bash
uv run pytest -q products/tech_blog_monitor/test/test_source_adapters.py
uv run pytest -q products/tech_blog_monitor/test
```

## 风险

### 1. 扩源过快

如果一口气接太多 source，很容易让质量问题和解析问题一起爆炸。

### 2. 伪高价值 source

有些 source 看起来官方，但内容结构差、更新不稳定，接入成本可能高于收益。

### 3. 归一化语义漂移

如果不同 source 输出的 `Article` 语义差异太大，后续正文、检索、QA 会被污染。

### 4. 范围漂移

不要顺手把下面内容混进来：

- internal relevance
- HN / Reddit
- 大规模社区源
- 新前端能力

## 一句话原则

`P1.4` 的重点不是“新增更多 source”，而是：

- `先把高信噪比、低噪音、结构稳定的非 RSS 信号接进现有知识管线`
