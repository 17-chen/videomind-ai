"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Link2, Loader2, Plus } from "lucide-react";
import { Button, Input, Textarea } from "@/components/ui";
import { createVideo } from "@/lib/api";

export function VideoSubmitForm() {
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
    setLoading(true);
    try {
      const video = await createVideo({
        url,
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
      setError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <div className="relative">
        <Link2 className="pointer-events-none absolute left-3 top-2.5 text-muted-foreground" size={17} />
        <Input
          required
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          className="pl-9"
          placeholder="粘贴 Bilibili 或抖音视频链接"
        />
      </div>
      <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="标题，可选" />
      <Input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="标签，用空格或逗号分隔" />
      <Textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="备注，可选" />
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <Button type="submit" disabled={loading} className="w-full">
        {loading ? <Loader2 className="animate-spin" size={16} /> : <Plus size={16} />}
        添加到我的记忆
      </Button>
    </form>
  );
}
