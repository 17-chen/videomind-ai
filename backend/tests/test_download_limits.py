from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.core.errors import ApiError
from app.services.video_processing import downloader
from app.services.video_processing.errors import VideoProcessingError


@pytest.fixture
def fake_downloader(monkeypatch):
    monkeypatch.setattr(settings, 'max_media_stage_mb', 1)
    Path(settings.video_storage_dir).mkdir()

    def install(extract):
        class FakeYDL:
            def __init__(self, options):
                self.options = options
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def extract_info(self, url, download):
                return extract(self.options)
            def prepare_filename(self, info):
                return str(Path(settings.video_storage_dir) / 'synthetic.mp4')
        monkeypatch.setitem(sys.modules, 'yt_dlp', SimpleNamespace(YoutubeDL=FakeYDL))
    return install


def test_download_progress_aborts_on_aggregate_video_and_audio_bytes(fake_downloader):
    def extract(options):
        assert options['max_filesize'] == 1024 * 1024
        root = Path(settings.video_storage_dir)
        (root / 'synthetic.fvideo.mp4').write_bytes(b'x' * (700 * 1024))
        (root / 'synthetic.faudio.m4a').write_bytes(b'x' * (400 * 1024))
        # Real yt-dlp may wrap hook exceptions; preserve the original quota response.
        try:
            options['progress_hooks'][0]({'status': 'downloading'})
        except ApiError as exc:
            raise RuntimeError('wrapper must not erase the quota response') from exc
    fake_downloader(extract)
    with pytest.raises(ApiError) as exc:
        downloader.download_video('https://example.com/synthetic.mp4', 'synthetic')
    assert exc.value.status_code == 413


def test_known_oversized_metadata_is_not_reported_as_missing_output(fake_downloader):
    fake_downloader(lambda _: {'filesize': 1024 * 1024 + 1})
    with pytest.raises(ApiError) as exc:
        downloader.download_video('https://example.com/synthetic.mp4', 'synthetic')
    assert exc.value.status_code == 413


def test_download_budget_is_checked_during_progress(fake_downloader, monkeypatch):
    monkeypatch.setattr(settings, 'video_download_timeout_seconds', 10)
    ticks = iter([0, 0, 11])
    monkeypatch.setattr(downloader, 'monotonic', lambda: next(ticks))

    def extract(options):
        options['progress_hooks'][0]({'status': 'downloading'})
    fake_downloader(extract)
    with pytest.raises(VideoProcessingError, match='下载超时'):
        downloader.download_video('https://example.com/synthetic.mp4', 'synthetic')


def test_postprocessing_hook_checks_merge_output(fake_downloader):
    def extract(options):
        root = Path(settings.video_storage_dir)
        (root / 'synthetic.mp4').write_bytes(b'x' * (1024 * 1024 + 1))
        options['postprocessor_hooks'][0]({'status': 'finished'})
    fake_downloader(extract)
    with pytest.raises(ApiError) as exc:
        downloader.download_video('https://example.com/synthetic.mp4', 'synthetic')
    assert exc.value.status_code == 413


def test_fragment_removed_during_size_scan_does_not_fail_download(fake_downloader, monkeypatch):
    from app.services.temporary_storage import check_stage_space

    root = Path(settings.video_storage_dir)
    fragment = root / 'synthetic.part-Frag1'
    fragment.write_bytes(b'fragment')
    (root / 'synthetic.mp4.part').write_bytes(b'current')
    original_lstat = Path.lstat

    def rename_between_scan_and_stat(path, *args, **kwargs):
        if path == fragment and fragment.exists():
            fragment.unlink()
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'lstat', rename_between_scan_and_stat)
    check_stage_space(root)
    assert not fragment.exists()
