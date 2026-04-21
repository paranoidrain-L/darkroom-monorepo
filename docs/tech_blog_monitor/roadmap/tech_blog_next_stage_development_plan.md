# Tech Blog Monitor Next Stage Development Plan

更新时间：`2026-04-20`

## 当前状态

截至 `2026-04-20`，下一阶段路线的执行状态可概括为：

- `P1.1`：已完成
- `P1.2`：已完成
- `P1.3`：已完成
- `P1.4`：已完成
- `P1.5`：已完成

当前对 `P1.3` 的判断：

- `SourceAdapter` 最小抽象已落地
- RSS 已被收敛为首个内置 adapter
- 主抓取链路已通过 adapter 分发
- fake adapter contract 测试已补齐
- 本地验收已通过：`ruff`、`test_fetcher.py`、`test_monitor.py`、全量 `products/tech_blog_monitor/test`

当前仍保留一个非阻塞收口项：

- `fetcher.py` 顶部模块说明和少量注释仍偏 RSS 表述，后续可做文字收口，但不影响将 `P1.3` 视为已完成

当前对 `P1.4` 的判断：

- 两类高信噪比非 RSS source 已接入：`github_releases` 与 `changelog`
- 默认 catalog 已启用 `uv Releases` 与 `FastAPI Release History`
- `test_source_adapters.py` 已补齐非 RSS 归一化与质量守门测试
- 本地验收已通过：`ruff`、`test_fetcher.py`、`test_monitor.py`、`test_retrieval_eval.py`、`test_source_adapters.py`、全量 `products/tech_blog_monitor/test`

当前剩余的是非阻塞收口项，不影响将 `P1.4` 视为已完成：

- 默认启用的新 source 仍只有 `2` 个，后续可在同一方向继续扩到第 `3` 个高价值源
- 如 source type 继续增加，可再补一份更完整的非 RSS source 配置 / 运维说明

当前对 `P1.5` 的判断：

- `P1_5_DESIGN.md` 与 `P1_5_PLAN.md` 已完成，设计与实现边界收口
- 第一版 `internal_relevance` 已落地，包含 profile loader、manifest scanner、rule-based scorer 与 relevance report
- `article_relevances` 独立持久化、repository/search 透传、Markdown/JSON 输出和主流程接线均已完成
- 本地验收已通过：`ruff`、`test_internal_relevance.py`、`test_monitor.py`、`test_api.py`、`test_search.py`、`test_archive_store.py`、全量 `products/tech_blog_monitor/test`

当前剩余的是非阻塞收口项，不影响将 `P1.5` 视为已完成：

- 当前仍是规则型 internal relevance 第一版，后续可继续扩展到 repo / team / role 粒度
- 暂未提供独立 relevance API，当前主要通过 article / search / report 结果消费
- manifest 扫描当前聚焦 Python / Node 高信号文件，`go.mod` / `Cargo.toml` 仍可后补

## 目标

这份文档用于规划 `tech_blog_monitor` 的下一阶段开发。

这一阶段不追求“大而全平台化”，而是围绕两个核心问题推进：

- 找得准
- 看得广

但两者的推进顺序不是完全并列，而是：

1. 先把 `Retrieve` 做到可评测、可优化
2. 再通过高信噪比扩源扩大覆盖面
3. 然后把外部情报和内部相关性连接起来
4. 最后再逐步进入更强的行动闭环

## 一句话结论

下一阶段最合理的主线是：

- `Retrieval Quality -> Source Adapter -> High-Signal Expansion -> Internal Relevance`

而不是：

- 先盲目扩很多源
- 或者先做重型知识图谱 / 自动化动作平台

## 这阶段要解决什么问题

当前系统已经有较强的：

- `Sense`
- `Understand`
- `Know`

但当前最明显的短板是：

- `Retrieve` 还停留在 baseline
- `Audit` 还没有稳定的评测闭环
- 扩源仍主要停留在 RSS
- 外部情报和内部代码/技术栈的关系还没有真正建立

所以这一阶段的任务不是继续堆更多模块，而是让已有能力真正形成下一步可扩展的底座。

## 总体优先级

### P1.1 Retrieval Evaluation Baseline

目标：

- 为 retrieval / QA 建立稳定、离线、可重复的评测基线

为什么先做：

- 没有 baseline，后续 embedding / ranking 升级无法判断是否变好
- 这是补 `S3* Audit` 的第一步

交付物：

- query set
- golden relevance labels
- retrieval eval 测试
- baseline 指标输出

完成标准：

- 本地一条命令跑出稳定指标
- 可用于 `P1.2` 前后对比

### P1.2 Real Embedding + Hybrid Ranking

目标：

- 在 `P1.1` 基线上，把 retrieval 从 baseline 提升到真实可用

为什么排第二：

- 现在 QA / insights 的上限被 retrieval 质量卡住
- 这是当前“智能体验”最大的瓶颈

交付物：

- 可选真实 embedding backend
- 保留 fake embedding fallback
- 更清晰的 lexical / semantic / freshness 混排
- 基于 baseline 的质量对比结果

完成标准：

- `MRR@10` 相对 `P1.1` baseline 提升至少 `15%`
- `Hit@5` 不低于 baseline，且至少一个 query bucket 有明确提升
- 无外部依赖环境仍能回退跑通

### P1.3 Source Adapter 抽象

目标：

- 把“数据源接入”从 RSS 特例抽成统一 adapter 模型

