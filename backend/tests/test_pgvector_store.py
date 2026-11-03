"""Real opt-in pgvector checks, each in a newly created disposable database."""

from concurrent.futures import ThreadPoolExecutor
import math
import os
import json
import subprocess
import sys
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.models import User, Video
from app.services import pgvector_store, videos
from app.services.embeddings import LocalHashEmbeddingService
from app.services.pgvector_store import PgVectorStore, vector_literal
from app.services.vector_store import ChromaVectorStore, create_vector_store
from scripts.prepare_pgvector import main as prepare_main, migration_config


requires_postgres = pytest.mark.skipif(os.environ.get('RUN_PGVECTOR_TESTS') != '1', reason='Set RUN_PGVECTOR_TESTS=1 for disposable PostgreSQL tests')


class SyntheticNonzeroEmbedding(LocalHashEmbeddingService):
    """Synthetic fixture vectors: tiny hash spaces can cancel to zero."""
    def embed_text(self, content):
        values = super().embed_text(content)
        if not any(values):
            values[0] = 1.0
        return values


@pytest.fixture(params=['public', 'extensions'])
def vector_db(monkeypatch, request):
    admin = create_engine(os.environ.get('PGVECTOR_TEST_DATABASE_URL', settings.database_url), isolation_level='AUTOCOMMIT')
    database = f'vm_vector_test_{uuid4().hex}'
    engine = None
    created = False
    roles_created = []
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database}"'))
            created = True
            for role in ('anon', 'authenticated', 'service_role'):
                if not connection.scalar(text('SELECT 1 FROM pg_roles WHERE rolname=:role'), {'role': role}):
                    connection.execute(text(f'CREATE ROLE "{role}" NOLOGIN'))
                    roles_created.append(role)
        engine = create_engine(admin.url.set(database=database), connect_args={'options': '-c statement_timeout=8000 -c lock_timeout=4000'})
        monkeypatch.setattr(settings, 'database_url', engine.url.render_as_string(hide_password=False))
        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / 'alembic.ini'))
        config.set_main_option('script_location', str(root / 'alembic'))
        command.upgrade(config, 'head')
        with engine.begin() as connection:
            if request.param == 'extensions':
                connection.execute(text('CREATE SCHEMA extensions'))
                connection.execute(text('CREATE EXTENSION vector WITH SCHEMA extensions'))
            # Reproduce hosted-provider default grants: migration must revoke them.
            for role in ('anon', 'authenticated', 'service_role'):
                connection.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "{role}"'))
            optional = migration_config()
            optional.attributes['connection'] = connection
            command.upgrade(optional, 'head')
        monkeypatch.setattr(settings, 'embedding_provider', 'local_hash')
        monkeypatch.setattr(pgvector_store, 'current_embedding_service', lambda: SyntheticNonzeroEmbedding(dimensions=8))
        with Session(engine) as db:
            alice = User(email='vector-alice@example.com', password_hash='synthetic')
            bob = User(email='vector-bob@example.com', password_hash='synthetic')
            items = [Video(user=alice, url=f'https://example.com/synthetic/{i}', tags=[]) for i in range(2)]
            other = Video(user=bob, url='https://example.com/other', tags=[])
            db.add_all([*items, other])
            db.commit()
            ids, user_id, other_id, other_user = [item.id for item in items], alice.id, other.id, bob.id
        yield engine, ids, user_id, other_id, other_user
    finally:
        if engine is not None:
            engine.dispose()
        with admin.connect() as connection:
            if created:
                connection.execute(text(f'DROP DATABASE "{database}"'))
            for role in roles_created:
                connection.execute(text(f'DROP ROLE "{role}"'))
        admin.dispose()


def put(store, user, video, document='linear algebra matrix vectors', **kwargs):
    store.upsert_video_document(vector_id=f'video:{video}', user_id=user, video_id=video, title='Synthetic', url='https://example.com/synthetic', category='Study', source='test', document=document, **kwargs)


