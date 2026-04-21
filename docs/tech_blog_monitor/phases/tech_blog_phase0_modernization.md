# Tech Blog Phase 0 Modernization Plan

更新时间：`2026-04-16`

## 目标

P0 的目标不是重写 `tech_blog_monitor`，而是在不改变当前主链路业务语义的前提下，先完成三件事：

- 建立统一的开发底座：`uv`、`pyproject.toml`、`Ruff`
- 拆解当前过重的配置层，引入 `pydantic-settings`
- 增加最小可用 HTTP API，让前端和外部调用方有稳定读接口

P0 完成后，系统应从“以 CLI 为主的脚本集合”升级为“保留 CLI 的可服务化后端”。

## 范围

P0 必做：

- 增加 `pyproject.toml`
- 接入 `uv`
- 接入 `Ruff`
- 拆分 `products/tech_blog_monitor/config.py`
- 引入 `pydantic-settings`
- 增加 `FastAPI` 应用与最小 API
- 补充对应测试与 README

P0 不做：

- 不迁移到 PostgreSQL
- 不拆 `archive_store.py` 为 repository
- 不升级正文抽取
- 不升级 retrieval / RAG
- 不做前端页面
- 不新增 `POST /run`、`POST /qa`

## 当前基线

当前代码的实际落点如下：

- 配置入口集中在 `products/tech_blog_monitor/config.py`
- CLI 入口在 `products/tech_blog_monitor/agent.py`
- 主执行链路在 `products/tech_blog_monitor/monitor.py`
- sqlite 资产读写集中在 `products/tech_blog_monitor/archive_store.py`
- 检索接口在 `products/tech_blog_monitor/search.py`
- insights 接口在 `products/tech_blog_monitor/insights.py`
- feedback 接口在 `products/tech_blog_monitor/feedback.py`
- 当前测试目录为 `products/tech_blog_monitor/test`

当前 repo 已有 `fastapi`、`uvicorn`、`pydantic` 依赖，但没有：

- `pyproject.toml`
- `uv` 工作流
- `Ruff` 配置
- `pydantic-settings`
- `tech_blog_monitor` 专用 API 应用

## P0 设计原则

### 1. 保留兼容壳，不直接打断现有调用方

`products/tech_blog_monitor/config.py` 当前被多个模块直接 import。P0 不应一次性让所有调用点直接依赖新 settings 文件，而应采用：

- 新增分层模块
- `config.py` 退化为兼容 facade
- 旧导入路径继续可用

这样可以降低对 `fetcher.py`、`monitor.py`、`scheduler.py`、测试文件的冲击。

### 2. 先补读 API，不改运行模型

P0 API 以“读接口优先”为原则：

- `GET /health`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /articles`
- `GET /articles/{article_id}`
- `GET /search`
- `GET /insights`
- `POST /feedback`

不做：

- `POST /run`
- `POST /qa`
- 异步任务执行模型

### 3. 不把仓库级打包重构和产品级 P0 混在一起

这是多产品仓库。P0 的 `pyproject.toml` 应尽量解决：

- 依赖声明
- `uv` 工作流
- `ruff` 配置
- pytest 基础配置

不应在 P0 同时引入复杂 monorepo packaging 方案。

推荐策略：

- 在 repo 根目录增加最小 `pyproject.toml`
- 保留现有 `requirements.txt` 作为过渡兼容
- README 同时给出 `uv` 和旧方式说明

## 目标结构

P0 结束后，`products/tech_blog_monitor` 建议至少演进到如下结构：

```text
products/tech_blog_monitor/
├── agent.py
├── monitor.py
├── archive_store.py
├── defaults.py
├── feed_catalog.py
├── config_loader.py
├── config_validator.py
├── settings.py
├── config.py
└── api/
    ├── __init__.py
    ├── app.py
    ├── deps.py
    └── schemas.py
