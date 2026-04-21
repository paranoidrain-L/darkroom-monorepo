# P1.3 Source Adapter Plan

更新时间：`2026-04-19`

## 执行状态

截至 `2026-04-19`，`P1.3` 可视为已完成并通过验收。

当前结论：

- 建议合入
- 未发现阻塞性问题

## 验收归档

本轮验收确认，`P1.3` 的核心边界已经满足：

- 最小 `SourceAdapter` 抽象已落地
- RSS 已收敛为首个内置 adapter
- 主抓取链路已通过 adapter 分发，而不是继续直接绑死 RSS
- `FeedSource` 只做了最小必要扩展，新增 `source_type`，没有演化成过度设计的大框架

兼容性与 contract 证据也已具备：

- 原有 `fetch_feed()` facade 仍保留，兼容现有调用方
- `test_fetcher.py` 继续覆盖 RSS 解析、重试、超时、SSL、过滤、去重语义
- 已补 fake adapter contract 测试与 `fetch_all()` 非 RSS 路径测试
- observability / health 中的 `source_type` 已保留

本轮复验结果归档如下：

- `uv run ruff check products/tech_blog_monitor` 通过
- `uv run pytest -q products/tech_blog_monitor/test/test_fetcher.py`：`23 passed`
- `uv run pytest -q products/tech_blog_monitor/test/test_monitor.py`：`19 passed`
- `uv run pytest -q products/tech_blog_monitor/test`：`247 passed, 1 skipped`

范围检查结论：

- 当前仓库里没有把 `GitHub Releases` 或其他真实新源接入主路径
- 本轮未看到明显 `P1.4` 或 `P1.5` 范围漂移

剩余非阻塞尾项：

- `fetcher.py` 顶部模块说明和少量注释文字仍偏“RSS 抓取器”表述，后续可顺手收口为更中性的 `source fetch pipeline`

## 目标

`P1.3` 的目标不是立刻接入很多新源，而是先把“数据源接入”从 RSS 特例抽成统一 adapter 模型。

这一阶段要解决的问题是：

- 当前抓取主流程基本等价于“RSS 抓取器”
- 新增非 RSS 源时，很容易继续复制 `fetcher.py` 的 RSS 语义
- 如果不先抽象，`P1.4` 扩源会把接入逻辑、归一化逻辑和主流程耦合得更深

一句话目标：

- `在不改变现有 RSS 主流程语义的前提下，建立 Source Adapter 抽象，并让 RSS 成为第一个 adapter`

## 范围

本阶段包含：

- 定义最小 `SourceAdapter` 抽象
- 定义统一 source descriptor / source type / metadata contract
- 让现有 RSS 路径通过 adapter 运行
- 保持 `Article` 作为当前统一归一化对象
- 补兼容测试和最小文档说明

本阶段不包含：

- `P1.4` 真正接入 `GitHub Releases` / changelog / 新 source
- 改写 `Article` 为全新多态模型
- 改前端、API、delivery、internal relevance
- 做完整 plugin marketplace

## 现状

当前主抓取流程的核心特点是：

- `fetcher.py` 直接承担 RSS 获取、解析、重试、并发和过滤
- `FeedSource` 默认就是 RSS source
- 主流程和 RSS 语义绑定较深

这在只有 RSS 时没有问题，但对下一步存在明显限制：

- 新增 source 时，容易继续复制 RSS 代码路径
- source type 的差异没有被显式建模
- 无法清晰表达“抓取 contract”和“归一化 contract”

## 建设原则

### 1. 先抽象，后扩源

`P1.3` 的完成标准不是“多接几个源”，而是：

- 新 source 的接入点已经清楚

### 2. 保持主流程语义不变

当前 `RSS -> Article -> 后续正文/分析/存储` 的主链路不能因为抽象而发生语义漂移。

### 3. 保持 `Article` 为当前统一归一化对象

这一阶段不做新的大模型重构。

所有 adapter 的输出仍然先归一化到现有 `Article`。

### 4. 不做过度设计

第一版不追求：

- 完整插件市场
- 动态加载系统
- 大而全 source 框架

只要让下一步 `P1.4` 能稳定接入新源即可。

## 建议设计

### 1. Source Descriptor

建议在现有 `FeedSource` 基础上向“通用 source descriptor”演进。

第一版至少显式包含：

- `source_type`
- `name`
- `category`
- `enabled`

RSS 特有字段例如：

- `url`
- `timeout`
- `verify_ssl`
- `headers`

仍可先保留在 RSS source 定义中，不必一次性抽成最通用模型。

### 2. Source Adapter Protocol

建议的最小抽象：

