"""Minimal AWS Signature Version 4 implementation for S3 PUT operations.

Lightweight alternative to boto3 for uploading telemetry events to
Linode Object Storage. Only supports PUT operations.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from urllib.parse import quote


def _sha256(data: bytes) -> bytes:
    """Return SHA256 hash of data."""
    return hashlib.sha256(data).digest()


def _hmac_sha256(key: bytes, msg: bytes) -> bytes:
    """Return HMAC-SHA256 of message with key."""
    return hmac.new(key, msg, hashlib.sha256).digest()


def _sign(key: bytes, msg: str) -> bytes:
    """Sign message with key using HMAC-SHA256."""
    return _hmac_sha256(key, msg.encode("utf-8"))


def sign_s3_request(
    method: str,
    endpoint: str,
    bucket: str,
    key: str,
    body: bytes,
    access_key: str,
    secret_key: str,
    region: str = "us-iad-1",
) -> dict[str, str]:
    """Generate AWS Signature V4 headers for S3 request.

    Args:
        method: HTTP method (e.g., "PUT")
        endpoint: S3 endpoint (e.g., "us-iad-18.linodeobjects.com")
        bucket: Bucket name
        key: Object key (e.g., "telemetry/events/2026-07-30/abc123.json")
        body: Request body bytes
        access_key: AWS/Linode access key ID
        secret_key: AWS/Linode secret access key
        region: AWS region (default: "us-iad-1")

    Returns:
        Dictionary of headers to add to the HTTP request
    """
    service = "s3"
    now = datetime.utcnow()
    datestamp = now.strftime("%Y%m%d")
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")

    # Canonical request components
    canonical_uri = f"/{bucket}/{quote(key, safe='/')}"
    canonical_querystring = ""
    payload_hash = hashlib.sha256(body).hexdigest()

    canonical_headers = (
        f"host:{endpoint}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "host;x-amz-content-sha256;x-amz-date"

    canonical_request = (
        f"{method}\n"
        f"{canonical_uri}\n"
        f"{canonical_querystring}\n"
        f"{canonical_headers}\n"
        f"{signed_headers}\n"
        f"{payload_hash}"
    )

    # String to sign
    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{datestamp}/{region}/{service}/aws4_request"
    string_to_sign = (
        f"{algorithm}\n"
        f"{amz_date}\n"
        f"{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )

    # Signing key
    k_date = _sign(f"AWS4{secret_key}".encode("utf-8"), datestamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")

    # Signature
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    # Authorization header
    authorization = (
        f"{algorithm} "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    return {
        "Authorization": authorization,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
        "Content-Type": "application/json",
    }


def put_object(
    endpoint: str,
    bucket: str,
    key: str,
    body: bytes,
    access_key: str,
    secret_key: str,
    region: str = "us-iad-1",
) -> None:
    """Upload object to S3-compatible storage.

    Args:
        endpoint: S3 endpoint hostname (e.g., "us-iad-18.linodeobjects.com")
        bucket: Bucket name
        key: Object key
        body: Object content as bytes
        access_key: Access key ID
        secret_key: Secret access key
        region: AWS region

    Raises:
        httpx.HTTPStatusError: If upload fails
    """
    import httpx

    headers = sign_s3_request(
        method="PUT",
        endpoint=endpoint,
        bucket=bucket,
        key=key,
        body=body,
        access_key=access_key,
        secret_key=secret_key,
        region=region,
    )

    url = f"https://{endpoint}/{bucket}/{key}"

    response = httpx.put(url, content=body, headers=headers, timeout=3.0)
    response.raise_for_status()
