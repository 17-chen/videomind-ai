from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.i18n import t
from app.services.video_processing.errors import VideoProcessingError
from app.services.video_processing.types import DownloadedVideo
from app.services.videos import detect_video_source


def download_video(url: str, video_id: str) -> DownloadedVideo:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise VideoProcessingError(t("yt_dlp_missing")) from exc

    output_dir = Path(settings.video_storage_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(output_dir / f"{video_id}.%(ext)s")

    options: dict[str, Any] = {
        "outtmpl": output_template,
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["zh-Hans", "zh-Hant", "zh-CN", "zh-TW", "zh", "en"],
        "subtitlesformat": "vtt/srt/best",
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
    except Exception as exc:
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


def _resolve_downloaded_file(prepared_path: Path, output_dir: Path, video_id: str) -> Path:
    candidates = [prepared_path, prepared_path.with_suffix(".mp4")]
    candidates.extend(output_dir.glob(f"{video_id}.*"))

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
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
