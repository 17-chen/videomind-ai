import type { ChatResponse, Video, VideoListResponse } from "@/lib/types";

const BROWSER_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const SERVER_API_BASE_URL = process.env.INTERNAL_API_BASE_URL ?? BROWSER_API_BASE_URL;

function getApiBaseUrl() {
  return typeof window === "undefined" ? SERVER_API_BASE_URL : BROWSER_API_BASE_URL;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers
    },
    cache: "no-store"
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(payload.detail ?? "请求失败");
  }

  return response.json() as Promise<T>;
}

export async function listVideos(params?: { search?: string; category?: string; limit?: number }) {
  const query = new URLSearchParams();
  if (params?.search) query.set("search", params.search);
  if (params?.category) query.set("category", params.category);
  if (params?.limit) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<VideoListResponse>(`/videos${suffix}`);
}

export async function getVideo(id: string) {
  return request<Video>(`/videos/${id}`);
}

export async function createVideo(payload: { url: string; title?: string; description?: string; tags: string[] }) {
  return request<Video>("/videos", {
    method: "POST",
    body: JSON.stringify(payload)
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

export async function chatWithVideos(payload: { question: string; limit: number }) {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export { BROWSER_API_BASE_URL as API_BASE_URL };
