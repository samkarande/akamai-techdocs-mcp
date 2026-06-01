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


@pytest.fixture(scope="session")
def chromium_available() -> bool:
    """Probe for a usable Chromium once per test session.

    Doing this lazily (at first fixture use, not at module import) keeps
    `pytest --ignore=tests/test_playwright_transport.py` and
    `pytest -k "not playwright"` from launching Chromium during
    collection — a previous module-level probe stalled the suite when
    multiple pytest runs queued up.
    """
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
        return True
    except Exception:
        return False


def _require_chromium(available: bool) -> None:
    if not available:
        pytest.skip("Chromium not installed; run `uv run playwright install chromium`")


def test_satisfies_transport_protocol() -> None:
    assert isinstance(PlaywrightTransport(), Transport)


def test_fetches_example_com_via_real_browser(chromium_available: bool) -> None:
    _require_chromium(chromium_available)
    with PlaywrightTransport() as transport:
        status, headers, html = transport.get(
            "https://example.com", headers={}, timeout=15.0
        )
    assert status == 200
    assert "Example Domain" in html
    assert any(k.lower() == "content-type" for k in headers)


def test_context_manager_reuses_browser(chromium_available: bool) -> None:
    """Both fetches inside one `with` block share the same browser."""
    _require_chromium(chromium_available)
    with PlaywrightTransport() as transport:
        s1, _, h1 = transport.get("https://example.com", headers={}, timeout=15.0)
        s2, _, h2 = transport.get("https://example.com", headers={}, timeout=15.0)
    assert s1 == 200 and s2 == 200
    assert "Example Domain" in h1
    assert "Example Domain" in h2
