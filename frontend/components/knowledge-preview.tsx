import { Bot, FileText, PlaySquare, Search } from "lucide-react";
import { Badge, Panel } from "@/components/ui";

const rows = [
  { title: "AI Agent 创业方法论", category: "Business", status: "已写入知识库" },
  { title: "Bilibili 技术分享：RAG 架构", category: "Programming", status: "已生成笔记" },
  { title: "抖音短视频增长复盘", category: "Marketing", status: "待分析" }
];

export function KnowledgePreview() {
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <Panel className="p-4">
          <PlaySquare size={18} className="text-primary" />
          <p className="mt-4 text-2xl font-semibold">128</p>
          <p className="text-xs text-muted-foreground">收藏视频</p>
        </Panel>
        <Panel className="p-4">
          <FileText size={18} className="text-accent" />
          <p className="mt-4 text-2xl font-semibold">94</p>
          <p className="text-xs text-muted-foreground">结构化笔记</p>
        </Panel>
        <Panel className="p-4">
          <Bot size={18} className="text-primary" />
          <p className="mt-4 text-2xl font-semibold">36</p>
          <p className="text-xs text-muted-foreground">可追问主题</p>
        </Panel>
      </div>

      <Panel className="overflow-hidden">
        <div className="border-b border-border bg-muted/40 px-4 py-3">
          <div className="flex items-center gap-2 rounded-md border border-border bg-white px-3 py-2 text-sm text-muted-foreground">
            <Search size={15} />
            搜索：AI Agent 创业
          </div>
        </div>
        <div className="divide-y divide-border">
          {rows.map((row) => (
            <div key={row.title} className="grid gap-2 px-4 py-3 sm:grid-cols-[1fr_auto] sm:items-center">
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
