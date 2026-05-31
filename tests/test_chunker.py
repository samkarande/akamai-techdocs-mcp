"""Tests for crawler.chunker."""

from __future__ import annotations

from textwrap import dedent

from crawler.chunker import chunk_markdown


def test_empty_markdown_yields_no_chunks() -> None:
    assert chunk_markdown("") == []
    assert chunk_markdown("   \n\n") == []


def test_single_heading_one_chunk() -> None:
    md = dedent(
        """\
        # Quickstart

        Install the aka CLI.
        """
    )
    chunks = chunk_markdown(md, page_title="Quickstart Page")
    assert len(chunks) == 1
    c = chunks[0]
    assert c.ordinal == 0
    assert c.heading_path == "Quickstart Page > Quickstart"
    assert "# Quickstart" in c.content_md
    assert "Install the aka CLI" in c.content_md


def test_splits_on_h2_boundaries() -> None:
    md = dedent(
        """\
        # Tutorial

        Intro paragraph.

        ## Step 1

        Do thing one.

        ## Step 2

        Do thing two.
        """
    )
    chunks = chunk_markdown(md, page_title="Tutorial Page")
    assert len(chunks) == 3
    paths = [c.heading_path for c in chunks]
    assert paths == [
        "Tutorial Page > Tutorial",
        "Tutorial Page > Tutorial > Step 1",
        "Tutorial Page > Tutorial > Step 2",
    ]
    assert "Intro paragraph" in chunks[0].content_md
    assert "Do thing one" in chunks[1].content_md
    assert "Do thing two" in chunks[2].content_md


def test_breadcrumb_pops_on_sibling_h2() -> None:
    md = dedent(
        """\
        # Top

        ## Section A

        ### Sub A1

        Body of sub a1.

        ## Section B

        Body of section B.
        """
    )
    chunks = chunk_markdown(md, page_title="P")
    paths = [c.heading_path for c in chunks]
    # Section B is a sibling of A, so it does not nest under "Sub A1".
    assert paths == [
        "P > Top",
        "P > Top > Section A",
        "P > Top > Section A > Sub A1",
        "P > Top > Section B",
    ]


def test_respects_max_heading_level_three() -> None:
    md = dedent(
        """\
        # Top

        ## H2

        ### H3

        #### H4

        Inner content under H4 stays with H3.
        """
    )
    chunks = chunk_markdown(md, page_title="P")
    # H4 should NOT create a new chunk
    paths = [c.heading_path for c in chunks]
    assert paths == ["P > Top", "P > Top > H2", "P > Top > H2 > H3"]
    last = chunks[-1]
    assert "#### H4" in last.content_md
    assert "stays with H3" in last.content_md


def test_does_not_split_inside_code_fence() -> None:
    md = dedent(
        """\
        # Title

        Setup:

        ```python
        # this is a Python comment, not a heading
        ## also not a heading
        def f():
            pass
        ```

        After the code.
        """
    )
    chunks = chunk_markdown(md, page_title="P")
    assert len(chunks) == 1
    assert "this is a Python comment" in chunks[0].content_md
    assert chunks[0].code_block_count == 1


def test_counts_multiple_code_blocks() -> None:
    md = dedent(
        """\
        # Title

        ```bash
        aka login
        ```

        Some prose.

        ```bash
        aka apps list
        ```
        """
    )
    chunks = chunk_markdown(md, page_title="P")
    assert len(chunks) == 1
    assert chunks[0].code_block_count == 2


def test_leading_content_before_first_heading_kept() -> None:
    md = dedent(
        """\
        Some prose before any heading.

        # Then the heading

        And content.
        """
    )
    chunks = chunk_markdown(md, page_title="Welcome")
    assert len(chunks) == 2
    # Pre-heading content lives under the page title alone.
    assert chunks[0].heading_path == "Welcome"
    assert "Some prose" in chunks[0].content_md
    assert chunks[1].heading_path == "Welcome > Then the heading"


def test_ordinals_are_sequential() -> None:
    md = dedent(
        """\
        # A

        ## B

        ## C

        ## D
        """
    )
    chunks = chunk_markdown(md, page_title="P")
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_char_count_matches_content_md() -> None:
    md = "# Title\n\nBody.\n"
    chunks = chunk_markdown(md, page_title="P")
    assert chunks[0].char_count == len(chunks[0].content_md)


def test_no_page_title_uses_first_heading_only() -> None:
    md = dedent(
        """\
        # H1

        ## H2

        Body.
        """
    )
    chunks = chunk_markdown(md)  # no page_title
    paths = [c.heading_path for c in chunks]
    assert paths == ["H1", "H1 > H2"]
