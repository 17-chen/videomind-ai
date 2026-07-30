import Link from "next/link";
import { ArrowLeft, FileText, ListChecks, MessageSquareQuote, Timer } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { VideoActions } from "@/components/video-actions";
import { Badge, EmptyState, Panel } from "@/components/ui";
import { getVideo } from "@/lib/api";
import { formatDate, sourceLabel, statusLabel } from "@/lib/utils";

type VideoDetailPageProps = {
  params: Promise<{ id: string }>;
};

export default async function VideoDetailPage({ params }: VideoDetailPageProps) {
  const { id } = await params;
  const video = await getVideo(id);
  const title = video.summary?.title ?? video.title ?? "未命名视频";

  return (
    <AppShell>
      <div className="space-y-6">
        <Link href="/library" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft size={16} />
          返回知识库
        </Link>

        <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
          <div className="space-y-5">
            <div>
              <div className="mb-3 flex flex-wrap gap-2">
                <Badge>{sourceLabel(video.source)}</Badge>
                <Badge className="bg-white">{statusLabel(video.status)}</Badge>
                {video.summary?.category ? <Badge className="border-primary/25 bg-primary/10 text-primary">{video.summary.category}</Badge> : null}
              </div>
              <h1 className="text-3xl font-semibold leading-tight tracking-normal">{title}</h1>
              <p className="mt-3 break-all text-sm leading-6 text-muted-foreground">{video.url}</p>
            </div>

            <Panel className="p-5">
              <div className="mb-4 flex items-center gap-2">
                <FileText size={18} className="text-primary" />
                <h2 className="font-semibold">AI 摘要</h2>
              </div>
              {video.summary ? (
                <div className="space-y-4 text-sm leading-7">
                  <p>{video.summary.summary}</p>
                  <div>
                    <p className="mb-2 font-medium">核心观点</p>
                    <ol className="space-y-2 pl-5">
                      {video.summary.key_points.map((point, index) => (
                        <li key={`${point}-${index}`} className="list-decimal text-muted-foreground">
                          {point}
                        </li>
                      ))}
                    </ol>
                  </div>
                </div>
              ) : (
                <EmptyState title="还没有 AI 摘要" description="先完成视频转写，再点击右侧的 AI 分析按钮。" />
              )}
            </Panel>

            <Panel className="p-5">
              <div className="mb-4 flex items-center gap-2">
                <Timer size={18} className="text-primary" />
                <h2 className="font-semibold">时间线</h2>
              </div>
              {video.summary?.timeline.length ? (
                <div className="space-y-3">
                  {video.summary.timeline.map((item, index) => (
                    <div key={index} className="rounded-md border border-border bg-muted/50 p-3 text-sm">
                      <pre className="whitespace-pre-wrap break-words font-sans text-muted-foreground">{JSON.stringify(item, null, 2)}</pre>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState title="暂无时间线" description="时间线会在 AI 分析完成后显示。" />
              )}
            </Panel>

            <Panel className="p-5">
              <div className="mb-4 flex items-center gap-2">
                <MessageSquareQuote size={18} className="text-primary" />
                <h2 className="font-semibold">Markdown 笔记</h2>
              </div>
              {video.summary?.markdown_note ? (
                <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap rounded-md border border-border bg-muted/50 p-4 text-sm leading-7">
                  {video.summary.markdown_note}
                </pre>
              ) : (
                <EmptyState title="还没有 Markdown 笔记" description="AI 分析完成后，这里会显示可复制和下载的笔记内容。" />
              )}
            </Panel>
          </div>

          <aside className="space-y-4">
            <Panel className="p-5">
              <p className="font-semibold">处理操作</p>
              <p className="mb-4 mt-1 text-sm text-muted-foreground">按顺序完成处理、分析、写入知识库。</p>
              <VideoActions videoId={video.id} />
            </Panel>

            <Panel className="p-5">
              <div className="mb-4 flex items-center gap-2">
                <ListChecks size={18} className="text-primary" />
                <p className="font-semibold">视频信息</p>
              </div>
              <dl className="space-y-3 text-sm">
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">创建时间</dt>
                  <dd>{formatDate(video.created_at)}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">完成时间</dt>
                  <dd>{formatDate(video.processed_at)}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">难度</dt>
                  <dd>{video.summary?.difficulty_level ?? "未分析"}</dd>
                </div>
              </dl>
              {video.tags.length ? (
                <div className="mt-5 flex flex-wrap gap-2">
                  {video.tags.map((tag) => (
                    <Badge key={tag} className="bg-white">
                      #{tag}
                    </Badge>
                  ))}
                </div>
              ) : null}
            </Panel>
          </aside>
        </div>
      </div>
    </AppShell>
  );
}
