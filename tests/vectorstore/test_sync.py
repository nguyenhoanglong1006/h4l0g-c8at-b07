from types import SimpleNamespace

import pytest
from google.genai import errors, types

from optibot.vectorstore.sync import Document, StoredFile, _delete_document, _to_stored_file, plan_delta


def make_document(article_id: str, markdown: str, piece_count: int = 1) -> Document:
    return Document(
        article_id=article_id,
        slug=f"{article_id}-slug",
        url=f"https://support.optisigns.com/hc/en-us/articles/{article_id}",
        markdown=markdown,
        pieces=[markdown] * piece_count,
    )


def stored_for(document: Document, file_id: str, **overrides) -> StoredFile:
    values = {
        "file_id": file_id,
        "article_id": document.article_id,
        "content_hash": document.content_hash,
        "piece_count": len(document.pieces),
        "completed": True,
    }
    return StoredFile(**(values | overrides))


def test_new_article_is_added():
    document = make_document("1", "new")

    delta = plan_delta([document], [])

    assert delta.added == [document]
    assert delta.stale_file_ids == []


def test_unchanged_article_is_skipped():
    document = make_document("1", "same", piece_count=2)
    stored = [stored_for(document, "f1"), stored_for(document, "f2")]

    delta = plan_delta([document], stored)

    assert delta.skipped == [document]
    assert not delta.added and not delta.updated and not delta.stale_file_ids


def test_changed_article_is_updated_and_old_files_are_stale():
    document = make_document("1", "edited")
    stored = [stored_for(document, "old", content_hash="previous-hash")]

    delta = plan_delta([document], stored)

    assert delta.updated == [document]
    assert delta.stale_file_ids == ["old"]


def test_partially_uploaded_or_failed_article_is_reuploaded():
    document = make_document("1", "text", piece_count=2)
    missing_piece = [stored_for(document, "f1")]
    failed_piece = [stored_for(document, "f1"), stored_for(document, "f2", completed=False)]

    assert plan_delta([document], missing_piece).updated == [document]
    assert plan_delta([document], failed_piece).updated == [document]


def test_unpublished_article_files_are_removed():
    gone = make_document("9", "gone")

    delta = plan_delta([], [stored_for(gone, "f9")])

    assert delta.removed_article_ids == ["9"]
    assert delta.stale_file_ids == ["f9"]


def test_stored_file_is_read_from_document_metadata():
    document = types.Document(
        name="fileSearchStores/s/documents/d1",
        state=types.DocumentState.STATE_ACTIVE,
        custom_metadata=[
            types.CustomMetadata(key="article_id", string_value="42"),
            types.CustomMetadata(key="content_hash", string_value="abc"),
            types.CustomMetadata(key="piece_count", numeric_value=3),
        ],
    )

    assert _to_stored_file(document) == StoredFile(
        file_id="fileSearchStores/s/documents/d1",
        article_id="42",
        content_hash="abc",
        piece_count=3,
        completed=True,
    )


def test_pending_document_without_metadata_is_not_completed():
    stored = _to_stored_file(types.Document(name="d", state=types.DocumentState.STATE_PENDING))

    assert stored.article_id == ""
    assert not stored.completed


class FakeDocuments:
    def __init__(self, error: errors.ClientError | None = None):
        self.error = error
        self.deleted: list[str] = []

    def delete(self, name: str, config: types.DeleteDocumentConfig) -> None:
        if self.error:
            raise self.error
        self.deleted.append(name)


def fake_client(documents: FakeDocuments) -> SimpleNamespace:
    return SimpleNamespace(file_search_stores=SimpleNamespace(documents=documents))


def api_error(code: int) -> errors.ClientError:
    return errors.ClientError(code, {"error": {"code": code, "message": "x", "status": "X"}})


def test_delete_removes_document():
    documents = FakeDocuments()

    _delete_document(fake_client(documents), "doc-1")

    assert documents.deleted == ["doc-1"]


def test_delete_of_already_removed_document_is_not_an_error():
    _delete_document(fake_client(FakeDocuments(api_error(404))), "doc-1")


def test_delete_propagates_other_api_errors():
    with pytest.raises(errors.ClientError):
        _delete_document(fake_client(FakeDocuments(api_error(403))), "doc-1")
