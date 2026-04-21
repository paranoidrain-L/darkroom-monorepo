# Tech Blog Execution Roadmap

## 当前基线

`tech_blog_monitor` 当前已经具备以下能力：

- 多 RSS 源并发抓取
- feed 级超时 / SSL / headers / enabled 配置
- 重试退避与 feed 健康状态统计
- URL 去重、时效过滤、关键词过滤、全局排序
- Markdown 报告输出
- JSON 结构化输出
- 增量状态记录与新增文章视图
- 历史归档（按天 / 周）
- Phase 1 sqlite 历史资产存储
- Phase 2 启发式正文抓取与正文清洗
- Phase 3 结构化 enrichment
- Phase 4 基础检索 API 与 CLI
- Phase 5 基础 RAG（chunk / mixed retrieval / QA CLI）
- Phase 6 基础 insights（主题簇 / 趋势 / 来源对比 / 时间线）
- Phase 7 基础产品化输出（role digest / webhook delivery / feedback）
- AI 摘要与趋势分析降级处理（需持续测试确认）
- 配置解析与统一校验失败返回 `exit code 1`（需持续测试确认）

这意味着后续 roadmap 不应再重复规划“配置收口”“增量状态”“归档基线”等已落地能力，而应基于当前代码进入下一阶段的产品演进。

## Testing Baseline

以下规则适用于所有 phase：

- 每个 phase 完成时必须运行 `pytest -q products/tech_blog_monitor/test`
- 涉及抓取、归档、正文抽取、搜索、RAG、推送的 phase，必须提供不依赖外网的 fixture 测试
- 真实 RSS 冒烟只能作为补充验收，不能作为唯一测试依据
- 涉及 AI 输出的功能必须覆盖以下情况：
- fake client
- 非法输出
- 空输出
- 部分成功
- client 初始化失败
- 涉及 schema、archive、state、DB 的功能必须覆盖以下情况：
- backward compatibility tests
- migration tests
- 旧数据读取兼容性
- 涉及搜索、RAG、趋势分析的功能必须提供：
- golden corpus
- 可重复评测查询集
- 排序或召回质量门槛

## 全局回归门禁

所有 phase 合入前至少应确认：

- 单元测试通过
- 关键集成测试通过
- 失败 / 降级路径可控
- 现有 CLI 行为不被破坏
- 历史产物兼容性未被破坏

## 基线测试清单

在进入后续 phase 之前，应先确认当前基线具备以下测试：

- 配置错误路径
- AI 降级路径
- 增量模式连续两次运行
- JSON 输出
- 历史归档
- 真实 RSS 冒烟

这些属于 rebaseline checklist，而不是默认视为“已自动可信”。

## Phase 0: Rebaseline

目标：先对齐文档、代码和真实能力，避免 roadmap 落后于实现。

状态：已完成（文档与本地测试基线对齐），剩余 1 项人工真实 RSS 冒烟记录。

- 盘点当前已完成能力
- 将已完成项从未来 roadmap 中剔除
- 明确哪些能力属于“已落地但待优化”，哪些属于“尚未开始”
- 对齐 README、TODO、RAG 规划文档之间的表述

交付：

- 更新后的 roadmap
- 当前能力边界说明
- 已完成 / 待优化 / 未开始三类清单
- rebaseline 测试清单

测试交付：

- 基线单元测试清单
- 配置错误路径测试
- AI 降级路径测试
- 增量连续两次运行测试
- 真实 RSS 冒烟记录

失败 / 降级路径：

- 非法环境变量
- 坏 YAML
- AI backend 非法或初始化失败
- 抓取成功但 AI 分析失败
- 第二次运行无新增文章

回归门禁：

- 当前基线能力都有对应测试或人工验收记录
- 文档描述与当前代码一致

验收：

- 不再把已实现能力误写成未来阶段目标
- baseline 测试项全部有对应测试或记录

执行记录：

- 当前能力边界、基线测试清单、人工冒烟状态见 `docs/tech_blog_monitor/roadmap/tech_blog_rebaseline.md`
- 模块入口说明见 `products/tech_blog_monitor/README.md`

## Phase 1: 可检索历史资产

目标：把“归档文件”升级为“可管理的历史文章资产”。

当前已有归档与 JSON 输出，但仍偏运行产物，不是面向检索和复用的资产层。

状态：已完成最小可用版本。

- 统一历史文章元数据格式
- 明确文章唯一标识、内容 hash、来源标识规范
- 明确运行批次、文章记录、状态记录之间的关系
- 为后续查询准备稳定的数据组织方式

交付：

- 稳定的 Article schema 基线
- 历史文章元数据规范
- 运行批次与文章记录的存储约定
- 面向检索的 JSON / DB 基础结构设计

测试交付：

- Article schema contract tests
- archive / state backward compatibility tests
- migration tests
- 唯一标识与 content hash 稳定性测试
- 旧 JSON / 旧 state / 旧 archive 读取测试

失败 / 降级路径：

