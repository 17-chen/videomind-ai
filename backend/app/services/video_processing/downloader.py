from pathlib import Path
from typing import Any
from time import monotonic

from app.core.config import settings
from app.services.storage_quota import artifact_directory
from app.core.i18n import t
from app.core.errors import ApiError
from app.services.temporary_storage import STAGE_LIMIT_MESSAGE, check_stage_space, stage_limit_bytes
from app.services.video_processing.errors import VideoProcessingError
from app.services.video_processing.subtitles import SUBTITLE_LANGUAGES
from app.services.video_processing.types import DownloadedVideo
from app.services.videos import detect_video_source


VIDEO_EXTENSIONS = {".mp4", ".webm", ".mkv", ".mov", ".m4v", ".flv", ".avi", ".ts", ".3gp"}


def download_video(url: str, video_id: str) -> DownloadedVideo:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise VideoProcessingError(t("yt_dlp_missing")) from exc

    output_dir = artifact_directory("video")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(output_dir / f"{video_id}.%(ext)s")
    started = monotonic()
    guard_failure: ApiError | VideoProcessingError | None = None

    def check_progress(_event: dict) -> None:
        nonlocal guard_failure
        try:
            check_stage_space(output_dir)
            if monotonic() - started >= settings.video_download_timeout_seconds:
                raise VideoProcessingError("视频下载超时，请稍后重试")
        except (ApiError, VideoProcessingError) as exc:
            guard_failure = exc
            raise

    class LimitLogger:
        def debug(self, message):
            nonlocal guard_failure
            # HttpFD can reject Content-Length before hooks or filesize metadata exist.
            if 'File is larger than max-filesize' in message:
                guard_failure = ApiError(STAGE_LIMIT_MESSAGE, 413)

        def warning(self, message):
            pass

        def error(self, message):
            pass

    check_progress({})

    options: dict[str, Any] = {
        "outtmpl": output_template,
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": LimitLogger(),
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": list(SUBTITLE_LANGUAGES),
        "subtitlesformat": "vtt/srt/best",
        "max_filesize": stage_limit_bytes(),
        "progress_hooks": [check_progress],
        "postprocessor_hooks": [check_progress],
        "socket_timeout": 30,
        "retries": 3,
        "http_headers": {
            "User-Agent": settings.video_user_agent,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": _referer_for_url(url),
        },
    }
    if settings.video_cookie_file:
        cookie_file = Path(settings.video_cookie_file)
        if not cookie_file.is_file():
            raise VideoProcessingError(f"Cookie 文件不存在：{cookie_file}")
        options["cookiefile"] = str(cookie_file)
    if settings.video_http_proxy:
        options["proxy"] = settings.video_http_proxy

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            prepared_path = Path(ydl.prepare_filename(info))
            if _metadata_exceeds_limit(info):
                raise ApiError(STAGE_LIMIT_MESSAGE, 413)
        if guard_failure is not None:
            raise guard_failure
        check_progress({})
    except (ApiError, VideoProcessingError):
        raise
    except Exception as exc:
        if guard_failure is not None:
            raise guard_failure from exc
        message = str(exc)
        if detect_video_source(url) == "bilibili" and "HTTP Error 412" in message:
            raise VideoProcessingError(
                "Bilibili 拒绝了当前下载请求（HTTP 412）。请导出 Netscape 格式登录 Cookie，"
                "保存到 storage/cookies/bilibili.txt，并设置 VIDEO_COOKIE_FILE=/app/storage/cookies/bilibili.txt。"
            ) from exc
        raise VideoProcessingError(f"{t('video_download_failed')}: {message}") from exc

    file_path = _resolve_downloaded_file(prepared_path, output_dir, video_id)

    return DownloadedVideo(
        video_id=video_id,
        url=url,
        file_path=str(file_path),
        title=_string_or_none(info.get("title")),
        description=_string_or_none(info.get("description")),
        duration=_int_or_none(info.get("duration")),
        thumbnail=_string_or_none(info.get("thumbnail")),
        source=detect_video_source(url),
    )


def _metadata_exceeds_limit(info: dict) -> bool:
    # yt-dlp may skip an oversized known file before invoking any progress hook.
    candidates = [info, *(info.get("requested_downloads") or []), *(info.get("requested_formats") or [])]
    return any(isinstance(item.get("filesize"), int) and item["filesize"] > stage_limit_bytes() for item in candidates)


def _resolve_downloaded_file(prepared_path: Path, output_dir: Path, video_id: str) -> Path:
    candidates = [output_dir / f"{video_id}.mp4", prepared_path.with_suffix(".mp4"), prepared_path]
    candidates.extend(
        sorted(output_dir.glob(f"{video_id}.*"), key=lambda path: (path.suffix.lower() != ".mp4", path.name))
    )

    for candidate in candidates:
        if candidate.suffix.lower() in VIDEO_EXTENSIONS and candidate.is_file():
            return candidate

    raise VideoProcessingError(t("video_output_missing"))


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _referer_for_url(url: str) -> str:
    if detect_video_source(url) == "bilibili":
        return "https://www.bilibili.com/"
    if detect_video_source(url) == "douyin":
        return "https://www.douyin.com/"
    return url
