# 飞书机器人

这版实现只保留一种运行方式，而且运行时几乎全部交给 `lark-cli`：

- 入站事件：`lark-cli event +subscribe`
- 出站消息：`lark-cli im +messages-reply`
- 文件资源下载：`lark-cli im +messages-resources-download`
- AI 对话：复用仓库里的 `runtime.factory.get_client`

这样把原来手写 webhook 验签、解密、回复和文件下载逻辑都移掉了。

## 当前能力

- 文本对话
- 文件上传后，等待下一条文本指令再分析文件
- 会话级文件上下文，默认 300 秒过期
- 对话日志写入 `logs/conversations/YYYY-MM-DD.jsonl`
- 可选 SQLite 会话记忆，支持重启后恢复同一会话历史
- `/reset`、`/summary`、`/memory off`、`/memory on` 会话记忆控制命令
- 默认只处理 P2P 会话，避免在群里失控回复

## 前置条件

1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

2. 安装并登录 `lark-cli`

```bash
npm install -g @larksuite/cli
lark-cli config init
lark-cli auth login --recommend
```

3. 飞书应用需要至少具备这些权限

- `im:message`
- `im:message:send_as_bot`
- `im:file`

## 配置

环境变量示例：

```bash
export LARK_CLI_PATH="lark-cli"
export FEISHU_BACKEND="codex"       # 或 claude_code / trae / claude
export FEISHU_MODEL="GLM-5"
export TRAE_CLI_PATH="trae-cli"
export FEISHU_MEMORY_STORE="sqlite"
export FEISHU_MEMORY_DB_PATH="data/feishu_bot_memory.sqlite3"
export FEISHU_MEMORY_TRACE_ENABLED="true"
export FEISHU_MEMORY_LOG_REDACTION="true"
export FEISHU_MEMORY_ENABLE_AUTO_SUMMARY="false"
```

公开模板配置见 `config/feishu_bot.example.json`。建议复制为本地私有配置文件后再启动。

JSON 配置示例：

```json
{
  "backend": "codex",
  "model": "GLM-5",
  "agent": "",
  "trae_cli_path": "trae-cli",
  "timeout": 120,
  "lark_cli_path": "lark-cli",
  "log_dir": "logs/conversations",
  "download_dir": "downloads",
  "session_ttl": 300,
  "allow_group_chats": false,
  "event_types": "im.message.receive_v1",
  "memory_store": "sqlite",
  "memory_db_path": "data/feishu_bot_memory.sqlite3",
  "memory_busy_timeout_ms": 5000,
  "memory_enabled": true,
  "memory_trace_enabled": true,
  "memory_log_redaction": true,
  "memory_enable_auto_summary": false,
  "memory_enable_fact_extraction": false
}
```

如果已经完成 `lark-cli config init`，通常不需要再单独配置 `app_id` / `app_secret` 给机器人。

记忆能力默认仍是 `in_memory`。需要重启恢复时显式配置 `memory_store=sqlite` 和独立 `memory_db_path`。

## 启动

```bash
python -m products.feishu_bot.client
python -m products.feishu_bot.client --config config/feishu_bot.local.json
```

## 使用方式

文本对话：

1. 给机器人发送文本
2. 机器人调用配置好的 AI 后端返回结果

会话记忆控制：

- `/summary`：查看当前会话摘要
- `/reset`：清空当前会话记忆和待处理文件
- `/memory off`：当前会话后续消息不读写长期记忆
- `/memory on`：恢复当前会话记忆；如果全局 `memory_enabled=false`，该命令不会覆盖灰度开关

文件分析：

1. 发送一个支持的文本类文件
2. 机器人回复“已收到文件”
3. 再发一条文本指令，例如“帮我总结这个文件”
4. 机器人把文件内容和你的指令一起喂给 AI

支持的特殊文件名：

- `.env`
- `Dockerfile`
- `Makefile`

## 代码结构

- `bot.py`：进程生命周期、`lark-cli` 事件订阅、worker queue 和消息分发
- `message_parser.py`：飞书事件解析、文本内容提取
- `file_flow.py`：文件下载、读取、pending file 流程
- `memory_adapter.py`：memory scope、store/service 构造、memory 命令和 summary/facts helper
- `logging.py`：conversation JSONL、trace 记录和敏感信息脱敏

## 运行测试

```bash
python -m pytest -q products/feishu_bot/test/test_bot.py
```

## 设计限制

- webhook 模式已经移除
- 当前默认串行处理消息，优先保证顺序和稳定性
- 如果 `lark-cli` 未安装、未配置或权限不足，启动或回复阶段会直接报错到日志
