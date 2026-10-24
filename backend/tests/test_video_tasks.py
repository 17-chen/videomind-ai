from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import dependencies
from app.api.dependencies import get_db
from app.core.config import settings
from app.database.base import Base
from app.main import app
from app.models import AiSettings, Embedding, RequestWindow, Summary, Transcript, User, Video, VideoTask  # noqa: F401
from app.services import video_tasks
from app.services.auth import AuthIdentity


@pytest.fixture
def task_api(monkeypatch):
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "auth_mode", "supabase")
    monkeypatch.setattr(dependencies, "decode_supabase_token", lambda token: AuthIdentity(subject=token, email=f"{token}@example.com"))

    def db_session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = db_session
    try:
        with TestClient(app) as client:
            yield client, engine
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def auth(name):
    return {"Authorization": f"Bearer {name}"}


def create_video(client):
    result = client.post("/api/v1/videos", headers=auth("alice"), json={"url": "https://example.com/task-video", "tags": []})
    assert result.status_code == 201
    return result.json()["id"]


def test_task_is_durable_owned_and_cancelled_before_claim(task_api):
    client, engine = task_api
    video_id = create_video(client)
    url = f"/api/v1/videos/{video_id}"
    started = client.post(url + "/process", headers=auth("alice"))
    assert started.status_code == 202
    assert started.json()["status"] == "queued"
    assert client.post(url + "/process", headers=auth("alice")).status_code == 409
    assert client.get(url + "/task", headers=auth("bob")).status_code == 404
    assert client.post(url + "/task/cancel", headers=auth("bob")).status_code == 404
    assert client.get(url + "/task", headers=auth("alice")).json()["id"] == started.json()["task_id"]

    # The API session has closed; a fresh worker session can still see the queued task.
    with Session(engine) as db:
        assert db.get(VideoTask, started.json()["task_id"]).status == "queued"
    cancelled = client.post(url + "/task/cancel", headers=auth("alice"))
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    with Session(engine) as db:
        assert video_tasks.claim_next_task(db, "worker-a") is None
    assert client.get(url, headers=auth("alice")).json()["status"] == "cancelled"
    assert client.post(url + "/task/cancel", headers=auth("alice")).status_code == 409


def test_user_task_limit_counts_queued_and_running_and_releases_cancelled(task_api, monkeypatch):
    client, engine = task_api
    monkeypatch.setattr(settings, "max_active_video_tasks_per_user", 2)
    first, second, third = [create_video(client) for _ in range(3)]
    assert client.post(f"/api/v1/videos/{first}/process", headers=auth("alice")).status_code == 202
    with Session(engine) as db:
        assert video_tasks.claim_next_task(db, "worker-a").video_id == first
    assert client.post(f"/api/v1/videos/{second}/process", headers=auth("alice")).status_code == 202
    assert client.post(f"/api/v1/videos/{first}/process", headers=auth("alice")).status_code == 409

    limited = client.post(f"/api/v1/videos/{third}/process", headers=auth("alice"))
    assert limited.status_code == 429
    assert "任务已达上限" in limited.json()["detail"]
    assert client.get(f"/api/v1/videos/{third}", headers=auth("alice")).json()["status"] == "created"
    with Session(engine) as db:
        assert db.query(VideoTask).filter(VideoTask.user_id == db.get(Video, first).user_id).count() == 2

    bob = client.post("/api/v1/videos", headers=auth("bob"), json={"url": "https://example.com/bob-video", "tags": []})
    assert bob.status_code == 201
    assert client.post(f"/api/v1/videos/{bob.json()['id']}/process", headers=auth("bob")).status_code == 202
    assert client.post(f"/api/v1/videos/{second}/task/cancel", headers=auth("alice")).status_code == 200
    assert client.post(f"/api/v1/videos/{third}/process", headers=auth("alice")).status_code == 202


def test_video_task_request_rate_limit_counts_successful_admissions(task_api, monkeypatch):
    client, _ = task_api
    monkeypatch.setattr(settings, "max_video_task_requests_per_minute", 2)
    first, second, third = [create_video(client) for _ in range(3)]
    for video_id in (first, second):
        assert client.post(f"/api/v1/videos/{video_id}/process", headers=auth("alice")).status_code == 202
        assert client.post(f"/api/v1/videos/{video_id}/task/cancel", headers=auth("alice")).status_code == 200
    rejected = client.post(f"/api/v1/videos/{third}/process", headers=auth("alice"))
    assert rejected.status_code == 429
    assert "频繁" in rejected.json()["detail"]
    assert client.get(f"/api/v1/videos/{third}", headers=auth("alice")).json()["status"] == "created"