为什么这时做：

- retrieval 质量站稳后，扩源收益才不会被噪音吞掉
- 这是长期从 RSS 走向技术情报平台的必要台阶

交付物：

- `SourceAdapter` 抽象
- RSS adapter 兼容接线
- 统一 source type / fetch contract / metadata contract

完成标准：

- 不改现有主流程语义
- 新增 source 不需要继续复制 RSS 逻辑

### P1.4 High-Signal Source Expansion

目标：

- 在 adapter 基础上扩展第一批高信噪比新源

建议第一批来源：

- `GitHub Releases`
- 官方 changelog / release notes
- 结构化项目公告源

不建议第一批就主打：

- `Hacker News`
- `Reddit`
- 高噪音 discussions 流

原因：

- 当前系统的理解、检索、审计层还不够强，不适合先吃高噪音源

交付物：

- 2-3 个非 RSS 高价值源
- 统一归一化到 `Article` 或兼容资产模型
- source health / source type 可观测

完成标准：

- 新源贡献的日增文章量占比达到至少 `20%`
- 新源正文抽取成功率不低于现有主源平均水平的 `95%`
- 新源接入后，retrieval eval 核心指标相对 `P1.2` 不出现超过 `5%` 的回退

### P1.5 Internal Relevance Layer

目标：

- 建立“外部技术动态和内部是否相关”的第一层连接

为什么它比知识图谱更早：

- 这是内部工具的核心差异化能力
- 先解决“和我们有没有关系”，再解决“它在知识网络里怎么表示”

建议先做的最小版本：

- 技术栈画像
- dependency relevance
- repo-topic mapping
- source/article -> internal stack impact hint

落地路径：

1. 技术栈输入先采用双路径：
   - `stack_profile.yaml` 这类手工配置文件，作为权威覆盖层
   - repo 扫描结果，作为自动发现层
2. repo 扫描首批只支持高信号文件：
   - `requirements*.txt`
   - `pyproject.toml`
   - `package.json`
   - `go.mod`
   - `Cargo.toml`
3. 匹配分两级：
   - `L1`：库名 / 框架名精确或别名匹配，如 `fastapi`、`pydantic`、`grpc`
   - `L2`：主题级弱匹配，如 `gRPC performance`、`PostgreSQL indexing`
4. 第一版评分建议采用可解释规则分：
   - `dependency_match_score`
   - `topic_match_score`
   - `source_priority_score`
   - 汇总为 `relevance_score`
5. 第一版输出先做两种形态：
   - article 级 `relevance_score` / `relevance_reasons`
   - run 级或 insight 级 `internal relevance report`

交付物：

- 最小内部相关性模型
- article 或 insight 上的 relevance hint
- 可解释的规则或轻量匹配结果
- `P1.5 DESIGN.md`

完成标准：

- 至少支持 `1` 份手工技术栈画像输入和 `2` 类 repo manifest 自动扫描
- 对样例集中的高相关文章，`Recall@10 >= 0.8`
- article 结果可输出结构化 `relevance_score` 和 `relevance_reasons`
- 系统可以回答“这条动态是否和我们的技术栈相关”，且结果可解释

## 本阶段明确不做

这一阶段不建议优先投入：

- 完整知识图谱平台
- 重型 entity-relation 图数据库
- 大规模 HN / Reddit / 社区噪音流
- 高风险自动动作执行
- 完整多 Agent 平台治理
- 复杂前端产品化大改

原因很简单：

- 这些方向都建立在“检索质量站稳、扩源有节制、内部相关性可解释”之后

## 建议节奏

## Iteration A

重点：

- `P1.1 Retrieval Evaluation Baseline`
- `P1.2 Real Embedding + Hybrid Ranking`

交付结果：

- retrieval 可评测
- retrieval 有第一版真正可用的质量提升

## Iteration B

重点：

- `P1.3 Source Adapter`
- `P1.4 High-Signal Source Expansion`
- `P1.5 DESIGN.md`

交付结果：

- 非 RSS 新源可接入
- 第一批高质量外部信号扩进来
- `P1.5` 的输入、匹配粒度、输出形态在设计层收口

## Iteration C

重点：

- `P1.5 Internal Relevance Layer`

交付结果：

- 外部情报不再只是“外部新闻”
- 开始和内部技术栈发生关联

## 关键设计原则

### 1. 先补 `S3*`，再扩 `S1`

没有评测闭环时，扩更多源只会更快制造噪音。

### 2. 高信噪比优先

扩源顺序要按信号质量排，而不是按“看起来很丰富”排。

### 3. 先相关性，后图谱化

先做内部相关性，收益比早期重型图谱更高。

### 4. 自动动作后置

`Act` 必须建立在：

- 检索质量
- 审计能力
- 策略边界

都达到可用线之后。

## 阶段验收标准

这一阶段结束时，系统至少应达到下面状态：

- retrieval 有稳定 baseline，且有一版可证明变好的升级
- 系统不再是 RSS-only
- 第一批新源已通过统一 adapter 接入
- 外部动态开始具备内部相关性判断
- 下一步再做知识网络、个性化和行动闭环时，有清晰数据底座和质量底座

## 一句话路线

下一阶段不是“做更多功能”，而是：

- 先把情报系统的检索质量做实
- 再把情报入口从 RSS 扩到高价值多源
- 再把外部情报和内部上下文真正连起来
