# Tech Blog Monitor Capability-VSM Mapping

更新时间：`2026-04-18`

## 目标

这份文档用于把 `tech_blog_monitor` 的两套抽象统一起来：

- 能力抽象：系统“会什么”
- `VSM` 骨架：系统“如何形成闭环并保持可控”

重点不是再定义一批角色名，而是回答下面几个问题：

- 当前 8 类能力分别落在 `VSM` 的哪几层
- 当前能力主要集中在哪一层
- 哪些地方已经形成闭环，哪些地方还只是功能堆叠
- 下一步应该优先补哪一层，才能让系统更像一个真正的 Agent

## 一句话结论

当前 `tech_blog_monitor` 已经具备了比较强的：

- `Sense`
- `Understand`
- `Know`

以及基础可用的：

- `Retrieve`
- `Reason`
- `Ops`

但它仍然存在一个很明确的结构特征：

- 能力主要集中在 `S1`
- `S2 / S3` 有雏形
- `S3* / S4 / S5` 仍然偏弱

所以当前更准确的定义是：

- 一个已经具备 Agent 前半身能力的技术情报知识系统

而不是：

- 一个已经完成闭环的 Knowledge Agent

## 两层抽象如何连接

需要先明确一个原则：

- `8 类能力`和`VSM 6 层`不是一一对应关系

它们是两层不同抽象：

- 能力层定义“做什么”
- 骨架层定义“如何组织、协调、控制、审计和演进”

因此，一个能力往往会跨多个 `VSM` 层存在。

例如：

- `Retrieve` 不只是 `S1` 执行检索
- 还需要 `S3*` 评测检索质量
- 需要 `S4` 推动 ranking / embedding 迭代
- 需要 `S5` 定义什么场景允许自动回答

这也是为什么：

- “有能力”不等于“形成闭环”

## 8 类能力与 VSM 映射

| 能力 | 能力含义 | 主要落点 | 当前模块 | 当前成熟度 |
|---|---|---|---|---|
| `1. Sense` | 感知外部技术变化 | `S1 + S4` | `fetcher.py` `feed_catalog.py` `state.py` | `强` |
| `2. Understand` | 抽取正文、去噪、结构化理解 | `S1` | `content_fetcher.py` `extractors/` `content_quality.py` `analyzer.py` | `中上到强` |
| `3. Know` | 沉淀为长期知识资产 | `S1 + S2 + Infra` | `archive_store.py` `db/` `chunking.py` | `强` |
| `4. Retrieve` | 检索、召回、排序 | `S1 + S3* + S4` | `search.py` `retrieval.py` `db/repositories/` | `中` |
| `5. Reason` | 基于证据生成回答与归纳 | `S1 + S3*` | `qa.py` `insights.py` | `中` |
| `6. Act` | 任务化执行、修复、重跑 | `S1 + S2 + S3 + S5` | `tasks/runner.py` `local_scheduler.py` `orchestration/` `agent.py` | `弱到中` |
| `7. Audit` | 独立验证质量与伪成功 | `S3*` | `test/` `ops.py` `observability/` `content_quality.py` | `弱到中` |
| `8. Policy/Ops` | 稳态控制、策略边界、运营决策 | `S3 + S4 + S5` | `ops.py` `settings.py` `delivery.py` `feed_catalog.py` | `中` |

## 逐项解释

### 1. Sense

`Sense` 负责持续感知外部变化。

当前已经具备：

- 多 RSS 源抓取
- feed 级 `timeout / verify_ssl / headers / enabled`
- 重试与健康状态统计
- 增量状态记录

这部分主要是 `S1` 能力，因为它已经能执行感知动作。

但从 `VSM` 看，还缺一部分 `S4`：

- 还没有系统化的来源组合优化
- 还没有持续吸收“哪些来源更有价值”的外部反馈
- 还没有把 source portfolio 当作长期演进对象

结论：

- `Sense` 的执行能力已经比较强
- `Sense` 的演进能力还不强

### 2. Understand

`Understand` 负责把原始网页转成结构化内容。

当前已经具备：

- `Trafilatura` 主路径
- heuristic fallback
- 受控 `Playwright` fallback
- 正文质量状态，如 `empty / low_quality`
- enrichment 生成摘要、标签、topic、why it matters

这部分主要落在 `S1`，因为核心问题是“把内容处理出来”。

当前短板主要不是骨架问题，而是质量问题：

- 还缺更强的站点级规则
- 还缺更多真实样本下的 rebaseline

结论：

- `Understand` 是当前最接近产品可用线的能力之一

### 3. Know

`Know` 负责把结果沉淀成长期资产。

当前已经有：

- `runs`
- `articles`
- `run_articles`
- `article_contents`
- `article_enrichments`
- `article_chunks`
- `article_search_documents`
- `chunk_embedding_records`
- `deliveries`
- `feedback`
- `task_records`

这说明系统已经不只是产出报告，而是在建设知识底座。

这部分在 `VSM` 上主要落在：

- `S1`：写入资产
- `S2`：组织上下文和数据流
- `Infra`：承载知识库本身

当前短板：

- 资产仍偏 article / chunk 级
- 还没有更高层的 topic / entity / event 结构化长期记忆

结论：

- `Know` 是当前系统最扎实的能力之一

### 4. Retrieve

`Retrieve` 负责在知识资产上找到相关证据。

当前已经有：

- search API / CLI
- retrieval repository
- lexical overlap
- fake embedding
- basic hybrid score
- freshness bonus

但这一层仍然明显处在 baseline 状态。

它在 `VSM` 上至少跨三层：

- `S1`：执行检索与排序
- `S3*`：评测检索质量
- `S4`：推动 ranking / embedding 升级