```

职责建议：

- `defaults.py`
  只放默认值和常量
- `feed_catalog.py`
  只放 `FeedSource` 和默认 feeds
- `config_loader.py`
  只处理 env / YAML / 类型转换
- `config_validator.py`
  只处理值域校验和错误聚合
- `settings.py`
  提供 `TechBlogMonitorSettings`
- `config.py`
  兼容导出层，保留 `TechBlogMonitorConfig.from_env()` 和旧导入路径
- `api/app.py`
  提供 `FastAPI` app
- `api/deps.py`
  统一注入 settings / sqlite store
- `api/schemas.py`
  定义 API response/request model

## 交付物

P0 合格交付物应包含：

### 1. 工程底座

- 根目录 `pyproject.toml`
- 可选 `uv.lock`
- `Ruff` 配置
- `pydantic-settings` 依赖声明

### 2. 配置分层

- 新的 settings 分层模块
- 兼容旧 import 的 `config.py`
- 对应单元测试

### 3. HTTP API

- `FastAPI` app
- 启动入口
- API 测试
- README 启动说明

### 4. 文档

- README 中增加 `uv` 安装方式
- README 中增加 API 启动与调用方式
- 明确 `asset_db_path` 未配置时哪些接口不可用

## 分阶段执行方案

## Phase 0.1：开发底座

### 目标

先统一依赖、lint 和本地运行入口，但不改业务逻辑。

### 具体任务

1. 增加根目录 `pyproject.toml`

要求：

- 包含 `project` 元数据
- 收口 `tech_blog_monitor` 依赖
- 补充 `pydantic-settings`
- 增加开发依赖组，例如 `pytest`、`ruff`

建议不要在 P0 做复杂的 package discovery，只需保证：

- `uv sync`
- `uv run pytest -q products/tech_blog_monitor/test`
- `uv run python -m products.tech_blog_monitor.agent`

可正常工作。

2. 保留 `requirements.txt` 兼容

要求：

- 不删除 `requirements.txt`
- README 说明它是过渡方案
- 新增开发流程默认推荐 `uv`

3. 接入 `Ruff`

要求：

- 先启用基础规则
- 只做低风险格式化和 import 排序
- 不在 P0 引入过严规则导致大面积无关改动

建议范围：

- `E/F/I`
- 基础 `UP`
- 行宽配置

### 涉及文件

- [requirements.txt](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/requirements.txt)
- 新增 [pyproject.toml](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/pyproject.toml)
- 更新 [products/tech_blog_monitor/README.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/products/tech_blog_monitor/README.md)

### 验收

- `uv` 能完成依赖同步
- `ruff check` 能跑通目标目录
- 原有 CLI 运行方式不被移除

## Phase 0.2：配置层重构

### 目标

将当前“大而全”的 `config.py` 拆层，但保持外部调用语义尽量不变。

### 具体任务

1. 拆分默认值和 feed catalog

将以下内容从 `config.py` 拆出：

- `FeedSource`
- `DEFAULT_FEEDS`
- 默认数值常量

分别放入：

- `feed_catalog.py`
- `defaults.py`

2. 引入 `TechBlogMonitorSettings`

在 `settings.py` 中基于 `pydantic-settings` 建立统一 settings model。

要求：

- env 读取逻辑集中
- 保留当前环境变量名，不改 env contract
- 支持 YAML feed 覆盖
- 支持默认值、env 值、YAML 值、校验错误分层处理

3. 拆出 loader 和 validator

建议职责：

- `config_loader.py`
  解析 env、读取 YAML、做原始类型转换
- `config_validator.py`
  值域校验、错误聚合、兼容错误消息

4. 保留兼容层 `config.py`

兼容策略建议：

- `config.py` 继续导出 `FeedSource`
- `config.py` 继续暴露 `TechBlogMonitorConfig`
- `TechBlogMonitorConfig.from_env()` 内部可委托 `TechBlogMonitorSettings`

如果短期内完全替换 dataclass 成本过高，可采用双层模型：

- `TechBlogMonitorSettings` 负责输入侧
- `TechBlogMonitorConfig` 作为兼容输出对象

优先保证：

- `fetcher.py`
- `monitor.py`
- `scheduler.py`
- `agent.py`
- 现有测试

不需要大改。

### 涉及文件

- [products/tech_blog_monitor/config.py](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/products/tech_blog_monitor/config.py)
- 新增 [products/tech_blog_monitor/defaults.py](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/products/tech_blog_monitor/defaults.py)
- 新增 [products/tech_blog_monitor/feed_catalog.py](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/products/tech_blog_monitor/feed_catalog.py)
- 新增 [products/tech_blog_monitor/config_loader.py](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/products/tech_blog_monitor/config_loader.py)
- 新增 [products/tech_blog_monitor/config_validator.py](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/products/tech_blog_monitor/config_validator.py)
- 新增 [products/tech_blog_monitor/settings.py](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/products/tech_blog_monitor/settings.py)
- 更新 [products/tech_blog_monitor/test/test_config.py](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/products/tech_blog_monitor/test/test_config.py)

### 验收

- 现有环境变量仍可驱动系统运行
- 原有 `TechBlogMonitorConfig.from_env()` 调用仍可工作
- `test_config.py` 通过
- 配置错误语义没有明显回归

## Phase 0.3：最小 API

### 目标

为当前已有能力补一个稳定 HTTP 外壳，不重写主 pipeline。

### API 设计

建议新增：

- `GET /health`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /articles`
- `GET /articles/{article_id}`
- `GET /search`
- `GET /insights`
- `POST /feedback`

