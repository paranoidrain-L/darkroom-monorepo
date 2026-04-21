# Tech Blog Phase 3 Enrichment

更新时间：`2026-04-15`

## 目标

Phase 3 的目标是为单篇文章增加结构化理解结果，让文章不只是“可抓取、可归档”，还可以被快速理解和结构化消费。

当前实现是最小可用版，重点解决：

- 为每篇文章生成结构化 enrichment
- 支持部分成功隔离
- enrichment 失败时不打断整批处理
- 将 enrichment 写入 JSON 输出与 sqlite 资产层

## 当前字段

当前 `Article` 已新增：

- `one_line_summary`
- `key_points`
- `why_it_matters`
- `recommended_for`
- `tags`
- `topic`
- `enrichment_status`
- `enrichment_error`

## enrichment 流程

实现位置：

- `products/tech_blog_monitor/analyzer.py`

当前流程：

1. 优先使用 `clean_text`，无正文时退回 `rss_summary`
2. 批量请求 AI 输出 JSON 数组
3. 对每个条目做 schema 校验
4. 有效条目写回文章
5. 无效条目只标记当前文章失败，不打断整批
6. 趋势分析仍作为独立第二步执行

## schema 约束

当前每个 enrichment 条目要求：

- `one_line_summary`：非空字符串
- `key_points`：非空字符串列表
- `why_it_matters`：非空字符串
- `recommended_for`：非空字符串列表
- `tags`：非空字符串列表
- `topic`：非空字符串

## 失败与降级

当前支持以下失败路径：

- AI backend 不可用
- AI 返回非法 JSON
- 单篇条目 schema 不合法
- 批量返回中部分文章缺失
- 趋势分析单独失败

行为约定：

- 单篇 enrichment 失败时，仅该文章标记 `enrichment_status=failed`
- 全量 enrichment 调用失败时，整批文章标记失败，但主流程继续
- 趋势分析失败时仅回退趋势段，不影响 enrichment 结果

## 存储

### JSON 输出

当前会写出：

- `one_line_summary`
- `key_points`
- `why_it_matters`
- `recommended_for`
- `tags`
- `topic`
- `enrichment_status`
- `enrichment_error`

### sqlite 资产层

当前新增 `article_enrichments` 表，保存最新 enrichment 结果。

这意味着：

- `articles` 保存基础元数据
- `article_contents` 保存正文
- `article_enrichments` 保存结构化理解结果

## 当前限制

- enrichment 结果是“最新态”，不是按 run 版本化快照
- 报告层当前仍主要复用 `ai_summary/one_line_summary`，还没有完整文章卡片视图
- `key_points / tags / recommended_for` 主要面向 JSON 和资产层，后续可用于 search / retrieval / clustering

## 测试

当前已补：

- enrichment schema validation tests
- fake AI client tests
- 非法 JSON / 部分成功 / 整体失败测试
- sqlite schema v2 -> v3 迁移测试

执行命令：

```bash
pytest -q products/tech_blog_monitor/test
```

## 后续建议

Phase 3 完成后，下一步更合理的是：

1. 在 Phase 4 基于 `topic / tags / source / time` 做最小检索接口
2. 让 retrieval 直接消费 `clean_text + enrichment`
3. 如需更强阅读体验，再单独升级报告层为真正的文章卡片
