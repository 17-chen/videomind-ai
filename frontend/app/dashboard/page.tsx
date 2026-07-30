import { BookMarked, CheckCircle2, Clock3, Layers3 } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { VideoSubmitForm } from "@/components/video-submit-form";
import { VideoList } from "@/components/video-list";
import { Badge, Panel } from "@/components/ui";
import { listVideos } from "@/lib/api";
import { statusLabel } from "@/lib/utils";

export default async function DashboardPage() {
  const data = await listVideos({ limit: 8 }).catch(() => ({ items: [], total: 0, limit: 8, offset: 0 }));
  const completed = data.items.filter((video) => video.status === "completed").length;
  const processing = data.items.filter((video) => video.status === "processing" || video.status === "queued").length;
  const categories = new Set(data.items.map((video) => video.summary?.category).filter(Boolean));

  const stats = [
    { label: "视频总数", value: data.total, icon: BookMarked },
    { label: "已完成", value: completed, icon: CheckCircle2 },
    { label: "处理中", value: processing, icon: Clock3 },
    { label: "分类数量", value: categories.size, icon: Layers3 }
  ];

  return (
    <AppShell>
      <div className="space-y-7">
        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
          <div>
            <Badge className="bg-white">工作台</Badge>
            <h1 className="mt-3 text-3xl font-semibold tracking-normal">工作台</h1>
            <p className="mt-2 text-sm text-muted-foreground">查看处理进度、最近学习内容和知识库增长情况。</p>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {stats.map((stat) => {
            const Icon = stat.icon;
            return (
              <Panel key={stat.label} className="p-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">{stat.label}</span>
                  <Icon size={18} className="text-primary" />
                </div>
                <p className="mt-4 text-3xl font-semibold">{stat.value}</p>
              </Panel>
            );
          })}
        </div>

        <div className="grid gap-6 lg:grid-cols-[0.88fr_1.12fr]">
          <Panel className="p-5">
            <p className="font-semibold">添加新视频</p>
            <p className="mb-5 mt-1 text-sm text-muted-foreground">提交后进入队列，详情页可触发处理和 AI 分析。</p>
            <VideoSubmitForm />
          </Panel>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">最近学习内容</h2>
              <span className="text-xs text-muted-foreground">
                {data.items[0] ? statusLabel(data.items[0].status) : "暂无状态"}
              </span>
            </div>
            <VideoList videos={data.items.slice(0, 4)} />
          </div>
        </div>
      </div>
    </AppShell>
  );
}
