"""Best-effort index updater that runs on server startup.

Polls the GitHub Releases of the repo for the latest ``index-YYYY-MM-DD``
tag, downloads ``index.sqlite`` plus its ``index.sqlite.sha256`` when a
newer release exists, verifies the checksum, validates the schema, and
atomically installs the file into the user's cache dir.

Design principles:

- **Never break startup.** Every failure path (offline, no releases,
  rate-limited, sha mismatch, schema mismatch, disk error) is logged
  to stderr and swallowed. The MCP server continues with whatever
  index is currently available.
- **Tag is the version**, lexicographically comparable (the release
  workflow tags with ISO-8601 dates).
- **Atomic swap.** Download to ``index.sqlite.new``, validate, then
  ``Path.replace`` over ``index.sqlite``. A reader holding the old
  file (the server itself) keeps reading the old inode until restart.
- **Concurrent-safe.** ``fcntl.flock`` on ``updater.lock`` serializes
  competing MCP server processes; losers skip instead of blocking
  startup.
- **Honors ``AKAMAI_MCP_OFFLINE=1``** to skip the update entirely.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from akamai_techdocs_mcp.index import (
    EXPECTED_SCHEMA_VERSION,
    USER_CACHE_DIR,
)

DEFAULT_REPO = "samkarande/akamai-techdocs-mcp"
INDEX_ASSET = "index.sqlite"
SHA_ASSET = "index.sqlite.sha256"
GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 5.0

ENV_OFFLINE = "AKAMAI_MCP_OFFLINE"
ENV_REPO = "AKAMAI_MCP_RELEASES_REPO"


class UpdateError(RuntimeError):
    """Raised internally when an update step fails; never escapes maybe_update."""


@dataclass(frozen=True, slots=True)
class _ReleaseInfo:
    tag: str
    published_at: str
    index_url: str
    sha256_url: str


@dataclass(frozen=True, slots=True)
class _LocalIndexMeta:
    tag: str
    sha256: str
    installed_at: str
    published_at: str = ""


def maybe_update(
    *,
    cache_dir: Path | None = None,
    repo: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    client: httpx.Client | None = None,
) -> Path | None:
    """Best-effort: pull a newer index from GitHub Releases into the cache.

    Returns the path to the cached index if one exists after this call
    (whether or not we updated). Returns None if no cache exists and
    nothing could be downloaded — caller can then fall through to the
    bundled index.

    Never raises. Logs each failure path to stderr.
    """
    cache_dir = cache_dir or USER_CACHE_DIR
    cache_index = cache_dir / INDEX_ASSET
    cache_meta = cache_dir / "index-meta.json"

    if os.environ.get(ENV_OFFLINE):
        return cache_index if cache_index.exists() else None

    target_repo = repo or os.environ.get(ENV_REPO, DEFAULT_REPO)

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _warn(f"cannot create cache dir {cache_dir}: {exc}")
        return None

    lockfile = cache_dir / "updater.lock"
    try:
        # Silence httpx/httpcore INFO logs — they would appear on stderr and
        # confuse MCP clients that capture the server process's stderr output.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        with _try_lock(lockfile) as locked:
            if not locked:
                # Another process is updating; let it finish.
                return cache_index if cache_index.exists() else None

            owned_client = client is None
            client = client or httpx.Client(
                timeout=timeout,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "akamai-techdocs-mcp-updater/0.1",
                },
                follow_redirects=True,
            )
            try:
                release = _fetch_latest_release(client, target_repo, timeout)
                if release is None:
                    return cache_index if cache_index.exists() else None

                local = _read_local_meta(cache_meta)
                # Compare by release publish time (ISO-8601, lexically
                # sortable), not the tag string: tag schemes can be mixed
                # (e.g. "v0.1.3" vs "index-2026-06-21") and string-compare
                # would wrongly treat a newer dated index as older.
                if (
                    local is not None
                    and cache_index.exists()
                    and local.published_at
                    and release.published_at
                    and local.published_at >= release.published_at
                ):
                    return cache_index

                _install_release(client, release, cache_dir, cache_meta, timeout)
            finally:
                if owned_client:
                    client.close()
        return cache_index if cache_index.exists() else None

    except UpdateError as exc:
        _warn(str(exc))
        return cache_index if cache_index.exists() else None
    except Exception as exc:  # noqa: BLE001 — last-resort safety net
        _warn(f"unexpected updater error: {type(exc).__name__}: {exc}")
        return cache_index if cache_index.exists() else None


# ----- internals -----

def _fetch_latest_release(
    client: httpx.Client, repo: str, timeout: float
) -> _ReleaseInfo | None:
    url = f"{GITHUB_API}/repos/{repo}/releases/latest"
    resp = client.get(url, timeout=timeout)
    if resp.status_code == 404:
        # Repo has no releases yet, or repo doesn't exist publicly.
        return None
    if resp.status_code == 403:
        # Rate-limited or auth required; skip silently.
        _warn(f"GitHub rate-limited or forbidden ({resp.status_code}); skipping update")
        return None
    if resp.status_code >= 400:
        raise UpdateError(f"releases/latest returned HTTP {resp.status_code}")

    data: dict[str, Any] = resp.json()
    tag = data.get("tag_name")
    if not isinstance(tag, str) or not tag:
        raise UpdateError("releases/latest response missing tag_name")

    assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
    if INDEX_ASSET not in assets or SHA_ASSET not in assets:
        raise UpdateError(
            f"release {tag} is missing {INDEX_ASSET} and/or {SHA_ASSET} assets"
        )
    return _ReleaseInfo(
        tag=tag,
        published_at=str(data.get("published_at") or ""),
        index_url=assets[INDEX_ASSET],
        sha256_url=assets[SHA_ASSET],
    )


def _install_release(
    client: httpx.Client,
    release: _ReleaseInfo,
    cache_dir: Path,
    cache_meta: Path,
    timeout: float,
) -> None:
    # Fetch the (small) checksum file first — fail fast if missing.
    sha_resp = client.get(release.sha256_url, timeout=timeout)
    if sha_resp.status_code >= 400:
        raise UpdateError(f"sha256 fetch failed: HTTP {sha_resp.status_code}")
    expected_sha = _parse_sha_line(sha_resp.text)

    # Download the index file to a temp location alongside the final.
    tmp = cache_dir / f"{INDEX_ASSET}.new"
    idx_resp = client.get(release.index_url, timeout=timeout)
    if idx_resp.status_code >= 400:
        raise UpdateError(f"index fetch failed: HTTP {idx_resp.status_code}")
    tmp.write_bytes(idx_resp.content)

    try:
        actual_sha = _sha256_of(tmp)
        if actual_sha != expected_sha:
            raise UpdateError(
                f"sha256 mismatch for {release.tag}: "
                f"expected {expected_sha[:16]}…, got {actual_sha[:16]}…"
            )
        _validate_downloaded_schema(tmp)
        tmp.replace(cache_dir / INDEX_ASSET)
        _write_local_meta(
            cache_meta,
            _LocalIndexMeta(
                tag=release.tag,
                sha256=expected_sha,
                installed_at=_now_iso(),
                published_at=release.published_at,
            ),
        )
    finally:
        # If anything above raised, leave the cache untouched and clean up.
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _parse_sha_line(text: str) -> str:
    """Pull the hex digest out of a `sha256sum` style line."""
    first = text.strip().splitlines()[0] if text.strip() else ""
    digest = first.split()[0] if first else ""
    if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest.lower()):
        raise UpdateError(f"malformed sha256 line: {first!r}")
    return digest.lower()


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_downloaded_schema(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()
    except sqlite3.DatabaseError as exc:
        raise UpdateError(f"downloaded index is not valid SQLite: {exc}") from exc
    finally:
        conn.close()
    if row is None:
        raise UpdateError("downloaded index missing schema_version")
    try:
        v = int(row[0])
    except (TypeError, ValueError) as exc:
        raise UpdateError(f"downloaded index has non-integer schema_version: {row[0]!r}") from exc
    if v != EXPECTED_SCHEMA_VERSION:
        raise UpdateError(
            f"downloaded index schema_version {v} != server's expected "
            f"{EXPECTED_SCHEMA_VERSION}; not installing"
        )


def _read_local_meta(path: Path) -> _LocalIndexMeta | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return _LocalIndexMeta(
            tag=str(data["tag"]),
            sha256=str(data["sha256"]),
            installed_at=str(data["installed_at"]),
            # Optional: absent in caches written by older versions. An
            # empty value forces one re-download to migrate the metadata.
            published_at=str(data.get("published_at", "")),
        )
    except (OSError, ValueError, KeyError):
        return None


def _write_local_meta(path: Path, meta: _LocalIndexMeta) -> None:
    path.write_text(
        json.dumps(
            {
                "tag": meta.tag,
                "sha256": meta.sha256,
                "installed_at": meta.installed_at,
                "published_at": meta.published_at,
            },
            indent=2,
        )
    )


@contextmanager
def _try_lock(lockfile: Path):
    """Yield True if we got the lock, False if another process holds it."""
    lockfile.parent.mkdir(parents=True, exist_ok=True)
    with open(lockfile, "wb") as f:
        got = False
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            got = True
        except BlockingIOError:
            pass
        try:
            yield got
        finally:
            if got:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _warn(msg: str) -> None:
    print(f"akamai-techdocs-mcp updater: {msg}", file=sys.stderr)