- 缺字段历史记录
- schema 版本不一致
- 旧 state 文件读取失败
- 历史归档目录部分损坏

回归门禁：

- 旧产物仍可被读取或迁移
- schema 变更不会破坏已有数据

验收：

- 历史文章可稳定索引和回查
- 归档数据可作为后续搜索与 RAG 的输入，而不是一次性产物

执行记录：

- sqlite 资产层实现见 `products/tech_blog_monitor/archive_store.py`
- 设计说明见 `docs/tech_blog_monitor/phases/tech_blog_phase1_asset_design.md`
- 当前最小查询接口已具备，完整 search CLI / API 留在 Phase 4

## Phase 2: 正文抓取与正文清洗

目标：从“RSS 摘要系统”升级为“文章内容系统”。

当前系统主要依赖 RSS 标题和摘要，尚未具备正文抓取能力，因此这应作为独立 phase，而不是与归档混在一起。

状态：已完成最小可用版本。

- 为文章增加正文抓取能力
- 支持 HTML 抽取与正文清洗
- 区分 RSS 摘要、正文全文、清洗正文
- 对抓取失败和正文缺失给出明确状态

交付：

- article full text 获取流程
- 清洗后的正文文本
- 原始内容与清洗内容的存储约定
- 正文抓取失败状态模型

测试交付：

- 本地 HTML fixture corpus
- 正文抽取单元测试
- 编码与清洗测试
- 无正文 / 跳转 / 403 / 超长页面测试
- fixture 驱动的集成测试

建议 fixture 覆盖：

- 正常正文页面
- 403 / 反爬页面
- 无正文页面
- 正文在 script / json-ld 中
- 多语言页面
- 超长页面
- 跳转链接页面
- 编码异常页面

失败 / 降级路径：

- 正文抓取失败
- 只保留 RSS 摘要
- 编码识别失败
- 正文为空但元数据存在

回归门禁：

- 不依赖真实网页临时状态也能稳定测试正文抽取
- 正文抓取失败不会破坏现有 RSS 路径

验收：

- 历史文章不再只依赖 RSS 摘要
- 至少部分核心来源具备可用正文
- 系统能区分“有摘要无正文”和“正文抓取成功”

执行记录：

- 启发式正文抓取实现见 `products/tech_blog_monitor/content_fetcher.py`
- sqlite 资产层已扩展 `article_contents` 表
- 设计说明见 `docs/tech_blog_monitor/phases/tech_blog_phase2_content_fetch.md`
- 当前仍未引入站点级规则或专用正文解析器

## Phase 3: Structured Enrichment

目标：让单篇文章不仅可存储，还能被快速理解和结构化消费。

状态：已完成最小可用版本。

- 为文章补充结构化理解字段
- 输出单篇文章级别的摘要与重点
- 支持从“文章列表”升级到“文章卡片”

建议字段：

- `one_line_summary`
- `key_points`
- `why_it_matters`
- `recommended_for`
- `tags`
- `topic`

交付：

- enrichment 数据结构
- 单篇文章结构化理解结果
- 支持人阅读和系统检索的 enriched article

测试交付：

- enrichment schema validation tests
- fake AI client tests
- 非法 JSON / 空输出 / 部分成功测试
- 批量 enrichment 中单篇失败隔离测试
- 降级行为测试

失败 / 降级路径：

- `key_points` 不是 list
- `tags` 为空
- AI 返回非法 JSON
- 部分文章 enrichment 失败
- 全量 enrichment 失败时保留原始文章

回归门禁：

- enrichment 失败不会打断整批处理
- enrichment 输出满足 schema 约束

验收：

- 用户无需读全文也能判断文章是否值得看
- 结构化字段可用于检索、推荐、聚类和后续 RAG

执行记录：

- enrichment 实现见 `products/tech_blog_monitor/analyzer.py`
- sqlite 资产层已扩展 `article_enrichments` 表
- 设计说明见 `docs/tech_blog_monitor/phases/tech_blog_phase3_enrichment.md`
- 当前仍未实现完整文章卡片视图与 enrichment 历史版本化

## Phase 4: Search and Retrieval

目标：先做检索，再做问答。

在正文与结构化字段准备充分后，先建设可靠的搜索与召回能力。

状态：已完成最小可用版本。

- 支持关键词搜索
- 支持按来源、时间、主题、标签筛选
- 支持历史相关文章集合查询
- 建立文章级和字段级检索能力

交付：

- 历史文章搜索接口
- 基础查询 CLI / API
- 时间过滤、来源过滤、主题过滤能力
- 检索结果排序策略

测试交付：

- small golden corpus
- 固定查询集
- 排序验证测试
- 时间过滤边界测试
- 来源 / 标签 / 主题过滤测试
- 空结果行为测试

失败 / 降级路径：

- 无匹配结果
- 时间范围为空
- 标签不存在
- 索引部分缺失

回归门禁：

- golden corpus 上的查询结果可重复
- 排序与过滤结果具备稳定性

验收：

