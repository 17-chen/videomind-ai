"""Optional shared PostgreSQL vectors. Schema is installed explicitly, never here."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.errors import ApiError
from app.core.logging import logger
from app.services.embeddings import current_embedding_service
from app.services.vector_documents import (
    DOCUMENT_CHUNK_SIZE,
    DOCUMENT_CHUNK_OVERLAP,
    VectorSearchResult,
    split_document,
)


UNAVAILABLE = "知识库暂不可用，请稍后重试"
INVALID_VECTOR = "知识库索引生成失败，请稍后重试"


def vector_literal(values: list[float]) -> str:
    if (
        not 1 <= len(values) <= 16000
        or not all(math.isfinite(value) for value in values)
        or not any(values)
    ):
        raise ApiError(INVALID_VECTOR, 503)
    return json.dumps(values, allow_nan=False, separators=(",", ":"))


def model_key(dimensions: int) -> str:
    if settings.embedding_provider == "local_hash":
        return f"local_hash:v1:{dimensions}"
    if settings.embedding_provider == "bge_zh":
        fingerprint = hashlib.sha256(settings.embedding_model.encode()).hexdigest()
        return f"bge_zh:{fingerprint}:{dimensions}"
    raise ApiError("不支持的向量模型配置", 503)


class PgVectorStore:
    def __init__(
        self,
        *,
        engine: Engine | None = None,
        chunk_size: int = DOCUMENT_CHUNK_SIZE,
        chunk_overlap: int = DOCUMENT_CHUNK_OVERLAP,
    ):
        if chunk_size < 1 or not 0 <= chunk_overlap < chunk_size:
            raise ValueError("chunk size must be positive and overlap must be smaller")
        self._engine = engine
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    @contextmanager
    def _transaction(self):
        if self._engine is None:
            from app.database.session import engine

            self._engine = engine
        try:
            with self._engine.begin() as connection:
                if connection.dialect.name != "postgresql":
                    raise ApiError(UNAVAILABLE, 503)
                yield connection
        except SQLAlchemyError as exc:
            logger.error("Shared vector database error type={}", type(exc).__name__)
            raise ApiError(UNAVAILABLE, 503) from exc

    @staticmethod
    def _extension_schema(connection) -> str:
        namespace = connection.scalar(
            text("""
            SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
            WHERE e.extname = 'vector'
        """)
        )
        if namespace is None:
            raise ApiError(UNAVAILABLE, 503)
        return connection.dialect.identifier_preparer.quote_schema(namespace)

    def check_connection(self) -> None:
        with self._transaction() as connection:
            schema = self._extension_schema(connection)
            connection.execute(
                text(
                    f"SELECT '[1,0]'::{schema}.vector OPERATOR({schema}.<=>) '[1,0]'::{schema}.vector"
                )
            )
            connection.execute(
                text(
                    "SELECT user_id, video_id, model_key, dimensions, chunk_index, embedding FROM public.vm_vector_chunks LIMIT 0"
                )
            )

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
        if vector_id != f"video:{video_id}":
            raise ValueError("vector ID must match video ID")
        chunks = (
            split_document(document, self._chunk_size, self._chunk_overlap)
            if settings.embedding_provider == "bge_zh"
            else [document]
        )
        service = current_embedding_service()
        vectors = [service.embed_text(chunk) for chunk in chunks]
        literals = [vector_literal(vector) for vector in vectors]
        dimensions = len(vectors[0])
        if any(len(vector) != dimensions for vector in vectors):
            raise ApiError(INVALID_VECTOR, 503)
        key = model_key(dimensions)
        with self._transaction() as connection:
            schema = self._extension_schema(connection)
            # Serialize revisions for this video, and reject a deleted/foreign owner.
            owned = connection.scalar(
                text(
                    "SELECT id FROM public.videos WHERE id=:video_id AND user_id=:user_id FOR UPDATE"
                ),
                {"video_id": video_id, "user_id": user_id},
            )
            if owned is None:
                raise ApiError("未找到该视频", 404)
            connection.execute(
                text(
                    "DELETE FROM public.vm_vector_chunks WHERE user_id=:user_id AND video_id=:video_id AND model_key=:key"
                ),
                {"user_id": user_id, "video_id": video_id, "key": key},
            )
            connection.execute(
                text(f"""
                INSERT INTO public.vm_vector_chunks
                (user_id, video_id, model_key, dimensions, chunk_index, title, url, category, source, document, embedding)
                VALUES (:user_id, :video_id, :key, :dimensions, :index, :title, :url, :category, :source, :document, CAST(:embedding AS {schema}.vector))
            """),
                [
                    {
                        "user_id": user_id,
                        "video_id": video_id,
                        "key": key,
                        "dimensions": dimensions,
                        "index": index,
                        "title": title,
                        "url": url,
                        "category": category,
                        "source": source,
                        "document": chunk,
                        "embedding": literal,
                    }
                    for index, (chunk, literal) in enumerate(
                        zip(chunks, literals, strict=True)
                    )
                ],
            )

    def delete_video_document(self, *, vector_id: str, user_id: str) -> None:
        if not vector_id.startswith("video:"):
            raise ValueError("vector ID must identify a video")
        with self._transaction() as connection:
            # Caller may already lock the Video in another SQLAlchemy session.
            # Do not acquire that parent lock here: it would self-deadlock.
            connection.execute(
                text(
                    "DELETE FROM public.vm_vector_chunks WHERE user_id=:user_id AND video_id=:video_id"
                ),
                {"user_id": user_id, "video_id": vector_id.removeprefix("video:")},
            )

    def query_video_documents(
        self, *, user_id: str, query: str, limit: int
    ) -> list[VectorSearchResult]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        values = current_embedding_service().embed_query(query)
        if values and all(math.isfinite(value) for value in values) and not any(values):
            return []
        literal = vector_literal(values)
        with self._transaction() as connection:
            schema = self._extension_schema(connection)
            # Exact search, with user/model filtering before scoring. Rank per video
            # in SQL so a long document cannot exhaust a bounded candidate pool.
            rows = (
                connection.execute(
                    text(f"""
                WITH ranked AS (
                    SELECT video_id, title, url, category, document,
                        embedding OPERATOR({schema}.<=>) CAST(:query AS {schema}.vector) AS distance,
                        row_number() OVER (PARTITION BY video_id ORDER BY
                            embedding OPERATOR({schema}.<=>) CAST(:query AS {schema}.vector), chunk_index) AS rank
                    FROM public.vm_vector_chunks
                    WHERE user_id=:user_id AND model_key=:key AND dimensions=:dimensions
                )
                SELECT video_id, title, url, category, document, distance FROM ranked
                WHERE rank=1 ORDER BY distance, video_id LIMIT :limit
            """),
                    {
                        "query": literal,
                        "user_id": user_id,
                        "key": model_key(len(values)),
                        "dimensions": len(values),
                        "limit": limit,
                    },
                )
                .mappings()
                .all()
            )
        return [VectorSearchResult(**dict(row)) for row in rows]