def test_video_task_request_rate_limit_counts_duplicate_attempts(task_api, monkeypatch):
    client, _ = task_api
    monkeypatch.setattr(settings, "max_video_task_requests_per_minute", 2)
    first, second = [create_video(client) for _ in range(2)]
    assert client.post(f"/api/v1/videos/{first}/process", headers=auth("alice")).status_code == 202
    assert client.post(f"/api/v1/videos/{first}/process", headers=auth("alice")).status_code == 409
    assert client.post(f"/api/v1/videos/{second}/process", headers=auth("alice")).status_code == 429


def test_chat_rate_limit_is_per_user(task_api, monkeypatch):
    client, _ = task_api
    monkeypatch.setattr(settings, "max_chat_requests_per_minute", 1)
    payload = {"question": "What is in my library?", "language": "en"}
    assert client.post("/api/v1/chat", headers=auth("alice"), json=payload).status_code == 200
    assert client.post("/api/v1/chat", headers=auth("alice"), json=payload).status_code == 429
    assert client.post("/api/v1/chat", headers=auth("bob"), json=payload).status_code == 200


def test_worker_claim_and_resume_policy(task_api):
    client, engine = task_api
    video_id = create_video(client)
    started = client.post(f"/api/v1/videos/{video_id}/process", headers=auth("alice"))
    with Session(engine) as db:
        task = video_tasks.claim_next_task(db, "worker-a")
        assert task.id == started.json()["task_id"]
        assert task.attempts == 1
        assert video_tasks.claim_next_task(db, "worker-b") is None
        original_lease = task.lease_expires_at
        assert video_tasks.extend_task_lease(db, task.id, "worker-b") is False
        assert video_tasks.extend_task_lease(db, task.id, "worker-a") is True
        db.refresh(task)
        assert task.lease_expires_at >= original_lease
        task.stage = "transcription"
        task.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    with Session(engine) as db:
        assert video_tasks.recover_expired_tasks(db) == 1
        task = video_tasks.claim_next_task(db, "worker-b")
        assert task.attempts == 2
        assert task.worker_id == "worker-b"

    with Session(engine) as db:
        task = db.get(VideoTask, started.json()["task_id"])
        task.stage = "analysis"
        task.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    with Session(engine) as db:
        assert video_tasks.recover_expired_tasks(db) == 1
        task = db.get(VideoTask, started.json()["task_id"])
        assert task.status == "failed"
        assert "重复计费" in task.error
        assert video_tasks.claim_next_task(db, "worker-c") is None


def test_running_cancellation_is_owned_and_seen_by_worker(task_api, monkeypatch):
    client, engine = task_api
    video_id = create_video(client)
    url = f"/api/v1/videos/{video_id}"
    started = client.post(url + "/process", headers=auth("alice"))
    with Session(engine) as db:
        video_tasks.claim_next_task(db, "worker-a")
    assert client.post(url + "/task/cancel", headers=auth("bob")).status_code == 404
    result = client.post(url + "/task/cancel", headers=auth("alice"))
    assert result.status_code == 200
    assert result.json()["status"] == "running"
    assert result.json()["cancel_requested_at"] is not None
    monkeypatch.setattr(video_tasks, "process_video", lambda *args, **kwargs: pytest.fail("cancelled task must not process"))
    with Session(engine) as db:
        video_tasks.execute_claimed_task(db, started.json()["task_id"], "worker-a")
        assert db.get(VideoTask, started.json()["task_id"]).status == "cancelled"


