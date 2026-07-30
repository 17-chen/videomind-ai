from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import chromadb
from fastapi import status

from app.core.config import settings
from app.core.errors import ApiError
from app.core.i18n import t
from app.core.logging import logger
from app.services.embeddings import embedding_service


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
        self._client: chromadb.HttpClient | None = None

    def _collection(self) -> Any:
        try:
            if self._client is None:
                self._client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
            return self._client.get_or_create_collection(
                name=settings.chroma_collection,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            logger.exception("Failed to connect ChromaDB")
            raise ApiError(t("chroma_unavailable"), status.HTTP_503_SERVICE_UNAVAILABLE) from exc

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
        collection.upsert(
            ids=[vector_id],
            embeddings=[embedding_service.embed_text(document)],
            documents=[document],
            metadatas=[
                {
                    "user_id": user_id,
                    "video_id": video_id,
                    "title": title,
                    "url": url,
                    "category": category or "",
                    "source": source or "",
                }
            ],
        )

    def query_video_documents(self, *, user_id: str, query: str, limit: int) -> list[VectorSearchResult]:
        collection = self._collection()
        response = collection.query(
            query_embeddings=[embedding_service.embed_text(query)],
            n_results=limit,
            where={"user_id": user_id},
            include=["documents", "metadatas", "distances"],
        )

        documents = response.get("documents", [[]])[0]
        metadatas = response.get("metadatas", [[]])[0]
        distances = response.get("distances", [[]])[0]
        results: list[VectorSearchResult] = []

        for document, metadata, distance in zip(documents, metadatas, distances, strict=False):
            results.append(
                VectorSearchResult(
                    video_id=str(metadata.get("video_id", "")),
                    title=str(metadata.get("title", "")),
                    url=str(metadata.get("url", "")),
                    category=str(metadata.get("category") or "") or None,
                    document=str(document),
                    distance=float(distance) if distance is not None else None,
                )
            )
        return results


vector_store = ChromaVectorStore()
