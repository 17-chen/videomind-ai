import { Bot, FileText, Network, PlaySquare, Search } from "lucide-react";
import { Badge, Panel } from "@/components/ui";

const rows = [
  { title: "AI Agent 创业方法论", category: "Business", status: "已写入知识库" },
  { title: "Bilibili 技术分享：RAG 架构", category: "Programming", status: "已生成笔记" },
  { title: "抖音短视频增长复盘", category: "Marketing", status: "待分析" }
];

export function KnowledgePreview() {
  return (
    <div className="space-y-4">
      <Panel className="ai-constellation relative min-h-[310px] overflow-hidden p-7">
        <div className="relative z-10 flex h-full flex-col justify-between">
          <div>
            <Badge className="border-accent/30 bg-white text-foreground">Memory Space</Badge>
            <h2 className="mt-5 max-w-md text-5xl font-black leading-[0.92] tracking-normal sm:text-6xl">
              AI Video Memory
            </h2>
            <p className="mt-5 max-w-sm text-sm leading-6 text-muted-foreground">
              你的收藏视频会被转写、理解、归档，并在未来的某个问题里重新出现。
            </p>
          </div>
          <div className="mt-8 flex flex-wrap gap-2">
            {["Transcript", "Notes", "RAG", "Timeline"].map((item) => (
              <Badge key={item} className="bg-white/90 text-foreground">
                {item}
              </Badge>
            ))}
          </div>
        </div>
        <div className="absolute right-8 top-8 hidden h-28 w-28 rounded-full border border-foreground/10 sm:block" />
        <div className="absolute bottom-8 right-10 hidden rotate-[-10deg] rounded-[24px] border border-border bg-white/86 px-5 py-4 shadow-panel sm:block">
          <p className="text-xs text-muted-foreground">Today insight</p>
          <p className="mt-1 text-2xl font-black">+ 12%</p>
        </div>
      </Panel>

      <div className="grid gap-4 sm:grid-cols-3">
        <Panel className="p-5">
          <PlaySquare size={20} className="text-foreground" />
          <p className="mt-5 text-3xl font-black">128</p>
          <p className="text-sm text-muted-foreground">Video Library</p>
        </Panel>
        <Panel className="p-5">
          <FileText size={18} className="text-accent" />
          <p className="mt-5 text-3xl font-black">94</p>
          <p className="text-sm text-muted-foreground">AI Notes</p>
        </Panel>
        <Panel className="p-5">
          <Network size={18} className="text-violet" />
          <p className="mt-5 text-3xl font-black">36</p>
          <p className="text-sm text-muted-foreground">Knowledge Map</p>
        </Panel>
      </div>

      <Panel className="overflow-hidden">
        <div className="border-b border-border bg-muted/30 px-5 py-4">
          <div className="flex items-center gap-2 rounded-full border border-border bg-white px-4 py-3 text-sm text-muted-foreground">
            <Search size={15} />
            搜索：AI Agent 创业
          </div>
        </div>
        <div className="divide-y divide-border">
          {rows.map((row) => (
            <div key={row.title} className="grid gap-2 px-5 py-4 sm:grid-cols-[1fr_auto] sm:items-center">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{row.title}</p>
                <p className="mt-1 text-xs text-muted-foreground">{row.status}</p>
              </div>
              <Badge className="w-fit bg-white">{row.category}</Badge>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
