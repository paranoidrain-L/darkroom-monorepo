# -*- coding: utf-8 -*-
"""
Trae CLI Client — 通过 subprocess 调用 trae-cli 的 AI 后端
"""

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List

from loguru import logger

from runtime.clients.base import AIClient

# ============== 通用配置 ==============


@dataclass
class TraeClientConfig:
    """Trae CLI 客户端配置"""

    trae_cli_path: str = "trae-cli"
    model: str = ""
    agent: str = ""
    timeout: int = 300
    yolo: bool = True


# ============== JSON 修复工具 ==============


def repair_json(json_str: str) -> Dict[str, Any]:
    """修复并解析可能损坏的 JSON 字符串"""
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    try:
        import json_repair

        result = json_repair.repair_json(json_str, return_objects=True)
        if isinstance(result, dict):
            return result
        return {"data": result}
    except Exception:
        pass

    return _repair_json_builtin(json_str)


def _repair_json_builtin(json_str: str) -> Dict[str, Any]:
    """内置的 JSON 修复方法"""
    json_start = json_str.find("{")
    json_end = json_str.rfind("}") + 1
    if json_start == -1 or json_end <= json_start:
        raise RuntimeError(f"响应中未找到 JSON 格式数据: {json_str[:500]}")

    json_str = json_str[json_start:json_end]

    prev_str = None
    while prev_str != json_str:
        prev_str = json_str
        json_str = re.sub(
            r'"([^"]*?)"\s*\+\s*"([^"]*?)"',
            lambda m: '"' + str(m.group(1)) + str(m.group(2)) + '"',
            json_str,
        )

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON 解析失败: {e}")

    issues = _extract_issues_array(json_str)
    if issues:
        return {"issues": issues, "summary": "JSON 解析部分失败，已提取部分问题"}

    raise RuntimeError(f"无法解析 JSON: {json_str[:500]}")


def _extract_issues_array(json_str: str) -> List[Dict[str, Any]]:
    """从可能损坏的 JSON 中提取 issues 数组"""
    issues: List[Dict[str, Any]] = []
    issues_match = re.search(r'"issues"\s*:\s*\[', json_str)
    if not issues_match:
        return issues

    start_idx = issues_match.end() - 1
    bracket_count = 0
    end_idx = start_idx

    for i in range(start_idx, len(json_str)):
        if json_str[i] == "[":
            bracket_count += 1
        elif json_str[i] == "]":
            bracket_count -= 1
            if bracket_count == 0:
                end_idx = i + 1
                break

    array_str = json_str[start_idx:end_idx]
    i = 0
    while i < len(array_str):
        if array_str[i] == "{":
            brace_count = 0
            start = i
            for j in range(i, len(array_str)):
                if array_str[j] == "{":
                    brace_count += 1
                elif array_str[j] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        obj_str = array_str[start : j + 1]  # noqa: E203
                        try:
                            obj_str = re.sub(r"(?<!\\)\n", "\\n", obj_str)
                            obj_str = re.sub(r"(?<!\\)\t", "\\t", obj_str)
                            obj = json.loads(obj_str)
                            if isinstance(obj, dict):
                                issues.append(obj)
                        except json.JSONDecodeError:
                            pass
                        i = j + 1
                        break
            else:
                i += 1
        else:
            i += 1

    return issues


# ============== Trae CLI 客户端 ==============


class TraeCLIClient(AIClient):
    """Trae CLI 客户端，供所有 agent 复用"""

    def __init__(self, config: TraeClientConfig):
        self.config = config
        self._check_cli_available()

    def _check_cli_available(self) -> bool:
        """检查 Trae CLI 是否可用"""
        try:
            result = subprocess.run(
                [self.config.trae_cli_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info(f"Trae CLI 可用: {result.stdout.strip()}")
                return True
            logger.warning(f"Trae CLI 返回非零状态: {result.stderr}")
            return False
        except FileNotFoundError:
            logger.warning(f"Trae CLI 未找到: {self.config.trae_cli_path}")
            return False
        except subprocess.TimeoutExpired:
            logger.warning("Trae CLI 版本检查超时")
            return False
        except Exception as e:
            logger.warning(f"检查 Trae CLI 时出错: {e}")
            return False

    def _build_command(self, prompt: str) -> List[str]:
        """构建 Trae CLI 命令"""
        cmd = [self.config.trae_cli_path]
        if self.config.yolo:
            cmd.append("-y")
        if self.config.model:
            cmd.extend(["-c", f"model.name={self.config.model}"])
        if self.config.agent:
            cmd.extend(["-c", f"agent={self.config.agent}"])
        cmd.extend(["-p", "--json", "--query-timeout", f"{self.config.timeout}s", prompt])
        return cmd

    def chat(self, prompt: str) -> str:
        """发送 prompt 到 Trae CLI 并获取响应"""
        cmd = self._build_command(prompt)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout + 30,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Trae CLI 执行失败: {result.stderr}")

            output = result.stdout.strip()
            if not output:
                raise RuntimeError("Trae CLI 返回空输出")

            try:
                return self._extract_content(json.loads(output))
            except json.JSONDecodeError:
                pass

            for line in output.splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    return self._extract_content(json.loads(line))
                except (json.JSONDecodeError, RuntimeError):
                    continue

            raise RuntimeError(f"无法从 Trae CLI 输出中提取有效内容: {output[:500]}")

        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Trae CLI 执行超时 ({self.config.timeout}s)")
        except Exception as e:
            logger.error(f"Trae CLI 执行出错: {e}")
            raise

    def _extract_content(self, data: Dict[str, Any]) -> str:
        """从 Trae CLI 的 JSON 输出中提取内容"""
        if "message" in data and isinstance(data["message"], dict):
            content = data["message"].get("content", "")
            if not content:
                error_hint = next(
                    (s["error"] for s in data.get("agent_states", []) if isinstance(s, dict) and s.get("error")), ""
                )
                msg = "模型返回空响应（message.content 为空）"
                if error_hint:
                    msg += f": {error_hint}"
                raise RuntimeError(msg)
            for prefix in ["```json", "```"]:
                if content.startswith(prefix):
                    content = content[len(prefix) :]  # noqa: E203
            if content.endswith("```"):
                content = content[:-3]
            return content.strip()

        for key in ("response", "content", "text"):
            if key in data and data[key]:
                return data[key]

        raise RuntimeError(f"Trae CLI JSON 输出中未找到已知内容字段: {list(data.keys())}")
