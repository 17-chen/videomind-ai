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
from app.models import AiSettings, Embedding, Summary, Transcript, User, Video, VideoTask  # noqa: F401
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
