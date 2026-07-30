# Telemetry Setup Instructions

## Overview

Your MCP server now has **always-on telemetry** that tracks usage metrics. The implementation is **privacy-safe** and only sends data from CI builds (not user installs).

## Quick Start: 3 Steps to Enable

### Step 1: Add GitHub Secrets

Go to your repository settings and add these two secrets:

**URL**: https://github.com/samkarande/akamai-techdocs-mcp/settings/secrets/actions

1. Click **"New repository secret"**
2. Add **first secret**:
   - Name: `LINODE_OBJECT_ACCESS_KEY`
   - Value: Your Linode Object Storage access key
   - Click "Add secret"

3. Add **second secret**:
   - Name: `LINODE_OBJECT_SECRET_KEY`  
   - Value: Your Linode Object Storage secret key
   - Click "Add secret"

### Step 2: Verify Secrets Are Set

After adding secrets, verify they appear in the list:
- Go to: https://github.com/samkarande/akamai-techdocs-mcp/settings/secrets/actions
- You should see:
  - `LINODE_OBJECT_ACCESS_KEY` (Updated X time ago)
  - `LINODE_OBJECT_SECRET_KEY` (Updated X time ago)

### Step 3: Test with a Build

Trigger a GitHub Actions workflow to test:

**Option A: Manual workflow dispatch**
```bash
gh workflow run build-index.yml
```

**Option B: Push a commit**
```bash
git commit --allow-empty -m "test: trigger telemetry"
git push
```

Then check the workflow logs:
```bash
gh run list --workflow=build-index.yml --limit=1
gh run view <run-id>
```

