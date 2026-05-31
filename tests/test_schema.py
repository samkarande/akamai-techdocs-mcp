"""End-to-end smoke test for the SQLite index schema.

Loads crawler/schema.sql into an in-memory database, inserts one
source / url / chunk, indexes it in FTS5, and verifies that joined
lookups return what the MCP server tools will need.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

SCHEMA_PATH = Path(__file__).parent.parent / "crawler" / "schema.sql"


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text())
    conn.row_factory = sqlite3.Row
    return conn


def test_schema_file_exists() -> None:
    assert SCHEMA_PATH.exists(), f"schema.sql missing at {SCHEMA_PATH}"


def test_can_insert_and_query_chunk(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?), (?, ?)",
        ("schema_version", "1", "manifest_version", "0.1.0"),
    )
    db.execute(
        "INSERT INTO sources(id, product, version, description, domain) "
        "VALUES (?, ?, ?, ?, ?)",
        ("akamai-functions", "Akamai Functions", "latest", "Test", "techdocs.akamai.com"),
    )
    cur = db.execute(
        "INSERT INTO urls(source_id, url, doc_title, http_status, crawled_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "akamai-functions",
            "https://techdocs.akamai.com/akamai-functions/docs/quickstart",
            "Quickstart",
            200,
            "2026-05-31T12:00:00Z",
        ),
    )
    url_id = cur.lastrowid

    cur = db.execute(
        "INSERT INTO chunks(url_id, ordinal, heading_path, content_md, char_count, "
        "code_block_count) VALUES (?, ?, ?, ?, ?, ?)",
        (
            url_id,
            0,
            "Quickstart > Install the aka CLI",
            "Run `aka login` to authenticate against your Akamai account.",
            58,
            1,
        ),
    )
    chunk_id = cur.lastrowid

    db.execute(
        "INSERT INTO chunks_fts(rowid, heading_path, content_md, doc_title) "
        "VALUES (?, ?, ?, ?)",
        (
            chunk_id,
            "Quickstart > Install the aka CLI",
            "Run `aka login` to authenticate against your Akamai account.",
            "Quickstart",
        ),
    )

    row = db.execute(
        "SELECT u.url, u.doc_title, c.heading_path, c.content_md, s.product "
        "FROM chunks_fts f "
        "JOIN chunks c ON c.id = f.rowid "
        "JOIN urls   u ON u.id = c.url_id "
        "JOIN sources s ON s.id = u.source_id "
        "WHERE chunks_fts MATCH 'authenticate'"
    ).fetchone()
    assert row is not None
    assert row["product"] == "Akamai Functions"
    assert row["doc_title"] == "Quickstart"
    assert "aka login" in row["content_md"]


def test_fts_splits_on_punctuation(db: sqlite3.Connection) -> None:
    """Natural-language queries should match identifiers via their parts.

    "spin" should find docs mentioning "spin.toml", and "trigger" should
    find docs mentioning "http-trigger". This is the dominant query
    pattern for a docs MCP.
    """
    db.execute(
        "INSERT INTO sources(id, product, version, domain) VALUES (?, ?, ?, ?)",
        ("spin-framework", "Spin", "v3", "spinframework.dev"),
    )
    cur = db.execute(
        "INSERT INTO urls(source_id, url, http_status, crawled_at) VALUES (?, ?, ?, ?)",
        (
            "spin-framework",
            "https://spinframework.dev/v3/manifest-reference",
            200,
            "2026-05-31T12:00:00Z",
        ),
    )
    cur = db.execute(
        "INSERT INTO chunks(url_id, ordinal, heading_path, content_md, char_count) "
        "VALUES (?, ?, ?, ?, ?)",
        (cur.lastrowid, 0, "Manifest", "Define triggers in spin.toml using http-trigger keys.", 51),
    )
    db.execute(
        "INSERT INTO chunks_fts(rowid, heading_path, content_md, doc_title) "
        "VALUES (?, ?, ?, ?)",
        (
            cur.lastrowid,
            "Manifest",
            "Define triggers in spin.toml using http-trigger keys.",
            "Manifest",
        ),
    )

    for term in ("spin", "toml", "trigger"):
        rows = db.execute(
            "SELECT content_md FROM chunks_fts WHERE chunks_fts MATCH ?", (term,),
        ).fetchall()
        assert len(rows) == 1, f"query {term!r} should match the spin.toml/http-trigger chunk"


def test_tombstoned_url_filter(db: sqlite3.Connection) -> None:
    """Server-side queries can filter out tombstoned URLs."""
    db.execute(
        "INSERT INTO sources(id, product, version, domain) VALUES (?, ?, ?, ?)",
        ("akamai-functions", "Akamai Functions", "latest", "techdocs.akamai.com"),
    )
    base = "https://techdocs.akamai.com/akamai-functions/docs"
    now = "2026-05-31T12:00:00Z"
    db.executemany(
        "INSERT INTO urls(source_id, url, http_status, crawled_at, tombstoned) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            ("akamai-functions", f"{base}/a", 200, now, 0),
            ("akamai-functions", f"{base}/b", 404, now, 1),
        ],
    )
    live = db.execute("SELECT COUNT(*) FROM urls WHERE tombstoned = 0").fetchone()[0]
    assert live == 1
