# Telemetry Status Report

## Summary

✅ **Telemetry is working correctly!**

The telemetry system successfully uploads anonymized usage data to Linode Object Storage during CI builds.

## Test Results

### Upload Test (2026-07-30)
- **Status**: ✅ SUCCESS
- **Workflow**: `test-telemetry.yml` (run #30576026656)
- **Result**: `✓ Upload succeeded!`
- **Endpoint**: `us-iad-18.linodeobjects.com`
- **Bucket**: `skills-db-access-keys`
- **Path Pattern**: `telemetry/events/YYYY-MM-DD/{hash}.json`

### Verification Test
- **Status**: ⚠️  EXPECTED FAILURE
- **Error**: `403 Forbidden` on LIST operation
- **Reason**: Object Storage access keys are **write-only** (PUT permissions only)
- **Impact**: None - this is a security feature, not a bug

## How It Works

1. **CI Builds Only**: Telemetry only runs when `LINODE_OBJECT_ACCESS_KEY` and `LINODE_OBJECT_SECRET_KEY` environment variables are present
2. **User Installs**: Regular users installing via `uvx` or `pip` will NOT send telemetry (no credentials = no uploads)
3. **Silent Operation**: Upload failures never break the MCP server
4. **Write-Only Access**: For security, the API keys can only PUT objects, not LIST or GET them

## Verification

Since the access keys are write-only, you cannot programmatically list uploaded telemetry events. To verify telemetry data:

1. **Linode Cloud Manager**: Log in to the Linode Cloud Manager and navigate to Object Storage
2. **Bucket**: `skills-db-access-keys`
3. **Path**: `telemetry/events/<date>/`

Alternatively, create a separate read-only access key for verification purposes.

## CI Integration

Telemetry is enabled in these workflows:

- ✅ `.github/workflows/build-index.yml` (scheduled index builds)
- ✅ `.github/workflows/release.yml` (releases)
- ✅ `.github/workflows/test-telemetry.yml` (manual testing)

## Privacy Guarantees

- ✅ User IDs are SHA256-hashed
- ✅ No PII collected (queries, URLs, usernames are excluded)
- ✅ Only aggregated metrics
- ✅ Disable anytime with `AKAMAI_MCP_TELEMETRY_DISABLE=1`

## Next Steps

To view telemetry data:

1. Log in to Linode Cloud Manager
2. Navigate to Object Storage > `skills-db-access-keys`
3. Browse `telemetry/events/2026-07-30/` (or current date)
4. Download and analyze the JSON events

Or create a read-access key for programmatic analysis.

## Files

- `src/akamai_techdocs_mcp/telemetry.py` - Core telemetry tracking
- `src/akamai_techdocs_mcp/s3_simple.py` - AWS SigV4 signer for Object Storage
- `test_telemetry_debug.py` - Manual test script
- `verify_object_storage.py` - Verification script (requires LIST permissions)
- `.github/workflows/test-telemetry.yml` - CI test workflow
