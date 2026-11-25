"""Synthetic credentials only; no real key files or provider requests."""

import json
import os

from cryptography.fernet import Fernet
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models import AiSettings, User
from app.services.key_rotation import KeyRotationError, rotate_stored_keys
from scripts import rotate_user_keys


def seed_keys(engine, current):
    cipher = Fernet(current.encode())
    with Session(engine) as db:
        for index in range(2):
            user = User(email=f'synthetic-rotation-{index}@example.com', password_hash='synthetic')
            db.add(user)
            db.flush()
            db.add(AiSettings(id=str(index), user_id=user.id, provider='openai', model='test-only',
                              encrypted_api_key=cipher.encrypt(f'model-{index}'.encode()).decode(),
                              encrypted_asr_api_key=cipher.encrypt(b'asr-0').decode() if index == 0 else None))
        db.commit()


def ciphertexts(engine):
    with Session(engine) as db:
        return db.execute(select(AiSettings.id, AiSettings.encrypted_api_key, AiSettings.encrypted_asr_api_key)
                          .order_by(AiSettings.id)).all()


@pytest.fixture
def rotation_db():
    engine = create_engine('sqlite+pysqlite://', poolclass=StaticPool)
    Base.metadata.create_all(engine)
    current, next_key = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    seed_keys(engine, current)
    try:
        yield engine, current, next_key
    finally:
        engine.dispose()


def test_preflight_verifies_all_values_without_writes(rotation_db):
    engine, current, next_key = rotation_db
    before = ciphertexts(engine)
    def reject_write(connection, cursor, statement, *args):
        assert not statement.lstrip().upper().startswith(('UPDATE', 'INSERT', 'DELETE'))
    event.listen(engine, 'before_cursor_execute', reject_write)
    try:
        with Session(engine) as db:
            assert rotate_stored_keys(db, current, next_key) == {
                'status': 'verified', 'settings_rows': 2, 'encrypted_values_checked': 3,
                'writes_performed': False, 'configuration_changed': False,
            }
        assert ciphertexts(engine) == before
    finally:
        event.remove(engine, 'before_cursor_execute', reject_write)


@pytest.mark.parametrize('problem,reason', [
    ('wrong_key', 'credential_verification_failed'), ('corrupt_asr', 'credential_verification_failed'),
    ('budget', 'row_budget_exceeded'), ('identical', 'distinct_keys_required'),
    ('bad_key', 'invalid_key_format'), ('dirty', 'dedicated_session_required'),
    ('unconfirmed', 'stopped_writers_required'), ('sqlite_apply', 'postgresql_required'),
])
def test_preflight_and_apply_fail_without_partial_changes(rotation_db, problem, reason):
    engine, current, next_key = rotation_db
    if problem == 'corrupt_asr':
        with Session(engine) as db:
            db.get(AiSettings, '1').encrypted_asr_api_key = 'synthetic-invalid-token'
            db.commit()
    before = ciphertexts(engine)
    options = {}
    if problem == 'wrong_key':
        current = Fernet.generate_key().decode()
    elif problem == 'budget':
        options['max_rows'] = 1
    elif problem == 'identical':
        next_key = current
    elif problem == 'bad_key':
        next_key = 'synthetic-invalid-key'
    elif problem in ('unconfirmed', 'sqlite_apply'):
        options = {'apply': True, 'writers_stopped': problem == 'sqlite_apply'}
    with Session(engine) as db:
        if problem == 'dirty':
            db.get(AiSettings, '0').model = 'uncommitted'
        with pytest.raises(KeyRotationError, match=reason):
            rotate_stored_keys(db, current, next_key, **options)
    assert ciphertexts(engine) == before


@pytest.mark.parametrize('budget', [0, 100001])
def test_invalid_budgets_are_rejected(rotation_db, budget):
    engine, current, next_key = rotation_db
    with Session(engine) as db, pytest.raises(KeyRotationError, match='invalid_row_budget'):
        rotate_stored_keys(db, current, next_key, max_rows=budget)


