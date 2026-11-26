"""Real filesystem locks/processes, synthetic budgets and media only."""

from contextlib import ExitStack
from io import BytesIO
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from fastapi import UploadFile
import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.models import Transcript, VideoTask
from app.services import analysis, temporary_reservations as reservations, video_upload
from app.services.object_storage.repository import materialize_artifact, materialize_artifacts
from app.services.storage_quota import artifact_directory, generate_artifacts
from app.services.temporary_reservations import reserve_temporary_space, reservation_descriptors
from app.services.video_processing.audio import _run_audio_command
from app.services.video_processing import managed_downloader
from test_managed_download import download_job as _download_job
from test_object_storage import ledger as _ledger, publish
from test_temporary_storage import stage_db as _stage_db

# Reuse the existing isolated fixtures without introducing global plugins.
download_job, ledger, stage_db = _download_job, _ledger, _stage_db

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Validated local POSIX flock/descriptor behavior')


@pytest.fixture
def registry(tmp_path, monkeypatch):
    root = tmp_path / 'reservations'
    root.mkdir(mode=0o700)
    monkeypatch.setattr(settings, 'media_reservation_dir', str(root))
    monkeypatch.setattr(reservations.shutil, 'disk_usage', lambda _: SimpleNamespace(free=1000))
    return root


def records(root):
    return list(root.glob('reservation-*'))


def test_disabled_mode_does_not_touch_registry_or_change_exception(monkeypatch, tmp_path):
    monkeypatch.setattr(reservations, '_open_root', lambda _: pytest.fail('Disabled mode must not open registry'))
    with pytest.raises(RuntimeError, match='synthetic-body'):
        with reserve_temporary_space(tmp_path / 'missing', -1):
            assert not reservation_descriptors()
            raise RuntimeError('synthetic-body')


def test_active_reservations_compete_and_release_after_normal_or_error_exit(registry, tmp_path):
    with reserve_temporary_space(tmp_path, 600):
        assert len(reservation_descriptors()) == 1
        with pytest.raises(ApiError) as error:
            with reserve_temporary_space(tmp_path, 401):
                pytest.fail('Budget must be checked before entering')
        assert error.value.status_code == 507
        with reserve_temporary_space(tmp_path, 400):
            assert len(reservation_descriptors()) == 2
        assert len(reservation_descriptors()) == 1
    assert not records(registry) and not reservation_descriptors()
    with pytest.raises(RuntimeError, match='synthetic-body'):
        with reserve_temporary_space(tmp_path, 1000):
            raise RuntimeError('synthetic-body')
    assert not records(registry)
    with reserve_temporary_space(tmp_path, 1000):
        pass


def test_floor_and_already_used_bytes_are_not_credited_twice(registry, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'min_media_free_space_mb', 1)
    free = [1024 * 1024 + 1000]
    monkeypatch.setattr(reservations.shutil, 'disk_usage', lambda _: SimpleNamespace(free=free[0]))
    with reserve_temporary_space(tmp_path, 600):
        free[0] -= 200  # Model some output already having consumed actual disk.
        with pytest.raises(ApiError) as error:
            with reserve_temporary_space(tmp_path, 201):
                pytest.fail('Conservative admission must retain all active bytes')
        assert error.value.status_code == 507
        with reserve_temporary_space(tmp_path, 200):
            pass


@pytest.mark.parametrize('amount', [-1, 2**63, 0.5])
def test_invalid_budgets_fail_closed(registry, tmp_path, amount):
    with pytest.raises(ApiError) as error:
        with reserve_temporary_space(tmp_path, amount):
            pytest.fail('Unsupported budget')
    assert error.value.status_code == 503
    assert str(tmp_path) not in error.value.message


@pytest.mark.parametrize('problem', ['missing', 'public', 'symlink', 'ancestor_symlink', 'parent_component'])
def test_registry_must_be_real_private_directory(registry, tmp_path, monkeypatch, problem):
    target = registry
    if problem == 'missing':
        target = tmp_path / 'missing'
    elif problem == 'public':
        registry.chmod(0o755)
    elif problem == 'symlink':
        target = tmp_path / 'linked-registry'
        target.symlink_to(registry, target_is_directory=True)
    elif problem == 'ancestor_symlink':
        link = tmp_path / 'linked-parent'
        link.symlink_to(tmp_path, target_is_directory=True)
        target = link / registry.name
    else:
        target = registry / '..' / registry.name
    monkeypatch.setattr(settings, 'media_reservation_dir', str(target))
    with pytest.raises(ApiError) as error:
        with reserve_temporary_space(tmp_path, 1):
            pytest.fail('Unsafe registry must be rejected')
    assert error.value.status_code == 503
    assert not records(registry)


