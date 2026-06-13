"""Build a fresh index.sqlite from sources.yaml.

Entry point for the CI weekly-rebuild workflow. Reads the manifest,
picks a transport per source (HttpxTransport for plain sites,
PlaywrightTransport for WAF-protected ones), fetches each URL,
parses + chunks the content, and writes everything into a single
SQLite file that the server downloads from GitHub Releases.

Usage:
    uv run python -m crawler.build_index \
        --manifest sources.yaml \
        --output dist/index.sqlite \
        [--verbose]
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from crawler.chunker import chunk_markdown
from crawler.fetcher import (
    FetchOutcome,
    FetchRequest,
    HttpxTransport,
    Transport,
    fetch,
)
from crawler.manifest import Source, load_manifest
from crawler.openapi import parse_openapi
from crawler.parser import parse_html
from crawler.writer import IndexWriter

# Map source domain -> transport class. Domains not listed here fall
# back to HttpxTransport.
WAF_DOMAINS = {"techdocs.akamai.com"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build_index", description=__doc__)
    parser.add_argument("--manifest", default="sources.yaml", type=Path)
    parser.add_argument("--output", default="dist/index.sqlite", type=Path)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    manifest_sha = hashlib.sha256(args.manifest.read_bytes()).hexdigest()

    counts: dict[str, int] = {"ok": 0, "unchanged": 0, "not_found": 0, "error": 0}

    with IndexWriter(args.output) as writer:
        writer.set_meta("schema_version", "1")
        writer.set_meta("manifest_version", manifest.manifest_version)
        writer.set_meta("manifest_sha", manifest_sha)
        writer.set_meta("built_at", datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
        writer.set_meta("crawler_version", _package_version())

        for source in manifest.sources:
            writer.add_source(source)
            transport = _select_transport(source.domain)
            print(f"[{source.id}] {len(source.urls)} URLs via {type(transport).__name__}")
            with _safe_transport(transport) as t:
                if t is None:
                    # Transport unavailable (e.g. Playwright missing); mark
                    # all URLs as ERROR and continue.
                    for url in source.urls:
                        _record_unavailable(writer, source, url, counts)
                    continue
                for url in source.urls:
                    _crawl_one(writer, source, url, t, counts, verbose=args.verbose)

    total = sum(counts.values())
    print(
        f"\nFinished. ok={counts['ok']} unchanged={counts['unchanged']} "
        f"not_found={counts['not_found']} error={counts['error']} total={total}"
    )
    print(f"Wrote {args.output} ({args.output.stat().st_size:,} bytes)")
    # Non-zero exit only if literally nothing was indexed.
    return 0 if counts["ok"] > 0 else 2


def _package_version() -> str:
    try:
        return version("akamai-techdocs-mcp")
    except PackageNotFoundError:
        return "0.0.0+dev"


def _select_transport(domain: str) -> Transport:
    if domain in WAF_DOMAINS:
        try:
            from crawler.playwright_transport import PlaywrightTransport
        except ImportError:
            print(f"  warning: playwright not installed; falling back to httpx for {domain}")
            return HttpxTransport()
        return PlaywrightTransport()
    return HttpxTransport()


@contextlib.contextmanager
def _safe_transport(transport: Transport):  # type: ignore[no-untyped-def]
    """Yield the transport entered as a context manager; yield None on failure."""
    try:
        with transport as t:  # type: ignore[attr-defined]
            yield t
    except Exception as exc:  # noqa: BLE001
        print(f"  warning: transport setup failed ({type(exc).__name__}: {exc})")
        yield None


def _crawl_one(
    writer: IndexWriter,
    source: Source,
    url: str,
    transport: Transport,
    counts: dict[str, int],
    *,
    verbose: bool,
) -> None:
    result = fetch(FetchRequest(url=url), transport=transport)
    counts[result.outcome.value] = counts.get(result.outcome.value, 0) + 1

    if result.outcome is FetchOutcome.OK and result.html is not None:
        # OpenAPI specs are JSON, not HTML; try that renderer first and
        # fall back to HTML parsing when the body isn't a spec.
        parsed = parse_openapi(result.html) or parse_html(result.html)
        chunks = chunk_markdown(parsed.markdown, page_title=parsed.title)
    else:
        parsed = None
        chunks = []

    writer.add_page(source.id, result, parsed, chunks)

    if verbose or result.outcome is FetchOutcome.ERROR:
        n_chunks = len(chunks)
        print(f"  {result.outcome.value:10s} chunks={n_chunks:<3d} {url}")


def _record_unavailable(
    writer: IndexWriter, source: Source, url: str, counts: dict[str, int]
) -> None:
    from crawler.fetcher import FetchResult

    counts["error"] = counts.get("error", 0) + 1
    writer.add_page(
        source.id,
        FetchResult(
            url=url,
            outcome=FetchOutcome.ERROR,
            http_status=0,
            html=None,
            etag=None,
            last_modified=None,
            content_hash=None,
            crawled_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            error="transport unavailable",
        ),
        parsed=None,
        chunks=[],
    )


if __name__ == "__main__":
    sys.exit(main())
