# akamai-techdocs-mcp

An MCP server that gives AI assistants (Claude Desktop, Claude Code,
Cursor, …) full-text search across Akamai Functions and Spin Framework
documentation, plus the ability to fetch entire doc pages by URL.

The server ships with a prebuilt SQLite index of the docs, so it works
offline immediately after install. A weekly CI job rebuilds the index
from the URLs declared in [`sources.yaml`](./sources.yaml) — adding
new URLs to that file is the primary way to extend coverage.

## What's indexed

- **Spin Framework v3** — quickstart, writing apps, triggers, language
  guides (Rust / Go / JS / Python), manifest reference, deployment.
- **Akamai Functions** — declared in `sources.yaml`, but currently
  blocked by Akamai's Bot Manager on `techdocs.akamai.com` (HTTP 403
  even via headless Chromium). Resolving that is a separate
  conversation; for now Spin docs (the upstream foundation of
  Akamai Functions) carry most of the code-gen value.

Call `list_sources` from any MCP client to see exactly what's in the
shipped index, including `url_count` and `last_crawled_at`.

## Install

You need [`uv`](https://docs.astral.sh/uv/) installed. Pick whichever
of these matches how you want to run the server.

### Option 1 — `uvx`, no install (recommended for trying it out)

Point your MCP client at `uvx` and let it fetch + cache on each launch:

```sh
uvx --from git+https://github.com/samkarande/akamai-techdocs-mcp akamai-techdocs-mcp
```

Wheels built this way ship without a bundled index; the server's
auto-updater downloads `index.sqlite` from the latest GitHub Release
on first run.

### Option 2 — pinned install from a GitHub Release

The [`build-index.yml`](.github/workflows/build-index.yml) workflow
attaches an installable wheel (with the freshly built index baked in)
to every weekly release. Install the latest:

```sh
uv tool install --reinstall \
  https://github.com/samkarande/akamai-techdocs-mcp/releases/latest/download/akamai_techdocs_mcp-0.0.1-py3-none-any.whl
```

That puts `akamai-techdocs-mcp` on your PATH (typically
`~/.local/bin/akamai-techdocs-mcp`).

### Option 3 — local build from source (developer flow)

```sh
git clone https://github.com/samkarande/akamai-techdocs-mcp.git
cd akamai-techdocs-mcp

# 1. Build the prebuilt index (run once, ~10s for Spin docs).
uv run python -m crawler.build_index

# 2. Build a wheel that bundles the index.
uv build --wheel

# 3. Install the CLI tool globally.
uv tool install --reinstall ./dist/akamai_techdocs_mcp-*.whl
```

## Wire it into your AI client

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or the platform equivalent.

**If you used Option 1 (uvx, no install):**

```json
{
  "mcpServers": {
    "akamai-techdocs": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/samkarande/akamai-techdocs-mcp",
        "akamai-techdocs-mcp"
      ]
    }
  }
}
```

**If you used Option 2 or 3 (installed wheel):**

```json
{
  "mcpServers": {
    "akamai-techdocs": {
      "command": "akamai-techdocs-mcp"
    }
  }
}
```

If `akamai-techdocs-mcp` isn't on Claude Desktop's PATH, use the
absolute path from `which akamai-techdocs-mcp` instead.

Fully quit and reopen Claude Desktop.

### Claude Code

If installed (Options 2/3):

```sh
claude mcp add akamai-techdocs -- akamai-techdocs-mcp
```

Or zero-install (Option 1):

```sh
claude mcp add akamai-techdocs -- \
  uvx --from git+https://github.com/samkarande/akamai-techdocs-mcp akamai-techdocs-mcp
```

### Cursor / other MCP clients

Same shape — `command: akamai-techdocs-mcp`, no args, no env vars.

## Try it

In your assistant, ask things like:

- *"Use the akamai-techdocs MCP to look up how to write a Spin
  component in Rust."*
- *"List the products indexed by akamai-techdocs."*
- *"Search akamai-techdocs for `spin.toml` manifest structure."*
- *"Get the full doc at <https://spinframework.dev/v3/triggers>."*

Each result includes the source URL so the model can (and should) cite
it back in answers.

## Tools the server exposes

- **`search_docs(query, product?, limit?)`** — BM25 full-text search
  across all chunks. Returns a ranked list of `{url, doc_title,
  heading_path, snippet, source_id, product, version, rank}` with
  `«match»` highlighting in the snippet.
- **`get_doc(url)`** — reassembles the full markdown of one doc page
  from its chunks. Returns metadata + the markdown body.
- **`list_sources()`** — catalogue of indexed products with
  `url_count`, `tombstoned_count`, and `last_crawled_at`. Useful for
  finding the exact `product` filter values `search_docs` accepts.

Every response includes an index `meta` block (schema_version,
manifest_version, manifest_sha, built_at, crawler_version) so freshness
is observable.

## Adding URLs to the index

Edit [`sources.yaml`](./sources.yaml). Open a PR. The (still-to-be-set-up)
weekly CI workflow will rebuild the index with your URLs included; users
get the new content on their next refresh — no package upgrade required.

Constraints enforced by the manifest loader:

- URLs must be HTTPS.
- Each URL's hostname must match its source's `domain`.
- Every source `domain` must be present in `allowed_domains`.
- `schema_version` must match what the loader supports.

## Rebuilding the index locally

```sh
uv run python -m crawler.build_index --verbose
```

Inspect the output:

```sh
uv run python -c "
import sqlite3
c = sqlite3.connect('dist/index.sqlite')
for r in c.execute('SELECT key, value FROM meta'): print(r)
print(c.execute('SELECT COUNT(*) FROM chunks').fetchone()[0], 'chunks')
"
```

## Development

```sh
uv sync
uv run pytest
uv run ruff check .
uv run pyright
```

The repo uses Python 3.13 pinned via `.python-version` because Python
3.13.3+ and 3.14 silently skip hatchling's editable install `.pth`
file (it starts with `_`, treated as hidden after a CVE backport).
The repo-root `conftest.py` puts `src/` on `sys.path` for tests as a
local workaround. Wheels (what users install) are unaffected.

## Auto-update

When the server starts, it checks GitHub Releases for a newer
`index-YYYY-MM-DD` tag than what's already in your local cache
(`~/.cache/akamai-techdocs-mcp/`). If one exists, it downloads
`index.sqlite` + `index.sqlite.sha256`, verifies the checksum,
validates the schema, and atomically swaps the file into place.

- The update is **best-effort**: any failure (offline, rate-limited,
  schema mismatch, etc.) logs to stderr and falls back to whatever
  index is already on disk. Server startup never blocks on it for
  more than a few seconds.
- A newly downloaded index **takes effect on the next server
  restart** — your MCP client (Claude Desktop / Code) restarts the
  server when it relaunches, which is usually enough.
- Set `AKAMAI_MCP_OFFLINE=1` in the server's environment to skip
  the check entirely.
- Point at a different repo's releases with
  `AKAMAI_MCP_RELEASES_REPO=owner/repo`.

The weekly [`build-index.yml`](.github/workflows/build-index.yml)
workflow is what produces those releases; users running the installed
wheel pick up fresh content automatically.

## Known limitations

- **Akamai techdocs are not currently indexed** — see "What's indexed"
  above. Akamai's Bot Manager blocks even real headless Chromium with
  HTTP 403. Practical paths: (a) get a UA allowlist via Akamai contacts,
  (b) wait for an alternate doc source.
- **Hot-swap of a freshly downloaded index isn't supported.** The
  running server keeps the old SQLite connection open; the new file
  is visible only on the next start. For most MCP clients this is a
  non-issue since they restart the server on app relaunch.

## License

GPL-3.0-only. See [LICENSE](./LICENSE).
