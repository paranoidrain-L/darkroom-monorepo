# Tech Blog Monitor Phase 5: 基础 RAG

更新时间：`2026-04-16`

## 目标

在现有历史资产层之上，提供最小可用的问答闭环：

- 正文切分为 article chunks
- 离线、确定性的 fake embedding / index
- mixed retrieval：关键词命中 + 元数据 + embedding 相似度
- QA 服务输出可追溯回答与 citation
- 无证据时显式拒答

## 当前实现边界

已落地：

- `article_chunks` 表，按文章维护 chunk 数据
- 自动 chunk 建库与 `v3 -> v4` 迁移回填
- 基于 hash bag-of-words 的确定性 embedding
- repository provider + `RetrievalRepository.retrieve_chunks(...)`
- `products.tech_blog_monitor.qa.answer_question(...)`
- `python -m products.tech_blog_monitor.qa_cli`
- `chunk_embedding_records` 结构化向量记录表
- PostgreSQL `pgvector` 兼容列与向量检索路径

当前仍未做：

- 真实向量模型
- reranker
- 多跳推理
- 复杂答案生成与摘要压缩
- HTTP API

## 设计说明

### Chunk 来源

优先级：

1. `clean_text`
2. `title + one_line_summary + rss_summary + why_it_matters + key_points`

这样可以保证：

- 有正文时，RAG 使用正文
- 无正文但已有 summary/enrichment 时，仍可最小可用

### Embedding

当前默认仍使用 deterministic fake embedding：

- token -> sha256 -> fixed bucket
- 64 维归一化向量
- 无外部依赖
- fixture 下完全可重复

它不追求真实语义效果，当前目标是：

- 为 Phase 5 建立稳定接口
- 满足离线测试和 citation 一致性约束
- 为 P1 的 `pgvector` 兼容路径和后续真实 embedding 留出 schema 与调用位点

### Retrieval

当前 retrieval 分两条路径：

- 若配置 `TECH_BLOG_DATABASE_URL` 且底层为 PostgreSQL，优先走 `ChunkEmbeddingRecordModel.embedding_vector`
- 否则回退到 sqlite / fake embedding 路径

排序信号：

- lexical overlap
- fake embedding cosine similarity
- 轻量 freshness bonus

返回前按 `article_id` 去重，避免单篇文章多个 chunk 淹没结果。

### QA

回答策略当前保持保守：

- 仅基于检索到的 chunk 生成事实性汇总
- citation URL 必须来自命中 chunk
- 证据分数不足时直接拒答

这保证了：

- 输出可追溯
- 不需要依赖在线 LLM 也能通过核心回归

当前 P1 状态下的判断：

- RAG 数据访问已经现代化到 repository provider
- 向量 schema 和 PostgreSQL 路径已经接通
- 但真实 embedding provider 尚未替换 fake embedding，因此当前仍属于“pgvector-compatible，而非真实语义向量 fully enabled”

## 测试门禁

Phase 5 补充的本地测试覆盖：

- deterministic embedding
- retrieval ranking
- citation consistency
- 无证据拒答
- QA CLI 缺库报错
- `v3 -> v4` schema migration 与 chunk backfill
- repository provider 路径
- PostgreSQL 可选集成测试
