# P1.5 Internal Relevance Layer Design

更新时间：`2026-04-18`

## 目标

`P1.5` 的目标不是做完整知识图谱，而是先回答一个更直接的问题：

- 这条外部技术动态，和我们的内部技术栈有没有关系

第一版必须满足三个要求：

- 可落地
- 可解释
- 可渐进增强

## 设计范围

第一版只做：

- 技术栈画像输入
- manifest 扫描
- article/topic 与内部栈的相关性打分
- relevance report / article relevance hint

第一版不做：

- 完整 entity-relation 图谱
- 全仓库静态分析
- 自动触发外部动作
- 复杂在线个性化推荐

## 一、输入来源

内部技术栈信息采用双路径：

### 1. 手工配置层

使用一份显式配置文件，例如：

- `stack_profile.yaml`

它是第一版的权威覆盖层，用来表达：

- 关键语言
- 核心框架
- 中间件 / 数据库
- 云基础设施
- 团队关注主题
- 权重和优先级

手工配置层的作用：

- 解决扫描不全的问题
- 允许写入“虽然仓库没直接声明，但团队明确在关注”的技术
- 作为 relevance 的优先级校准输入

### 2. 自动发现层

自动扫描 repo 中的高信号 manifest 文件：

- `requirements.txt`
- `pyproject.toml`
- `package.json`
- `go.mod`
- `Cargo.toml`

第一版不做更深层代码分析。

原因：

- manifest 扫描实现成本低
- 噪音可控
- 已足够覆盖大部分依赖级相关性判断

## 二、数据模型

第一版建议引入三个核心对象：

### 1. StackProfile

表示内部技术栈画像。

字段建议：

- `profile_id`
- `profile_name`
- `languages`
- `frameworks`
- `libraries`
- `infrastructure`
- `priority_topics`
- `weights`
- `updated_at`

### 2. StackSignal

表示从 repo 或配置中抽出的单个技术信号。

字段建议：

- `signal_id`
- `signal_type`
- `name`
- `normalized_name`
- `aliases`
- `source`
- `weight`
- `repo_scope`

### 3. ArticleRelevance

表示 article 与内部技术栈的相关性结果。

字段建议：

- `article_id`
- `relevance_score`
- `relevance_level`
- `dependency_match_score`
- `topic_match_score`
- `source_priority_score`
- `matched_signals`
- `relevance_reasons`
- `evaluated_at`

## 三、匹配粒度

第一版采用两级匹配。

### L1：依赖级精确匹配

适用场景：

- 文章提到具体库、框架、数据库、中间件
- 内部栈里也存在明确对应对象

例如：

- `FastAPI`
- `Pydantic`
- `PostgreSQL`
- `gRPC`
- `Kubernetes`

匹配方式：

- 规范化名称匹配
- alias 映射
- 标题、标签、topic、摘要、正文中的精确或近似命中

### L2：主题级弱匹配

适用场景：

- 文章不一定提具体依赖名
- 但明显属于团队关注的技术领域

例如：

- `gRPC performance`
- `vector retrieval`
- `PostgreSQL indexing`
- `Kubernetes scheduling`

匹配方式：

- 主题词表
- 受控关键词簇
- article topic / tags / summary / clean_text 的弱匹配

第一版不做完全自由语义推理，优先做可解释规则。

## 四、评分策略

第一版建议使用规则分，不直接上复杂学习模型。

### 总分

`relevance_score = dependency_match_score + topic_match_score + source_priority_score`

### 子分建议

#### dependency_match_score

来源：

- article 与 `StackSignal` 的依赖级匹配

建议规则：

- 强精确匹配：高分
- alias 匹配：中高分
- 多信号同时命中：加分

#### topic_match_score

来源：

- article 的 topic / tags / summary / clean_text 与 `priority_topics`

建议规则：

- topic 直接命中：高分
- tags 命中：中分
- clean_text 弱匹配：低到中分

#### source_priority_score

来源：

- 来源质量和信号可信度

建议规则：

- 官方 release / changelog：高分
- 官方博客：中高分
- 社区讨论：低到中分

## 五、输出形式

第一版同时提供两类输出。

### 1. Article 级输出

给每篇文章附加：

- `relevance_score`
- `relevance_level`
- `relevance_reasons`
- `matched_signals`

用途：

- 在 article 列表、search、QA、insights 中直接消费

### 2. Relevance Report

给单次 run 或单个主题生成：

- 高相关文章列表
- 相关技术信号分布
- 对内部技术栈的潜在影响说明

用途：

- 作为内部情报汇总视图
- 为后续 issue / alert / briefing 提供上游输入

## 六、实施建议

第一版建议拆三步：

### Step 1

- 定义 `stack_profile.yaml` 格式
- 实现 manifest 扫描器
- 产出规范化 `StackSignal`

### Step 2

- 实现 article relevance 打分器
- 输出 `relevance_score` 与 `relevance_reasons`

### Step 3

- 输出 run 级 relevance report
- 在 search / insights / ops 中暴露最小结果

## 七、验收标准

第一版验收建议量化为：

- 至少支持 `1` 份手工技术栈画像输入
- 至少支持 `2` 类 manifest 自动扫描
- 样例集高相关文章的 `Recall@10 >= 0.8`
- article 结果包含结构化 `relevance_score` 与 `relevance_reasons`
- relevance 结果可以解释到“命中了哪些技术信号或主题”

## 八、后续演进

第一版完成后，才考虑继续扩展：

- repo 粒度 relevance
- team / role 粒度 relevance
- entity / relation 网络
- 自动 impact report
- issue draft / alert / watch 等行动闭环
