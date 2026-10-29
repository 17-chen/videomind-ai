import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def isolate_business_storage(monkeypatch, tmp_path):
    """Tests must never depend on or write the running application's files."""
    for kind in ('video', 'audio', 'transcript', 'note'):
        monkeypatch.setattr(settings, f'{kind}_storage_dir', str(tmp_path / kind))
