import { formatTimestamp } from "@/lib/date";
import type { Video } from "@/lib/types";
import { translate, type Language } from "@/lib/i18n";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(value: string | null | undefined, language: Language = "zh") {
  if (!value) return translate(language, "未完成");
  return formatTimestamp(value, language) ?? translate(language, "未完成");
}

export function statusLabel(status: string) {
  const map: Record<string, string> = {
    created: "待处理",
    queued: "排队中",
    processing: "处理中",
    downloading: "下载中",
    transcribing: "转写中",
    analyzing: "AI 分析中",
    embedding: "写入知识库中",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消"
  };
  return map[status] ?? status;
}

export function videoStageLabel(video: Pick<Video, "status" | "transcript" | "summary">) {
  if (video.status === "completed" && video.summary) return "已生成笔记";
  if (video.status === "completed" && video.transcript) return "已转写";
  return statusLabel(video.status);
}

export function sourceLabel(source: string | null) {
  const map: Record<string, string> = {
    bilibili: "Bilibili",
    douyin: "抖音",
    youtube: "YouTube",
    tiktok: "TikTok",
    upload: "本地上传"
  };
  return source ? map[source] ?? source : "未知来源";
}
