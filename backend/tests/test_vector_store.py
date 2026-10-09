from app.core.config import settings
from app.services.vector_store import ChromaVectorStore


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
