"""Tests for akamai_techdocs_mcp.updater.

Uses httpx.MockTransport to fake the GitHub Releases API + the asset
download endpoints. No real network. Builds a tiny valid SQLite index
on the fly so the schema validation path can be exercised.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from akamai_techdocs_mcp import updater
from akamai_techdocs_mcp.updater import (
    DEFAULT_REPO,
    ENV_OFFLINE,
    INDEX_ASSET,
    SHA_ASSET,
    maybe_update,
)
from tests.test_index import _build_tiny_index

NEW_TAG = "index-2026-06-08"
OLD_TAG = "index-2026-05-25"

INDEX_URL = f"https://example.invalid/releases/{NEW_TAG}/{INDEX_ASSET}"
SHA_URL = f"https://example.invalid/releases/{NEW_TAG}/{SHA_ASSET}"
RELEASE_API_URL = (
    f"{updater.GITHUB_API}/repos/{DEFAULT_REPO}/releases/latest"
)


def _release_json(tag: str = NEW_TAG, *, with_index: bool = True, with_sha: bool = True) -> dict:
    assets = []
    if with_index:
        assets.append({"name": INDEX_ASSET, "browser_download_url": INDEX_URL})
    if with_sha:
        assets.append({"name": SHA_ASSET, "browser_download_url": SHA_URL})
    return {"tag_name": tag, "assets": assets}


def _make_index_bytes(tmp_path: Path) -> bytes:
    p = tmp_path / "src_index.sqlite"
    _build_tiny_index(p)
    return p.read_bytes()


def _sha_text(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest() + "  index.sqlite\n"


def _client_with_routes(routes: dict[str, httpx.Response]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in routes or str(request.url) in routes:
            return routes.get(str(request.url)) or routes[request.url.path]
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_OFFLINE, raising=False)


def test_offline_env_skips_update(
    cache_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_OFFLINE, "1")
    result = maybe_update(cache_dir=cache_dir)
    assert result is None
    assert not (cache_dir / INDEX_ASSET).exists()


def test_no_releases_yet_returns_none_when_cache_empty(
    cache_dir: Path,
) -> None:
    client = _client_with_routes({RELEASE_API_URL: httpx.Response(404)})
    assert maybe_update(cache_dir=cache_dir, client=client) is None


def test_no_releases_yet_returns_cache_when_present(
    cache_dir: Path, tmp_path: Path
) -> None:
    cache_dir.mkdir(parents=True)
    (cache_dir / INDEX_ASSET).write_bytes(_make_index_bytes(tmp_path))
    client = _client_with_routes({RELEASE_API_URL: httpx.Response(404)})
    assert maybe_update(cache_dir=cache_dir, client=client) == cache_dir / INDEX_ASSET


def test_downloads_new_release_when_cache_missing(
    cache_dir: Path, tmp_path: Path
) -> None:
    index_bytes = _make_index_bytes(tmp_path)
    client = _client_with_routes(
        {
            RELEASE_API_URL: httpx.Response(200, json=_release_json()),
            INDEX_URL: httpx.Response(200, content=index_bytes),
            SHA_URL: httpx.Response(200, text=_sha_text(index_bytes)),
        }
    )
    out = maybe_update(cache_dir=cache_dir, client=client)
    assert out == cache_dir / INDEX_ASSET
    assert out is not None and out.exists()
    meta = json.loads((cache_dir / "index-meta.json").read_text())
    assert meta["tag"] == NEW_TAG
    assert meta["sha256"] == hashlib.sha256(index_bytes).hexdigest()


def test_skips_when_local_tag_is_already_newer_or_equal(
    cache_dir: Path, tmp_path: Path
) -> None:
    cache_dir.mkdir(parents=True)
    index_bytes = _make_index_bytes(tmp_path)
    (cache_dir / INDEX_ASSET).write_bytes(index_bytes)
    (cache_dir / "index-meta.json").write_text(
        json.dumps(
            {
                "tag": NEW_TAG,  # exactly equal to what's "available"
                "sha256": hashlib.sha256(index_bytes).hexdigest(),
                "installed_at": "2026-06-08T00:00:00Z",
            }
        )
    )
    download_counter = {"index": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == RELEASE_API_URL:
            return httpx.Response(200, json=_release_json())
        if str(request.url) == INDEX_URL:
            download_counter["index"] += 1
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = maybe_update(cache_dir=cache_dir, client=client)
    assert result == cache_dir / INDEX_ASSET
    # Did NOT re-download the index.
    assert download_counter["index"] == 0


def test_upgrades_when_local_tag_older(cache_dir: Path, tmp_path: Path) -> None:
    cache_dir.mkdir(parents=True)
    old_bytes = b"stale-not-a-real-sqlite"
    (cache_dir / INDEX_ASSET).write_bytes(old_bytes)
    (cache_dir / "index-meta.json").write_text(
        json.dumps(
            {
                "tag": OLD_TAG,
                "sha256": hashlib.sha256(old_bytes).hexdigest(),
                "installed_at": "2026-05-25T00:00:00Z",
            }
        )
    )
    new_bytes = _make_index_bytes(tmp_path)
    client = _client_with_routes(
        {
            RELEASE_API_URL: httpx.Response(200, json=_release_json(NEW_TAG)),
            INDEX_URL: httpx.Response(200, content=new_bytes),
            SHA_URL: httpx.Response(200, text=_sha_text(new_bytes)),
        }
    )
    out = maybe_update(cache_dir=cache_dir, client=client)
    assert out is not None
    assert out.read_bytes() == new_bytes  # swapped


def test_sha_mismatch_rejects_download(
    cache_dir: Path, tmp_path: Path
) -> None:
    cache_dir.mkdir(parents=True)
    existing = b"existing"
    (cache_dir / INDEX_ASSET).write_bytes(existing)
    new_bytes = _make_index_bytes(tmp_path)
    wrong_sha = "0" * 64 + "  index.sqlite\n"
    client = _client_with_routes(
        {
            RELEASE_API_URL: httpx.Response(200, json=_release_json()),
            INDEX_URL: httpx.Response(200, content=new_bytes),
            SHA_URL: httpx.Response(200, text=wrong_sha),
        }
    )
    out = maybe_update(cache_dir=cache_dir, client=client)
    # Update was rejected; existing cache file is intact.
    assert out == cache_dir / INDEX_ASSET
    assert (cache_dir / INDEX_ASSET).read_bytes() == existing
    # No partial file left behind.
    assert not (cache_dir / f"{INDEX_ASSET}.new").exists()


def test_invalid_sqlite_download_is_rejected(
    cache_dir: Path,
) -> None:
    junk = b"this is not a sqlite db"
    sha_text = hashlib.sha256(junk).hexdigest() + "  index.sqlite\n"
    client = _client_with_routes(
        {
            RELEASE_API_URL: httpx.Response(200, json=_release_json()),
            INDEX_URL: httpx.Response(200, content=junk),
            SHA_URL: httpx.Response(200, text=sha_text),
        }
    )
    out = maybe_update(cache_dir=cache_dir, client=client)
    assert out is None  # nothing cached, nothing installed
    assert not (cache_dir / INDEX_ASSET).exists()


def test_release_missing_assets_is_treated_as_no_update(
    cache_dir: Path, tmp_path: Path
) -> None:
    cache_dir.mkdir(parents=True)
    existing = _make_index_bytes(tmp_path)
    (cache_dir / INDEX_ASSET).write_bytes(existing)
    client = _client_with_routes(
        {
            RELEASE_API_URL: httpx.Response(
                200, json=_release_json(with_sha=False)
            )
        }
    )
    out = maybe_update(cache_dir=cache_dir, client=client)
    assert out == cache_dir / INDEX_ASSET
    assert (cache_dir / INDEX_ASSET).read_bytes() == existing


def test_github_rate_limited_falls_back_to_cache(
    cache_dir: Path, tmp_path: Path
) -> None:
    cache_dir.mkdir(parents=True)
    existing = _make_index_bytes(tmp_path)
    (cache_dir / INDEX_ASSET).write_bytes(existing)
    client = _client_with_routes({RELEASE_API_URL: httpx.Response(403)})
    out = maybe_update(cache_dir=cache_dir, client=client)
    assert out == cache_dir / INDEX_ASSET


def test_returns_cache_when_lock_held_by_other_process(
    cache_dir: Path, tmp_path: Path
) -> None:
    """Simulates a concurrent updater process holding the lockfile.

    Acquires fcntl.LOCK_EX on the lockfile from this test, then runs
    maybe_update. It should skip (not block) and return the cache path.
    """
    import fcntl

    cache_dir.mkdir(parents=True)
    existing = _make_index_bytes(tmp_path)
    (cache_dir / INDEX_ASSET).write_bytes(existing)
    lockfile = cache_dir / "updater.lock"
    with open(lockfile, "wb") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX)
        # No client provided — if the updater attempted any network call
        # under the lock, we'd see real DNS errors. The lock skip should
        # prevent that path.
        out = maybe_update(cache_dir=cache_dir)
    assert out == cache_dir / INDEX_ASSET
    assert (cache_dir / INDEX_ASSET).read_bytes() == existing


def test_repo_override_env(
    cache_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom_repo = "someone-else/their-fork"
    monkeypatch.setenv("AKAMAI_MCP_RELEASES_REPO", custom_repo)
    expected_url = f"{updater.GITHUB_API}/repos/{custom_repo}/releases/latest"
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    maybe_update(cache_dir=cache_dir, client=client)
    assert any(u == expected_url for u in seen), seen
