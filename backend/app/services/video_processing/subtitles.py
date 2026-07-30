import re
from pathlib import Path

from app.core.config import settings
from app.services.video_processing.types import SubtitleResult


TIMESTAMP_PATTERN = re.compile(r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}[,.]\d{3}")
WEBVTT_PATTERN = re.compile(r"^WEBVTT|^Kind:|^Language:", re.IGNORECASE)
TAG_PATTERN = re.compile(r"<[^>]+>")


def find_downloaded_subtitles(video_id: str) -> SubtitleResult | None:
    video_dir = Path(settings.video_storage_dir)
    if not video_dir.exists():
        return None

    subtitle_files = [
        path
        for path in video_dir.glob(f"{video_id}.*")
        if path.suffix.lower() in {".vtt", ".srt"}
    ]

    for subtitle_file in subtitle_files:
        content = _parse_subtitle_text(subtitle_file)
        if content:
            _persist_transcript_file(video_id=video_id, content=content)
            return SubtitleResult(video_id=video_id, content=content, file_path=str(subtitle_file))

    return None


def _parse_subtitle_text(path: Path) -> str:
    raw_text = path.read_text(encoding="utf-8", errors="ignore")
    lines: list[str] = []
    seen: set[str] = set()

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.isdigit() or TIMESTAMP_PATTERN.search(line) or WEBVTT_PATTERN.search(line):
            continue

        cleaned = TAG_PATTERN.sub("", line).strip()
        if not cleaned or cleaned in seen:
            continue

        seen.add(cleaned)
        lines.append(cleaned)

    return "\n".join(lines).strip()


def _persist_transcript_file(video_id: str, content: str) -> None:
    output_dir = Path(settings.transcript_storage_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_id}.txt"
    output_path.write_text(content, encoding="utf-8")