@requires_postgres
def test_pgvector_restart_ownership_and_backend_role_boundary(vector_db):
    engine, ids, alice, bob_video, bob = vector_db
    first = PgVectorStore(engine=engine)
    first.check_connection()
    put(first, alice, ids[0])
    put(first, bob, bob_video)
    restarted = PgVectorStore(engine=engine)
    assert [row.video_id for row in restarted.query_video_documents(user_id=alice, query='matrix', limit=5)] == [ids[0]]
    assert [row.video_id for row in restarted.query_video_documents(user_id=bob, query='matrix', limit=5)] == [bob_video]
    process = subprocess.run([
        sys.executable, '-c',
        "import json,sys; from app.services.vector_store import vector_store; "
        "vector_store.check_connection(); "
        "print(json.dumps({'backend': type(vector_store).__name__, 'ids': [r.video_id for r in vector_store.query_video_documents(user_id=sys.argv[1], query='matrix', limit=5)]}))",
        alice,
    ], env={**os.environ, 'DATABASE_URL': settings.database_url, 'VECTOR_STORE_BACKEND': 'pgvector',
            'EMBEDDING_PROVIDER': 'local_hash', 'EMBEDDING_DIMENSIONS': '8'}, capture_output=True, text=True, timeout=20)
    assert process.returncode == 0
    assert json.loads(process.stdout) == {'backend': 'PgVectorStore', 'ids': [ids[0]]}

    with pytest.raises(ApiError) as error:
        put(restarted, bob, ids[0], 'must not replace Alice')
    assert error.value.status_code == 404
    restarted.delete_video_document(vector_id=f'video:{ids[0]}', user_id=bob)
    assert len(first.query_video_documents(user_id=alice, query='matrix', limit=5)) == 1
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid='public.vm_vector_chunks'::regclass")) is True
        for role in ('anon', 'authenticated', 'service_role'):
            assert connection.scalar(text("SELECT has_table_privilege(:role, 'public.vm_vector_chunks', 'SELECT')"), {'role': role}) is False
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '20261024_0008'
        assert connection.scalar(text('SELECT version_num FROM alembic_version_pgvector')) == '20261103_v001'
    # Second migrate is a no-op and leaves data intact.
    with engine.begin() as connection:
        config = migration_config()
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')
    assert len(first.query_video_documents(user_id=alice, query='matrix', limit=5)) == 1


@requires_postgres
def test_chunk_dedup_model_isolation_and_delete_all_models(vector_db, monkeypatch):
    engine, ids, alice, _, _ = vector_db
    store = PgVectorStore(engine=engine, chunk_size=30, chunk_overlap=5)
    put(store, alice, ids[0], 'hash original')
    monkeypatch.setattr(settings, 'embedding_provider', 'bge_zh')
    put(store, alice, ids[0], 'matrix linear algebra ' * 80)
    put(store, alice, ids[1], 'matrix alternative')
    rows = store.query_video_documents(user_id=alice, query='matrix', limit=5)
    assert {row.video_id for row in rows} == set(ids)
    assert len(rows) == 2
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM vm_vector_chunks WHERE video_id=:id'), {'id': ids[0]}) > 2
    monkeypatch.setattr(settings, 'embedding_model', 'different-synthetic-model')
    assert store.query_video_documents(user_id=alice, query='matrix', limit=5) == []
    store.delete_video_document(vector_id=f'video:{ids[0]}', user_id=alice)
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM vm_vector_chunks WHERE video_id=:id'), {'id': ids[0]}) == 0


@requires_postgres
def test_sql_failure_after_delete_rolls_back_and_keeps_previous_index(vector_db):
    engine, ids, alice, _, _ = vector_db
    store = PgVectorStore(engine=engine)
    put(store, alice, ids[0], 'original matrix')
    # A real SQL constraint failure after deleting the old rows must roll back.
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE vm_vector_chunks ADD CONSTRAINT synthetic_failure CHECK (document NOT LIKE 'reject%')"))
    with pytest.raises(ApiError) as error:
        put(store, alice, ids[0], 'reject synthetic update')
    assert error.value.status_code == 503
    assert error.value.message == pgvector_store.UNAVAILABLE
    assert store.query_video_documents(user_id=alice, query='matrix', limit=5)[0].document == 'original matrix'


@requires_postgres
def test_concurrent_revisions_are_coherent_and_shortening_removes_old_chunks(vector_db, monkeypatch):
    engine, ids, alice, _, _ = vector_db
    monkeypatch.setattr(settings, 'embedding_provider', 'bge_zh')
    ready = Barrier(2)
    synthetic_service = SyntheticNonzeroEmbedding(dimensions=8)

    class Synchronized:
        def __init__(self):
            self.first = True

        def embed_text(self, content):
            if self.first:
                self.first = False
                ready.wait(timeout=10)
            return synthetic_service.embed_text(content)

    monkeypatch.setattr(pgvector_store, 'current_embedding_service', Synchronized)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda content: put(PgVectorStore(engine=engine, chunk_size=20, chunk_overlap=0), alice, ids[0], content), ['a' * 80, 'b' * 80]))
    with engine.connect() as connection:
        assert set(connection.scalars(text('SELECT document FROM vm_vector_chunks'))) in ({'a' * 20}, {'b' * 20})
    monkeypatch.setattr(pgvector_store, 'current_embedding_service', lambda: synthetic_service)
    put(PgVectorStore(engine=engine), alice, ids[0], 'shortened matrix')
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM vm_vector_chunks')) == 1


@requires_postgres
def test_real_delete_route_lock_order_and_database_cascade(vector_db, monkeypatch):
    engine, ids, alice, _, _ = vector_db
    store = PgVectorStore(engine=engine)
    put(store, alice, ids[0])
    put(store, alice, ids[1])
    monkeypatch.setattr(videos, 'vector_store', store)
    with Session(engine) as db:
        user = db.get(User, alice)
        videos.delete_video_for_user(db, user, ids[0])
        db.delete(db.get(Video, ids[1]))
        db.commit()
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM vm_vector_chunks')) == 0


