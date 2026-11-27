"""Actual RLS and repeatable-read checks in a disposable PostgreSQL database."""
from datetime import UTC, datetime, timedelta
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.base import Base
from app.models import User, Video, VideoTask
from app.services.task_monitoring import task_queue_snapshot
from app.services.operations_monitoring import OperationsThresholds, operations_snapshot
from scripts import task_queue_status

pytestmark = pytest.mark.skipif(os.environ.get('RUN_POSTGRES_QUOTA_TESTS') != '1', reason='Disposable PostgreSQL opt-in')
NOW = datetime(2026, 11, 27, tzinfo=UTC)


@pytest.fixture
def postgres_queue():
    admin = create_engine(settings.database_url, isolation_level='AUTOCOMMIT')
    database = 'vm_monitor_test_' + uuid4().hex
    engine = None
    created = False
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database}"')
            created = True
        engine = create_engine(admin.url.set(database=database))
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            user = User(email='synthetic-queue@example.com', password_hash='synthetic')
            db.add(VideoTask(user=user, video=Video(user=user, url='https://example.com/synthetic', tags=[]),
                             kind='process', status='running', worker_id='synthetic-worker',
                             lease_expires_at=NOW + timedelta(seconds=60)))
            db.commit()
            owner = user.id
        yield engine, owner
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.connect() as connection:
                connection.exec_driver_sql(f'DROP DATABASE "{database}"')
        admin.dispose()


@pytest.mark.parametrize('operation', ['snapshot', 'operations', 'cli'])
def test_rls_hidden_queue_never_reports_empty_or_healthy(postgres_queue, tmp_path, monkeypatch, capsys, operation):
    engine, _ = postgres_queue
    role = 'vm_monitor_' + uuid4().hex[:12]
    with engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE ROLE "{role}" NOLOGIN')
        connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO "{role}"')
        connection.exec_driver_sql(f'GRANT SELECT ON video_tasks TO "{role}"')
        connection.exec_driver_sql('ALTER TABLE video_tasks ENABLE ROW LEVEL SECURITY')
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql(f'SET ROLE "{role}"')
            connection.commit()
            try:
                assert connection.scalar(text('SELECT count(*) FROM video_tasks')) == 0
                connection.commit()
                def factory():
                    return Session(bind=connection)
                if operation == 'snapshot':
                    with factory() as db, pytest.raises(ValueError, match='unfiltered backend view'):
                        task_queue_snapshot(db)
                elif operation == 'operations':
                    report = operations_snapshot(factory, roots=[tmp_path], thresholds=OperationsThresholds(min_free_mb=0))
                    assert report['status'] == 'unavailable' and report['unavailable'] == ['queue_read_failed']
                    assert report['checks']['local_disk']['status'] == 'ok'
                else:
                    monkeypatch.setattr(task_queue_status, 'SessionLocal', factory)
                    assert task_queue_status.main() == 2
                    assert json.loads(capsys.readouterr().out)['reason'] == 'queue_read_failed'
            finally:
                connection.rollback()
                connection.exec_driver_sql('RESET ROLE')
                connection.commit()
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(f'DROP OWNED BY "{role}"')
            connection.exec_driver_sql(f'DROP ROLE "{role}"')


def test_all_metrics_use_one_read_only_snapshot_during_concurrent_insert(postgres_queue):
    engine, owner = postgres_queue
    inserted, read_only = [], []
    def add_after_counts(connection, cursor, statement, *args):
        if 'GROUP BY video_tasks.status' not in statement or inserted:
            return
        inserted.append(True)
        read_only.append(connection.exec_driver_sql('SHOW transaction_read_only').scalar())
        with Session(engine) as writer:
            user = writer.get(User, owner)
            writer.add(VideoTask(user=user, video=Video(user=user, url='https://example.com/second', tags=[]),
                                 kind='process', status='running'))
            writer.commit()
    event.listen(engine, 'after_cursor_execute', add_after_counts)
    try:
        with Session(engine) as db:
            report = task_queue_snapshot(db, now=NOW)
            assert report['running'] == 1 and report['invalid_running_leases'] == 0
    finally:
        event.remove(engine, 'after_cursor_execute', add_after_counts)
    assert read_only == ['on']
    with Session(engine) as db:
        report = task_queue_snapshot(db, now=NOW)
        assert report['running'] == 2 and report['invalid_running_leases'] == 1
