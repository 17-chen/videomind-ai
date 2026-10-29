"""Opt-in real PostgreSQL concurrency checks, always using a disposable database."""

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import os
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.database.base import Base
from app.models import User, Video
from app.services import video_upload
from app.services.storage_quota import ARTIFACT_KINDS, artifact_directory, generate_artifacts, user_storage_bytes


pytestmark = pytest.mark.skipif(
    os.environ.get('RUN_POSTGRES_QUOTA_TESTS') != '1',
    reason='Set RUN_POSTGRES_QUOTA_TESTS=1 to create a disposable PostgreSQL database',
)


@pytest.fixture
def postgres_quota(monkeypatch, tmp_path):
    for kind in ARTIFACT_KINDS:
        monkeypatch.setattr(settings, f'{kind}_storage_dir', str(tmp_path / kind))
    monkeypatch.setattr(settings, 'max_user_storage_mb', 1)
    monkeypatch.setattr(video_upload, '_probe_video', lambda _: 1)
    admin = create_engine(settings.database_url, isolation_level='AUTOCOMMIT')
    database = f'vm_quota_test_{uuid4().hex}'
    engine = None
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database}"'))
            created = True
        engine = create_engine(admin.url.set(database=database), connect_args={'options': '-c statement_timeout=15000'})
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            user = User(email='quota-test@example.com', password_hash='synthetic')
            videos = [Video(user=user, url=f'https://example.com/{i}', tags=[]) for i in range(2)]
            db.add_all(videos)
            db.commit()
            ids, user_id = [video.id for video in videos], user.id
        yield engine, ids, user_id
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{database}"'))
        admin.dispose()


@pytest.mark.parametrize('with_upload', [False, True], ids=['two-generated-files', 'upload-vs-generated-file'])
def test_postgres_serializes_total_quota_across_sessions(postgres_quota, with_upload):
    engine, ids, user_id = postgres_quota
    ready = Barrier(2)

    def write(index):
        with Session(engine) as db:
            video = db.get(Video, ids[index])
            try:
                if with_upload and index == 1:
                    ready.wait(timeout=10)
                    video_upload.save_uploaded_video(
                        db, video.user, UploadFile(BytesIO(b'u' * (700 * 1024)), filename='synthetic.mp4'),
                    )
                else:
                    def produce():
                        root = artifact_directory('audio')
                        path = root / f'{video.id}.mp3'
                        path.write_bytes(b'a' * (700 * 1024))
                        ready.wait(timeout=10)
                    generate_artifacts(db, video, 'audio', produce)
                return 201
            except ApiError as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(write, [0, 1]))
    assert sorted(codes) == [201, 413]
    with Session(engine) as db:
        assert user_storage_bytes(db, user_id) == 700 * 1024
    for kind in ARTIFACT_KINDS:
        assert not list(artifact_directory(kind).glob('.staging-*'))
        assert not list(artifact_directory(kind).glob('*.part'))
