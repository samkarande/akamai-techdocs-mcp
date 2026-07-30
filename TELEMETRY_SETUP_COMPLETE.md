# Telemetry Implementation Summary

## ✅ Implementation Complete

The akamai-techdocs-mcp server now has **always-on, privacy-safe telemetry** that tracks usage metrics to help improve the service.

## What Was Added

### 1. **Core Telemetry Module** (`src/akamai_techdocs_mcp/telemetry.py`)
- Anonymized user tracking (SHA256 hash of username@hostname)
- Session-based metrics (UUID per server start)
- Event tracking for:
  - `server_start` — Server initialization
  - `tool_call` — MCP tool usage (`search_docs`, `get_doc`, `list_sources`)
  - `index_update_check` — Index update checks/downloads

### 2. **S3 Upload Module** (`src/akamai_techdocs_mcp/s3_simple.py`)
- Lightweight AWS Signature V4 implementation
- No boto3 dependency (keeps package minimal)
- Uploads telemetry events to Linode Object Storage

### 3. **Instrumented Code**
- **`server.py`** — Tracks tool calls and server start
- **`updater.py`** — Tracks index update checks

### 4. **Documentation**
- **`docs/TELEMETRY.md`** — User-facing privacy policy
- **`docs/GITHUB_SECRETS_SETUP.md`** — Setup guide for maintainers

### 5. **GitHub Actions Integration**
- Updated `.github/workflows/build-index.yml` to pass Object Storage credentials
- Updated `.github/workflows/release.yml` to pass Object Storage credentials

## How It Works

### User Installs (Zero Privacy Risk)
- **No credentials** → Telemetry is **no-op** (silent, no network calls)
- Users never send telemetry from their machines

### CI Builds/Releases
- **Credentials available** (from GitHub Secrets) → Events sent to Object Storage
- Events stored in: `s3://skills-db-telemetry/telemetry/events/YYYY-MM-DD/{hash}.json`

## Data Collected (Privacy-Safe)

✅ **What we track:**
- Anonymous user ID (hashed)
- Platform (darwin/linux/win32)
- Python version
- Tool usage (which tools, how often)
- Query metadata (length, has_filter) — **NOT the query text**
- Result counts
- Session duration

❌ **What we DON'T track:**
- Search queries or URLs
- Document content
- Usernames, IPs, hostnames (unhashed)
- Any PII

## Next Steps: GitHub Secrets Setup

To enable telemetry in CI builds, add these secrets to your GitHub repository:

1. Go to: https://github.com/samkarande/akamai-techdocs-mcp/settings/secrets/actions
2. Click **New repository secret**
3. Add:
   - Name: `LINODE_OBJECT_ACCESS_KEY`
   - Value: Your Linode Object Storage access key
4. Add:
   - Name: `LINODE_OBJECT_SECRET_KEY`
   - Value: Your Linode Object Storage secret key

**See `docs/GITHUB_SECRETS_SETUP.md` for detailed instructions.**

## Telemetry Storage Details

- **Bucket**: `skills-db-telemetry`
- **Endpoint**: `us-iad-18.linodeobjects.com` (US, Washington DC)
- **Region**: `us-iad-1`
- **Path**: `telemetry/events/YYYY-MM-DD/{event_hash}.json`

Example event file:
```
s3://skills-db-telemetry/telemetry/events/2026-07-30/a3f7c8e91234.json
```

## Testing Telemetry

### Local Test (with credentials)
```bash
export LINODE_OBJECT_ACCESS_KEY="your-access-key"
export LINODE_OBJECT_SECRET_KEY="your-secret-key"

# Run MCP server
akamai-techdocs-mcp
# → Should send server_start event to Object Storage
```

### CI Test
1. Add secrets to GitHub
2. Trigger a workflow (push commit or manual run)
3. Check workflow logs (telemetry failures are silent, won't break builds)
4. Verify files in Object Storage:
   ```bash
   s3cmd ls s3://skills-db-telemetry/telemetry/events/$(date +%Y-%m-%d)/
   ```

## Disabling Telemetry

Set environment variable:
```bash
export AKAMAI_MCP_TELEMETRY_DISABLE=1
```

Or in MCP client config:
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

## Files Modified/Created

### New Files
- `src/akamai_techdocs_mcp/telemetry.py`
- `src/akamai_techdocs_mcp/s3_simple.py`
- `docs/TELEMETRY.md`
- `docs/GITHUB_SECRETS_SETUP.md`
- `TELEMETRY_SETUP_COMPLETE.md` (this file)

### Modified Files
- `src/akamai_techdocs_mcp/server.py` (instrumented)
- `src/akamai_techdocs_mcp/updater.py` (instrumented)
- `.github/workflows/build-index.yml` (added secrets)
- `.github/workflows/release.yml` (added secrets)

## Metrics You Can Track

Once telemetry is flowing, you can analyze:

### Daily Active Users (DAU)
```bash
# Count unique user_ids per day
jq -r .user_id telemetry/events/2026-07-30/*.json | sort -u | wc -l
```

### Tool Usage
```bash
# Most popular tools
jq -r '.tool' telemetry/events/2026-07-30/*.json | sort | uniq -c | sort -rn
```

### Platform Distribution
```bash
# macOS vs Linux vs Windows
jq -r '.platform' telemetry/events/2026-07-30/*.json | sort | uniq -c
```

### Install Methods
```bash
# uvx vs wheel vs git
jq -r '.install_method' telemetry/events/2026-07-30/*.json | sort | uniq -c
```

### Search Patterns
```bash
# Average query length
jq -r 'select(.tool=="search_docs") | .query_char_count' telemetry/events/2026-07-30/*.json | \
  awk '{sum+=$1; n++} END {print sum/n}'
```

## Questions?

- **Privacy concerns?** See `docs/TELEMETRY.md`
- **Setup issues?** See `docs/GITHUB_SECRETS_SETUP.md`
- **Need help?** Open an issue at https://github.com/samkarande/akamai-techdocs-mcp/issues
