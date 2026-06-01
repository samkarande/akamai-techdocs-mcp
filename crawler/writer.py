"""Write a populated index.sqlite from crawl results.

Composes the rest of the crawler pipeline: takes FetchResult + parsed
markdown + chunks and writes rows into the sources/urls/chunks/chunks_fts
tables. Each CI run creates a fresh index file from scratch — there is
no incremental update story at this layer (the server consumes the
file as a whole when downloaded from a GitHub Release).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType

from crawler.chunker import Chunk
from crawler.fetcher import FetchOutcome, FetchResult
from crawler.manifest import Source
from crawler.parser import ParsedPage

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class IndexWriter:
    """Open and populate a fresh SQLite index file."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> IndexWriter:
        # Start fresh: never append to an existing index.
        if self._db_path.exists():
            self._db_path.unlink()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._conn is not None:
            if exc is None:
                self._conn.commit()
            self._conn.close()
            self._conn = None

    def set_meta(self, key: str, value: str) -> None:
        self._require_conn().execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (key, value),
        )

    def add_source(self, source: Source) -> None:
        self._require_conn().execute(
            "INSERT INTO sources(id, product, version, description, domain) "
            "VALUES (?, ?, ?, ?, ?)",
            (source.id, source.product, source.version, source.description, source.domain),
        )

    def add_page(
        self,
        source_id: str,
        fetch: FetchResult,
        parsed: ParsedPage | None,
        chunks: list[Chunk],
    ) -> None:
        """Insert a URL row plus its chunks (or a tombstone for 404s).

        FetchResults with outcome ERROR are skipped — they belong in the
        crawl log, not the index. Tombstones (NOT_FOUND) are inserted
        with tombstoned=1 so the server can hide them from search while
        still returning a clear "removed upstream" answer on direct
        lookups.
        """
        conn = self._require_conn()

        if fetch.outcome is FetchOutcome.ERROR:
            return

        doc_title = parsed.title if parsed else None
        tombstoned = 1 if fetch.outcome is FetchOutcome.NOT_FOUND else 0

        cur = conn.execute(
            "INSERT INTO urls(source_id, url, doc_title, http_status, etag, "
            "last_modified, content_hash, crawled_at, tombstoned) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source_id,
                fetch.url,
                doc_title,
                fetch.http_status,
                fetch.etag,
                fetch.last_modified,
                fetch.content_hash,
                fetch.crawled_at,
                tombstoned,
            ),
        )
        url_id = cur.lastrowid

        # Only OK pages with parsed content produce chunks.
        if fetch.outcome is not FetchOutcome.OK or parsed is None or not chunks:
            return

        for chunk in chunks:
            chunk_cur = conn.execute(
                "INSERT INTO chunks(url_id, ordinal, heading_path, content_md, "
                "char_count, code_block_count) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    url_id,
                    chunk.ordinal,
                    chunk.heading_path,
                    chunk.content_md,
                    chunk.char_count,
                    chunk.code_block_count,
                ),
            )
            conn.execute(
                "INSERT INTO chunks_fts(rowid, heading_path, content_md, doc_title) "
                "VALUES (?, ?, ?, ?)",
                (
                    chunk_cur.lastrowid,
                    chunk.heading_path,
                    chunk.content_md,
                    doc_title or "",
                ),
            )

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("IndexWriter used outside of a `with` block")
        return self._conn