Telemetry failures are **silent** (won't break builds), so no error = success.

## Object Storage Details

- **Bucket**: `skills-db-access-keys`
- **Endpoint**: `us-iad-18.linodeobjects.com`
- **Region**: `us-iad-1`
- **Path pattern**: `telemetry/events/YYYY-MM-DD/{hash}.json`

## Verify Telemetry Data

After a workflow run, check that events appear in Object Storage:

### Using s3cmd
```bash
# List today's events
s3cmd ls s3://skills-db-access-keys/telemetry/events/$(date +%Y-%m-%d)/

# View an event file
s3cmd get s3://skills-db-access-keys/telemetry/events/2026-07-30/abc123.json - | jq
```

### Using Linode Cloud Manager
1. Go to: https://cloud.linode.com/object-storage/buckets
2. Click on `skills-db-access-keys` bucket
3. Navigate to: `telemetry/events/YYYY-MM-DD/`
4. You should see `.json` files (one per event)

## What Gets Tracked

### Events
- **`server_start`** — MCP server initialization
- **`tool_call`** — Tool usage (`search_docs`, `get_doc`, `list_sources`)
- **`index_update_check`** — Index update checks/downloads

### Safe Metadata (No PII)
- Anonymous user ID (SHA256 hash, 16 chars)
- Session ID (random UUID per server start)
- Platform (darwin/linux/win32)
- Python version
- Install method (uvx/wheel/git)
- MCP client (claude-desktop/claude-code/cursor)
- Server/index versions

### Tool-Specific Data
For `search_docs`:
- Query length (chars/words) — **NOT the query text**
- Product filter (if used)
- Result count
- Top rank score

For `get_doc`:
- Doc found (boolean)
- Source ID
- Doc size (bytes)

## Privacy Guarantees

✅ **We NEVER collect:**
- Search queries or URLs
- Document content
- Usernames, IPs, hostnames (unhashed)
- File paths or environment variables
- Any personally identifiable information

✅ **User installs (via uvx, uv tool install):**
- **Zero telemetry** — no credentials → no network calls
- Complete privacy for end users

✅ **CI builds only:**
- Telemetry only sent from GitHub Actions
- Only when secrets are configured

## Troubleshooting

### No telemetry files appearing?

**1. Check secrets are set correctly**
```bash
gh secret list
# Should show:
# LINODE_OBJECT_ACCESS_KEY  Updated X ago
# LINODE_OBJECT_SECRET_KEY  Updated X ago
```

**2. Check workflow logs**
```bash
gh run list --workflow=build-index.yml --limit=1
gh run view <run-id> --log
```

Look for telemetry-related errors (silent failures won't show)

**3. Test credentials locally**
```bash
export LINODE_OBJECT_ACCESS_KEY="your-key"
export LINODE_OBJECT_SECRET_KEY="your-secret"

python test_telemetry.py
# Should print: ✓ Event sent!
```

**4. Verify bucket permissions**
Your access key needs **read/write** permission on `skills-db-access-keys` bucket.

Check in Linode Cloud Manager:
- Object Storage → Access Keys
- Click on your key
- Verify: `skills-db-access-keys` (read/write) ✓

### Test locally with credentials

```bash
# Export credentials
export LINODE_OBJECT_ACCESS_KEY="your-access-key"
export LINODE_OBJECT_SECRET_KEY="your-secret-key"

# Run test script
python test_telemetry.py

# Or run the MCP server (will send server_start event)
uv run akamai-techdocs-mcp
```

### Invalid credentials error

If you see `403 Forbidden` or signature errors:
1. Regenerate access keys in Linode Cloud Manager
2. Update GitHub secrets with new values
3. Test with a new workflow run

## Metrics Analysis Examples

Once telemetry is flowing, analyze with these commands:

### Daily Active Users
```bash
# Count unique users per day
jq -r .user_id telemetry/events/2026-07-30/*.json | sort -u | wc -l
```

### Tool Usage Distribution
```bash
# Most popular tools
jq -r '.tool' telemetry/events/2026-07-30/*.json | \
  grep -v null | sort | uniq -c | sort -rn
```

### Platform Breakdown
```bash
# macOS vs Linux vs Windows
jq -r '.platform' telemetry/events/2026-07-30/*.json | \
  sort | uniq -c | sort -rn
```

### Install Method Distribution
```bash
# uvx vs wheel vs git
jq -r '.install_method' telemetry/events/2026-07-30/*.json | \
  sort | uniq -c | sort -rn
```

### Search Analytics
```bash
# Average query length
jq -r 'select(.tool=="search_docs") | .query_char_count' \
  telemetry/events/2026-07-30/*.json | \
  awk '{sum+=$1; n++} END {if(n>0) print sum/n}'

# Search success rate (queries with results)
jq -r 'select(.tool=="search_docs") | .has_results' \
  telemetry/events/2026-07-30/*.json | \
  awk '{if($1=="true") yes++; total++} END {print yes/total*100 "%"}'
```

## Disabling Telemetry

### For all users (via environment variable)
Add to MCP client config:

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

### For CI builds only
Remove GitHub secrets:
```bash
gh secret remove LINODE_OBJECT_ACCESS_KEY
gh secret remove LINODE_OBJECT_SECRET_KEY
```

## Files Added/Modified

### New Files
- `src/akamai_techdocs_mcp/telemetry.py` — Core telemetry module
- `src/akamai_techdocs_mcp/s3_simple.py` — Minimal AWS SigV4 signer
- `docs/TELEMETRY.md` — User-facing privacy policy
- `docs/GITHUB_SECRETS_SETUP.md` — Detailed setup guide
- `test_telemetry.py` — Local testing script
- `TELEMETRY_SETUP_COMPLETE.md` — Implementation summary
- `SETUP_INSTRUCTIONS.md` — This file

### Modified Files
- `src/akamai_techdocs_mcp/server.py` — Instrumented tool calls
- `src/akamai_techdocs_mcp/updater.py` — Instrumented index updates
- `.github/workflows/build-index.yml` — Added secrets to env
- `.github/workflows/release.yml` — Added secrets to env

## Next Steps

1. ✅ Add GitHub Secrets (Step 1 above)
2. ✅ Verify secrets are set
3. ✅ Trigger a test build
4. ✅ Check Object Storage for telemetry files
5. 📊 Set up weekly aggregation script (future work)
6. 📈 Build analytics dashboard (future work)

## Support

- **Privacy questions?** → See `docs/TELEMETRY.md`
- **Setup issues?** → See `docs/GITHUB_SECRETS_SETUP.md`
- **Need help?** → Open issue at https://github.com/samkarande/akamai-techdocs-mcp/issues
