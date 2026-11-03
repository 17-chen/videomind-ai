"""Shared result shape and chunk boundaries for Chroma and PostgreSQL."""

from dataclasses import dataclass


DOCUMENT_CHUNK_SIZE = 350
DOCUMENT_CHUNK_OVERLAP = 60
DOCUMENT_CANDIDATE_MULTIPLIER = 5


@dataclass(frozen=True)
class VectorSearchResult:
    video_id: str
    title: str
    url: str
    category: str | None
    document: str
    distance: float | None


def split_document(
    document: str,
    chunk_size: int = DOCUMENT_CHUNK_SIZE,
    overlap: int = DOCUMENT_CHUNK_OVERLAP,
) -> list[str]:
    text = document.strip()
    if not text:
        return [document]
    chunks = []
    step = chunk_size - overlap
    for start in range(0, len(text), step):
        chunk = text[start : start + chunk_size]
        chunks.append(chunk)
        if start + chunk_size >= len(text):
            break
    return chunks
