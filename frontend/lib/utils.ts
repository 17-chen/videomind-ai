import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(value: string | null | undefined) {
  if (!value) return "未完成";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

export function statusLabel(status: string) {
  const map: Record<string, string> = {
    queued: "待处理",
    processing: "处理中",
    completed: "已完成",
    failed: "失败"
  };
  return map[status] ?? status;
}

export function sourceLabel(source: string | null) {
  const map: Record<string, string> = {
    bilibili: "Bilibili",
    douyin: "抖音",
    youtube: "YouTube",
    tiktok: "TikTok"
  };
  return source ? map[source] ?? source : "未知来源";
}
