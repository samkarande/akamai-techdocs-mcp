"""Tests for akamai_techdocs_mcp.index.IndexHandle.

Builds a tiny SQLite index in a temp dir using the real schema and
crawler.writer, then exercises the read API the MCP server depends on.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from akamai_techdocs_mcp.index import (
    ENV_INDEX_PATH,
    EXPECTED_SCHEMA_VERSION,
    IndexError,
    IndexHandle,
    resolve_index_path,
)
from crawler.chunker import Chunk
from crawler.fetcher import FetchOutcome, FetchResult
from crawler.manifest import Source
from crawler.parser import ParsedPage
from crawler.writer import IndexWriter


def _build_tiny_index(path: Path) -> None:
    """Write a minimal but realistic index file."""
    source = Source(
        id="spin-framework",
        product="Spin Framework",
        version="v3",
        domain="spinframework.dev",
        description="upstream",
        urls=("https://spinframework.dev/v3/quickstart",),
    )
    fetch_ok = FetchResult(
        url="https://spinframework.dev/v3/quickstart",
        outcome=FetchOutcome.OK,
        http_status=200,
        html="<html/>",
        etag="abc",
        last_modified="Mon, 01 Jan 2026 00:00:00 GMT",
        content_hash="h",
        crawled_at="2026-06-01T00:00:00Z",
    )
    chunks = [
        Chunk(
            ordinal=0,
            heading_path="Quickstart",
            content_md="# Quickstart\nInstall the Spin CLI on your system.\n",
            char_count=51,
            code_block_count=0,
        ),
        Chunk(
            ordinal=1,
            heading_path="Quickstart > Build a Rust component",
            content_md="## Build a Rust component\nUse `cargo` to compile.\n",
            char_count=48,
            code_block_count=0,
        ),
    ]
    fetch_404 = FetchResult(
        url="https://spinframework.dev/v3/removed",
        outcome=FetchOutcome.NOT_FOUND,
        http_status=404,
        html=None,
        etag=None,
        last_modified=None,
        content_hash=None,
        crawled_at="2026-06-01T00:00:00Z",
    )
    with IndexWriter(path) as w:
        w.set_meta("schema_version", str(EXPECTED_SCHEMA_VERSION))
        w.set_meta("manifest_version", "0.1.0")
        w.set_meta("manifest_sha", "deadbeef")
        w.set_meta("built_at", "2026-06-01T00:00:00Z")
        w.set_meta("crawler_version", "0.0.1")
        w.add_source(source)
        w.add_page("spin-framework", fetch_ok, ParsedPage("Quickstart", "ignored", 1), chunks)
        w.add_page("spin-framework", fetch_404, None, [])


@pytest.fixture
def index_path(tmp_path: Path) -> Path:
    p = tmp_path / "index.sqlite"
    _build_tiny_index(p)
    return p


def test_open_returns_working_handle(index_path: Path) -> None:
    handle = IndexHandle.open(index_path)
    try:
        assert handle.path == index_path
    finally:
        handle.close()


def test_open_rejects_wrong_schema_version(tmp_path: Path) -> None:
    bad = tmp_path / "bad.sqlite"
    conn = sqlite3.connect(bad)
    conn.execute("CREATE TABLE meta(key TEXT, value TEXT)")
    conn.execute("INSERT INTO meta VALUES ('schema_version', '99')")
    conn.commit()
    conn.close()
    with pytest.raises(IndexError, match="schema_version 99"):
        IndexHandle.open(bad)


def test_open_rejects_missing_schema_version(tmp_path: Path) -> None:
    bad = tmp_path / "bad.sqlite"
    conn = sqlite3.connect(bad)
    conn.execute("CREATE TABLE meta(key TEXT, value TEXT)")
    conn.commit()
    conn.close()
    with pytest.raises(IndexError, match="missing schema_version"):
        IndexHandle.open(bad)


def test_open_raises_if_file_missing(tmp_path: Path) -> None:
    with pytest.raises(IndexError, match="does not exist"):
        IndexHandle.open(tmp_path / "nope.sqlite")


def test_search_returns_relevant_chunk(index_path: Path) -> None:
    handle = IndexHandle.open(index_path)
    try:
        result = handle.search("install spin cli")
    finally:
        handle.close()
    assert len(result["results"]) >= 1
    top = result["results"][0]
    assert top["url"] == "https://spinframework.dev/v3/quickstart"
    assert "Install" in top["snippet"] or "install" in top["snippet"].lower()
    assert top["source_id"] == "spin-framework"
    assert top["product"] == "Spin Framework"
    assert "Quickstart" in top["heading_path"]
    assert result["meta"]["schema_version"] == "1"
    assert result["meta"]["manifest_sha"] == "deadbeef"


def test_search_filters_by_product(index_path: Path) -> None:
    handle = IndexHandle.open(index_path)
    try:
        hit = handle.search("install", product="Spin Framework")
        miss = handle.search("install", product="Nonexistent Product")
    finally:
        handle.close()
    assert len(hit["results"]) >= 1
    assert miss["results"] == []


def test_search_excludes_tombstoned_urls(index_path: Path) -> None:
    handle = IndexHandle.open(index_path)
    try:
        # The 404'd URL has no chunks, so it can't appear anyway, but
        # verifying the WHERE clause is correct: search 'removed' (which
        # is in the URL but not indexed content) should return nothing.
        result = handle.search("removed")
    finally:
        handle.close()
    assert result["results"] == []


def test_search_limit_clamped(index_path: Path) -> None:
    handle = IndexHandle.open(index_path)
    try:
        many = handle.search("the", limit=1000)
    finally:
        handle.close()
    assert len(many["results"]) <= 50


def test_search_sanitizes_special_chars(index_path: Path) -> None:
    handle = IndexHandle.open(index_path)
    try:
        # Queries with FTS5 operator-like chars should not raise.
        for q in ['rust:component', '"unclosed', 'a OR b', '*', '"', "a-b-c"]:
            handle.search(q)
    finally:
        handle.close()


def test_get_doc_reassembles_full_markdown(index_path: Path) -> None:
    handle = IndexHandle.open(index_path)
    try:
        doc = handle.get_doc("https://spinframework.dev/v3/quickstart")
    finally:
        handle.close()
    assert doc["found"] is True
    assert doc["chunk_count"] == 2
    assert "# Quickstart" in doc["markdown"]
    assert "## Build a Rust component" in doc["markdown"]
    assert doc["tombstoned"] is False
    assert doc["product"] == "Spin Framework"


def test_get_doc_for_tombstoned_url(index_path: Path) -> None:
    handle = IndexHandle.open(index_path)
    try:
        doc = handle.get_doc("https://spinframework.dev/v3/removed")
    finally:
        handle.close()
    assert doc["found"] is True
    assert doc["tombstoned"] is True
    assert doc["chunk_count"] == 0
    assert doc["http_status"] == 404


def test_get_doc_returns_not_found_for_unknown_url(index_path: Path) -> None:
    handle = IndexHandle.open(index_path)
    try:
        doc = handle.get_doc("https://nowhere.example/x")
    finally:
        handle.close()
    assert doc["found"] is False
    assert "not present" in doc["message"]


def test_list_sources_returns_counts(index_path: Path) -> None:
    handle = IndexHandle.open(index_path)
    try:
        listing = handle.list_sources()
    finally:
        handle.close()
    assert len(listing["sources"]) == 1
    src = listing["sources"][0]
    assert src["id"] == "spin-framework"
    assert src["url_count"] == 2
    assert src["tombstoned_count"] == 1
    assert src["product"] == "Spin Framework"
    assert src["last_crawled_at"] == "2026-06-01T00:00:00Z"


def test_resolve_index_path_honors_env_var(
    index_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_INDEX_PATH, str(index_path))
    assert resolve_index_path() == index_path


def test_resolve_index_path_returns_none_when_nothing_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(ENV_INDEX_PATH, raising=False)
    # Redirect HOME so the user-cache path search misses any real file.
    monkeypatch.setenv("HOME", str(tmp_path))
    # We can't easily mock files() but the bundled path won't exist for
    # the dev wheel since we haven't put one there yet.
    import importlib

    from akamai_techdocs_mcp import index as index_mod

    importlib.reload(index_mod)
    assert index_mod.resolve_index_path() is None
