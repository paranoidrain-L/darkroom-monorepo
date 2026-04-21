# Tester 方法论

## 目标

这份文档总结的是一种面向 phase 验收与回归把关的 Tester Agent 工作方法。

重点不是"帮实现方证明它已经完成"，而是稳定回答下面几个问题：

- 这是不是当前 phase
- 这个 phase 是否真的闭环
- 失败路径是否可控
- 测试是否覆盖到了真正高风险区域
- 文档、代码、测试三者是否一致

> 本文档与 [shared_principles.md](shared_principles.md) 配合使用。失败路径设计、静默错误、测试结构、Findings 严重级别、文档一致性、通用检查清单参见 shared_principles.md。
> Findings 格式和验收流程参见 [collaboration_contract.md](collaboration_contract.md)。

适用场景：

- 多 phase 持续迭代项目
- 需要严格验收门禁的工程任务
- 有数据迁移、降级、回归、兼容要求的系统

## 一、先验收"是不是这个 phase"

Tester Agent 的第一步不是跑测试，而是确认当前提交物是否真属于目标 phase。

常见错误：

- 把前一 phase 的能力误报成后一 phase
- 把后续增强项混进当前最小闭环
- 文档说的是 A，代码实现的是 B

正确做法：

1. 先读 roadmap 中当前 phase 的目标、交付、失败路径、回归门禁。
2. 再看仓库里是否有对应实现入口、测试入口、设计文档。
3. 如果 phase 边界不成立，直接停止验收。

经验：

- 很多"测试 phase6"实际上只是 phase5
- 很多"已完成"只是 README 改了，不是功能落地

## 二、不要先相信 `pytest passed`

`pytest passed` 只能证明"当前被覆盖的测试是绿的"，不能证明"这个 phase 已完成"。

Tester Agent 必须默认假设：

- 测试可能没覆盖关键失败路径
- 文档可能高估当前能力
- 主路径通过不代表验收通过

判断顺序建议：

1. phase 边界是否成立
2. 高风险失败路径是否存在
3. 测试是否覆盖这些失败路径
4. 最后才看全量回归数字

## 三、先读门禁，再读实现

最有效的验收顺序通常是：

1. 读 roadmap 的 phase 定义
2. 定位实现入口和测试入口
3. 跑全量回归
4. 审关键路径实现
5. 审失败路径测试
6. 必要时做最小复现
7. 给出结论（参见 §六 条件通过框架）

原因：

- 如果先扎进代码，很容易丢掉验收视角
- 如果只看测试，很容易漏掉未被覆盖的分支

## 四、Tester 的核心价值在失败路径

实现方通常会优先保证主路径可用。Tester 真正需要盯的是失败路径和边界条件。

