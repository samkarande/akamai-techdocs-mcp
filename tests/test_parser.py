"""Tests for crawler.parser HTML → markdown extraction."""

from __future__ import annotations

from textwrap import dedent

from crawler.parser import parse_html


def _wrap(body: str, title: str = "Example Doc") -> str:
    return dedent(
        f"""\
        <!DOCTYPE html>
        <html><head><title>{title}</title></head>
        <body>
        <nav>Sidebar nav that should be dropped</nav>
        <header>Page header that should be dropped</header>
        {body}
        <footer>Footer that should be dropped</footer>
        </body></html>
        """
    )


def test_extracts_main_content_drops_chrome() -> None:
    html = _wrap(
        """
        <main>
          <h1>Quickstart</h1>
          <p>Install the <code>aka</code> CLI.</p>
        </main>
        """
    )
    page = parse_html(html)
    assert page.title == "Quickstart"
    assert "# Quickstart" in page.markdown
    assert "Install the `aka` CLI" in page.markdown
    assert "Sidebar nav" not in page.markdown
    assert "Footer" not in page.markdown
    assert "Page header" not in page.markdown


def test_preserves_heading_hierarchy() -> None:
    html = _wrap(
        """
        <main>
          <h1>Title</h1>
          <h2>Step 1</h2>
          <p>Do the thing.</p>
          <h2>Step 2</h2>
          <p>Do the next thing.</p>
        </main>
        """
    )
    page = parse_html(html)
    assert "# Title" in page.markdown
    assert "## Step 1" in page.markdown
    assert "## Step 2" in page.markdown


def test_preserves_code_blocks() -> None:
    html = _wrap(
        """
        <main>
          <h1>Install</h1>
          <pre><code>aka login --account my-acct
aka apps list</code></pre>
        </main>
        """
    )
    page = parse_html(html)
    assert "```" in page.markdown
    assert "aka login --account my-acct" in page.markdown
    assert "aka apps list" in page.markdown


def test_falls_back_to_article_then_body() -> None:
    html_article = _wrap(
        """
        <article>
          <h1>From Article</h1>
          <p>Content under article tag.</p>
        </article>
        """
    )
    page = parse_html(html_article)
    assert "From Article" in page.markdown
    assert "Content under article tag" in page.markdown

    # No main/article — falls back to body
    html_body_only = """
    <!DOCTYPE html>
    <html><head><title>Just Body</title></head>
    <body>
      <h1>Just Body</h1>
      <p>Direct body content.</p>
    </body></html>
    """
    page2 = parse_html(html_body_only)
    assert "Just Body" in page2.markdown
    assert "Direct body content" in page2.markdown


def test_strips_scripts_and_styles() -> None:
    html = _wrap(
        """
        <main>
          <h1>Title</h1>
          <script>var x = 'secret';</script>
          <style>.x { color: red; }</style>
          <p>Visible content.</p>
        </main>
        """
    )
    page = parse_html(html)
    assert "secret" not in page.markdown
    assert "color: red" not in page.markdown
    assert "Visible content" in page.markdown


def test_keeps_link_text_drops_anchor() -> None:
    html = _wrap(
        """
        <main>
          <h1>Title</h1>
          <p>See the <a href="https://example.com/x">reference page</a> for details.</p>
        </main>
        """
    )
    page = parse_html(html)
    assert "reference page" in page.markdown
    # markdownify with strip=['a'] removes the link wrapper but keeps text.


def test_returns_empty_markdown_for_empty_body() -> None:
    page = parse_html("<html><head><title>X</title></head><body></body></html>")
    assert page.markdown == ""
    assert page.char_count == 0


def test_collapses_excessive_blank_lines() -> None:
    html = _wrap(
        """
        <main>
          <h1>Title</h1>
          <p>One.</p>
          <p>Two.</p>
          <p>Three.</p>
        </main>
        """
    )
    page = parse_html(html)
    # No run of 3+ consecutive newlines in cleaned output.
    assert "\n\n\n" not in page.markdown
