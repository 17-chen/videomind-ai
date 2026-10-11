from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.video import Video


class Embedding(IdMixin, TimestampMixin, Base):
    __tablename__ = "embeddings"

    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), unique=True, index=True)
    vector_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    video: Mapped["Video"] = relationship(back_populates="embedding")
