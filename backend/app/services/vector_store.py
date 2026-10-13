from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings
from fastapi import status

from app.core.config import settings
from app.core.errors import ApiError
from app.core.i18n import t
from app.core.logging import logger
from app.services.embeddings import current_embedding_service


@dataclass(frozen=True)
class VectorSearchResult:
    video_id: str
    title: str
    url: str
    category: str | None
    document: str
    distance: float | None


class ChromaVectorStore:
    def __init__(self) -> None:
        self._client: Any | None = None

    def _collection(self) -> Any:
        try:
            if self._client is None:
                if settings.chroma_mode == "embedded":
                    self._client = chromadb.PersistentClient(
                        path=settings.chroma_persist_dir,
                        settings=ChromaSettings(anonymized_telemetry=False),
                    )
                elif settings.chroma_mode == "http":
                    self._client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
                else:
                    raise ValueError("CHROMA_MODE must be embedded or http")
            return self._client.get_or_create_collection(
                name=self._collection_name(),
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            logger.exception("Failed to connect ChromaDB")
            raise ApiError(t("chroma_unavailable"), status.HTTP_503_SERVICE_UNAVAILABLE) from exc

    @staticmethod
    def _collection_name() -> str:
        if settings.embedding_provider == "local_hash":
            return settings.chroma_collection
        if settings.embedding_provider == "bge_zh":
            fingerprint = hashlib.sha256(settings.embedding_model.encode()).hexdigest()[:8]
            return f"{settings.chroma_collection[:45]}_bge_{fingerprint}"
        raise ApiError("不支持的向量模型配置", status.HTTP_503_SERVICE_UNAVAILABLE)

    def check_connection(self) -> None:
        self._collection()
        self._client.heartbeat()

    def upsert_video_document(
        self,
        *,
        vector_id: str,
        user_id: str,
        video_id: str,
        title: str,
        url: str,
        category: str | None,
        source: str | None,
        document: str,
    ) -> None:
        collection = self._collection()
        chunks = _split_document(document) if settings.embedding_provider == "bge_zh" else [document]
        service = current_embedding_service()
        embeddings = [service.embed_text(chunk) for chunk in chunks]
        ids = [vector_id]
        if settings.embedding_provider == "bge_zh":
            revision = hashlib.sha256(document.encode("utf-8")).hexdigest()[:12]
            ids = [f"{vector_id}:{revision}:{index}" for index in range(len(chunks))]
            previous_ids = collection.get(where=_video_filter(user_id, video_id), include=[])["ids"]
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=[
                {
                    "user_id": user_id,
                    "video_id": video_id,
                    "title": title,
                    "url": url,
                    "category": category or "",
                    "source": source or "",
                }
                for _ in chunks
            ],
        )
        if settings.embedding_provider == "bge_zh":
            stale_ids = [old_id for old_id in previous_ids if old_id not in ids]
            if stale_ids:
                collection.delete(ids=stale_ids, where=_video_filter(user_id, video_id))

    def delete_video_document(self, *, vector_id: str, user_id: str) -> None:
        self._collection()
        base_name = settings.chroma_collection
        bge_prefix = f"{base_name[:45]}_bge_"
        for item in self._client.list_collections():
            name = item if isinstance(item, str) else item.name
            if name == base_name or name.startswith(bge_prefix):
                self._client.get_collection(name).delete(
                    where=_video_filter(user_id, vector_id.removeprefix("video:"))
                )

    def query_video_documents(self, *, user_id: str, query: str, limit: int) -> list[VectorSearchResult]:
        collection = self._collection()
        query_embedding = current_embedding_service().embed_query(query)
        initial_count = limit * 5 if settings.embedding_provider == "bge_zh" else limit
        response = self._query(collection, user_id, query_embedding, initial_count)
        results = _search_results(response, limit)
        if settings.embedding_provider != "bge_zh" or len(results) >= limit:
            return results

        returned_count = len(response.get("documents", [[]])[0])
        if returned_count < initial_count:
            return results
        expanded_count = min(max(collection.count(), initial_count), 1000)
        if expanded_count <= initial_count:
            return results
        return _search_results(self._query(collection, user_id, query_embedding, expanded_count), limit)

    @staticmethod
    def _query(collection: Any, user_id: str, query_embedding: list[float], count: int) -> dict[str, Any]:
        return collection.query(
            query_embeddings=[query_embedding],
            n_results=count,
            where={"user_id": user_id},
            include=["documents", "metadatas", "distances"],
        )


def _search_results(response: dict[str, Any], limit: int) -> list[VectorSearchResult]:
    documents = response.get("documents", [[]])[0]
    metadatas = response.get("metadatas", [[]])[0]
    distances = response.get("distances", [[]])[0]
    results: list[VectorSearchResult] = []
    seen_video_ids: set[str] = set()

    for document, metadata, distance in zip(documents, metadatas, distances, strict=False):
        video_id = str(metadata.get("video_id", ""))
        if video_id in seen_video_ids:
            continue
        seen_video_ids.add(video_id)
        results.append(
            VectorSearchResult(
                video_id=video_id,
                title=str(metadata.get("title", "")),
                url=str(metadata.get("url", "")),
                category=str(metadata.get("category") or "") or None,
                document=str(document),
                distance=float(distance) if distance is not None else None,
            )
        )
        if len(results) >= limit:
            break
    return results


def _video_filter(user_id: str, video_id: str) -> dict[str, Any]:
    return {"$and": [{"user_id": user_id}, {"video_id": video_id}]}


def _split_document(document: str, chunk_size: int = 350, overlap: int = 60) -> list[str]:
    text = document.strip()
    if not text:
        return [document]
    chunks = []
    step = chunk_size - overlap
    for start in range(0, len(text), step):
        chunk = text[start:start + chunk_size]
        chunks.append(chunk)
        if start + chunk_size >= len(text):
            break
    return chunks


vector_store = ChromaVectorStore()
