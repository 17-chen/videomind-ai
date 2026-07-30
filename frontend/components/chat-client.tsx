"use client";

import { useState } from "react";
import { Loader2, Send, SlidersHorizontal } from "lucide-react";
import { Button, Panel, SecondaryButton, Textarea } from "@/components/ui";
import { chatWithVideos } from "@/lib/api";
import type { ChatResponse } from "@/lib/types";

const examples = ["我之前看过哪些关于人工智能的视频？", "总结我收藏的视频里面关于创业的共同观点", "有哪些视频提到了 AI Agent 的商业化？"];

export function ChatClient() {
  const [question, setQuestion] = useState("");
  const [limit, setLimit] = useState(5);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ChatResponse | null>(null);

  async function ask(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      setResult(await chatWithVideos({ question, limit }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "问答失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <Panel className="p-5">
        <form onSubmit={ask} className="space-y-4">
          <Textarea
            required
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="输入问题，例如：总结我收藏的视频里面关于创业的共同观点"
          />
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <label className="flex items-center gap-3 text-sm text-muted-foreground">
              <SlidersHorizontal size={16} />
              检索数量
              <input
                type="range"
                min={1}
                max={10}
                value={limit}
                onChange={(event) => setLimit(Number(event.target.value))}
                className="w-32 accent-[hsl(var(--primary))]"
              />
              <span className="w-5 text-foreground">{limit}</span>
            </label>
            <Button type="submit" disabled={loading || !question.trim()} className="sm:w-32">
              {loading ? <Loader2 className="animate-spin" size={16} /> : <Send size={16} />}
              提问
            </Button>
          </div>
        </form>
      </Panel>

      <div className="flex flex-wrap gap-2">
        {examples.map((example) => (
          <SecondaryButton key={example} type="button" onClick={() => setQuestion(example)} className="h-9 rounded-full px-3 text-xs">
            {example}
          </SecondaryButton>
        ))}
      </div>

      {error ? <Panel className="border-destructive/35 p-4 text-sm text-destructive">{error}</Panel> : null}

      {result ? (
        <div className="space-y-4">
          <Panel className="p-5">
            <p className="mb-3 text-sm font-semibold text-muted-foreground">回答</p>
            <div className="whitespace-pre-wrap text-sm leading-7">{result.answer}</div>
          </Panel>
          {result.sources.length ? (
            <div className="space-y-3">
              <p className="text-sm font-semibold">引用视频</p>
              {result.sources.map((source) => (
                <Panel key={source.video_id} className="p-4">
                  <a href={`/videos/${source.video_id}`} className="font-medium hover:text-primary">
                    {source.title}
                  </a>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">{source.snippet}</p>
                  <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
                    <span>{source.category ?? "未分类"}</span>
                    {source.distance !== null ? <span>距离 {source.distance.toFixed(3)}</span> : null}
                  </div>
                </Panel>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
