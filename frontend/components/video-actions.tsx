"use client";

import { useTranslator } from "@/lib/language";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Bot, Database, Loader2, WandSparkles } from "lucide-react";
import { Button, SecondaryButton } from "@/components/ui";
import { analyzeVideo, embedVideo, processVideo, runVideo } from "@/lib/api";
import type { Video } from "@/lib/types";
import { videoStageLabel } from "@/lib/utils";

type ActionVideo = Pick<Video, "id" | "status" | "transcript" | "summary" | "processing_error">;
const activeStatuses = new Set(["processing", "downloading", "transcribing", "analyzing", "embedding"]);

export function VideoActions({ video }: { video: ActionVideo }) {
  const tx = useTranslator();
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState<string | null>(null);
  const active = activeStatuses.has(video.status);

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => router.refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [active, router]);

  async function run(action: "all" | "process" | "analyze" | "embed") {
    setLoading(action);
    setMessage("");
    try {
      const result =
        action === "all" ? await runVideo(video.id) : action === "process" ? await processVideo(video.id) : action === "analyze" ? await analyzeVideo(video.id) : await embedVideo(video.id);
      setMessage("message" in result ? result.message : action === "analyze" ? tx("AI 分析已完成") : tx("操作完成"));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : tx("操作失败"));
    } finally {
      setLoading(null);
      router.refresh();
    }
  }

  const busy = loading !== null || active;
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{tx("当前状态：")}<span className="font-semibold text-foreground">{tx(videoStageLabel(video))}</span></p>
      <div className="grid gap-2">
        <Button type="button" onClick={() => run("all")} disabled={busy}>
          {loading === "all" || active ? <Loader2 className="animate-spin" size={16} /> : <WandSparkles size={16} />}
          {active ? tx("处理中，请稍候") : video.status === "failed" ? tx("从中断处继续") : tx("一键处理并入库")}
        </Button>
        <p className="text-xs leading-5 text-muted-foreground">
          {tx("将处理字幕、生成 AI 笔记并写入知识库。模型服务商可能按用量收费。")}{" "}
          <Link href="/settings" className="font-semibold text-foreground underline underline-offset-2">{tx("检查模型设置")}</Link>
        </p>
        <SecondaryButton type="button" onClick={() => run("process")} disabled={busy}>
          {loading === "process" ? <Loader2 className="animate-spin" size={16} /> : <WandSparkles size={16} />}
          {video.status === "failed" ? tx("重新处理视频") : tx("仅处理字幕")}
        </SecondaryButton>
        <SecondaryButton type="button" onClick={() => run("analyze")} disabled={busy || !video.transcript}>
          {loading === "analyze" ? <Loader2 className="animate-spin" size={16} /> : <Bot size={16} />}
          {tx("AI 分析")}
        </SecondaryButton>
        <SecondaryButton type="button" onClick={() => run("embed")} disabled={busy || (!video.transcript && !video.summary)}>
          {loading === "embed" ? <Loader2 className="animate-spin" size={16} /> : <Database size={16} />}
          {tx("写入知识库")}
        </SecondaryButton>
      </div>
      {!video.transcript && !active ? <p className="text-xs leading-5 text-muted-foreground">{tx("先处理视频，获得字幕或转写文本后才能分析。")}</p> : null}
      {video.status === "failed" && video.processing_error ? <p className="rounded-[20px] border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm leading-6 text-destructive">{video.processing_error}</p> : null}
      {message ? <p className="rounded-[20px] border border-border bg-white px-4 py-3 text-sm leading-6 text-muted-foreground">{message}</p> : null}
    </div>
  );
}
