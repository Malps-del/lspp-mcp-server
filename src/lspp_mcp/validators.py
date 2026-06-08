"""Validation and safety helpers."""

from __future__ import annotations

import re
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any


class LsppValidationError(ValueError):
    """Raised when user-controlled input fails a safety check."""


_WINDOW_SIZE_RE = re.compile(r"^[1-9][0-9]{1,4}x[1-9][0-9]{1,4}$")
_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:+\-/*(), ]+$")
_PART_SPEC_RE = re.compile(r"^[0-9]+(?::[0-9]+)?(?:,[0-9]+(?::[0-9]+)?)*$")
_FORBIDDEN_CFILE_RE = re.compile(r"^\s*(system|shell|exec|cmd)\b", re.IGNORECASE)


def resolve_user_path(path: str | Path, workspace_root: Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = workspace_root / candidate
    return candidate.resolve(strict=False)


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def ensure_within_allowed_roots(
    path: str | Path,
    workspace_root: Path,
    allowed_roots: Sequence[Path],
) -> Path:
    resolved = resolve_user_path(path, workspace_root)
    roots = [root.expanduser().resolve(strict=False) for root in allowed_roots]
    if not roots:
        roots = [workspace_root.expanduser().resolve(strict=False)]
    if not any(is_relative_to(resolved, root) for root in roots):
        roots_text = ", ".join(str(root) for root in roots)
        raise LsppValidationError(
            f"Path is outside allowed roots: {resolved}. Allowed roots: {roots_text}"
        )
    return resolved


def ensure_input_file(
    path: str | Path,
    workspace_root: Path,
    allowed_roots: Sequence[Path],
    label: str = "input file",
) -> Path:
    resolved = ensure_within_allowed_roots(path, workspace_root, allowed_roots)
    if not resolved.exists() or not resolved.is_file():
        raise LsppValidationError(f"{label} does not exist: {resolved}")
    return resolved


def ensure_input_directory(
    path: str | Path,
    workspace_root: Path,
    allowed_roots: Sequence[Path],
    label: str = "input directory",
) -> Path:
    resolved = ensure_within_allowed_roots(path, workspace_root, allowed_roots)
    if not resolved.exists() or not resolved.is_dir():
        raise LsppValidationError(f"{label} does not exist: {resolved}")
    return resolved


def ensure_output_path(
    path: str | Path,
    workspace_root: Path,
    allowed_roots: Sequence[Path],
    overwrite: bool = False,
) -> Path:
    resolved = ensure_within_allowed_roots(path, workspace_root, allowed_roots)
    if resolved.exists() and not overwrite:
        raise LsppValidationError(
            f"Output already exists and overwrite=false: {resolved}"
        )
    ensure_within_allowed_roots(resolved.parent, workspace_root, allowed_roots)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def validate_lsprepost_installation(
    lsprepost_exe: str | Path,
    workspace_root: str | Path,
) -> dict[str, Any]:
    exe = Path(lsprepost_exe).expanduser().resolve(strict=False)
    workspace = Path(workspace_root).expanduser().resolve(strict=False)
    if not exe.exists() or not exe.is_file():
        return {
            "ok": False,
            "message": f"LS-PrePost executable not found: {exe}",
            "detected_exe": str(exe),
            "workspace_root": str(workspace),
        }
    if not workspace.exists() or not workspace.is_dir():
        return {
            "ok": False,
            "message": f"Workspace root not found: {workspace}",
            "detected_exe": str(exe),
            "workspace_root": str(workspace),
        }
    try:
        with tempfile.NamedTemporaryFile(
            prefix="lspp_mcp_validate_",
            suffix=".tmp",
            dir=workspace,
            delete=True,
        ) as handle:
            handle.write(b"ok")
    except OSError as exc:
        return {
            "ok": False,
            "message": f"Workspace is not writable: {exc}",
            "detected_exe": str(exe),
            "workspace_root": str(workspace),
        }
    return {
        "ok": True,
        "message": "LS-PrePost executable and workspace are valid.",
        "detected_exe": str(exe),
        "workspace_root": str(workspace),
    }


def validate_cfile_content(content: str) -> None:
    for line_number, line in enumerate(content.splitlines(), start=1):
        if _FORBIDDEN_CFILE_RE.search(line):
            raise LsppValidationError(
                f"Forbidden command in generated cfile at line {line_number}: {line}"
            )


def validate_window_size(window_size: str) -> str:
    if not _WINDOW_SIZE_RE.match(window_size):
        raise LsppValidationError(
            "window_size must use WIDTHxHEIGHT, for example 1600x1200"
        )
    return window_size


def safe_cfile_string(value: str | Path) -> str:
    text = str(value)
    if any(char in text for char in ['"', "\r", "\n"]):
        raise LsppValidationError("cfile string values cannot contain quotes/newlines")
    return text


def safe_token(value: str | int, label: str = "token") -> str:
    text = str(value).strip()
    if not text or any(char in text for char in ['"', "\r", "\n"]):
        raise LsppValidationError(f"{label} cannot be empty or contain quotes/newlines")
    if not _SAFE_TOKEN_RE.match(text):
        raise LsppValidationError(f"{label} contains unsupported characters: {text}")
    return text


def positive_int(value: int | str, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise LsppValidationError(f"{label} must be an integer") from exc
    if number < 0:
        raise LsppValidationError(f"{label} must be non-negative")
    return number


def format_part_ids(part_ids: Sequence[int] | str | int | None) -> str:
    if part_ids is None:
        return ""
    if isinstance(part_ids, int):
        if part_ids < 0:
            raise LsppValidationError("part_ids cannot contain negative ids")
        return str(part_ids)
    if isinstance(part_ids, str):
        text = part_ids.strip()
        if not _PART_SPEC_RE.match(text):
            raise LsppValidationError(
                "part_ids string must look like 3, 1,2,3, or 1:10"
            )
        return text
    formatted: list[str] = []
    for part_id in part_ids:
        formatted.append(str(positive_int(part_id, "part_id")))
    return ",".join(formatted)


def require_variable_code(
    variable_maps: dict[str, Any],
    category: str,
    variable: str | None,
    variable_code: int | None = None,
) -> int:
    if variable_code is not None:
        return positive_int(variable_code, "variable_code")
    if not variable:
        raise LsppValidationError("Either variable or variable_code is required")
    category_map = variable_maps.get(category, {})
    if variable not in category_map:
        raise LsppValidationError(
            f"Unsupported variable '{variable}' for category '{category}'"
        )
    return positive_int(category_map[variable], f"{category}.{variable}")


def output_file_check(path: Path) -> dict[str, Any]:
    exists = path.exists()
    size = path.stat().st_size if exists and path.is_file() else 0
    return {
        "path": str(path),
        "exists": exists,
        "size_bytes": size,
        "nonempty": exists and size > 0,
    }
