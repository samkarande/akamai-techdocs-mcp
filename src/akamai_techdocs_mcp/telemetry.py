"""Privacy-safe telemetry for akamai-techdocs-mcp.

Tracks usage metrics to help understand how the MCP server is being used
and improve the service. All telemetry is:
- Always-on (no opt-in required) with strict no-PII guarantees
- Anonymized: user_id is SHA256(username@hostname)[:16]
- Minimal: only aggregated metrics, no query text or URLs
- Non-blocking: failures never affect the MCP server

Events are written to Linode Object Storage as individual JSON files
for later aggregation and analysis.

Environment variables:
- AKAMAI_MCP_TELEMETRY_DISABLE=1  Completely disable telemetry
- LINODE_OBJECT_ACCESS_KEY        Object Storage access key (CI only)
- LINODE_OBJECT_SECRET_KEY        Object Storage secret key (CI only)
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
import uuid
from datetime import date, datetime
from typing import Any

_session_id: str | None = None
_session_start: float | None = None
_telemetry_disabled = os.getenv("AKAMAI_MCP_TELEMETRY_DISABLE") == "1"


def get_session_id() -> str:
    """Return ephemeral session ID (fresh UUID per server start)."""
    global _session_id
    if not _session_id:
        _session_id = str(uuid.uuid4())
    return _session_id


def get_user_id() -> str:
    """Return stable anonymous user ID: SHA256(username@hostname)[:16]."""
    user = os.getenv("USER") or os.getenv("USERNAME") or "unknown"
    host = platform.node() or "unknown"
    return hashlib.sha256(f"{user}@{host}".encode()).hexdigest()[:16]


def get_install_method() -> str:
    """Detect how the MCP server was installed."""
    argv0 = sys.argv[0] if sys.argv else ""
    if "uvx" in argv0 or "uvx" in sys.executable:
        return "uvx"
    elif "site-packages" in sys.executable or ".whl" in sys.executable:
        return "wheel"
    else:
        return "git"


def get_mcp_client() -> str:
    """Attempt to detect which MCP client is running this server."""
    # Check parent process name (rough heuristic)
    try:
        import psutil

        parent = psutil.Process().parent()
        if parent:
            name = parent.name().lower()
            if "claude" in name:
                if "code" in name:
                    return "claude-code"
                return "claude-desktop"
            elif "cursor" in name:
                return "cursor"
    except Exception:
        pass
    return "unknown"


def _get_index_metadata() -> dict[str, Any]:
    """Read metadata from the current index.sqlite (if available)."""
    try:
        from akamai_techdocs_mcp.index import resolve_index_path
        import sqlite3

        index_path = resolve_index_path()
        if not index_path:
            return {}

        conn = sqlite3.connect(index_path)
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())

        # Get counts
        url_count = conn.execute("SELECT COUNT(*) FROM urls").fetchone()[0]
        chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        source_count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]

        conn.close()

        return {
            "index_version": meta.get("built_at", "unknown"),
            "index_schema_version": int(meta.get("schema_version", 0)),
            "manifest_version": meta.get("manifest_version", "unknown"),
            "indexed_url_count": url_count,
            "indexed_chunk_count": chunk_count,
            "indexed_source_count": source_count,
        }
    except Exception:
        return {}


def track(event_type: str, properties: dict[str, Any] | None = None) -> None:
    """Track a telemetry event.

    Args:
        event_type: Type of event (e.g., "server_start", "tool_call", "index_update")
        properties: Event-specific properties (must not contain PII)

    Returns:
        None. Failures are silently ignored.
    """
    if _telemetry_disabled:
        return

    global _session_start
    if _session_start is None:
        _session_start = time.time()

    try:
        from akamai_techdocs_mcp import __version__

        event = {
            # Core identifiers (anonymized)
            "session_id": get_session_id(),
            "user_id": get_user_id(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type,
            # Platform metadata
            "platform": platform.system().lower(),
            "python_version": platform.python_version(),
            "install_method": get_install_method(),
            "mcp_client": get_mcp_client(),
            # Version tracking
            "server_version": __version__,
            **_get_index_metadata(),
            # Session metrics
            "session_uptime_seconds": int(time.time() - _session_start),
            # Event-specific properties
            **(properties or {}),
        }

        # Write to Linode Object Storage
        _write_to_object_storage(event)

    except Exception:
        # Never fail the MCP server due to telemetry
        pass


def _write_to_object_storage(event: dict[str, Any]) -> None:
    """Write event to Linode Object Storage as individual JSON file.

    Uses fan-out pattern: telemetry/events/YYYY-MM-DD/{event_hash}.json
    This avoids S3's lack of native append and makes later aggregation easy.
    """
    access_key = os.getenv("LINODE_OBJECT_ACCESS_KEY")
    secret_key = os.getenv("LINODE_OBJECT_SECRET_KEY")

    # Only send telemetry if credentials are available (CI builds/releases)
    # User installs won't have these and telemetry will be a no-op
    if not access_key or not secret_key:
        return

    try:
        from akamai_techdocs_mcp.s3_simple import put_object

        # Object Storage details
        endpoint = "us-iad-18.linodeobjects.com"
        bucket = "skills-db-telemetry"

        # Generate unique event ID (hash of event content)
        event_json = json.dumps(event, sort_keys=True)
        event_hash = hashlib.sha256(event_json.encode()).hexdigest()[:12]

        # S3 key: telemetry/events/YYYY-MM-DD/{hash}.json
        today = date.today().isoformat()
        key = f"telemetry/events/{today}/{event_hash}.json"

        # Upload to Object Storage with AWS SigV4 authentication
        put_object(
            endpoint=endpoint,
            bucket=bucket,
            key=key,
            body=event_json.encode("utf-8"),
            access_key=access_key,
            secret_key=secret_key,
            region="us-iad-1",
        )

    except Exception:
        # Silent fail - never break the MCP server
        pass
