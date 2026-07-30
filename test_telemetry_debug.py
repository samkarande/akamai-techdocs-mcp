#!/usr/bin/env python3
"""Debug telemetry upload to Linode Object Storage."""

import os
import sys
import traceback

def main():
    # Check credentials
    access_key = os.getenv("LINODE_OBJECT_ACCESS_KEY")
    secret_key = os.getenv("LINODE_OBJECT_SECRET_KEY")

    if not access_key:
        print("❌ LINODE_OBJECT_ACCESS_KEY not set", file=sys.stderr)
        sys.exit(1)

    if not secret_key:
        print("❌ LINODE_OBJECT_SECRET_KEY not set", file=sys.stderr)
        sys.exit(1)

    print(f"✓ Access key: {access_key[:10]}...")
    print(f"✓ Secret key: {secret_key[:10]}...")

    # Test telemetry with verbose error handling
    try:
        from akamai_techdocs_mcp.telemetry import track, _write_to_object_storage
        import json
        from datetime import datetime

        print("\nCreating test event...")
        event = {
            "session_id": "test-session",
            "user_id": "test-user",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": "test_event",
            "test": True,
            "message": "Debug test",
        }

        print(f"Event: {json.dumps(event, indent=2)}")
        print("\nAttempting upload to Object Storage...")

        _write_to_object_storage(event)

        print("✓ Upload succeeded!")

    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
