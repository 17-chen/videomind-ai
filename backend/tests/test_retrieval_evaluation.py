import json

import pytest
from pydantic import ValidationError

from app.core.config import settings
from scripts import evaluate_retrieval as evaluation


def sample_dataset():
    return evaluation.EvaluationDataset.model_validate({
        "name": "test-corpus",
        "videos": [
            {"id": "math", "user_id": "alice", "title": "Math", "document": "linear algebra matrices"},
            {"id": "cooking", "user_id": "alice", "title": "Cooking", "document": "tomato egg recipe"},
            {"id": "private", "user_id": "bob", "title": "Private", "document": "linear algebra matrices"},
        ],
        "cases": [
            {"id": "math", "user_id": "alice", "question": "linear algebra matrices", "expected_video_ids": ["math"]},
            {"id": "empty", "user_id": "charlie", "question": "linear algebra matrices", "expected_video_ids": []},
        ],
    })


def test_metrics_count_unique_videos_and_detect_other_users_results():
    case = evaluation.EvaluationCase(id="multi", user_id="alice", question="question", expected_video_ids=["a", "b"])
    scored = evaluation.score_case(case, ["foreign", "a", "a", "b"], {"a": "alice", "b": "alice", "foreign": "bob"}, 3)

    assert scored["retrieved_video_ids"] == ["foreign", "a", "b"]
    assert scored["hit"] is True
    assert scored["recall"] == 1
    assert scored["precision"] == pytest.approx(2 / 3)
    assert scored["reciprocal_rank"] == 0.5
    assert scored["foreign_or_unknown_video_ids"] == ["foreign"]


@pytest.mark.parametrize("expected", [["private"], ["missing"], ["math", "math"]])
def test_dataset_rejects_invalid_answer_references(expected):
    payload = sample_dataset().model_dump()
    payload["cases"][0]["expected_video_ids"] = expected
    with pytest.raises(ValidationError):
        evaluation.EvaluationDataset.model_validate(payload)


def test_real_hash_evaluation_is_isolated_and_excludes_empty_libraries_from_quality_metrics(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "bge_zh")
    monkeypatch.setattr(settings, "chroma_collection", "existing_user_collection")
    report = evaluation.run_evaluation(sample_dataset(), provider="local_hash", top_k=1)

    assert report["metrics"] == {"hit_rate_at_k": 1, "recall_at_k": 1, "precision_at_k": 1, "mrr_at_k": 1}
    assert report["privacy_violation_count"] == 0
    assert report["relevance_case_count"] == report["empty_library_case_count"] == 1
    assert report["cases"][1]["retrieved_video_ids"] == []
    assert report["cases"][1]["hit"] is None
    assert len(report["dataset_sha256"]) == 64
    assert settings.embedding_provider == "bge_zh"
    assert settings.chroma_collection == "existing_user_collection"


def test_public_source_url_is_used_for_indexed_result():
    dataset = sample_dataset()
    dataset.videos[0].source_url = "https://commons.wikimedia.org/wiki/File:Example.webm"

    class RecordingStore:
        def __init__(self):
            self.urls = {}

        def upsert_video_document(self, **kwargs):
            self.urls[kwargs["video_id"]] = kwargs["url"]

        def query_video_documents(self, **kwargs):
            return []

    store = RecordingStore()
    evaluation.evaluate_store(dataset, store, 1)
    assert store.urls["math"] == "https://commons.wikimedia.org/wiki/File:Example.webm"
    assert store.urls["cooking"] == "https://example.com/evaluation/cooking"


def test_failed_evaluation_restores_configuration(monkeypatch):
    before = settings.embedding_provider, settings.chroma_collection

    def fail(*args):
        raise RuntimeError("index failed")

    monkeypatch.setattr(evaluation, "evaluate_store", fail)
    with pytest.raises(RuntimeError, match="index failed"):
        evaluation.run_evaluation(sample_dataset(), provider="local_hash", top_k=3)
    assert (settings.embedding_provider, settings.chroma_collection) == before


@pytest.mark.parametrize(("privacy_count", "recall", "exit_code"), [(0, 0.9, 0), (0, 0.5, 1), (1, 1, 1)])
def test_cli_gates_quality_and_privacy_and_writes_report(monkeypatch, tmp_path, capsys, privacy_count, recall, exit_code):
    monkeypatch.setattr(evaluation, "run_evaluation", lambda *args, **kwargs: {
        "privacy_violation_count": privacy_count, "metrics": {"recall_at_k": recall},
    })
    path = tmp_path / "report.json"
    assert evaluation.main(["--min-recall", "0.8", "--output", str(path)]) == exit_code
    report = json.loads(path.read_text())
    assert report["passed"] is (exit_code == 0)
    assert json.loads(capsys.readouterr().out) == report


def test_cli_rejects_invalid_dataset_before_opening_vector_store(tmp_path, capsys):
    path = tmp_path / "invalid.json"
    path.write_text('{"name":"missing cases"}')
    assert evaluation.main(["--dataset", str(path)]) == 2
    assert "Evaluation failed" in capsys.readouterr().err


@pytest.mark.parametrize("options", [
    ["--chunk-size", "0", "--provider", "bge_zh"],
    ["--chunk-size", "100", "--chunk-overlap", "100", "--provider", "bge_zh"],
    ["--candidate-multiplier", "0", "--provider", "bge_zh"],
    ["--chunk-size", "100"],
])
def test_cli_rejects_invalid_or_irrelevant_chunk_options(options):
    with pytest.raises(SystemExit) as exc:
        evaluation.main(options)
    assert exc.value.code == 2
