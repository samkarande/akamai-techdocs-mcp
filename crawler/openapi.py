"""OpenAPI / Swagger JSON → markdown conversion for crawled API specs.

Some sources in the manifest are raw OpenAPI documents (e.g. the Linode
API spec) rather than HTML pages. ``parse_html`` cannot extract anything
useful from JSON, so this module renders a spec into heading-structured
markdown that the existing chunker splits into one chunk per operation.

The markdown shape is chosen for the chunker (which splits on H1..H3):

    # {API title} (v{version})        <- intro chunk: description + servers
    ## {tag}                          <- one section per tag
    ### {METHOD} {path} — {summary}   <- one chunk per operation

Each operation chunk carries its operationId, parameters, request-body
properties, and response codes so search hits are self-describing.

``parse_openapi`` returns ``None`` when the body is not a JSON OpenAPI /
Swagger document, letting the caller fall back to HTML parsing.
"""

from __future__ import annotations

import json
import re
from typing import Any

from crawler.parser import ParsedPage

# HTTP methods that count as operations in an OpenAPI path item.
_METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")

# Cap per-operation description length so individual chunks stay compact.
_MAX_DESC_CHARS = 1500

# Bound $ref resolution depth so cyclic component schemas can't loop forever.
_MAX_REF_DEPTH = 4

# Lines beginning with markdown headings inside descriptions would create
# spurious chunk boundaries; this strips the leading '#'s to plain text.
_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+")

# ReadMe-hosted specs embed magic tokens like "<<LB>>" (line break) and
# other "<<GLOSSARY>>" widgets in descriptions; strip them as noise.
_README_TOKEN = re.compile(r"<<[A-Za-z0-9_ ]{1,20}>>")

# Collapse runs of 3+ newlines left after token/heading stripping.
_BLANK_RUN = re.compile(r"\n{3,}")


def parse_openapi(body: str) -> ParsedPage | None:
    """Render an OpenAPI/Swagger JSON document to markdown.

    Returns ``None`` if ``body`` is not JSON or lacks the ``openapi`` /
    ``swagger`` marker key, so callers can fall back to ``parse_html``.
    """
    try:
        spec = json.loads(body)
    except (ValueError, TypeError):
        return None
    if not isinstance(spec, dict):
        return None
    if "openapi" not in spec and "swagger" not in spec:
        return None

    info = spec.get("info") or {}
    title = str(info.get("title") or "API Reference").strip()
    version = str(info.get("version") or "").strip()
    heading = f"{title} (v{version})" if version else title

    # No H1 for the title: chunk_markdown already receives it as page_title
    # (level 0). Emitting it again here would double it in every heading
    # path. Intro content sits before the first ## as the page-title chunk.
    lines: list[str] = []

    description = _sanitize(info.get("description"))
    if description:
        lines.append(description)
        lines.append("")

    servers = _render_servers(spec)
    if servers:
        lines.extend(servers)
        lines.append("")

    components = spec.get("components") if isinstance(spec, dict) else None
    schemas = (components or {}).get("schemas", {}) if isinstance(components, dict) else {}

    for tag, operations in _operations_by_tag(spec):
        lines.append(f"## {tag}")
        lines.append("")
        for method, path, op in operations:
            lines.extend(_render_operation(method, path, op, spec, schemas))
            lines.append("")

    markdown = "\n".join(lines).strip() + "\n"
    return ParsedPage(title=heading, markdown=markdown, char_count=len(markdown))


def _render_servers(spec: dict[str, Any]) -> list[str]:
    servers = spec.get("servers")
    out: list[str] = []
    if isinstance(servers, list):
        urls = [s.get("url") for s in servers if isinstance(s, dict) and s.get("url")]
        if urls:
            out.append("**Servers:** " + ", ".join(str(u) for u in urls))
    # Swagger 2.0 host/basePath fallback.
    elif spec.get("host"):
        base = f"{spec['host']}{spec.get('basePath', '')}"
        out.append(f"**Server:** {base}")
    return out


def _operations_by_tag(
    spec: dict[str, Any],
) -> list[tuple[str, list[tuple[str, str, dict[str, Any]]]]]:
    """Group operations by their first tag, preserving spec order."""
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return []

    grouped: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    order: list[str] = []
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method in _METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            tags = op.get("tags")
            tag = str(tags[0]) if isinstance(tags, list) and tags else "Operations"
            if tag not in grouped:
                grouped[tag] = []
                order.append(tag)
            grouped[tag].append((method.upper(), str(path), op))
    return [(tag, grouped[tag]) for tag in order]


