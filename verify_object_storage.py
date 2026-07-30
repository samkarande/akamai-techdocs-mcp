#!/usr/bin/env python3
"""Verify Object Storage credentials and check for telemetry data."""

import os
import sys

def main():
    access_key = os.getenv("LINODE_OBJECT_ACCESS_KEY")
    secret_key = os.getenv("LINODE_OBJECT_SECRET_KEY")

    if not access_key or not secret_key:
        print("❌ Object Storage credentials not set")
        print("\nTo test locally:")
        print("  export LINODE_OBJECT_ACCESS_KEY='your-key'")
        print("  export LINODE_OBJECT_SECRET_KEY='your-secret'")
        print("  python verify_object_storage.py")
        sys.exit(1)

    print("✓ Credentials found")
    print(f"  Access Key: {access_key[:10]}...")

    # Test connectivity and list telemetry events
    try:
        import httpx
        from src.akamai_techdocs_mcp.s3_simple import sign_s3_request
        from datetime import date

        endpoint = "us-iad-18.linodeobjects.com"
        bucket = "skills-db-telemetry"
        today = date.today().isoformat()
        prefix = f"telemetry/events/{today}/"

        # List objects with this prefix
        url = f"https://{endpoint}/{bucket}/?prefix={prefix}"

        headers = sign_s3_request(
            method="GET",
            endpoint=endpoint,
            bucket=bucket,
            key="",  # Empty for bucket list
            body=b"",
            access_key=access_key,
            secret_key=secret_key,
            region="us-iad-1",
        )

        print(f"\nChecking bucket: {bucket}")
        print(f"Prefix: {prefix}")
        print(f"URL: {url}")

        response = httpx.get(url, headers=headers, timeout=10.0)
        response.raise_for_status()

        # Parse XML response
        from xml.etree import ElementTree as ET
        root = ET.fromstring(response.content)

        # Count objects
        ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        objects = root.findall(".//s3:Contents", ns)

        if not objects:
            # Try without namespace
            objects = root.findall(".//Contents")

        print(f"\n✓ Found {len(objects)} telemetry events for {today}")

        if objects:
            print("\nRecent events:")
            for obj in objects[:5]:
                key_elem = obj.find(".//s3:Key", ns) or obj.find("Key")
                size_elem = obj.find(".//s3:Size", ns) or obj.find("Size")
                modified_elem = obj.find(".//s3:LastModified", ns) or obj.find("LastModified")

                if key_elem is not None:
                    print(f"  - {key_elem.text}")
                    if size_elem is not None:
                        print(f"    Size: {size_elem.text} bytes")
                    if modified_elem is not None:
                        print(f"    Modified: {modified_elem.text}")
        else:
            print("\n⚠️  No telemetry events found for today")
            print("   This could mean:")
            print("   1. No CI builds have run with telemetry enabled")
            print("   2. Telemetry upload is failing silently")
            print("   3. The bucket/prefix is incorrect")

    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
