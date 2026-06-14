"""Tests for crawler.fetcher.

Uses a fake Transport (no real network) to validate conditional-GET
semantics, 404 tombstoning, retry-on-5xx, and exhaustion behavior.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from crawler.fetcher import (
    CurlTransport,
    FetchOutcome,
    FetchRequest,
    HttpxTransport,
    Transport,
    _parse_curl_headers,
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


# --- CurlTransport ----------------------------------------------------------


def _fake_curl_run(status_line: str, header_lines: str, body: bytes):
    """Build a subprocess.run replacement that writes curl's -D/-o files."""

    def run(cmd, capture_output, text, timeout):  # noqa: ANN001, ANN202
        header_path = cmd[cmd.index("-D") + 1]
        body_path = cmd[cmd.index("-o") + 1]
        with open(header_path, "w", encoding="utf-8") as fh:
            fh.write(f"{status_line}\r\n{header_lines}\r\n\r\n")
        with open(body_path, "wb") as fh:
            fh.write(body)
        code = status_line.split()[-1]

        class _Proc:
            returncode = 0
            stdout = code
            stderr = ""

        return _Proc()

    return run


def test_curl_transport_returns_status_headers_body(monkeypatch) -> None:
    monkeypatch.setattr(
        "crawler.fetcher.subprocess.run",
        _fake_curl_run("HTTP/2 200", 'content-type: application/json\r\netag: "abc"',
                       b'{"ok": true}'),
    )
    with CurlTransport() as t:
        status, headers, body = t.get(
            "https://raw.githubusercontent.com/x/openapi.json",
            {"If-None-Match": '"abc"'},
            30.0,
        )
    assert status == 200
    assert headers["content-type"] == "application/json"
    assert headers["etag"] == '"abc"'
    assert body == '{"ok": true}'


def test_curl_transport_passes_conditional_headers(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def run(cmd, capture_output, text, timeout):  # noqa: ANN001, ANN202
        seen["cmd"] = cmd
        header_path = cmd[cmd.index("-D") + 1]
        body_path = cmd[cmd.index("-o") + 1]
        with open(header_path, "w", encoding="utf-8") as fh:
            fh.write("HTTP/2 304\r\n\r\n")
        with open(body_path, "wb") as fh:
            fh.write(b"")

        class _Proc:
            returncode = 0
            stdout = "304"
            stderr = ""

        return _Proc()

    monkeypatch.setattr("crawler.fetcher.subprocess.run", run)
    with CurlTransport() as t:
        status, _, _ = t.get("https://example.com/x", {"If-None-Match": '"v1"'}, 30.0)
    assert status == 304
    cmd = seen["cmd"]
    assert "-H" in cmd
    assert 'If-None-Match: "v1"' in cmd


def test_curl_transport_raises_on_nonzero_exit(monkeypatch) -> None:
    def run(cmd, capture_output, text, timeout):  # noqa: ANN001, ANN202
        class _Proc:
            returncode = 6
            stdout = "000"
            stderr = "Could not resolve host"

        return _Proc()

    monkeypatch.setattr("crawler.fetcher.subprocess.run", run)
    with CurlTransport() as t, pytest.raises(RuntimeError, match="curl exited 6"):
        t.get("https://nope.invalid/x", {}, 5.0)


def test_parse_curl_headers_keeps_last_redirect_block(tmp_path) -> None:
    dump = tmp_path / "h"
    dump.write_text(
        "HTTP/2 301\r\nlocation: https://example.com/final\r\n\r\n"
        "HTTP/2 200\r\ncontent-type: text/plain\r\netag: \"z\"\r\n\r\n",
        encoding="utf-8",
    )
    headers = _parse_curl_headers(str(dump))
    assert headers == {"content-type": "text/plain", "etag": '"z"'}
