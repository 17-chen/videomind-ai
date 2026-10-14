import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models import AiSettings, Embedding, Summary, Transcript, User, Video  # noqa: F401
from scripts import reindex_vectors


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            User(id="alice", email="alice@example.com", password_hash="unused"),
            User(id="bob", email="bob@example.com", password_hash="unused"),
        ])
        session.add_all([
            Video(id="01", user_id="alice", url="https://example.com/1", transcript=Transcript(content="first")),
            Video(id="02", user_id="alice", url="https://example.com/2", transcript=Transcript(content="second")),
            Video(id="03", user_id="alice", url="https://example.com/3"),
            Video(id="04", user_id="bob", url="https://example.com/4", transcript=Transcript(content="fourth")),
        ])
        session.commit()
        yield session
    engine.dispose()


def test_dry_run_filters_user_and_never_calls_indexer(db):
    def unexpected_index(*_):
        raise AssertionError("dry-run must not index")

    result = reindex_vectors.reindex_videos(db, user_id="alice", dry_run=True, indexer=unexpected_index)

    assert (result.scanned, result.eligible, result.indexed, result.skipped) == (3, 2, 0, 1)
    assert result.failed_video_ids == []


def test_failure_rolls_back_and_continues_with_next_video(db):
    calls = []

    def flaky_index(session, video):
        calls.append(video.id)
        if video.id == "02":
            session.add(Video(id="temporary", user_id="alice", url="https://example.com/temp"))
            raise RuntimeError("vector store unavailable")

    result = reindex_vectors.reindex_videos(db, indexer=flaky_index)

    assert calls == ["01", "02", "04"]
    assert (result.scanned, result.eligible, result.indexed, result.skipped) == (4, 3, 2, 1)
    assert result.failed_video_ids == ["02"]
    assert db.get(Video, "temporary") is None


def test_limit_counts_scanned_videos_in_id_order(db):
    indexed = []

    result = reindex_vectors.reindex_videos(
        db, limit=2, indexer=lambda _session, video: indexed.append(video.id)
    )

    assert indexed == ["01", "02"]
    assert (result.scanned, result.indexed) == (2, 2)


def test_scan_continues_after_first_id_batch(db):
    db.add_all([
        Video(
            id=f"{number:03d}",
            user_id="bob",
            url=f"https://example.com/{number}",
            transcript=Transcript(content="content"),
        )
        for number in range(5, 106)
    ])
    db.commit()
    indexed = []

    result = reindex_vectors.reindex_videos(db, indexer=lambda _session, video: indexed.append(video.id))

    assert result.scanned == 105
    assert result.indexed == 104
    assert len(indexed) == 104
    assert indexed[-1] == "105"


def test_cli_reports_failure_and_returns_nonzero(db, monkeypatch, capsys):
    monkeypatch.setattr(reindex_vectors, "SessionLocal", lambda: db)
    received = {}

    def fake_reindex(session, **kwargs):
        received.update(kwargs)
        return reindex_vectors.ReindexResult(scanned=1, eligible=1, failed_video_ids=["01"])

    monkeypatch.setattr(reindex_vectors, "reindex_videos", fake_reindex)

    assert reindex_vectors.main(["--user-id", "alice", "--limit", "1"]) == 1
    assert received == {"user_id": "alice", "limit": 1, "dry_run": False}
    output = capsys.readouterr().out
    assert "failed=1" in output
    assert "Failed video IDs: 01" in output
