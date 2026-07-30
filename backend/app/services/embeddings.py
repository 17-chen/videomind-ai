from __future__ import annotations

import hashlib
import math
import re

from app.core.config import settings

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

    def _tokenize(self, text: str) -> list[str]:
        normalized = text.lower().strip()
        words = WORD_RE.findall(normalized)
        cjk_chars = CJK_RE.findall(normalized)
        cjk_bigrams = [f"{left}{right}" for left, right in zip(cjk_chars, cjk_chars[1:])]
        return words + cjk_chars + cjk_bigrams


embedding_service = LocalHashEmbeddingService()