### 关键设计决策

1. API 只包装现有能力，不引入新的业务核心逻辑。

2. 除 `GET /health` 外，依赖 sqlite 资产库的接口都应基于统一配置读取 `asset_db_path`。

3. 当 `asset_db_path` 未配置时：

- 返回明确的 `503` 或 `400`
- 错误消息写清楚 “asset db not configured”

4. `GET /articles/{article_id}` 需要补充 `ArchiveStore` 的按 `article_id` 查询能力。当前只有 `get_article_by_url()`，不足以支撑该接口。

5. `GET /runs` 需要补充 `ArchiveStore` 的 runs 列表能力。当前只有 `get_run()`，没有 list 接口。

### 建议实现方式

新增：

- `products/tech_blog_monitor/api/app.py`
- `products/tech_blog_monitor/api/deps.py`
- `products/tech_blog_monitor/api/schemas.py`

必要时补充 archive 读接口：

- `ArchiveStore.list_runs(limit: int, offset: int = 0)`
- `ArchiveStore.get_article(article_id: str)`

现有可直接复用：

- `search.search_articles()`
- `insights.analyze_insights()`
- `feedback.record_feedback()`
- `ArchiveStore.list_articles()`
- `ArchiveStore.get_run()`
- `ArchiveStore.list_run_articles()`

### 建议 response 形态

`GET /health`

```json
{
  "status": "ok"
}
```

`GET /runs`

```json
{
  "items": [
    {
      "run_id": "run_xxx",
      "generated_at": 1710000000,
      "article_count": 12,
      "new_article_count": 4
    }
  ]
}
```

`GET /runs/{run_id}`

```json
{
  "run": {},
  "articles": []
}
```

`GET /articles`

支持参数：

- `source_name`
- `category`
- `limit`

`GET /search`

支持参数：

- `query`
- `source_name`
- `category`
- `topic`
- `tag`
- `days`
- `limit`

`GET /insights`

支持参数：

- `days`
- `top_k`
- `max_articles`

`POST /feedback`

body 建议：

```json
{
  "run_id": "run_xxx",
  "role": "engineer",
  "feedback_type": "thumbs_up",
  "feedback_text": "搜索结果可用",
  "metadata": {}
}
```

### 启动入口

P0 建议至少提供一个稳定入口：

```bash
uv run uvicorn products.tech_blog_monitor.api.app:app --reload
```

如果需要，也可增加：

- `python -m products.tech_blog_monitor.api.app`

