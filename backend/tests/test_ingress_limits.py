from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.services.ingress_limits import IngressLimiter, IngressLimitMiddleware


def test_peer_windows_reset_without_extending_on_rejection():
    limiter = IngressLimiter(per_peer=1, total=100)
    assert limiter.consume('a', now=0) == 0
    assert limiter.consume('a', now=59.1) == 1
    assert limiter.consume('b', now=59.1) == 0
    assert limiter.consume('a', now=60) == 0
    assert limiter.consume('b', now=60) == 60


def test_global_budget_counts_peer_rejections_and_resets():
    limiter = IngressLimiter(per_peer=1, total=2)
    assert limiter.consume('a', now=0) == 0
    assert limiter.consume('a', now=1) == 59
    assert limiter.consume('b', now=2) == 58
    assert limiter.consume('b', now=60) == 0


def test_peer_map_is_bounded_and_does_not_evict_active_limits():
    limiter = IngressLimiter(per_peer=1, total=100, max_peers=2)
    assert limiter.consume('a', now=0) == 0
    assert limiter.consume('b', now=1) == 0
    assert limiter.consume('c', now=2) == 58
    assert limiter.consume('a', now=3) == 57
    assert len(limiter.peers) == 2
    assert limiter.consume('c', now=60) == 0
    assert list(limiter.peers) == ['b', 'c']


def test_concurrent_requests_cannot_overrun_peer_budget():
    limiter = IngressLimiter(per_peer=5, total=100)
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: limiter.consume('a', now=0), range(40)))
    assert results.count(0) == 5


def test_rejection_precedes_body_reads_and_downstream_services():
    import asyncio

    limiter = IngressLimiter(per_peer=1, total=100)
    limiter.consume('a')
    sent = []

    async def forbidden(*args):
        raise AssertionError('Body or downstream service must not be accessed')

    async def send(message):
        sent.append(message)

    middleware = IngressLimitMiddleware(forbidden, limiter)
    asyncio.run(middleware(
        {'type': 'http', 'method': 'POST', 'path': '/api/v1/videos/upload', 'client': ('a', 123)},
        forbidden, send,
    ))
    assert sent[0]['status'] == 429


def test_headers_cannot_bypass_limit_and_cors_survives_rejection():
    app = FastAPI()
    calls = []

    @app.get('/protected')
    def protected():
        calls.append(1)
        return {'ok': True}

    @app.get('/health')
    def health():
        return {'ok': True}

    app.add_middleware(IngressLimitMiddleware, limiter=IngressLimiter(1, 100))
    app.add_middleware(CORSMiddleware, allow_origins=['https://example.com'], expose_headers=['Retry-After'])
    client = TestClient(app)
    assert client.get('/protected').status_code == 200
    response = client.get('/protected', headers={
        'Authorization': 'Bearer invented', 'X-Forwarded-For': '1.2.3.4',
        'Forwarded': 'for=5.6.7.8', 'Origin': 'https://example.com',
    })
    assert response.status_code == 429
    assert 1 <= int(response.headers['Retry-After']) <= 60
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['Access-Control-Allow-Origin'] == 'https://example.com'
    assert response.headers['Access-Control-Expose-Headers'] == 'Retry-After'
    assert calls == [1]
    assert client.get('/health').status_code == 200
    assert client.get('/api/v1/health/ready').status_code == 429
    assert client.get('/unknown').status_code == 429
