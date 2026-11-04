"""Private Supabase Storage REST transport; credentials never leave this client."""

from contextlib import contextmanager
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from tempfile import NamedTemporaryFile
import time
from urllib.parse import urlsplit

import httpx

from app.core.errors import ApiError
from app.core.logging import logger
from app.services.object_storage.spec import ArtifactSpec, BLOCK_SIZE, INTEGRITY_ERROR, UNAVAILABLE, open_regular_file
from app.services.temporary_storage import ensure_free_space, stage_limit_bytes


class SupabaseObjectStore:
    def __init__(self, project_url: str, service_key: str, bucket: str, *, transport=None, allow_insecure_loopback=False, transfer_seconds=300):
        try:
            parsed = urlsplit(project_url)
            loopback = allow_insecure_loopback and parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')
            if ((parsed.scheme != 'https' and not loopback) or not parsed.hostname or parsed.username or parsed.password
                    or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.port == 0
                    or any(char.isspace() for char in project_url)
                    or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,99}', bucket) or transfer_seconds <= 0):
                raise ValueError('Invalid storage configuration')
            if service_key.startswith('sb_secret_'):
                valid_key = bool(re.fullmatch(r'sb_secret_[A-Za-z0-9_-]{11,}', service_key))
                headers = {'apikey': service_key}
            else:
                parts = service_key.split('.')
                payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4))) if len(parts) == 3 else {}
                valid_key = isinstance(payload, dict) and payload.get('role') == 'service_role'
                headers = {'apikey': service_key, 'Authorization': f'Bearer {service_key}'}
            if not valid_key:
                raise ValueError('Server storage credential required')
        except (ValueError, TypeError, UnicodeError):
            raise ApiError(UNAVAILABLE, 503) from None
        self.bucket = bucket
        self._url = project_url.rstrip('/') + '/storage/v1'
        self.project_fingerprint = hashlib.sha256(project_url.rstrip('/').encode()).hexdigest()
        self._client = httpx.Client(headers=headers, transport=transport, trust_env=False, follow_redirects=False, timeout=httpx.Timeout(30, connect=10))
        self._transfer_seconds = transfer_seconds

    @classmethod
    def from_settings(cls):
        from app.core.config import settings
        return cls(settings.supabase_url, settings.supabase_storage_service_key, settings.supabase_storage_bucket)

    def close(self):
        self._client.close()

    @contextmanager
    def _request(self, method, path, **kwargs):
        try:
            with self._client.stream(method, self._url + path, **kwargs) as response:
                yield response
        except httpx.HTTPError as exc:
            logger.error('Object storage transport error type={}', type(exc).__name__)
            raise ApiError(UNAVAILABLE, 503) from None

    def _private_bucket(self):
        with self._request('GET', f'/bucket/{self.bucket}') as response:
            if response.status_code != 200:
                raise ApiError(UNAVAILABLE, 503)
            data = bytearray()
            for chunk in response.iter_bytes(BLOCK_SIZE):
                data.extend(chunk)
                if len(data) > BLOCK_SIZE:
                    raise ApiError(UNAVAILABLE, 503)
            try:
                metadata = json.loads(data)
                if metadata.get('id') != self.bucket or metadata.get('public') is not False:
                    raise ValueError('Private bucket required')
            except (ValueError, AttributeError):
                raise ApiError(UNAVAILABLE, 503) from None

    def _validate(self, spec: ArtifactSpec):
        if spec.bucket != self.bucket or spec.project_fingerprint != self.project_fingerprint:
            raise ApiError(UNAVAILABLE, 503)
        if spec.size_bytes > stage_limit_bytes():
            raise ApiError('本次处理的临时文件超过大小上限，请使用较小的视频', 413)
        self._private_bucket()

    def put(self, spec: ArtifactSpec, path: Path):
        self._validate(spec)
        deadline = time.monotonic() + self._transfer_seconds
        digest = hashlib.sha256()
        count = 0

        def chunks():
            nonlocal count
            with open_regular_file(path) as source:
                while data := source.read(BLOCK_SIZE):
                    count += len(data)
                    if count > spec.size_bytes or time.monotonic() > deadline:
                        raise ApiError(INTEGRITY_ERROR, 502)
                    digest.update(data)
                    yield data

        with self._request('POST', f'/object/{self.bucket}/{spec.object_key}', content=chunks(), headers={
            'Content-Type': 'application/octet-stream', 'Content-Length': str(spec.size_bytes), 'x-upsert': 'false',
        }) as response:
            if response.status_code not in (200, 201):
                raise ApiError(UNAVAILABLE, 503)
        if count != spec.size_bytes or digest.hexdigest() != spec.sha256:
            raise ApiError(INTEGRITY_ERROR, 502)

    def download(self, spec: ArtifactSpec, destination: Path):
        self._validate(spec)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink() or (destination.exists() and not stat.S_ISREG(destination.lstat().st_mode)):
            raise ApiError(INTEGRITY_ERROR, 409)
        ensure_free_space(destination.parent, incoming_bytes=spec.size_bytes)
        temporary = None
        count = 0
        digest = hashlib.sha256()
        deadline = time.monotonic() + self._transfer_seconds
        try:
            with self._request('GET', f'/object/authenticated/{self.bucket}/{spec.object_key}', headers={'Accept-Encoding': 'identity'}) as response:
                if response.status_code != 200:
                    raise ApiError(UNAVAILABLE, 503)
                if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                    raise ApiError(INTEGRITY_ERROR, 502)
                length = response.headers.get('Content-Length')
                if length is not None and length != str(spec.size_bytes):
                    raise ApiError(INTEGRITY_ERROR, 502)
                with NamedTemporaryFile(dir=destination.parent, prefix='.object-', delete=False) as output:
                    temporary = Path(output.name)
                    for data in response.iter_raw(BLOCK_SIZE):
                        count += len(data)
                        if count > spec.size_bytes or time.monotonic() > deadline:
                            raise ApiError(INTEGRITY_ERROR, 502)
                        ensure_free_space(destination.parent, incoming_bytes=len(data))
                        digest.update(data)
                        output.write(data)
                if count != spec.size_bytes or digest.hexdigest() != spec.sha256:
                    raise ApiError(INTEGRITY_ERROR, 502)
            os.replace(temporary, destination)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def delete(self, spec: ArtifactSpec):
        self._validate(spec)
        with self._request('DELETE', f'/object/{self.bucket}', json={'prefixes': [spec.object_key]}) as response:
            if response.status_code not in (200, 204, 404):
                raise ApiError(UNAVAILABLE, 503)
        # A successful remove response alone is not proof of disappearance.
        with self._request('GET', f'/object/authenticated/{self.bucket}/{spec.object_key}') as response:
            if response.status_code != 404:
                raise ApiError(UNAVAILABLE, 503)
