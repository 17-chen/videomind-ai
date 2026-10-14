from app.services.video_processing.subtitles import _parse_subtitle_text


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
