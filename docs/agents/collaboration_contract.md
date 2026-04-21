# Agent 协作契约

定义 Planner、Worker、Tester 三个角色之间的信息流、交接格式和循环终止条件。

## 一、协作流程总览 {#协作流程总览}

```
Planner → [DESIGN.md + 验收条件] → Worker → [交付声明] → Tester → [Findings]
                                                                      ↓
                                                              通过 → 进入下一 phase
                                                              不通过 → Worker 修复 → Tester 复验
                                                              系统性问题 → 回流 Planner
```

## 二、Planner → Worker 交接 {#planner-worker-交接}

### 交接产物

- DESIGN.md（含 phase 目标、边界、验收条件、失败路径预判）
- 当前 phase 的最小闭环描述（一句话）
- 明确的"不做"清单

### Worker 接收检查

- 验收条件是否可测试
- Phase 边界是否清晰
- 如有歧义，Worker 应在开始实现前向 Planner 提出

## 三、Worker → Tester 交接 {#worker-tester-交接}

### 交付声明格式

Worker 完成实现后，必须产出一份交付声明：

```markdown
## 交付声明

**Phase**: <phase 编号和名称>
**最小闭环**: <一句话描述>

### 已完成项
- [ ] <能力 1>
- [ ] <能力 2>

### 已知限制
- <限制 1>（计划在 <目标 phase> 处理）

### 测试入口
- 定向测试: <命令>
- 全量回归: <命令>

### 文档同步
- [ ] README 已更新
- [ ] Phase 设计文档已更新
```

### Tester 接收检查

- 交付声明是否完整
- 测试入口是否可执行
- 是否与 DESIGN.md 中的验收条件对应

## 四、Tester → Worker 反馈 {#tester-worker-反馈}

### Findings 格式

严重级别参见 [shared_principles.md#findings-严重级别排序](shared_principles.md#findings-严重级别排序)。

```markdown
## Findings

### Blocker（阻断验收）
1. [B1] <问题描述>
   - 复现方式: <最小复现>
   - 影响: <对最小闭环/失败路径/用户的影响>

### Known-Issue（已知问题，条件通过）
1. [K1] <问题描述>
   - 目标修复 phase: <phase>
   - 风险说明: <当前不修复的影响>

### Tech-Debt（技术债务延迟）
1. [D1] <问题描述>
   - 建议: <修复建议>

## 结论
- [ ] 通过验收
- [ ] 条件通过（Known-Issue: K1, K2...）
- [ ] 不通过验收（Blocker: B1, B2...）
```

### Worker 响应规则

- 先修 Blocker，再处理其他
- 修复后必须跑定向测试 + 全量回归
- 不允许只回复"本地测试都过了"
- 对 Known-Issue 确认接受或提出异议

## 五、Tester → Planner 回流 {#tester-planner-回流}

### 回流触发条件

- 同类 Blocker 在连续 2 个 phase 出现
- 验收条件被证明有歧义或不可测试
- Phase 边界被证明划分不当

### 回流格式

```markdown
## 规划回流

**来源 Phase**: <phase>
**问题类型**: 验收条件歧义 / Phase 边界不当 / 系统性缺口
**描述**: <具体问题>
**建议**: <对后续 phase 规划的调整建议>
```

## 六、循环终止条件 {#循环终止条件}

### Worker-Tester 修复循环

- 终止条件：所有 Blocker 已修复且复验通过
- 最大迭代次数：3 轮
- 超过 3 轮未收敛：升级到 Planner 重新评估 phase 范围

### Phase 验收终止

- 所有 Blocker 已清零
- Known-Issue 已记录到下一 phase 的技术债务清单
- 文档 / 代码 / 测试三者一致

## 七、升级规则 {#升级规则}

- Worker 认为验收条件不合理 → 升级到 Planner
- Tester 认为 phase 边界不成立 → 升级到 Planner
- 修复循环超过 3 轮 → 升级到 Planner
- 发现安全风险 → 直接阻断，不走正常循环
