export type AiSettings = {
  provider: "deepseek" | "openai" | null;
  model: string | null;
  has_api_key: boolean;
  has_asr_api_key: boolean;
  demo_mode: boolean;
};

export type AiSettingsWrite = {
  provider: "deepseek" | "openai";
  model: string;
  api_key?: string;
  asr_api_key?: string;
  clear_asr_api_key?: boolean;
};

export type Transcript = {
  id: string;
  content: string;
  created_at: string;
  updated_at: string;
};

export type Summary = {
  id: string;
  title: string | null;
  summary: string;
  key_points: string[];
  keywords: string[];
  category: string | null;
  important_quotes: string[];
  timeline: Record<string, unknown>[];
  action_items: string[];
  difficulty_level: string | null;
  target_audience: string | null;
  analysis_json: Record<string, unknown>;
  markdown_note: string | null;
  created_at: string;
  updated_at: string;
};

export type Video = {
  id: string;
  user_id: string;
  url: string;
  title: string | null;
  description: string | null;
  duration: number | null;
  thumbnail: string | null;
  status: "queued" | "processing" | "completed" | "failed" | string;
  source: string | null;
  tags: string[];
  processing_error: string | null;
  media_path: string | null;
  audio_path: string | null;
  processed_at: string | null;
  transcript: Transcript | null;
  summary: Summary | null;
  created_at: string;
  updated_at: string;
};

export type VideoListResponse = {
  items: Video[];
  total: number;
  limit: number;
  offset: number;
};

export type ChatSource = {
  video_id: string;
  title: string;
  url: string;
  category: string | null;
  distance: number | null;
  snippet: string;
};

export type ChatResponse = {
  answer: string;
  sources: ChatSource[];
};
