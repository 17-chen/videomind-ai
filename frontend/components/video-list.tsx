import Link from "next/link";
import { Clock, ExternalLink } from "lucide-react";
import type { Video } from "@/lib/types";
import { Badge, EmptyState, Panel } from "@/components/ui";
import { formatDate, sourceLabel, statusLabel } from "@/lib/utils";

export function VideoList({ videos }: { videos: Video[] }) {
  if (!videos.length) {
    return <EmptyState title="还没有视频" description="先添加一个视频链接，VideoMind AI 会把它变成可整理、可检索的知识资产。" />;
  }

  return (
    <div className="grid gap-3">
      {videos.map((video) => (
        <Panel key={video.id} className="p-4">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div className="min-w-0 space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge>{sourceLabel(video.source)}</Badge>
                <Badge className="bg-white">{statusLabel(video.status)}</Badge>
                {video.summary?.category ? <Badge className="border-primary/25 bg-primary/10 text-primary">{video.summary.category}</Badge> : null}
              </div>
              <Link href={`/videos/${video.id}`} className="block text-base font-semibold hover:text-primary">
                {video.summary?.title ?? video.title ?? "未命名视频"}
              </Link>
              <p className="line-clamp-2 text-sm leading-6 text-muted-foreground">
                {video.summary?.summary ?? video.description ?? video.url}
              </p>
              <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1">
                  <Clock size={13} />
                  {formatDate(video.created_at)}
                </span>
                {video.tags.map((tag) => (
                  <span key={tag}>#{tag}</span>
                ))}
              </div>
            </div>
            <a
              href={video.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-md border border-border px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <ExternalLink size={15} />
              原视频
            </a>
          </div>
        </Panel>
      ))}
    </div>
  );
}