def key_arguments(tmp_path, current, next_key):
    paths = [tmp_path / 'current.key', tmp_path / 'next.key']
    for path, value in zip(paths, (current, next_key), strict=True):
        path.write_text(value + '\n')
        path.chmod(0o600)
    return ['--current-key-file', str(paths[0]), '--next-key-file', str(paths[1])], paths


def test_cli_preflight_is_private_and_never_changes_key_files(rotation_db, tmp_path, monkeypatch, capsys):
    engine, current, next_key = rotation_db
    arguments, paths = key_arguments(tmp_path, current, next_key)
    monkeypatch.setattr(rotate_user_keys, 'SessionLocal', lambda: Session(engine))
    assert rotate_user_keys.main(arguments) == 0
    output = capsys.readouterr().out
    assert json.loads(output)['encrypted_values_checked'] == 3
    for private in (current, next_key, str(tmp_path), 'model-0', 'asr-0', 'example.com'):
        assert private not in output
    assert [path.read_text() for path in paths] == [current + '\n', next_key + '\n']


@pytest.mark.parametrize('kind', ['public', 'symlink', 'fifo', 'large', 'missing', 'directory', 'unicode'])
def test_cli_rejects_unsafe_key_files_before_database_access(rotation_db, tmp_path, monkeypatch, capsys, kind):
    _, current, next_key = rotation_db
    arguments, paths = key_arguments(tmp_path, current, next_key)
    path = paths[1]
    if kind == 'public':
        path.chmod(0o644)
    else:
        path.unlink()
        if kind == 'symlink':
            path.symlink_to(paths[0])
        elif kind == 'fifo':
            os.mkfifo(path, 0o600)
        elif kind == 'large':
            path.write_bytes(b'x' * 129)
            path.chmod(0o600)
        elif kind == 'directory':
            path.mkdir(mode=0o700)
        elif kind == 'unicode':
            path.write_text('合成密钥')
            path.chmod(0o600)
    monkeypatch.setattr(rotate_user_keys, 'SessionLocal', lambda: pytest.fail('No DB for unsafe key files'))
    assert rotate_user_keys.main(arguments) == 1
    output = capsys.readouterr().out
    assert json.loads(output)['writes_may_have_occurred'] is False
    assert str(tmp_path) not in output and current not in output


def test_empty_database_is_inconclusive(rotation_db, tmp_path, monkeypatch, capsys):
    engine, current, next_key = rotation_db
    with engine.begin() as connection:
        connection.execute(AiSettings.__table__.delete())
    arguments, _ = key_arguments(tmp_path, current, next_key)
    monkeypatch.setattr(rotate_user_keys, 'SessionLocal', lambda: Session(engine))
    assert rotate_user_keys.main(arguments) == 2
    assert json.loads(capsys.readouterr().out)['status'] == 'inconclusive'


def test_apply_requires_explicit_stopped_process_confirmation(tmp_path, capsys):
    with pytest.raises(SystemExit) as error:
        rotate_user_keys.main(['--apply', '--current-key-file', str(tmp_path / 'a'), '--next-key-file', str(tmp_path / 'b')])
    assert error.value.code == 2
    assert '--apply requires --writers-stopped' in capsys.readouterr().err


@pytest.mark.parametrize('apply', [False, True])
def test_cli_unexpected_error_is_sanitized(rotation_db, tmp_path, monkeypatch, capsys, apply):
    _, current, next_key = rotation_db
    arguments, _ = key_arguments(tmp_path, current, next_key)
    def unavailable():
        raise RuntimeError('synthetic-secret-sentinel')
    monkeypatch.setattr(rotate_user_keys, 'SessionLocal', unavailable)
    if apply:
        arguments += ['--apply', '--writers-stopped']
    assert rotate_user_keys.main(arguments) == 1
    output = capsys.readouterr().out
    assert json.loads(output) == {'status': 'failed', 'reason': 'rotation_unavailable',
                                 'writes_may_have_occurred': apply, 'configuration_changed': False}
    assert 'synthetic-secret-sentinel' not in output
