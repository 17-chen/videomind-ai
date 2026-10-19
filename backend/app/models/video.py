from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.embedding import Embedding
    from app.models.summary import Summary
    from app.models.transcript import Transcript
    from app.models.user import User


class VideoStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    PROCESSING = "processing"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    FAILED = "failed"


class Video(IdMixin, TimestampMixin, Base):
    __tablename__ = "videos"
    __table_args__ = (UniqueConstraint("user_id", "upload_sha256", name="uq_videos_user_upload_sha256"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumbnail: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=VideoStatus.CREATED.value, index=True, nullable=False)
    source: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    media_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    upload_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="videos")
    transcript: Mapped["Transcript | None"] = relationship(back_populates="video", cascade="all, delete-orphan", uselist=False)
    summary: Mapped["Summary | None"] = relationship(back_populates="video", cascade="all, delete-orphan", uselist=False)
    embedding: Mapped["Embedding | None"] = relationship(back_populates="video", cascade="all, delete-orphan", uselist=False)
