import Link from "next/link";
import { getServerTranslator } from "@/lib/server-language";
import { ArrowRight, BrainCircuit, Library, Search, Sparkles } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { KnowledgePreview } from "@/components/knowledge-preview";
import { VideoSubmitForm } from "@/components/video-submit-form";
import { Badge, Panel } from "@/components/ui";

const steps = [
  { title: "Video Library", description: "所有收藏视频沉淀成可回访的个人记忆。", icon: Library },
  { title: "AI Notes", description: "处理视频后生成字幕、摘要和 Markdown 笔记。", icon: BrainCircuit },
  { title: "Ask Memory", description: "用对话重新调用过去收藏过的知识。", icon: Search }
];

export default async function HomePage() {
  const tx = await getServerTranslator();
  return (
    <AppShell>
      <section className="grid gap-8 pb-12 lg:grid-cols-[0.88fr_1.12fr] lg:items-start">
        <div className="space-y-8 pt-4">
          <Badge className="border-accent/30 bg-white text-foreground">
            <Sparkles size={13} />
            {tx("Personal AI memory space")}
          </Badge>
          <div className="max-w-3xl space-y-6">
            <h1 className="text-6xl font-black leading-[0.9] tracking-normal text-foreground sm:text-7xl lg:text-8xl">
              VideoMind
            </h1>
            <p className="max-w-xl text-xl font-medium leading-8 text-foreground">
              {tx("把收藏但没时间看的视频，变成一个属于你的 AI 第二大脑。")}
            </p>
            <p className="max-w-lg text-sm leading-7 text-muted-foreground">
              {tx("添加视频链接后，可以依次处理字幕、生成 AI 笔记并写入知识库，让它成为以后能追问的内容。")}
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/dashboard"
              className="inline-flex h-12 items-center gap-2 rounded-full bg-foreground px-6 text-sm font-semibold text-primary-foreground transition hover:-translate-y-0.5 hover:shadow-float"
            >
              {tx("打开今日记忆")}
              <ArrowRight size={16} />
            </Link>
            <Link
              href="/chat"
              className="inline-flex h-12 items-center gap-2 rounded-full border border-border bg-white px-6 text-sm font-semibold transition hover:-translate-y-0.5 hover:shadow-panel"
            >
              {tx("询问我的视频")}
            </Link>
          </div>
          <Panel className="p-6">
            <div className="mb-5">
              <p className="text-lg font-black">{tx("Save a video memory")}</p>
              <p className="mt-1 text-sm text-muted-foreground">{tx("粘贴视频链接保存记录，然后在详情页继续处理。")}</p>
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
                    <p className="text-lg font-black">{tx(step.title)}</p>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">{tx(step.description)}</p>
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
