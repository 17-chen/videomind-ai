import shutil
import subprocess
from pathlib import Path

from app.core.config import settings
from app.core.i18n import t
from app.services.video_processing.errors import VideoProcessingError
from app.services.video_processing.types import ExtractedAudio


def extract_audio(video_path: str, video_id: str) -> ExtractedAudio:
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise VideoProcessingError(t("ffmpeg_missing"))

    input_path = Path(video_path)
    if not input_path.exists():
        raise VideoProcessingError(f"{t('video_file_missing')}: {video_path}")

    output_dir = Path(settings.audio_storage_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_id}.mp3"

    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "64k",
        str(output_path),
    ]

    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=settings.audio_extraction_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise VideoProcessingError(t("audio_extraction_timeout")) from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or "ffmpeg failed"
        raise VideoProcessingError(f"{t('audio_extraction_failed')}: {message}") from exc

    if completed.returncode != 0 or not output_path.exists():
        raise VideoProcessingError(t("audio_output_missing"))

    return ExtractedAudio(video_id=video_id, file_path=str(output_path))
