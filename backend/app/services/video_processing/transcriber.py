from pathlib import Path

from openai import OpenAI

from app.core.config import settings
from app.core.i18n import t
from app.services.video_processing.errors import VideoProcessingError
from app.services.video_processing.types import TranscriptResult


def transcribe_audio(audio_path: str, video_id: str, api_key: str | None = None) -> TranscriptResult:
    if settings.asr_provider == "disabled" and not api_key:
        raise VideoProcessingError(t("asr_disabled"))
    if settings.asr_provider not in ("openai", "disabled"):
        raise VideoProcessingError(f"暂不支持的音频转写服务: {settings.asr_provider}")
    if not api_key:
        raise VideoProcessingError(t("openai_key_required"))

    input_path = Path(audio_path)
    if not input_path.exists():
        raise VideoProcessingError(f"{t('audio_file_missing')}: {audio_path}")

    client = OpenAI(api_key=api_key)

    try:
        with input_path.open("rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model=settings.openai_whisper_model,
                file=audio_file,
                response_format="text",
            )
    except Exception as exc:
        raise VideoProcessingError(f"{t('whisper_failed')}: {exc}") from exc

    content = str(transcript).strip()
    if not content:
        raise VideoProcessingError(t("whisper_empty"))

    _persist_transcript_file(video_id=video_id, content=content)
    return TranscriptResult(video_id=video_id, content=content, source="whisper")


def _persist_transcript_file(video_id: str, content: str) -> None:
    output_dir = Path(settings.transcript_storage_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_id}.txt"
    output_path.write_text(content, encoding="utf-8")
