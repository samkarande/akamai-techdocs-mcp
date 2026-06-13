"""Tests for crawler.openapi OpenAPI/Swagger JSON → markdown rendering."""

from __future__ import annotations

import json

from crawler.chunker import chunk_markdown
from crawler.openapi import parse_openapi

_SPEC = {
    "openapi": "3.0.1",
    "info": {
        "title": "Example API",
        "version": "1.2.3",
        "description": "An example.\n\n## Heading inside description\n\nmore <<LB>> text",
    },
    "servers": [{"url": "https://api.example.com/v4"}],
    "components": {
        "schemas": {
            "CreateThing": {
                "type": "object",
                "required": ["label"],
                "properties": {
                    "label": {"type": "string", "description": "The label."},
                    "size": {"type": "integer"},
                },
            }
        }
    },
    "paths": {
        "/things": {
            "post": {
                "operationId": "create-thing",
                "summary": "Create a thing",
                "tags": ["Things"],
                "description": "Creates a thing.",
                "parameters": [
                    {"name": "region", "in": "query", "required": True,
                     "schema": {"type": "string"}, "description": "Target region."}
                ],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/CreateThing"}
                        }
                    }
                },
                "responses": {"200": {"description": "OK"}, "default": {"description": "Error"}},
            }
        }
    },
}


def test_returns_none_for_non_openapi() -> None:
    assert parse_openapi("not json") is None
    assert parse_openapi("<html><body>hi</body></html>") is None
    assert parse_openapi(json.dumps({"foo": "bar"})) is None


def test_title_includes_version() -> None:
    page = parse_openapi(json.dumps(_SPEC))
    assert page is not None
    assert page.title == "Example API (v1.2.3)"


def test_renders_operation_with_method_and_path() -> None:
    page = parse_openapi(json.dumps(_SPEC))
    assert page is not None
    assert "## Things" in page.markdown
    assert "### POST /things — Create a thing" in page.markdown
    assert "`create-thing`" in page.markdown


def test_resolves_request_body_ref_and_required() -> None:
    page = parse_openapi(json.dumps(_SPEC))
    assert page is not None
    # property from the $ref'd schema, flagged required
    assert "`label` `string` (required)" in page.markdown
    assert "`size` `integer`" in page.markdown


def test_renders_parameters_and_responses() -> None:
    page = parse_openapi(json.dumps(_SPEC))
    assert page is not None
    assert "`region` (query) `string` (required)" in page.markdown
    assert "`200`" in page.markdown


def test_strips_readme_tokens_and_inline_headings() -> None:
    page = parse_openapi(json.dumps(_SPEC))
    assert page is not None
    assert "<<LB>>" not in page.markdown
    # A '## Heading inside description' must not survive as a real heading.
    assert "## Heading inside description" not in page.markdown


def test_chunks_one_per_operation_without_doubled_title() -> None:
    page = parse_openapi(json.dumps(_SPEC))
    assert page is not None
    chunks = chunk_markdown(page.markdown, page_title=page.title)
    op_chunks = [c for c in chunks if "POST /things" in c.heading_path]
    assert len(op_chunks) == 1
    path = op_chunks[0].heading_path
    # Page title appears exactly once in the breadcrumb.
    assert path.count("Example API (v1.2.3)") == 1
    assert path == "Example API (v1.2.3) > Things > POST /things — Create a thing"
