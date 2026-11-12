import os
import shutil
import subprocess
import sys
from pathlib import Path
from time import monotonic

from app.core.config import settings
from app.services.storage_quota import artifact_directory
from app.core.i18n import t
from app.core.errors import ApiError
from app.services.temporary_storage import STAGE_LIMIT_MESSAGE, ensure_free_space, stage_limit_bytes
from app.services.video_processing.errors import VideoProcessingError
from app.services.video_processing.types import ExtractedAudio


def _run_audio_command(command: list[str], output_dir: Path) -> int:
    timeout = settings.audio_extraction_timeout_seconds
    # No pipes: raw tool output is neither shown nor accumulated in memory.
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = monotonic() + timeout
    try:
        while process.poll() is None:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                process.wait(timeout=min(0.5, remaining))
            except subprocess.TimeoutExpired:
                ensure_free_space(output_dir)
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command)
        return process.returncode
    finally:
        # Includes low space, failed space probes, timeout and caller errors.
        # Reap before staging cleanup so no child can keep writing into it.
        if process.poll() is None:
            process.kill()
        process.wait()


def extract_audio(video_path: str, video_id: str) -> ExtractedAudio:
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise VideoProcessingError(t("ffmpeg_missing"))

    input_path = Path(video_path)
    if not input_path.exists():
        raise VideoProcessingError(f"{t('video_file_missing')}: {video_path}")

    output_dir = artifact_directory("audio")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_id}.mp3"

    ensure_free_space(output_dir)
    limit = stage_limit_bytes()
    command = [
        sys.executable, "-m", "app.services.video_processing.limited_exec", str(limit), str(os.getpid()),
        ffmpeg_path,
        "-loglevel", "error",
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
        returncode = _run_audio_command(command, output_dir)
    except subprocess.TimeoutExpired as exc:
        raise VideoProcessingError(t("audio_extraction_timeout")) from exc
    except subprocess.CalledProcessError as exc:
        if output_path.exists() and output_path.stat().st_size >= limit:
            raise ApiError(STAGE_LIMIT_MESSAGE, 413) from exc
        raise VideoProcessingError(t("audio_extraction_failed")) from exc

    if returncode != 0 or not output_path.exists():
        raise VideoProcessingError(t("audio_output_missing"))

    if output_path.stat().st_size >= limit:
        raise ApiError(STAGE_LIMIT_MESSAGE, 413)
    ensure_free_space(output_dir)
    return ExtractedAudio(video_id=video_id, file_path=str(output_path))
