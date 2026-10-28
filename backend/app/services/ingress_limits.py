"""Bounded, process-local admission control before authentication or body reads."""

from collections import OrderedDict
from math import ceil
from threading import Lock
from time import monotonic

from starlette.responses import JSONResponse

from app.core.i18n import t


class IngressLimiter:
    def __init__(self, per_peer: int, total: int, max_peers: int = 4096):
        self.per_peer = per_peer
        self.total = total
        self.max_peers = max_peers
        self.peers: OrderedDict[str, tuple[float, int]] = OrderedDict()
        self.window_start: float | None = None
        self.count = 0
        self.lock = Lock()

    def consume(self, peer: str, *, now: float | None = None) -> int:
        """Return zero when admitted, otherwise the seconds until retry."""
        now = monotonic() if now is None else now
        with self.lock:
            if self.window_start is None or now >= self.window_start + 60:
                self.window_start, self.count = now, 0
            while self.peers and next(iter(self.peers.values()))[0] + 60 <= now:
                self.peers.popitem(last=False)
            if self.count >= self.total:
                return max(1, ceil(self.window_start + 60 - now))
            # Rejected per-peer requests also consume the shared budget.
            self.count += 1
            window = self.peers.get(peer)
            if window is None:
                if len(self.peers) >= self.max_peers:
                    return max(1, ceil(next(iter(self.peers.values()))[0] + 60 - now))
                self.peers[peer] = (now, 1)
                return 0
            start, count = window
            if count >= self.per_peer:
                return max(1, ceil(start + 60 - now))
            self.peers[peer] = (start, count + 1)
            return 0


class IngressLimitMiddleware:
    def __init__(self, app, limiter: IngressLimiter):
        self.app = app
        self.limiter = limiter

    async def __call__(self, scope, receive, send):
        # Only the cheap liveness endpoint is exempt; readiness touches services.
        if scope['type'] != 'http' or (scope['method'] == 'GET' and scope['path'] == '/health'):
            await self.app(scope, receive, send)
            return
        client = scope.get('client')
        retry_after = self.limiter.consume(client[0] if client else '<unknown>')
        if retry_after:
            response = JSONResponse(
                status_code=429,
                content={'detail': t('ingress_limit_reached')},
                headers={'Retry-After': str(retry_after), 'Cache-Control': 'no-store'},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
