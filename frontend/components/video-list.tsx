import Link from "next/link";
import { ArrowUpRight, Clock, ExternalLink, Play } from "lucide-react";
import type { Video } from "@/lib/types";
import { Badge, EmptyState, Panel } from "@/components/ui";
import { formatDate, sourceLabel, statusLabel } from "@/lib/utils";

export function VideoList({ videos }: { videos: Video[] }) {
  if (!videos.length) {
    return <EmptyState title="还没有视频" description="先添加一个视频链接，VideoMind AI 会把它变成可整理、可检索的知识资产。" />;
  }

  return (
    <div className="grid gap-4">
      {videos.map((video) => (
        <Panel key={video.id} className="group overflow-hidden p-5">
          <div className="grid gap-5 md:grid-cols-[156px_1fr_auto] md:items-center">
            <Link href={`/videos/${video.id}`} className="relative block aspect-video overflow-hidden rounded-[22px] bg-muted">
              {video.thumbnail ? (
                <img src={video.thumbnail} alt="" className="h-full w-full object-cover transition duration-500 group-hover:scale-105" />
              ) : (
                <div className="ai-constellation flex h-full w-full items-center justify-center">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-foreground text-primary-foreground">
                    <Play size={17} className="fill-current" />
                  </div>
                </div>
              )}
            </Link>

            <div className="min-w-0 space-y-3">
              <Link href={`/videos/${video.id}`} className="block text-2xl font-black leading-tight hover:text-accent">
                {video.summary?.title ?? video.title ?? "Untitled Memory"}
              </Link>
              <p className="line-clamp-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                {video.summary?.summary ?? video.description ?? video.url}
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <Badge className="bg-white">{sourceLabel(video.source)}</Badge>
                <Badge className="bg-white">{statusLabel(video.status)}</Badge>
                {video.summary?.category ? <Badge className="border-accent/30 bg-accent/10 text-foreground">{video.summary.category}</Badge> : null}
                <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                  <Clock size={13} />
                  {formatDate(video.created_at)}
                </span>
                {video.tags.slice(0, 3).map((tag) => (
                  <span key={tag} className="text-xs text-muted-foreground">
                    #{tag}
                  </span>
                ))}
              </div>
            </div>

            <a
              href={video.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-12 w-fit shrink-0 items-center justify-center gap-2 rounded-full border border-border bg-white px-5 text-sm font-semibold text-foreground transition hover:-translate-y-0.5 hover:shadow-panel"
            >
              <ExternalLink size={15} className="md:hidden" />
              <ArrowUpRight size={16} className="hidden md:block" />
              原视频
            </a>
          </div>
        </Panel>
      ))}
    </div>
  );
}
