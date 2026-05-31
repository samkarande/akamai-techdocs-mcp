-- akamai-techdocs-mcp index schema v1
--
-- Source of truth for the SQLite index format produced by the CI
-- crawler and consumed by the MCP server. One file ships per CI
-- release; the server validates meta.schema_version against the
-- EXPECTED_SCHEMA_VERSION constant in the server code.

-- Key/value metadata for the index as a whole.
-- Expected keys: schema_version, manifest_version, manifest_sha,
-- manifest_url, built_at, crawler_version.
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- One row per logical source (e.g. akamai-functions, spin-framework).
CREATE TABLE sources (
    id          TEXT PRIMARY KEY,
    product     TEXT NOT NULL,
    version     TEXT NOT NULL,
    description TEXT,
    domain      TEXT NOT NULL
);

-- One row per crawled URL. Survives 404s as tombstones so that
-- removed pages no longer surface in search but still resolve when
-- looked up explicitly (with a clear status).
CREATE TABLE urls (
    id            INTEGER PRIMARY KEY,
    source_id     TEXT    NOT NULL REFERENCES sources(id),
    url           TEXT    NOT NULL UNIQUE,
    doc_title     TEXT,
    http_status   INTEGER NOT NULL,
    etag          TEXT,
    last_modified TEXT,
    content_hash  TEXT,
    crawled_at    TEXT    NOT NULL,          -- ISO-8601 UTC
    tombstoned    INTEGER NOT NULL DEFAULT 0 -- 1 = removed upstream
);
CREATE INDEX urls_source_id_idx ON urls(source_id);

-- One chunk per heading-scoped section of a doc page.
CREATE TABLE chunks (
    id               INTEGER PRIMARY KEY,
    url_id           INTEGER NOT NULL REFERENCES urls(id),
    ordinal          INTEGER NOT NULL,  -- 0-based position within the page
    heading_path     TEXT    NOT NULL,  -- breadcrumb, e.g. "Quickstart > Install"
    content_md       TEXT    NOT NULL,
    char_count       INTEGER NOT NULL,
    code_block_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX chunks_url_id_idx ON chunks(url_id);

-- Full-text search over chunks. Contentless form keeps schema simple;
-- the crawler explicitly INSERTs into both chunks and chunks_fts.
-- porter+unicode61 gives English stemming with identifiers split on
-- punctuation (so "spin" matches docs about "spin.toml", which is the
-- dominant natural-language query pattern). Exact identifier matching
-- can be added later via a second indexed column if needed.
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    heading_path,
    content_md,
    doc_title,
    tokenize = "porter unicode61"
);
