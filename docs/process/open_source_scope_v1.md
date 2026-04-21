# Open Source Scope V1

更新时间：`2026-04-21`

## 当前决定

首批公开范围只包含以下四块：

- `runtime/`
- `docs/agents/`
- `docs/platform/`
- `products/tech_blog_monitor/`

这份文档的作用不是讨论“还能不能多开一些”，而是把当前已经确认的首批范围固定下来，避免后续执行时继续漂移。

实际执行时，请配合：

- [docs/process/public_monorepo_v1_checklist.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/docs/process/public_monorepo_v1_checklist.md)

## V1 范围清单

### 1. `runtime/`

定位：

- Agent Platform 的多 Runtime 抽象层

应包含：

- `runtime/factory.py`
- `runtime/launcher.py`
- `runtime/clients/`
- `runtime/test/`

公开价值：

- 统一 `claude / claude_code / trae / codex` 后端接口
- 为 CLI Agent、代码审查 Agent、内容 Agent 提供复用底座

注意事项：

- 文档中不要默认假设任何企业级本地安装路径
- 环境变量和认证方式应只保留通用描述

### 2. `docs/agents/`

定位：

- Planner / Worker / Tester 协作方法论

应包含：

- `docs/agents/shared_principles.md`
- `docs/agents/planner_methodology.md`
- `docs/agents/worker_methodology.md`
- `docs/agents/tester_methodology.md`
- `docs/agents/collaboration_contract.md`

公开价值：

- 多 Agent 协作协议
- 任务分工与验收方法论

注意事项：

- 保持方法论文档，不引入私有流程地址或企业内部平台假设

### 3. `docs/platform/`

定位：

- Agentic Platform / VSM 设计文档

应包含：

- `docs/platform/agentic_platform_topology.md`
- `docs/platform/agentic_platform_topology_review.md`

公开价值：

- 平台分层设计
- VSM 骨架与 SubAgent 拓扑

注意事项：

- 保持概念和方法论层
- 不引用私有业务背景作为前提

### 4. `products/tech_blog_monitor/`

定位：

- 首批公开的完整产品样板

应包含：

- 抓取、source adapters、正文抽取、search / retrieval / QA / insights
- observability / tasks / orchestration
- API / CLI
- test

公开价值：

- 独立产品完整度最高
- 最容易成为外界理解这套平台能力的样板仓

注意事项：

- `internal_relevance/` 中与“内部技术栈画像”强绑定的描述应改成中性 public wording
- `delivery.py` 保留通用 webhook 语义，不带企业内部接收方约定
- 不导出任何私有 runbook、session risk、todo、reports

## V1 明确不包含

以下内容不属于首批公开范围：

- `capabilities/`
- `common/`
- `deploy/`
- `infra/`
- `products/code_review_ci/`
- `products/lint_fix_mr/`
- `products/feishu_bot/`
- `products/issue_monitor/`
- `products/pre_occ_agent/`
- `config/`
- `.gitlab/`
- `reports/`
- `docs/process/`
- `docs/tech_blog_monitor/operations/`

这些内容后续可以继续评估，但不属于当前 V1。

## V1 推荐输出形式

最推荐的方式不是从原仓直接公开，而是导出两个公开仓：

### 仓库 A：`agent-platform-core`

仅包含：

- `runtime/`
- `docs/agents/`
- `docs/platform/`

### 仓库 B：`tech-blog-monitor`

仅包含：

- `products/tech_blog_monitor/`

如果当前不想立刻拆成两个仓，也可以先做一个临时公开仓，但目录边界仍建议保持一致。

## V1 执行顺序

### Step 1

先处理 `products/tech_blog_monitor/`

原因：

- 产品可展示性最强
- 样板意义最大
- 风险相对最低

### Step 2

再处理 `runtime/ + docs/agents/ + docs/platform/`

原因：

- 这部分更像平台仓
- 需要重新整理公共 README 和包边界

## 验收口径

当且仅当满足以下条件，才算完成 `Open Source V1` 收口：

- 公开范围严格限制在这四块
- 不包含真实配置、真实凭证、真实运维产物
- `tech_blog_monitor` 可以单独作为公开产品解释清楚
- `runtime/ + docs/agents/ + docs/platform/` 可以单独作为平台底座解释清楚

## 一句话结论

`Open Source V1` 的范围已经固定为四块：

- `runtime/`
- `docs/agents/`
- `docs/platform/`
- `products/tech_blog_monitor/`

其他目录先不动，不在这一轮讨论范围内。
