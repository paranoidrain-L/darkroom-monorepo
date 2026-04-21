# Public Monorepo V1 Checklist

更新时间：`2026-04-21`

## 目标

这份文档用于把当前仓库收敛为一个可公开的 monorepo `V1`。

当前已经确认的公开范围：

- `runtime/`
- `docs/agents/`
- `docs/platform/`
- `products/tech_blog_monitor/`

并且已经确认：

- 不拆双仓
- 先做一个公开 monorepo
- 后续如需公开 `products/feishu_bot/`，继续放在同一个公开仓中

因此本文回答的不是“哪些东西理论上可以开源”，而是：

- 这个公开 monorepo `V1` 应该保留什么
- 应该删除什么
- 应该脱敏后再保留什么

执行删除时，请配合：

- [docs/process/public_monorepo_v1_delete_manifest.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/docs/process/public_monorepo_v1_delete_manifest.md)

执行导出时，优先使用：

- `scripts/export_public_monorepo_v1.sh <target-dir>`

## V1 目标目录

公开 monorepo `V1` 最终建议只保留这几个主要目录：

```text
repo/
├── runtime/
├── docs/
│   ├── README.md
│   ├── agents/
│   ├── platform/
│   └── tech_blog_monitor/
├── products/
│   └── tech_blog_monitor/
├── README.md
├── LICENSE
├── pyproject.toml
├── requirements.txt
├── uv.lock
└── .gitignore
```

## 目录级清单

### 一、直接保留

这些目录和文件可以直接进入 `V1`：

- `runtime/`
- `docs/README.md`
- `docs/agents/`
- `docs/platform/`
- `docs/tech_blog_monitor/`
  - 但要排除 `operations/` 里的私有文档，见后文
- `products/tech_blog_monitor/`
  - 但要处理少量脱敏项，见后文
- `README.md`
  - 需要改成公开版仓库说明
- `LICENSE`
- `pyproject.toml`
- `requirements.txt`
- `uv.lock`
- `alembic/`
  - 如果 `tech_blog_monitor` 的迁移还依赖它，则保留

### 二、删除

这些目录或文件不应进入 `V1`：

- `.claude/`
- `.traecli/`
- `.venv/`
- `.mypy_cache/`
- `.pytest_cache/`
- `.ruff_cache/`
- `.gitlab/`
- `reports/`
- `bot/`
- `common/`
- `capabilities/`
- `config/`
- `deploy/`
- `infra/`
- `prompts/`
- `products/code_review_ci/`
- `products/lint_fix_mr/`
- `products/issue_monitor/`
- `products/pre_occ_agent/`
- `products/feishu_bot/`
  - 当前 `V1` 不公开，后续再单独加回
- `pre_occ_agent_process.md`
- `ai_review_report.md`
- `lint_fix_report.md`
- `diagnosis_753249.md`
- `investigation_753249.md`
- `agent_deploy.sh`
- `deploy.sh`
- `verify.sh`
- `gitlab-ci.jsonnet`
- `CHANGE_LOG.md`
  - 如果内容是内部流水账，可删除；若要保留，需重写成公开 changelog

### 三、脱敏后保留

这些内容可以保留，但不能原样公开：

- `README.md`
  - 改为公开 monorepo 说明
  - 不再列出私有 products
- `docs/tech_blog_monitor/`
  - 保留 `modernization/`、`roadmap/`、`phases/`、`feeds/`
  - 删除或裁剪私有运维文档
- `products/tech_blog_monitor/README.md`
  - 去掉私有运营假设
  - 去掉“完整前端”一类已废弃表述
- `products/tech_blog_monitor/internal_relevance/`
  - 保留框架
  - 文案改成通用技术栈相关性，而不是“内部技术栈画像”
- `products/tech_blog_monitor/delivery.py`
  - 保留通用 webhook / notification 语义
  - 不保留企业接收方约定

## 文档级清单

### `docs/agents/`

建议：全部保留

- `shared_principles.md`
- `planner_methodology.md`
- `worker_methodology.md`
- `tester_methodology.md`
- `collaboration_contract.md`

### `docs/platform/`

建议：全部保留

- `agentic_platform_topology.md`
- `agentic_platform_topology_review.md`

### `docs/process/`

当前 `V1` 原则上不纳入公开范围。

建议处理方式：

- 保留：
  - `docs/process/open_source_scope_v1.md`
  - `docs/process/open_source_split_plan.md`
  - `docs/process/public_monorepo_v1_checklist.md`
- 删除：
  - `docs/process/plan.md`
  - `docs/process/refactor-roadmap.md`
  - `docs/process/agent-development-pipeline.md`
    - 如果未来要公开，可单独改写成平台公开方法论文档

### `docs/tech_blog_monitor/operations/`

建议：

- 保留：
  - `tech_blog_monitor_operations_runbook.md`
    - 仅在确认不含私有环境路径和内部流程后保留
- 删除：
  - `tech_blog_monitor_session_risk.md`
  - `tech_blog_monitor_todo.md`

## 配置与敏感信息清单

以下文件不要进入公开仓：

- `config/feishu_config.json`
- `config/ones_wiki_config.json`
- 任何真实 token / secret / webhook
- 任何真实 `s3://...` 路径
- 任何企业内网地址或企业平台 URL

如果未来公开仓需要示例配置，可以新增公开模板，例如：

- `.env.example`
- `products/tech_blog_monitor/config/stack_profile.example.yaml`

## `tech_blog_monitor` 专项检查

`products/tech_blog_monitor/` 在进入公开仓前，建议重点检查：

### 保留

- 抓取与 source adapters
- content extraction
- search / retrieval / QA / insights
- db / tasks / observability / orchestration
- API / CLI
- test

### 检查并裁剪

- `internal_relevance/`
  - 把“内部”措辞改成更中性的 stack relevance
- `delivery.py`
  - 保留通用 webhook，去掉企业流程化表述
- `README.md`
  - 去掉企业内部语境
- `docs/tech_blog_monitor/operations/`
  - 只保留公开 runbook

## 根 README 改写建议

当前根 README 仍在描述一个包含多个私有产品的全集仓。

公开 monorepo `V1` 的根 README 应改成：

- 只描述公开范围
- 说明这是一个 Agent platform + tech_blog_monitor 的公开 monorepo
- 不再列出未公开的 products
- 明确未来计划中会补 `feishu_bot`

## 推荐执行顺序

### Step 1

先创建公开版目录清单并冻结范围

完成标准：

- 只认这四块
- 不再讨论额外目录是否一起带出

### Step 2

清理根目录与私有目录

完成标准：

- 删除所有 `Keep Private` 目录和文件

### Step 3

裁剪 `products/tech_blog_monitor/` 文档与表述

完成标准：

- 没有“内部平台 / 私有运维 / 企业 webhook 假设”这类强私有表述

### Step 4

重写公开版根 README

完成标准：

- 新用户看到 README 就能理解：
  - 仓库里有什么
  - 现在能跑什么
  - 将来会补什么

## V1 完成定义

满足以下条件，才算 `public monorepo v1` 可对外：

- 仓库范围只包含已确认的四块
- 不含私有配置、私有产品、私有运维资产
- `runtime/` 可独立解释为平台层
- `products/tech_blog_monitor/` 可独立解释为公开产品样板
- 根 README、docs README、产品 README 三者表述一致

## 一句话结论

`public monorepo v1` 不是“在现有仓库上做少量遮挡”，而是：

- 只保留 `runtime/`、`docs/agents/`、`docs/platform/`、`products/tech_blog_monitor/`
- 清理其余目录
- 对根 README 和 `tech_blog_monitor` 做一次公开版改写
