"""Tests for crawler.writer.IndexWriter.

Validates that fetch results + parsed pages + chunks land in the
schema correctly, including the tombstone path for 404s and the
no-chunks path for pages with parse failures.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from crawler.chunker import Chunk
from crawler.fetcher import FetchOutcome, FetchResult
from crawler.manifest import Source
from crawler.parser import ParsedPage
from crawler.writer import IndexWriter


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "index.sqlite"


def _source() -> Source:
    return Source(
        id="spin-framework",
        product="Spin",
        version="v3",
        domain="spinframework.dev",
        description="upstream",
        urls=("https://spinframework.dev/v3/quickstart",),
    )


def _ok_fetch(url: str = "https://spinframework.dev/v3/quickstart") -> FetchResult:
    return FetchResult(
        url=url,
        outcome=FetchOutcome.OK,
        http_status=200,
        html="<html><h1>X</h1></html>",
        etag="abc",
        last_modified="Mon, 01 Jan 2026 00:00:00 GMT",
        content_hash="hash",
        crawled_at="2026-05-31T12:00:00Z",
    )


def test_creates_schema_on_enter(db_path: Path) -> None:
    with IndexWriter(db_path):
        pass
    assert db_path.exists()
    conn = sqlite3.connect(db_path)
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"meta", "sources", "urls", "chunks"} <= tables


def test_round_trip_source_url_and_chunks(db_path: Path) -> None:
    with IndexWriter(db_path) as w:
        w.set_meta("schema_version", "1")
        w.set_meta("manifest_version", "0.1.0")
        w.add_source(_source())
        parsed = ParsedPage(title="Quickstart", markdown="# Quickstart\n", char_count=14)
        chunks = [
            Chunk(
                ordinal=0,
                heading_path="Quickstart",
                content_md="# Quickstart\nInstall the SDK.\n",
                char_count=30,
                code_block_count=0,
            ),
        ]
        w.add_page("spin-framework", _ok_fetch(), parsed, chunks)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    meta = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}
    assert meta["schema_version"] == "1"
    src = conn.execute("SELECT * FROM sources WHERE id='spin-framework'").fetchone()
    assert src["product"] == "Spin"
    urls = conn.execute("SELECT * FROM urls").fetchall()
    assert len(urls) == 1
    assert urls[0]["doc_title"] == "Quickstart"
    assert urls[0]["tombstoned"] == 0
    chunks_rows = conn.execute("SELECT * FROM chunks WHERE url_id=?", (urls[0]["id"],)).fetchall()
    assert len(chunks_rows) == 1
    # FTS row should be searchable
    fts = conn.execute(
        "SELECT chunks.content_md FROM chunks_fts "
        "JOIN chunks ON chunks.id = chunks_fts.rowid "
        "WHERE chunks_fts MATCH ?",
        ("install",),
    ).fetchall()
    assert len(fts) == 1


def test_404_inserts_tombstoned_row_no_chunks(db_path: Path) -> None:
    with IndexWriter(db_path) as w:
        w.add_source(_source())
        not_found = FetchResult(
            url="https://spinframework.dev/v3/deleted",
            outcome=FetchOutcome.NOT_FOUND,
            http_status=404,
            html=None,
            etag=None,
            last_modified=None,
            content_hash=None,
            crawled_at="2026-05-31T12:00:00Z",
        )
        w.add_page("spin-framework", not_found, parsed=None, chunks=[])

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM urls").fetchone()
    assert row["http_status"] == 404
    assert row["tombstoned"] == 1
    assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0


def test_error_outcome_skipped(db_path: Path) -> None:
    with IndexWriter(db_path) as w:
        w.add_source(_source())
        err = FetchResult(
            url="https://spinframework.dev/v3/flaky",
            outcome=FetchOutcome.ERROR,
            http_status=0,
            html=None,
            etag=None,
            last_modified=None,
            content_hash=None,
            crawled_at="2026-05-31T12:00:00Z",
            error="connection reset",
        )
        w.add_page("spin-framework", err, parsed=None, chunks=[])

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM urls").fetchone()[0] == 0


def test_overwrites_existing_index_file(db_path: Path) -> None:
    db_path.write_bytes(b"junk")
    with IndexWriter(db_path) as w:
        w.add_source(_source())
    # File is now a real SQLite — no stale junk.
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 1


def test_raises_if_used_outside_context(db_path: Path) -> None:
    w = IndexWriter(db_path)
    with pytest.raises(RuntimeError, match="outside of a `with` block"):
        w.set_meta("k", "v")


def test_does_not_commit_on_exception(db_path: Path) -> None:
    with pytest.raises(RuntimeError, match="boom"), IndexWriter(db_path) as w:
        w.add_source(_source())
        raise RuntimeError("boom")
    # Connection closed without commit; sources insert was rolled back.
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0
