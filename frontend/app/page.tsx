import Link from "next/link";
import { ArrowRight, BrainCircuit, Library, Search, Sparkles } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { KnowledgePreview } from "@/components/knowledge-preview";
import { VideoSubmitForm } from "@/components/video-submit-form";
import { Badge, Panel } from "@/components/ui";

const steps = [
  { title: "收藏视频", description: "粘贴 Bilibili、抖音链接，统一进入个人知识库。", icon: Library },
  { title: "自动理解", description: "字幕、转写、AI 分析和 Markdown 笔记串成一条工作流。", icon: BrainCircuit },
  { title: "随时追问", description: "用 RAG 在过往视频里检索观点、案例和行动建议。", icon: Search }
];

export default function HomePage() {
  return (
    <AppShell>
      <section className="grid gap-8 pb-12 lg:grid-cols-[0.92fr_1.08fr] lg:items-start">
        <div className="space-y-7">
          <Badge className="border-primary/20 bg-white text-primary">
            <Sparkles size={13} />
            中文优先的视频知识管理平台
          </Badge>
          <div className="max-w-3xl space-y-5">
            <h1 className="text-4xl font-semibold leading-tight tracking-normal text-foreground sm:text-5xl lg:text-6xl">
              VideoMind AI
            </h1>
            <p className="max-w-2xl text-lg leading-8 text-muted-foreground">
              把收藏但没时间看的视频，自动转化为结构化笔记、可搜索资料和可以追问的个人知识资产。
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/dashboard"
              className="inline-flex h-11 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:brightness-95"
            >
              进入工作台
              <ArrowRight size={16} />
            </Link>
            <Link
              href="/chat"
              className="inline-flex h-11 items-center gap-2 rounded-md border border-border bg-white px-4 text-sm font-medium hover:bg-muted"
            >
              打开视频问答
            </Link>
          </div>
          <Panel className="p-5">
            <div className="mb-5">
              <p className="text-sm font-semibold">快速添加视频</p>
              <p className="mt-1 text-sm text-muted-foreground">先入库，再处理、分析和写入向量知识库。</p>
            </div>
            <VideoSubmitForm />
          </Panel>
        </div>

        <div className="space-y-4">
          <KnowledgePreview />
          <div className="grid gap-3 pt-2 sm:grid-cols-3">
            {steps.map((step) => {
              const Icon = step.icon;
              return (
                <div key={step.title} className="space-y-3 rounded-lg border border-border bg-white p-4 shadow-panel">
                  <Icon className="text-primary" size={20} />
                  <div>
                    <p className="font-semibold">{step.title}</p>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">{step.description}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>
    </AppShell>
  );
}
