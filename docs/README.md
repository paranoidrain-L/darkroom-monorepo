# Docs Index

`docs/` 目录按主题拆分，避免所有文档继续堆在根目录。

当前公开 monorepo `v1` 主要保留三类文档。公开仓品牌名为 `Darkroom`：

- `docs/agents/`
- `docs/platform/`
- `docs/tech_blog_monitor/`

## 目录结构

```text
docs/
├── README.md                    # 文档总索引
├── agents/                      # Planner / Worker / Tester 方法论与协作契约
├── platform/                    # Agentic platform / VSM 相关设计
├── process/                     # 开源拆分与导出相关文档
└── tech_blog_monitor/           # tech_blog_monitor 专项文档
```

## 入口建议

如果你只关心 `tech_blog_monitor`：

- 先看 [docs/tech_blog_monitor/README.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/docs/tech_blog_monitor/README.md)

如果你在看 Agent 协作方法：

- 先看 [docs/agents/shared_principles.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/docs/agents/shared_principles.md) — 三角色共享原则
- 看 [docs/agents/planner_methodology.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/docs/agents/planner_methodology.md) — Planner 方法论
- 看 [docs/agents/worker_methodology.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/docs/agents/worker_methodology.md) — Worker 方法论
- 看 [docs/agents/tester_methodology.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/docs/agents/tester_methodology.md) — Tester 方法论
- 看 [docs/agents/collaboration_contract.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/docs/agents/collaboration_contract.md) — 角色间协作契约

如果你在看平台拓扑与 VSM：

- 看 [docs/platform/agentic_platform_topology.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/docs/platform/agentic_platform_topology.md)
- 看 [docs/platform/agentic_platform_topology_review.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/docs/platform/agentic_platform_topology_review.md)

如果你在看公开仓范围与导出计划：

- 看 [docs/process/open_source_scope_v1.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/docs/process/open_source_scope_v1.md)
- 看 [docs/process/open_source_split_plan.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/docs/process/open_source_split_plan.md)
- 看 [docs/process/public_monorepo_v1_checklist.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/docs/process/public_monorepo_v1_checklist.md)
- 看 [docs/process/public_monorepo_v1_delete_manifest.md](/home/SENSETIME/luoshunwei/WorkSpace/agent_workspace/agents/docs/process/public_monorepo_v1_delete_manifest.md)

## 约定

- 开源拆分与导出说明放在 `docs/process/`
- 平台与多 Agent 设计放在 `docs/platform/`
- 具体产品专项文档放在各自子目录下
- `tech_blog_monitor` 的 roadmap、modernization、phases、operations、feeds 分开存放，不再直接平铺在 `docs/` 根目录
