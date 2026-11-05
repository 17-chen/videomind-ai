"""Real optional ledger migrations/concurrency, synthetic users and transport."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.models import User, Video
from app.services.object_storage.models import StoredArtifact
from app.services.object_storage.repository import publish_artifact
from scripts.prepare_objects import migration_config

pytestmark = pytest.mark.skipif(os.environ.get('RUN_STORAGE_OBJECT_TESTS') != '1', reason='Set RUN_STORAGE_OBJECT_TESTS=1 for disposable PostgreSQL ledger tests')


@pytest.fixture
def object_db(monkeypatch):
    admin = create_engine(os.environ.get('STORAGE_TEST_DATABASE_URL', settings.database_url), isolation_level='AUTOCOMMIT')
    database = f'vm_object_test_{uuid4().hex}'
    engine = None
    created = False
    roles = []
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database}"'))
            created = True
            for role in ('anon', 'authenticated', 'service_role'):
                if not connection.scalar(text('SELECT 1 FROM pg_roles WHERE rolname=:role'), {'role': role}):
                    connection.execute(text(f'CREATE ROLE "{role}" NOLOGIN'))
                    roles.append(role)
        engine = create_engine(admin.url.set(database=database), connect_args={'options': '-c statement_timeout=8000 -c lock_timeout=4000'})
        monkeypatch.setattr(settings, 'database_url', engine.url.render_as_string(hide_password=False))
        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / 'alembic.ini'))
        config.set_main_option('script_location', str(root / 'alembic'))
        command.upgrade(config, 'head')
        with engine.begin() as connection:
            for role in ('anon', 'authenticated', 'service_role'):
                connection.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "{role}"'))
            optional = migration_config()
            optional.attributes['connection'] = connection
            command.upgrade(optional, 'head')
        with Session(engine) as db:
            owner = User(email='storage-alice@example.com', password_hash='synthetic')
            videos = [Video(user=owner, url=f'https://example.com/synthetic/{i}', tags=[]) for i in range(2)]
            db.add_all(videos)
            db.commit()
            owner_id, ids = owner.id, [video.id for video in videos]
        yield engine, owner_id, ids
    finally:
        if engine is not None:
            engine.dispose()
        with admin.connect() as connection:
            if created:
                connection.execute(text(f'DROP DATABASE "{database}"'))
            for role in roles:
                connection.execute(text(f'DROP ROLE "{role}"'))
        admin.dispose()


def test_migration_idempotent_and_backend_only(object_db):
    engine, *_ = object_db
    with engine.begin() as connection:
        optional = migration_config()
        optional.attributes['connection'] = connection
        command.upgrade(optional, 'head')
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '20261024_0008'
        assert connection.scalar(text('SELECT version_num FROM alembic_version_objects')) == '20261105_o002'
        assert connection.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid='public.vm_storage_objects'::regclass")) is True
        for role in ('anon', 'authenticated', 'service_role'):
            for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE'):
                assert connection.scalar(text("SELECT has_table_privilege(:role, 'public.vm_storage_objects', :privilege)"), {'role': role, 'privilege': privilege}) is False


@pytest.mark.parametrize('same_video', [False, True])
def test_concurrent_quota_and_version_publication(object_db, tmp_path, monkeypatch, same_video):
    engine, owner, videos = object_db
    monkeypatch.setattr(settings, 'max_user_storage_mb', 1)
    barrier = Barrier(2)

    class SyntheticStore:
        bucket = 'videomind-private'
        project_fingerprint = 'a' * 64

        def put(self, spec, path):
            # A durable pending record must be visible BEFORE network transfer.
            with Session(engine) as observer:
                assert observer.get(StoredArtifact, spec.id).state == 'pending'
            barrier.wait(timeout=10)

    def upload(index):
        video = videos[0] if same_video else videos[index]
        directory = tmp_path / str(index)
        directory.mkdir()
        path = directory / f'{video}.md'
        path.write_bytes(bytes([65 + index]) * 700000)
        with Session(engine) as db:
            try:
                publish_artifact(db, user_id=owner, video_id=video, kind='note', path=path, store=SyntheticStore())
                return 200
            except ApiError as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(upload, range(2)))
    assert statuses == ([200, 200] if same_video else [200, 413])
    with Session(engine) as db:
        rows = db.scalars(select(StoredArtifact)).all()
        assert len(rows) == 2
        assert sorted(row.state for row in rows) == (['ready', 'retired'] if same_video else ['pending', 'ready'])
        assert len({row.id for row in rows}) == 2


def test_sql_publish_failure_retains_previous_and_pending_key(object_db, tmp_path):
    engine, owner, videos = object_db
    class SyntheticStore:
        bucket = 'videomind-private'
        project_fingerprint = 'b' * 64

        def put(self, spec, path):
            pass

    path = tmp_path / f'{videos[0]}.md'
    path.write_bytes(b'previous')
    with Session(engine) as db:
        first = publish_artifact(db, user_id=owner, video_id=videos[0], kind='note', path=path, store=SyntheticStore())
        # Real SQL constraint failure after retiring old: both state changes rollback.
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE vm_storage_objects ADD CONSTRAINT synthetic_failure CHECK (state != 'ready' OR size_bytes != 7)"))
        path.write_bytes(b'failure')
        with pytest.raises(ApiError) as error:
            publish_artifact(db, user_id=owner, video_id=videos[0], kind='note', path=path, store=SyntheticStore())
        assert error.value.status_code == 503
        assert error.value.message == '文件存储暂不可用，请稍后重试'
        assert db.get(StoredArtifact, first.id).state == 'ready'
        assert sorted(db.scalars(select(StoredArtifact.state))) == ['pending', 'ready']


class DeletionTestStore:
    bucket = 'videomind-private'
    project_fingerprint = 'c' * 64

    def __init__(self):
        self.keys = set()
        self.delete_calls = 0

    def put(self, spec, path):
        self.keys.add(spec.object_key)

    def delete(self, spec):
        self.delete_calls += 1
        self.keys.discard(spec.object_key)


def prepare_deleted_object(object_db, tmp_path, monkeypatch):
    from app.services import videos
    engine, owner, ids = object_db
    calls = []
    class Vectors:
        def delete_video_document(self, **kwargs):
            calls.append(kwargs)
    monkeypatch.setattr(videos, 'vector_store', Vectors())
    path = tmp_path / f'{ids[0]}.md'
    path.write_bytes(b'synthetic-content')
    store = DeletionTestStore()
    with Session(engine) as db:
        spec = publish_artifact(db, user_id=owner, video_id=ids[0], kind='note', path=path, store=store)
        videos.delete_video_for_user(db, db.get(User, owner), ids[0])
    return spec, store, calls


def test_delete_and_cleanup_are_durable_across_database_sessions(object_db, tmp_path, monkeypatch):
    from app.services.object_storage.cleanup import cleanup_requested_objects
    engine, _, ids = object_db
    spec, store, calls = prepare_deleted_object(object_db, tmp_path, monkeypatch)
    assert len(calls) == 1 and spec.object_key in store.keys
    with Session(engine) as restarted:
        assert restarted.get(Video, ids[0]) is None
        row = restarted.get(StoredArtifact, spec.id)
        assert row.delete_requested and row.state == 'retired'
        report = cleanup_requested_objects(restarted, store=store)
        assert report['confirmed_deleted'] == 1 and report['status'] == 'complete'
    assert not store.keys


def test_cleanup_workers_skip_locked_key_and_never_delete_twice(object_db, tmp_path, monkeypatch):
    from threading import Event
    from app.services.object_storage.cleanup import cleanup_requested_objects
    engine, *_ = object_db
    _, store, _ = prepare_deleted_object(object_db, tmp_path, monkeypatch)
    entered, release = Event(), Event()
    delete = store.delete
    def held_delete(spec):
        entered.set()
        assert release.wait(timeout=10)
        delete(spec)
    store.delete = held_delete
    def worker():
        with Session(engine) as db:
            return cleanup_requested_objects(db, store=store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(worker)
        try:
            assert entered.wait(timeout=5)
            second = pool.submit(worker)
            assert second.result(timeout=5)['attempted'] == 0
        finally:
            release.set()
        assert first.result(timeout=5)['confirmed_deleted'] == 1
    assert store.delete_calls == 1


def test_delete_during_upload_preserves_pending_intent_without_holding_video_lock(object_db, tmp_path, monkeypatch):
    from threading import Event
    from app.services import videos
    from app.services.object_storage.cleanup import cleanup_requested_objects
    engine, owner, ids = object_db
    entered, release = Event(), Event()
    class Vectors:
        def delete_video_document(self, **kwargs):
            pass
    monkeypatch.setattr(videos, 'vector_store', Vectors())
    class InFlight(DeletionTestStore):
        def put(self, spec, path):
            entered.set()
            assert release.wait(timeout=10)
            super().put(spec, path)
    store = InFlight()
    path = tmp_path / f'{ids[0]}.md'
    path.write_bytes(b'synthetic-inflight-content')
    def upload():
        with Session(engine) as db:
            with pytest.raises(ApiError) as error:
                publish_artifact(db, user_id=owner, video_id=ids[0], kind='note', path=path, store=store)
            assert error.value.status_code == 404
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(upload)
        try:
            assert entered.wait(timeout=5)
            with Session(engine) as db:
                videos.delete_video_for_user(db, db.get(User, owner), ids[0])
                report = cleanup_requested_objects(db, store=store)
                assert report['pending_uncertain'] == 1 and report['attempted'] == 0
        finally:
            release.set()
        future.result(timeout=5)
    with Session(engine) as db:
        row = db.scalar(select(StoredArtifact))
        assert row.delete_requested and row.state == 'pending'
        assert db.get(Video, ids[0]) is None
    assert store.delete_calls == 0 and len(store.keys) == 1


def test_deleted_video_cannot_register_pending_intent_after_measurement(object_db, tmp_path, monkeypatch):
    from app.services import videos
    from app.services.object_storage import repository
    engine, owner, ids = object_db
    class Vectors:
        def delete_video_document(self, **kwargs):
            pass
    monkeypatch.setattr(videos, 'vector_store', Vectors())
    measure = repository.measure_file
    def delete_before_register(path):
        measured = measure(path)
        with Session(engine) as db:
            videos.delete_video_for_user(db, db.get(User, owner), ids[0])
        return measured
    monkeypatch.setattr(repository, 'measure_file', delete_before_register)
    path = tmp_path / f'{ids[0]}.md'
    path.write_bytes(b'synthetic-content')
    store = DeletionTestStore()
    with Session(engine) as db:
        with pytest.raises(ApiError) as error:
            publish_artifact(db, user_id=owner, video_id=ids[0], kind='note', path=path, store=store)
        assert error.value.status_code == 404
        assert db.scalar(select(StoredArtifact)) is None
    assert not store.keys


def test_real_sql_delete_failure_rolls_back_video_and_intents(object_db, tmp_path, monkeypatch):
    from app.services import videos
    engine, owner, ids = object_db
    class Vectors:
        def delete_video_document(self, **kwargs):
            pass
    monkeypatch.setattr(videos, 'vector_store', Vectors())
    path = tmp_path / f'{ids[0]}.md'
    path.write_bytes(b'synthetic-content')
    with Session(engine) as db:
        spec = publish_artifact(db, user_id=owner, video_id=ids[0], kind='note', path=path, store=DeletionTestStore())
        with engine.begin() as connection:
            connection.execute(text("CREATE FUNCTION synthetic_reject_delete() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'private-database-sentinel'; END $$"))
            connection.execute(text('CREATE TRIGGER synthetic_reject_delete BEFORE DELETE ON videos FOR EACH ROW EXECUTE FUNCTION synthetic_reject_delete()'))
        with pytest.raises(ApiError) as error:
            videos.delete_video_for_user(db, db.get(User, owner), ids[0])
        assert error.value.status_code == 503 and 'private-database-sentinel' not in error.value.message
        assert db.get(Video, ids[0]) is not None
        row = db.get(StoredArtifact, spec.id)
        assert row.state == 'ready' and row.delete_requested is False


def test_real_sql_cleanup_failure_after_remote_delete_can_retry(object_db, tmp_path, monkeypatch):
    from app.services.object_storage.cleanup import cleanup_requested_objects
    engine, *_ = object_db
    spec, store, _ = prepare_deleted_object(object_db, tmp_path, monkeypatch)
    with engine.begin() as connection:
        connection.execute(text("CREATE FUNCTION synthetic_reject_cleanup() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.state = 'deleted' THEN RAISE EXCEPTION 'private-database-sentinel'; END IF; RETURN NEW; END $$"))
        connection.execute(text('CREATE TRIGGER synthetic_reject_cleanup BEFORE UPDATE ON vm_storage_objects FOR EACH ROW EXECUTE FUNCTION synthetic_reject_cleanup()'))
    with Session(engine) as db:
        report = cleanup_requested_objects(db, store=store)
        assert report['failed'] == 1 and report['eligible'] == 1
        assert not store.keys
        assert db.get(StoredArtifact, spec.id).state == 'retired'
    with engine.begin() as connection:
        connection.execute(text('DROP TRIGGER synthetic_reject_cleanup ON vm_storage_objects'))
    with Session(engine) as db:
        assert cleanup_requested_objects(db, store=store)['confirmed_deleted'] == 1
    assert store.delete_calls == 2


def test_old_ledger_schema_blocks_business_delete_before_touching_vectors(object_db, monkeypatch):
    from app.services import videos
    engine, owner, ids = object_db
    calls = []
    class Vectors:
        def delete_video_document(self, **kwargs):
            calls.append(True)
    monkeypatch.setattr(videos, 'vector_store', Vectors())
    with engine.begin() as connection:
        optional = migration_config()
        optional.attributes['connection'] = connection
        command.downgrade(optional, '20261104_o001')
    with Session(engine) as db:
        with pytest.raises(ApiError) as error:
            videos.delete_video_for_user(db, db.get(User, owner), ids[0])
        assert error.value.status_code == 503
        assert db.get(Video, ids[0]) is not None
        assert not calls


def test_migration_preserves_existing_row_and_blocks_losing_pending_deletion(object_db):
    engine, owner, ids = object_db
    with engine.begin() as connection:
        optional = migration_config()
        optional.attributes['connection'] = connection
        command.downgrade(optional, '20261104_o001')
        connection.execute(text("""INSERT INTO vm_storage_objects
            (id,user_id,video_id,kind,filename,bucket,project_fingerprint,sha256,size_bytes,state)
            VALUES (:id,:owner,:video,'note',:filename,'videomind-private',:fingerprint,:sha,7,'ready')"""),
            {'id': str(uuid4()), 'owner': owner, 'video': ids[0], 'filename': f'{ids[0]}.md', 'fingerprint': 'c' * 64, 'sha': 'd' * 64})
        command.upgrade(optional, 'head')
    with Session(engine) as db:
        row = db.scalar(select(StoredArtifact))
        assert row.state == 'ready' and row.size_bytes == 7 and row.delete_requested is False
        row.state, row.delete_requested = 'pending', True
        db.commit()
    with pytest.raises(RuntimeError, match='Unfulfilled'):
        with engine.begin() as connection:
            optional = migration_config()
            optional.attributes['connection'] = connection
            command.downgrade(optional, '20261104_o001')
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version_objects')) == '20261105_o002'
        assert connection.scalar(text('SELECT delete_requested FROM vm_storage_objects')) is True