但不应在 P0 引入复杂 serve orchestration。

### 涉及文件

- 新增 [products/tech_blog_monitor/api/app.py](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/products/tech_blog_monitor/api/app.py)
- 新增 [products/tech_blog_monitor/api/deps.py](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/products/tech_blog_monitor/api/deps.py)
- 新增 [products/tech_blog_monitor/api/schemas.py](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/products/tech_blog_monitor/api/schemas.py)
- 更新 [products/tech_blog_monitor/archive_store.py](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/products/tech_blog_monitor/archive_store.py)
- 更新 [products/tech_blog_monitor/README.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/products/tech_blog_monitor/README.md)
- 新增 API 测试文件，例如 [products/tech_blog_monitor/test/test_api.py](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/products/tech_blog_monitor/test/test_api.py)

### 验收

- API 能正常启动
- `GET /health` 不依赖 sqlite 可直接返回
- 其余接口在有资产库时可正常返回 JSON
- 缺 `asset_db_path` 时返回明确错误
- 不破坏现有 CLI 行为

## Worker 执行顺序

如果只派一个 Worker，按下面顺序执行：

1. `Phase 0.1` 工程底座
2. `Phase 0.2` 配置层重构
3. `Phase 0.3` 最小 API
4. README 和测试收口

如果拆成多个 Worker，推荐这样切：

### Worker A：工程底座

负责范围：

- `pyproject.toml`
- `uv` 工作流
- `Ruff`
- README 开发命令更新

禁止修改：

- `archive_store.py`
- API 业务逻辑

### Worker B：配置层

负责范围：

- `defaults.py`
- `feed_catalog.py`
- `config_loader.py`
- `config_validator.py`
- `settings.py`
- `config.py` 兼容层
- `test_config.py`

禁止修改：

- API 路由
- `archive_store.py` schema

### Worker C：API 层

负责范围：

- `api/` 目录
- `archive_store.py` 中新增只读 helper
- `test_api.py`

禁止修改：

- 主 pipeline 语义
- `monitor.py` 的执行流程
- 数据 schema version

### 集成人员

负责范围：

- 合并冲突处理
- README 最终收口
- 统一跑测试
- 验证 CLI 与 API 并存

## 回归门禁

P0 合入前至少满足：

- `pytest -q products/tech_blog_monitor/test` 通过
- 新增 API 测试通过
- 原有 CLI 用法仍可执行
- 配置错误路径仍可控
- `GET /health`、`GET /articles`、`GET /search` 具备最小可用性

建议补充命令：

```bash
uv run pytest -q products/tech_blog_monitor/test
uv run ruff check products/tech_blog_monitor
uv run python -m products.tech_blog_monitor.agent --help
uv run uvicorn products.tech_blog_monitor.api.app:app --host 127.0.0.1 --port 8000
```

## 明确不允许的改动

Worker 在 P0 不应做以下事情：

- 顺手重构 `archive_store.py` 为 repository
- 顺手把 sqlite 改成 PostgreSQL
- 顺手改 search / retrieval 排序逻辑
- 顺手替换正文抽取器
- 顺手做前端页面
- 顺手引入复杂任务编排

这些都不属于 P0，会放大回归面。

## 完成定义

满足以下条件即可认为 P0 完成：

- 项目具备 `uv` 和 `Ruff` 的标准开发入口
- 配置层已分层，不再由单个 `config.py` 承担全部职责
- `tech_blog_monitor` 有可启动的最小 FastAPI 服务
- 前端或外部系统已有稳定读接口可接
- CLI 仍然是可用的主执行入口

## 给 Worker Agent 的一句话任务描述

在不改变 `tech_blog_monitor` 当前抓取、正文、enrichment、sqlite 资产化主链路语义的前提下，完成 P0：补 `pyproject.toml + uv + Ruff`，把 `config.py` 拆成 `pydantic-settings` 驱动的分层配置模块，并增加一个只包装现有能力的最小 FastAPI API。
