# Planner 方法论

## 目标

Planner 的职责是把模糊需求转化为可验收的 phase 计划。

不是"写一份漂亮的设计文档"，而是产出 Worker 能直接执行、Tester 能直接验收的结构化交付物。

Planner 不做的事：

- 不写实现代码
- 不做技术选型的最终决定（提供选项和推荐，Worker 决定）
- 不替代 Tester 做验收

## 一、需求收敛：从模糊到可执行 {#需求收敛}

Planner 的第一步不是开始写设计文档，而是把需求压缩到可执行粒度。

判断标准：如果无法用一句话描述 phase 交付什么，说明范围还没收敛。

收敛方法：

1. 找到核心动词 — "做一个 RAG" 不是需求，"在固定语料上检索并生成带 citation 的回答"才是
2. 划出边界 — 明确"不做"比明确"做什么"更重要
3. 定义最小闭环 — 去掉所有"锦上添花"后，剩下的就是最小闭环

常见反模式：

- "做一个 RAG"（没有边界）
- "支持产品化"（没有具体交付物）
- "优化性能"（没有可测量的目标）

## 二、DESIGN.md 产出规范 {#design-md-产出规范}

DESIGN.md 是 Planner 的核心交付物。与 [agent-development-pipeline.md](../process/agent-development-pipeline.md) Phase 1 的关系：pipeline 定义模板结构，本节定义填写方法。

DESIGN.md 必须包含：

- Agent 边界（负责 / 不负责）
- 自主权等级（L1 / L2 / L3）
- 每个 phase 的最小闭环描述（一句话）
- 每个 phase 的验收条件（Tester 可直接使用）
- 失败路径预判（参见 [shared_principles.md#失败路径设计原则](shared_principles.md#失败路径设计原则)）
- 明确的"不做"清单

### 验收条件写法指南

验收条件是 Planner 和 Tester 之间的契约。

好的验收条件：

- "在 golden corpus 上 recall@10 ≥ 0.6" — 可测量
- "AI backend 不可用时返回 fallback 而非抛异常" — 可复现
- "旧版本 DB 文件可被新版本正常读取" — 可验证

坏的验收条件：

- "性能良好" — 不可测量
- "用户体验好" — 主观
- "基本可用" — 没有边界

每条验收条件应对应一个可测试的断言。

## 三、Phase 划分策略 {#phase-划分策略}

### 轻量模式 vs 完整模式

不是所有任务都需要走完 7 个 phase。

轻量模式适用于：

- 单一能力变更
- 无数据迁移
- 无外部依赖变更
- 影响范围 ≤ 2 个模块

轻量模式只需：Phase 1（边界定义）+ Phase 2（工具设计）+ Phase 7（验证迭代）。

完整模式适用于：

- 涉及数据层变更
- 多组件联动
- 有兼容要求
- 新增 Agent

### Phase 粒度原则

- 每个 phase 应能在一个 Worker 迭代周期内完成
- 每个 phase 应有独立可验收的交付物
- Phase 之间的依赖必须显式声明

常见拆分错误：

- 把"做完整个功能"作为一个 phase（粒度太粗）
- 把测试和文档拆成独立 phase（应内嵌在每个 phase 中）

## 四、验收条件设计 {#验收条件设计}

验收条件分三层：

### 功能门禁

最小闭环是否打通。这是最基本的验收条件。

### 质量门禁

失败路径是否可控。参见 [shared_principles.md#失败路径设计原则](shared_principles.md#失败路径设计原则)。

### 一致性门禁

文档 / 代码 / 测试是否对齐。参见 [shared_principles.md#文档一致性要求](shared_principles.md#文档一致性要求)。

验收条件的可测试性检查：对每条验收条件问一句 — "Tester 能用什么命令或什么复现步骤来验证这条？"如果答不上来，条件需要重写。

## 五、技术债务与风险预判 {#技术债务与风险预判}

Planner 应在 DESIGN.md 中标注已知技术债务和风险。

风险分级：

- 阻断性风险：不解决就无法进入下一 phase
- 可接受风险：已知但不影响当前 phase 闭环，记录并延迟
- 待观察风险：不确定是否会成为问题，标注观察点

Phase 间技术债务传递规则：

- 当前 phase 产生的技术债务必须在 DESIGN.md 中记录
- 下一 phase 的 Planner 必须评估累积债务
- 连续 2 个 phase 未处理的债务应升级优先级

## 六、反馈闭环 {#反馈闭环}

Tester Findings 中的系统性问题应回流到 Planner。

回流触发条件（参见 [collaboration_contract.md#tester-planner-回流](collaboration_contract.md#tester-planner-回流)）：

- 同类问题在多个 phase 重复出现
- 验收条件被证明不可测试或有歧义
- Phase 边界被证明划分不当

回流产��：

- 更新 DESIGN.md
- 调整后续 phase 计划
- 补充验收条件模板（避免同类问题再次出现）

## 七、Planner 检查清单 {#planner-检查清单}

- 需求是否收敛到一句话最小闭环
- DESIGN.md 是否包含所有必要结构
- 验收条件是否可测试（每条都能回答"怎么验"）
- Phase 粒度是否合理（一个迭代周期内可完成）
- 失败路径是否预判
- 技术债务是否标注
- "不做"清单是否明确
- 与 Worker / Tester 的交接格式是否符合 [collaboration_contract.md](collaboration_contract.md)
