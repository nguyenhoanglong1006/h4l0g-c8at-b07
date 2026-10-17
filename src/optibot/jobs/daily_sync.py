"""Daily job: scrape the help center, write Markdown, upload only new/changed articles, log counts.

Runs once and exits: 0 on success, 1 on any failure.
"""

import json
import logging
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from google import genai
from google.genai import types

from optibot.config import ARTICLES_DIR, HELP_CENTER_URL, LAST_RUN_PATH, STORE_DISPLAY_NAME, load_settings
from optibot.ingestion.chunker import split_into_pieces
from optibot.ingestion.converter import article_header, article_slug, article_to_markdown
from optibot.ingestion.scraper import Article, fetch_articles
from optibot.vectorstore.sync import Document, SyncReport, ensure_store, sync_documents

log = logging.getLogger("optibot")


def to_document(article: Article) -> Document:
    markdown = article_to_markdown(article)
    return Document(
        article_id=str(article.id),
        slug=article_slug(article),
        url=article.url,
        markdown=markdown,
        pieces=split_into_pieces(markdown, article_header(article)),
    )


def write_markdown(documents: list[Document], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    current = {f"{d.slug}.md" for d in documents}
    for stale in directory.glob("*.md"):
        if stale.name not in current:
            stale.unlink()
    for document in documents:
        (directory / f"{document.slug}.md").write_text(document.markdown, encoding="utf-8")


def write_last_run(report: SyncReport, store_name: str, articles: int) -> None:
    LAST_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "store_name": store_name,
        "articles_scraped": articles,
        **asdict(report),
    }
    LAST_RUN_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    log.info("Run summary: %s", json.dumps(payload))


def run() -> None:
    settings = load_settings()
    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=5)),
    )

    articles = fetch_articles(HELP_CENTER_URL)
    log.info("Scraped %d articles", len(articles))
    documents = [to_document(article) for article in articles]
    write_markdown(documents, ARTICLES_DIR)
    log.info("Wrote %d Markdown files to %s/", len(documents), ARTICLES_DIR)

    store_name = ensure_store(client, settings.store_name, STORE_DISPLAY_NAME)
    if not settings.store_name:
        log.info("Created File Search store %s; set FILE_SEARCH_STORE to reuse it", store_name)

    report = sync_documents(client, store_name, documents)
    log.info(
        "added=%d updated=%d skipped=%d removed=%d | embedded %d files, %d chunks",
        report.added,
        report.updated,
        report.skipped,
        report.removed,
        report.files_uploaded,
        report.chunks_embedded,
    )
    write_last_run(report, store_name, len(articles))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Library request logs would print every one of ~1200 uploads; keep the job log readable.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        run()
    except Exception:
        log.exception("Sync failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
