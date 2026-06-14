"""Load and validate sources.yaml.

The manifest declares which URLs the CI crawler should index. This
module parses the YAML, validates structure and security invariants
(URLs must be HTTPS and inside the allow-listed domains), and returns
immutable dataclasses for downstream use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

SUPPORTED_SCHEMA_VERSIONS = {1}

# Optional per-source fetch transport override. Empty string = auto
# (domain-based selection in the crawler).
VALID_TRANSPORTS = {"httpx", "curl", "playwright"}


class ManifestError(ValueError):
    """Raised when sources.yaml is malformed or violates an invariant."""


@dataclass(frozen=True, slots=True)
class Source:
    id: str
    product: str
    version: str
    domain: str
    urls: tuple[str, ...]
    description: str = ""
    follow_links: bool = False
    transport: str = ""


@dataclass(frozen=True, slots=True)
class Manifest:
    schema_version: int
    manifest_version: str
    allowed_domains: tuple[str, ...]
    sources: tuple[Source, ...] = field(default_factory=tuple)


def load_manifest(path: Path | str) -> Manifest:
    p = Path(path)
    if not p.exists():
        raise ManifestError(f"manifest not found: {p}")
    return load_manifest_from_text(p.read_text(encoding="utf-8"))


def load_manifest_from_text(text: str) -> Manifest:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ManifestError(f"invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ManifestError("manifest root must be a mapping")

    schema_version = _require(raw, "schema_version", int)
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ManifestError(
            f"unsupported schema_version {schema_version!r}; "
            f"this build understands {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )

    manifest_version = _require(raw, "manifest_version", str)

    allowed_domains_raw = _require(raw, "allowed_domains", list)
    allowed_domains = tuple(_validate_domain_list(allowed_domains_raw))

    sources_raw = raw.get("sources", []) or []
    if not isinstance(sources_raw, list):
        raise ManifestError("sources must be a list")

    sources = tuple(_parse_source(s, allowed_domains) for s in sources_raw)
    _check_unique_ids(sources)

    return Manifest(
        schema_version=schema_version,
        manifest_version=manifest_version,
        allowed_domains=allowed_domains,
        sources=sources,
    )


def _require(d: dict[str, Any], key: str, typ: type) -> Any:
    if key not in d:
        raise ManifestError(f"missing required field: {key!r}")
    value = d[key]
    if not isinstance(value, typ):
        raise ManifestError(
            f"field {key!r} must be {typ.__name__}, got {type(value).__name__}"
        )
    return value


def _validate_domain_list(raw: list[Any]) -> list[str]:
    out: list[str] = []
    for d in raw:
        if not isinstance(d, str) or not d:
            raise ManifestError(f"allowed_domains entry must be non-empty string: {d!r}")
        if "/" in d or ":" in d:
            raise ManifestError(
                f"allowed_domains entry must be a bare hostname (no scheme or path): {d!r}"
            )
        out.append(d.lower())
    return out


def _parse_source(raw: Any, allowed_domains: tuple[str, ...]) -> Source:
    if not isinstance(raw, dict):
        raise ManifestError("each source must be a mapping")
    src_id = _require(raw, "id", str)
    product = _require(raw, "product", str)
    version = _require(raw, "version", str)
    domain = _require(raw, "domain", str).lower()
    if domain not in allowed_domains:
        raise ManifestError(
            f"source {src_id!r} domain {domain!r} is not in allowed_domains {list(allowed_domains)}"
        )
    description = raw.get("description") or ""
    follow_links = bool(raw.get("follow_links", False))
    transport = str(raw.get("transport") or "").strip().lower()
    if transport and transport not in VALID_TRANSPORTS:
        raise ManifestError(
            f"source {src_id!r} transport {transport!r} is not one of "
            f"{sorted(VALID_TRANSPORTS)}"
        )
    urls_raw = _require(raw, "urls", list)
    urls = tuple(_validate_url(u, domain, src_id) for u in urls_raw)
    if not urls:
        raise ManifestError(f"source {src_id!r} has no URLs")
    return Source(
        id=src_id,
        product=product,
        version=version,
        domain=domain,
        description=description,
        follow_links=follow_links,
        transport=transport,
        urls=urls,
    )


def _validate_url(url: Any, source_domain: str, source_id: str) -> str:
    if not isinstance(url, str):
        raise ManifestError(f"source {source_id!r} URL must be string, got {type(url).__name__}")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ManifestError(f"source {source_id!r} URL must be http(s): {url!r}")
    if not parsed.hostname:
        raise ManifestError(f"source {source_id!r} URL has no hostname: {url!r}")
    host = parsed.hostname.lower()
    if host != source_domain:
        raise ManifestError(
            f"source {source_id!r} URL hostname {host!r} does not match source domain "
            f"{source_domain!r}: {url!r}"
        )
    return url


def _check_unique_ids(sources: tuple[Source, ...]) -> None:
    seen: set[str] = set()
    for s in sources:
        if s.id in seen:
            raise ManifestError(f"duplicate source id: {s.id!r}")
        seen.add(s.id)
