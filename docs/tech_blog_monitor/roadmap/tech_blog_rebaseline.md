# Tech Blog Monitor Rebaseline

更新时间：`2026-04-15`

这份文档用于执行 `docs/tech_blog_monitor/roadmap/tech_blog_execution_roadmap.md` 的 `Phase 0: Rebaseline`，把当前代码、文档和测试基线对齐。

## 当前能力边界

### 已完成

- 多 RSS 源并发抓取
- feed 级 `timeout` / `verify_ssl` / `headers` / `enabled` 配置
- 重试退避与 feed 健康状态统计
- URL 去重、时效过滤、关键词过滤、全局排序
- Markdown 报告输出
- JSON 结构化输出
- 增量状态记录与新增文章视图
- 历史归档（按天 / 周）
- AI 摘要与趋势分析降级处理
- 配置解析与统一校验失败返回 `exit code 1`
- sqlite 历史资产存储
- 启发式正文抓取与正文清洗
- 单篇文章结构化 enrichment
- 基础检索 API 与 CLI
- 基础 RAG（chunk / mixed retrieval / QA CLI）
- 基础 insights（主题簇 / 趋势 / 来源对比 / 时间线）
- 基础产品化输出（role digest / webhook delivery / feedback）

### 已落地但待优化

- AI 摘要结构化输出仍是“宽松解析 + 警告”，不是严格 schema 校验
- 并发抓取当前使用跨线程共享 `requests.Session()`，存在稳健性风险
- JSON / archive / state 已兼容旧格式，但还没有正式 migration 机制
- 真实 RSS 冒烟仍依赖外部网络，尚未纳入稳定自动化回归
- 正文抽取仍以启发式规则为主，尚未引入站点级抽取策略
- RAG 仍使用 deterministic fake embedding，不是生产级向量检索
- delivery / feedback 已有最小闭环，但未接真实飞书适配器和异步 worker

### Phase 1 新增能力

- 已新增 sqlite 历史资产层
- 已具备 `runs / articles / run_articles` 三类基础记录
- 已支持旧 state 文件和当前 archive payload 的兼容导入
- 已具备最小查询接口，为 Phase 2 和 Phase 4 提供基础

### Phase 2 新增能力

- 已新增启发式正文抓取与正文清洗
- 已区分 `fetched / empty / http_error / fetch_error` 正文状态
- 已将清洗正文和正文状态写入 JSON 输出
- 已将原始 HTML 与清洗正文写入 sqlite 资产层的 `article_contents`

### Phase 3 新增能力

- 已新增单篇文章结构化 enrichment
- 已将 `one_line_summary / key_points / why_it_matters / recommended_for / tags / topic` 写入 JSON 输出
- 已将 enrichment 结果写入 sqlite 资产层的 `article_enrichments`
- 已支持 enrichment 条目级失败隔离与整批失败降级

### Phase 4 新增能力

- 已新增本地 sqlite 检索接口
- 已支持关键词、来源、分类、主题、标签、时间过滤
- 已新增基础查询 CLI
- 已补 golden corpus 风格检索测试

### Phase 5 新增能力

- 已新增 article chunk 持久化与 schema migration
- 已新增 deterministic fake embedding 与 mixed retrieval
- 已新增 QA 服务与 CLI
- 已支持 citation consistency 与无证据拒答

### Phase 6 新增能力

- 已新增 insights 分析能力
- 已支持主题簇、趋势变化、来源对比、时间线摘要
- 已支持低信号样本降级为事实汇总
- 已新增 insights CLI

### Phase 7 新增能力

- 已新增 role digest 模板
- 已新增 webhook delivery 幂等 / 重试 / 限流
- 已新增 feedback 落库与查询
- 已支持 monitor 主流程在开启配置时自动触发 delivery

### 当前明确未做

- 更强的站点级正文抽取规则
- 更强的全文检索 / HTTP API / 高质量 mixed retrieval
- enrichment 历史版本化快照
- 真实向量模型与生产级 RAG
- 真实飞书适配器、push queue / worker 分离部署、用户级订阅配置

## 基线测试清单

### 已有自动化测试

| 基线能力 | 覆盖位置 |
|---------|---------|
| 配置错误路径 | `products/tech_blog_monitor/test/test_config.py` |
| AI 降级路径 | `products/tech_blog_monitor/test/test_analyzer.py` |
| 增量连续两次运行 | `products/tech_blog_monitor/test/test_monitor.py` |
| JSON 输出 | `products/tech_blog_monitor/test/test_monitor.py` |
| 历史归档 | `products/tech_blog_monitor/test/test_monitor.py` |
| state 兼容旧格式 | `products/tech_blog_monitor/test/test_state.py` |
| 报告增量视图 | `products/tech_blog_monitor/test/test_reporter.py` |

### 已执行本地回归

执行命令：

```bash
pytest -q products/tech_blog_monitor/test
```

状态：

- 已执行
- 结果：`162 passed`

### 待人工执行的真实 RSS 冒烟

说明：该项依赖外部网络，不纳入默认离线测试基线。

建议命令：

```bash
PYTHONPATH=. \
TECH_BLOG_MAX_ARTICLES=1 \
TECH_BLOG_MAX_TOTAL=5 \
TECH_BLOG_STATE_PATH=/tmp/tech_blog_seen.json \
TECH_BLOG_JSON_OUTPUT=/tmp/tech_blog_report.json \
python -m products.tech_blog_monitor.agent --output /tmp/tech_blog_report.md
```

建议验收点：

- 进程退出码为 `0`
- Markdown 报告成功生成
- JSON 输出成功生成
- 至少一个 feed 抓取成功
- AI 不可用时报告仍可生成降级内容

本次执行状态：

- 未执行
- 原因：当前会话未使用外网冒烟验证

## 相关文档对齐结果

- `docs/tech_blog_monitor/roadmap/tech_blog_execution_roadmap.md`
  - 作为后续阶段路线图
- `docs/tech_blog_monitor/operations/tech_blog_monitor_todo.md`
  - 作为历史阶段完成情况与使用示例
- `docs/tech_blog_monitor/roadmap/tech_blog_rag_plan.md`
  - 作为中长期 RAG 演进方向说明
- `products/tech_blog_monitor/README.md`
  - 作为当前模块入口说明
- `README.md`
  - 作为仓库级目录入口

## Phase 0 结论

`Phase 0: Rebaseline` 已完成到“本地文档和自动化测试基线对齐”的程度。

当前剩余的人工项只有：

- 一次真实 RSS 冒烟记录（可选补充验收，不阻塞本地基线收口）

后续应基于当前真实基线继续推进“质量增强”而不是重复规划已完成 phase。
