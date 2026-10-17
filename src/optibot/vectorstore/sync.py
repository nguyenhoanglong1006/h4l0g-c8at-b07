"""Delta upload of article pieces to a Gemini File Search store.

State lives on the store itself: every document carries `article_id`, `content_hash` and
`piece_count` metadata, so a fresh container can tell what is already embedded.
"""

import hashlib
import io
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from http import HTTPStatus

from google import genai
from google.genai import errors, types

from optibot.ingestion.chunker import CHUNK_SIZE_TOKENS

MAX_WORKERS = 8
POLL_SECONDS = 2
LIST_PAGE_SIZE = 20  # API maximum; the default of 10 doubles the listing requests.
CHUNKING_CONFIG = types.ChunkingConfig(
    white_space_config=types.WhiteSpaceConfig(max_tokens_per_chunk=CHUNK_SIZE_TOKENS, max_overlap_tokens=0)
)


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


def _to_stored_file(document: types.Document) -> StoredFile:
    metadata = {m.key: m for m in document.custom_metadata or []}

    def text(key: str) -> str:
        return metadata[key].string_value or "" if key in metadata else ""

    piece_count = metadata["piece_count"].numeric_value if "piece_count" in metadata else 0
    return StoredFile(
        file_id=document.name or "",
        article_id=text("article_id"),
        content_hash=text("content_hash"),
        piece_count=int(piece_count or 0),
        completed=document.state == types.DocumentState.STATE_ACTIVE,
    )


def _list_stored_files(client: genai.Client, store_name: str) -> list[StoredFile]:
    # Iterating the pager follows the page tokens through every page.
    pager = client.file_search_stores.documents.list(
        parent=store_name, config=types.ListDocumentsConfig(page_size=LIST_PAGE_SIZE)
    )
    return [_to_stored_file(d) for d in pager]


def _run_parallel[T, R](task: Callable[[T], R], items: Iterable[T]) -> list[R]:
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        return list(executor.map(task, items))


def _upload_piece(client: genai.Client, store_name: str, job: tuple[Document, int, str]) -> None:
    document, index, piece = job
    operation = client.file_search_stores.upload_to_file_search_store(
        file_search_store_name=store_name,
        file=io.BytesIO(piece.encode("utf-8")),
        config=types.UploadToFileSearchStoreConfig(
            display_name=f"{document.slug}--part-{index:02d}.md",
            mime_type="text/markdown",
            chunking_config=CHUNKING_CONFIG,
            custom_metadata=[
                types.CustomMetadata(key="article_id", string_value=document.article_id),
                types.CustomMetadata(key="content_hash", string_value=document.content_hash),
                types.CustomMetadata(key="piece_count", numeric_value=len(document.pieces)),
                types.CustomMetadata(key="url", string_value=document.url),
            ],
        ),
    )
    while not operation.done:
        time.sleep(POLL_SECONDS)
        operation = client.operations.get(operation)
    if operation.error:
        raise RuntimeError(f"Upload of {document.slug} part {index} failed: {operation.error}")


def _upload_pieces(client: genai.Client, store_name: str, documents: list[Document]) -> int:
    jobs = [
        (document, index, piece)
        for document in documents
        for index, piece in enumerate(document.pieces, start=1)
    ]
    _run_parallel(lambda job: _upload_piece(client, store_name, job), jobs)
    return len(jobs)


def _delete_document(client: genai.Client, name: str) -> None:
    try:
        client.file_search_stores.documents.delete(name=name, config=types.DeleteDocumentConfig(force=True))
    except errors.ClientError as error:
        # Already gone (e.g. removed by an interrupted run) is the desired state; anything else fails.
        if error.code != HTTPStatus.NOT_FOUND:
            raise


def _delete_documents(client: genai.Client, document_names: list[str]) -> None:
    _run_parallel(lambda name: _delete_document(client, name), document_names)


def sync_documents(client: genai.Client, store_name: str, documents: list[Document]) -> SyncReport:
    delta = plan_delta(documents, _list_stored_files(client, store_name))
    uploaded = _upload_pieces(client, store_name, delta.added + delta.updated)
    # New pieces are added before old ones are removed, so an article is never missing mid-run.
    _delete_documents(client, delta.stale_file_ids)
    return SyncReport(
        added=len(delta.added),
        updated=len(delta.updated),
        skipped=len(delta.skipped),
        removed=len(delta.removed_article_ids),
        files_uploaded=uploaded,
        # Each piece is sized below the configured chunk size, so one document is one chunk.
        chunks_embedded=uploaded,
    )


def ensure_store(client: genai.Client, store_name: str, display_name: str) -> str:
    if store_name:
        return store_name
    config = types.CreateFileSearchStoreConfig(display_name=display_name)
    store = client.file_search_stores.create(config=config)
    return store.name or ""
