import Link from "next/link";
import { ArrowRight, BrainCircuit, Library, Search, Sparkles } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { KnowledgePreview } from "@/components/knowledge-preview";
import { VideoSubmitForm } from "@/components/video-submit-form";
import { Badge, Panel } from "@/components/ui";

const steps = [
  { title: "Video Library", description: "所有收藏视频沉淀成可回访的个人记忆。", icon: Library },
  { title: "AI Notes", description: "字幕、转写、摘要和 Markdown 自动生成。", icon: BrainCircuit },
  { title: "Ask Memory", description: "用对话重新调用过去收藏过的知识。", icon: Search }
];

export default function HomePage() {
  return (
    <AppShell>
      <section className="grid gap-8 pb-12 lg:grid-cols-[0.88fr_1.12fr] lg:items-start">
        <div className="space-y-8 pt-4">
          <Badge className="border-accent/30 bg-white text-foreground">
            <Sparkles size={13} />
            Personal AI memory space
          </Badge>
          <div className="max-w-3xl space-y-6">
            <h1 className="text-6xl font-black leading-[0.9] tracking-normal text-foreground sm:text-7xl lg:text-8xl">
              VideoMind
            </h1>
            <p className="max-w-xl text-xl font-medium leading-8 text-foreground">
              把收藏但没时间看的视频，变成一个属于你的 AI 第二大脑。
            </p>
            <p className="max-w-lg text-sm leading-7 text-muted-foreground">
              视频链接进入记忆空间后，会被自动转写、总结、生成知识卡片，并成为未来可以被追问的上下文。
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/dashboard"
              className="inline-flex h-12 items-center gap-2 rounded-full bg-foreground px-6 text-sm font-semibold text-primary-foreground transition hover:-translate-y-0.5 hover:shadow-float"
            >
              打开今日记忆
              <ArrowRight size={16} />
            </Link>
            <Link
              href="/chat"
              className="inline-flex h-12 items-center gap-2 rounded-full border border-border bg-white px-6 text-sm font-semibold transition hover:-translate-y-0.5 hover:shadow-panel"
            >
              询问我的视频
            </Link>
          </div>
          <Panel className="p-6">
            <div className="mb-5">
              <p className="text-lg font-black">Save a video memory</p>
              <p className="mt-1 text-sm text-muted-foreground">粘贴一个视频链接，开始生成你的 AI 记忆卡片。</p>
            </div>
            <VideoSubmitForm />
          </Panel>
        </div>

        <div className="space-y-4">
          <KnowledgePreview />
          <div className="grid gap-4 pt-2 sm:grid-cols-3">
            {steps.map((step) => {
              const Icon = step.icon;
              return (
                <div
                  key={step.title}
                  className="space-y-5 rounded-[24px] border border-border bg-white p-6 shadow-panel transition duration-300 hover:-translate-y-1 hover:shadow-float"
                >
                  <Icon className="text-foreground" size={22} />
                  <div>
                    <p className="text-lg font-black">{step.title}</p>
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
