# Architecture

```
src/optibot/
  config.py            settings (.env) and constants
  ingestion/           Zendesk API client -> HTML to Markdown -> token-bounded pieces
  vectorstore/         delta planning + Gemini File Search upload
  assistant/           system prompt + file_search query (python -m optibot.assistant)
  jobs/daily_sync.py   scrape -> convert -> sync -> report (exit 0/1)
main.py                Docker entry point
data/articles/         generated Markdown (one file per article)
tests/                 mirrors src/optibot
```

Dependencies point one way: `jobs -> ingestion, vectorstore, config`; `assistant -> config`;
`ingestion` and `vectorstore` never import `jobs`.

## Delta detection

Each File Search document carries `article_id`, `content_hash`, `piece_count` and `url` custom metadata, so no
database is needed between runs. New id -> added; different hash or missing/failed piece -> updated
(new pieces attached before old ones are removed); same hash -> skipped; id no longer published -> removed.

## Scraping & cleaning

The Zendesk API returns only the article body, so navigation and ads never enter the pipeline. The
converter drops scripts/styles/base64 images, turns YouTube iframes into links, one-column NOTE tables
into blockquotes, and keeps tables, fenced code, heading levels and `#anchor` links.