@pytest.mark.parametrize('problem', ['unknown', 'corrupt', 'oversized', 'public', 'symlink', 'fifo', 'directory', 'hardlink'])
def test_unknown_or_unsafe_records_are_preserved_and_never_trusted(registry, tmp_path, problem):
    path = registry / ('unknown' if problem == 'unknown' else 'reservation-' + 'a' * 32)
    if problem == 'symlink':
        source = tmp_path / 'source'
        source.write_bytes(b'synthetic-source')
        path.symlink_to(source)
    elif problem == 'fifo':
        os.mkfifo(path, 0o600)
    elif problem == 'directory':
        path.mkdir(mode=0o700)
    else:
        path.write_bytes(b'x' * (129 if problem == 'oversized' else 1))
        path.chmod(0o644 if problem == 'public' else 0o600)
        if problem == 'hardlink':
            os.link(path, tmp_path / 'outside-link')
    with pytest.raises(ApiError) as error:
        with reserve_temporary_space(tmp_path, 1):
            pytest.fail('Unknown data must not be guessed safe')
    assert error.value.status_code == 503
    assert path.lstat() is not None
    assert len(records(registry)) <= 1


def test_filesystem_mismatch_rejects_without_registering(registry, tmp_path):
    if not Path('/dev/shm').is_dir() or Path('/dev/shm').stat().st_dev == registry.stat().st_dev:
        pytest.skip('A second disposable local filesystem is required')
    with TemporaryDirectory(dir='/dev/shm') as target:
        with pytest.raises(ApiError) as error:
            with reserve_temporary_space(Path(target), 1):
                pytest.fail('Cross-filesystem accounting must not be allowed')
    assert error.value.status_code == 503 and not records(registry)


def test_valid_stale_metadata_is_pruned_but_media_files_remain(registry, tmp_path):
    path = registry / ('reservation-' + 'b' * 32)
    path.write_text('v1 999999 1000\n')  # Device numbers can change across reboots.
    path.chmod(0o600)
    orphan = tmp_path / '.staging-orphan'
    orphan.mkdir()
    (orphan / 'keep').write_bytes(b'keep')
    with reserve_temporary_space(tmp_path, 1000):
        assert not path.exists()
    assert (orphan / 'keep').read_bytes() == b'keep'


def test_active_record_capacity_is_bounded_without_dropping_existing_budgets(registry, tmp_path, monkeypatch):
    monkeypatch.setattr(reservations, 'MAX_RECORDS', 2)
    with ExitStack() as stack:
        for _ in range(2):
            stack.enter_context(reserve_temporary_space(tmp_path, 1))
        with pytest.raises(ApiError) as error:
            with reserve_temporary_space(tmp_path, 1):
                pytest.fail('Registry capacity must not grow beyond its bound')
        assert error.value.status_code == 503 and len(records(registry)) == 2
    assert not records(registry)


def read_line(process):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        assert selector.select(timeout=10), 'Child failed to report synthetic reservation state'
    return process.stdout.readline().decode().strip()


CHILD = '''
import sys
from pathlib import Path
from types import SimpleNamespace
from app.core.config import settings
from app.core.errors import ApiError
from app.services import temporary_reservations as r
settings.media_reservation_dir = sys.argv[1]
settings.min_media_free_space_mb = 0
r.shutil.disk_usage = lambda _: SimpleNamespace(free=1000)
sys.stdin.readline()
try:
    with r.reserve_temporary_space(Path(sys.argv[2]), 600):
        print('entered', flush=True)
        sys.stdin.readline()
except ApiError as exc:
    print(str(exc.status_code), flush=True)
'''


