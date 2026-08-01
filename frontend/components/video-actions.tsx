"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Bot, Database, Loader2, WandSparkles } from "lucide-react";
import { Button, SecondaryButton } from "@/components/ui";
import { analyzeVideo, embedVideo, processVideo } from "@/lib/api";

export function VideoActions({ videoId }: { videoId: string }) {
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState<string | null>(null);

  async function run(action: "process" | "analyze" | "embed") {
    setLoading(action);
    setMessage("");
    try {
      const result =
        action === "process" ? await processVideo(videoId) : action === "analyze" ? await analyzeVideo(videoId) : await embedVideo(videoId);
      setMessage("message" in result ? result.message : action === "analyze" ? "AI 分析已完成" : "操作完成");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "操作失败");
    } finally {
      setLoading(null);
      router.refresh();
    }
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-2">
        <Button type="button" onClick={() => run("process")} disabled={loading !== null}>
          {loading === "process" ? <Loader2 className="animate-spin" size={16} /> : <WandSparkles size={16} />}
          处理视频
        </Button>
        <SecondaryButton type="button" onClick={() => run("analyze")} disabled={loading !== null}>
          {loading === "analyze" ? <Loader2 className="animate-spin" size={16} /> : <Bot size={16} />}
          AI 分析
        </SecondaryButton>
        <SecondaryButton type="button" onClick={() => run("embed")} disabled={loading !== null}>
          {loading === "embed" ? <Loader2 className="animate-spin" size={16} /> : <Database size={16} />}
          写入知识库
        </SecondaryButton>
      </div>
      {message ? <p className="rounded-[20px] border border-border bg-white px-4 py-3 text-sm leading-6 text-muted-foreground">{message}</p> : null}
    </div>
  );
}
