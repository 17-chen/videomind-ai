"""Manual fixture for a NEW disposable PostgreSQL cluster only.

seed creates two fixed-name synthetic databases and never overwrites them.
exercise checks the restored copy, then deliberately corrupts its transcript.
Never use real credentials or a running application database for this fixture.
"""

import base64
import json
import sys
from pathlib import Path
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models import User, Video, Transcript, Summary, AiSettings, Embedding, VideoTask
from app.services.object_storage.models import StoredArtifact
from app.services.database_restore_verification import compare_database_restore
from scripts.prepare_pgvector import migration_config as vector_config
from scripts.prepare_objects import migration_config as objects_config
from scripts.verify_key_recovery import verify_stored_keys

if len(sys.argv) != 2 or sys.argv[1] not in ('seed', 'exercise'):
    raise SystemExit('Choose seed or exercise in a NEW disposable test cluster')

base = create_engine(settings.database_url, isolation_level='AUTOCOMMIT')
source = create_engine(base.url.set(database='vm_source_probe'))
target = create_engine(base.url.set(database='vm_restore_probe'))
# Deliberately synthetic test key, never an application/master key.
key = base64.urlsafe_b64encode(b'0' * 32).decode()
try:
    if sys.argv[1] == 'seed':
        with base.connect() as db:
            db.execute(text('CREATE DATABASE vm_source_probe'))
            db.execute(text('CREATE DATABASE vm_restore_probe'))
        settings.database_url = source.url.render_as_string(hide_password=False)
        root = Path(__file__).resolve().parents[2]
        config = Config(str(root / 'alembic.ini'))
        config.set_main_option('script_location', str(root / 'alembic'))
        command.upgrade(config, 'head')
        with source.begin() as db:
            for optional in (vector_config(), objects_config()):
                optional.attributes['connection'] = db
                command.upgrade(optional, 'head')
        with Session(source) as db:
            owner = User(email='synthetic-restore-a@example.com', password_hash='test-only')
            other = User(email='synthetic-restore-b@example.com', password_hash='test-only')
            video = Video(user=owner, url='https://example.com/synthetic', source='upload', tags=['test'], status='completed')
            video.transcript = Transcript(content='Synthetic recovery transcript')
            video.summary = Summary(summary='Synthetic recovery summary', markdown_note='Synthetic note')
            video.embedding = Embedding(vector_id='synthetic-vector')
            db.add_all([video, other])
            db.flush()
            db.add(AiSettings(user=owner, provider='deepseek', model='synthetic',
                encrypted_api_key=Fernet(key.encode()).encrypt(b'synthetic-provider-key').decode()))
            db.add(VideoTask(video=video, user=owner, kind='run', status='succeeded', stage='completed'))
            db.add(StoredArtifact(user_id=owner.id, video_id=video.id, kind='note', filename=f'{video.id}.md',
                bucket='synthetic', project_fingerprint='0'*64, sha256='0'*64, size_bytes=14, state='ready'))
            db.execute(text('''INSERT INTO vm_vector_chunks
                (user_id,video_id,model_key,dimensions,chunk_index,title,url,source,document,embedding)
                VALUES (:user,:video,'synthetic:2',2,0,'Synthetic','https://example.com/synthetic','upload','Synthetic passage','[1,0]')'''),
                {'user': owner.id, 'video': video.id})
            db.commit()
        print(json.dumps({'synthetic_seed': 'created', 'cloud_calls': 0}))
    else:
        report = compare_database_restore(source, target)
        print(json.dumps(report))
        assert report['status'] == 'matched'
        assert all(v['status'] == 'matched' for v in report['tables'].values())
        with Session(target) as db:
            result = verify_stored_keys(db, key)
            print(json.dumps({'restored_synthetic_key_check': result}))
            assert result['status'] == 'verified'
        with target.begin() as db:
            db.execute(text("UPDATE transcripts SET content='Changed synthetic content with identical row count'"))
        changed = compare_database_restore(source, target)
        print(json.dumps({'same_count_corruption_check': changed['tables']['transcripts']}))
        assert changed['status'] == 'mismatch'
finally:
    source.dispose()
    target.dispose()
    base.dispose()