```python
class SourceAdapter(Protocol):
    def source_type(self) -> str: ...
    def fetch(self, source, *, max_articles: int, run_context=None) -> tuple[list[Article], list[dict] | object]: ...
```

第一版重点不是接口长相绝对正确，而是满足：

- 主流程不再直接依赖 RSS 解析细节
- 不同 source type 后续有独立落点

### 3. RSS Adapter

把现有 RSS 抓取实现收敛为：

- `RssSourceAdapter`

要求：

- 内部复用现有 `fetch_feed` / `fetch_all` 逻辑或其拆分结果
- 不改变 RSS 输出行为
- 不改变当前 fetch 健康统计语义

### 4. 统一归一化 Contract

第一版所有 adapter 输出统一归一化到现有 `Article`：

- `title`
- `url`
- `source_name`
- `category`
- `source_id`
- `rss_summary`
- `published`
- `published_ts`
- `fetched_at`

即使 future source 不是 RSS，也先映射到这套字段。

其中：

- `rss_summary` 可以在后续考虑更名，但 `P1.3` 不做字段级重命名

### 5. Source Metadata Contract

建议第一版至少保证：

- source 有 `source_type`
- health / observability 能感知 source type
- 后续 `P1.4` 可按 source type 做统计和筛选

## 实施步骤

### Step 1：定义 adapter 抽象和 source type

完成：

- `SourceAdapter` 协议或等价抽象
- `rss` 作为第一个显式 `source_type`
- 与现有 source config 的兼容映射

### Step 2：把 RSS 路径收敛为 adapter

完成：

- RSS 抓取逻辑不再只以“特例函数”存在
- 主流程通过 adapter 层消费 RSS source

### Step 3：补一个非生产 fake adapter 测试对象

这一阶段不接真实新源，但建议在测试里增加：

- fake / in-memory adapter

用途：

- 验证 adapter contract 真的能支持“非 RSS source”
- 避免抽象只服务现有 RSS 实现

### Step 4：补文档和扩展点说明

至少写清：

- adapter 抽象是什么
- RSS adapter 在哪
- 下一步 `P1.4` 如何在不改主流程的情况下接新源

## 文件范围

建议主要修改：

- `products/tech_blog_monitor/fetcher.py`
- `products/tech_blog_monitor/feed_catalog.py`
- 可新增：
  - `products/tech_blog_monitor/source_adapters/__init__.py`
  - `products/tech_blog_monitor/source_adapters/base.py`
  - `products/tech_blog_monitor/source_adapters/rss_adapter.py`
- `products/tech_blog_monitor/test/test_fetcher.py`
- `products/tech_blog_monitor/README.md`

## 完成标准

`P1.3` 完成至少需要满足：

- 主抓取链路不再直接绑定 RSS 特例实现，而是通过 adapter 层运行
- RSS 相关现有测试语义不回归
- 新增一个 fake / in-memory adapter 测试，证明抽象可承载非 RSS source
- 不需要修改核心抓取主流程，就能为 `P1.4` 添加新 source adapter
- 本阶段不发生 `P1.4` 范围漂移

建议量化为：

- `test_fetcher.py` 及相关抓取测试全部通过
- adapter 化前后的 RSS fixture 结果保持一致
- 至少 `1` 个 fake adapter contract 测试通过

## 建议验证命令

```bash
uv run ruff check products/tech_blog_monitor
uv run pytest -q products/tech_blog_monitor/test/test_fetcher.py
uv run pytest -q products/tech_blog_monitor/test/test_monitor.py
```

如改动较大，可补跑：

```bash
uv run pytest -q products/tech_blog_monitor/test
```

## 风险

### 1. 抽象过度

如果一开始就做成大而全插件框架，会拖慢节奏，也容易和当前代码风格脱节。

### 2. RSS 回归

如果 adapter 化后 RSS 行为变了，说明 `P1.3` 没守住边界。

### 3. 假抽象

如果新增 adapter 接口，但主流程仍硬编码 RSS 分支，那不算完成。

### 4. 范围漂移

不要顺手把下面内容混进来：

- GitHub Releases 真接入
- HN / Reddit 扩源
- Article 大模型重构
- API 扩展

## Worker Prompt

你负责实现 `P1.3 Source Adapter`。

目标：

在不改变现有 RSS 主流程语义的前提下，把“数据源接入”从 RSS 特例抽成统一 adapter 模型，为 `P1.4` 扩源铺路。

执行基线文档：

- `docs/tech_blog_monitor/roadmap/P1_3_PLAN.md`

任务边界：

- 只做 adapter 抽象和 RSS adapter 接线
- 保持 `Article` 作为当前统一归一化对象
- 不做 `P1.4` 真实新源接入
- 不做 `P1.5 Internal Relevance`
- 不做前端 / API / delivery 扩展
- 不做大而全插件市场

