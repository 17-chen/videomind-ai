"""Opaque artifact identities, never a provider URL or a portable local path."""

from uuid import UUID

from app.core.errors import ApiError
from app.services.object_storage.spec import UNAVAILABLE

PREFIX = 'object://'


def artifact_reference(artifact_id: str) -> str:
    if str(UUID(artifact_id)) != artifact_id:
        raise ValueError('Canonical artifact identifier required')
    return PREFIX + artifact_id


def reference_id(value: str | None) -> str:
    try:
        if not value or not value.startswith(PREFIX):
            raise ValueError('Object reference required')
        identifier = value[len(PREFIX):]
        if str(UUID(identifier)) != identifier:
            raise ValueError('Canonical artifact identifier required')
        return identifier
    except ValueError:
        raise ApiError(UNAVAILABLE, 503) from None


def require_object_store(video, object_store):
    if object_store is None and any(value and value.startswith(PREFIX) for value in (video.media_path, video.audio_path)):
        raise ApiError(UNAVAILABLE, 503)
