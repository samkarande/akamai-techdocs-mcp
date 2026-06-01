"""Tests for crawler.fetcher.

Uses a fake Transport (no real network) to validate conditional-GET
semantics, 404 tombstoning, retry-on-5xx, and exhaustion behavior.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from crawler.fetcher import (
    FetchOutcome,
    FetchRequest,
    HttpxTransport,
    Transport,
    fetch,
)


class _FakeTransport:
    """Returns a scripted sequence of responses; records seen headers."""

    def __init__(self, responses: list[tuple[int, dict[str, str], str]]) -> None:
        self._responses: Iterator[tuple[int, dict[str, str], str]] = iter(responses)
        self.seen_headers: list[dict[str, str]] = []

    def get(
        self, url: str, headers: dict[str, str], timeout: float
    ) -> tuple[int, dict[str, str], str]:
        self.seen_headers.append(dict(headers))
        try:
            return next(self._responses)
        except StopIteration as exc:  # pragma: no cover
            raise AssertionError("fetcher made more requests than expected") from exc


class _AlwaysRaises:
    def get(
        self, url: str, headers: dict[str, str], timeout: float
    ) -> tuple[int, dict[str, str], str]:
        raise ConnectionError("boom")


def _no_sleep(_seconds: float) -> None:
    return None


def test_fetcher_satisfies_transport_protocol() -> None:
    assert isinstance(HttpxTransport(), Transport)


def test_fetch_ok_200_returns_html_and_hashes_body() -> None:
    headers = {"ETag": "abc", "Last-Modified": "Mon, 01 Jan 2026 00:00:00 GMT"}
    transport = _FakeTransport([(200, headers, "<html>hi</html>")])
    result = fetch(FetchRequest(url="https://example.com/x"), transport=transport, sleep=_no_sleep)
    assert result.outcome is FetchOutcome.OK
    assert result.http_status == 200
    assert result.html == "<html>hi</html>"
    assert result.etag == "abc"
    assert result.last_modified == "Mon, 01 Jan 2026 00:00:00 GMT"
    assert result.content_hash is not None
    assert len(result.content_hash) == 64  # sha256 hex


def test_fetch_sends_conditional_headers_when_provided() -> None:
    transport = _FakeTransport([(304, {"ETag": "abc"}, "")])
    fetch(
        FetchRequest(
            url="https://example.com/x",
            prior_etag="abc",
            prior_last_modified="Mon, 01 Jan 2026 00:00:00 GMT",
        ),
        transport=transport,
        sleep=_no_sleep,
    )
    sent = transport.seen_headers[0]
    assert sent.get("If-None-Match") == "abc"
    assert sent.get("If-Modified-Since") == "Mon, 01 Jan 2026 00:00:00 GMT"


def test_fetch_304_returns_unchanged_outcome() -> None:
    transport = _FakeTransport([(304, {}, "")])
    result = fetch(
        FetchRequest(url="https://example.com/x", prior_etag="abc"),
        transport=transport,
        sleep=_no_sleep,
    )
    assert result.outcome is FetchOutcome.UNCHANGED
    assert result.html is None
    # Prior etag survives so the caller can keep the same row.
    assert result.etag == "abc"


def test_fetch_404_tombstones() -> None:
    transport = _FakeTransport([(404, {}, "Not Found")])
    result = fetch(
        FetchRequest(url="https://example.com/missing"), transport=transport, sleep=_no_sleep
    )
    assert result.outcome is FetchOutcome.NOT_FOUND
    assert result.http_status == 404
    assert result.html is None


def test_fetch_retries_on_5xx_then_succeeds() -> None:
    transport = _FakeTransport(
        [
            (503, {}, ""),
            (502, {}, ""),
            (200, {"ETag": "z"}, "<html/>"),
        ]
    )
    result = fetch(
        FetchRequest(url="https://example.com/x"),
        transport=transport,
        max_retries=3,
        sleep=_no_sleep,
    )
    assert result.outcome is FetchOutcome.OK
    assert result.html == "<html/>"


def test_fetch_retries_on_429() -> None:
    transport = _FakeTransport([(429, {}, ""), (200, {}, "<html/>")])
    result = fetch(
        FetchRequest(url="https://example.com/x"),
        transport=transport,
        max_retries=2,
        sleep=_no_sleep,
    )
    assert result.outcome is FetchOutcome.OK


def test_fetch_exhausts_retries_returns_error() -> None:
    transport = _FakeTransport([(500, {}, ""), (500, {}, ""), (500, {}, "")])
    result = fetch(
        FetchRequest(url="https://example.com/x"),
        transport=transport,
        max_retries=3,
        sleep=_no_sleep,
    )
    assert result.outcome is FetchOutcome.ERROR
    assert result.error and "500" in result.error


def test_fetch_handles_transport_exceptions() -> None:
    result = fetch(
        FetchRequest(url="https://example.com/x"),
        transport=_AlwaysRaises(),
        max_retries=2,
        sleep=_no_sleep,
    )
    assert result.outcome is FetchOutcome.ERROR
    assert result.error and "ConnectionError" in result.error


def test_non_retryable_4xx_returns_error_without_retry() -> None:
    transport = _FakeTransport([(403, {}, "Forbidden")])
    result = fetch(
        FetchRequest(url="https://example.com/x"),
        transport=transport,
        max_retries=3,
        sleep=_no_sleep,
    )
    assert result.outcome is FetchOutcome.ERROR
    assert result.http_status == 0  # error result, http_status reset
    # Only one request was made — 403 is not retried.
    assert len(transport.seen_headers) == 1


@pytest.mark.parametrize("attempt,expected_min", [(0, 1.0), (1, 2.0), (2, 4.0), (3, 8.0)])
def test_backoff_is_exponential_capped_at_8s(attempt: int, expected_min: float) -> None:
    # Just exercise the backoff function as part of fetch by checking
    # how many sleep calls happen and with which durations.
    sleeps: list[float] = []

    transport = _FakeTransport([(500, {}, "")] * (attempt + 1))
    fetch(
        FetchRequest(url="https://example.com/x"),
        transport=transport,
        max_retries=attempt + 1,
        sleep=lambda s: sleeps.append(s),
    )
    assert sleeps, "expected at least one backoff sleep"
    assert sleeps[-1] == expected_min
