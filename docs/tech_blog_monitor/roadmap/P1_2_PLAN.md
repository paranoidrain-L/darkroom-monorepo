# P1.2 Real Embedding And Hybrid Ranking Plan

更新时间：`2026-04-18`

## 目标

`P1.2` 的目标是在 `P1.1 retrieval evaluation baseline` 之上，把当前的 baseline retrieval 升级为真正可用的混合检索能力。

这一阶段要解决的问题不是“继续补功能入口”，而是：

- 让 retrieval 质量有实质提升
- 让 QA / insights 的证据质量随之提升
- 保持本地无外部依赖环境仍可运行
- 不破坏 sqlite / PostgreSQL 双路径兼容

一句话目标：

- `在可评测基线上，把 fake embedding + lexical overlap 提升为可选真实 embedding + 可解释 hybrid ranking`

## 范围

本阶段包含：

- 可选真实 embedding backend
- fake embedding fallback
- hybrid ranking 结构重构
- 基于 `P1.1` baseline 的质量对比
- 必要测试与最小文档更新

本阶段不包含：

- `P1.3 Source Adapter`
- 新数据源接入
- `P1.5 Internal Relevance`
- 前端扩展
- Prefect / orchestration 扩展
- 重型知识图谱或自动动作

## 现状

当前 retrieval 主要基于：

- lexical overlap
- fake embedding
- 简单 freshness bonus

这使得系统已经具备 baseline 检索能力，但仍有明显上限：

- 语义相关但词面不重合的问题表现有限
- query bucket 间表现不均衡
- QA / insights 的质量上限被 retrieval 卡住

因此 `P1.2` 的核心不是“把 embedding 接上就结束”，而是：

- 让 retrieval 的组成部分可解释、可调、可回归

## 建设原则

### 1. 先基于 `P1.1` baseline，再改 ranking

任何质量提升都必须通过 `P1.1` 的 query set / golden labels 验证。

没有 baseline 的改动，不算 `P1.2` 完成。

### 2. 真实 provider 是增强，不是强依赖

真实 embedding backend 必须是可选项：

- 可启用
- 可禁用
- 不可用时明确回退

### 3. 先做可解释混排，不做黑盒分数

至少要显式区分：

- lexical score
- semantic score
- freshness bonus

而不是把更多逻辑继续塞进一个难解释的总分。

### 4. 不扩大产品边界

`P1.2` 是 retrieval 升级，不是平台扩张。

不要顺手把：

- Source Adapter
- 新源接入
- Internal Relevance
- API 扩展

夹带进来。

## 实施步骤

### Step 1：消化 `P1.1` 基线结果

先读取 `P1.1` 的 baseline 输出，确认：

- 当前总体 `MRR@10`
- 当前 `Hit@5`
- 哪些 query bucket 最弱
- 哪些 query 属于 lexical overlap 弱但语义相关

输出要求：

- 在实现前明确“想提升什么，不想打坏什么”

### Step 2：定义 embedding provider 抽象

新增或收敛一层最小 provider 抽象，要求：

- 默认 fake embedding
- 可选真实 provider
- provider 不可用时有明确降级策略

建议能力：

- `embed_text(text) -> vector`
- `is_available()`
- provider name / mode 可观测

第一版不要求做成完整 provider 平台，只要：

- 结构清晰
- 接口稳定
- fallback 明确

### Step 3：重构 ranking 结构

对现有 ranking 进行最小但清晰的重构。

至少显式拆出：

- `lexical_score`
- `semantic_score`
- `freshness_bonus`
- `final_score`

建议做法：

- 保持默认参数保守
- 支持后续实验性调权
- 不引入难以解释的隐式规则

目标不是“最复杂”，而是“最清楚、最可调”。

### Step 4：兼容 repository 和存储路径

如果真实 embedding 需要调整 retrieval repository 或数据读取方式，需要满足：

- sqlite 路径语义不漂移
- PostgreSQL 路径可兼容
- pgvector 位点继续保持兼容，不强绑定外部环境

这一阶段重点是“兼容增强”，不是“强制切主路径”。

### Step 5：跑 `P1.1` baseline，对比前后结果

至少对比：

- `MRR@10`
- `Hit@5`
- query bucket 表现
- 失败样例是否发生有意义变化

如果只看到个别 query 偶然变好，而整体无提升，不算完成。

### Step 6：补测试与最小文档

至少覆盖：

- fake fallback 行为
- provider 不可用时的降级
- mixed ranking 行为
- eval 测试可稳定运行

README 或相关文档至少说明：

- 如何启用真实 embedding
- 默认 fallback 行为
- 如何运行 eval

## 文件范围

建议主要修改：

- `products/tech_blog_monitor/retrieval.py`
- `products/tech_blog_monitor/db/repositories/retrieval_repository.py`
- `products/tech_blog_monitor/qa.py`
- `products/tech_blog_monitor/test/test_retrieval_eval.py`
- `products/tech_blog_monitor/test/test_qa.py`
- `products/tech_blog_monitor/test/test_postgres_integration.py`
- `products/tech_blog_monitor/README.md`

## 完成标准

`P1.2` 完成至少需要满足：

- `MRR@10` 相对 `P1.1` baseline 提升至少 `15%`
- `Hit@5` 不低于 baseline
- 至少一个 query bucket 有明确改善
- 无外部依赖环境下测试仍可通过
- provider 不可用时可稳定 fallback
- sqlite / PostgreSQL 路径语义不漂移

## 建议验证命令

```bash
uv run ruff check products/tech_blog_monitor
uv run pytest -q products/tech_blog_monitor/test/test_retrieval_eval.py
uv run pytest -q products/tech_blog_monitor/test/test_qa.py
uv run pytest -q products/tech_blog_monitor/test/test_postgres_integration.py
```

如改动范围较大，可补跑：

```bash
uv run pytest -q products/tech_blog_monitor/test
```

## 风险

### 1. 真实 provider 变成强依赖

这是最需要避免的问题之一。

如果本地开发、测试和 CI 因 provider 不可用而失效，说明设计失败。

### 2. 为了通过 eval 写硬编码

不要对 query set 做特判，不要把测试语料逻辑塞进生产排序。

### 3. lexical 质量被误伤

如果 semantic 增强后，基础 lexical 命中显著退化，也不能算成功。

### 4. 超范围漂移

不要顺手把下面内容做进去：

- 新 source adapter
- 新 source ingestion
- internal relevance
- 新 API

## 产出要求

最终交付至少应包含：

- 代码改动
- baseline 前后指标对比
- fallback 说明
- 测试结果
- 仍存在的限制

## 一句话原则

`P1.2` 的重点不是“接上一个 embedding 服务”，而是：

- 在 `P1.1` 的尺子下，把 retrieval 提升为可解释、可回退、可证明变好的混合检索系统