def test_real_processes_cannot_both_admit_the_same_remaining_capacity(registry, tmp_path):
    children = [subprocess.Popen([sys.executable, '-c', CHILD, str(registry), str(tmp_path)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
    try:
        for child in children:
            child.stdin.write(b'go\n')
            child.stdin.flush()
        assert sorted(read_line(child) for child in children) == ['507', 'entered']
    finally:
        for child in children:
            try:
                child.stdin.write(b'finish\n')
                child.stdin.flush()
            except BrokenPipeError:
                pass
            try:
                child.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate()
            assert child.returncode == 0
    assert not records(registry)


def test_process_death_releases_lock_without_deleting_generated_data(registry, tmp_path):
    keep = tmp_path / 'keep.bin'
    keep.write_bytes(b'keep')
    child = subprocess.Popen([sys.executable, '-c', CHILD, str(registry), str(tmp_path)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        child.stdin.write(b'go\n')
        child.stdin.flush()
        assert read_line(child) == 'entered'
        assert len(records(registry)) == 1
        child.kill()
        child.communicate(timeout=10)
        with reserve_temporary_space(tmp_path, 1000):
            assert len(records(registry)) == 1  # Old dead metadata was pruned.
        assert keep.read_bytes() == b'keep'
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=10)


def test_inherited_descriptor_retains_budget_after_parent_context_exits(registry, tmp_path):
    child = None
    try:
        with reserve_temporary_space(tmp_path, 600):
            child = subprocess.Popen([sys.executable, '-c', 'import sys; print("ready", flush=True); sys.stdin.readline()'],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, pass_fds=reservation_descriptors())
            assert read_line(child) == 'ready'
        assert len(records(registry)) == 1
        with pytest.raises(ApiError) as error:
            with reserve_temporary_space(tmp_path, 401):
                pytest.fail('A living inherited lease must retain its budget')
        assert error.value.status_code == 507
        child.communicate(input=b'finish\n', timeout=10)
        with reserve_temporary_space(tmp_path, 1000):
            pass
        assert not records(registry)
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.communicate(timeout=10)


def test_audio_supervisor_passes_active_descriptors_to_real_child(registry, tmp_path):
    with reserve_temporary_space(tmp_path, 600):
        script = 'import os,sys; [os.fstat(int(fd)) for fd in sys.argv[1:]]'
        assert _run_audio_command([sys.executable, '-c', script, *map(str, reservation_descriptors())], tmp_path) == 0
    assert not records(registry)


def test_generation_rejects_before_producer_and_releases_after_staging_cleanup(registry, stage_db, tmp_path, monkeypatch):
    db, video = stage_db
    with pytest.raises(ApiError) as error:
        generate_artifacts(db, video, 'video', lambda: pytest.fail('Insufficient reservation before producer'))
    assert error.value.status_code == 507
    monkeypatch.setattr(reservations.shutil, 'disk_usage', lambda _: SimpleNamespace(free=3 * 1024 * 1024))
    def produce():
        assert len(records(registry)) == 1
        (artifact_directory('video') / f'{video.id}.mp4').write_bytes(b'synthetic')
    generate_artifacts(db, video, 'video', produce)
    assert not records(registry)
    assert (Path(settings.video_storage_dir) / f'{video.id}.mp4').read_bytes() == b'synthetic'
    assert not list(Path(settings.video_storage_dir).glob('.staging-*'))


@pytest.mark.parametrize('remote', [False, True])
def test_upload_reservation_rejects_before_read_or_provider(registry, stage_db, monkeypatch, remote):
    db, video = stage_db
    class Unreadable(BytesIO):
        def read(self, *args):
            pytest.fail('Upload body must not be read after failed admission')
    file = UploadFile(Unreadable(b'synthetic'), filename='synthetic.mp4')
    with pytest.raises(ApiError) as error:
        video_upload.save_uploaded_video(db, video.user, file, object_store=object() if remote else None)
    assert error.value.status_code == 507
    assert not records(registry)
    assert not list(Path(settings.video_storage_dir).iterdir())


def test_auto_note_reserves_before_model_and_manual_note_requires_no_disk_budget(registry, stage_db, monkeypatch):
    from app.models import Summary
    from app.agents.video_analysis_agent import VideoAnalysisResult
    db, video = stage_db
    video.transcript = Transcript(content='synthetic source')
    db.commit()
    monkeypatch.setattr(analysis, 'analyze_video_transcript', lambda **_: pytest.fail('Reserve before model call'))
    with pytest.raises(ApiError) as error:
        analysis.analyze_video(db, video)
    assert error.value.status_code == 507 and video.summary is None
    video.summary = Summary(summary='old', markdown_note='handwritten', note_is_manual=True)
    db.commit()
    monkeypatch.setattr(analysis, 'analyze_video_transcript', lambda **_: (VideoAnalysisResult(title='Synthetic', summary='new'), 'generated'))
    analysis.analyze_video(db, video)
    assert video.summary.markdown_note == 'handwritten' and not records(registry)


@pytest.mark.parametrize('group', [False, True])
def test_object_cache_reserves_exact_size_and_cleans_before_release(registry, ledger, tmp_path, monkeypatch, group):
    db, alice, _, video, store = ledger
    path = tmp_path / f'{video}.md'
    path.write_bytes(b'x' * 600)
    spec = publish(db, alice, video, path, store)
    cached = tmp_path / 'cache'
    def materialize():
        if group:
            return materialize_artifacts(db, user_id=alice, video_id=video, kind='note', cache_root=cached, store=store, required_id=spec.id)
        return materialize_artifact(db, user_id=alice, artifact_id=spec.id, cache_root=cached, store=store)
    with reserve_temporary_space(tmp_path, 401):
        with pytest.raises(ApiError) as error:
            with materialize():
                pytest.fail('Insufficient cache budget')
        assert error.value.status_code == 507
        assert not list(cached.iterdir())
    with materialize() as result:
        output = result[1] if group else result
        assert output.read_bytes() == b'x' * 600
        assert len(records(registry)) == 1
    assert not records(registry) and not list(cached.iterdir())


@pytest.mark.skipif(shutil.which('ffmpeg') is None, reason='Real ffmpeg fixture')
def test_managed_real_http_download_with_enabled_reservation(registry, download_job, monkeypatch):
    monkeypatch.setattr(settings, 'max_media_stage_mb', 1)
    monkeypatch.setattr(reservations.shutil, 'disk_usage', lambda _: SimpleNamespace(free=3 * 1024 * 1024))
    with Session(download_job[2]) as db:
        video = db.get(VideoTask, download_job[3]).video
        result = generate_artifacts(db, video, 'video', lambda: managed_downloader.download_video(
            f'http://127.0.0.1:{download_job[6]}/sample.mp4', video.id,
        ))
    assert Path(result.file_path).is_file()
    assert not records(registry)
    assert (download_job[5] / 'keep').read_bytes() == b'keep'


@pytest.mark.parametrize('problem', ['public', 'nonempty', 'symlink', 'fifo'])
def test_admission_lock_itself_must_be_private_empty_regular_file(registry, tmp_path, problem):
    path = registry / '.lock'
    if problem == 'symlink':
        target = tmp_path / 'lock-target'
        target.write_bytes(b'keep')
        path.symlink_to(target)
    elif problem == 'fifo':
        os.mkfifo(path, 0o600)
    else:
        path.write_bytes(b'keep' if problem == 'nonempty' else b'')
        path.chmod(0o644 if problem == 'public' else 0o600)
    with pytest.raises(ApiError) as error:
        with reserve_temporary_space(tmp_path, 1):
            pytest.fail('Untrusted lock must never be bypassed')
    assert error.value.status_code == 503 and not records(registry)
    assert path.lstat() is not None


def test_busy_admission_lock_times_out_without_bypassing_existing_writer(registry, tmp_path, monkeypatch):
    import fcntl
    path = registry / '.lock'
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        moments = iter([0, 3])
        monkeypatch.setattr(reservations.time, 'monotonic', lambda: next(moments))
        with pytest.raises(ApiError) as error:
            with reserve_temporary_space(tmp_path, 1):
                pytest.fail('Must not ignore a busy admission lock')
        assert error.value.status_code == 503
    finally:
        os.close(descriptor)
    assert not records(registry)


def test_release_cleanup_error_does_not_turn_success_into_client_failure(registry, tmp_path, monkeypatch):
    unlink = os.unlink
    def reject_metadata_unlink(path, *args, **kwargs):
        if str(path).startswith('reservation-'):
            raise PermissionError('synthetic-private-cleanup-error')
        return unlink(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(reservations.os, 'unlink', reject_metadata_unlink)
        with reserve_temporary_space(tmp_path, 1000):
            pass
    assert len(records(registry)) == 1
    with reserve_temporary_space(tmp_path, 1000):
        pass
    assert not records(registry)


def test_enabled_mode_fails_without_lock_support_and_never_falls_back(registry, tmp_path, monkeypatch):
    monkeypatch.setattr(reservations, 'fcntl', None)
    with pytest.raises(ApiError) as error:
        with reserve_temporary_space(tmp_path, 1):
            pytest.fail('Enabled mode requires locking support')
    assert error.value.status_code == 503
    assert not records(registry)
