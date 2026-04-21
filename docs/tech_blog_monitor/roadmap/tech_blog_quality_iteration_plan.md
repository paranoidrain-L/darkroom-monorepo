# Tech Blog Monitor Quality Iteration Plan

更新时间：`2026-04-17`

## 目标

这份文档描述的是 `tech_blog_monitor` 在 `P2` 收口之后的一轮“质量优先”迭代。

这一轮不追求继续扩系统边界，而是优先提升：

- retrieval / QA 的可评测性与可信度
- 核心来源正文抽取命中率
- delivery 链路的恢复能力

一句话目标：

把当前系统从“功能基本齐全”推进到“内容质量更可控、检索质量可验证、投递失败更容易恢复”的状态。

## 为什么先做质量

当前最显著的短板不是缺入口，而是：

- retrieval 仍以 `fake embedding + lexical overlap` 为主，缺少稳定评测基线
- 正文抽取已经完成通用链路升级，但高价值源还缺站点级规则
- delivery 已有幂等 / 重试 / 限流，但仍偏同步链路，恢复成本较高

这意味着：

- 如果先做更多 UI / orchestration，用户看到的仍可能是“不够准”的结果
- 如果先换 retrieval 而没有 eval 基线，就无法判断“变好了还是只是变了”

因此本轮顺序必须是：

1. 先建立 retrieval evaluation baseline
2. 再基于 eval 升级 ranking / embedding
3. 再对高价值来源做站点级正文规则
4. 最后把 delivery 做成最小可恢复链路

## 本轮范围

本轮只做以下四项：

- `P1.1` retrieval evaluation 基线
- `P1.2` 在 eval 基线上做 embedding / ranking 升级
- `P1.3` 只做 2-3 个高价值源的站点级正文规则
- `P1.4` delivery 最小异步化或可恢复化

本轮不做：

- 完整前端
- Prefect deployment lifecycle
- 大规模更多 insights 花样
- 大范围 source rule pack 扩张
- 多租户 / 权限 / 平台运营层改造

## 两周顺序

### 第 1 周

- `P1.1` retrieval evaluation 基线
- `P1.2` retrieval 升级的最小实验实现

第 1 周的交付物应该是：

- 有稳定 query set / golden set / 评分脚本
- 能比较“旧排序”和“新排序”
- 至少一版升级后的 retrieval 可以在同一套基线上评估

### 第 2 周

- `P1.3` 2-3 个高价值源的站点级正文规则
- `P1.4` delivery 最小异步化或可恢复化

第 2 周的交付物应该是：

- 核心来源正文抽取命中率明显改善
- delivery 失败不必依赖整次 run 重做
- 质量提升可以通过 fixture / regression / smoke 明确体现

## P1.1：Retrieval Evaluation Baseline

### 目标

给 retrieval / QA 建立一套可重复评测基线，使后续排名升级有明确判断标准。

### 当前问题

- 现在有 retrieval 和 QA 功能，但缺少独立的 evaluation 基线
- 改 ranking 容易只看“主观上像更好”
- 现在的 `fake embedding` 只是技术占位，不适合直接当质量标准

### 建议交付

1. 增加最小 query set

至少覆盖：

- topic query
- source-aware query
- trend / why / compare 类 query
- 同义表达 query
- lexical overlap 弱但语义相关 query

2. 增加 golden corpus / relevance label

建议先做小而稳的一版：

- 15-30 个 query
- 每个 query 1-5 个相关 article / chunk
- 用 fixture / sqlite 测试库保证可重复

3. 增加 evaluation 脚本或测试辅助

至少输出：

- recall@k
- hit@k
- mrr 或简化 rank score

4. 明确 baseline 报告格式

建议至少记录：

- 当前 retrieval 版本
- query 数量
- 各指标结果
- 与上一次基线对比

### 主要文件范围

