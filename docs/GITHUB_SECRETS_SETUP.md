# GitHub Secrets Setup for Telemetry

The MCP server collects telemetry during **CI builds and releases** only. To enable this, you need to add Linode Object Storage credentials as GitHub repository secrets.

## Required Secrets

Add these two secrets to your GitHub repository:

1. **`LINODE_OBJECT_ACCESS_KEY`** — Your Object Storage access key
2. **`LINODE_OBJECT_SECRET_KEY`** — Your Object Storage secret key

## Step-by-Step Setup

### 1. Get Your Linode Object Storage Access Keys

You should already have access keys for the `skills-db-access-keys` bucket. If not, create them:

1. Log in to [Linode Cloud Manager](https://cloud.linode.com/)
2. Navigate to **Object Storage** → **Access Keys**
3. Click **Create Access Key**
4. Label it: `akamai-techdocs-mcp-telemetry`
5. **Limit bucket access** → Select: `skills-db-access-keys` (read/write)
6. Click **Submit**
7. **Copy both keys immediately** (secret key is shown only once!)

### 2. Add Secrets to GitHub Repository

1. Go to your repository: https://github.com/samkarande/akamai-techdocs-mcp
2. Click **Settings** (top navigation)
3. In the left sidebar: **Secrets and variables** → **Actions**
4. Click **New repository secret**

**Add first secret:**
- Name: `LINODE_OBJECT_ACCESS_KEY`
- Value: *paste your access key* (looks like `ABCDEFGHIJKLMNOPQR12`)
- Click **Add secret**

**Add second secret:**
- Name: `LINODE_OBJECT_SECRET_KEY`
- Value: *paste your secret key* (looks like a long random string)
- Click **Add secret**

### 3. Update GitHub Actions Workflows

The workflows (`build-index.yml` and `release.yml`) need to expose these secrets as environment variables.

**For `build-index.yml`**, add this to the build step:

```yaml
- name: Build index from sources.yaml
  env:
    LINODE_OBJECT_ACCESS_KEY: ${{ secrets.LINODE_OBJECT_ACCESS_KEY }}
    LINODE_OBJECT_SECRET_KEY: ${{ secrets.LINODE_OBJECT_SECRET_KEY }}
  run: uv run python -m crawler.build_index --verbose
```

**For `release.yml`**, add this to the build step:

```yaml
- name: Build index from sources.yaml
  env:
    LINODE_OBJECT_ACCESS_KEY: ${{ secrets.LINODE_OBJECT_ACCESS_KEY }}
    LINODE_OBJECT_SECRET_KEY: ${{ secrets.LINODE_OBJECT_SECRET_KEY }}
  run: uv run python -m crawler.build_index --verbose
```

This ensures the telemetry module can access the credentials during CI builds.

### 4. Verify Setup

After adding the secrets and updating workflows:

1. Trigger a workflow run (push a commit or manual dispatch)
2. Check the workflow logs — telemetry should silently send events
3. Verify telemetry files appear in Object Storage:
   ```bash
   # List today's telemetry events
   s3cmd ls s3://skills-db-access-keys/telemetry/events/$(date +%Y-%m-%d)/
   ```

## Security Best Practices

✅ **Good:**
- Secrets are encrypted at rest in GitHub
- Only accessible to Actions workflows
- Never logged in workflow output
- Scoped to one bucket (read/write on `skills-db-access-keys` only)

❌ **Don't:**
- Don't commit access keys to the repository
- Don't echo secrets in workflow logs (GitHub auto-redacts, but still)
- Don't use full-access keys (always scope to specific bucket)

## Telemetry Data Location

Events are written to:
```
s3://skills-db-access-keys/telemetry/events/YYYY-MM-DD/{hash}.json
```

Example:
```
s3://skills-db-access-keys/telemetry/events/2026-07-30/a3f7c8e91234.json
```

## Troubleshooting

### Telemetry not appearing in Object Storage?

1. **Check GitHub Actions logs** for errors
2. **Verify secrets are set** (Settings → Secrets and variables → Actions)
3. **Test credentials locally**:
   ```bash
   export LINODE_OBJECT_ACCESS_KEY="your-key"
   export LINODE_OBJECT_SECRET_KEY="your-secret"
   python -c "from akamai_techdocs_mcp.telemetry import track; track('test', {})"
   ```
4. **Check bucket permissions** — access key must have write permission

### How to rotate access keys?

1. Create a new access key in Linode Cloud Manager
2. Update GitHub secrets with new values
3. Test with a workflow run
4. Delete the old access key from Linode

## User Privacy

**Important:** User installs (via `uvx`, `uv tool install`) **never** send telemetry because:
- Secrets are only in GitHub Actions environment
- User machines don't have `LINODE_OBJECT_ACCESS_KEY` set
- Telemetry module no-ops when credentials are missing

This design ensures zero privacy risk for end users.

## Questions?

Open an issue at [github.com/samkarande/akamai-techdocs-mcp/issues](https://github.com/samkarande/akamai-techdocs-mcp/issues)
