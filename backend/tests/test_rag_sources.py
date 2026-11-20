"""SQL-authoritative source checks with deliberately faulty index results."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

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
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
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


@pytest.fixture
def chat_api(library):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.dependencies import get_db, get_current_user
    from app.api.v1.routes.chat import router
    from app.core.errors import register_exception_handlers

    db, alice, (first, _, _), candidates, _, _ = library
    candidates.append(hit(first.id))
    api = FastAPI()
    api.include_router(router, prefix='/chat')
    register_exception_handlers(api)
    api.dependency_overrides[get_db] = lambda: db
    api.dependency_overrides[get_current_user] = lambda: alice
    with TestClient(api) as client:
        yield client


@pytest.mark.parametrize('language', ['zh', 'en'])
@pytest.mark.parametrize('upstream,expected', [
    (401, 502), (403, 502), (429, 503), (500, 502), (422, 502),
    ('timeout', 504), ('connection', 503),
])
def test_provider_failures_return_actionable_safe_http_errors(chat_api, library, monkeypatch, language, upstream, expected):
    import httpx
    from openai import OpenAI

    calls = []
    def respond(request):
        calls.append(request)
        if upstream == 'timeout':
            raise httpx.ReadTimeout('SENSITIVE_PROVIDER_BODY', request=request)
        if upstream == 'connection':
            raise httpx.ConnectError('SENSITIVE_PROVIDER_BODY', request=request)
        return httpx.Response(upstream, json={'error': {'message': 'SENSITIVE_PROVIDER_BODY', 'type': 'synthetic'}}, request=request)

    with OpenAI(api_key='synthetic-user-key', max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(respond))) as model:
        monkeypatch.setattr(rag, 'get_llm_client', lambda user: (model, 'synthetic-model'))
        response = chat_api.post('/chat', json={'question': 'Question', 'language': language})
    assert response.status_code == expected
    detail = response.json()['detail']
    assert ('model' in detail) if language == 'en' else ('模型' in detail)
    assert 'SENSITIVE_PROVIDER_BODY' not in response.text
    assert 'synthetic-user-key' not in response.text
    assert 'sources' not in response.json()
    assert len(calls) == 1  # This application error handler does not resubmit.
    assert calls[0].headers['authorization'] == 'Bearer synthetic-user-key'
    assert library[-1] == []


@pytest.mark.parametrize('content', [None, '', ' \n\t'])
def test_empty_provider_answer_is_not_reported_as_success(chat_api, monkeypatch, content):
    def complete(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
    monkeypatch.setattr(rag, 'get_llm_client', lambda user: (
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=complete))), 'synthetic-model',
    ))
    response = chat_api.post('/chat', json={'question': 'Question'})
    assert response.status_code == 502
    assert '有效正文' in response.json()['detail']


def test_no_choices_is_a_provider_failure(chat_api, monkeypatch):
    monkeypatch.setattr(rag, 'get_llm_client', lambda user: (
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(choices=[])))), 'synthetic-model',
    ))
    assert chat_api.post('/chat', json={'question': 'Question'}).status_code == 502


@pytest.mark.parametrize('question', ['', ' ', '\n\t', '\u3000'])
def test_blank_question_never_retrieves_or_calls_provider(chat_api, library, question):
    from app.models.request_window import RequestWindow

    response = chat_api.post('/chat', json={'question': question})
    assert response.status_code == 422
    assert library[-2] == []
    assert library[-1] == []
    assert library[0].query(RequestWindow).count() == 0


def test_question_is_trimmed_before_retrieval_and_prompt(chat_api, library):
    response = chat_api.post('/chat', json={'question': '  Question \n'})
    assert response.status_code == 200
    assert library[-2][0]['query'] == 'Question'
    assert library[-1][0]['messages'][1]['content'].startswith('用户问题：Question\n')


def test_provider_error_can_be_retried_explicitly_without_losing_sources(chat_api, library, monkeypatch):
    import httpx
    from openai import OpenAI

    calls = []
    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(401, json={'error': {'message': 'SENSITIVE_PROVIDER_BODY'}}, request=request)
        return httpx.Response(200, json={'id': 'synthetic', 'created': 0, 'model': 'synthetic-model',
            'object': 'chat.completion', 'choices': [{'index': 0, 'finish_reason': 'stop',
            'message': {'role': 'assistant', 'content': 'Recovered answer [1]'}}]}, request=request)

    with OpenAI(api_key='synthetic-user-key', max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(respond))) as model:
        monkeypatch.setattr(rag, 'get_llm_client', lambda user: (model, 'synthetic-model'))
        assert chat_api.post('/chat', json={'question': 'Question'}).status_code == 502
        response = chat_api.post('/chat', json={'question': 'Question'})
    assert response.status_code == 200
    assert response.json()['answer'] == 'Recovered answer [1]'
    assert [source['video_id'] for source in response.json()['sources']] == [library[2][0].id]
    assert len(calls) == 2


def test_missing_own_key_still_never_uses_owner_configuration(chat_api, monkeypatch):
    from app.core.config import settings
    from app.services.ai_provider import get_llm_client

    monkeypatch.setattr(settings, 'auth_mode', 'supabase')
    monkeypatch.setattr(settings, 'deepseek_api_key', 'synthetic-owner-key-never-use')
    monkeypatch.setattr(rag, 'get_llm_client', get_llm_client)
    response = chat_api.post('/chat', json={'question': 'Question'})
    assert response.status_code == 400
    assert '自己的模型' in response.json()['detail']
    assert 'synthetic-owner-key' not in response.text
