import re

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify

from scraper import Article

_DROP_TAGS = ("script", "style", "noscript", "button", "form", "input", "svg")
_YOUTUBE_EMBED = re.compile(r"youtube(?:-nocookie)?\.com/embed/([\w-]+)")


def _absolute(src: str) -> str:
    return f"https:{src}" if src.startswith("//") else src


def _replace_iframes(soup: BeautifulSoup) -> None:
    """Embedded players become plain links; Markdown cannot render iframes."""
    for iframe in soup.find_all("iframe"):
        src = _absolute(iframe.get("src", ""))
        youtube = _YOUTUBE_EMBED.search(src)
        href = f"https://www.youtube.com/watch?v={youtube.group(1)}" if youtube else src
        link = soup.new_tag("a", href=href)
        link.string = "Watch the video" if youtube else "View embedded content"
        paragraph = soup.new_tag("p")
        paragraph.append(link)
        iframe.replace_with(paragraph)


def _drop_inline_images(soup: BeautifulSoup) -> None:
    """Base64 `data:` images can be tens of thousands of tokens of noise; keep only their alt text."""
    for image in soup.find_all("img", src=re.compile(r"^data:")):
        image.replace_with(image.get("alt", ""))


def _is_callout(table: Tag) -> bool:
    rows = table.find_all("tr")
    return bool(rows) and all(len(row.find_all(["td", "th"])) == 1 for row in rows)


def _replace_callout_tables(soup: BeautifulSoup) -> None:
    """Zendesk renders NOTE/IMPORTANT boxes as one-column tables; a blockquote reads better."""
    for table in soup.find_all("table"):
        if not _is_callout(table):
            continue
        quote = soup.new_tag("blockquote")
        for cell in table.find_all(["td", "th"]):
            # Each cell becomes its own block so text from adjacent rows never runs together.
            block = soup.new_tag("div")
            block.extend(list(cell.children))
            quote.append(block)
        table.replace_with(quote)


def _keep_anchor_targets(soup: BeautifulSoup) -> None:
    """In-page links (#Section) target <a name>; keep them as HTML anchors so the links still resolve."""
    for anchor in soup.find_all("a", attrs={"name": True}):
        if anchor.get("href"):
            continue
        anchor.replace_with(f'<a id="{anchor["name"]}"></a>')


def _clean_headings(soup: BeautifulSoup) -> None:
    """Headings are often wrapped in <strong>/<span>; plain text avoids `## **Title**`."""
    for heading in soup.find_all(re.compile(r"^h[1-6]$")):
        text = heading.get_text(" ", strip=True)
        if not text:
            heading.decompose()
            continue
        heading.clear()
        heading.string = text


def _code_language(pre: Tag) -> str:
    code = pre.find("code")
    classes = code.get("class", []) if code else []
    language = next((c.removeprefix("language-") for c in classes if c.startswith("language-")), "")
    return "" if language == "auto" else language


def _tidy(markdown: str) -> str:
    markdown = markdown.replace("\xa0", " ")
    markdown = re.sub(r"[ \t]+\n", "\n", markdown)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown.strip() + "\n"


def html_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(_DROP_TAGS):
        tag.decompose()
    _replace_iframes(soup)
    _drop_inline_images(soup)
    _replace_callout_tables(soup)
    _keep_anchor_targets(soup)
    _clean_headings(soup)
    markdown = markdownify(
        str(soup),
        heading_style="ATX",
        bullets="-",
        code_language_callback=_code_language,
    )
    return _tidy(markdown)


def article_slug(article: Article) -> str:
    """`<id>-<title-slug>` taken from the help-center URL; the id prefix keeps names unique."""
    return article.url.rstrip("/").rsplit("/", 1)[-1].lower()


def article_header(article: Article) -> str:
    return f"# {article.title}\n\nArticle URL: {article.url}\n\n"


def article_to_markdown(article: Article) -> str:
    return article_header(article) + html_to_markdown(article.body_html)