当前问题是：

- `S1` 已有 baseline
- `S3*` 的 eval 基线还不够成熟
- `S4` 的 retrieval evolution 机制还较弱

结论：

- `Retrieve` 已有功能，但还没有形成强闭环

### 5. Reason

`Reason` 负责把证据转成回答、总结和洞察。

当前已经有：

- grounded QA
- citation
- insights 聚合
- why / topic / summary 这类基础归纳

当前主要落在：

- `S1`：生成回答和洞察
- `S3*`：验证回答是否真正 grounded

当前短板：

- 还偏“证据拼接式回答”
- 还没有更强的 compare / synthesize / plan 型 reasoning
- 还缺 answer quality 的独立审计

结论：

- `Reason` 已经可用，但还没有达到强 Agent 水平

### 6. Act

`Act` 负责把能力变成任务化动作。

当前已经有：

- `LocalTaskRunner`
- `task_records`
- `manual_run`
- `scheduled_run`
- `rebuild_*_index`
- local scheduler
- orchestration adapter

从 `VSM` 看，这层天然跨层：

- `S1`：执行任务
- `S2`：拆任务与编排
- `S3`：控制重试、队列、并发
- `S5`：定义哪些动作允许自动执行

当前问题：

- 任务种类还不够细
- article-level 修复任务尚未补齐
- 自动动作边界还没有制度化

结论：

- `Act` 有骨架，但远未成熟

### 7. Audit

`Audit` 负责绕过“主流程自我汇报”，直接看真实信号。

当前已经有：

- 测试
- observability
- ops summary
- content quality status
- 失败记录和任务状态

这部分主要对应 `S3*`。

当前最明显的缺口：

- retrieval eval 仍需强化
- QA 质量缺少稳定审计基线
- source quality 还没有独立质量回路
- “执行成功但语义错误”的检测还不够强

结论：

- `Audit` 已经有入口，但仍是当前系统最值得补的一层之一

### 8. Policy / Ops

`Policy / Ops` 负责稳态控制、优先级和边界。

当前已经有：

- ops summary
- 任务状态与失败样本
- delivery cadence / rate limit / retry
- feed 配置和运行配置

从 `VSM` 看，这层主要落在：

- `S3`：吞吐、失败恢复、运行稳态
- `S4`：来源组合和能力升级方向
- `S5`：目标函数、自动动作边界、高风险阻断

当前问题：

- `S3` 还只是本地优先的轻量控制层
- `S4` 的外部变化吸收还弱
- `S5` 的策略边界还没有固化

结论：

- `Ops` 已经开始形成
- `Policy` 仍然偏弱

## 按 VSM 看当前能力分布

如果反过来从 `VSM` 视角看当前能力，会更清楚：

### S1：最强

当前大部分能力都已经落在 `S1`：

- 抓取
- 抽取
- enrichment
- search
- retrieval
- QA
- insights
- delivery
- feedback

这说明系统“能做事”。

### S2：有雏形

当前已经有：

- CLI
- API
- task runner
- scheduler
- orchestration adapter

这说明系统开始具备“任务协调”能力。

但还没有完全成熟的：

- 子任务依赖模型
- 上下文交接模型
- 更细粒度的任务编排边界

### S3：中等

当前已经有：

- observability
- ops summary
- task status
- retry / cadence / rate limit

但它更像“轻量控制层”，还不是强 runtime control。

### S3*：偏弱

当前已经有：

- tests
- content quality gate
- failure sample
- metrics

但独立审计仍然是当前闭环里最薄的部分之一。

### S4：偏弱

当前还缺：

- 系统化的来源组合优化
- 系统化的 retrieval / QA eval 演进
- 对用户需求变化和模型变化的持续吸收

### S5：偏弱

当前还缺：

- 长期目标函数
- 自动动作审批边界
- 高风险动作阻断规则
- 明确的“能自动做什么、不能自动做什么”

## 当前阶段最重要的结构性判断

当前最大的问题不是“没有能力”，而是：

- 关键能力大多已经有了 `S1` 实现
- 但还没有被 `S3* / S4 / S5` 充分管起来

因此系统现在更像：

- 一个功能丰富的知识处理管线

而不是：

- 一个已经形成完整闭环的 Agent

## 下一步建设顺序

如果要让系统真正沿着 `VSM` 骨架成长，建议按下面顺序补：

### 1. 先补 `S3*`

优先项：

- retrieval evaluation baseline
- QA quality baseline
- source quality audit
- low quality / false positive / false negative 回归样本

原因：

- 没有独立审计，系统容易长期伪成功

### 2. 再补 `S4`

优先项：

- source portfolio 管理
- retrieval / ranking 的持续迭代机制
- 评测集与能力基线的持续维护

原因：

- 没有外部感知，系统只会优化当前，不会持续适应

### 3. 再补 `S5`

优先项：

- 自动动作边界
- 风险分级
- 哪些任务允许自动执行、哪些必须人工确认

原因：

- 没有边界，`Act` 只会越长越危险

### 4. 最后再把 `Act` 做强

优先项：

- article-level 修复任务
- 可恢复 delivery 链路
- 主题级 watch / brief / refresh 任务

原因：

- `Act` 必须建立在审计、策略和控制之上

## 一句话原则

对于 `tech_blog_monitor` 来说：

- 不是先堆更多执行能力，就会自然变成 Agent

真正的演进路径应该是：

- 先把 `Sense / Understand / Know / Retrieve / Reason` 做成稳定底座
- 再用 `S3* / S4 / S5` 把它们放进可控闭环
- 最后再把 `Act` 做成真正可靠的 Agent 行为
