import sys
from types import ModuleType, SimpleNamespace

from app.core.config import settings
from app.services import embeddings
from app.services.vector_store import ChromaVectorStore
from app.services.video_processing import transcriber


def test_local_whisper_transcribes_without_api_key(monkeypatch, tmp_path):
    calls = []

    class FakeWhisperModel:
        def __init__(self, name, device, compute_type):
            calls.append((name, device, compute_type))

        def transcribe(self, audio_path, beam_size):
            calls.append((audio_path, beam_size))
            return iter([SimpleNamespace(text="第一句"), SimpleNamespace(text="第二句")]), None

    fake_module = ModuleType("faster_whisper")
    fake_module.WhisperModel = FakeWhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)
    monkeypatch.setattr(settings, "asr_provider", "faster_whisper")
    monkeypatch.setattr(settings, "transcript_storage_dir", str(tmp_path))
    transcriber._local_model.cache_clear()
    audio = tmp_path / "sample.mp3"
    audio.write_bytes(b"sample")

    result = transcriber.transcribe_audio(str(audio), "video-1")

    assert result.content == "第一句 第二句"
    assert result.source == "faster_whisper"
    assert (tmp_path / "video-1.txt").read_text(encoding="utf-8") == result.content
    assert calls == [("base", "cpu", "int8"), (str(audio), 5)]
    transcriber._local_model.cache_clear()


def test_bge_query_uses_instruction_and_isolated_collection(monkeypatch):
    inputs = []

    class FakeModel:
        def __init__(self, name):
            inputs.append(name)

        def encode(self, text, normalize_embeddings):
            inputs.append((text, normalize_embeddings))
            return [0.6, 0.8]

    fake_module = ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = FakeModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    monkeypatch.setattr(settings, "embedding_provider", "bge_zh")
    monkeypatch.setattr(settings, "embedding_model", "BAAI/bge-small-zh-v1.5")
    embeddings._load_sentence_model.cache_clear()

    service = embeddings.current_embedding_service()
    assert service.embed_text("视频正文") == [0.6, 0.8]
    assert service.embed_query("数学") == [0.6, 0.8]
    assert inputs == [
        "BAAI/bge-small-zh-v1.5",
        ("视频正文", True),
        ("为这个句子生成表示以用于检索相关文章：数学", True),
    ]
    assert ChromaVectorStore._collection_name() != settings.chroma_collection
    embeddings._load_sentence_model.cache_clear()
