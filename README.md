# OptiBot mini-clone

Scrapes the OptiSigns help center, converts articles to Markdown, and keeps a Gemini File Search store
in sync for a support assistant (Gemini API + File Search). Design details: [docs/architecture.md](docs/architecture.md).

## Setup & run

```bash
cp .env.sample .env      # fill GEMINI_API_KEY; leave FILE_SEARCH_STORE empty on first run
make install
make sync                # first run prints the new store name -> put it in .env
make ask Q="How do I add a YouTube video?"
make test lint

docker build -t optibot-sync . && docker run --rm --env-file .env optibot-sync main.py
```

## Chunking

Articles are split at headings and packed into pieces of ≤ 400 tokens; each piece repeats the title and
`Article URL:` so any retrieved chunk can be cited. Each piece is uploaded as its own document with a
512-token (Gemini's maximum) / 0-overlap chunking config, so **one document = one chunk** and the logged
chunk count follows.

## Daily job

[`daily-sync.yml`](.github/workflows/daily-sync.yml) runs the Docker image at 02:00 UTC. It re-scrapes,
compares each article's SHA-256 with the one stored in the File Search store, uploads only the delta and logs
`added / updated / skipped / removed` plus files and chunks embedded.

- Job logs: <!-- TODO: paste Actions run URL after first run -->
- Last-run artefact: `last-run` on each run page (`last_run.json`)

## Sample answer

![OptiBot answering "How do I add a YouTube video?"](docs/images/sample-answer.png)
