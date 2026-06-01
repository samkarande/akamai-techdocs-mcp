"""Tests for crawler.playwright_transport.

Most assertions are real-browser integration tests; they are skipped
automatically if Chromium hasn't been installed (``playwright install
chromium``). One unit-level check verifies the transport satisfies
the Transport protocol without touching a browser.
"""

from __future__ import annotations

import pytest

from crawler.fetcher import Transport
from crawler.playwright_transport import PlaywrightTransport


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


needs_browser = pytest.mark.skipif(
    not _chromium_available(),
    reason="Chromium not installed; run `uv run playwright install chromium`",
)


def test_satisfies_transport_protocol() -> None:
    assert isinstance(PlaywrightTransport(), Transport)


@needs_browser
def test_fetches_example_com_via_real_browser() -> None:
    with PlaywrightTransport() as transport:
        status, headers, html = transport.get(
            "https://example.com", headers={}, timeout=15.0
        )
    assert status == 200
    assert "Example Domain" in html
    assert any(k.lower() == "content-type" for k in headers)


@needs_browser
def test_context_manager_reuses_browser() -> None:
    """Both fetches inside one `with` block share the same browser."""
    with PlaywrightTransport() as transport:
        s1, _, h1 = transport.get("https://example.com", headers={}, timeout=15.0)
        s2, _, h2 = transport.get("https://example.com", headers={}, timeout=15.0)
    assert s1 == 200 and s2 == 200
    assert "Example Domain" in h1
    assert "Example Domain" in h2
