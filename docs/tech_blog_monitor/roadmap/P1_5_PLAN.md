# P1.5 Internal Relevance Implementation Plan

更新时间：`2026-04-20`

## 执行状态

截至 `2026-04-20`，`P1.5` 可视为已完成并通过验收。

当前结论：

- 建议合入
- 未发现阻塞性问题
- 本文同时作为 `P1.5` 的执行计划与验收归档

## 一句话目标

在不引入重型图谱和复杂个性化系统的前提下，让 `tech_blog_monitor` 能回答：

- `这篇外部技术动态，是否和我们的内部技术栈相关`

第一版必须满足三个要求：

- 可落地
- 可解释
- 可验证

## 验收归档

本轮验收确认，`P1.5` 的核心边界已经满足：

- 已新增第一版 `internal_relevance` 模块，覆盖 `profile_loader`、`manifest_scanner`、`scorer`、`report`
- 已引入独立持久化表 `article_relevances`，没有把 relevance 混入 enrichment 语义
- 已在 `monitor.run()` 中接入 `evaluate_relevance` 阶段，并保留 fail-open 降级路径
- 已将 relevance 结果透传到 article repository、search 结果、JSON 产物和 Markdown 报告
- 已补齐 `TECH_BLOG_STACK_PROFILE_PATH` / `TECH_BLOG_STACK_REPO_ROOTS` 配置契约、fixture-based eval 与主流程回归测试

实现与覆盖证据如下：

- `monitor.py` 已在分析后、写报告前接入 `evaluate_relevance` 阶段，并在异常时降级为 `skipped`
- `db/models.py` 已新增 `ArticleRelevanceModel`
- `db/repositories/article_repository.py` / `db/repositories/search_repository.py` 已透出 relevance 字段
- `internal_relevance/scorer.py` 已实现规则型打分与解释性 reasons
- `test_internal_relevance.py` 已覆盖 article 打分、Recall@10 守门和无输入跳过语义
- `README.md` 已补 stack profile / repo roots / relevance 输出说明

本轮复验结果归档如下：

- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check products/tech_blog_monitor` 通过
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_internal_relevance.py`：`5 passed`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test/test_monitor.py products/tech_blog_monitor/test/test_api.py products/tech_blog_monitor/test/test_search.py products/tech_blog_monitor/test/test_archive_store.py`：`56 passed`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q products/tech_blog_monitor/test`：`266 passed, 1 skipped`

按当前测试证据，可认为以下验收口径已经满足：

- 至少支持 `1` 份手工技术栈画像输入
- 已支持 `requirements*.txt`、`pyproject.toml`、`package.json` 三类 manifest 扫描
- article 结果包含 `relevance_score`、`relevance_level`、`relevance_reasons`
- run 产物包含最小 `relevance_report`
- relevance eval 守门测试已覆盖 `Recall@10 >= 0.8`
- 未配置 relevance 输入时，主流程稳定跳过，不阻塞 run

剩余非阻塞尾项：

- 当前 internal relevance 仍是规则型第一版，尚未进入 repo / team / role 粒度
- 目前 relevance 结果已透传到文章与搜索结果，但还没有独立 relevance API
- manifest 扫描当前聚焦 Python / Node 高信号文件，`go.mod` / `Cargo.toml` 仍可在后续轮次补上

## 为什么现在做

`P1.1` 到 `P1.4` 已经分别补了：

- retrieval 评测基线
- retrieval 排序质量
- source adapter 抽象
- 第一批高信噪比非 RSS source

到这一步，系统已经能：

- 找到更多内容
- 初步判断内容主题
- 提供 search / QA / insights / ops

但还缺少一层真正有内部差异化价值的能力：

- `外部技术变化和我们有没有关系`

如果没有这层，系统仍然更像“技术信息聚合器”；有了这层，才开始进入“内部技术情报工具”的轨道。

## 范围

本阶段包含：

