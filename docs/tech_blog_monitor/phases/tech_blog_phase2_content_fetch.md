# Tech Blog Phase 2 Content Fetch

更新时间：`2026-04-14`

## 目标

Phase 2 的目标是把 `tech_blog_monitor` 从“RSS 摘要系统”推进到“具备正文抓取能力的文章内容系统”。

当前实现是最小可用版，重点解决：

- 抓取文章原始 HTML
- 提取清洗后的正文文本
- 区分正文抓取成功、空正文、HTTP 错误、抓取异常
- 将正文状态落到 JSON 输出和 sqlite 资产层

## 当前实现

模块：

- `products/tech_blog_monitor/content_fetcher.py`

主流程接入点：

- `products/tech_blog_monitor/monitor.py`

资产存储扩展：

- `products/tech_blog_monitor/archive_store.py`

## 抽取策略

当前使用标准库和 `requests` 的启发式抽取，不依赖额外 HTML 解析库。

优先顺序：

1. `<article>`
2. `<main>`
3. 常见 `content/article/post/entry/main` 容器
4. `<body>`
5. `application/ld+json` 中的 `articleBody`

清洗规则：

- 删除 `script/style/noscript/svg/iframe/canvas/template`
- 删除 `header/nav/footer/aside/form`
- 转换块级标签换行
- 去 HTML 标签
- 合并空白
- 按 `content_max_chars` 截断

## 文章正文状态

当前 `Article` 增加以下字段：

- `content_status`
- `content_source`
- `raw_html`
- `clean_text`
- `content_error`
- `content_http_status`
- `content_fetched_at`
- `content_final_url`

`content_status` 当前可能值：

- `not_fetched`
- `fetched`
- `empty`
- `http_error`
- `fetch_error`

## 配置项

- `TECH_BLOG_FETCH_CONTENT`
- `TECH_BLOG_CONTENT_TIMEOUT`
- `TECH_BLOG_CONTENT_WORKERS`
- `TECH_BLOG_CONTENT_MAX_CHARS`

默认行为：

- 默认启用正文抓取
- 抓取失败不会打断当前 RSS 报告主流程

## 存储约定

### JSON 输出

当前 JSON payload 会额外写出：

- `content_status`
- `content_source`
- `clean_text`
- `content_error`
- `content_http_status`
- `content_fetched_at`
- `content_final_url`

不默认输出 `raw_html`，避免归档 JSON 过大。

### sqlite 资产层

当前新增 `article_contents` 表，保存：

- 抽取状态
- 原始 HTML
- 清洗正文
- HTTP 状态
- 错误信息
- 最终 URL

这意味着：

- 原始 HTML 存 sqlite
- 清洗正文同时存 sqlite 和 JSON 输出

## 当前限制

- 启发式抽取，对复杂页面不如专用正文解析器稳定
- 未做站点级抽取规则
- 未做正文语言识别
- 未做正文质量评分
- `json-ld` 仅支持 `articleBody` 基础提取

## 测试

当前已补：

- 本地 HTML fixture corpus
- 正文抽取单元测试
- 无正文 / 403 / 异常 / 超长页面测试
- fixture 驱动的并发抓取测试
- sqlite schema v1 -> v2 迁移测试

执行命令：

```bash
pytest -q products/tech_blog_monitor/test
```

## 后续建议

如果继续推进 Phase 2，下一步优先级建议是：

1. 为核心来源增加站点级抽取规则
2. 引入更强的 HTML 正文提取器或保留当前实现作为 fallback
3. 增加正文质量判断，避免导航文本被误判为正文
4. 为 Phase 3 enrichment 切换输入源，从 RSS 摘要逐步过渡到 `clean_text`
