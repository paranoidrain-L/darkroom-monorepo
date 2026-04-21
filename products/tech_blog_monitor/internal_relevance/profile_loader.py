"""Stack profile YAML loader."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from products.tech_blog_monitor.internal_relevance.models import StackProfile, StackSignal

_DEFAULT_SOURCE_PRIORITIES = {
    "github_releases": 1.5,
    "changelog": 1.2,
    "rss": 0.6,
}


def _normalize_name(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _build_signal_id(prefix: str, name: str) -> str:
    digest = hashlib.sha1(f"{prefix}:{name}".encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:12]}"


def _clean_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def load_stack_profile(path: str) -> StackProfile:
    if not path:
        return StackProfile(source_priorities=dict(_DEFAULT_SOURCE_PRIORITIES))

    profile_path = Path(path)
    if not profile_path.exists():
        return StackProfile(
            source_priorities=dict(_DEFAULT_SOURCE_PRIORITIES),
            warnings=[f"stack profile 不存在: {path}"],
            loaded_from=path,
        )

    try:
        data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return StackProfile(
            source_priorities=dict(_DEFAULT_SOURCE_PRIORITIES),
            warnings=[f"stack profile YAML 解析失败 ({path}): {exc}"],
            loaded_from=path,
        )

    if not isinstance(data, dict):
        return StackProfile(
            source_priorities=dict(_DEFAULT_SOURCE_PRIORITIES),
            warnings=[f"stack profile 顶层必须是对象: {path}"],
            loaded_from=path,
        )

    signals: list[StackSignal] = []
    warnings: list[str] = []

    for item in data.get("dependencies", []):
        if not isinstance(item, dict):
            warnings.append("dependencies 中存在非法条目，已跳过")
            continue
        raw_name = item.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            warnings.append("dependencies 中存在缺少 name 的条目，已跳过")
            continue
        name = _normalize_name(raw_name)
        aliases = {name, raw_name.strip()}
        aliases.update(_clean_string_list(item.get("aliases")))
        signals.append(
            StackSignal(
                signal_id=_build_signal_id("dep", name),
                name=name,
                kind="dependency",
                aliases=sorted({_normalize_name(alias) for alias in aliases if alias}),
                weight=float(item.get("weight", 1.0) or 1.0),
                source="profile",
                source_detail=str(profile_path),
            )
        )

    for item in data.get("topics", []):
        if not isinstance(item, dict):
            warnings.append("topics 中存在非法条目，已跳过")
            continue
        raw_name = item.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            warnings.append("topics 中存在缺少 name 的条目，已跳过")
            continue
        keywords = _clean_string_list(item.get("keywords"))
        if not keywords:
            warnings.append(f"topic={raw_name!r} 未提供 keywords，已跳过")
            continue
        name = raw_name.strip().lower()
        signals.append(
            StackSignal(
                signal_id=_build_signal_id("topic", name),
                name=name,
                kind="topic",
                keywords=sorted({keyword.strip().lower() for keyword in keywords}),
                weight=float(item.get("weight", 1.0) or 1.0),
                source="profile",
                source_detail=str(profile_path),
            )
        )

    priorities = dict(_DEFAULT_SOURCE_PRIORITIES)
    raw_priorities = data.get("source_priorities", {})
    if isinstance(raw_priorities, dict):
        for key, value in raw_priorities.items():
            if isinstance(key, str):
                try:
                    priorities[key.strip().lower()] = float(value)
                except (TypeError, ValueError):
                    warnings.append(f"source_priorities[{key!r}] 不是合法数字，已跳过")

    return StackProfile(
        signals=signals,
        source_priorities=priorities,
        profile_name=str(data.get("name") or profile_path.stem),
        loaded_from=str(profile_path),
        warnings=warnings,
    )
