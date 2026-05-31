"""Split a parsed page's markdown into heading-scoped chunks.

The MCP server's search_docs returns chunks (snippets + URLs), so the
chunking strategy directly shapes the model's information-density per
tool call. We split on H1/H2/H3 boundaries by default; code fences are
respected so that lines starting with `#` inside a code block are not
mistaken for headings.

Each chunk carries:
- ordinal: 0-based position within the page
- heading_path: breadcrumb from the doc title down to this section
                (e.g. "Quickstart > Step 1: Install")
- content_md: the chunk body (including its own heading line)
- char_count: len(content_md)
- code_block_count: number of fenced code blocks in the chunk

Leading content before the first heading is emitted as a chunk under
the page title alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Match ATX headings: "#", "##", ..., optionally followed by text.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
# Match the opening/closing of a fenced code block.
_FENCE_RE = re.compile(r"^\s{0,3}(```|~~~)")

DEFAULT_MAX_HEADING_LEVEL = 3


@dataclass(frozen=True, slots=True)
class Chunk:
    ordinal: int
    heading_path: str
    content_md: str
    char_count: int
    code_block_count: int


def chunk_markdown(
    markdown: str,
    *,
    page_title: str = "",
    max_heading_level: int = DEFAULT_MAX_HEADING_LEVEL,
) -> list[Chunk]:
    """Split markdown into chunks at H1..H{max_heading_level} boundaries."""
    if not markdown.strip():
        return []

    heading_stack: list[tuple[int, str]] = []
    if page_title:
        heading_stack.append((0, page_title))

    current_lines: list[str] = []
    chunks: list[Chunk] = []
    in_code_fence = False
    ordinal = 0

    def flush() -> None:
        nonlocal ordinal, current_lines
        if not current_lines:
            return
        body = "\n".join(current_lines).strip()
        if not body:
            current_lines = []
            return
        path = " > ".join(text for _, text in heading_stack) or "Untitled"
        content_md = body + "\n"
        chunks.append(
            Chunk(
                ordinal=ordinal,
                heading_path=path,
                content_md=content_md,
                char_count=len(content_md),
                code_block_count=_count_code_blocks(content_md),
            )
        )
        ordinal += 1
        current_lines = []

    for line in markdown.splitlines():
        if _FENCE_RE.match(line):
            in_code_fence = not in_code_fence
            current_lines.append(line)
            continue

        if in_code_fence:
            current_lines.append(line)
            continue

        m = _HEADING_RE.match(line)
        if m and len(m.group(1)) <= max_heading_level:
            level = len(m.group(1))
            text = m.group(2).strip()
            flush()
            # Pop stack to ancestors of this heading. Index 0 is the
            # page title (level 0); never pop it.
            while len(heading_stack) > 1 and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, text))
            current_lines.append(line)
            continue

        current_lines.append(line)

    flush()
    return chunks


def _count_code_blocks(md: str) -> int:
    """Count opening fences (each opening fence = one code block)."""
    fences = 0
    in_fence = False
    for line in md.splitlines():
        if _FENCE_RE.match(line):
            if not in_fence:
                fences += 1
            in_fence = not in_fence
    return fences
