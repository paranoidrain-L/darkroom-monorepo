# Tech Blog Modernization P1.5: Content Extraction Plan

更新时间：`2026-04-16`

## 验收归档

截至 `2026-04-16`，modernization `P1.5` 可按“已完成并归档”处理。

当前验收结论：

- 已完成：`Trafilatura` 主抽取路径
- 已完成：heuristic fallback 保留且继续兼容旧 facade
- 已完成：受控 `Playwright` fallback
- 已完成：正文质量判断与 `low_quality` / `empty` 可观测状态
- 已完成：`monitor.py` / 配置层 / README / 测试接线

本地验证结果：

- `PYTHONPATH=. .venv/bin/python3 -m pytest -q products/tech_blog_monitor/test/test_content_fetcher.py`
  `12 passed`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test`
  `203 passed, 1 skipped`
- `uv run ruff check products/tech_blog_monitor`
  `All checks passed!`

当前仍保留的非阻塞尾项：

- 补 `test_config.py` 中新环境变量的 env contract 测试：
  `TECH_BLOG_CONTENT_EXTRACTOR`、`TECH_BLOG_PLAYWRIGHT_FALLBACK`、`TECH_BLOG_PLAYWRIGHT_TIMEOUT`、`TECH_BLOG_PLAYWRIGHT_WORKERS`
- 在安装浏览器二进制的环境补一条真实 `Playwright` smoke test
- 基于真实站点样本重新校准正文质量阈值，确认 `low_quality` 不会误杀边缘短正文

## 说明

这份文档描述的是 modernization 路线中的 `P1.5`，目标是升级正文抽取能力。

它不是回头重做历史 `Phase 2`，而是在当前已存在的正文抓取基线之上，提升：

- 抽取完整度
- 抽取稳定性
- 复杂站点适应性
- 抽取质量可观测性

历史正文抓取基线见：

- [docs/tech_blog_monitor/phases/tech_blog_phase2_content_fetch.md](../phases/tech_blog_phase2_content_fetch.md)

## 立项前状态

立项前，正文抓取已经具备：

- 基于 `requests` 的 HTML 获取
- 启发式正文抽取
- `article/main/body/json-ld` 优先级策略
- 正文状态字段
- JSON / sqlite 资产落库
- fixture 驱动测试

当前主实现位于：

- [products/tech_blog_monitor/content_fetcher.py](../../../products/tech_blog_monitor/content_fetcher.py)

立项前的主要限制：

- 启发式规则对复杂页面稳定性一般
- 对 JS-heavy 页面无能为力
- 缺少正文质量评分
- 无站点级适配策略
- 缺少“主抽取器失败 -> fallback 抽取器 -> 浏览器 fallback”的清晰链路

## 目标

P1.5 的目标是把当前：

- `requests + 正则/HTML 启发式抽取`

升级为：

- `Trafilatura` 主路径
- 当前启发式抽取逻辑作为 fallback
- `Playwright` 作为 JS-heavy 页面兜底路径
- 抽取质量判断与失败原因分类

P1.5 完成后，系统应满足：

- 普通文章页优先使用正文抽取器而不是纯启发式正则
- JS-heavy 或客户端渲染页面有受控的浏览器 fallback
- 内容抽取失败不会静默成功
- 上层 enrichment / search / QA 能获得更稳定的 `clean_text`

## 不在 P1.5 做的事

P1.5 不做：

- 不重构 P1 的 repository / migration 体系
- 不重写 search / retrieval / QA 主逻辑
- 不做前端
- 不做多租户或权限
- 不做复杂站点规则平台
- 不要求引入在线爬虫集群

P1.5 也不应做：

- 为少量特殊站点写大量一次性硬编码规则
- 让浏览器路径默认覆盖全部站点
- 在没有质量门禁的情况下把 `Playwright` 当默认抓取器

## 总体原则

### 1. 主路径升级，不改上层契约

P1.5 应尽量保持现有 `Article` 字段和 `content_status` 语义稳定：

- `content_status`
- `content_source`
- `clean_text`
- `content_error`
- `content_http_status`
- `content_fetched_at`
- `content_final_url`

允许增加更细粒度状态或 metadata，但不要破坏当前 JSON / DB / API 契约。

### 2. 先抽取器升级，再浏览器兜底

正确顺序应是：

1. `Trafilatura` 主抽取器
2. 当前启发式逻辑 fallback
3. `Playwright` 仅在必要时进入

不要把浏览器抓取变成默认主路径。

### 3. 浏览器路径必须受控

浏览器 fallback 只能在有限条件下触发，例如：

- 初次请求成功但正文为空
- 页面高度疑似客户端渲染
- 特定内容块明显缺失

并且必须限制：

- timeout
- 并发
- 重试次数

### 4. 抽取质量必须显式评估

P1.5 不只是“换个抽取器”，还要解决：

- 抽到的是不是正文
- 是否只是导航/页脚/菜单文本
- 是否过短、过碎、过噪

因此至少要引入基础质量判断，而不是仅以“非空”视为成功。

## 当前实现与建议目标结构

当前核心文件：

- [products/tech_blog_monitor/content_fetcher.py](../../../products/tech_blog_monitor/content_fetcher.py)

P1.5 完成后，建议至少演进到：

```text
products/tech_blog_monitor/
├── content_fetcher.py
├── content_quality.py
├── extractors/
│   ├── __init__.py
│   ├── trafilatura_extractor.py
│   ├── heuristic_extractor.py
│   └── playwright_extractor.py
└── ...
```

职责建议：

- `content_fetcher.py`
  调度主流程、组装 extractor 链、维护状态与 fallback
- `content_quality.py`
  做正文质量判断
- `trafilatura_extractor.py`
  `Trafilatura` 主抽取器
- `heuristic_extractor.py`
  保留当前启发式实现
- `playwright_extractor.py`
  浏览器 fallback

## 建议依赖

P1.5 建议引入：

- `trafilatura`
- `playwright`

注意：

- `playwright` 依赖浏览器运行时，P1.5 应把它作为可选路径
- 不应要求所有本地开发默认都安装浏览器二进制才能跑普通测试

## 配置设计

P1.5 建议新增最小配置面：

- `TECH_BLOG_CONTENT_EXTRACTOR`
- `TECH_BLOG_PLAYWRIGHT_FALLBACK`
- `TECH_BLOG_PLAYWRIGHT_TIMEOUT`
- `TECH_BLOG_PLAYWRIGHT_WORKERS`

建议语义：

- `TECH_BLOG_CONTENT_EXTRACTOR=trafilatura|heuristic`
- `TECH_BLOG_PLAYWRIGHT_FALLBACK=true|false`
- `TECH_BLOG_PLAYWRIGHT_TIMEOUT`：浏览器兜底超时
- `TECH_BLOG_PLAYWRIGHT_WORKERS`：浏览器兜底并发

推荐默认值：

- 主抽取器默认 `trafilatura`
- 浏览器 fallback 默认开启但严格受控，或在开发环境默认关闭、生产显式开启

## 分阶段执行方案

## Phase 1.5.1：抽取器分层与 Trafilatura 主路径

### 目标

把正文抽取从单文件启发式实现，升级为可扩展 extractor 链。

### 具体任务

1. 抽出当前启发式实现

把当前 [content_fetcher.py](../../../products/tech_blog_monitor/content_fetcher.py) 中的：

- HTML 清洗
- 正文提取
- `json-ld` 抽取

拆到：

- `extractors/heuristic_extractor.py`

2. 增加 `Trafilatura` 主抽取器

新增：

- `extractors/trafilatura_extractor.py`

要求：

- 主路径优先尝试 `Trafilatura`
- 能返回 `(clean_text, source, metadata)` 或等价结构
- 对解析失败、空文本、异常有清晰返回

3. 在 `content_fetcher.py` 中引入 extractor 链

推荐顺序：

1. `Trafilatura`
2. heuristic fallback

### 验收

- 普通 fixture 页面可走 `Trafilatura`
- 原有 fixture 测试继续通过
- 主调用接口不破坏现有 `fetch_article_content()` / `fetch_contents()`

## Phase 1.5.2：正文质量判断

### 目标

避免把“非空文本”误当成“成功正文”。

### 具体任务

1. 新增质量判断模块

新增：

- `content_quality.py`

至少判断：

- 纯文本长度
- 段落数量
- 链接/导航噪声比例
- 重复文本比例

2. 扩展状态语义

建议保留现有主状态，但允许增加更细粒度错误，例如：

- `empty`
- `low_quality`
- `fetch_error`
- `http_error`

或者保留原状态不变，把质量问题写入：

- `content_error`
- `content_source`

### 验收

- 对“明显不是正文”的页面不会静默标记为 `fetched`
- fixture 可覆盖低质量正文与空正文边界

## Phase 1.5.3：Playwright 浏览器 fallback

### 目标

为 JS-heavy 页面补受控浏览器兜底能力。

### 具体任务

1. 新增浏览器抽取器

新增：

- `extractors/playwright_extractor.py`

职责：

- 打开页面
- 等待基础内容稳定
- 获取渲染后 HTML 或直接抽取正文

2. 定义触发条件

推荐仅在以下情况触发：

- 普通请求成功但正文为空
- 抽取质量判断失败
- 页面对客户端渲染特征明显

3. 严格约束资源

要求：

- timeout 可配置
- workers 可配置
- 明确异常与超时状态

### 验收

- 浏览器 fallback 只在必要时触发
- 不会显著拖垮普通抓取路径
- 本地测试支持 mock，不依赖真实浏览器联网

## Phase 1.5.4：资产层与可观测性收口

### 目标

把抽取来源、失败原因和质量结果稳定落到现有数据面。

### 具体任务

1. 保持现有字段兼容

继续维护：

- `content_status`
- `content_source`
- `clean_text`
- `content_error`
- `content_http_status`
- `content_fetched_at`
- `content_final_url`

2. 如有必要，增加最小 metadata

例如：

- `content_quality_score`
- `content_extractor`

但新增字段必须评估：

- JSON 输出兼容性
- sqlite / Postgres schema 影响
- API 是否需要暴露

3. 增加观测点

至少记录：

- extractor 使用分布
- 正文抽取成功率
- fallback 触发率
- Playwright 超时/失败率

### 验收

- 正文状态与来源可在 JSON / DB 中稳定追踪
- 问题来源可被定位，而不是只有泛化错误

## Worker 拆分建议

如果拆多个 Worker，建议按下面切：

### Worker A：抽取器分层

负责范围：

- `content_fetcher.py`
- `extractors/heuristic_extractor.py`
- `extractors/trafilatura_extractor.py`

禁止修改：

- search / retrieval / QA 逻辑
- API 契约

### Worker B：质量判断与状态收口

负责范围：

- `content_quality.py`
- `content_fetcher.py`
- 相关测试

禁止修改：

- DB 大规模 schema 重构

### Worker C：Playwright fallback

负责范围：

- `extractors/playwright_extractor.py`
- fallback 触发条件
- mock / fixture 测试

禁止修改：

- 主抓取策略大面积重构
- 无关模块

### 集成人员

负责范围：

- 合并 extractor 链、质量判断和 fallback
- 跑正文抓取回归
- 更新 README / 文档

## 测试与回归门禁

P1.5 合入前至少满足：

- 现有 `test_content_fetcher.py` 继续通过
- 新增 `Trafilatura` 路径测试
- 新增低质量正文测试
- 新增 Playwright fallback mock 测试
- 原有 `monitor.py` / JSON / DB 相关正文路径测试继续通过

最低测试矩阵建议：

1. fixture corpus

- 正常正文页面
- `json-ld` 页面
- 无正文页面
- 超长页面
- 低质量噪声页面
- JS-heavy mock 页面

2. extractor fallback

- `Trafilatura` 成功
- `Trafilatura` 空结果 -> heuristic 成功
- 主路径失败 -> Playwright fallback 成功
- 所有路径失败 -> 明确错误状态

3. compatibility

- `fetch_article_content()` 契约不变
- `fetch_contents()` 并发顺序不变
- JSON / DB 输出兼容

## 建议命令

```bash
uv run pytest -q products/tech_blog_monitor/test/test_content_fetcher.py
uv run pytest -q products/tech_blog_monitor/test
uv run ruff check products/tech_blog_monitor
```

如果引入 `playwright`，建议补：

```bash
uv run playwright install
```

但此命令不应成为普通单元测试的前置条件。

## 明确不允许的做法

P1.5 不应出现以下做法：

- 直接删除当前启发式实现而没有 fallback
- 让 `Playwright` 成为默认主路径
- 没有质量门禁就把所有非空文本标为成功
- 为个别站点写大量临时硬编码规则并混入主流程
- 把正文升级和搜索/检索大规模重构绑在同一批里

## 完成定义

满足以下条件，可认为 modernization `P1.5` 完成：

- `Trafilatura` 已成为正文抽取主路径
- 当前启发式逻辑保留为 fallback
- `Playwright` 兜底路径已接入且受控
- 正文质量判断已落地
- JSON / DB / API 正文状态语义保持稳定
- 上层 enrichment / search / QA 能获得更稳定的 `clean_text`

当前状态：

- 上述完成条件已满足
- 可以进入后续阶段，不需要继续把 P1.5 作为在制任务保留

## 给 Worker Agent 的一句话任务描述

在不打断现有正文状态契约和主链路行为的前提下，把 `tech_blog_monitor` 的正文抓取从启发式单路径升级为 `Trafilatura` 主抽取 + heuristic fallback + 受控 `Playwright` 兜底，并补齐正文质量判断与回归测试。
