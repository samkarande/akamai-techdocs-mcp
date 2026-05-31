"""HTML → markdown conversion for crawled doc pages.

Doc sites differ in DOM structure but share a common pattern: the
useful content lives inside a `<main>` or `<article>` container, with
navigation, sidebars, and footers wrapped in other tags. This module
strips the noise, extracts the main content, and converts it to
markdown — preserving heading hierarchy, code blocks, links, and lists
so the downstream chunker can split by heading.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify

# Tags whose content we never want — scripts, styles, page chrome.
_NOISE_TAGS = (
    "script", "style", "nav", "header", "footer", "aside",
    "noscript", "iframe", "form", "svg",
)

# Selectors tried in order to locate the main content. First non-empty
# match wins. Final fallback is <body>.
_CONTENT_SELECTORS = (
    "main",
    "article",
    "[role=main]",
    ".markdown-body",        # GitHub, ReadMe-style sites
    ".content",
    "#content",
    "#main-content",
)


@dataclass(frozen=True, slots=True)
class ParsedPage:
    title: str
    markdown: str
    char_count: int


def parse_html(html: str) -> ParsedPage:
    """Parse an HTML document and return its title + main-content markdown."""
    soup = BeautifulSoup(html, "html.parser")

    title = _extract_title(soup)

    for tag_name in _NOISE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    content = _find_main_content(soup)
    if content is None:
        return ParsedPage(title=title, markdown="", char_count=0)

    md = markdownify(
        str(content),
        heading_style="ATX",     # # H1, ## H2 — easier to chunk on
        bullets="-",
        code_language="",        # leave fences blank when language is unknown
        strip=["a"],             # drop link wrappers but keep their text
    )
    md = _clean_markdown(md)
    return ParsedPage(title=title, markdown=md, char_count=len(md))


def _extract_title(soup: BeautifulSoup) -> str:
    # Prefer <h1> inside main content; fall back to <title>.
    h1 = soup.find("h1")
    if isinstance(h1, Tag):
        text = h1.get_text(strip=True)
        if text:
            return text
    title_tag = soup.find("title")
    if isinstance(title_tag, Tag):
        return title_tag.get_text(strip=True)
    return ""


def _find_main_content(soup: BeautifulSoup) -> Tag | None:
    for selector in _CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if isinstance(node, Tag) and node.get_text(strip=True):
            return node
    body = soup.body
    return body if isinstance(body, Tag) else None


# Collapse runs of >2 blank lines and trim trailing whitespace per line.
_BLANK_RUN = re.compile(r"\n{3,}")
_TRAILING_WS = re.compile(r"[ \t]+\n")


def _clean_markdown(md: str) -> str:
    md = _TRAILING_WS.sub("\n", md)
    md = _BLANK_RUN.sub("\n\n", md)
    stripped = md.strip()
    return stripped + "\n" if stripped else ""
