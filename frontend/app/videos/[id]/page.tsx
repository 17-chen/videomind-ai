import Link from "next/link";
import { ArrowLeft, Bot, Calendar, FileText, MessageCircle, MessageSquareQuote, Play, Timer } from "lucide-react";
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
  const summary = video.summary?.summary ?? "这条视频还在等待 AI 理解。完成处理和分析后，它会变成一张可回顾、可追问的知识卡片。";
  const points = video.summary?.key_points ?? [];

  return (
    <AppShell>
      <div className="space-y-7">
        <Link href="/library" className="inline-flex items-center gap-2 rounded-full border border-border bg-white px-4 py-2 text-sm font-semibold text-muted-foreground shadow-panel hover:text-foreground">
          <ArrowLeft size={16} />
          返回知识库
        </Link>

        <Panel className="overflow-hidden p-5 sm:p-7">
          <div className="grid gap-7 lg:grid-cols-[0.95fr_1.05fr] lg:items-stretch">
            <div className="relative min-h-[280px] overflow-hidden rounded-[24px] bg-muted">
              {video.thumbnail ? (
                <img src={video.thumbnail} alt="" className="h-full min-h-[280px] w-full object-cover" />
              ) : (
                <div className="ai-constellation flex h-full min-h-[280px] w-full items-center justify-center">
                  <div className="flex h-20 w-20 items-center justify-center rounded-full bg-foreground text-primary-foreground shadow-float">
                    <Play size={28} className="fill-current" />
                  </div>
                </div>
              )}
              <div className="absolute left-5 top-5 flex flex-wrap gap-2">
                <Badge className="bg-white/90 text-foreground">{sourceLabel(video.source)}</Badge>
                <Badge className="bg-white/90 text-foreground">{statusLabel(video.status)}</Badge>
              </div>
            </div>

            <div className="flex flex-col justify-between gap-8">
              <div>
                <div className="flex flex-wrap gap-2">
                  {video.summary?.category ? <Badge className="border-accent/30 bg-accent/10 text-foreground">{video.summary.category}</Badge> : null}
                  <Badge className="bg-white">Knowledge Card</Badge>
                </div>
                <h1 className="mt-5 max-w-3xl text-4xl font-black leading-[0.98] tracking-normal sm:text-6xl">{title}</h1>
                <p className="mt-5 max-w-2xl text-base leading-8 text-muted-foreground">{summary}</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-[24px] border border-border bg-white p-4">
                  <Calendar size={16} className="text-muted-foreground" />
                  <p className="mt-3 text-xs text-muted-foreground">创建时间</p>
                  <p className="mt-1 text-sm font-black">{formatDate(video.created_at)}</p>
                </div>
                <div className="rounded-[24px] border border-border bg-white p-4">
                  <Timer size={16} className="text-muted-foreground" />
                  <p className="mt-3 text-xs text-muted-foreground">完成时间</p>
                  <p className="mt-1 text-sm font-black">{formatDate(video.processed_at)}</p>
                </div>
                <div className="rounded-[24px] border border-border bg-white p-4">
                  <Bot size={16} className="text-accent" />
                  <p className="mt-3 text-xs text-muted-foreground">难度</p>
                  <p className="mt-1 text-sm font-black">{video.summary?.difficulty_level ?? "未分析"}</p>
                </div>
              </div>
            </div>
          </div>
        </Panel>

        <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
          <div className="space-y-6">
            <Panel className="p-6 sm:p-7">
              <div className="mb-6 flex items-center gap-3">
                <FileText size={20} className="text-foreground" />
                <h2 className="text-2xl font-black">核心观点</h2>
              </div>
              {points.length ? (
                <div className="grid gap-4 sm:grid-cols-2">
                  {points.map((point, index) => (
                    <div key={`${point}-${index}`} className="rounded-[24px] border border-border bg-white p-5">
                      <p className="text-sm font-black text-accent">0{index + 1}</p>
                      <p className="mt-4 text-sm leading-7 text-foreground">{point}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState title="还没有核心观点" description="完成 AI 分析后，这里会显示视频被提炼出的知识卡片。" />
              )}
            </Panel>

            <Panel className="p-6 sm:p-7">
              <div className="mb-4 flex items-center gap-2">
                <Timer size={20} className="text-foreground" />
                <h2 className="text-2xl font-black">Timeline</h2>
              </div>
              {video.summary?.timeline.length ? (
                <div className="space-y-4">
                  {video.summary.timeline.map((item, index) => (
                    <div key={index} className="rounded-[24px] border border-border bg-white p-5 text-sm">
                      <pre className="whitespace-pre-wrap break-words font-sans text-muted-foreground">{JSON.stringify(item, null, 2)}</pre>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState title="暂无时间线" description="时间线会在 AI 分析完成后显示。" />
              )}
            </Panel>

            <Panel className="p-6 sm:p-7">
              <div className="mb-4 flex items-center gap-2">
                <MessageSquareQuote size={20} className="text-foreground" />
                <h2 className="text-2xl font-black">Markdown Notes</h2>
              </div>
              {video.summary?.markdown_note ? (
                <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap rounded-[24px] border border-border bg-white p-5 text-sm leading-7">
                  {video.summary.markdown_note}
                </pre>
              ) : (
                <EmptyState title="还没有 Markdown 笔记" description="AI 分析完成后，这里会显示可复制和下载的笔记内容。" />
              )}
            </Panel>
          </div>

          <aside className="space-y-4">
            <Panel className="sticky top-24 p-6">
              <p className="text-2xl font-black">AI Actions</p>
              <p className="mb-5 mt-2 text-sm leading-6 text-muted-foreground">按顺序让这条视频进入你的长期记忆。</p>
              <VideoActions videoId={video.id} />
            </Panel>

            <Panel className="p-6">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-foreground text-primary-foreground">
                <MessageCircle size={20} />
              </div>
              <p className="mt-5 text-2xl font-black">Ask this memory</p>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">进入视频问答，用这条内容和其它视频一起生成回答。</p>
              <Link href="/chat" className="mt-5 inline-flex h-12 items-center rounded-full bg-foreground px-6 text-sm font-semibold text-primary-foreground">
                打开 AI Chat
              </Link>
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
