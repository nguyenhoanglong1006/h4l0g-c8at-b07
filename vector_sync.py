"""Delta upload of article pieces to an OpenAI vector store.

State lives on the vector store itself: every file carries `article_id`, `content_hash` and
`piece_count` attributes, so a fresh container can tell what is already embedded.
"""

import hashlib
from collections import defaultdict
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from openai import OpenAI

from chunker import CHUNK_SIZE_TOKENS

Attributes = dict[str, str | float | bool]

MAX_WORKERS = 8
BATCH_SIZE = 500  # API limit is 2000 files per batch; smaller batches fail faster and poll sooner.
CHUNKING_STRATEGY = {
    "type": "static",
    "static": {"max_chunk_size_tokens": CHUNK_SIZE_TOKENS, "chunk_overlap_tokens": 0},
}


@dataclass(frozen=True)
class Document:
    article_id: str
    slug: str
    url: str
    markdown: str
    pieces: list[str]

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.markdown.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StoredFile:
    file_id: str
    article_id: str
    content_hash: str
    piece_count: int
    completed: bool


@dataclass
class Delta:
    added: list[Document] = field(default_factory=list)
    updated: list[Document] = field(default_factory=list)
    skipped: list[Document] = field(default_factory=list)
    removed_article_ids: list[str] = field(default_factory=list)
    stale_file_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SyncReport:
    added: int
    updated: int
    skipped: int
    removed: int
    files_uploaded: int
    chunks_embedded: int


def _is_current(document: Document, files: list[StoredFile]) -> bool:
    """Current only if every piece of this exact content is present and finished embedding."""
    return len(files) == len(document.pieces) and all(
        f.completed and f.content_hash == document.content_hash and f.piece_count == len(document.pieces)
        for f in files
    )


def plan_delta(documents: list[Document], stored: list[StoredFile]) -> Delta:
    files_by_article: dict[str, list[StoredFile]] = defaultdict(list)
    for stored_file in stored:
        files_by_article[stored_file.article_id].append(stored_file)

    delta = Delta()
    for document in documents:
        existing = files_by_article.pop(document.article_id, [])
        if not existing:
            delta.added.append(document)
        elif _is_current(document, existing):
            delta.skipped.append(document)
        else:
            delta.updated.append(document)
            delta.stale_file_ids.extend(f.file_id for f in existing)

    # Whatever is left belongs to articles no longer published.
    for article_id, files in files_by_article.items():
        delta.removed_article_ids.append(article_id)
        delta.stale_file_ids.extend(f.file_id for f in files)
    return delta


def _to_stored_file(file_id: str, status: str, attributes: Attributes | None) -> StoredFile:
    attributes = attributes or {}
    return StoredFile(
        file_id=file_id,
        article_id=str(attributes.get("article_id", "")),
        content_hash=str(attributes.get("content_hash", "")),
        piece_count=int(attributes.get("piece_count", 0)),
        completed=status == "completed",
    )


def _list_stored_files(client: OpenAI, vector_store_id: str) -> list[StoredFile]:
    # Iterating the page object follows the cursor through every page.
    return [
        _to_stored_file(f.id, f.status, f.attributes)
        for f in client.vector_stores.files.list(vector_store_id=vector_store_id, limit=100)
    ]


def _run_parallel[T, R](task: Callable[[T], R], items: Iterable[T]) -> list[R]:
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        return list(executor.map(task, items))


def _upload_raw_files(client: OpenAI, documents: list[Document]) -> list[dict]:
    """Upload every piece as its own file; return batch entries carrying the per-file attributes."""
    jobs = [
        (document, index, piece)
        for document in documents
        for index, piece in enumerate(document.pieces, start=1)
    ]

    def upload(job: tuple[Document, int, str]) -> dict:
        document, index, piece = job
        file_name = f"{document.slug}--part-{index:02d}.md"
        uploaded = client.files.create(file=(file_name, piece.encode("utf-8")), purpose="assistants")
        return {
            "file_id": uploaded.id,
            "chunking_strategy": CHUNKING_STRATEGY,
            "attributes": {
                "article_id": document.article_id,
                "content_hash": document.content_hash,
                "piece_count": len(document.pieces),
                "url": document.url,
            },
        }

    return _run_parallel(upload, jobs)


def _attach(client: OpenAI, vector_store_id: str, entries: list[dict]) -> None:
    for start in range(0, len(entries), BATCH_SIZE):
        batch = client.vector_stores.file_batches.create_and_poll(
            vector_store_id=vector_store_id, files=entries[start : start + BATCH_SIZE]
        )
        counts = batch.file_counts
        if batch.status != "completed" or counts.failed or counts.cancelled:
            raise RuntimeError(
                f"Vector store batch {batch.id} ended {batch.status}: "
                f"{counts.completed} completed, {counts.failed} failed, {counts.cancelled} cancelled"
            )


def _delete_files(client: OpenAI, vector_store_id: str, file_ids: list[str]) -> None:
    def delete(file_id: str) -> None:
        client.vector_stores.files.delete(file_id, vector_store_id=vector_store_id)
        client.files.delete(file_id)

    _run_parallel(delete, file_ids)


def sync_documents(client: OpenAI, vector_store_id: str, documents: list[Document]) -> SyncReport:
    delta = plan_delta(documents, _list_stored_files(client, vector_store_id))
    to_upload = delta.added + delta.updated
    entries = _upload_raw_files(client, to_upload)
    _attach(client, vector_store_id, entries)
    # New pieces are attached before old ones are removed, so an article is never missing mid-run.
    _delete_files(client, vector_store_id, delta.stale_file_ids)
    return SyncReport(
        added=len(delta.added),
        updated=len(delta.updated),
        skipped=len(delta.skipped),
        removed=len(delta.removed_article_ids),
        files_uploaded=len(entries),
        # Each piece is sized below the static chunk size, so one file is exactly one chunk.
        chunks_embedded=len(entries),
    )


def ensure_vector_store(client: OpenAI, vector_store_id: str, name: str) -> str:
    if vector_store_id:
        return vector_store_id
    return client.vector_stores.create(name=name).id
