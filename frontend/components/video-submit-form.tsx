"use client";

import { useTranslator } from "@/lib/language";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Link2, Loader2, Plus } from "lucide-react";
import { Button, Input, Textarea } from "@/components/ui";
import { createVideo } from "@/lib/api";
import { extractShareTitle, extractVideoUrl } from "@/lib/video-url";

export function VideoSubmitForm() {
  const tx = useTranslator();
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const videoUrl = extractVideoUrl(url);
    if (!videoUrl) {
      setError(tx("没有识别到有效链接，请粘贴以 http:// 或 https:// 开头的视频地址。"));
      return;
    }
    setLoading(true);
    try {
      const video = await createVideo({
        url: videoUrl,
        title: title || undefined,
        description: description || undefined,
        tags: tags
          .split(/[,\s，]+/)
          .map((tag) => tag.trim())
          .filter(Boolean)
      });
      router.refresh();
      router.push(`/videos/${video.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : tx("提交失败"));
    } finally {
      setLoading(false);
    }
  }

  function onPaste(event: React.ClipboardEvent<HTMLInputElement>) {
    const pastedText = event.clipboardData.getData("text");
    const videoUrl = extractVideoUrl(pastedText);
    if (!videoUrl) return;

    event.preventDefault();
    setUrl(videoUrl);
    setError("");
    if (!title) {
      setTitle(extractShareTitle(pastedText, videoUrl));
    }
  }

  function onUrlChange(value: string) {
    const videoUrl = extractVideoUrl(value);
    const isShareText = Boolean(videoUrl) && value.trim() !== videoUrl && /\s/.test(value.trim());
    if (!videoUrl || !isShareText) {
      setUrl(value);
      return;
    }

    setUrl(videoUrl);
    setError("");
    if (!title) {
      setTitle(extractShareTitle(value, videoUrl));
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <div className="relative">
        <Link2 className="pointer-events-none absolute left-3 top-2.5 text-muted-foreground" size={17} />
        <Input
          required
          value={url}
          onChange={(event) => onUrlChange(event.target.value)}
          onPaste={onPaste}
          inputMode="url"
          className="pl-9"
          placeholder={tx("粘贴 Bilibili 或抖音视频链接")}
        />
      </div>
      <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder={tx("标题，可选")} />
      <Input value={tags} onChange={(event) => setTags(event.target.value)} placeholder={tx("标签，用空格或逗号分隔")} />
      <Textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder={tx("备注，可选")} />
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <Button type="submit" disabled={loading} className="w-full">
        {loading ? <Loader2 className="animate-spin" size={16} /> : <Plus size={16} />}
        {tx("添加到我的记忆")}
      </Button>
    </form>
  );
}
