"""Tests for crawler.manifest.

Validates the manifest loader handles the real sources.yaml at repo
root and rejects malformed / unsafe manifests.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from crawler.manifest import (
    Manifest,
    ManifestError,
    Source,
    load_manifest,
    load_manifest_from_text,
)

REPO_ROOT = Path(__file__).parent.parent
SOURCES_YAML = REPO_ROOT / "sources.yaml"


def test_loads_real_sources_yaml() -> None:
    m = load_manifest(SOURCES_YAML)
    assert isinstance(m, Manifest)
    assert m.schema_version == 1
    assert "raw.githubusercontent.com" in m.allowed_domains
    assert "spinframework.dev" in m.allowed_domains
    # The WAF-blocked techdocs source/domain was retired in favor of
    # GitHub README sources.
    assert "techdocs.akamai.com" not in m.allowed_domains
    source_ids = {s.id for s in m.sources}
    assert source_ids == {
        "spin-framework",
        "linode-api-spec",
        "keda",
        "karpenter",
        "terraform-modules",
        "linode-github",
    }
    gh = next(s for s in m.sources if s.id == "linode-github")
    assert gh.domain == "raw.githubusercontent.com"
    assert gh.transport == "curl"
    assert len(gh.urls) >= 30  # full linode org README set
    assert len(set(gh.urls)) == len(gh.urls)  # no duplicates
    assert all(u.startswith("https://raw.githubusercontent.com/linode/") for u in gh.urls)


def test_returns_immutable_dataclasses() -> None:
    m = load_manifest(SOURCES_YAML)
    with pytest.raises((AttributeError, TypeError)):
        m.schema_version = 2  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        m.sources[0].id = "evil"  # type: ignore[misc]


def test_minimal_valid_manifest() -> None:
    text = dedent(
        """
        schema_version: 1
        manifest_version: "0.1.0"
        allowed_domains:
          - example.com
        sources:
          - id: ex
            product: Example
            version: latest
            domain: example.com
            urls:
              - https://example.com/a
        """
    )
    m = load_manifest_from_text(text)
    assert m.manifest_version == "0.1.0"
    assert len(m.sources) == 1
    assert isinstance(m.sources[0], Source)
    assert m.sources[0].transport == ""  # default: auto


def _manifest_with_transport(value: str) -> str:
    return dedent(
        f"""
        schema_version: 1
        manifest_version: "0.1.0"
        allowed_domains:
          - example.com
        sources:
          - id: ex
            product: Example
            version: latest
            domain: example.com
            transport: {value}
            urls:
              - https://example.com/a
        """
    )


def test_parses_valid_transport_override() -> None:
    m = load_manifest_from_text(_manifest_with_transport("curl"))
    assert m.sources[0].transport == "curl"


def test_rejects_unknown_transport() -> None:
    with pytest.raises(ManifestError, match="transport"):
        load_manifest_from_text(_manifest_with_transport("wget"))


def test_rejects_missing_schema_version() -> None:
    text = dedent(
        """
        manifest_version: "0.1.0"
        allowed_domains: [example.com]
        sources: []
        """
    )
    with pytest.raises(ManifestError, match="schema_version"):
        load_manifest_from_text(text)


def test_rejects_unsupported_schema_version() -> None:
    text = dedent(
        """
        schema_version: 99
        manifest_version: "0.1.0"
        allowed_domains: [example.com]
        sources: []
        """
    )
    with pytest.raises(ManifestError, match="unsupported schema_version"):
        load_manifest_from_text(text)


def test_rejects_url_outside_allowed_domains() -> None:
    text = dedent(
        """
        schema_version: 1
        manifest_version: "0.1.0"
        allowed_domains:
          - example.com
        sources:
          - id: ex
            product: Example
            version: latest
            domain: evil.com
            urls:
              - https://evil.com/a
        """
    )
    with pytest.raises(ManifestError, match="not in allowed_domains"):
        load_manifest_from_text(text)


def test_rejects_url_not_matching_source_domain() -> None:
    text = dedent(
        """
        schema_version: 1
        manifest_version: "0.1.0"
        allowed_domains:
          - example.com
          - other.com
        sources:
          - id: ex
            product: Example
            version: latest
            domain: example.com
            urls:
              - https://other.com/a
        """
    )
    with pytest.raises(ManifestError, match="does not match source domain"):
        load_manifest_from_text(text)


def test_rejects_non_https_url() -> None:
    text = dedent(
        """
        schema_version: 1
        manifest_version: "0.1.0"
        allowed_domains:
          - example.com
        sources:
          - id: ex
            product: Example
            version: latest
            domain: example.com
            urls:
              - ftp://example.com/a
        """
    )
    with pytest.raises(ManifestError, match="must be http"):
        load_manifest_from_text(text)


def test_rejects_duplicate_source_ids() -> None:
    text = dedent(
        """
        schema_version: 1
        manifest_version: "0.1.0"
        allowed_domains: [example.com]
        sources:
          - id: ex
            product: A
            version: latest
            domain: example.com
            urls: [https://example.com/a]
          - id: ex
            product: B
            version: latest
            domain: example.com
            urls: [https://example.com/b]
        """
    )
    with pytest.raises(ManifestError, match="duplicate source id"):
        load_manifest_from_text(text)


def test_rejects_source_with_no_urls() -> None:
    text = dedent(
        """
        schema_version: 1
        manifest_version: "0.1.0"
        allowed_domains: [example.com]
        sources:
          - id: ex
            product: Example
            version: latest
            domain: example.com
            urls: []
        """
    )
    with pytest.raises(ManifestError, match="no URLs"):
        load_manifest_from_text(text)


def test_rejects_bad_allowed_domain_entry() -> None:
    text = dedent(
        """
        schema_version: 1
        manifest_version: "0.1.0"
        allowed_domains:
          - https://example.com
        sources: []
        """
    )
    with pytest.raises(ManifestError, match="bare hostname"):
        load_manifest_from_text(text)
