import { ArrowUpRight, Brain, Clock3, FileText, Library, Network, PlaySquare } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { VideoSubmitForm } from "@/components/video-submit-form";
import { VideoList } from "@/components/video-list";
import { Badge, Panel } from "@/components/ui";
import { listVideos } from "@/lib/api";
import { formatDate } from "@/lib/utils";

export default async function DashboardPage() {
  const data = await listVideos({ limit: 8 }).catch(() => ({ items: [], total: 0, limit: 8, offset: 0 }));
  const notes = data.items.filter((video) => video.summary).length;
  const learningSeconds = data.items.reduce((total, video) => total + (video.duration ?? 0), 0);
  const learningMinutes = Math.max(0, Math.round(learningSeconds / 60));
  const knowledgeGrowth = data.items.filter((video) => video.transcript || video.summary).length;

  const memoryCards = [
    { title: "Video Library", value: data.total, label: "收藏视频", icon: Library, detail: "所有视频记忆入口" },
    { title: "AI Notes", value: notes, label: "生成笔记", icon: FileText, detail: "摘要、观点、行动建议" },
    { title: "Knowledge Map", value: knowledgeGrowth, label: "知识节点", icon: Network, detail: "等待可视化连接" },
    { title: "Recent Learning", value: data.items.length, label: "最近内容", icon: PlaySquare, detail: data.items[0]?.title ?? "暂无新视频" }
  ];

  return (
    <AppShell>
      <div className="space-y-8">
        <Panel className="ai-constellation overflow-hidden p-7 sm:p-9">
          <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-end">
            <div>
              <Badge className="border-accent/30 bg-white text-foreground">Today</Badge>
              <h1 className="mt-6 text-5xl font-black leading-[0.92] tracking-normal sm:text-7xl">
                Good afternoon
              </h1>
              <p className="mt-4 text-2xl font-semibold text-foreground">Your AI memory today</p>
              <p className="mt-4 max-w-xl text-sm leading-7 text-muted-foreground">
                今天你的收藏视频会继续变成笔记、时间线和可追问的知识。这里不是后台，是你的个人 AI 记忆空间。
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
              <div className="rounded-[24px] border border-border bg-white/84 p-5">
                <p className="text-sm text-muted-foreground">今日总结视频</p>
                <p className="mt-2 text-4xl font-black">{notes}</p>
              </div>
              <div className="rounded-[24px] border border-border bg-white/84 p-5">
                <p className="text-sm text-muted-foreground">学习时间</p>
                <p className="mt-2 text-4xl font-black">{learningMinutes || "0"}m</p>
              </div>
              <div className="rounded-[24px] border border-border bg-white/84 p-5">
                <p className="text-sm text-muted-foreground">知识增长</p>
                <p className="mt-2 text-4xl font-black">+{knowledgeGrowth}</p>
              </div>
            </div>
          </div>
        </Panel>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {memoryCards.map((card) => {
            const Icon = card.icon;
            return (
              <Panel key={card.title} className="min-h-56 p-6">
                <div className="flex items-start justify-between">
                  <Icon size={23} className="text-foreground" />
                  <ArrowUpRight size={18} className="text-muted-foreground" />
                </div>
                <p className="mt-10 text-5xl font-black">{card.value}</p>
                <p className="mt-2 text-lg font-black">{card.title}</p>
                <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">{card.detail}</p>
                <Badge className="mt-5 bg-white">{card.label}</Badge>
              </Panel>
            );
          })}
        </div>

        <div className="grid gap-6 lg:grid-cols-[0.78fr_1.22fr]">
          <Panel className="p-6">
            <div className="mb-6 flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-foreground text-primary-foreground">
                <Brain size={20} />
              </div>
              <div>
                <p className="text-lg font-black">Add memory</p>
                <p className="text-sm text-muted-foreground">把视频交给 AI 归档</p>
              </div>
            </div>
            <VideoSubmitForm />
          </Panel>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-black">Recent Learning</h2>
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <Clock3 size={13} />
                {data.items[0] ? formatDate(data.items[0].created_at) : "暂无内容"}
              </span>
            </div>
            <VideoList videos={data.items.slice(0, 4)} />
          </div>
        </div>
      </div>
    </AppShell>
  );
}
