"""Playwright-backed Transport for sites behind aggressive bot protection.

The Akamai techdocs site blocks plain HTTPS clients (TLS fingerprint /
WAF), returning HTTP 403 even with realistic browser headers. A real
headless browser passes those checks.

PlaywrightTransport is a context manager: enter once at the start of a
crawl, run many .get() calls against the shared browser, exit at the
end. Using it without a context manager still works (one browser per
get() call) but is significantly slower.

This module imports Playwright lazily so the rest of the crawler can
be unit-tested without the playwright package being installed.
"""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:  # pragma: no cover
    from playwright.sync_api import Browser, Playwright

WaitUntil = Literal["load", "domcontentloaded", "networkidle", "commit"]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_WAIT_UNTIL: WaitUntil = "networkidle"


class PlaywrightTransport:
    """Headless-Chromium Transport. Slow startup but bypasses Akamai Bot Manager."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        wait_until: WaitUntil = DEFAULT_WAIT_UNTIL,
    ) -> None:
        self._user_agent: str = user_agent
        self._wait_until: WaitUntil = wait_until
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    def __enter__(self) -> PlaywrightTransport:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def get(
        self, url: str, headers: dict[str, str], timeout: float
    ) -> tuple[int, dict[str, str], str]:
        if self._browser is None:
            # Fallback: one-shot launch. Slow but correct for callers
            # who forget the context manager.
            with self as ephemeral:
                return ephemeral._fetch(url, headers, timeout)
        return self._fetch(url, headers, timeout)

    def _fetch(
        self, url: str, headers: dict[str, str], timeout: float
    ) -> tuple[int, dict[str, str], str]:
        assert self._browser is not None
        context = self._browser.new_context(
            user_agent=self._user_agent,
            extra_http_headers=headers,
        )
        try:
            page = context.new_page()
            response = page.goto(url, wait_until=self._wait_until, timeout=int(timeout * 1000))
            if response is None:
                return 0, {}, ""
            status = response.status
            resp_headers = response.all_headers()
            html = page.content()
            return status, resp_headers, html
        finally:
            context.close()
