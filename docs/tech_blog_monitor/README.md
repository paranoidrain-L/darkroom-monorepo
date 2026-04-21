# Tech Blog Monitor Docs

`tech_blog_monitor` 的文档已经按用途整理到独立目录，建议从这里进入。

## 目录结构

```text
docs/tech_blog_monitor/
├── README.md
├── feeds/            # feed 配置说明与示例
├── roadmap/          # 执行路线、长期规划、质量迭代、rebaseline
├── modernization/    # P0 / P1 / P1.5 / P2 现代化方案与归档
├── phases/           # 历史 phase 设计文档
└── operations/       # 公开 runbook
```

## 推荐阅读顺序

### 当前路线

- [roadmap/tech_blog_long_term_roadmap.md](roadmap/tech_blog_long_term_roadmap.md)
- [roadmap/tech_blog_capability_vsm_mapping.md](roadmap/tech_blog_capability_vsm_mapping.md)
- [roadmap/tech_blog_next_stage_development_plan.md](roadmap/tech_blog_next_stage_development_plan.md)
- [roadmap/P1_2_PLAN.md](roadmap/P1_2_PLAN.md)
- [roadmap/P1_3_PLAN.md](roadmap/P1_3_PLAN.md)
- [roadmap/P1_4_PLAN.md](roadmap/P1_4_PLAN.md)
- [roadmap/P1_5_DESIGN.md](roadmap/P1_5_DESIGN.md)
- [roadmap/tech_blog_execution_roadmap.md](roadmap/tech_blog_execution_roadmap.md)
- [roadmap/tech_blog_quality_iteration_plan.md](roadmap/tech_blog_quality_iteration_plan.md)

### 现代化归档

- [modernization/tech_monitor_modernization_plan.md](modernization/tech_monitor_modernization_plan.md)
- [modernization/P2_1_PLAN.md](modernization/P2_1_PLAN.md)
- [modernization/P2_2_PLAN.md](modernization/P2_2_PLAN.md)
- [modernization/P2_3_PLAN.md](modernization/P2_3_PLAN.md)
- [modernization/tech_blog_p1_data_retrieval_modernization.md](modernization/tech_blog_p1_data_retrieval_modernization.md)
- [modernization/tech_blog_p1_5_content_extraction_modernization.md](modernization/tech_blog_p1_5_content_extraction_modernization.md)
- [modernization/tech_blog_p2_observability_orchestration_modernization.md](modernization/tech_blog_p2_observability_orchestration_modernization.md)

### 历史设计

- [phases/tech_blog_phase1_asset_design.md](phases/tech_blog_phase1_asset_design.md)
- [phases/tech_blog_phase2_content_fetch.md](phases/tech_blog_phase2_content_fetch.md)
- [phases/tech_blog_phase3_enrichment.md](phases/tech_blog_phase3_enrichment.md)
- [phases/tech_blog_phase4_search.md](phases/tech_blog_phase4_search.md)
- [phases/tech_blog_phase5_rag.md](phases/tech_blog_phase5_rag.md)
- [phases/tech_blog_phase6_insights.md](phases/tech_blog_phase6_insights.md)
- [phases/tech_blog_phase7_productization.md](phases/tech_blog_phase7_productization.md)

### 运行与配置

- [feeds/rss-feeds.md](feeds/rss-feeds.md)
- [feeds/rss-feeds-example.yaml](feeds/rss-feeds-example.yaml)
- [operations/tech_blog_monitor_operations_runbook.md](operations/tech_blog_monitor_operations_runbook.md)

## 整理原则

- roadmap 和长期规划放一起
- modernization 文档单独归档，避免和当前执行计划混在一起
- 历史 phase 设计保留，但不再作为主入口
- 运维和 feeds 文档单独放，便于查找
