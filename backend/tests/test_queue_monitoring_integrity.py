"""Synthetic queue anomalies must not produce a healthy operational report."""
from datetime import UTC, datetime, timedelta
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models import User, Video, VideoTask
from app.services.task_monitoring import task_queue_snapshot
from app.services.operations_monitoring import OperationsThresholds, operations_snapshot
from scripts import task_queue_status

NOW = datetime(2026, 11, 27, tzinfo=UTC)


@pytest.fixture
def queue_db():
    engine = create_engine('sqlite+pysqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email='synthetic-monitor@example.com', password_hash='synthetic')
        task = VideoTask(user=user, video=Video(user=user, url='https://example.com/synthetic', tags=[]),
                         kind='process', status='running', worker_id='synthetic-worker',
                         lease_expires_at=NOW + timedelta(seconds=60))
        db.add(task)
        db.commit()
        task_id = task.id
    try:
        yield engine, task_id
    finally:
        engine.dispose()


@pytest.mark.parametrize('worker,lease', [(None, 'future'), ('', 'future'), ('  ', 'future'), ('worker', None), (None, None)])
def test_incomplete_running_lease_is_counted_and_alerts(queue_db, tmp_path, worker, lease):
    engine, task_id = queue_db
    with Session(engine) as db:
        task = db.get(VideoTask, task_id)
        task.worker_id = worker
        task.lease_expires_at = NOW + timedelta(seconds=60) if lease else None
        db.commit()
    report = operations_snapshot(lambda: Session(engine), roots=[tmp_path], now=NOW,
                                 thresholds=OperationsThresholds(min_free_mb=0))
    assert report['status'] == 'attention'
    assert report['checks']['queue']['invalid_running_leases'] == 1
    assert report['alerts'] == ['invalid_running_leases_detected']
    assert report['mutations_performed'] is False
    assert task_id not in json.dumps(report)


def test_unknown_status_is_anonymous_attention_instead_of_disappearing(queue_db, tmp_path):
    engine, task_id = queue_db
    with Session(engine) as db:
        db.get(VideoTask, task_id).status = 'private-sentinel'
        db.commit()
    report = operations_snapshot(lambda: Session(engine), roots=[tmp_path], now=NOW,
                                 thresholds=OperationsThresholds(min_free_mb=0))
    assert report['status'] == 'attention' and report['alerts'] == ['unknown_task_status_detected']
    assert report['checks']['queue']['unknown_status_tasks'] == 1
    assert 'private-sentinel' not in json.dumps(report)
    with Session(engine) as db:
        assert db.get(VideoTask, task_id).status == 'private-sentinel'


@pytest.mark.parametrize('seconds,expired', [(0, 1), (1, 0)])
def test_lease_deadline_is_expired_at_exact_boundary(queue_db, seconds, expired):
    engine, task_id = queue_db
    with Session(engine) as db:
        db.get(VideoTask, task_id).lease_expires_at = NOW + timedelta(seconds=seconds)
        db.commit()
        assert task_queue_snapshot(db, now=NOW)['expired_leases'] == expired


@pytest.mark.parametrize('change', ['new', 'dirty', 'deleted'])
def test_monitor_refuses_to_autoflush_caller_changes(queue_db, change):
    engine, task_id = queue_db
    with Session(engine) as db:
        if change == 'new':
            db.add(User(email='uncommitted@example.com', password_hash='synthetic'))
        elif change == 'dirty':
            db.get(VideoTask, task_id).status = 'failed'
        else:
            db.delete(db.get(VideoTask, task_id))
        with pytest.raises(ValueError, match='clean dedicated session'):
            task_queue_snapshot(db, now=NOW)
    with Session(engine) as db:
        assert db.get(VideoTask, task_id).status == 'running'
        assert len(db.scalars(select(User)).all()) == 1


def test_queue_cli_reports_fixed_unavailable_without_sql_or_identity(monkeypatch, capsys):
    def unavailable():
        raise RuntimeError('postgresql://private-user:private-key@private-host')
    monkeypatch.setattr(task_queue_status, 'SessionLocal', unavailable)
    assert task_queue_status.main() == 2
    assert json.loads(capsys.readouterr().out) == {
        'status': 'unavailable', 'reason': 'queue_read_failed', 'mutations_performed': False,
    }


def test_queue_cli_success_preserves_additive_counts(queue_db, monkeypatch, capsys):
    engine, _ = queue_db
    monkeypatch.setattr(task_queue_status, 'SessionLocal', lambda: Session(engine))
    assert task_queue_status.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report['running'] == 1 and report['unknown_status_tasks'] == 0
