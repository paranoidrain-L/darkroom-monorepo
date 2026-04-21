"""Manifest scanners for repo-derived stack signals."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from products.tech_blog_monitor.internal_relevance.models import ManifestScanResult, StackSignal

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

_SUPPORTED_FILENAMES = {"pyproject.toml", "package.json"}
_REQUIREMENTS_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)")
_SKIP_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"}


def _normalize_package_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _build_dependency_signal(name: str, *, source_detail: str) -> StackSignal:
    normalized = _normalize_package_name(name)
    aliases = {
        normalized,
        normalized.replace("-", " "),
        normalized.replace("-", ""),
    }
    return StackSignal(
        signal_id=f"manifest_dep_{normalized}",
        name=normalized,
        kind="dependency",
        aliases=sorted(alias for alias in aliases if alias),
        weight=1.0,
        source="manifest",
        source_detail=source_detail,
    )


def _parse_requirements_file(path: Path) -> set[str]:
    packages: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped or stripped.startswith(("-", "--")):
            continue
        match = _REQUIREMENTS_RE.match(stripped)
        if match is None:
            continue
        packages.add(_normalize_package_name(match.group(1)))
    return packages


def _extract_pep508_name(spec: str) -> str | None:
    candidate = spec.split(";", 1)[0].strip()
    match = _REQUIREMENTS_RE.match(candidate)
    if match is None:
        return None
    return _normalize_package_name(match.group(1))


def _parse_pyproject_file(path: Path) -> set[str]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    packages: set[str] = set()

    project = data.get("project")
    if isinstance(project, dict):
        for item in project.get("dependencies", []) or []:
            if isinstance(item, str) and (name := _extract_pep508_name(item)):
                packages.add(name)
        optional = project.get("optional-dependencies", {}) or {}
        if isinstance(optional, dict):
            for items in optional.values():
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, str) and (name := _extract_pep508_name(item)):
                            packages.add(name)

    tool = data.get("tool")
    if isinstance(tool, dict):
        poetry = tool.get("poetry")
        if isinstance(poetry, dict):
            for section_name in ("dependencies", "group"):
                section = poetry.get(section_name)
                if section_name == "dependencies" and isinstance(section, dict):
                    for key in section.keys():
                        if key != "python":
                            packages.add(_normalize_package_name(str(key)))
                if section_name == "group" and isinstance(section, dict):
                    for group_value in section.values():
                        if not isinstance(group_value, dict):
                            continue
                        dependencies = group_value.get("dependencies")
                        if isinstance(dependencies, dict):
                            for key in dependencies.keys():
                                packages.add(_normalize_package_name(str(key)))
    return packages


def _parse_package_json(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    packages: set[str] = set()
    for section_name in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        section = data.get(section_name)
        if isinstance(section, dict):
            for key in section.keys():
                packages.add(_normalize_package_name(str(key)))
    return packages


def _iter_manifest_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [dirname for dirname in dirnames if dirname not in _SKIP_DIRS]
        current = Path(current_root)
        for filename in filenames:
            if filename.startswith("requirements") and filename.endswith(".txt"):
                paths.append(current / filename)
            elif filename in _SUPPORTED_FILENAMES:
                paths.append(current / filename)
    return sorted(paths)


def scan_repo_roots(repo_roots: list[str]) -> ManifestScanResult:
    signals_by_name: dict[str, StackSignal] = {}
    scanned_files: list[str] = []
    warnings: list[str] = []

    for raw_root in repo_roots:
        if not raw_root.strip():
            continue
        root = Path(raw_root).expanduser()
        if not root.exists():
            warnings.append(f"stack repo root 不存在: {root}")
            continue
        if not root.is_dir():
            warnings.append(f"stack repo root 不是目录: {root}")
            continue

        for path in _iter_manifest_paths(root):
            try:
                if path.name.startswith("requirements") and path.suffix == ".txt":
                    packages = _parse_requirements_file(path)
                elif path.name == "pyproject.toml":
                    packages = _parse_pyproject_file(path)
                elif path.name == "package.json":
                    packages = _parse_package_json(path)
                else:
                    continue
            except Exception as exc:
                warnings.append(f"manifest 解析失败 ({path}): {exc}")
                continue

            scanned_files.append(str(path))
            for package_name in packages:
                signals_by_name.setdefault(
                    package_name,
                    _build_dependency_signal(package_name, source_detail=str(path)),
                )

    return ManifestScanResult(
        signals=sorted(signals_by_name.values(), key=lambda signal: signal.name),
        scanned_files=scanned_files,
        warnings=warnings,
    )
