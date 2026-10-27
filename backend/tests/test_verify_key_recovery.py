import json

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models import AiSettings, User  # noqa: F401
from scripts import verify_key_recovery


def test_verifier_checks_both_ciphertexts_without_disclosing_values(capsys, monkeypatch, tmp_path):
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    key = Fernet.generate_key()
    cipher = Fernet(key)
    with Session(engine) as db:
        user = User(email="private@example.com", password_hash="test-only", auth_subject="synthetic-user")
        db.add(user)
        db.flush()
        db.add(AiSettings(
            user_id=user.id, provider="openai", model="test",
            encrypted_api_key=cipher.encrypt(b"private-model-token").decode(),
            encrypted_asr_api_key=cipher.encrypt(b"private-asr-token").decode(),
        ))
        db.commit()
        assert verify_key_recovery.verify_stored_keys(db, key.decode()) == {
            "status": "verified", "settings_rows": 1, "encrypted_values_checked": 2,
        }
        wrong = Fernet.generate_key().decode()
        with pytest.raises(verify_key_recovery.KeyVerificationError, match="decryption_failed"):
            verify_key_recovery.verify_stored_keys(db, wrong)

    key_file = tmp_path / "master.key"
    key_file.write_bytes(key + b"\n")
    key_file.chmod(0o600)
    monkeypatch.setattr(verify_key_recovery, "SessionLocal", lambda: Session(engine))
    assert verify_key_recovery.main(["--key-file", str(key_file)]) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["encrypted_values_checked"] == 2
    assert "private" not in output and key.decode() not in output
    key_file.chmod(0o644)
    assert verify_key_recovery.main(["--key-file", str(key_file)]) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "key_file_not_private"
    engine.dispose()


def test_verifier_reports_empty_database_as_inconclusive(monkeypatch, capsys):
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    key = Fernet.generate_key().decode()
    with Session(engine) as db:
        result = verify_key_recovery.verify_stored_keys(db, key)
    assert result == {"status": "inconclusive", "settings_rows": 0, "encrypted_values_checked": 0}
    monkeypatch.setattr(verify_key_recovery, "SessionLocal", lambda: Session(engine))
    monkeypatch.setattr(verify_key_recovery.settings, "user_api_key_encryption_key", key)
    assert verify_key_recovery.main([]) == 2
    assert json.loads(capsys.readouterr().out) == result
    engine.dispose()
