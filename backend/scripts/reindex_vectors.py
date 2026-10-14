"""Rebuild the active embedding collection from videos stored in PostgreSQL."""

import argparse
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database.session import SessionLocal
from app.models.video import Video
from app.services.rag import index_video

BATCH_SIZE = 100


@dataclass
class ReindexResult:
    scanned: int = 0
    eligible: int = 0
    indexed: int = 0
    skipped: int = 0
    failed_video_ids: list[str] = field(default_factory=list)


def reindex_videos(
    db: Session,
    *,
    user_id: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    indexer: Callable[[Session, Video], object] = index_video,
) -> ReindexResult:
    """Scan in stable ID batches and keep going when one video cannot be indexed."""
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")

    result = ReindexResult()
    last_id: str | None = None
    while limit is None or result.scanned < limit:
        batch_limit = min(BATCH_SIZE, limit - result.scanned) if limit else BATCH_SIZE
        query = select(Video.id).order_by(Video.id).limit(batch_limit)
        if last_id is not None:
            query = query.where(Video.id > last_id)
        if user_id is not None:
            query = query.where(Video.user_id == user_id)
        video_ids = list(db.scalars(query))
        if not video_ids:
            break

        for video_id in video_ids:
            last_id = video_id
            video = db.scalar(
                select(Video)
                .where(Video.id == video_id)
                .options(joinedload(Video.summary), joinedload(Video.transcript))
            )
            if video is None:
                continue
            result.scanned += 1
            if not ((video.transcript and video.transcript.content) or video.summary):
                result.skipped += 1
                continue
            result.eligible += 1
            if dry_run:
                continue
            try:
                indexer(db, video)
            except Exception:
                db.rollback()
                result.failed_video_ids.append(video_id)
            else:
                result.indexed += 1
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", help="Only reindex videos owned by this user ID")
    parser.add_argument("--limit", type=int, help="Maximum number of videos to scan")
    parser.add_argument("--dry-run", action="store_true", help="Count eligible videos without writing vectors")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")

    with SessionLocal() as db:
        result = reindex_videos(db, user_id=args.user_id, limit=args.limit, dry_run=args.dry_run)

    action = "Would reindex" if args.dry_run else "Reindexed"
    print(
        f"{action} {result.eligible if args.dry_run else result.indexed} videos "
        f"(scanned={result.scanned}, skipped={result.skipped}, failed={len(result.failed_video_ids)})"
    )
    if result.failed_video_ids:
        print("Failed video IDs: " + ", ".join(result.failed_video_ids))
    return 1 if result.failed_video_ids else 0


if __name__ == "__main__":
    raise SystemExit(main())
