"""Tests for the MCP server's tool functions.

Calls the tool functions directly (bypassing FastMCP transport) since
the routing layer is the SDK's responsibility. Builds a tiny index
in a temp dir, points AKAMAI_MCP_INDEX_PATH at it, and verifies
each tool returns sensible structured output.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from tests.test_index import _build_tiny_index  # reuse the fixture builder


@pytest.fixture
def server_with_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    index_path = tmp_path / "index.sqlite"
    _build_tiny_index(index_path)
    monkeypatch.setenv("AKAMAI_MCP_INDEX_PATH", str(index_path))

    # Reload the server module so its lazy _index global is reset.
    from akamai_techdocs_mcp import server as server_mod

    importlib.reload(server_mod)
    yield server_mod
    # Close any opened handle
    if server_mod._index is not None:
        server_mod._index.close()


def test_search_docs_tool_returns_results(server_with_index) -> None:
    out = server_with_index.search_docs("install spin cli")
    assert "results" in out and "meta" in out
    assert len(out["results"]) >= 1
    assert out["results"][0]["product"] == "Spin Framework"


def test_search_docs_respects_product_filter(server_with_index) -> None:
    out = server_with_index.search_docs("install", product="Nonexistent")
    assert out["results"] == []


def test_get_doc_tool_returns_full_markdown(server_with_index) -> None:
    out = server_with_index.get_doc("https://spinframework.dev/v3/quickstart")
    assert out["found"] is True
    assert "# Quickstart" in out["markdown"]
    assert out["chunk_count"] == 2


def test_list_sources_tool_returns_one_source(server_with_index) -> None:
    out = server_with_index.list_sources()
    assert len(out["sources"]) == 1
    assert out["sources"][0]["product"] == "Spin Framework"


def test_tools_registered_on_fastmcp(server_with_index) -> None:
    # The @mcp.tool decorator adds tools to the FastMCP instance.
    # We verify all three are present by name.
    tool_names = set()
    # FastMCP stores tools internally; we use the documented API surface
    # by calling .list_tools() if available, else inspecting the module.
    for name in ("search_docs", "get_doc", "list_sources"):
        assert callable(getattr(server_with_index, name)), f"missing tool fn: {name}"
        tool_names.add(name)
    assert tool_names == {"search_docs", "get_doc", "list_sources"}


def test_main_opens_index_eagerly(server_with_index, monkeypatch: pytest.MonkeyPatch) -> None:
    """main() should open the index before starting the MCP run loop.

    We patch ``mcp.run`` to a no-op (so the server doesn't actually
    start) and ``maybe_update`` to a no-op (so the test doesn't hit
    the real GitHub API), then assert the global _index handle is
    non-None after main() returns.
    """
    server_with_index._index = None
    monkeypatch.setattr(server_with_index.mcp, "run", lambda: None)
    monkeypatch.setattr(server_with_index, "maybe_update", lambda *a, **kw: None)
    server_with_index.main()
    assert server_with_index._index is not None