- 定义手工技术栈画像文件格式
- 增加 repo manifest 扫描能力
- 产出规范化 `StackSignal`
- 计算 article 级 relevance 结果
- 输出 run 级 relevance report
- 将 relevance 结果接入现有文章读取与报告产物
- 增加离线样例集和守门测试
- 补最小 README / 配置说明

本阶段不包含：

- 知识图谱
- repo 级深度静态分析
- 个性化推荐
- 高风险自动动作触发
- 新前端
- 大规模新 API 面扩张

## 当前代码现状

当前系统的现实边界如下：

- `fetcher.Article` 仍是抓取期 dataclass，尚无 relevance 字段
- 持久化结构目前以 `articles` / `article_contents` / `article_enrichments` 为主
- `search.py`、`insights.py`、`api/app.py` 都通过 repository 层读取 article 字典
- `monitor.py` 目前在抓取、正文提取、AI enrichment 之后直接进入报告 / 落库 / insights / delivery 链路

这意味着 `P1.5` 的合理接入点应该是：

- 在 enrichment 之后增加一段独立的 relevance 计算
- 通过单独的数据对象或单独表落库
- 让现有 repository 在不破坏旧字段语义的前提下，顺带返回 relevance 字段

## 设计原则

### 1. 先做规则型 relevance，不做黑盒语义系统

第一版不追求“智能推荐感”，而是追求：

- 能解释为什么相关
- 出错时容易排查
- 能被 fixture 和测试守住

### 2. 手工配置层必须存在

只靠仓库扫描，会漏掉：

- 团队关注但尚未落库的技术
- 基础设施层关注项
- 架构主题级关注项

所以第一版必须保留显式 `stack_profile.yaml`。

### 3. 自动发现层只扫高信号 manifest

首批只扫：

- `requirements*.txt`
- `pyproject.toml`
- `package.json`

`go.mod` / `Cargo.toml` 可以在结构上预留，但不要求进入本轮必交付。

### 4. relevance 结果必须能独立存取

不要把 relevance 硬塞进 enrichment 字段，也不要做成仅运行时临时变量。

推荐单独建模，这样后续：

- repository join 更清晰
- 重新打分更容易
- 后续扩到 repo / team / role 粒度时不会反复拆表

### 5. 输出以“文章级字段 + run 级汇总”为主

第一版不要扩很多新 endpoint。

最小可用输出应为：

- article 级结构化字段
- run 级 relevance report
- JSON / Markdown / repository 读取链路可消费

## 目标产物

`P1.5` 第一版交付物应包括：

- `stack_profile.yaml` 契约
- manifest 扫描器
- `StackSignal` 规范化模型
- article relevance 规则打分器
- relevance 持久化层
- run 级 relevance report
- fixture-based relevance eval
- README / 配置说明

## 建议实现方案

### A. 输入层

建议新增最小配置面：

- `TECH_BLOG_STACK_PROFILE_PATH`
- `TECH_BLOG_STACK_REPO_ROOTS`

建议行为：

- 未提供 `TECH_BLOG_STACK_PROFILE_PATH` 时，手工画像层为空
- 未提供 `TECH_BLOG_STACK_REPO_ROOTS` 时，自动扫描层为空
- 两层都为空时，relevance 计算跳过，但主流程继续运行

建议 `TECH_BLOG_STACK_REPO_ROOTS` 为逗号分隔路径列表。

### B. 手工画像格式

建议新增一份示例文件，例如：

- `products/tech_blog_monitor/config/stack_profile.example.yaml`

建议字段：

- `profile_id`
- `profile_name`
- `languages`
- `frameworks`
- `libraries`
- `infrastructure`
- `priority_topics`
- `weights`

其中每个技术项建议至少支持：

- `name`
- `aliases`
- `weight`

### C. 自动发现层

建议实现一个独立扫描模块，例如：

- `products/tech_blog_monitor/internal_relevance/manifest_scanner.py`

第一版至少支持：

- `requirements*.txt`
- `pyproject.toml`
- `package.json`

输出统一的 `StackSignal` 列表，字段建议包含：

- `signal_type`
- `name`
- `normalized_name`
- `aliases`
- `source`
- `weight`
- `repo_scope`

