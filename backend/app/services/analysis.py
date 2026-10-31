from fastapi import status
from sqlalchemy.orm import Session

from app.agents.video_analysis_agent import analyze_video_transcript
from app.services.storage_quota import artifact_directory, generate_artifacts
from app.services.temporary_storage import ensure_free_space, write_bounded_text
from app.core.errors import ApiError
from app.core.i18n import t
from app.models.summary import Summary
from app.models.video import Video


def analyze_video(db: Session, video: Video) -> Summary:
    if video.transcript is None or not video.transcript.content.strip():
        raise ApiError(t("transcript_required"), status_code=status.HTTP_400_BAD_REQUEST)

    if video.summary is None or not video.summary.note_is_manual:
        output_dir = artifact_directory("note")
        output_dir.mkdir(parents=True, exist_ok=True)
        ensure_free_space(output_dir)

    analysis, markdown_note = analyze_video_transcript(
        transcript=video.transcript.content,
        user=video.user,
        video_title=video.title,
    )
    if video.summary is None or not video.summary.note_is_manual:
        generate_artifacts(db, video, "note", lambda: _persist_markdown_note(video.id, markdown_note))

    summary = video.summary
    if summary is None:
        summary = Summary(video_id=video.id, summary=analysis.summary)
        video.summary = summary

    summary.title = analysis.title
    summary.summary = analysis.summary
    summary.key_points = analysis.key_points
    summary.keywords = analysis.keywords
    summary.category = analysis.category
    summary.important_quotes = analysis.important_quotes
    summary.timeline = [item.model_dump() for item in analysis.timeline]
    summary.action_items = analysis.action_items
    summary.difficulty_level = analysis.difficulty_level
    summary.target_audience = analysis.target_audience
    summary.analysis_json = analysis.model_dump()
    if not summary.note_is_manual:
        summary.markdown_note = markdown_note

    db.add(summary)
    db.commit()
    db.refresh(summary)
    return summary


def _persist_markdown_note(video_id: str, markdown_note: str) -> None:
    output_dir = artifact_directory("note")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_id}.md"
    write_bounded_text(output_path, markdown_note)
