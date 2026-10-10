from pathlib import Path

import pytest

from app.services.video_processing.downloader import _resolve_downloaded_file
from app.services.video_processing.errors import VideoProcessingError


def test_resolver_never_returns_subtitle_as_video(tmp_path: Path) -> None:
    (tmp_path / "video.en.vtt").write_text("WEBVTT\n", encoding="utf-8")

    with pytest.raises(VideoProcessingError, match="没有找到输出文件"):
        _resolve_downloaded_file(tmp_path / "video.webm", tmp_path, "video")


def test_resolver_prefers_merged_mp4(tmp_path: Path) -> None:
    original = tmp_path / "video.webm"
    merged = tmp_path / "video.mp4"
    original.write_bytes(b"original")
    merged.write_bytes(b"merged")

    assert _resolve_downloaded_file(original, tmp_path, "video") == merged


def test_resolver_accepts_original_video_when_no_merge_exists(tmp_path: Path) -> None:
    original = tmp_path / "video.webm"
    original.write_bytes(b"original")

    assert _resolve_downloaded_file(original, tmp_path, "video") == original