### D. 评分层

建议实现一个规则型打分器，例如：

- `products/tech_blog_monitor/internal_relevance/scorer.py`

总分建议保持和设计稿一致：

- `relevance_score = dependency_match_score + topic_match_score + source_priority_score`

评分输入建议使用现有文章字段：

- `title`
- `rss_summary`
- `ai_summary`
- `one_line_summary`
- `why_it_matters`
- `tags`
- `topic`
- `clean_text`
- `source_name`

建议评分细则：

- `dependency_match_score`
  - 标题 / tags / topic 命中强信号：高分
  - alias 命中：中高分
  - 多个独立信号同时命中：加分
- `topic_match_score`
  - priority topic 命中：中高分
  - 仅正文弱命中：低到中分
- `source_priority_score`
  - `github_releases` / `changelog`：高分
  - 官方 blog：中高分
  - 其他一般 source：中低分

建议输出结构：

- `relevance_score`
- `relevance_level`
- `dependency_match_score`
- `topic_match_score`
- `source_priority_score`
- `matched_signals`
- `relevance_reasons`
- `evaluated_at`

### E. 持久化层

建议新增独立表，例如：

- `article_relevances`

建议字段：

- `article_id`
- `relevance_score`
- `relevance_level`
- `dependency_match_score`
- `topic_match_score`
- `source_priority_score`
- `matched_signals_json`
- `relevance_reasons_json`
- `updated_at`

第一版不要求单独建 `run_relevance_reports` 表。

run 级 relevance report 可在已有 article relevance 基础上按需聚合。

### F. 主流程接线

建议在 `monitor.run()` 中新增独立阶段：

- `evaluate_relevance`

推荐顺序：

1. fetch
2. content fetch
3. analyze articles
4. evaluate relevance
5. build report / archive / insights / delivery

要求：

- 未配置 stack profile / repo roots 时，阶段可跳过
- relevance 失败不能拖垮整次 run，可降级为跳过并记录状态

### G. 结果暴露

第一版建议接入以下消费面：

- article repository 序列化结果增加 relevance 字段
- `/articles` / `/articles/{article_id}` 自然透出 relevance 字段
- `/search` 返回结果中透出 relevance 字段
- JSON 输出增加 `relevance_report`
- Markdown 报告增加一段简短 `Internal Relevance` 摘要

第一版不要求：

- 新增独立 relevance API
- 改 QA 主排序
- 改 retrieval embedding 流程

### H. relevance report

建议新增一个轻量 report builder，例如：

- `products/tech_blog_monitor/internal_relevance/report.py`

run 级 report 最小输出建议包括：

- 高相关 article top list
- 命中的主要技术信号
- 相关性分布
- 一段简短摘要

## 推荐文件落点

建议新增或修改的文件范围如下。

建议新增：

- `docs/tech_blog_monitor/roadmap/P1_5_PLAN.md`
- `products/tech_blog_monitor/internal_relevance/__init__.py`
- `products/tech_blog_monitor/internal_relevance/models.py`
- `products/tech_blog_monitor/internal_relevance/profile_loader.py`
- `products/tech_blog_monitor/internal_relevance/manifest_scanner.py`
- `products/tech_blog_monitor/internal_relevance/scorer.py`
- `products/tech_blog_monitor/internal_relevance/report.py`
- `products/tech_blog_monitor/config/stack_profile.example.yaml`
- `products/tech_blog_monitor/test/test_internal_relevance.py`
- `products/tech_blog_monitor/test/fixtures/internal_relevance_articles.json`
- `products/tech_blog_monitor/test/fixtures/internal_relevance_profile.yaml`

建议修改：

- `products/tech_blog_monitor/defaults.py`
- `products/tech_blog_monitor/settings.py`
- `products/tech_blog_monitor/config.py`
- `products/tech_blog_monitor/config_loader.py`
- `products/tech_blog_monitor/config_validator.py`
- `products/tech_blog_monitor/db/models.py`
- `products/tech_blog_monitor/db/repositories/article_repository.py`
- `products/tech_blog_monitor/monitor.py`
- `products/tech_blog_monitor/search.py`
- `products/tech_blog_monitor/README.md`

