# Public Monorepo V1 Audit Round 2

更新时间：`2026-04-21`

## 目标

这份审计记录用于复核 `Darkroom` 公开仓在首轮上线后的公开边界，重点检查：

- 是否仍残留本机绝对路径
- 是否仍残留私有产品或企业化表述
- 是否存在误提交真实凭证、真实 webhook、真实 repo root 的风险
- 是否存在会误导外部协作者的缺失链接或错误入口

## 本轮检查方法

主要通过全文搜索和工作树复核完成，口径包括：

- 敏感词：`senseauto`、`sensetime`、`feishu`、`ones`、`token`、`secret`
- 路径：本机绝对路径模式
- 公开边界：`webhook`、`internal`、私有配置与运维痕迹

## 已修复问题

### 1. 公开文档仍残留本机绝对路径

本轮修复了以下类别：

- `docs/README.md`
- `docs/platform/agentic_platform_topology_review.md`
- `docs/process/*.md`
- `docs/tech_blog_monitor/README.md`
- `docs/tech_blog_monitor/phases/tech_blog_phase0_modernization.md`
- `docs/tech_blog_monitor/modernization/*.md` 中的部分公开入口

修复方式：

- 将内部绝对路径改为仓内相对链接
- 将本机命令路径改为通用 `uv run ...` 形式

### 2. 公开文档索引仍引用已删除的私有 operations 文件

已从 `docs/tech_blog_monitor/README.md` 中移除：

- `tech_blog_monitor_session_risk.md`
- `tech_blog_monitor_todo.md`

当前只保留公开 runbook 入口。

### 3. 公开仓仍带有私有产品残留表述

已修复：

- 根 `README.md` 中对未来 `feishu_bot` 的直接提及
- `public_monorepo_v1_checklist.md` 中的未来产品表述
- `requirements.txt` 中的 `feishu_bot 依赖` 注释

处理方式：

- 改成更中性的 “更多 products” / “通用 API / webhook 集成依赖”

### 4. `.gitignore` 仍保留不属于公开仓的私有配置路径

已移除：

- `s3_config.json`
- `config/ones_wiki_config.json`

这些路径不属于当前公开仓 contract，不应继续出现在公开忽略规则中。

## 本轮结论

当前没有发现真实 token、真实 webhook、真实数据库 URL、真实 repo root 被跟踪进 git。

本轮修复后，公开边界的主要阻塞项已经收口：

- 文档不再依赖本机绝对路径
- 公开索引不再指向未导出的私有文件
- 根级公开说明不再混入不必要的私有产品语境

## 仍可接受的命中项

以下命中项在本轮审计中保留，属于可接受公开内容：

- `uv.lock` 中的 `https://pypi.org/...` 与 wheel URL
- `LICENSE` 中的 Apache 官方 URL
- 示例配置中的 `https://example.com/webhook`
- 测试中的 fake token / example URL
- `runtime/clients/claude.py` 中公开服务 URL 与环境变量名
- `products/tech_blog_monitor/internal_relevance/` 目录名
  当前作为兼容模块名保留，公开文案已统一收敛到 `stack relevance`

## 下一步建议

如果继续做第三轮公开化收口，优先级建议是：

1. 补 `SECURITY.md`
2. 补 `CODE_OF_CONDUCT.md`
3. 为 `tech_blog_monitor` 增加面向外部用户的 5 分钟 quickstart
4. 清理 `docs/process/` 中过于内部化、但已不再需要对外解释的历史导出文档
