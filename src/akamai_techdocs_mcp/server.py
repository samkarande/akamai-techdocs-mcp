"""The akamai-techdocs MCP server.

Exposes three tools backed by a single SQLite index. The index is
opened lazily on first tool call so import-time failures (missing
index, schema mismatch) surface as actionable errors rather than
silent import errors when the host enumerates the server's tools.

Tools (descriptions here become what MCP clients show the model):

- search_docs: full-text search across indexed documentation
- get_doc:     return the full markdown of one doc page by URL
- list_sources: enumerate indexed products + their crawl freshness
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from akamai_techdocs_mcp.index import IndexHandle

mcp: FastMCP = FastMCP("akamai-techdocs")

_index: IndexHandle | None = None


def get_index() -> IndexHandle:
    """Return the process-wide IndexHandle, opening it on first use."""
    global _index
    if _index is None:
        _index = IndexHandle.open()
    return _index


@mcp.tool()
def search_docs(
    query: str, product: str | None = None, limit: int = 10
) -> dict[str, Any]:
    """Search Akamai Functions / Spin Framework documentation.

    Args:
        query: Free-form search query. Natural language works well
            ("how do I trigger a function on http", "rust component
            template"). Identifiers split on punctuation, so "spin"
            will match "spin.toml" and "trigger" will match
            "http-trigger".
        product: Optional product name to filter results
            (e.g. "Spin Framework", "Akamai Functions"). Use
            list_sources() to see exact product names available.
        limit: Maximum results to return (1-50; default 10).

    Returns a dict with `results` (list of {url, doc_title, heading_path,
    snippet, source_id, product, version, rank}) and `meta` (index
    schema/manifest info). Each result's URL is citable.
    """
    return get_index().search(query, product=product, limit=limit)


@mcp.tool()
def get_doc(url: str) -> dict[str, Any]:
    """Fetch the full markdown of one doc page by its URL.

    Use this after search_docs surfaces a relevant URL and the model
    needs the complete content of that page (not just the snippet).
    Returns the reassembled markdown from all chunks of that URL,
    plus metadata (product, doc_last_modified, crawled_at). If the
    URL is not in the current index, returns ``found: false``.
    """
    return get_index().get_doc(url)


@mcp.tool()
def list_sources() -> dict[str, Any]:
    """List the products/doc-sets this MCP currently has indexed.

    Returns per-source: id, product, version, domain, url_count,
    tombstoned_count, last_crawled_at, plus the index meta. Useful
    for the model to know exact `product` filter values it can pass
    to search_docs, and for users debugging "why doesn't the MCP
    know about X" questions.
    """
    return get_index().list_sources()


def main() -> None:
    # Open the index eagerly so the server fails fast with a clear
    # error rather than starting up and erroring on the first tool call.
    get_index()
    mcp.run()


if __name__ == "__main__":
    main()