你需要完成的交付：

- 最小 `SourceAdapter` 抽象
- `rss` source type
- `RssSourceAdapter` 或等价实现
- 主抓取链路通过 adapter 层运行
- fake / in-memory adapter contract 测试
- 最小文档说明

建议修改范围：

- `products/tech_blog_monitor/fetcher.py`
- `products/tech_blog_monitor/feed_catalog.py`
- `products/tech_blog_monitor/source_adapters/`
- `products/tech_blog_monitor/test/test_fetcher.py`
- `products/tech_blog_monitor/test/test_monitor.py`
- `products/tech_blog_monitor/README.md`

实现要求：

1. 先梳理当前 RSS 路径，把“RSS 抓取细节”和“主流程调度”拆开。
2. 定义最小 adapter 抽象，不要过度设计。
3. 让 RSS 成为第一个 adapter，但保持当前行为不变。
4. 保持 `Article` 不变，不要顺手做大字段改名。
5. 补一个 fake / in-memory adapter 测试，证明抽象不是只服务 RSS。
6. 保证 observability / health 至少还能感知 `source_type`。
7. 只做与 `P1.3` 直接相关的改动。

强约束：

- 不要顺手接入 GitHub Releases 或其他真实新源
- 不要把主流程继续硬编码成 RSS 特例
- 不要改 API、internal relevance、delivery
- 你不是一个人在代码库里工作，不要回退他人改动

完成标准：

- 主抓取链路通过 adapter 层运行
- RSS 行为和现有测试语义不回归
- 至少 `1` 个 fake adapter contract 测试通过
- 下一步 `P1.4` 可以在不改核心主流程的情况下接新源

建议验证命令：

```bash
uv run ruff check products/tech_blog_monitor
uv run pytest -q products/tech_blog_monitor/test/test_fetcher.py
uv run pytest -q products/tech_blog_monitor/test/test_monitor.py
```

如改动较大，可补跑：

```bash
uv run pytest -q products/tech_blog_monitor/test
```

最终输出请包含：

- 改了哪些文件
- adapter 抽象长什么样
- RSS 是如何接到 adapter 层的
- fake adapter 测试怎么证明抽象有效
- 测试结果
- 剩余限制

## Tester Prompt

你负责验收 `P1.3 Source Adapter`。

目标：

确认这批改动是否真的把“数据源接入”抽成了可扩展 adapter 层，同时没有打坏 RSS 主流程，也没有夹带 `P1.4` 扩源内容。

验收基线文档：

- `docs/tech_blog_monitor/roadmap/P1_3_PLAN.md`

重点检查：

- 是否存在清晰的 `SourceAdapter` 抽象
- 主抓取链路是否真的通过 adapter 层运行
- RSS 语义是否保持不变
- 是否存在 fake / in-memory adapter 测试，证明抽象可承载非 RSS source
- 是否发生 `P1.4` 范围漂移

重点文件：

- `products/tech_blog_monitor/fetcher.py`
- `products/tech_blog_monitor/feed_catalog.py`
- `products/tech_blog_monitor/source_adapters/`
- `products/tech_blog_monitor/test/test_fetcher.py`
- `products/tech_blog_monitor/test/test_monitor.py`
- `products/tech_blog_monitor/README.md`

请重点找下面几类问题：

1. 只是加了抽象名词，但主流程仍然硬编码 RSS。
2. adapter 设计过度，复杂度明显超出当前阶段需要。
3. RSS 行为发生回归，例如抓取结果、健康状态、过滤语义变化。
4. fake adapter 不存在，导致无法证明抽象真能承载非 RSS source。
5. 顺手接入了 GitHub Releases 或其他真实新源，发生范围漂移。
6. observability / health 丢失了原有信息。

建议复验命令：

```bash
uv run ruff check products/tech_blog_monitor
uv run pytest -q products/tech_blog_monitor/test/test_fetcher.py
uv run pytest -q products/tech_blog_monitor/test/test_monitor.py
```

如有必要，可补跑：

```bash
uv run pytest -q products/tech_blog_monitor/test
```

验收标准：

- 主链路 adapter 化完成
- RSS 测试无回归
- 至少 `1` 个 fake adapter contract 测试通过
- 无明显 `P1.4` 范围漂移
- 建议合入前有清晰测试证据

输出格式要求：

- 先给 `Findings`
- 按严重度排序
- 每条 finding 尽量带文件和行号
- 如果没有阻塞问题，明确写“未发现阻塞性问题”
- 最后给简短结论：是否建议合入，剩余非阻塞尾项是什么
