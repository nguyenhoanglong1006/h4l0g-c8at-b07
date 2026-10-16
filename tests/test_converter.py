from converter import article_slug, article_to_markdown, html_to_markdown
from scraper import Article


def test_keeps_headings_lists_and_code_blocks():
    html = (
        '<h2 id="h_1"><strong>Set up</strong></h2><ul><li>One</li><li>Two</li></ul>'
        '<pre class="wysiwyg-code-block"><code class="language-auto">curl https://x.io</code></pre>'
    )

    markdown = html_to_markdown(html)

    assert "## Set up\n" in markdown
    assert "- One\n- Two" in markdown
    assert "```\ncurl https://x.io\n```" in markdown


def test_preserves_relative_links_and_their_anchor_targets():
    html = '<p><a href="#Steps">Jump</a></p><p><a name="Steps"></a></p><h2>Steps</h2>'

    markdown = html_to_markdown(html)

    assert "[Jump](#Steps)" in markdown
    assert '<a id="Steps"></a>' in markdown


def test_removes_scripts_styles_and_inline_base64_images():
    html = '<script>track()</script><style>p{}</style><p>Text<img src="data:image/png;base64,AAAA"></p>'

    markdown = html_to_markdown(html)

    assert markdown == "Text\n"


def test_turns_youtube_iframe_into_watch_link():
    html = '<iframe src="//www.youtube-nocookie.com/embed/GyWZd10ure0"></iframe>'

    assert "[Watch the video](https://www.youtube.com/watch?v=GyWZd10ure0)" in html_to_markdown(html)


def test_turns_one_column_callout_table_into_blockquote():
    html = "<table><tr><td><strong>NOTE</strong></td></tr><tr><td>Admins only.</td></tr></table>"

    markdown = html_to_markdown(html)

    assert "> **NOTE**" in markdown
    assert "> Admins only." in markdown
    assert "|" not in markdown


def test_keeps_real_tables_as_markdown_tables():
    html = "<table><tr><th>Plan</th><th>Price</th></tr><tr><td>Pro</td><td>$10</td></tr></table>"

    assert "| Plan | Price |" in html_to_markdown(html)


def test_article_markdown_starts_with_title_and_url():
    article = Article(
        id=42,
        title="Add a Video",
        url="https://support.optisigns.com/hc/en-us/articles/42-Add-a-Video",
        updated_at="2026-01-01T00:00:00Z",
        body_html="<p>Body</p>",
    )

    assert article_to_markdown(article).startswith(
        "# Add a Video\n\nArticle URL: https://support.optisigns.com/hc/en-us/articles/42-Add-a-Video\n\nBody"
    )
    assert article_slug(article) == "42-add-a-video"
