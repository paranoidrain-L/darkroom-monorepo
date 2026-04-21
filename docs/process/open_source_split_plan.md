# Open Source Split Plan

更新时间：`2026-04-21`

## 目标

这份文档用于回答一个具体问题：

- 当前 `agents/` 仓库里，哪些东西适合直接开源
- 哪些东西适合脱敏后开源
- 哪些东西应继续保留私有

这里的判断基于当前仓库结构：

- 既包含 `Agent Platform` 底座
- 也包含多个 `products/`
- 还包含企业集成、部署配置、运维文档与本地运行产物

结论先行：

- 最值得开源的是 `Platform Core + 通用产品`
- 最不适合直接开源的是 `企业集成 + 内部配置 + 运维资产`
- 最合理的执行方式不是“整仓直接公开”，而是“拆成 2~3 个公开仓 + 一个私有集成仓”

当前已确认的首批公开范围见：

- [docs/process/open_source_scope_v1.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/docs/process/open_source_scope_v1.md)

当前 `V1` 只公开四块：

- `runtime/`
- `docs/agents/`
- `docs/platform/`
- `products/tech_blog_monitor/`

## 分类原则

目录或模块是否适合开源，按以下顺序判断：

1. 是否对外具备独立价值
2. 是否依赖内部平台、内部账号体系或内部流程
3. 是否包含真实凭证、真实地址、真实存储路径或真实运维信息
4. 是否需要保留，但应先改为更中性的 public contract

本文统一用三类标签：

- `Open Source`
  - 可以直接作为公开仓内容
- `Redact Then Open`
  - 建议先脱敏、抽象或裁剪，再开源
- `Keep Private`
  - 明显内部耦合或含敏感信息，不建议公开

## 顶层目录拆分建议

| 路径 | 建议 | 原因 |
| --- | --- | --- |
| `runtime/` | `Open Source` | 通用 AI runtime 抽象，具备独立价值 |
| `capabilities/prompts/` | `Open Source` | 通用 prompt 模板，可直接公开 |
| `capabilities/skills/code-review/` | `Open Source` | 通用代码审查方法论 |
| `capabilities/skills/lint-fix/` | `Redact Then Open` | 可公开，但需去掉企业流程描述 |
| `capabilities/skills/doc-reader/` | `Open Source` | 通用文档读取能力 |
| `capabilities/skills/s3-tools/` | `Redact Then Open` | 能力可开，但需去掉私有 endpoint / profile 叙述 |
| `capabilities/skills/ones-wiki/` | `Keep Private` | 强依赖 ONES |
| `capabilities/tools/doc_reader/` | `Open Source` | 通用 MCP 工具 |
| `capabilities/tools/s3/` | `Redact Then Open` | 工具可开，但配置体系需脱敏 |
| `capabilities/tools/ones_wiki/` | `Keep Private` | 强依赖 ONES |
| `common/` | `Redact Then Open` | 可公开，但更适合作为兼容层并回 `runtime/` |
| `deploy/` | `Redact Then Open` | 可开源为通用 deploy helper，但不要带内部默认假设 |
| `infra/` | `Keep Private` | 当前偏内部基础设施骨架，公开价值不高 |
| `docs/agents/` | `Open Source` | Planner / Worker / Tester 方法论可公开 |
| `docs/platform/` | `Open Source` | Agentic Platform / VSM 文档适合公开 |
| `docs/process/agent-development-pipeline.md` | `Redact Then Open` | 框架可公开，但需去掉企业路径和工具链细节 |
| `docs/process/refactor-roadmap.md` | `Keep Private` | 偏内部重构过程记录 |
| `docs/process/plan.md` | `Keep Private` | 偏内部迁移过程记录 |
| `products/` | `Mixed` | 需按产品逐个判断 |
| `config/` | `Keep Private` | 当前含真实本地配置文件和企业接入配置 |
| `docker/` | `Redact Then Open` | 若不含企业 registry / 内网依赖，可裁剪后公开 |
| `.gitlab/` / `gitlab-ci.jsonnet` | `Keep Private` | 明显企业 CI 耦合 |
| `reports/` | `Keep Private` | 运行产物，不应开源 |
| `pre_occ_agent_process.md` | `Keep Private` | 明显内部文档 |
| `agent_deploy.sh` / `deploy.sh` / `verify.sh` | `Redact Then Open` | 可保留公共版，但要去企业环境假设 |
| `README.md` | `Redact Then Open` | 应改为公开版仓库说明 |
| `requirements.txt` / `pyproject.toml` / `uv.lock` | `Open Source` | 可直接公开 |

## Products 拆分建议

### 1. `products/tech_blog_monitor/`

建议：`Open Source`

原因：

- 独立性最好
- 技术边界清晰
- 通用价值强
- 已具备完整 README、测试、架构层次和数据层

可以直接公开的核心：

- source adapters
- content extraction
- search / retrieval / QA / insights
- task / observability / orchestration
- API / CLI

需要先裁剪的部分：

- `internal_relevance/` 中与“内部技术栈画像”强绑定的叙述
- `delivery.py` 中过于企业化的 webhook 语义
- `docs/tech_blog_monitor/operations/` 中的运维私有文档

