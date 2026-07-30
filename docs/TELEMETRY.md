# Telemetry

The akamai-techdocs-mcp server collects **privacy-safe, always-on telemetry** to help understand usage patterns and improve the service.

## What We Collect

All telemetry is **anonymized and aggregate**. We track:

### Server Events
- **Server starts** — when the MCP server launches
- **Index updates** — when the server checks for/downloads a new index
- **Tool calls** — which tools (`search_docs`, `get_doc`, `list_sources`) are used

### Safe Metadata (No PII)
- **Anonymous user ID** — SHA256 hash of `username@hostname` (first 16 chars)
- **Session ID** — Random UUID generated per server start
- **Platform** — Operating system (darwin/linux/win32)
- **Python version** — e.g., "3.13.1"
- **Install method** — How the MCP was installed (uvx/wheel/git)
- **MCP client** — Which client is running the server (claude-desktop/claude-code/cursor)
- **Server version** — MCP server version (e.g., "0.0.1")
- **Index version** — Timestamp of the indexed documentation

### Tool Usage (Aggregated Only)
For `search_docs`:
- Query length (characters/words) — **NOT the query text itself**
- Whether a product filter was used
- Product name (if filtered) — e.g., "Akamai Functions" (safe, from our index)
- Number of results returned
- Rank score of top result

For `get_doc`:
- Whether the document was found
- Source ID (e.g., "akamai-functions")
- Document size in bytes

For `list_sources`:
- Number of sources returned

## What We DON'T Collect

We **never** collect:
- ❌ Your search queries or document URLs
- ❌ Documentation content
- ❌ Usernames, hostnames, IP addresses (stored as-is)
- ❌ File paths or working directories
- ❌ Environment variables (except our own `AKAMAI_MCP_*` flags)
- ❌ Any personally identifiable information (PII)

## How It Works

1. **Telemetry is always-on** but only sends data when **Object Storage credentials are available** (CI/releases only)
2. Events are written to Linode Object Storage: `skills-db-access-keys` bucket
3. Files are stored as: `telemetry/events/YYYY-MM-DD/{hash}.json`
4. Data is aggregated weekly for analysis

### User Installs vs. CI Builds

- **User installs** (via `uvx`, `uv tool install`) — Telemetry is **no-op** (no credentials → no network calls)
- **CI builds/releases** — Telemetry sends events to Object Storage using GitHub Secrets

This design ensures:
- No unexpected network calls from user machines
- Zero privacy risk for end users
- Telemetry only from "official" builds we distribute

## Disabling Telemetry

To completely disable telemetry (even in CI builds):

```bash
export AKAMAI_MCP_TELEMETRY_DISABLE=1
```

Or in your MCP client config:

```json
{
  "mcpServers": {
    "akamai-techdocs": {
      "command": "akamai-techdocs-mcp",
      "env": {
        "AKAMAI_MCP_TELEMETRY_DISABLE": "1"
      }
    }
  }
}
```

## Example Event

Here's what a typical telemetry event looks like:

```json
{
  "session_id": "a3f7c8e9-1234-5678-90ab-cdef12345678",
  "user_id": "d4e56f789abc",
  "timestamp": "2026-07-30T14:23:45Z",
  "event_type": "tool_call",
  "platform": "darwin",
  "python_version": "3.13.1",
  "install_method": "uvx",
  "mcp_client": "claude-desktop",
  "server_version": "0.0.1",
  "index_version": "2026-07-28T06:15:32Z",
  "index_schema_version": 1,
  "session_uptime_seconds": 142,
  "tool": "search_docs",
  "query_char_count": 42,
  "query_word_count": 6,
  "has_product_filter": true,
  "product_filter": "Akamai Functions",
  "limit_requested": 10,
  "result_count": 8,
  "has_results": true,
  "top_rank": 12.5
}
```

Note: **No query text** or sensitive data.

## Data Retention

- Events are stored indefinitely in Object Storage
- Aggregated metrics are retained for analysis
- Individual event files can be deleted on request

## Questions?

Open an issue at [github.com/samkarande/akamai-techdocs-mcp/issues](https://github.com/samkarande/akamai-techdocs-mcp/issues)
