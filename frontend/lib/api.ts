import type { AiSettings, AiSettingsWrite, ChatResponse, Video, VideoListResponse } from "@/lib/types";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";

const BROWSER_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const SERVER_API_BASE_URL = process.env.INTERNAL_API_BASE_URL ?? BROWSER_API_BASE_URL;

function getApiBaseUrl() {
  return typeof window === "undefined" ? SERVER_API_BASE_URL : BROWSER_API_BASE_URL;
}

async function request<T>(path: string, init?: RequestInit, accessToken?: string): Promise<T> {
  let token = accessToken;
  if (!token && typeof window !== "undefined") {
    const supabase = getSupabaseBrowserClient();
    token = (await supabase?.auth.getSession())?.data.session?.access_token;
  }
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers
    },
    cache: "no-store"
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(formatApiError(payload));
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function formatApiError(payload: unknown): string {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) return "请求失败，请稍后重试。";

  const detail = payload.detail;
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return "请求失败，请检查输入内容。";

  const messages = detail
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const issue = item as { loc?: unknown[]; msg?: string };
      const field = issue.loc?.at(-1);
      if (field === "url") return "视频链接格式不正确，请粘贴完整的视频地址。";
      return issue.msg ?? null;
    })
    .filter((message): message is string => Boolean(message));

  return [...new Set(messages)].join("；") || "请求参数不正确，请检查后重试。";
}

export async function listVideos(params?: { search?: string; category?: string; limit?: number }, accessToken?: string) {
  const query = new URLSearchParams();
  if (params?.search) query.set("search", params.search);
  if (params?.category) query.set("category", params.category);
  if (params?.limit) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<VideoListResponse>(`/videos${suffix}`, undefined, accessToken);
}

export async function getVideo(id: string, accessToken?: string) {
  return request<Video>(`/videos/${id}`, undefined, accessToken);
}

export async function createVideo(payload: { url: string; title?: string; description?: string; tags: string[] }) {
  return request<Video>("/videos", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function runVideo(id: string) {
  return request<{ id: string; status: string; message: string }>(`/videos/${id}/run`, {
    method: "POST"
  });
}

export async function processVideo(id: string) {
  return request<{ id: string; status: string; message: string }>(`/videos/${id}/process`, {
    method: "POST"
  });
}

export async function analyzeVideo(id: string) {
  return request<{ id: string; summary: Video["summary"] }>(`/videos/${id}/analyze`, {
    method: "POST"
  });
}

export async function embedVideo(id: string) {
  return request<{ id: string; vector_id: string; message: string }>(`/videos/${id}/embed`, {
    method: "POST"
  });
}

export async function chatWithVideos(payload: { question: string; limit: number; language: "zh" | "en" }) {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function getAiSettings() {
  return request<AiSettings>("/settings/ai");
}

export async function saveAiSettings(payload: AiSettingsWrite) {
  return request<AiSettings>("/settings/ai", { method: "PUT", body: JSON.stringify(payload) });
}

export async function deleteAiSettings() {
  return request<void>("/settings/ai", { method: "DELETE" });
}

export { BROWSER_API_BASE_URL as API_BASE_URL };
