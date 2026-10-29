from pathlib import Path
from functools import lru_cache

from openai import OpenAI

from app.core.config import settings
from app.services.storage_quota import artifact_directory
from app.core.i18n import t
from app.services.video_processing.errors import VideoProcessingError
from app.services.video_processing.types import TranscriptResult


def transcribe_audio(audio_path: str, video_id: str, api_key: str | None = None) -> TranscriptResult:
    if settings.asr_provider == "faster_whisper":
        return _transcribe_locally(audio_path, video_id)
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


def ensure_local_asr_available() -> None:
    try:
        import faster_whisper  # noqa: F401
    except ImportError as exc:
        raise VideoProcessingError("本地转写组件未安装，请安装 backend/requirements-local-ai.txt") from exc


@lru_cache(maxsize=2)
def _local_model(model_name: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    return WhisperModel(model_name, device=device, compute_type=compute_type)


def _transcribe_locally(audio_path: str, video_id: str) -> TranscriptResult:
    ensure_local_asr_available()
    input_path = Path(audio_path)
    if not input_path.is_file():
        raise VideoProcessingError(f"{t('audio_file_missing')}: {audio_path}")
    try:
        model = _local_model(
            settings.local_whisper_model,
            settings.local_whisper_device,
            settings.local_whisper_compute_type,
        )
        segments, _ = model.transcribe(str(input_path), beam_size=5)
        content = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
    except Exception as exc:
        raise VideoProcessingError(f"本地 Whisper 转写失败: {type(exc).__name__}") from exc
    if not content:
        raise VideoProcessingError(t("whisper_empty"))
    _persist_transcript_file(video_id=video_id, content=content)
    return TranscriptResult(video_id=video_id, content=content, source="faster_whisper")


def _persist_transcript_file(video_id: str, content: str) -> None:
    output_dir = artifact_directory("transcript")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_id}.txt"
    output_path.write_text(content, encoding="utf-8")
