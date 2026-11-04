"""Opt-in object ledger, deliberately outside automatic business create_all."""

from sqlalchemy import BigInteger, CheckConstraint, Index, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.models.mixins import IdMixin, TimestampMixin


class ArtifactBase(DeclarativeBase):
    pass


class StoredArtifact(IdMixin, TimestampMixin, ArtifactBase):
    __tablename__ = 'vm_storage_objects'
    __table_args__ = (
        CheckConstraint("state IN ('pending','ready','retired','deleted')", name='ck_storage_state'),
        CheckConstraint("kind IN ('video','audio','transcript','note')", name='ck_storage_kind'),
        CheckConstraint('size_bytes >= 0', name='ck_storage_size'),
        Index('ix_storage_owner_state', 'user_id', 'state'),
        Index('uq_storage_ready', 'user_id', 'video_id', 'kind', 'filename', unique=True,
              postgresql_where=text("state='ready'"), sqlite_where=text("state='ready'")),
    )
    # No cascading FK: deleting a video must not erase the remote cleanup record.
    # Repository methods independently verify current Video ownership before I/O.
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    video_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    filename: Mapped[str] = mapped_column(String(180), nullable=False)
    bucket: Mapped[str] = mapped_column(String(100), nullable=False)
    project_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default='pending')
