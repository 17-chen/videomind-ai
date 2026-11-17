"use client";

import { useLanguage, useTranslator } from "@/lib/language";
import { useEffect, useRef, useState } from "react";
import { Bot, Loader2, Send, SlidersHorizontal } from "lucide-react";
import { Button, Panel, SecondaryButton, Textarea } from "@/components/ui";
import { chatWithVideos } from "@/lib/api";
import type { ChatResponse } from "@/lib/types";
import { splitAnswerCitations } from "@/lib/chat-citations";

const examples = ["我之前看过哪些关于人工智能的视频？", "总结我收藏的视频里面关于创业的共同观点", "有哪些视频提到了 AI Agent 的商业化？"];

export function ChatClient() {
  const tx = useTranslator();
  const { language } = useLanguage();
  const [question, setQuestion] = useState("");
  const [limit, setLimit] = useState(5);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<(ChatResponse & { question: string }) | null>(null);
  const pending = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  async function ask(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submittedQuestion = question.trim();
    if (!submittedQuestion || pending.current || !mounted.current) return;
    // State-driven button disabling alone cannot guard two submissions before
    // the next render. Keep one in-flight request per mounted form.
    pending.current = true;
    setError("");
    setLoading(true);
    try {
      const response = await chatWithVideos({ question: submittedQuestion, limit, language });
      if (mounted.current) setResult({ ...response, question: submittedQuestion });
    } catch (err) {
      if (mounted.current) setError(err instanceof Error ? err.message : tx("问答失败"));
    } finally {
      pending.current = false;
      if (mounted.current) setLoading(false);
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
            placeholder={tx("输入问题，例如：总结我收藏的视频里面关于创业的共同观点")}
          />
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <label className="flex items-center gap-3 rounded-full border border-border bg-white px-4 py-3 text-sm text-muted-foreground">
              <SlidersHorizontal size={16} />
              {tx("检索数量")}
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
              {tx("询问记忆")}
            </Button>
          </div>
        </form>
      </Panel>

      <div className="flex flex-wrap gap-2">
        {examples.map((example) => (
          <SecondaryButton key={example} type="button" onClick={() => setQuestion(example)} className="h-10 px-4 text-xs">
            {tx(example)}
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
              <p className="text-xl font-black">{tx("Memory answer")}</p>
            </div>
            <p className="mb-4 whitespace-pre-wrap break-words text-sm text-muted-foreground">
              {tx("回答的问题")}：{result.question}
            </p>
            <div className="whitespace-pre-wrap text-sm leading-8">
              {splitAnswerCitations(result.answer, result.sources.length).map((part, index) => part.sourceIndex === undefined ? part.text : (
                <a
                  key={index}
                  href={`/videos/${encodeURIComponent(result.sources[part.sourceIndex].video_id)}`}
                  title={result.sources[part.sourceIndex].title}
                  aria-label={`${part.text} ${result.sources[part.sourceIndex].title}`}
                  className="rounded-sm font-semibold text-accent underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
                >{part.text}</a>
              ))}
            </div>
          </Panel>
          {result.sources.length ? (
            <div className="space-y-3">
              <p className="text-sm font-semibold text-muted-foreground">{tx("引用视频记忆")}</p>
              {result.sources.map((source, index) => (
                <Panel key={source.video_id} className="p-5">
                  <a href={`/videos/${encodeURIComponent(source.video_id)}`} className="text-lg font-black hover:text-accent">
                    {`[${index + 1}] ${source.title}`}
                  </a>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">{source.snippet}</p>
                  <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
                    <span>{source.category ?? tx("未分类")}</span>
                    {source.distance !== null ? <span>{tx("距离")} {source.distance.toFixed(3)}</span> : null}
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
