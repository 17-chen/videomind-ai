"use client";

import { useState } from "react";
import { Bot, Loader2, Send, SlidersHorizontal } from "lucide-react";
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
    <div className="space-y-5">
      <Panel className="ai-constellation p-5 sm:p-7">
        <form onSubmit={ask} className="space-y-4">
          <Textarea
            required
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            className="min-h-40 bg-white/90 text-base leading-8"
            placeholder="输入问题，例如：总结我收藏的视频里面关于创业的共同观点"
          />
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <label className="flex items-center gap-3 rounded-full border border-border bg-white px-4 py-3 text-sm text-muted-foreground">
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
            <Button type="submit" disabled={loading || !question.trim()} className="sm:w-36">
              {loading ? <Loader2 className="animate-spin" size={16} /> : <Send size={16} />}
              询问记忆
            </Button>
          </div>
        </form>
      </Panel>

      <div className="flex flex-wrap gap-2">
        {examples.map((example) => (
          <SecondaryButton key={example} type="button" onClick={() => setQuestion(example)} className="h-10 px-4 text-xs">
            {example}
          </SecondaryButton>
        ))}
      </div>

      {error ? <Panel className="border-destructive/35 p-5 text-sm text-destructive">{error}</Panel> : null}

      {result ? (
        <div className="space-y-4">
          <Panel className="p-6 sm:p-7">
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-full bg-foreground text-primary-foreground">
                <Bot size={18} />
              </div>
              <p className="text-xl font-black">Memory answer</p>
            </div>
            <div className="whitespace-pre-wrap text-sm leading-8">{result.answer}</div>
          </Panel>
          {result.sources.length ? (
            <div className="space-y-3">
              <p className="text-sm font-semibold text-muted-foreground">引用视频记忆</p>
              {result.sources.map((source) => (
                <Panel key={source.video_id} className="p-5">
                  <a href={`/videos/${source.video_id}`} className="text-lg font-black hover:text-accent">
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
