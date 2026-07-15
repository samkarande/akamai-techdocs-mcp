"""Fetch a URL and return its HTML + metadata for incremental crawls.

Designed around two transports:

- HttpxTransport: plain HTTPS via httpx for sites that don't WAF
  generic clients (e.g. spinframework.dev). Implemented here.
- PlaywrightTransport: headless browser for sites behind Akamai
  Bot Manager (e.g. techdocs.akamai.com). Stubbed; wired in a
  follow-up commit once Chromium is available.

The fetcher does conditional GETs using the caller-supplied ETag and
Last-Modified values, returning ``FetchOutcome.UNCHANGED`` on 304 so
the crawler can skip re-parsing. Network errors and HTTP 5xx are
retried with exponential backoff up to ``max_retries`` times.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

import httpx

DEFAULT_USER_AGENT = "akamai-techdocs-mcp-crawler/0.1"
TECHDOCS_USER_AGENT = "ClaudeBot"  # Allowlisted by techdocs.akamai.com WAF
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 3


class FetchOutcome(StrEnum):
    OK = "ok"                  # 200, content fetched
    UNCHANGED = "unchanged"    # 304, conditional GET satisfied
    NOT_FOUND = "not_found"    # 404 / 410, page removed
    ERROR = "error"            # any other failure after retries


@dataclass(frozen=True, slots=True)
class FetchRequest:
    url: str
    prior_etag: str | None = None
    prior_last_modified: str | None = None


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    outcome: FetchOutcome
    http_status: int
    html: str | None
    etag: str | None
    last_modified: str | None
    content_hash: str | None
    crawled_at: str            # ISO-8601 UTC
    error: str | None = None


@runtime_checkable
class Transport(Protocol):
    def get(
        self, url: str, headers: dict[str, str], timeout: float
    ) -> tuple[int, dict[str, str], str]:  # status, response_headers, body
        ...


class HttpxTransport:
    """Plain HTTPS via httpx. Suitable for sites without bot protection.

    Implements no-op context-manager methods so the crawler driver can
    use ``with transport:`` uniformly regardless of which transport it
    selected for a given source.
    """

    def __init__(self, *, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self._user_agent = user_agent

    def __enter__(self) -> HttpxTransport:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def get(
        self, url: str, headers: dict[str, str], timeout: float
    ) -> tuple[int, dict[str, str], str]:
        merged = {
            "User-Agent": self._user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
            **headers,
        }
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            resp = client.get(url, headers=merged)
            return resp.status_code, dict(resp.headers), resp.text


class CurlTransport:
    """Fetch via the system ``curl`` binary.

    Same Transport contract as HttpxTransport, selected per-source via
    ``transport: curl`` in the manifest. Useful where we want to fetch
    exactly as a manual ``curl`` would (e.g. raw.githubusercontent.com
    OpenAPI specs). Follows redirects, sends the caller's conditional
    headers (so 304 still works), and decodes the body as UTF-8.

    Implements no-op context-manager methods so the crawler driver can
    use ``with transport:`` uniformly.
    """

    def __init__(
        self, *, user_agent: str = DEFAULT_USER_AGENT, curl_path: str = "curl"
    ) -> None:
        self._user_agent = user_agent
        self._curl_path = curl_path

    def __enter__(self) -> CurlTransport:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def get(
        self, url: str, headers: dict[str, str], timeout: float
    ) -> tuple[int, dict[str, str], str]:
        with tempfile.TemporaryDirectory() as tmp:
            header_path = os.path.join(tmp, "headers")
            body_path = os.path.join(tmp, "body")
            cmd = [
                self._curl_path,
                "-sS",                       # quiet, but still print errors
                "-L",                        # follow redirects
                "--compressed",
                "--max-time", str(int(timeout)),
                "-A", self._user_agent,
                "-D", header_path,           # dump response headers
                "-o", body_path,             # write body to file
                "-w", "%{http_code}",        # print final status to stdout
            ]
            for key, value in headers.items():
                cmd += ["-H", f"{key}: {value}"]
            cmd.append(url)

            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout + 10
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"curl exited {proc.returncode}: {proc.stderr.strip()}"
                )
            try:
                status = int(proc.stdout.strip().split()[-1])
            except (ValueError, IndexError):
                status = 0
            resp_headers = _parse_curl_headers(header_path)
            with open(body_path, "rb") as fh:
                body = fh.read().decode("utf-8", errors="replace")
            return status, resp_headers, body


def _parse_curl_headers(path: str) -> dict[str, str]:
    """Parse curl's ``-D`` dump, returning the final response's headers.

    With ``-L`` the dump holds one block per redirect hop separated by a
    blank line; the last non-empty block is the headers we want.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return {}
    blocks = [b for b in text.replace("\r\n", "\n").split("\n\n") if b.strip()]
    if not blocks:
        return {}
    headers: dict[str, str] = {}
    for line in blocks[-1].splitlines():
        if ":" in line and not line.upper().startswith("HTTP/"):
            key, _, value = line.partition(":")
            headers[key.strip()] = value.strip()
    return headers


def fetch(
    request: FetchRequest,
    *,
    transport: Transport,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
) -> FetchResult:
    """Fetch one URL with conditional GET semantics + retry on 5xx."""
    conditional_headers = _conditional_headers(request)

    last_error: str | None = None
    for attempt in range(max_retries):
        try:
            status, resp_headers, body = transport.get(
                request.url, conditional_headers, timeout_seconds
            )
        except Exception as exc:  # noqa: BLE001 — transport errors vary
            last_error = f"{type(exc).__name__}: {exc}"
            sleep(_backoff(attempt))
            continue

        # Normalize header keys to lowercase for lookups.
        h = {k.lower(): v for k, v in resp_headers.items()}

        if status == 304:
            return FetchResult(
                url=request.url,
                outcome=FetchOutcome.UNCHANGED,
                http_status=304,
                html=None,
                etag=h.get("etag", request.prior_etag),
                last_modified=h.get("last-modified", request.prior_last_modified),
                content_hash=None,
                crawled_at=_now_iso(),
            )

        if status in (404, 410):
            return FetchResult(
                url=request.url,
                outcome=FetchOutcome.NOT_FOUND,
                http_status=status,
                html=None,
                etag=None,
                last_modified=None,
                content_hash=None,
                crawled_at=_now_iso(),
            )

        if 200 <= status < 300:
            content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
            return FetchResult(
                url=request.url,
                outcome=FetchOutcome.OK,
                http_status=status,
                html=body,
                etag=h.get("etag"),
                last_modified=h.get("last-modified"),
                content_hash=content_hash,
                crawled_at=_now_iso(),
            )

        # Retry-worthy: 429 and 5xx. Others (3xx without follow, 4xx) → error.
        if status == 429 or 500 <= status < 600:
            last_error = f"http_status={status}"
            sleep(_backoff(attempt))
            continue

        last_error = f"http_status={status}"
        break

    return FetchResult(
        url=request.url,
        outcome=FetchOutcome.ERROR,
        http_status=0,
        html=None,
        etag=None,
        last_modified=None,
        content_hash=None,
        crawled_at=_now_iso(),
        error=last_error or "exhausted retries",
    )


def _conditional_headers(request: FetchRequest) -> dict[str, str]:
    h: dict[str, str] = {}
    if request.prior_etag:
        h["If-None-Match"] = request.prior_etag
    if request.prior_last_modified:
        h["If-Modified-Since"] = request.prior_last_modified
    return h


def _backoff(attempt: int) -> float:
    return min(1.0 * (2 ** attempt), 8.0)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
