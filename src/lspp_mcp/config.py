"""Configuration loading for lspp-mcp-server."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .variable_maps import deep_update, default_variable_maps


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index]
    return line


def _parse_scalar(raw: str) -> Any:
    text = raw.strip()
    if text == "":
        return ""
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        return text[1:-1]
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def _simple_yaml_load(text: str) -> dict[str, Any]:
    """Parse the simple YAML subset used by config.example.yaml.

    PyYAML is used when installed. This fallback supports indented mappings and
    scalar lists, which is enough to keep unit tests dependency-free.
    """

    lines: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        no_comment = _strip_comment(raw_line).rstrip()
        if not no_comment.strip():
            continue
        indent = len(no_comment) - len(no_comment.lstrip(" "))
        lines.append((indent, no_comment.strip()))

    def parse_block(start: int, indent: int) -> tuple[Any, int]:
        if start >= len(lines):
            return {}, start
        first_indent, first_content = lines[start]
        if first_indent != indent:
            return {}, start
        if first_content.startswith("- "):
            values: list[Any] = []
            index = start
            while index < len(lines):
                current_indent, content = lines[index]
                if current_indent < indent:
                    break
                if current_indent != indent or not content.startswith("- "):
                    break
                item = content[2:].strip()
                values.append(_parse_scalar(item))
                index += 1
            return values, index

        values: dict[str, Any] = {}
        index = start
        while index < len(lines):
            current_indent, content = lines[index]
            if current_indent < indent:
                break
            if current_indent > indent:
                raise ValueError(f"Unexpected indentation near: {content}")
            if ":" not in content:
                raise ValueError(f"Expected key/value YAML line: {content}")
            key, raw_value = content.split(":", 1)
            key = key.strip()
            raw_value = raw_value.strip()
            index += 1
            if raw_value:
                values[key] = _parse_scalar(raw_value)
                continue
            if index < len(lines) and lines[index][0] > current_indent:
                child, index = parse_block(index, lines[index][0])
                values[key] = child
            else:
                values[key] = {}
        return values, index

    parsed, final_index = parse_block(0, lines[0][0]) if lines else ({}, 0)
    if final_index != len(lines):
        raise ValueError("Could not parse all YAML lines")
    if not isinstance(parsed, dict):
        raise ValueError("Top-level YAML document must be a mapping")
    return parsed


def load_yaml_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        return _simple_yaml_load(text)
    loaded = yaml.safe_load(text) or {}
    if not isinstance(loaded, dict):
        raise ValueError("Configuration YAML must be a mapping")
    return loaded


@dataclass(frozen=True)
class LsppConfig:
    lsprepost_exe: str = "lsprepost"
    workspace_root: Path = field(default_factory=Path.cwd)
    allowed_roots: tuple[Path, ...] = field(default_factory=tuple)
    timeout_seconds: int = 300
    open_d3plot_command: str = "openc"
    case_generator_python: str = ""
    case_generator_src: Path | None = None
    variable_maps: dict[str, Any] = field(default_factory=default_variable_maps)

    def resolved_allowed_roots(self) -> tuple[Path, ...]:
        roots = self.allowed_roots or (self.workspace_root,)
        return tuple(root.expanduser().resolve(strict=False) for root in roots)


def _resolve_config_path(value: str | os.PathLike[str], base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve(strict=False)


def load_config(path: str | os.PathLike[str] | None = None) -> LsppConfig:
    """Load config.yaml or return a safe cwd-based default config."""

    if path is None:
        env_path = os.environ.get("LSPP_MCP_CONFIG")
        if env_path:
            path = env_path
        elif Path("config.yaml").exists():
            path = "config.yaml"

    if path is None:
        workspace_root = Path.cwd().resolve(strict=False)
        return LsppConfig(workspace_root=workspace_root, allowed_roots=(workspace_root,))

    config_path = Path(path).expanduser().resolve(strict=False)
    data = load_yaml_file(config_path)
    base_dir = config_path.parent
    variable_maps = default_variable_maps()
    if isinstance(data.get("variables"), dict):
        deep_update(variable_maps, data["variables"])

    workspace_root = _resolve_config_path(
        data.get("workspace_root", "."), base_dir
    )
    allowed_roots_raw = data.get("allowed_roots") or [str(workspace_root)]
    if not isinstance(allowed_roots_raw, list):
        raise ValueError("allowed_roots must be a YAML list")
    allowed_roots = tuple(
        _resolve_config_path(item, base_dir) for item in allowed_roots_raw
    )

    return LsppConfig(
        lsprepost_exe=str(data.get("lsprepost_exe", "lsprepost")),
        workspace_root=workspace_root,
        allowed_roots=allowed_roots,
        timeout_seconds=int(data.get("timeout_seconds", 300)),
        open_d3plot_command=str(data.get("open_d3plot_command", "openc")),
        case_generator_python=str(data.get("case_generator_python", "")),
        case_generator_src=_resolve_config_path(data["case_generator_src"], base_dir)
        if data.get("case_generator_src")
        else None,
        variable_maps=variable_maps,
    )
