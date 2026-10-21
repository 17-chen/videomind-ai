"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslator } from "@/lib/language";
import { updateVideo, updateVideoNote, syncVideoIndex } from "@/lib/api";
import type { Video } from "@/lib/types";
import { Button, Input, SecondaryButton, Textarea } from "@/components/ui";

const activeStatuses = new Set(["queued", "processing", "downloading", "transcribing", "analyzing", "embedding"]);

export function VideoEditor({ video, mode }: { video: Video; mode: "metadata" | "note" }) {
  const router = useRouter();
  const tx = useTranslator();
  const [title, setTitle] = useState(video.title ?? "");
  const [description, setDescription] = useState(video.description ?? "");
  const [tags, setTags] = useState(video.tags.join(", "));
  const [category, setCategory] = useState(video.user_category ?? video.summary?.category ?? "");
  const [note, setNote] = useState(video.summary?.markdown_note ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const disabled = busy || activeStatuses.has(video.status);

  async function save() {
    if (mode === "metadata") {
      const parsedTags = tags.split(",").map((tag) => tag.trim()).filter(Boolean);
      if (parsedTags.length > 20 || parsedTags.some((tag) => tag.length > 60)) {
        setMessage(tx("标签最多 20 个，每个最多 60 字"));
        return;
      }
    }
    setBusy(true);
    setMessage("");
    try {
      const result = mode === "note"
        ? await updateVideoNote(video.id, note)
        : await updateVideo(video.id, {
            title,
            description,
            tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean),
            category
          });
      setMessage(result.index_sync_error ?? tx("已保存，并已同步知识库"));
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : tx("保存失败"));
    } finally {
      setBusy(false);
    }
  }

  async function retryIndex() {
    setBusy(true);
    try {
      const result = await syncVideoIndex(video.id);
      setMessage(result.index_sync_error ?? tx("知识库已同步"));
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : tx("同步失败"));
    } finally {
      setBusy(false);
    }
  }

  if (mode === "note") {
    return <div className="space-y-3">
      <label className="block text-sm font-semibold" htmlFor="video-note">{tx("编辑 Markdown 笔记")}</label>
      <Textarea id="video-note" value={note} onChange={(event) => setNote(event.target.value)} maxLength={100000} rows={12} disabled={disabled} />
      <p className="text-xs text-muted-foreground">{tx("保存后成为手工笔记；再次运行 AI 分析会更新摘要，但保留手工笔记。")}</p>
      <Button type="button" onClick={save} disabled={disabled}>{tx("保存笔记")}</Button>
      {message ? <p role="status" className="text-sm text-muted-foreground">{message}</p> : null}
    </div>;
  }

  return <div className="space-y-3">
    <h2 className="text-xl font-black">{tx("编辑资料")}</h2>
    <label className="block text-sm font-semibold" htmlFor="video-title">{tx("标题")}</label>
    <Input id="video-title" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={500} disabled={disabled} />
    <label className="block text-sm font-semibold" htmlFor="video-description">{tx("备注")}</label>
    <Textarea id="video-description" value={description} onChange={(event) => setDescription(event.target.value)} maxLength={10000} disabled={disabled} />
    <label className="block text-sm font-semibold" htmlFor="video-tags">{tx("标签（逗号分隔，最多 20 个，每个最多 60 字）")}</label>
    <Input id="video-tags" value={tags} onChange={(event) => setTags(event.target.value)} disabled={disabled} />
    <label className="block text-sm font-semibold" htmlFor="video-category">{tx("分类")}</label>
    <Input id="video-category" value={category} onChange={(event) => setCategory(event.target.value)} maxLength={120} disabled={disabled} />
    <Button type="button" onClick={save} disabled={disabled}>{tx("保存资料")}</Button>
    {video.index_sync_error ? <SecondaryButton type="button" onClick={retryIndex} disabled={disabled}>{tx("重试知识库同步")}</SecondaryButton> : null}
    {message ? <p role="status" className="text-sm text-muted-foreground">{message}</p> : null}
  </div>;
}
