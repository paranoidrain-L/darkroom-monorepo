# Tech Blog Monitor Phase 7: 产品化输出

## 目标

让系统从“本地分析脚本”升级为“可分发、可消费、可反馈”的最小产品闭环。

当前交付范围：

- 角色化 digest 模板
- webhook 分发链路
- delivery 幂等 / 重试 / 限流
- feedback 落库与查询

## 当前实现边界

已落地：

- `ArchiveStore` schema `v5`
- `deliveries` / `feedback` 两张表
- `products.tech_blog_monitor.delivery`
- `products.tech_blog_monitor.feedback`
- `products.tech_blog_monitor.feedback_cli`
- 主流程在配置开启时自动出发 delivery

当前仍未做：

- 真实飞书适配器
- push queue / worker 分离部署
- 用户级订阅配置
- richer role templates
- 推荐阅读排序学习

## 设计说明

### Delivery

当前 delivery 模型依赖以下字段：

- `run_id`
- `role`
- `cadence`
- `dedupe_key`
- `status`
- `attempt_count`

通过 `dedupe_key = "{run_id}:{role}:{cadence}"` 保证单次 run 对单角色单周期只会生成一条 delivery。

### Retry / Rate Limit

当前实现策略：

- 非 2xx 响应记为失败尝试
- 未达到 `max_retries` 时保留 `pending`
- 超过上限转 `failed`
- 单分钟超过配额时标记为 `rate_limited`

### Feedback

反馈直接关联到 `run_id`，支持：

- `role`
- `feedback_type`
- `feedback_text`
- `metadata`

这样后续可以继续演进成：

- 角色偏好
- 推荐优化
- push 质量回放

## 测试门禁

Phase 7 本地测试覆盖：

- 推送幂等测试
- 失败重试测试
- 限流测试
- 角色模板消息格式测试
- 用户反馈落库测试
- monitor 主流程 delivery 集成测试
