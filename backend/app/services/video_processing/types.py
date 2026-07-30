from dataclasses import dataclass


@dataclass(frozen=True)
class DownloadedVideo:
    video_id: str
    url: str
    file_path: str
    title: str | None = None
    description: str | None = None
    duration: int | None = None
    thumbnail: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class ExtractedAudio:
    video_id: str
    file_path: str


@dataclass(frozen=True)
class TranscriptResult:
    video_id: str
    content: str
    source: str


@dataclass(frozen=True)
class SubtitleResult:
    video_id: str
    content: str
    file_path: str
