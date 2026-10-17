from app.core.config import settings
from app.services.video_processing.subtitles import _parse_subtitle_text, find_downloaded_subtitles


def test_parse_webvtt_omits_timestamps_without_hours(tmp_path):
    subtitle = tmp_path / "video.en.vtt"
    subtitle.write_text(
        "WEBVTT\n\n"
        "00:12.345 --> 00:15.678 align:start position:0%\n"
        "Hello world\n\n"
        "01:02:03.456 --> 01:02:05.789\n"
        "A later caption\n",
        encoding="utf-8",
    )

    assert _parse_subtitle_text(subtitle) == "Hello world\nA later caption"


def test_prefers_chinese_subtitles_and_falls_back_from_empty_file(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "video_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "transcript_storage_dir", str(tmp_path / "transcripts"))
    (tmp_path / "video.en.vtt").write_text("WEBVTT\n\nEnglish caption\n", encoding="utf-8")
    chinese = tmp_path / "video.zh-Hans.vtt"
    chinese.write_text("WEBVTT\n\n中文字幕\n", encoding="utf-8")

    result = find_downloaded_subtitles("video")
    assert result is not None
    assert result.content == "中文字幕"
    assert result.file_path == str(chinese)
    assert (tmp_path / "transcripts/video.txt").read_text(encoding="utf-8") == "中文字幕"

    chinese.write_text("WEBVTT\n", encoding="utf-8")
    result = find_downloaded_subtitles("video")
    assert result is not None
    assert result.content == "English caption"
