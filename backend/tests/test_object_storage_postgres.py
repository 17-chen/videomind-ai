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
        assert connection.scalar(text('SELECT version_num FROM alembic_version_objects')) == '20261104_o001'
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