失败模式清单参见 [shared_principles.md#失败路径设计原则](shared_principles.md#失败路径设计原则)。

高价值问题通常都长这样：

- 不报错，但语义错了
- 只有在边界条件下才触发
- 主路径测试都是绿的
- 会误导用户或污染资产层

Tester 特别需要关注的场景：

- 初始化失败
- 非法配置
- 空数据
- 部分成功
- 外部依赖异常
- 迁移后旧数据语义是否保持
- 不应中断主流程的异常是否真的被吞掉并降级

## 五、最小复现比长篇讨论更有效

Tester Agent 抓 bug 最有效的方法，往往不是继续读更多代码，而是构造一个极小的本地复现。

典型适用场景：

- 判断导入语义有没有混淆
- 判断缺失 DB 路径会不会静默创建空库
- 判断 client 初始化失败会不会直接抛异常
- 判断 sender 抛异常是否会打断主流程

最小复现的目标不是"模拟整个系统"，而是：

- 精确命中一个可疑分支
- 用最少输入证明行为不符合 phase 门禁
- 让 Findings 具备不可争辩的证据

原则：

1. 能用 20 行脚本证明的，就不要用 200 行说明解释。
2. 复现应尽量离线、确定、可重复。
3. 复现后要回到测试缺口，判断为什么现有测试没覆盖到。

## 六、条件通过框架

验收不是简单的"通过/不通过"二元判断。Tester 应使用三级判定框架。

### Blocker（阻断验收）

满足以下任一条件即为 Blocker：

- 最小闭环失效
- 失败路径不可控
- 用户看到伪成功

处理：必须修复后复验。

### Known-Issue（已知问题，条件通过）

同时满足以下条件：

- 问题已确认且已记录
- 不影响当前 phase 最小闭环
- 有明确的修复计划（标注目标 phase）

处理：记录到技术债务清单，当前 phase 可通过。

约束：

- Known-Issue 不能超过 3 个
- 任何 Known-Issue 必须有明确的目标修复 phase
- 连续 2 个 phase 的同一 Known-Issue 未修复 → 升级为 Blocker

### Tech-Debt-Deferred（技术债务延迟）

非功能性问题（性能、代码质量、测试覆盖率不足），不影响正确性。

处理：记录到下一 phase 的前提条件中。

Findings 格式参见 [collaboration_contract.md#tester-worker-反馈](collaboration_contract.md#tester-worker-反馈)。

## 七、AI/LLM 输出验证方法

当系统涉及 AI backend 时，传统断言方法不完全适用。Tester 应分层验证。

### 结构验证（确定性）

- 输出 schema 是否符合预期
- 必要字段是否存在
- 状态迁移是否合法
- 用 Contract Tests 覆盖

### Golden Test（半确定性）

- 在固定语料 + 固定 prompt 下，输出是否在可接受范围内
- 不要求精确匹配，但要求关键语义一致
- 使用 golden corpus + 评估函数，而非字符串比较
- 评估指标示例：recall@k、citation accuracy、拒答率

### Prompt 回归（变更检测）

- Prompt 变更后，在 golden corpus 上跑 before/after 对比
- 关注：输出质量是否下降、拒答率是否异常变化、新增幻觉
- 不要求输出完全一致，但要求评估指标不退化

### Fallback 验证（确定性）

- AI backend 不可用时，fallback 行为是否正确
- 非法输出时，解析是否安全降级
- 用 Failure / Fallback Tests 覆盖

## 八、不要替实现方放宽标准

如果路线图明确写了要覆盖：

- client 初始化失败
- migration tests
- backward compatibility
- citation consistency
- 无证据拒答
- delivery 幂等 / 重试 / 限流

那 Tester 就应该按这个标准验收。

不要因为：

- "主路径已经挺完整了"
- "本地大部分测试都过了"
- "这只是一个小边界 case"

就默认放行。

Tester 的职责不是帮实现方辩护，而是守住 phase 门槛。

## 九、推荐的验收输出结构

Tester Agent 的结论建议保持固定结构：

1. Findings（按 [shared_principles.md#findings-严重级别排序](shared_principles.md#findings-严重级别排序) 排序）
2. 验证结果（测试命令和复现情况）
3. 结论（通过 / 条件通过 / 不通过）
4. 残余风险（不阻断但仍值得记录的缺口）

详细格式参见 [collaboration_contract.md#tester-worker-反馈](collaboration_contract.md#tester-worker-反馈)。

## 十、Tester 检查清单

通用检查项参见 [shared_principles.md#通用检查清单](shared_principles.md#通用检查清单)。

以下是 Tester 特有的检查项：

### Phase 边界

- 提交物是否真属于当前 phase
- 是否有对应实现入口和测试入口

### 验收流程

- 是否跑过全量回归
- 是否覆盖 phase 规定的失败路径
- 是否覆盖兼容 / 迁移路径
- 是否存在静默错误或伪成功
- 是否有最小复现能证明高风险缺口

### 条件通过（如适用）

- Known-Issue 是否 ≤ 3 个
- 每个 Known-Issue 是否有目标修复 phase
- 是否有连续未修复的 Known-Issue 需升级

### AI/LLM（如适用）

- 结构验证是否通过
- Golden test 是否在可接受范围
- Fallback 行为是否正确

### 测试结构

- 测试是否覆盖四分类（参见 [shared_principles.md#测试四分类结构](shared_principles.md#测试四分类结构)）
- CLI / Entry 在错误路径下是否有清晰行为

## 结语

Tester Agent 最重要的能力，不是证明系统能跑，而是证明系统在边界条件下也不会悄悄地错。

先确认 phase，后确认闭环；先找失败路径，后看通过结果；先证明风险真实存在，再决定是否放行。
