# akamai-techdocs-mcp

An MCP server that gives AI assistants (Claude Desktop, Claude Code,
Cursor, …) full-text search across Akamai Cloud (Linode) and Akamai
Functions documentation, plus the ability to fetch entire doc pages by
URL.

The server ships with a prebuilt SQLite index of the docs, so it works
offline immediately after install. A CI job rebuilds the index from the
URLs declared in [`sources.yaml`](./sources.yaml) — adding new URLs to
that file is the primary way to extend coverage.

## Sources included

Roughly 1,500 searchable chunks across:

- **Linode API** — the full OpenAPI specification (~449 operations:
  Linodes, LKE, Managed Databases, Object Storage, VPCs, NodeBalancers,
  Firewalls, DNS, account/billing, and more).
- **Linode open-source projects** — READMEs for every non-fork repo in
  [github.com/linode](https://github.com/linode) (91 repos): SDKs
  (`linodego`, `linode_api4-python`), the Linode CLI, IaC providers
  (Terraform, Ansible, Packer), Kubernetes/LKE operators (cloud
  controller manager, CSI/COSI drivers, Cluster API, Karpenter), the
  Akamai App Platform (APL), AI quickstarts, and more.
- **Spin Framework v3** — the WebAssembly app framework upstream of
  Akamai Functions (quickstart, triggers, language guides, manifest
  reference, deployment).
- **Ecosystem references** — KEDA (event-driven autoscaling), Karpenter
  (node autoscaling), and a HashiCorp Terraform modules tutorial.

Call `list_sources` from any MCP client to see exactly what's in the
shipped index, including `url_count` and `last_crawled_at`.

> Note: hand-written docs on `techdocs.akamai.com` are not indexed —
> Akamai's Bot Manager returns HTTP 403 to crawlers (local and CI
> alike). The Linode API content is sourced from the upstream OpenAPI
> spec on GitHub instead.

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

Every release attaches an installable wheel with the freshly built
index baked in. Grab the wheel URL from the
[latest release](https://github.com/samkarande/akamai-techdocs-mcp/releases/latest)
and install it (the filename includes the version):

```sh
uv tool install --reinstall \
  https://github.com/samkarande/akamai-techdocs-mcp/releases/download/<tag>/akamai_techdocs_mcp-<version>-py3-none-any.whl
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

- *"Use akamai-techdocs to look up the Linode API call to create an LKE
  Kubernetes cluster."*
- *"Search akamai-techdocs for the `linode_object_storage_bucket`
  Terraform resource."*
- *"How do I create an instance with the linodego Go SDK? Check
  akamai-techdocs."*
- *"Look up how to write a Spin component in Rust."*
- *"List the products indexed by akamai-techdocs."*

Each result includes the source URL so the model can (and should) cite
it back in answers.

## Examples

The [`examples/`](./examples) directory holds worked, copy-pasteable
solutions to common Akamai Cloud tasks. Each example is its own folder
containing the originating natural-language **prompt** (`prompt.txt`),
runnable code, and a README explaining the design.

| # | Example | Stack |
|---|---|---|
| 1 | [`01-nodebalancer-vpc-apache`](./examples/01-nodebalancer-vpc-apache) | Terraform — Apache web tier (2× nano) behind a NodeBalancer in a new VPC |
| 2 | [`02-object-storage-private-bucket`](./examples/02-object-storage-private-bucket) | Terraform — a private (non-public) Object Storage bucket |
| 3 | [`03-managed-mysql-database`](./examples/03-managed-mysql-database) | Terraform — a Managed MySQL 8 database |

These were produced by prompting an assistant wired to this MCP server;
the `prompt.txt` in each folder is the exact request. They are reference
code — review before applying to a real account.

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

Edit [`sources.yaml`](./sources.yaml). Open a PR. The weekly CI workflow
([`build-index.yml`](.github/workflows/build-index.yml)) rebuilds the
index with your URLs included; users get the new content on their next
refresh — no package upgrade required.

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

## Cutting a release

Two workflows publish to GitHub Releases:

- **[`build-index.yml`](.github/workflows/build-index.yml)** runs every
  Monday at 06:00 UTC (and on demand via `workflow_dispatch`). It
  rebuilds `index.sqlite`, packages a wheel with that index, and
  publishes both under a date-based tag like `index-2026-06-08`. This
  is what keeps installed copies' documentation fresh.

- **[`release.yml`](.github/workflows/release.yml)** is for cutting a
  versioned code release. Two ways to trigger it:

  ```sh
  # Tag-driven (preferred)
  git tag v0.1.0
  git push origin v0.1.0

  # Or manual via the GitHub UI / CLI
  gh workflow run release.yml -f version=0.1.0
  ```

  It builds an index, builds a wheel whose filename includes the
  version (`akamai_techdocs_mcp-0.1.0-py3-none-any.whl`), and creates
  a release named `v0.1.0`. The pyproject version is edited in the
  runner only; the repo itself stays untouched.

## Auto-update

When the server starts, it checks GitHub Releases for a release newer
(by publish time) than what's already in your local cache
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

- **`techdocs.akamai.com` is not indexed** — see "Sources included"
  above. Akamai's Bot Manager returns HTTP 403 to crawlers (local and
  CI), so Linode API content comes from the upstream OpenAPI spec on
  GitHub instead.
- **Hot-swap of a freshly downloaded index isn't supported.** The
  running server keeps the old SQLite connection open; the new file
  is visible only on the next start. For most MCP clients this is a
  non-issue since they restart the server on app relaunch.

## License

GPL-3.0-only. See [LICENSE](./LICENSE).
