"""Daily job: scrape the help center, write Markdown, upload only new/changed articles, log counts.

Runs once and exits: 0 on success, 1 on any failure.
"""

import json
import logging
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from openai import OpenAI

from chunker import split_into_pieces
from config import ARTICLES_DIR, HELP_CENTER_URL, LAST_RUN_PATH, VECTOR_STORE_NAME, load_settings
from converter import article_header, article_slug, article_to_markdown
from scraper import Article, fetch_articles
from vector_sync import Document, SyncReport, ensure_vector_store, sync_documents

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


def write_last_run(report: SyncReport, vector_store_id: str, articles: int) -> None:
    LAST_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "vector_store_id": vector_store_id,
        "articles_scraped": articles,
        **asdict(report),
    }
    LAST_RUN_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    log.info("Run summary: %s", json.dumps(payload))


def run() -> None:
    settings = load_settings()
    client = OpenAI(api_key=settings.openai_api_key, max_retries=5)

    articles = fetch_articles(HELP_CENTER_URL)
    log.info("Scraped %d articles", len(articles))
    documents = [to_document(article) for article in articles]
    write_markdown(documents, ARTICLES_DIR)
    log.info("Wrote %d Markdown files to %s/", len(documents), ARTICLES_DIR)

    vector_store_id = ensure_vector_store(client, settings.vector_store_id, VECTOR_STORE_NAME)
    if not settings.vector_store_id:
        log.info("Created vector store %s; set VECTOR_STORE_ID to reuse it", vector_store_id)

    report = sync_documents(client, vector_store_id, documents)
    log.info(
        "added=%d updated=%d skipped=%d removed=%d | embedded %d files, %d chunks",
        report.added,
        report.updated,
        report.skipped,
        report.removed,
        report.files_uploaded,
        report.chunks_embedded,
    )
    write_last_run(report, vector_store_id, len(articles))


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
