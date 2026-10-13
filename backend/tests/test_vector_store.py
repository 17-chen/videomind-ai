import pytest

from app.core.config import settings
from app.services.vector_store import ChromaVectorStore
from app.services import vector_store as vector_store_module
from app.services.embeddings import LocalHashEmbeddingService


def test_embedded_chroma_persists_and_filters_users(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "chroma_mode", "embedded")
    monkeypatch.setattr(settings, "chroma_persist_dir", str(tmp_path / "chroma"))
    monkeypatch.setattr(settings, "chroma_collection", "videomind_test")
    first = ChromaVectorStore()
    first.upsert_video_document(
        vector_id="video:alice", user_id="alice", video_id="alice", title="Alice's video",
        url="https://example.com/alice", category="Study", source="youtube", document="linear algebra vectors matrix",
    )
    first.upsert_video_document(
        vector_id="video:bob", user_id="bob", video_id="bob", title="Bob's video",
        url="https://example.com/bob", category="Study", source="youtube", document="linear algebra vectors matrix",
    )
    restarted = ChromaVectorStore()
    alice_results = restarted.query_video_documents(user_id="alice", query="linear algebra", limit=5)
    bob_results = restarted.query_video_documents(user_id="bob", query="linear algebra", limit=5)
    assert [item.video_id for item in alice_results] == ["alice"]
    assert [item.video_id for item in bob_results] == ["bob"]
    assert alice_results[0].document == "linear algebra vectors matrix"

    restarted.delete_video_document(vector_id="video:alice", user_id="bob")
    assert [item.video_id for item in restarted.query_video_documents(user_id="alice", query="linear algebra", limit=5)] == ["alice"]
    restarted.delete_video_document(vector_id="video:alice", user_id="alice")
    assert restarted.query_video_documents(user_id="alice", query="linear algebra", limit=5) == []
    assert [item.video_id for item in restarted.query_video_documents(user_id="bob", query="linear algebra", limit=5)] == ["bob"]


def test_delete_cleans_old_and_new_embedding_collections(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "chroma_mode", "embedded")
    monkeypatch.setattr(settings, "chroma_persist_dir", str(tmp_path / "chroma"))
    monkeypatch.setattr(settings, "chroma_collection", "videomind_switch_test")
    monkeypatch.setattr(vector_store_module, "current_embedding_service", lambda: LocalHashEmbeddingService(dimensions=8))
    store = ChromaVectorStore()

    monkeypatch.setattr(settings, "embedding_provider", "local_hash")
    store.upsert_video_document(
        vector_id="video:alice", user_id="alice", video_id="alice", title="Test",
        url="https://example.com/alice", category=None, source=None, document="旧向量",
    )
    monkeypatch.setattr(settings, "embedding_provider", "bge_zh")
    store.upsert_video_document(
        vector_id="video:alice", user_id="alice", video_id="alice", title="Test",
        url="https://example.com/alice", category=None, source=None, document="中文向量测试" * 100,
    )
    assert len(store._client.list_collections()) == 2
    assert len(store.query_video_documents(user_id="alice", query="中文向量", limit=5)) == 1
    bge_collection = store._client.get_collection(store._collection_name())
    assert bge_collection.count() > 1

    store.upsert_video_document(
        vector_id="video:alice", user_id="alice", video_id="alice", title="Test",
        url="https://example.com/alice", category=None, source=None, document="更新后的短笔记",
    )
    assert bge_collection.count() == 1
    assert bge_collection.get()["documents"] == ["更新后的短笔记"]

    store.delete_video_document(vector_id="video:alice", user_id="alice")
    for collection in store._client.list_collections():
        assert store._client.get_collection(collection.name).count() == 0


def test_failed_bge_update_keeps_previous_chunks(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "bge_zh")
    monkeypatch.setattr(vector_store_module, "current_embedding_service", lambda: LocalHashEmbeddingService(dimensions=8))

    class FailingCollection:
        def __init__(self):
            self.ids = ["video:alice:old:0"]
            self.deleted = False

        def get(self, **kwargs):
            return {"ids": self.ids}

        def upsert(self, **kwargs):
            raise RuntimeError("temporary Chroma failure")

        def delete(self, **kwargs):
            self.deleted = True

    collection = FailingCollection()
    store = ChromaVectorStore()
    monkeypatch.setattr(store, "_collection", lambda: collection)

    with pytest.raises(RuntimeError, match="temporary Chroma failure"):
        store.upsert_video_document(
            vector_id="video:alice", user_id="alice", video_id="alice", title="Test",
            url="https://example.com/alice", category=None, source=None, document="新内容",
        )
    assert collection.ids == ["video:alice:old:0"]
    assert not collection.deleted


def test_bge_search_expands_when_one_video_crowds_initial_results(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "bge_zh")
    monkeypatch.setattr(vector_store_module, "current_embedding_service", lambda: LocalHashEmbeddingService(dimensions=8))
    requested_counts = []

    class CrowdedCollection:
        def query(self, *, n_results, **kwargs):
            requested_counts.append(n_results)
            video_ids = ["alice"] * 10 + (["bob"] if n_results > 10 else [])
            return {
                "documents": [[f"content {video_id}" for video_id in video_ids]],
                "metadatas": [[{"video_id": video_id, "title": video_id, "url": "https://example.com"} for video_id in video_ids]],
                "distances": [[0.1] * len(video_ids)],
            }

        def count(self):
            return 25

    store = ChromaVectorStore()
    monkeypatch.setattr(store, "_collection", lambda: CrowdedCollection())
    results = store.query_video_documents(user_id="owner", query="question", limit=2)
    assert [result.video_id for result in results] == ["alice", "bob"]
    assert requested_counts == [10, 25]