- `products/tech_blog_monitor/retrieval.py`
- `products/tech_blog_monitor/qa.py`
- `products/tech_blog_monitor/test/test_qa.py`
- 新增建议：
  - `products/tech_blog_monitor/test/test_retrieval_eval.py`
  - `products/tech_blog_monitor/test/fixtures/retrieval_eval_*.json`

### 预计工作量

- `M`

### 风险

- query set 太小会导致评测失真
- relevance 标注如果不稳定，会让后续升级没有参考价值

### 验收

- 可以在本地一条命令跑出稳定 retrieval eval
- baseline 结果能区分 lexical-only 与 mixed retrieval 的差异
- 后续 ranking 变化可以用同一套 baseline 回归

## P1.2：Embedding / Ranking 升级

### 目标

在 `P1.1` 的基线上，把 retrieval 从“baseline 可用”提升到“质量更可信”。

### 当前问题

- `build_fake_embedding(...)` 仍然是 deterministic 占位实现
- 当前排序仍然高度依赖 lexical overlap
- 对语义相关但词面不重合的问题表现有限

### 建议策略

不要一步到位做“完整真实 embedding 平台”，本轮只做一版有评测支撑的升级。

建议优先顺序：

1. 重构 ranking 参数，使 lexical / vector / freshness 权重可调
2. 增加 query-aware rerank 逻辑的最小版本
3. 如果已有稳定 provider 可用，再接一版真实 embedding backend
4. 保留 fallback 到 fake embedding，避免本地测试依赖外部服务

### 建议交付

至少完成以下之一：

- `lexical + semantic + freshness` 的更合理组合排序
- 或引入可选真实 embedding provider，同时保留 fake fallback

更推荐的落地方式：

- 先让 ranker 结构清晰、参数可实验
- 再让真实 embedding 作为可选增强，而不是强依赖

### 主要文件范围

- `products/tech_blog_monitor/retrieval.py`
- `products/tech_blog_monitor/db/repositories/retrieval_repository.py`
- `products/tech_blog_monitor/qa.py`
- `products/tech_blog_monitor/test/test_qa.py`
- `products/tech_blog_monitor/test/test_postgres_integration.py`
- `products/tech_blog_monitor/test/test_retrieval_eval.py`

### 预计工作量

- `M-L`

### 风险

- 直接引入真实 embedding provider 会拉高环境复杂度
- 如果没有 `P1.1` 先行，容易陷入“改了很多但无法证明变好”

### 验收

- 在 `P1.1` 基线上，至少一个核心指标显著改善
- 本地测试仍能在无外部依赖情况下跑通
- Postgres / sqlite 路径语义不漂移

## P1.3：2-3 个高价值源的站点级正文规则

### 目标

不要泛化地继续调通用 extractor，而是直接提升高价值源命中率。

### 范围约束

本轮只做 2-3 个高价值来源，不做 5-10 个，不做“大而全规则库”。

优先来源建议按下面标准选：

- 高频出现在内部阅读链路
- 当前正文抽取命中率不稳定
- 页面结构相对稳定

### 建议策略

1. 先定义 rule pack 机制

至少支持：

- 按域名匹配
- 自定义正文块优先级
- 特定噪音块剔除
- 自定义 metadata 提取

2. 再为 2-3 个来源落规则

建议优先从：

- 一个研究博客
- 一个工程博客
- 一个内容结构复杂或 JS-heavy 来源

3. fixture 先行

每个站点规则都必须有离线 fixture，不依赖真实网页临时状态

### 主要文件范围

- `products/tech_blog_monitor/content_fetcher.py`
- `products/tech_blog_monitor/extractors/heuristic_extractor.py`
- 新增建议：
  - `products/tech_blog_monitor/extractors/site_rules.py`
  - `products/tech_blog_monitor/extractors/rule_packs/*.py`
- `products/tech_blog_monitor/test/test_content_fetcher.py`
- `products/tech_blog_monitor/test/fixtures/*`

### 预计工作量

- `M`

### 风险

