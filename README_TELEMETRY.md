# 🎉 Telemetry Setup Complete!

Your MCP server now has **always-on, privacy-safe telemetry** to track usage metrics and help improve the service.

---

## 📋 Quick Reference

### GitHub Secrets (Action Required!)

**Add these two secrets to enable telemetry:**

1. Go to: https://github.com/samkarande/akamai-techdocs-mcp/settings/secrets/actions
2. Click "New repository secret"
3. Add:
   - `LINODE_OBJECT_ACCESS_KEY` — Your Object Storage access key
   - `LINODE_OBJECT_SECRET_KEY` — Your Object Storage secret key

**Detailed instructions**: See `docs/GITHUB_SECRETS_SETUP.md`

---

## 🔒 Privacy Guarantees

### ✅ Safe (We collect this)
- Anonymous user ID (SHA256 hash: `d4e56f789abc`)
- Platform (darwin/linux/win32)
- Tool usage: which tools, how often
- Query metadata: length, filters — **NOT the query text**
- Session metrics: uptime, tool counts

### ❌ Never Collected (Zero PII)
- Search queries or URLs
- Document content
- Usernames, IPs, hostnames (unhashed)
- Any personally identifiable information

### 🏡 User Privacy
- **User installs** (uvx/wheel) → **No telemetry** (no credentials = no network calls)
- **CI builds** (GitHub Actions) → Telemetry sent to Object Storage

**Full privacy policy**: See `docs/TELEMETRY.md`

---

## 📦 What Was Implemented

### Core Modules
- **`src/akamai_techdocs_mcp/telemetry.py`** — Telemetry tracking
- **`src/akamai_techdocs_mcp/s3_simple.py`** — AWS SigV4 signer for Object Storage

### Instrumented Code
- **`src/akamai_techdocs_mcp/server.py`** — Tracks `server_start` and tool calls
- **`src/akamai_techdocs_mcp/updater.py`** — Tracks index updates

### CI Integration
- **`.github/workflows/build-index.yml`** — Passes secrets to crawler
- **`.github/workflows/release.yml`** — Passes secrets to release builds

### Documentation
- **`docs/TELEMETRY.md`** — User-facing privacy policy
- **`docs/GITHUB_SECRETS_SETUP.md`** — Setup guide for maintainers
- **`SETUP_INSTRUCTIONS.md`** — Step-by-step quickstart
- **`TELEMETRY_SETUP_COMPLETE.md`** — Technical implementation summary
- **`test_telemetry.py`** — Local testing script

---

## 🚀 Quick Start (3 Steps)

### 1. Add GitHub Secrets
```
Go to: https://github.com/samkarande/akamai-techdocs-mcp/settings/secrets/actions
Add: LINODE_OBJECT_ACCESS_KEY
Add: LINODE_OBJECT_SECRET_KEY
```

### 2. Trigger a Test Build
```bash
gh workflow run build-index.yml
# Or push a commit
```

### 3. Verify Telemetry
```bash
# Check Object Storage for today's events
s3cmd ls s3://skills-db-telemetry/telemetry/events/$(date +%Y-%m-%d)/
```

---

## 📊 Object Storage Details

- **Bucket**: `skills-db-telemetry`
- **Endpoint**: `us-iad-18.linodeobjects.com`
- **Region**: `us-iad-1`
- **Path**: `telemetry/events/YYYY-MM-DD/{hash}.json`

---

## 🧪 Testing Locally

```bash
# Export credentials (don't commit these!)
export LINODE_OBJECT_ACCESS_KEY="your-access-key"
export LINODE_OBJECT_SECRET_KEY="your-secret-key"

# Run test script
python test_telemetry.py
# Output: ✓ Event sent!

# Or run the MCP server (sends server_start event)
uv run akamai-techdocs-mcp
```

---

## 📈 Metrics You Can Track

### Daily Active Users
```bash
jq -r .user_id telemetry/events/2026-07-30/*.json | sort -u | wc -l
```

### Tool Usage
```bash
jq -r '.tool' telemetry/events/2026-07-30/*.json | sort | uniq -c | sort -rn
```

### Platform Distribution
```bash
jq -r '.platform' telemetry/events/2026-07-30/*.json | sort | uniq -c
```

### Search Success Rate
```bash
jq -r 'select(.tool=="search_docs") | .has_results' \
  telemetry/events/2026-07-30/*.json | \
  awk '{if($1=="true") yes++; total++} END {print yes/total*100 "%"}'
```

---

## 🛠️ Troubleshooting

### No telemetry files appearing?

**Check secrets:**
```bash
gh secret list
# Should show: LINODE_OBJECT_ACCESS_KEY, LINODE_OBJECT_SECRET_KEY
```

**Check workflow logs:**
```bash
gh run list --workflow=build-index.yml --limit=1
gh run view <run-id> --log
```

**Test credentials locally:**
```bash
python test_telemetry.py
```

### Invalid credentials?
1. Regenerate keys in Linode Cloud Manager
2. Update GitHub secrets
3. Verify bucket permissions: `skills-db-telemetry` (read/write)

---

## 🚫 Disabling Telemetry

### For all users
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

### For CI only
```bash
gh secret remove LINODE_OBJECT_ACCESS_KEY
gh secret remove LINODE_OBJECT_SECRET_KEY
```

---

## 📚 Documentation Index

| Document | Purpose |
|----------|---------|
| **`SETUP_INSTRUCTIONS.md`** | 👈 **Start here!** Step-by-step setup |
| **`docs/TELEMETRY.md`** | Privacy policy (user-facing) |
| **`docs/GITHUB_SECRETS_SETUP.md`** | Detailed secrets setup |
| **`TELEMETRY_SETUP_COMPLETE.md`** | Technical implementation details |
| **`README_TELEMETRY.md`** | This file (quick reference) |

---

## 🎯 Next Steps

- [ ] Add GitHub Secrets (see Step 1 above)
- [ ] Trigger test build
- [ ] Verify telemetry in Object Storage
- [ ] (Future) Set up weekly aggregation script
- [ ] (Future) Build analytics dashboard

---

## 💬 Questions?

- **Privacy?** → `docs/TELEMETRY.md`
- **Setup?** → `SETUP_INSTRUCTIONS.md`
- **Technical?** → `TELEMETRY_SETUP_COMPLETE.md`
- **Issues?** → https://github.com/samkarande/akamai-techdocs-mcp/issues

---

**Implementation Status**: ✅ Complete  
**Telemetry Status**: ⏸️ Waiting for GitHub Secrets