def _render_operation(
    method: str,
    path: str,
    op: dict[str, Any],
    spec: dict[str, Any],
    schemas: dict[str, Any],
) -> list[str]:
    summary = str(op.get("summary") or "").strip()
    title = f"### {method} {path}"
    if summary:
        title += f" — {summary}"
    out = [title, ""]

    op_id = op.get("operationId")
    if op_id:
        out.append(f"**operationId:** `{op_id}`")
        out.append("")

    description = _sanitize(op.get("description"))
    if description:
        out.append(description)
        out.append("")

    params = _render_parameters(op.get("parameters"))
    if params:
        out.append("**Parameters:**")
        out.extend(params)
        out.append("")

    body_props = _render_request_body(op.get("requestBody"), spec, schemas)
    if body_props:
        out.append("**Request body:**")
        out.extend(body_props)
        out.append("")

    responses = _render_responses(op.get("responses"))
    if responses:
        out.append("**Responses:**")
        out.extend(responses)
        out.append("")

    return out


def _render_parameters(parameters: Any) -> list[str]:
    if not isinstance(parameters, list):
        return []
    out: list[str] = []
    for p in parameters:
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        if not name:
            continue
        location = p.get("in", "")
        required = " (required)" if p.get("required") else ""
        type_ = _schema_type(p.get("schema")) or p.get("type") or ""
        type_str = f" `{type_}`" if type_ else ""
        desc = _short(_sanitize(p.get("description")))
        desc_str = f" — {desc}" if desc else ""
        out.append(f"- `{name}` ({location}){type_str}{required}{desc_str}")
    return out


def _render_request_body(
    request_body: Any, spec: dict[str, Any], schemas: dict[str, Any]
) -> list[str]:
    if not isinstance(request_body, dict):
        return []
    content = request_body.get("content")
    if not isinstance(content, dict):
        return []
    media = content.get("application/json") or next(iter(content.values()), None)
    if not isinstance(media, dict):
        return []
    schema = _resolve(media.get("schema"), spec)
    props, required = _schema_properties(schema, spec, depth=0)
    out: list[str] = []
    for name, prop in props.items():
        type_ = _schema_type(prop)
        type_str = f" `{type_}`" if type_ else ""
        req = " (required)" if name in required else ""
        desc = _short(_sanitize(prop.get("description") if isinstance(prop, dict) else None))
        desc_str = f" — {desc}" if desc else ""
        out.append(f"- `{name}`{type_str}{req}{desc_str}")
    return out


def _render_responses(responses: Any) -> list[str]:
    if not isinstance(responses, dict):
        return []
    out: list[str] = []
    for code, resp in responses.items():
        desc = ""
        if isinstance(resp, dict):
            desc = _short(_sanitize(resp.get("description")))
        out.append(f"- `{code}`" + (f" — {desc}" if desc else ""))
    return out


def _schema_properties(
    schema: Any, spec: dict[str, Any], depth: int
) -> tuple[dict[str, Any], set[str]]:
    """Best-effort flatten of a schema's top-level properties + required set.

    Handles direct ``properties`` and merges ``allOf`` members. Bounded by
    ``_MAX_REF_DEPTH`` to survive cyclic component references.
    """
    if not isinstance(schema, dict) or depth > _MAX_REF_DEPTH:
        return {}, set()

    props: dict[str, Any] = {}
    required: set[str] = set()

    direct = schema.get("properties")
    if isinstance(direct, dict):
        props.update(direct)
    req = schema.get("required")
    if isinstance(req, list):
        required.update(str(r) for r in req)

    for combinator in ("allOf", "oneOf", "anyOf"):
        members = schema.get(combinator)
        if isinstance(members, list):
            for member in members:
                resolved = _resolve(member, spec)
                sub_props, sub_req = _schema_properties(resolved, spec, depth + 1)
                props.update(sub_props)
                required.update(sub_req)

    return props, required


def _resolve(node: Any, spec: dict[str, Any], depth: int = 0) -> Any:
    """Resolve a local ``$ref`` (``#/...``) one hop, bounded by depth."""
    if not isinstance(node, dict) or depth > _MAX_REF_DEPTH:
        return node
    ref = node.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return node
    target: Any = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(target, dict) and part in target:
            target = target[part]
        else:
            return node
    return _resolve(target, spec, depth + 1)


def _schema_type(schema: Any) -> str:
    if not isinstance(schema, dict):
        return ""
    t = schema.get("type")
    if t == "array":
        items = schema.get("items")
        inner = _schema_type(items) if isinstance(items, dict) else ""
        return f"array<{inner}>" if inner else "array"
    if isinstance(t, str):
        return t
    if "$ref" in schema:
        return str(schema["$ref"]).rsplit("/", 1)[-1]
    return ""


def _sanitize(text: Any) -> str:
    """Normalize a description: strip markdown heading markers, trim length."""
    if not isinstance(text, str):
        return ""
    text = _README_TOKEN.sub("", text)
    cleaned = "\n".join(_MD_HEADING.sub("", line) for line in text.splitlines())
    cleaned = _BLANK_RUN.sub("\n\n", cleaned).strip()
    if len(cleaned) > _MAX_DESC_CHARS:
        cleaned = cleaned[:_MAX_DESC_CHARS].rstrip() + "…"
    return cleaned


def _short(text: str, limit: int = 200) -> str:
    """Collapse to a single line and truncate, for inline list items."""
    one_line = " ".join(text.split())
    return one_line[:limit].rstrip() + "…" if len(one_line) > limit else one_line