如仓库中已有更合适的位置，可在不改变边界的前提下调整落点。

## 分步计划

### Step 1：收口配置与输入契约

目标：

- 把 `stack profile` 和 `repo roots` 的配置入口固定下来

交付：

- 新 env / config 字段
- profile 示例文件
- config contract 测试

完成标准：

- 不配置时系统仍可正常运行
- 配置错误时能给出明确校验信息

### Step 2：实现 manifest 扫描与 `StackSignal`

目标：

- 从手工画像和 repo manifest 统一产出规范化信号

交付：

- profile loader
- manifest scanner
- 去重 / 规范化逻辑

完成标准：

- 至少支持 `requirements*.txt` 和 `pyproject.toml`
- 再额外支持 `package.json`
- 同一技术可通过 alias 收敛为单一 `normalized_name`

### Step 3：实现 article relevance 打分

目标：

- 给单篇 article 产出可解释 relevance 结果

交付：

- scorer
- level 映射
- reasons 生成

完成标准：

- 每条高分结果都能列出命中的 signal 或 topic
- 无命中时返回稳定低分，而不是异常

### Step 4：接入持久化与主流程

目标：

- 让 relevance 进入主产物链路，而不是停留在单元测试级 demo

交付：

- `article_relevances` 持久化
- `monitor.run()` relevance stage
- repository join
- JSON / Markdown relevance report

完成标准：

- 文章查询结果可看到 relevance 字段
- 运行产物包含 run 级 relevance 汇总
- relevance 失败时主流程可降级

### Step 5：补 eval、回归测试与文档

目标：

- 把 `P1.5` 从“看起来合理”变成“可持续守门”

交付：

- fixture corpus
- relevance eval 测试
- README 更新

完成标准：

- relevance eval 守门测试可稳定跑通
- 文档能说明如何提供 stack profile 和 repo roots

## 验收标准

`P1.5` 合入前至少满足：

- 至少支持 `1` 份手工技术栈画像输入
- 至少支持 `2` 类 manifest 自动扫描，且本轮实际实现不少于 `requirements*.txt` / `pyproject.toml` / `package.json` 中的 `2` 类
- article 结果包含结构化 `relevance_score`、`relevance_level`、`relevance_reasons`
- run 产物中包含最小 `relevance_report`
- relevance 样例集的 `Recall@10 >= 0.8`
- relevance 结果能解释到命中了哪些技术信号或主题
- 未配置 relevance 输入时，主流程不报错、不阻塞
- 不出现对 retrieval / QA / delivery 的明显范围漂移

## 建议测试面

至少覆盖以下测试：

- config env contract 测试
- stack profile loader 测试
- manifest scanner 测试
- scorer 单测
- relevance eval fixture 测试
- repository / API 结果透传测试
- monitor 集成测试

建议最少复验命令：

- `uv run ruff check products/tech_blog_monitor`
- `uv run pytest -q products/tech_blog_monitor/test/test_internal_relevance.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_monitor.py`
- `uv run pytest -q products/tech_blog_monitor/test/test_api.py`
- `uv run pytest -q products/tech_blog_monitor/test`

## 非目标与风险提醒

这一轮最容易失控的点有三个：

- 把 `P1.5` 做成新的大而全推荐系统
- 把 article relevance 和 retrieval ranking 混成一层
- 为了“更智能”直接引入不可解释的复杂模型

如果出现这些倾向，应回到本文边界：

- `P1.5` 是 internal relevance 的第一层
- 不是知识图谱
- 不是在线推荐系统
- 不是自动动作引擎

## 结论

`P1.5` 最合理的实现方式，不是继续加概念，而是做成一条明确的可执行链路：

- `stack profile + manifest scan -> StackSignal -> article relevance -> run relevance report -> repository / report exposure`

做到这一步，系统就开始具备“外部技术动态是否和我们相关”的基础判断能力，也为后续 repo 级 relevance、impact report 和行动闭环打下结构化基础。
