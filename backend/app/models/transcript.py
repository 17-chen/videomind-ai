from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.video import Video


class Transcript(IdMixin, TimestampMixin, Base):
    __tablename__ = "transcripts"

    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), unique=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    video: Mapped["Video"] = relationship(back_populates="transcript")
