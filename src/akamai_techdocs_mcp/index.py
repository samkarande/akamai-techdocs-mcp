"""Read-side wrapper around the SQLite index file produced by the crawler.

The MCP server opens one IndexHandle at startup and routes all tool
calls through it. The class is responsible for:

- Discovering where the index file lives (env var > user cache dir >
  bundled wheel data).
- Validating schema_version on open so the server refuses to serve
  from an index it doesn't understand.
- Executing the three read patterns the tools need: FTS search, full
  doc reconstruction by URL, and a sources catalog.

All return values are plain ``dict`` / ``list[dict]`` so the FastMCP
JSON serializer can hand them straight to the client.
"""

from __future__ import annotations

import os
import sqlite3
from importlib.resources import files
from pathlib import Path

EXPECTED_SCHEMA_VERSION = 1

ENV_INDEX_PATH = "AKAMAI_MCP_INDEX_PATH"
USER_CACHE_DIR = Path.home() / ".cache" / "akamai-techdocs-mcp"
USER_CACHE_PATH = USER_CACHE_DIR / "index.sqlite"
BUNDLED_RESOURCE = "data/index.sqlite"


class IndexError(RuntimeError):
    """Raised when the index can't be found, opened, or is incompatible."""


class IndexHandle:
    """One per server process; threadsafe via sqlite3's check_same_thread=False."""

    def __init__(self, conn: sqlite3.Connection, path: Path) -> None:
        self._conn = conn
        self._path = path

    @classmethod
    def open(cls, path: Path | None = None) -> IndexHandle:
        resolved = path or resolve_index_path()
        if resolved is None:
            raise IndexError(
                "no index.sqlite found; set AKAMAI_MCP_INDEX_PATH, place "
                f"one at {USER_CACHE_PATH}, or install a package version "
                "that bundles one"
            )
        if not resolved.exists():
            raise IndexError(f"index file does not exist: {resolved}")

        # check_same_thread=False so FastMCP tool calls (which may come
        # in on different threads) can share one connection. We don't
        # write from the server, so race conditions on reads are fine.
        conn = sqlite3.connect(str(resolved), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _validate_schema(conn, resolved)
        return cls(conn, resolved)

    @property
    def path(self) -> Path:
        return self._path

    def close(self) -> None:
        self._conn.close()

    # ----- queries used by MCP tools -----

    def search(
        self, query: str, *, product: str | None = None, limit: int = 10
    ) -> dict:
        fts_query = _sanitize_fts(query)
        if not fts_query:
            return {"results": [], "meta": self._meta_for_response()}

        sql = (
            "SELECT urls.url, urls.doc_title, urls.last_modified, "
            "chunks.heading_path, chunks.ordinal, "
            "snippet(chunks_fts, 1, '«', '»', ' … ', 16) AS snippet, "
            "sources.id AS source_id, sources.product, sources.version, "
            "bm25(chunks_fts) AS rank "
            "FROM chunks_fts "
            "JOIN chunks ON chunks.id = chunks_fts.rowid "
            "JOIN urls   ON urls.id = chunks.url_id "
            "JOIN sources ON sources.id = urls.source_id "
            "WHERE chunks_fts MATCH ? AND urls.tombstoned = 0"
        )
        params: list[object] = [fts_query]
        if product:
            sql += " AND sources.product = ?"
            params.append(product)
        sql += " ORDER BY rank LIMIT ?"
        params.append(max(1, min(limit, 50)))

        rows = self._conn.execute(sql, params).fetchall()
        results = [
            {
                "url": r["url"],
                "doc_title": r["doc_title"],
                "heading_path": r["heading_path"],
                "ordinal": r["ordinal"],
                "snippet": r["snippet"],
                "source_id": r["source_id"],
                "product": r["product"],
                "version": r["version"],
                "doc_last_modified": r["last_modified"],
                "rank": r["rank"],
            }
            for r in rows
        ]
        return {"results": results, "meta": self._meta_for_response()}

    def get_doc(self, url: str) -> dict:
        url_row = self._conn.execute(
            "SELECT urls.id, urls.url, urls.doc_title, urls.http_status, "
            "urls.last_modified, urls.crawled_at, urls.tombstoned, "
            "sources.id AS source_id, sources.product, sources.version "
            "FROM urls JOIN sources ON sources.id = urls.source_id "
            "WHERE urls.url = ?",
            (url,),
        ).fetchone()
        if url_row is None:
            return {
                "url": url,
                "found": False,
                "message": "URL not present in this index",
                "meta": self._meta_for_response(),
            }

        chunks = self._conn.execute(
            "SELECT heading_path, content_md FROM chunks "
            "WHERE url_id = ? ORDER BY ordinal",
            (url_row["id"],),
        ).fetchall()

        markdown = "\n".join(c["content_md"] for c in chunks).rstrip() + ("\n" if chunks else "")

        return {
            "url": url_row["url"],
            "found": True,
            "doc_title": url_row["doc_title"],
            "source_id": url_row["source_id"],
            "product": url_row["product"],
            "version": url_row["version"],
            "http_status": url_row["http_status"],
            "doc_last_modified": url_row["last_modified"],
            "crawled_at": url_row["crawled_at"],
            "tombstoned": bool(url_row["tombstoned"]),
            "chunk_count": len(chunks),
            "markdown": markdown,
            "meta": self._meta_for_response(),
        }

    def list_sources(self) -> dict:
        rows = self._conn.execute(
            "SELECT sources.id, sources.product, sources.version, "
            "sources.domain, sources.description, "
            "COUNT(urls.id) AS url_count, "
            "SUM(CASE WHEN urls.tombstoned = 1 THEN 1 ELSE 0 END) AS tombstoned_count, "
            "MAX(urls.crawled_at) AS last_crawled_at "
            "FROM sources LEFT JOIN urls ON urls.source_id = sources.id "
            "GROUP BY sources.id ORDER BY sources.product"
        ).fetchall()
        sources = [
            {
                "id": r["id"],
                "product": r["product"],
                "version": r["version"],
                "domain": r["domain"],
                "description": r["description"],
                "url_count": r["url_count"],
                "tombstoned_count": r["tombstoned_count"] or 0,
                "last_crawled_at": r["last_crawled_at"],
            }
            for r in rows
        ]
        return {"sources": sources, "meta": self._meta_for_response()}

    # ----- internals -----

    def _meta_for_response(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT key, value FROM meta").fetchall()
        return {r["key"]: r["value"] for r in rows}


def resolve_index_path() -> Path | None:
    """Find the index file using the standard precedence chain."""
    env_path = os.environ.get(ENV_INDEX_PATH)
    if env_path:
        return Path(env_path)
    if USER_CACHE_PATH.exists():
        return USER_CACHE_PATH
    try:
        bundled = files("akamai_techdocs_mcp").joinpath(BUNDLED_RESOURCE)
        if bundled.is_file():
            return Path(str(bundled))
    except (FileNotFoundError, ModuleNotFoundError):
        pass
    return None


def _validate_schema(conn: sqlite3.Connection, path: Path) -> None:
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if row is None:
        raise IndexError(f"index missing schema_version meta: {path}")
    try:
        v = int(row["value"])
    except (TypeError, ValueError) as exc:
        raise IndexError(f"index has non-integer schema_version: {row['value']!r}") from exc
    if v != EXPECTED_SCHEMA_VERSION:
        raise IndexError(
            f"index schema_version {v} != expected {EXPECTED_SCHEMA_VERSION}; "
            "update the server or rebuild the index"
        )


def _sanitize_fts(query: str) -> str:
    """Turn a free-form query into a safe FTS5 MATCH expression.

    Pure alphanumeric tokens pass through unchanged (so FTS5 stemming /
    prefix logic applies). Tokens containing punctuation or operator
    characters are wrapped in double quotes so they're treated as
    literal phrases rather than parsed as FTS5 syntax.
    """
    tokens: list[str] = []
    for raw in query.split():
        token = raw.strip()
        if not token:
            continue
        if token.isalnum():
            tokens.append(token)
        else:
            tokens.append('"' + token.replace('"', '""') + '"')
    return " ".join(tokens)
