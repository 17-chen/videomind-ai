from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

from fastapi import status

from app.core.config import settings
from app.core.errors import ApiError

WORD_RE = re.compile(r"[A-Za-z0-9_]+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


class LocalHashEmbeddingService:
    """Deterministic local embeddings for the MVP RAG loop.

    This avoids depending on OpenAI embeddings while keeping the storage layer
    provider-agnostic. It can be replaced by bge-m3, sentence-transformers, or
    a hosted embedding provider without changing API routes.
    """

    def __init__(self, dimensions: int | None = None) -> None:
        self.dimensions = dimensions or settings.embedding_dimensions

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in self._tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            raw = int.from_bytes(digest, byteorder="big", signed=False)
            index = raw % self.dimensions
            sign = 1.0 if ((raw >> 8) & 1) else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_text(text)

    def _tokenize(self, text: str) -> list[str]:
        normalized = text.lower().strip()
        words = WORD_RE.findall(normalized)
        cjk_chars = CJK_RE.findall(normalized)
        cjk_bigrams = [f"{left}{right}" for left, right in zip(cjk_chars, cjk_chars[1:])]
        return words + cjk_chars + cjk_bigrams


embedding_service = LocalHashEmbeddingService()


@lru_cache(maxsize=2)
def _load_sentence_model(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise ApiError("中文向量组件未安装，请安装 backend/requirements-local-ai.txt", status.HTTP_503_SERVICE_UNAVAILABLE) from exc
    return SentenceTransformer(model_name)


class BgeZhEmbeddingService:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def embed_text(self, text: str) -> list[float]:
        values = _load_sentence_model(self.model_name).encode(text, normalize_embeddings=True)
        return [float(value) for value in values]

    def embed_query(self, text: str) -> list[float]:
        instruction = "为这个句子生成表示以用于检索相关文章："
        return self.embed_text(instruction + text)


def current_embedding_service() -> LocalHashEmbeddingService | BgeZhEmbeddingService:
    if settings.embedding_provider == "local_hash":
        return embedding_service
    if settings.embedding_provider == "bge_zh":
        return BgeZhEmbeddingService(settings.embedding_model)
    raise ApiError("不支持的向量模型配置", status.HTTP_503_SERVICE_UNAVAILABLE)
