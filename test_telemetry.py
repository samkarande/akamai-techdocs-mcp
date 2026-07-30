#!/usr/bin/env python3
"""Test telemetry upload to Linode Object Storage.

Usage:
    export LINODE_OBJECT_ACCESS_KEY="your-key"
    export LINODE_OBJECT_SECRET_KEY="your-secret"
    python test_telemetry.py
"""

import os
import sys

def main():
    # Check credentials
    if not os.getenv("LINODE_OBJECT_ACCESS_KEY"):
        print("❌ LINODE_OBJECT_ACCESS_KEY not set", file=sys.stderr)
        print("Set it with: export LINODE_OBJECT_ACCESS_KEY='your-key'", file=sys.stderr)
        sys.exit(1)

    if not os.getenv("LINODE_OBJECT_SECRET_KEY"):
        print("❌ LINODE_OBJECT_SECRET_KEY not set", file=sys.stderr)
        print("Set it with: export LINODE_OBJECT_SECRET_KEY='your-secret'", file=sys.stderr)
        sys.exit(1)

    print("✓ Credentials found")

    # Test telemetry
    from akamai_techdocs_mcp.telemetry import track

    print("Sending test event...")
    track("test_event", {
        "test": True,
        "message": "Telemetry test from test_telemetry.py",
    })

    print("✓ Event sent!")
    print("\nTo verify upload, check Object Storage:")
    print("  s3cmd ls s3://skills-db-access-keys/telemetry/events/$(date +%Y-%m-%d)/")
    print("  # Or via Linode Cloud Manager")


if __name__ == "__main__":
    main()
