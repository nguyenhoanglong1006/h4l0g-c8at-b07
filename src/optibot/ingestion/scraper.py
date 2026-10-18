import time
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PAGE_SIZE = 100
TIMEOUT_SECONDS = 30
PAGE_ATTEMPTS = 4
PAGE_BACKOFF_SECONDS = 2


@dataclass(frozen=True)
class Article:
    id: int
    title: str
    url: str
    updated_at: str
    body_html: str


def _session() -> requests.Session:
    retry = Retry(total=5, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _parse_article(raw: dict) -> Article | None:
    if raw.get("draft") or not raw.get("body"):
        return None
    return Article(
        id=int(raw["id"]),
        title=str(raw["title"]).strip(),
        url=str(raw["html_url"]),
        updated_at=str(raw["updated_at"]),
        body_html=str(raw["body"]),
    )


def _get_page(session: requests.Session, url: str) -> dict:
    """GET one page as JSON. The adapter's Retry misses body read timeouts, so retry them here."""
    for attempt in range(1, PAGE_ATTEMPTS + 1):
        try:
            response = session.get(url, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except requests.ConnectionError:
            if attempt == PAGE_ATTEMPTS:
                raise
            time.sleep(attempt * PAGE_BACKOFF_SECONDS)
    raise AssertionError("unreachable")


def fetch_articles(base_url: str) -> list[Article]:
    """Fetch every published article from the Zendesk Help Center API, following pagination."""
    session = _session()
    articles: list[Article] = []
    next_url: str | None = f"{base_url}?per_page={PAGE_SIZE}"
    while next_url:
        payload = _get_page(session, next_url)
        articles.extend(a for a in map(_parse_article, payload["articles"]) if a)
        next_url = payload.get("next_page")
    return articles
