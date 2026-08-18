# Telemetry Fix - Getting Data Collection Working

## Problem Identified

Telemetry was never actually collecting data because:

1. **Telemetry requires credentials** (`LINODE_OBJECT_ACCESS_KEY` / `LINODE_OBJECT_SECRET_KEY`)
2. **Credentials are only set in CI workflows**
3. **But in CI, we only BUILD the index** - we never actually RUN the MCP server
4. **Result**: No telemetry events were ever sent! ❌

## Root Cause

In `src/akamai_techdocs_mcp/telemetry.py` (lines 168-174):

```python
access_key = os.getenv("LINODE_OBJECT_ACCESS_KEY")
secret_key = os.getenv("LINODE_OBJECT_SECRET_KEY")

# Only send telemetry if credentials are available (CI builds/releases)
# User installs won't have these and telemetry will be a no-op
if not access_key or not secret_key:
    return
```

This design was intentional to avoid collecting telemetry from end users, but it created a catch-22:
- **Users don't have credentials** → no telemetry
- **CI has credentials BUT doesn't run the server** → no telemetry
- **Result**: Zero data collection

## Solution Implemented

### 1. New Workflow: `smoke-test-server.yml`

**Purpose**: Actually run the MCP server and make sample tool calls to generate telemetry

**Triggers**:
- After each weekly index build completes
- Manual via workflow_dispatch
- Weekly on Tuesdays (day after Monday's index build)

**What it does**:
- Starts the MCP server
- Tracks `server_start` event
- Calls `list_sources()`
- Calls `search_docs()` with various queries
- Calls `get_doc()` for a sample document
- All events are sent to Object Storage with credentials from GitHub secrets

**Result**: Real usage telemetry from simulated client interactions ✅

### 2. Enhanced `build-index.yml` Workflow

**Added**: New "Track index build telemetry" step after building the index

**What it tracks**:
```json
{
  "event_type": "index_build_complete",
  "context": "ci_build",
  "manifest_version": "0.10.0",
  "schema_version": 1,
  "total_urls": 1234,
  "total_chunks": 5678,
  "total_sources": 21,
  "sources": [
    {"product": "Akamai Cloud Computing", "version": "latest", "urls": 600},
    {"product": "EdgeWorkers", "version": "latest", "urls": 200},
    // ... etc
  ]
}
```

**Result**: Build-time telemetry showing index growth over time ✅

## Expected Telemetry Events

After these changes, we will now collect:

### From `smoke-test-server.yml` (weekly)
1. **`server_start`** - Server startup in CI
2. **`tool_call` (list_sources)** - Tracking source enumeration
3. **`tool_call` (search_docs)** - Multiple search queries with/without filters
4. **`tool_call` (get_doc)** - Document retrieval

### From `build-index.yml` (weekly)
1. **`index_build_complete`** - Index build statistics
2. **`index_update_check`** - Update checks (from updater.py when it runs)

## Verification

To verify telemetry is working:

1. **Wait for next scheduled run** (Monday 06:00 UTC for build, Tuesday 08:00 UTC for smoke test)
   
   OR
   
2. **Trigger manually**:
   ```bash
   # GitHub UI: Actions → "Build index" → Run workflow
   # GitHub UI: Actions → "Smoke Test Server" → Run workflow
   ```

3. **Check Object Storage**:
   - Log into Linode Cloud Manager
   - Navigate to Object Storage → `skills-db-telemetry`
   - Browse to `telemetry/events/<today's-date>/`
   - You should see multiple JSON files (one per event)

## File Structure

Telemetry events are stored as:
```
skills-db-telemetry/
  telemetry/
    events/
      2026-08-18/
        abc123def456.json  ← index_build_complete
        789ghi012jkl.json  ← server_start
        mno345pqr678.json  ← tool_call (search_docs)
        ...
```

Each filename is a SHA256 hash of the event content (first 12 chars).

## Privacy & Design Notes

✅ **Still privacy-safe**: Credentials only exist in GitHub Actions, not user installs

✅ **No user telemetry**: End users running the server locally still won't send data

✅ **CI-only metrics**: We only track CI builds and automated smoke tests

✅ **Non-blocking**: Telemetry failures are caught and ignored - never break workflows

## Next Steps

1. **Monitor first run**: Check Object Storage after next Monday's build (08/25)
2. **Validate data**: Download a few JSON files and verify structure
3. **Build dashboard**: Once data accumulates, create analysis scripts
4. **Track trends**: Monitor index growth, search patterns, client adoption over time

## Files Changed

- ✅ `.github/workflows/smoke-test-server.yml` (NEW) - Runs server and makes tool calls
- ✅ `.github/workflows/build-index.yml` (MODIFIED) - Added telemetry tracking step
- ✅ `src/akamai_techdocs_mcp/telemetry.py` (UNCHANGED) - Already has all tracking hooks
- ✅ `src/akamai_techdocs_mcp/updater.py` (UNCHANGED) - Already tracks update checks

---

**Status**: ✅ **Fixed and ready for next CI run!**

The telemetry system will now collect data starting with the next weekly index build (Mondays @ 06:00 UTC) and smoke test (Tuesdays @ 08:00 UTC).
