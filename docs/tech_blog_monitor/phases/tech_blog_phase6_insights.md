# Tech Blog Monitor Phase 6: 分析型产品能力

## 目标

在 Phase 5 的检索 / QA 基础上，补齐“输出洞察”的最小闭环：

- 主题簇输出
- 时间窗口趋势判断
- 多来源对比
- 时间线汇总
- 热点信号提取

## 当前实现边界

已落地：

- `products.tech_blog_monitor.insights.analyze_insights(...)`
- `python -m products.tech_blog_monitor.insights_cli`
- 基于历史 sqlite 文章资产的时间窗口分析
- 对“样本不足 / 信号不足 / 来源不均衡”的降级

当前仍未做：

- 真正的聚类模型
- 更复杂的 topic merge / alias 归一
- 统计显著性检验
- 可视化 dashboard
- 与日报主流程自动集成

## 设计说明

### 输入资产

直接复用 Phase 1-5 已有资产：

- `articles`
- `article_enrichments`
- `article_contents`
- `article_chunks`

当前 Phase 6 主要依赖：

- `published_ts`
- `source_name`
- `topic`
- `category`
- `title`

### 分析方法

当前实现以“可重复、可离线测试”为优先目标：

- 用 `topic` 做主题分组
- 用最近窗口 vs 上一窗口做趋势比较
- 用来源内 topic 分布做多来源差异
- 用逐日计数生成时间线
- 用文章数、跨来源覆盖、趋势增量合成热点分数

### 降级策略

以下情况不输出“强洞察”，而降级为事实汇总：

- 最近窗口样本不足
- 所有主题都没有显著升降
- 来源过少，无法做可靠对比

## 测试门禁

Phase 6 本地测试覆盖：

- 合成趋势数据集
- 上升 / 下降主题识别
- 多来源差异测试
- 时间线稳定性测试
- 低信号降级测试
- Insights CLI 缺库报错
