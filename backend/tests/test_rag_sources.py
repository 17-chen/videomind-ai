"""SQL-authoritative source checks with deliberately faulty index results."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models import User, Video
from app.services import rag
from app.services.vector_store import VectorSearchResult


def hit(video_id, document='Synthetic evidence', title='Synthetic title'):
    return VectorSearchResult(
        video_id=video_id, title=title, url=f'/videos/{video_id}',
        category='Test', document=document, distance=0.1,
    )


@pytest.fixture
def library(monkeypatch):
    engine = create_engine('sqlite+pysqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        alice = User(email='rag-alice@example.com', password_hash='synthetic')
        bob = User(email='rag-bob@example.com', password_hash='synthetic')
        first = Video(user=alice, title='First', url='https://example.com/first', tags=[])
        second = Video(user=alice, title='Second', url='https://example.com/second', tags=[])
        foreign = Video(user=bob, title='Private', url='https://example.com/private', tags=[])
        db.add_all([first, second, foreign])
        db.commit()
        candidates, queries, prompts = [], [], []

        def query(**kwargs):
            queries.append(kwargs)
            return list(candidates)

        def complete(**kwargs):
            prompts.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='Grounded answer [1]'))])

        monkeypatch.setattr(rag, 'vector_store', SimpleNamespace(query_video_documents=query))
        monkeypatch.setattr(rag, 'get_llm_client', lambda user: (
            SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=complete))), 'synthetic-model',
        ))
        yield db, alice, (first, second, foreign), candidates, queries, prompts
    engine.dispose()


def test_untrusted_index_is_filtered_before_prompt_and_source_numbering(library):
    db, alice, (first, second, foreign), candidates, queries, prompts = library
    candidates.extend([
        hit(foreign.id, 'FOREIGN_SENTINEL'), hit(str(uuid4()), 'DELETED_SENTINEL'),
        hit(second.id, 'Second evidence', 'Second'), hit(second.id, 'DUPLICATE_SENTINEL'),
        hit(first.id, 'First evidence', 'First'),
    ])
    result = rag.chat_with_videos(db, alice, 'Compare my videos', 10)
    assert queries == [{'user_id': alice.id, 'query': 'Compare my videos', 'limit': 10}]
    assert [source.video_id for source in result.sources] == [second.id, first.id]
    assert [source.snippet for source in result.sources] == ['Second evidence', 'First evidence']
    assert len(prompts) == 1
    context = prompts[0]['messages'][1]['content']
    assert '[1]\n标题：Second' in context
    assert '[2]\n标题：First' in context
    assert all(secret not in context for secret in ('FOREIGN_SENTINEL', 'DELETED_SENTINEL', 'DUPLICATE_SENTINEL'))
    assert '[3]' not in context
    assert '不得编造来源' in prompts[0]['messages'][0]['content']
    assert result.answer == 'Grounded answer [1]'


def test_source_metadata_comes_from_owned_video_not_stale_index(library):
    db, alice, (first, _, _), candidates, _, prompts = library
    first.source = 'upload'
    first.user_category = 'Current category'
    db.commit()
    candidates.append(replace(hit(first.id), title='STALE_TITLE',
                              url='https://example.com/STALE_URL', category='STALE_CATEGORY'))

    result = rag.chat_with_videos(db, alice, 'Question', 5)

    assert [(source.title, source.url, source.category) for source in result.sources] == [
        ('First', f'/videos/{first.id}', 'Current category')
    ]
    context = prompts[0]['messages'][1]['content']
    assert f'标题：First\n链接：/videos/{first.id}\n分类：Current category' in context
    assert 'STALE_' not in context


@pytest.mark.parametrize('language', ['zh', 'en'])
@pytest.mark.parametrize('kind', ['foreign', 'deleted', 'blank', 'empty'])
def test_no_authorized_evidence_never_calls_model(library, language, kind):
    db, alice, (first, _, foreign), candidates, _, prompts = library
    if kind == 'foreign':
        candidates.append(hit(foreign.id, 'PRIVATE_SENTINEL'))
    elif kind == 'deleted':
        candidates.append(hit(first.id, 'DELETED_SENTINEL'))
        db.delete(first)
        db.commit()
    elif kind == 'blank':
        candidates.append(hit(first.id, ' \n\t'))
    result = rag.chat_with_videos(db, alice, 'Question', 5, language)
    assert result.sources == []
    assert prompts == []
    assert 'SENTINEL' not in result.answer
    if language == 'en':
        assert result.answer == 'No relevant videos found in your library yet.'
    else:
        assert result.answer == rag.t('no_relevant_videos')


def test_database_verification_failure_never_falls_back_to_index(library, monkeypatch):
    db, alice, (first, _, _), candidates, _, prompts = library
    candidates.append(hit(first.id))

    def unavailable(*args, **kwargs):
        raise SQLAlchemyError('synthetic unavailable database')

    monkeypatch.setattr(db, 'scalars', unavailable)
    with pytest.raises(SQLAlchemyError):
        rag.chat_with_videos(db, alice, 'Question', 5)
    assert prompts == []
