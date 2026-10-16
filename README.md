# OptiBot mini-clone

Scrapes the OptiSigns help center, converts every article to clean Markdown, and keeps an OpenAI
vector store in sync for a support assistant (OpenAI Responses API + `file_search`).

| File | Role |
|---|---|
| `scraper.py` | Zendesk Help Center API, all pages, retries on 429/5xx |
| `converter.py` | HTML → Markdown (`articles/<id>-<slug>.md`) |
| `chunker.py` | Splits each article into ≤ 650-token pieces |
| `vector_sync.py` | Detects new/updated/removed articles, uploads only the delta |
| `main.py` | Daily job entry point: runs once, exits `0` on success, `1` on failure |
| `ask.py` | Asks the assistant from the terminal (same prompt + vector store) |

## Setup

```bash
cp .env.sample .env          # fill OPENAI_API_KEY; leave VECTOR_STORE_ID empty on first run
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```

## Run locally

```bash
.venv/bin/python main.py                        # first run prints the new VECTOR_STORE_ID → put it in .env
.venv/bin/python ask.py "How do I add a YouTube video?"
.venv/bin/pytest && .venv/bin/ruff check .

docker build -t optibot-sync .
docker run --rm --env-file .env optibot-sync main.py   # or: -e OPENAI_API_KEY=... -e VECTOR_STORE_ID=...
```

## Scraping & cleaning

The Zendesk API returns only the article body, so site navigation, footers and ads never enter the
pipeline. The converter then drops scripts/styles/base64 images, turns YouTube iframes into links,
turns one-column NOTE/IMPORTANT tables into blockquotes, keeps real tables, fenced code blocks and
heading levels, and keeps relative `#anchor` links working by emitting their `<a id>` targets.
Each file starts with `# Title` and an `Article URL:` line.

## Chunking strategy

Articles are split at headings and consecutive sections are packed into pieces of **≤ 650 tokens**
(`o200k_base`); a section that is too long is split by paragraph and later parts are labelled
`(Section path, continued)`. **Every piece repeats the title and `Article URL:`**, so any retrieved
chunk can be cited correctly. Pieces are uploaded as separate files with a static chunking strategy
of 800 tokens / 0 overlap, so **one file = exactly one chunk** and the logged chunk count is exact.

## Delta detection

Each vector-store file carries `article_id`, `content_hash` (SHA-256 of the article Markdown),
`piece_count` and `url` attributes, so no database or volume is needed between runs:
new id → **added**; different hash, missing or failed piece → **updated** (new pieces attached before
old ones are deleted); same hash → **skipped**; id no longer published → **removed**.
Each run logs these counts plus files/chunks embedded and writes `output/last_run.json`.

## Daily job

`.github/workflows/daily-sync.yml` builds the Dockerfile and runs it every day at 02:00 UTC
(plus manual `workflow_dispatch`). Secrets: `OPENAI_API_KEY`, `VECTOR_STORE_ID`.

- Job logs: _link added after the first scheduled run_
- Last-run artefact: `last-run` (`last_run.json` + Markdown files) on each run page

## Assistant

Created in the OpenAI Playground with the required system prompt (also in `ask.py`) and the
`file_search` tool attached to the vector store.

_Screenshot added after the first run: "How do I add a YouTube video?"_
