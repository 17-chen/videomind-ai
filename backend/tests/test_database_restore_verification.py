"""Actual PostgreSQL comparisons; all data and keys are synthetic and disposable."""

import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.base import Base
from app.models import User, Video
from app.services.database_restore_verification import compare_database_restore
from scripts import verify_database_restore


requires_postgres = pytest.mark.skipif(os.environ.get('RUN_POSTGRES_QUOTA_TESTS') != '1',
    reason='Requires disposable PostgreSQL databases')


@pytest.fixture
def databases():
    admin = create_engine(settings.database_url, isolation_level='AUTOCOMMIT')
    names = [f'vm_source_{uuid4().hex}', f'vm_restore_{uuid4().hex}']
    engines = []
    created = []
    try:
        for name in names:
            with admin.connect() as db:
                db.execute(text(f'CREATE DATABASE "{name}"'))
            created.append(name)
            engine = create_engine(admin.url.set(database=name))
            engines.append(engine)
            Base.metadata.create_all(engine)
            with Session(engine) as db:
                user = User(id='synthetic-user', email='restore-private@example.com', password_hash='private-secret')
                video = Video(id='synthetic-video', user=user, url='https://example.com/private', tags=['test'])
                db.add(video)
                db.commit()
            # Normalize server timestamps to the same recovery point.
            with engine.begin() as db:
                for table in ('users', 'videos'):
                    db.execute(text(f"UPDATE {table} SET created_at='2026-11-10', updated_at='2026-11-10'"))
        yield engines
    finally:
        for engine in engines:
            engine.dispose()
        with admin.connect() as db:
            for name in created:
                db.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()


@requires_postgres
def test_equal_content_matches_without_disclosing_data_or_digests(databases):
    report = compare_database_restore(*databases)
    assert report['status'] == 'matched'
    assert report['tables']['videos']['source_rows'] == 1
    assert report['tables']['vm_storage_objects']['status'] == 'not_present'
    assert report['writes_performed'] is False
    output = json.dumps(report)
    for private in ('synthetic-video', 'synthetic-user', 'restore-private', 'private-secret', 'https://', 'sha256'):
        assert private not in output


@requires_postgres
def test_same_row_count_with_changed_content_is_a_mismatch(databases):
    with databases[1].begin() as db:
        db.execute(text("UPDATE users SET password_hash='different-private-secret'"))
    result = compare_database_restore(*databases)
    assert result['status'] == 'mismatch'
    assert result['tables']['users'] == {'status': 'mismatch', 'source_rows': 1, 'restored_rows': 1}
    assert 'different-private-secret' not in json.dumps(result)


@requires_postgres
def test_high_precision_json_change_is_not_rounded_into_a_match(databases):
    for engine, payload in zip(databases, ('[0.10000000000000000001]', '[0.10000000000000000002]')):
        with engine.begin() as db:
            db.execute(text('UPDATE videos SET tags=CAST(:payload AS json)'), {'payload': payload})
    report = compare_database_restore(*databases)
    assert report['status'] == 'mismatch'
    assert report['tables']['videos']['source_rows'] == report['tables']['videos']['restored_rows'] == 1


@requires_postgres
@pytest.mark.parametrize('change', ['column', 'missing_optional', 'version'])
def test_schema_and_migration_changes_are_detected(databases, change):
    if change == 'column':
        with databases[1].begin() as db:
            db.execute(text('ALTER TABLE users ADD COLUMN unexpected TEXT'))
        name = 'users'
    else:
        for engine in databases:
            with engine.begin() as db:
                db.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
                db.execute(text("INSERT INTO alembic_version VALUES ('baseline')"))
        name = 'alembic_version'
        with databases[1].begin() as db:
            db.execute(text('DROP TABLE alembic_version') if change == 'missing_optional'
                       else text("UPDATE alembic_version SET version_num='wrong'"))
    result = compare_database_restore(*databases)
    assert result['status'] == 'mismatch'
    assert result['tables'][name]['status'] == 'mismatch'


@requires_postgres
@pytest.mark.parametrize('budget', [{'max_rows': 1}, {'max_bytes': 1}])
def test_partial_comparison_never_claims_matched(databases, budget):
    report = compare_database_restore(*databases, **budget)
    assert report['status'] == 'inconclusive'
    assert report['reason'] == 'read_budget_exceeded'


@requires_postgres
def test_same_database_rejected_before_reading_rows(databases):
    report = compare_database_restore(databases[1], databases[1])
    assert report['status'] == 'unavailable'
    assert report['reason'] == 'target_not_isolated'
    assert report['rows_read'] == 0


@requires_postgres
def test_comparison_transactions_are_read_only_and_schema_failure_is_sanitized(databases, monkeypatch):
    from app.services import database_restore_verification as verifier
    original = verifier._shape
    def guarded(connection, table):
        assert connection.scalar(text('SHOW transaction_read_only')) == 'on'
        assert connection.scalar(text('SHOW transaction_isolation')) == 'repeatable read'
        return original(connection, table)
    monkeypatch.setattr(verifier, '_shape', guarded)
    assert compare_database_restore(*databases)['status'] == 'matched'
    with databases[1].begin() as db:
        db.execute(text('ALTER TABLE users DROP CONSTRAINT users_pkey CASCADE'))
    report = compare_database_restore(*databases)
    assert report['status'] == 'unavailable'
    assert report['reason'] == 'database_verification_failed'


def test_cli_missing_target_and_invalid_url_never_disclose_configuration(monkeypatch, capsys):
    monkeypatch.delenv('RESTORE_VERIFICATION_DATABASE_URL', raising=False)
    assert verify_database_restore.main([]) == 2
    assert json.loads(capsys.readouterr().out)['reason'] == 'restore_target_missing'
    monkeypatch.setenv('RESTORE_VERIFICATION_DATABASE_URL', 'invalid://private:secret@private-host')
    assert verify_database_restore.main([]) == 2
    output = capsys.readouterr().out
    assert 'private' not in output and 'secret' not in output
    assert json.loads(output)['status'] == 'unavailable'


def test_cli_rejects_invalid_budget_before_loading_configuration(monkeypatch):
    with pytest.raises(SystemExit) as result:
        verify_database_restore.main(['--max-rows', '0'])
    assert result.value.code == 2


@requires_postgres
def test_rls_filtered_snapshot_cannot_claim_a_complete_match(databases, monkeypatch):
    from app.services import database_restore_verification as verifier
    source = databases[0]
    role = f'vm_restore_reader_{uuid4().hex}'
    with source.begin() as db:
        db.execute(text(f'CREATE ROLE "{role}" NOLOGIN'))
        db.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
        db.execute(text(f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{role}"'))
        db.execute(text('ALTER TABLE users ENABLE ROW LEVEL SECURITY'))
    original = verifier._shape
    def restricted(connection, table):
        if connection.engine is source:
            connection.execute(text(f'SET LOCAL ROLE "{role}"'))
        return original(connection, table)
    monkeypatch.setattr(verifier, '_shape', restricted)
    try:
        result = compare_database_restore(*databases)
        assert result['status'] == 'unavailable'
        assert result['rows_read'] == 0
        assert role not in json.dumps(result)
    finally:
        with source.begin() as db:
            db.execute(text(f'DROP OWNED BY "{role}"'))
            db.execute(text(f'DROP ROLE "{role}"'))