def test_running_cancel_stops_before_next_stage(task_api, monkeypatch):
    client, engine = task_api
    video_id = create_video(client)
    started = client.post(f"/api/v1/videos/{video_id}/run", headers=auth("alice"))
    assert started.status_code == 400  # A missing personal model key is rejected before paid work is queued.

    # Exercise cancellation at a worker checkpoint without calling external services.
    with Session(engine) as db:
        video = db.get(Video, video_id)
        task = video_tasks.enqueue_video_task(db, video.user, video, "run")
        task_id = task.id
    with Session(engine) as db:
        task = video_tasks.claim_next_task(db, "worker-a")
        assert task.id == task_id

    called = []

    def fake_process(db, video, final_status):
        called.append("transcription")
        with Session(engine) as other:
            other_task = other.get(VideoTask, task_id)
            other_task.cancel_requested_at = datetime.now(UTC)
            other.commit()
        return video

    monkeypatch.setattr(video_tasks, "process_video", fake_process)
    monkeypatch.setattr(video_tasks, "analyze_video", lambda *args: called.append("analysis"))
    monkeypatch.setattr(video_tasks, "index_video", lambda *args: called.append("embedding"))
    with Session(engine) as db:
        video_tasks.execute_claimed_task(db, task_id, "worker-a")
    assert called == ["transcription"]
    with Session(engine) as db:
        assert db.get(VideoTask, task_id).status == "cancelled"
        assert db.get(Video, video_id).status == "cancelled"


@pytest.mark.parametrize("raise_after_takeover", [False, True])
def test_old_worker_cannot_advance_or_fail_reclaimed_task(task_api, monkeypatch, raise_after_takeover):
    client, engine = task_api
    video_id = create_video(client)
    with Session(engine) as db:
        video = db.get(Video, video_id)
        task_id = video_tasks.enqueue_video_task(db, video.user, video, "run").id
        video_tasks.claim_next_task(db, "worker-a")

    called = []

    def interrupted_process(db, video, final_status):
        with Session(engine) as other:
            task = other.get(VideoTask, task_id)
            task.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            other.commit()
            assert video_tasks.recover_expired_tasks(other) == 1
            assert video_tasks.claim_next_task(other, "worker-b").id == task_id
        if raise_after_takeover:
            raise RuntimeError("old worker stage failed after lease takeover")

    monkeypatch.setattr(video_tasks, "process_video", interrupted_process)
    monkeypatch.setattr(video_tasks, "analyze_video", lambda *args: called.append("analysis"))
    monkeypatch.setattr(video_tasks, "index_video", lambda *args: called.append("embedding"))
    with Session(engine) as db:
        video_tasks.execute_claimed_task(db, task_id, "worker-a")

    assert called == []
    with Session(engine) as db:
        task = db.get(VideoTask, task_id)
        assert task.status == "running"
        assert task.worker_id == "worker-b"
        assert task.error is None


def test_run_retry_after_vector_failure_reuses_transcript_and_summary(task_api, monkeypatch):
    client, engine = task_api
    video_id = create_video(client)
    calls = {"transcription": 0, "analysis": 0, "embedding": 0}

    def fake_process(db, video, final_status):
        calls["transcription"] += 1
        video.transcript = Transcript(content="Recovered transcript")
        db.commit()

    def fake_analyze(db, video):
        calls["analysis"] += 1
        video.summary = Summary(summary="Recovered summary")
        db.commit()

    def flaky_index(db, video):
        calls["embedding"] += 1
        if calls["embedding"] == 1:
            raise RuntimeError("temporary vector outage")
        video.embedding = Embedding(vector_id=f"video:{video.id}")
        db.commit()

    monkeypatch.setattr(video_tasks, "process_video", fake_process)
    monkeypatch.setattr(video_tasks, "analyze_video", fake_analyze)
    monkeypatch.setattr(video_tasks, "index_video", flaky_index)

    with Session(engine) as db:
        video = db.get(Video, video_id)
        first_id = video_tasks.enqueue_video_task(db, video.user, video, "run").id
        assert video_tasks.claim_next_task(db, "worker-a").id == first_id
        video_tasks.execute_claimed_task(db, first_id, "worker-a")
        assert db.get(VideoTask, first_id).status == "failed"
        assert db.get(Video, video_id).transcript.content == "Recovered transcript"
        assert db.get(Video, video_id).summary.summary == "Recovered summary"

    retry = client.post(f"/api/v1/videos/{video_id}/run", headers=auth("alice"))
    assert retry.status_code == 202
    with Session(engine) as db:
        retry_id = retry.json()["task_id"]
        assert video_tasks.claim_next_task(db, "worker-b").id == retry_id
        video_tasks.execute_claimed_task(db, retry_id, "worker-b")
        assert db.get(VideoTask, retry_id).status == "succeeded"
        video = db.get(Video, video_id)
        assert video.embedding.vector_id == f"video:{video_id}"
        assert video.status == "completed"
    assert calls == {"transcription": 1, "analysis": 1, "embedding": 2}
