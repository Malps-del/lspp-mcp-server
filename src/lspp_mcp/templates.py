"""Whitelisted cfile template rendering."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .validators import LsppValidationError, validate_cfile_content


TEMPLATE_DIR = Path(__file__).with_name("cfile_templates")
ALLOWED_TEMPLATES = {
    "export_d3plot_contour.cfile.j2",
    "export_d3plot_contour_frames.cfile.j2",
    "extract_ascii_curve.cfile.j2",
    "extract_binout_curve.cfile.j2",
    "extract_d3plot_node_history.cfile.j2",
}
_PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")


def _fallback_render(template_text: str, context: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise KeyError(f"Missing template value: {key}")
        return str(context[key])

    rendered = _PLACEHOLDER_RE.sub(replace, template_text)
    if "{{" in rendered or "}}" in rendered:
        raise LsppValidationError("Unresolved template placeholders remain")
    return rendered


def render_template(template_name: str, context: dict[str, Any]) -> str:
    if template_name not in ALLOWED_TEMPLATES:
        raise LsppValidationError(f"Template is not whitelisted: {template_name}")
    try:
        import jinja2  # type: ignore
    except ModuleNotFoundError:
        template_text = (TEMPLATE_DIR / template_name).read_text(encoding="utf-8")
        rendered = _fallback_render(template_text, context)
    else:
        environment = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=False,
            undefined=jinja2.StrictUndefined,
            keep_trailing_newline=True,
        )
        rendered = environment.get_template(template_name).render(**context)
    validate_cfile_content(rendered)
    return rendered


def create_run_dir(output_path: Path, tool_name: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    unique = uuid.uuid4().hex[:8]
    safe_tool = re.sub(r"[^A-Za-z0-9_.-]+", "_", tool_name)
    run_dir = output_path.parent / ".lspp_mcp" / f"{stamp}_{safe_tool}_{unique}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def write_generated_cfile(
    run_dir: Path,
    template_name: str,
    context: dict[str, Any],
) -> Path:
    content = render_template(template_name, context)
    cfile_path = run_dir / "generated.cfile"
    cfile_path.write_text(content, encoding="utf-8", newline="\n")
    return cfile_path
