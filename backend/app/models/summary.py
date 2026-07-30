from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import IdMixin, TimestampMixin


class Summary(IdMixin, TimestampMixin, Base):
    __tablename__ = "summaries"

    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_points: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    category: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    important_quotes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    timeline: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    action_items: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    difficulty_level: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String(255), nullable=True)
    analysis_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    markdown_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    video: Mapped["Video"] = relationship(back_populates="summary")
