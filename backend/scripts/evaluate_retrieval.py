"""Measure retrieval on a fixed corpus using an isolated in-memory Chroma client."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Literal
from uuid import uuid4

import chromadb
from chromadb.config import Settings as ChromaSettings
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.core.config import settings
from app.core.errors import ApiError
from app.services.vector_store import (
    DOCUMENT_CANDIDATE_MULTIPLIER, DOCUMENT_CHUNK_OVERLAP, DOCUMENT_CHUNK_SIZE, ChromaVectorStore,
)

DEFAULT_DATASET = Path(__file__).resolve().parents[1] / "evals" / "retrieval_zh.json"


class EvaluationVideo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    document: str = Field(min_length=1)
    source_url: HttpUrl | None = None


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_video_ids: list[str]


class EvaluationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1)
    videos: list[EvaluationVideo] = Field(min_length=1)
    cases: list[EvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self):
        owners = {video.id: video.user_id for video in self.videos}
        if len(owners) != len(self.videos) or len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Video IDs and case IDs must be unique")
        if not any(case.expected_video_ids for case in self.cases):
            raise ValueError("At least one case must have relevant videos")
        for case in self.cases:
            if len(set(case.expected_video_ids)) != len(case.expected_video_ids):
                raise ValueError(f"Duplicate expected video in case {case.id}")
            if any(owners.get(video_id) != case.user_id for video_id in case.expected_video_ids):
                raise ValueError(f"Case {case.id} references an unknown or another user's video")
            if not case.expected_video_ids and case.user_id in owners.values():
                raise ValueError("Empty expected results are only supported for users with empty libraries")
        return self


def score_case(case: EvaluationCase, retrieved_ids: list[str], owners: dict[str, str], top_k: int) -> dict:
    # Repeated chunks must never inflate video-level relevance metrics.
    ranked = list(dict.fromkeys(retrieved_ids))[:top_k]
    relevant = set(case.expected_video_ids)
    matched = relevant.intersection(ranked)
    return {
        "id": case.id,
        "expected_video_ids": case.expected_video_ids,
        "retrieved_video_ids": ranked,
        "hit": bool(matched) if relevant else None,
        "recall": len(matched) / len(relevant) if relevant else None,
        "precision": len(matched) / top_k if relevant else None,
        "reciprocal_rank": next((1 / rank for rank, video_id in enumerate(ranked, 1) if video_id in relevant), 0.0) if relevant else None,
        "foreign_or_unknown_video_ids": [video_id for video_id in retrieved_ids if owners.get(video_id) != case.user_id],
    }


def evaluate_store(dataset: EvaluationDataset, store: ChromaVectorStore, top_k: int) -> dict:
    if not 1 <= top_k <= 10:
        raise ValueError("top_k must be between 1 and 10")
    for video in dataset.videos:
        store.upsert_video_document(
            vector_id=f"video:{video.id}", user_id=video.user_id, video_id=video.id,
            title=video.title, url=str(video.source_url) if video.source_url else f"https://example.com/evaluation/{video.id}",
            category=None, source=None, document=video.document,
        )
    owners = {video.id: video.user_id for video in dataset.videos}
    cases = [score_case(
        case,
        [item.video_id for item in store.query_video_documents(user_id=case.user_id, query=case.question, limit=top_k)],
        owners, top_k,
    ) for case in dataset.cases]
    positives = [case for case in cases if case["hit"] is not None]
    return {
        "video_count": len(dataset.videos),
        "case_count": len(cases),
        "relevance_case_count": len(positives),
        "empty_library_case_count": len(cases) - len(positives),
        "metrics": {
            "hit_rate_at_k": sum(case["hit"] for case in positives) / len(positives),
            "recall_at_k": sum(case["recall"] for case in positives) / len(positives),
            "precision_at_k": sum(case["precision"] for case in positives) / len(positives),
            "mrr_at_k": sum(case["reciprocal_rank"] for case in positives) / len(positives),
        },
        "privacy_violation_count": sum(bool(case["foreign_or_unknown_video_ids"]) for case in cases),
        "cases": cases,
    }


def run_evaluation(
    dataset: EvaluationDataset, *, provider: Literal["local_hash", "bge_zh"], top_k: int,
    chunk_size: int = DOCUMENT_CHUNK_SIZE, chunk_overlap: int = DOCUMENT_CHUNK_OVERLAP,
    candidate_multiplier: int = DOCUMENT_CANDIDATE_MULTIPLIER,
) -> dict:
    # This CLI runs in its own process. No database or persistent vector client is opened.
    previous = settings.embedding_provider, settings.chroma_collection
    settings.embedding_provider = provider
    settings.chroma_collection = f"retrieval_eval_{uuid4().hex}"
    collection = None
    try:
        client = chromadb.EphemeralClient(settings=ChromaSettings(anonymized_telemetry=False))
        store = ChromaVectorStore(
            client=client, chunk_size=chunk_size, chunk_overlap=chunk_overlap,
            candidate_multiplier=candidate_multiplier,
        )
        collection = store._collection()
        report = evaluate_store(dataset, store, top_k)
        return {
            "schema_version": 1,
            "dataset_name": dataset.name,
            "dataset_sha256": hashlib.sha256(dataset.model_dump_json(exclude_none=True).encode()).hexdigest(),
            "provider": provider,
            "embedding_model": settings.embedding_model if provider == "bge_zh" else None,
            "embedding_dimensions": settings.embedding_dimensions if provider == "local_hash" else None,
            "top_k": top_k,
            "scope": "retrieval_only_no_generation",
            "chunking": {"size": chunk_size, "overlap": chunk_overlap, "candidate_multiplier": candidate_multiplier} if provider == "bge_zh" else None,
            **report,
        }
    finally:
        try:
            if collection is not None:
                client.delete_collection(collection.name)
        finally:
            settings.embedding_provider, settings.chroma_collection = previous


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--provider", choices=("local_hash", "bge_zh"), default="local_hash")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--chunk-size", type=int, default=DOCUMENT_CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=DOCUMENT_CHUNK_OVERLAP)
    parser.add_argument("--candidate-multiplier", type=int, default=DOCUMENT_CANDIDATE_MULTIPLIER)
    parser.add_argument("--output", type=Path, help="Optional JSON report file")
    parser.add_argument("--min-recall", type=float, help="Fail when mean recall@k is below this value")
    args = parser.parse_args(argv)
    if not 1 <= args.top_k <= 10:
        parser.error("--top-k must be between 1 and 10")
    if args.min_recall is not None and not 0 <= args.min_recall <= 1:
        parser.error("--min-recall must be between 0 and 1")
    if not 1 <= args.chunk_size <= 4096 or not 0 <= args.chunk_overlap < args.chunk_size:
        parser.error("--chunk-size must be 1..4096 and --chunk-overlap must be smaller")
    if not 1 <= args.candidate_multiplier <= 20:
        parser.error("--candidate-multiplier must be 1..20")
    if args.provider == "local_hash" and (
        args.chunk_size != DOCUMENT_CHUNK_SIZE or args.chunk_overlap != DOCUMENT_CHUNK_OVERLAP
        or args.candidate_multiplier != DOCUMENT_CANDIDATE_MULTIPLIER
    ):
        parser.error("chunk and candidate options require --provider bge_zh")
    try:
        dataset = EvaluationDataset.model_validate_json(args.dataset.read_text(encoding="utf-8"))
        report = run_evaluation(
            dataset, provider=args.provider, top_k=args.top_k,
            chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap,
            candidate_multiplier=args.candidate_multiplier,
        )
        privacy_passed = report["privacy_violation_count"] == 0
        recall_passed = None if args.min_recall is None else report["metrics"]["recall_at_k"] >= args.min_recall
        report["checks"] = {"privacy_passed": privacy_passed, "recall_threshold_passed": recall_passed}
        report["passed"] = privacy_passed and recall_passed is not False
        report["minimum_recall"] = args.min_recall
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0 if report["passed"] else 1
    except (OSError, ValueError, ApiError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
