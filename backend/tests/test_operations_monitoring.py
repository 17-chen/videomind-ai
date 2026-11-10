from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.base import Base
from app.models import User, Video, VideoTask
from app.services import operations_monitoring as monitor
from app.services.operations_monitoring import OperationsThresholds
from scripts import check_operations


NOW = datetime(2026, 11, 10, 6, tzinfo=UTC)
MB = 1024 * 1024


@pytest.fixture
def queue(monkeypatch):
    engine = create_engine('sqlite+pysqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email='operator-private@example.com', password_hash='test')
        for state in ('queued', 'running', 'failed'):
            video = Video(user=user, url='https://example.com/private', tags=[])
            db.add(VideoTask(video=video, user=user, kind='process', status=state,
                created_at=NOW - timedelta(seconds=301),
                lease_expires_at=NOW - timedelta(seconds=1) if state == 'running' else None,
                finished_at=NOW - timedelta(minutes=30) if state == 'failed' else None,
                error='private-provider-error' if state == 'failed' else None))
        db.commit()
        private = [user.id, user.email, *(db.scalars(select(VideoTask.id))),
                   *(db.scalars(select(Video.id))), 'private-provider-error']
    monkeypatch.setattr(monitor.shutil, 'disk_usage', lambda _: SimpleNamespace(free=2 * MB))
    try:
        yield lambda: Session(engine), private
    finally:
        engine.dispose()


def test_thresholds_report_independent_alerts_without_mutations_or_private_data(queue, tmp_path):
    factory, private = queue
    marker = tmp_path / 'private-video.mp4'
    marker.write_bytes(b'private contents')
    before = marker.stat()
    report = monitor.operations_snapshot(factory, roots=[tmp_path], now=NOW,
        thresholds=OperationsThresholds(min_free_mb=3))
    assert report['status'] == 'attention'
    assert report['alerts'] == ['queue_wait_exceeded', 'expired_leases_exceeded',
                                'recent_failures_exceeded', 'local_disk_free_below_minimum']
    assert report['checks']['queue']['status'] == 'attention'
    assert report['checks']['local_disk']['status'] == 'attention'
    assert report['mutations_performed'] is False
    assert report['unavailable'] == []
    with factory() as db:
        assert sorted(db.scalars(select(VideoTask.status))) == ['failed', 'queued', 'running']
    assert marker.stat().st_mtime_ns == before.st_mtime_ns
    assert marker.read_bytes() == b'private contents'
    serialized = json.dumps(report)
    for value in [*private, str(tmp_path), marker.name]:
        assert value not in serialized


def test_exact_thresholds_and_duplicate_filesystems_are_healthy(queue, tmp_path):
    factory, _ = queue
    future_root = tmp_path / 'not-created' / 'notes'
    report = monitor.operations_snapshot(factory, roots=[tmp_path, future_root], now=NOW,
        thresholds=OperationsThresholds(max_queued_seconds=301, max_expired_leases=1,
                                        max_failures_last_hour=1, min_free_mb=2))
    assert report['status'] == 'ok'
    assert report['alerts'] == []
    assert report['checks']['local_disk']['filesystems_checked'] == 1
    assert not future_root.parent.exists()


def test_unavailable_queue_does_not_hide_low_disk_or_leak_exception(tmp_path, monkeypatch):
    def broken():
        raise RuntimeError('postgresql://private-user:private-token@private-host')
    monkeypatch.setattr(monitor.shutil, 'disk_usage', lambda _: SimpleNamespace(free=0))
    report = monitor.operations_snapshot(broken, roots=[tmp_path],
        thresholds=OperationsThresholds(min_free_mb=1))
    assert report['status'] == 'unavailable'
    assert report['checks']['queue'] == {'status': 'unavailable'}
    assert report['alerts'] == ['local_disk_free_below_minimum']
    assert report['unavailable'] == ['queue_read_failed']
    assert 'private' not in json.dumps(report)


def test_partial_disk_failure_preserves_queue_alerts_and_known_low_space(queue, tmp_path, monkeypatch):
    factory, _ = queue
    real = monitor._existing_directory
    blocked = tmp_path / 'blocked'
    def directory(path):
        if path == blocked:
            raise PermissionError('private path must not appear')
        return real(path)
    monkeypatch.setattr(monitor, '_existing_directory', directory)
    report = monitor.operations_snapshot(factory, roots=[tmp_path, blocked], now=NOW,
        thresholds=OperationsThresholds(min_free_mb=3))
    assert report['status'] == 'unavailable'
    assert report['checks']['local_disk']['read_errors'] == 1
    assert report['checks']['local_disk']['minimum_free_bytes'] == 2 * MB
    assert 'queue_wait_exceeded' in report['alerts']
    assert 'local_disk_free_below_minimum' in report['alerts']
    assert 'private path' not in json.dumps(report)


@pytest.mark.parametrize('kind', ['file', 'broken_link', 'no_roots'])
def test_invalid_storage_target_is_unavailable_not_healthy(queue, tmp_path, kind):
    factory, _ = queue
    root = tmp_path / 'invalid'
    if kind == 'file':
        root.write_text('untouched')
    elif kind == 'broken_link':
        root.symlink_to(tmp_path / 'missing')
    report = monitor.operations_snapshot(factory, roots=[] if kind == 'no_roots' else [root],
        now=NOW, thresholds=OperationsThresholds(min_free_mb=0))
    assert report['status'] == 'unavailable'
    assert report['unavailable'] == ['local_disk_read_failed']
    assert report['checks']['local_disk']['minimum_free_bytes'] is None


@pytest.mark.parametrize('expected', [0, 1, 2])
def test_cli_exit_status_and_json_are_usable_for_external_monitors(queue, monkeypatch, capsys, expected):
    factory, private = queue
    monkeypatch.setattr(check_operations, 'SessionLocal', factory)
    real_snapshot = monitor.operations_snapshot
    monkeypatch.setattr(check_operations, 'operations_snapshot',
        lambda *args, **kwargs: real_snapshot(*args, **kwargs, now=NOW))
    args = ['--max-queued-seconds', '301', '--max-expired-leases', '1',
            '--max-failures-last-hour', '1', '--min-free-mb', '2']
    if expected == 1:
        args[-1] = '3'
    elif expected == 2:
        def broken():
            raise RuntimeError('private-connection')
        monkeypatch.setattr(check_operations, 'SessionLocal', broken)
    assert check_operations.main(args) == expected
    output = capsys.readouterr().out
    assert json.loads(output)['status'] == {0: 'ok', 1: 'attention', 2: 'unavailable'}[expected]
    for value in [*private, settings.video_storage_dir, 'private-connection']:
        assert value not in output


def test_negative_threshold_rejected_before_any_read(monkeypatch):
    monkeypatch.setattr(check_operations, 'operations_snapshot', lambda *args, **kwargs: pytest.fail('must not read'))
    with pytest.raises(SystemExit) as exc:
        check_operations.main(['--max-queued-seconds', '-1'])
    assert exc.value.code == 2
    with pytest.raises(ValueError):
        OperationsThresholds(min_free_mb=-1)