@requires_postgres
def test_readiness_fails_sanitized_if_optional_schema_missing(vector_db):
    engine, *_ = vector_db
    with engine.begin() as connection:
        connection.execute(text('DROP TABLE vm_vector_chunks'))
    with pytest.raises(ApiError) as error:
        PgVectorStore(engine=engine).check_connection()
    assert error.value.status_code == 503
    assert error.value.message == pgvector_store.UNAVAILABLE


@pytest.mark.parametrize('values', [[], [0.0, 0.0], [math.nan, 1], [math.inf, 1]])
def test_invalid_vector_is_rejected_before_database_access(values):
    with pytest.raises(ApiError) as error:
        vector_literal(values)
    assert error.value.status_code == 503


def test_backend_selection_keeps_chroma_default_and_rejects_unknown(monkeypatch):
    monkeypatch.setattr(settings, 'vector_store_backend', 'chroma')
    assert isinstance(create_vector_store(), ChromaVectorStore)
    monkeypatch.setattr(settings, 'vector_store_backend', 'pgvector')
    assert isinstance(create_vector_store(), PgVectorStore)
    monkeypatch.setattr(settings, 'vector_store_backend', 'unknown')
    with pytest.raises(ValueError):
        create_vector_store()


def test_prepare_without_apply_never_opens_a_database(monkeypatch, capsys):
    monkeypatch.setattr(command, 'upgrade', lambda *args: pytest.fail('No migration without --apply'))
    assert prepare_main([]) == 2
    assert 'not_applied' in capsys.readouterr().out


@requires_postgres
def test_rag_index_and_edit_use_shared_vectors_without_changing_business_contract(vector_db, monkeypatch):
    from app.models import Transcript
    from app.schemas.video import VideoUpdate
    from app.services import rag

    engine, ids, alice, _, _ = vector_db
    store = PgVectorStore(engine=engine)
    monkeypatch.setattr(rag, 'vector_store', store)
    with Session(engine) as db:
        video = db.get(Video, ids[0])
        video.transcript = Transcript(content='Synthetic linear algebra transcript')
        db.commit()
        embedding = rag.index_video(db, video)
        assert embedding.vector_id == f'video:{ids[0]}'
        videos.update_video_for_user(db, db.get(User, alice), ids[0], VideoUpdate(title='Edited matrix', category='Edited study'))
        assert video.index_sync_error is None
    result = store.query_video_documents(user_id=alice, query='matrix', limit=5)[0]
    assert result.title == 'Edited matrix'
    assert result.category == 'Edited study'
    assert 'Synthetic linear algebra transcript' in result.document


@requires_postgres
def test_fixed_synthetic_retrieval_baseline_and_privacy(vector_db, monkeypatch):
    from scripts.evaluate_retrieval import DEFAULT_DATASET, EvaluationDataset, evaluate_store

    engine, *_ = vector_db
    dataset = EvaluationDataset.model_validate_json(DEFAULT_DATASET.read_text())
    with Session(engine) as db:
        for name in {item.user_id for item in dataset.videos}:
            db.add(User(id=name, email=f'{name}-corpus@example.com', password_hash='synthetic'))
        db.flush()
        for item in dataset.videos:
            db.add(Video(id=item.id, user_id=item.user_id, url=f'https://example.com/{item.id}', tags=[]))
        db.commit()
    monkeypatch.setattr(pgvector_store, 'current_embedding_service', lambda: LocalHashEmbeddingService(dimensions=384))
    report = evaluate_store(dataset, PgVectorStore(engine=engine), top_k=3)
    assert report['privacy_violation_count'] == 0
    assert report['metrics']['recall_at_k'] >= 0.9
    assert report['case_count'] == 15
    print(json.dumps({'pgvector_synthetic_metrics': report['metrics'], 'privacy_violations': report['privacy_violation_count']}))


def test_prepare_failure_does_not_echo_raw_database_error(monkeypatch, capsys):
    def fail(*args):
        raise RuntimeError('private-database-sentinel')
    monkeypatch.setattr(command, 'upgrade', fail)
    assert prepare_main(['--apply']) == 1
    output = capsys.readouterr()
    assert 'pgvector_migration_failed' in output.out
    assert 'private-database-sentinel' not in output.out + output.err


def test_zero_query_returns_no_results_without_database(monkeypatch):
    class EmptyQuery:
        def embed_query(self, query):
            return [0.0, 0.0]
    monkeypatch.setattr(pgvector_store, 'current_embedding_service', EmptyQuery)
    store = PgVectorStore()
    assert store.query_video_documents(user_id='synthetic', query='???', limit=3) == []
    assert store._engine is None