推荐结论：

- 可以作为第一优先级公开仓

### 2. `products/code_review_ci/`

建议：`Redact Then Open`

原因：

- 核心 reviewer 逻辑具备公开价值
- 但当前仍带有 CI、企业流程和后端运行方式假设

公开建议：

- 保留 reviewer / report / models
- 去掉企业 CI 约束、企业审批语义、默认内部触发方式

### 3. `products/lint_fix_mr/`

建议：`Redact Then Open`

原因：

- 核心能力有价值
- 但 `MR` / `GitLab` 流程强耦合

公开建议：

- 保留 lint 修复和 AI 修复能力
- 将 `git_mr.py` 改造成更中性的 SCM adapter

### 4. `products/feishu_bot/`

建议：`Redact Then Open`

原因：

- 可以公开
- 但平台绑定明显，且不是当前最强样板产品

公开优先级：

- 低于 `tech_blog_monitor`

### 5. `products/issue_monitor/`

建议：`Keep Private`

原因：

- 强依赖 ONES
- 配置、数据模型和使用场景都偏企业内生

### 6. `products/pre_occ_agent/`

建议：`Keep Private`

原因：

- 强依赖你们自己的 S3 路径、数据格式和业务流程
- 即使脱敏，公开价值也低于维护成本

## 配置与文档脱敏清单

以下内容不要直接公开：

- `config/feishu_config.json`
- `config/ones_wiki_config.json`
- 任何真实 token / secret / webhook
- 任何真实 `s3://...` 路径
- 任何真实 ONES / Feishu / GitLab 企业地址
- 运行产物与诊断报告
- 私有运维文档

应保留但替换为 template 的内容：

- `config/feishu_config.template.json`
- `config/ones_wiki_config.template.json`
- `config/mcp/s3_config.template.json`

文档层建议删除或私有化：

- `docs/process/refactor-roadmap.md`
- `docs/process/plan.md`
- `docs/tech_blog_monitor/operations/tech_blog_monitor_session_risk.md`
- `docs/tech_blog_monitor/operations/tech_blog_monitor_todo.md`

文档层建议保留公开版：

- `docs/agents/`
- `docs/platform/`
- `docs/tech_blog_monitor/modernization/`
- `docs/tech_blog_monitor/phases/`
- `docs/tech_blog_monitor/roadmap/`

但需要注意：

- 与企业内部使用习惯强绑定的措辞，建议改写为更中性的 public wording

## 推荐拆仓方式

### 仓库 A：`agent-platform-core`

建议内容：

- `runtime/`
- `capabilities/prompts/`
- `capabilities/skills/` 中的通用部分
- `capabilities/tools/doc_reader/`
- 可裁剪后的 `capabilities/tools/s3/`
- `docs/agents/`
- `docs/platform/`
- 裁剪后的 `deploy/`

定位：

- 多 Runtime Agent 平台底座

### 仓库 B：`tech-blog-monitor`

建议内容：

- `products/tech_blog_monitor/`
- `docs/tech_blog_monitor/` 中的公开版文档

定位：

- 技术情报 / 技术博客监控产品

### 仓库 C：`agent-enterprise-integrations` 私有

建议内容：

- `products/issue_monitor/`
- `products/pre_occ_agent/`
- `capabilities/tools/ones_wiki/`
- `capabilities/skills/ones-wiki/`
- `config/`
- `.gitlab/`
- 私有流程和运维文档

定位：

- 企业集成与私有业务产品仓

## 推荐执行顺序

### Step 1

先拆 `tech_blog_monitor`

原因：

- 最完整
- 最独立
- 对外最容易讲清楚
- 风险最低

### Step 2

再拆 `agent-platform-core`

原因：

- 可以把 `runtime + skills + docs/platform` 抽成真正的平台仓
- 对外品牌会更清晰

### Step 3

最后保留企业集成私有仓

原因：

- 这部分最不适合公开
- 也最容易因为脱敏不足带来风险

## 首批开源建议

如果你们只想先开一批最稳的内容，我建议公开：

- `runtime/`
- `docs/agents/`
- `docs/platform/`
- `capabilities/prompts/`
- `capabilities/skills/code-review/`
- `capabilities/skills/doc-reader/`
- `capabilities/tools/doc_reader/`
- `products/tech_blog_monitor/`

第二批再考虑：

- `products/code_review_ci/`
- `products/lint_fix_mr/`
- `capabilities/tools/s3/`
- `capabilities/skills/s3-tools/`
- `products/feishu_bot/`

明确不建议首批公开：

- `products/issue_monitor/`
- `products/pre_occ_agent/`
- `capabilities/tools/ones_wiki/`
- `capabilities/skills/ones-wiki/`
- `config/`
- `.gitlab/`
- `reports/`

## 一句话结论

这套仓库最合理的开源策略不是“整个仓库直接公开”，而是：

- 把 `Platform Core` 和 `tech_blog_monitor` 作为公开资产
- 把企业集成和私有运维资产继续保留私有
- 对边界不清晰的模块先做一次 public edition 裁剪，再决定是否公开
