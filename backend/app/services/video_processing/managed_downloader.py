"""Supervise yt-dlp and its ordinary subprocess group outside the Worker."""

from dataclasses import asdict
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from tempfile import TemporaryFile
from time import monotonic, sleep

from app.core.config import settings
from app.core.errors import ApiError
from app.core.i18n import t
from app.services.storage_quota import artifact_directory
from app.services.temporary_storage import check_stage_space
from app.services.video_processing.errors import VideoProcessingError
from app.services.video_processing.types import DownloadedVideo


MAX_INPUT_BYTES = 262144
MAX_RESULT_BYTES = 1048576
DOWNLOAD_SETTINGS = (
    'video_user_agent', 'video_cookie_file', 'video_http_proxy',
    'video_download_timeout_seconds', 'max_media_stage_mb', 'min_media_free_space_mb',
)


def download_video(url: str, video_id: str) -> DownloadedVideo:
    if not all(hasattr(os, name) for name in ('waitid', 'WNOWAIT', 'pread', 'killpg')):
        raise VideoProcessingError('下载执行环境不支持进程组保护，请使用 Linux 后端')
    output_dir = artifact_directory('video')
    output_dir.mkdir(parents=True, exist_ok=True)
    check_stage_space(output_dir)
    configuration = {name: getattr(settings, name) for name in DOWNLOAD_SETTINGS}
    configuration['video_storage_dir'] = str(output_dir)
    request = json.dumps({'url': url, 'video_id': video_id, 'settings': configuration}).encode()
    if len(request) > MAX_INPUT_BYTES:
        raise VideoProcessingError(t('video_download_failed'))

    # Anonymous private files: control parameters are not placed in this
    # command's argv/logs or an unbounded stdout/stderr capture. Third-party
    # external downloaders retain their own argument handling.
    with TemporaryFile() as incoming, TemporaryFile() as outgoing:
        incoming.write(request)
        incoming.seek(0)
        deadline = monotonic() + settings.video_download_timeout_seconds
        process = subprocess.Popen(
            [sys.executable, '-m', 'app.services.video_processing.download_runner',
             str(os.getpid()), str(outgoing.fileno())],
            stdin=incoming, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            pass_fds=(outgoing.fileno(),), start_new_session=True,
        )
        response = None
        try:
            while True:
                check_stage_space(output_dir)
                if monotonic() >= deadline:
                    raise VideoProcessingError('视频下载超时，请稍后重试')
                raw = os.pread(outgoing.fileno(), MAX_RESULT_BYTES + 2, 0)
                if len(raw) > MAX_RESULT_BYTES + 1:
                    raise VideoProcessingError(t('video_download_failed'))
                if raw.endswith(b'\n'):
                    try:
                        response = json.loads(raw)
                    except (ValueError, UnicodeError):
                        raise VideoProcessingError(t('video_download_failed')) from None
                    break
                # Do not reap yet: retaining the leader PID prevents accidental
                # signalling of a reused process-group ID in the finally block.
                if os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None:
                    break
                sleep(0.25)
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    return _result(response, output_dir, video_id, url)


def _result(response, directory, video_id, url):
    if isinstance(response, dict):
        if (response.get('kind') == 'api_error' and response.get('status') in (409, 413, 507)
                and isinstance(response.get('message'), str)):
            raise ApiError(response['message'], response['status'])
        if response.get('kind') == 'processing_error' and isinstance(response.get('message'), str):
            raise VideoProcessingError(response['message'])
        if response.get('kind') == 'success':
            try:
                result = DownloadedVideo(**response['result'])
                path = Path(result.file_path)
                if (result.video_id == video_id and result.url == url and
                        path.parent.resolve() == directory.resolve() and
                        path.name.startswith(f'{video_id}.') and path.is_file() and not path.is_symlink()):
                    return result
            except (KeyError, TypeError, ValueError, OSError):
                pass
    raise VideoProcessingError(t('video_download_failed'))


def encode_result(result):
    """Keep the protocol small; reject oversized metadata rather than truncate."""
    data = json.dumps({'kind': 'success', 'result': asdict(result)}).encode()
    if len(data) > MAX_RESULT_BYTES:
        raise VideoProcessingError(t('video_download_failed'))
    return data