- 直接硬编码到主流程里，会让后续规则越积越乱
- 如果没有 rule pack 抽象，会形成不可维护的 if/else 链

### 验收

- 2-3 个目标源的正文提取质量明显改善
- 新规则不破坏现有通用路径
- 每条规则有 fixture 和回归测试

## P1.4：Delivery 最小异步化或可恢复化

### 目标

让 delivery 从“同步发送 + 本地重试”提升到“失败更容易恢复、链路更适合持续运行”。

### 当前问题

- delivery 目前仍主要挂在 run 主链路后部
- 虽然已有幂等 / 重试 / 限流，但恢复动作仍偏人工
- 若未来 delivery 数量上升，同步路径会拖慢或污染主 run

### 建议策略

本轮只做“最小异步化或可恢复化”，不做完整消息系统。

建议两种可接受实现：

1. 可恢复化优先

- run 主链路只 enqueue
- dispatch 改为独立任务
- 提供 `retry pending deliveries` / `drain deliveries` 入口

2. 最小异步化

- 使用本地任务模型或 sidecar worker 处理 pending deliveries
- 保持现有 ArchiveStore / repository 语义不大改

### 建议交付

至少完成以下之一：

- `dispatch_delivery` 从主链路拆为独立可重放任务
- 新增 CLI/API 入口，允许对 pending / failed delivery 重试

### 主要文件范围

- `products/tech_blog_monitor/delivery.py`
- `products/tech_blog_monitor/monitor.py`
- `products/tech_blog_monitor/agent.py`
- `products/tech_blog_monitor/tasks/runner.py`
- `products/tech_blog_monitor/db/repositories/delivery_repository.py`
- `products/tech_blog_monitor/test/test_delivery.py`
- `products/tech_blog_monitor/test/test_monitor.py`

### 预计工作量

- `M`

### 风险

- 如果拆得过重，会和下一轮 orchestration 工作重叠
- 如果只改状态不改触发入口，恢复收益会有限

### 验收

- delivery 失败后可单独重试，不需要整次 run 重做
- 主 run 对 delivery 的同步依赖减弱
- 原有幂等 / 限流 / 重试语义保持稳定

## 建议实施顺序

严格按下面顺序推进：

1. `P1.1` retrieval eval baseline
2. `P1.2` retrieval / ranking upgrade
3. `P1.3` 2-3 个高价值源的 site rules
4. `P1.4` delivery recoverability

不要采用下面顺序：

1. 先换 embedding
2. 再补 eval
3. 再堆很多站点规则

这样风险最大，也最容易产生“改动很多但收益不清楚”的局面。

## 推荐 Worker 拆分

如果要并行推进，建议这样拆：

- Worker A：`P1.1` retrieval eval baseline
- Worker B：`P1.2` retrieval ranker / embedding upgrade
- Worker C：`P1.3` site rule pack + fixtures
- Worker D：`P1.4` delivery recoverability

但 critical path 仍然是：

- Worker A 先完成 baseline
- Worker B 再基于 baseline 迭代

## 测试基线

本轮合入前至少运行：

```bash
uv run pytest -q products/tech_blog_monitor/test
uv run ruff check products/tech_blog_monitor
```

新增测试建议至少包括：

- `test_retrieval_eval.py`
- `test_content_fetcher.py` 中的 site rule fixtures
- `test_delivery.py` 中的 delivery retry / drain / recoverability 用例

## 完成定义

满足以下条件，可认为这轮“质量优先迭代”完成：

- retrieval / QA 有稳定 eval baseline
- retrieval 升级能在 baseline 上证明收益
- 2-3 个高价值来源具备站点级正文规则并有 fixture 回归
- delivery 失败后可单独恢复，不依赖整次 run 重做

## 下一步

如果这轮完成，再考虑下一轮优先级：

1. article-level `reextract_content` / `reenrich_articles`
2. `POST /qa` 与 task trigger API 闭环
3. 内部运营前端
