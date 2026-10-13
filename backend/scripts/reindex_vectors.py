"""Rebuild the selected embedding collection from videos already stored in PostgreSQL."""

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database.session import SessionLocal
from app.models.video import Video
from app.services.rag import index_video


def main() -> None:
    with SessionLocal() as db:
        video_ids = list(db.scalars(select(Video.id)))
        completed = 0
        for video_id in video_ids:
            video = db.scalar(
                select(Video)
                .where(Video.id == video_id)
                .options(joinedload(Video.summary), joinedload(Video.transcript))
            )
            if video and ((video.transcript and video.transcript.content) or video.summary):
                index_video(db, video)
                completed += 1
    print(f"Reindexed {completed} videos")


if __name__ == "__main__":
    main()