- 可稳定回答“最近 30 天有哪些相关文章”
- 可按主题、来源、时间快速定位文章集合

执行记录：

- 检索实现见 `products/tech_blog_monitor/search.py`
- CLI 入口见 `products/tech_blog_monitor/search_cli.py`
- 设计说明见 `docs/tech_blog_monitor/phases/tech_blog_phase4_search.md`
- 当前仍未引入倒排索引、HTTP API、向量检索或 rerank

## Phase 5: RAG 基础版

目标：从搜索升级为基于历史文章的问答能力。

状态：已完成最小可用版本。

- 正文 chunk 切分
- embedding 建库
- 混合检索：关键词 + 元数据 + 向量
- 基于命中文章生成回答
- 回答附出处和原文链接

交付：

- article chunk 数据结构
- embedding / index 构建流程
- QA 服务
- 带证据的回答格式

测试交付：

- retrieval eval
- citation consistency tests
- answer faithfulness tests
- 无证据拒答 / 降级测试
- fake embedding / fake retrieval fixture

失败 / 降级路径：

- 检索不到足够证据
- citation 缺失
- citation URL 不在命中文章中
- 回答引用未检索内容
- embedding / index 不可用

回归门禁：

- citation 必须存在
- citation URL 必须来自命中文章
- 无证据时系统必须拒答或降级

验收：

- 回答可追溯到具体文章与链接
- 至少支持主题问答、时间问答、来源对比

执行记录：

- chunk 与 mixed retrieval 实现见 `products/tech_blog_monitor/chunking.py`、`products/tech_blog_monitor/retrieval.py`
- QA 服务与 CLI 见 `products/tech_blog_monitor/qa.py`、`products/tech_blog_monitor/qa_cli.py`
- 设计说明见 `docs/tech_blog_monitor/phases/tech_blog_phase5_rag.md`
- 当前仍未引入真实向量模型、reranker、多跳推理或 HTTP API

## Phase 6: 分析型产品能力

目标：从“回答问题”升级为“输出洞察”。

状态：已完成最小可用版本。

- 主题聚类
- 趋势变化分析
- 多来源对比
- 时间线生成
- 热点信号提取

交付：

- 主题簇输出
- 趋势分析视图
- 多来源对比报告
- 时间演进摘要

测试交付：

- 合成趋势数据集
- 主题上升 / 下降识别测试
- 多来源差异测试
- 时间线输出稳定性测试

失败 / 降级路径：

- 样本不足
- 趋势不显著
- 多来源数据分布不均
- 分析结果不满足阈值时降级为事实汇总

回归门禁：

- 在合成数据集上能识别预期的主题变化
- 趋势输出不完全依赖主观判断

验收：

- 系统不仅能检索文章，还能解释“这个方向发生了什么变化”

执行记录：

- insights 实现见 `products/tech_blog_monitor/insights.py`
- CLI 入口见 `products/tech_blog_monitor/insights_cli.py`
- 设计说明见 `docs/tech_blog_monitor/phases/tech_blog_phase6_insights.md`
- 当前仍未引入真正聚类模型、统计显著性检验或可视化 dashboard

## Phase 7: 产品化输出

目标：让系统变成团队可持续使用的产品，而不仅是本地脚本。

状态：已完成最小可用版本。

- 飞书推送
- 定制日报 / 周报
- 多角色视图
- 用户反馈闭环
- 推荐阅读与热点摘要

交付：

- 分发渠道
- 反馈机制
- 面向不同角色的输出模板

测试交付：

- 推送幂等测试
- 失败重试测试
- 限流测试
- 消息格式测试
- 用户反馈落库测试
- 定时边界测试

失败 / 降级路径：

- 重复推送
- 推送失败重试
- 下游限流
- 反馈写入失败
- 日报 / 周报边界时间错误

回归门禁：

- 推送链路具备幂等和重试保障
- 用户反馈可被稳定记录和回查

验收：

- 用户可稳定接收和消费内容
- 产品具备使用反馈与持续优化闭环

执行记录：

- delivery / feedback 实现见 `products/tech_blog_monitor/delivery.py`、`products/tech_blog_monitor/feedback.py`
- 主流程接入见 `products/tech_blog_monitor/monitor.py`
- 设计说明见 `docs/tech_blog_monitor/phases/tech_blog_phase7_productization.md`
- 当前仍未接真实飞书适配器、push queue / worker 分离部署、用户级订阅配置

## 执行原则

1. 先重做基线，再规划下一步。
2. 先做“可检索历史资产”，不要过早抽大量接口。
3. 先补正文能力，再做结构化理解和 RAG。
4. 先把历史文章变成稳定资产，再做问答和洞察。
5. 真实冒烟只做补充，不替代 fixture、golden corpus 和回归测试。

## 推荐优先级

1. `Phase 0`
2. `Phase 1`
3. `Phase 2`
4. `Phase 3`
5. `Phase 4`
6. `Phase 5`
7. `Phase 6`
8. `Phase 7`
