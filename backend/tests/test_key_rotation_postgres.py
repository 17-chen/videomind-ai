"""Real transactions/locks/RLS; always disposable databases and synthetic keys."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from threading import Event
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.base import Base
from app.models import AiSettings, User
from app.services import ai_settings
from app.services.key_rotation import KeyRotationError, rotate_stored_keys
from scripts import rotate_user_keys
from test_key_rotation import ciphertexts, key_arguments, seed_keys

pytestmark = pytest.mark.skipif(os.environ.get('RUN_POSTGRES_QUOTA_TESTS') != '1',
                                reason='Set RUN_POSTGRES_QUOTA_TESTS=1 for disposable PostgreSQL rotation tests')


@pytest.fixture
def postgres_rotation():
    admin = create_engine(settings.database_url, isolation_level='AUTOCOMMIT')
    name = 'vm_rotation_test_' + uuid4().hex
    engine = None
    created = False
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
            created = True
        engine = create_engine(admin.url.set(database=name))
        Base.metadata.create_all(engine)
        current, next_key = Fernet.generate_key().decode(), Fernet.generate_key().decode()
        seed_keys(engine, current)
        yield engine, current, next_key
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.connect() as connection:
                connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        admin.dispose()


def test_postgres_preflight_is_read_only_and_does_not_install_key(postgres_rotation, monkeypatch):
    engine, current, next_key = postgres_rotation
    monkeypatch.setattr(settings, 'user_api_key_encryption_key', current)
    before = ciphertexts(engine)
    with Session(engine) as db:
        report = rotate_stored_keys(db, current, next_key)
        assert report['status'] == 'verified' and not report['writes_performed']
    assert ciphertexts(engine) == before
    assert settings.user_api_key_encryption_key == current


def test_postgres_apply_rotates_both_credentials_and_application_reads_new_key(postgres_rotation, monkeypatch):
    engine, current, next_key = postgres_rotation
    with Session(engine) as db:
        metadata = db.execute(select(AiSettings.id, AiSettings.user_id, AiSettings.provider,
                                     AiSettings.model, AiSettings.created_at).order_by(AiSettings.id)).all()
        report = rotate_stored_keys(db, current, next_key, apply=True, writers_stopped=True)
        assert report == {'status': 'rotated', 'settings_rows': 2, 'encrypted_values_checked': 3,
                          'writes_performed': True, 'configuration_changed': False}
    for index, api_key, asr_key in ciphertexts(engine):
        assert Fernet(next_key.encode()).decrypt(api_key.encode()) == f'model-{index}'.encode()
        with pytest.raises(InvalidToken):
            Fernet(current.encode()).decrypt(api_key.encode())
        if index == '0':
            assert Fernet(next_key.encode()).decrypt(asr_key.encode()) == b'asr-0'
        else:
            assert asr_key is None
    monkeypatch.setattr(settings, 'user_api_key_encryption_key', next_key)
    monkeypatch.setattr(settings, 'auth_mode', 'supabase')
    with Session(engine) as db:
        assert db.execute(select(AiSettings.id, AiSettings.user_id, AiSettings.provider,
                                 AiSettings.model, AiSettings.created_at).order_by(AiSettings.id)).all() == metadata
        for row in db.scalars(select(AiSettings).order_by(AiSettings.id)):
            user = db.get(User, row.user_id)
            assert ai_settings.resolve_llm(user)[0] == f'model-{row.id}'
            assert ai_settings.resolve_asr_key(user) == ('asr-0' if row.id == '0' else 'model-1')


@pytest.mark.parametrize('failure', ['wrong_key', 'corrupt_asr', 'budget'])
def test_apply_preflight_failure_never_updates_any_row(postgres_rotation, failure):
    engine, current, next_key = postgres_rotation
    if failure == 'corrupt_asr':
        with Session(engine) as db:
            db.get(AiSettings, '1').encrypted_asr_api_key = 'synthetic-invalid-token'
            db.commit()
    before = ciphertexts(engine)
    statements = []
    def record(connection, cursor, statement, *args):
        statements.append(statement.split()[0].upper())
    event.listen(engine, 'before_cursor_execute', record)
    try:
        with Session(engine) as db, pytest.raises(KeyRotationError):
            rotate_stored_keys(db, Fernet.generate_key().decode() if failure == 'wrong_key' else current,
                               next_key, apply=True, writers_stopped=True, max_rows=1 if failure == 'budget' else 100)
    finally:
        event.remove(engine, 'before_cursor_execute', record)
    assert 'UPDATE' not in statements
    assert ciphertexts(engine) == before


@pytest.mark.parametrize('failure', ['sql_failure', 'trigger_changes_ciphertext'])
def test_postgres_write_or_readback_failure_rolls_back_every_credential(postgres_rotation, failure):
    engine, current, next_key = postgres_rotation
    before = ciphertexts(engine)
    with engine.begin() as connection:
        if failure == 'sql_failure':
            body = "IF NEW.id = '1' THEN RAISE EXCEPTION 'synthetic-private-error'; END IF;"
        else:
            replacement = Fernet(next_key.encode()).encrypt(b'synthetic-wrong-plaintext').decode()
            # A valid next-key token still must not substitute another user's secret.
            body = f"NEW.encrypted_api_key := '{replacement}';"
        connection.exec_driver_sql(f"CREATE FUNCTION synthetic_rotation_trigger() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN {body} RETURN NEW; END $$")
        connection.exec_driver_sql('CREATE TRIGGER synthetic_rotation_trigger BEFORE UPDATE ON ai_settings FOR EACH ROW EXECUTE FUNCTION synthetic_rotation_trigger()')
    with Session(engine) as db:
        with pytest.raises(KeyRotationError) as error:
            rotate_stored_keys(db, current, next_key, apply=True, writers_stopped=True)
    assert str(error.value) == ('rotation_failed' if failure == 'sql_failure' else 'stored_ciphertext_verification_failed')
    assert ciphertexts(engine) == before


@pytest.mark.parametrize('apply', [False, True])
def test_rotation_rejects_filtered_view_instead_of_partial_or_empty_success(postgres_rotation, apply):
    engine, current, next_key = postgres_rotation
    before = ciphertexts(engine)
    role = 'vm_rotation_reader_' + uuid4().hex[:12]
    with engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE ROLE "{role}" NOLOGIN')
        connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO "{role}"')
        connection.exec_driver_sql(f'GRANT SELECT, UPDATE ON ai_settings TO "{role}"')
        connection.exec_driver_sql('ALTER TABLE ai_settings ENABLE ROW LEVEL SECURITY')
        connection.exec_driver_sql("CREATE POLICY synthetic_partial ON ai_settings USING (id = '0')")
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql(f'SET ROLE "{role}"')
            connection.commit()
            try:
                assert connection.scalar(text('SELECT count(*) FROM ai_settings')) == 1
                connection.commit()
                with Session(bind=connection) as db, pytest.raises(KeyRotationError, match='unfiltered_backend_view_required'):
                    rotate_stored_keys(db, current, next_key, apply=apply, writers_stopped=apply)
            finally:
                connection.rollback()
                connection.exec_driver_sql('RESET ROLE')
                connection.commit()
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(f'DROP OWNED BY "{role}"')
            connection.exec_driver_sql(f'DROP ROLE "{role}"')
    assert ciphertexts(engine) == before


@pytest.mark.parametrize('competing_write', ['insert', 'update', 'delete', 'rotation'])
def test_rotation_table_lock_blocks_all_competing_credential_writes(postgres_rotation, competing_write):
    engine, current, next_key = postgres_rotation
    entered, release = Event(), Event()
    def hold_lock(connection, cursor, statement, *args):
        if statement.startswith('LOCK TABLE public.ai_settings'):
            entered.set()
            assert release.wait(timeout=10)
    event.listen(engine, 'after_cursor_execute', hold_lock)
    def rotate():
        with Session(engine) as db:
            return rotate_stored_keys(db, current, next_key, apply=True, writers_stopped=True)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(rotate)
            try:
                assert entered.wait(timeout=5)
                with engine.connect() as connection:
                    connection.exec_driver_sql("SET LOCAL lock_timeout = '200ms'")
                    sql = {
                        'insert': 'INSERT INTO ai_settings SELECT * FROM ai_settings WHERE false',
                        'update': "UPDATE ai_settings SET model = 'competing' WHERE id = '0'",
                        'delete': "DELETE FROM ai_settings WHERE id = '0'",
                        'rotation': 'LOCK TABLE public.ai_settings IN SHARE ROW EXCLUSIVE MODE',
                    }[competing_write]
                    with pytest.raises(OperationalError) as error:
                        connection.exec_driver_sql(sql)
                    assert error.value.orig.sqlstate == '55P03'
                    connection.rollback()
            finally:
                release.set()
            assert future.result(timeout=10)['status'] == 'rotated'
    finally:
        event.remove(engine, 'after_cursor_execute', hold_lock)
    for _, value, _ in ciphertexts(engine):
        Fernet(next_key.encode()).decrypt(value.encode())


def test_cli_apply_changes_only_database_and_followup_preflight_verifies(postgres_rotation, tmp_path, monkeypatch, capsys):
    engine, current, next_key = postgres_rotation
    arguments, paths = key_arguments(tmp_path, current, next_key)
    monkeypatch.setattr(rotate_user_keys, 'SessionLocal', lambda: Session(engine))
    assert rotate_user_keys.main(arguments + ['--apply', '--writers-stopped']) == 0
    output = capsys.readouterr().out
    assert json.loads(output)['status'] == 'rotated'
    assert current not in output and next_key not in output and str(tmp_path) not in output
    assert [path.read_text() for path in paths] == [current + '\n', next_key + '\n']
    # Repeating with the old key fails, never silently rotates only a subset.
    after = ciphertexts(engine)
    assert rotate_user_keys.main(arguments + ['--apply', '--writers-stopped']) == 1
    assert json.loads(capsys.readouterr().out)['writes_may_have_occurred'] is True
    assert ciphertexts(engine) == after
    later = Fernet.generate_key().decode()
    paths[0].write_text(next_key)
    paths[1].write_text(later)
    assert rotate_user_keys.main(arguments) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'verified'
    assert ciphertexts(engine) == after


def test_empty_postgres_apply_does_not_claim_rotation(postgres_rotation):
    engine, current, next_key = postgres_rotation
    with engine.begin() as connection:
        connection.exec_driver_sql('DELETE FROM ai_settings')
    with Session(engine) as db:
        report = rotate_stored_keys(db, current, next_key, apply=True, writers_stopped=True)
    assert report['status'] == 'inconclusive' and not report['writes_performed']


def test_cli_lost_commit_acknowledgement_reports_uncertainty_without_reverting_config(
    postgres_rotation, tmp_path, monkeypatch, capsys,
):
    engine, current, next_key = postgres_rotation
    arguments, paths = key_arguments(tmp_path, current, next_key)
    class LostAcknowledgement(Session):
        def commit(self):
            super().commit()
            # Simulate losing the result AFTER PostgreSQL committed; rollback
            # cannot undo that commit and the CLI must never claim no writes.
            raise RuntimeError('synthetic-private-commit-error')
    monkeypatch.setattr(rotate_user_keys, 'SessionLocal', lambda: LostAcknowledgement(engine))
    assert rotate_user_keys.main(arguments + ['--apply', '--writers-stopped']) == 1
    output = capsys.readouterr().out
    assert json.loads(output) == {'status': 'failed', 'reason': 'rotation_failed',
                                 'writes_may_have_occurred': True, 'configuration_changed': False}
    assert 'synthetic-private-commit-error' not in output
    for _, api_key, _ in ciphertexts(engine):
        Fernet(next_key.encode()).decrypt(api_key.encode())
        with pytest.raises(InvalidToken):
            Fernet(current.encode()).decrypt(api_key.encode())
    assert [path.read_text() for path in paths] == [current + '\n', next_key + '\n']


def test_rotation_targets_public_table_even_with_shadowing_search_path(postgres_rotation):
    engine, current, next_key = postgres_rotation
    before = ciphertexts(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE SCHEMA synthetic_shadow')
        connection.exec_driver_sql('CREATE TABLE synthetic_shadow.ai_settings AS TABLE public.ai_settings')
    with engine.connect() as connection:
        connection.exec_driver_sql('SET search_path = synthetic_shadow, public')
        connection.commit()
        try:
            with Session(bind=connection) as db:
                assert rotate_stored_keys(db, current, next_key, apply=True, writers_stopped=True)['status'] == 'rotated'
            assert connection.exec_driver_sql('SHOW search_path').scalar() == 'synthetic_shadow, public'
            assert connection.execute(text('SELECT id, encrypted_api_key, encrypted_asr_api_key FROM synthetic_shadow.ai_settings ORDER BY id')).all() == before
        finally:
            connection.rollback()
            connection.exec_driver_sql('RESET search_path')
            connection.commit()
    for _, value, _ in ciphertexts(engine):
        Fernet(next_key.encode()).decrypt(value.encode())
