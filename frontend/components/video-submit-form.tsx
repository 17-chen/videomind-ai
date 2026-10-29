"use client";

import { useTranslator } from "@/lib/language";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { FileUp, Link2, Loader2, Plus } from "lucide-react";
import { Button, Input, Textarea } from "@/components/ui";
import { createVideo, getUploadPolicy, uploadVideo, type UploadPolicy } from "@/lib/api";
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
  const [uploadPolicy, setUploadPolicy] = useState<UploadPolicy | null>(null);
  const [uploadPolicyError, setUploadPolicyError] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    getUploadPolicy().then(setUploadPolicy).catch(() => setUploadPolicyError(true));
  }, []);

  async function onUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setUploadError("");
    if (!uploadFile || !uploadPolicy) return;
    const extension = `.${uploadFile.name.split(".").at(-1)?.toLowerCase() ?? ""}`;
    if (!uploadPolicy.extensions.includes(extension)) {
      setUploadError(tx("不支持这种视频格式"));
      return;
    }
    if (uploadFile.size > uploadPolicy.max_bytes) {
      setUploadError(tx("视频文件超过上传限制"));
      return;
    }
    setUploading(true);
    try {
      const video = await uploadVideo(uploadFile, uploadTitle);
      router.refresh();
      router.push(`/videos/${video.id}`);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : tx("上传失败"));
    } finally {
      setUploading(false);
    }
  }

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
    <div className="space-y-6">
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
    <form onSubmit={onUpload} className="space-y-3 border-t border-border pt-5">
      <p className="text-sm font-semibold">{tx("或上传本地视频")}</p>
      <Input type="file" accept={uploadPolicy?.extensions.join(",") ?? ".mp4,.webm,.mkv,.mov,.m4v"} onChange={(event) => { setUploadFile(event.target.files?.[0] ?? null); setUploadError(""); }} />
      <Input value={uploadTitle} maxLength={500} onChange={(event) => setUploadTitle(event.target.value)} placeholder={tx("上传标题，可选")} />
      {uploadPolicy ? <p className="text-xs text-muted-foreground">{tx("最大文件大小")}：{Math.round(uploadPolicy.max_bytes / 1024 / 1024)} MB · {uploadPolicy.extensions.join("、")}</p> : null}
      {uploadPolicy ? <p className="text-xs text-muted-foreground">{tx("个人文件存储总量上限")}：{Math.round(uploadPolicy.max_user_storage_bytes / 1024 / 1024)} MB · {tx("包括视频、音频、转写和笔记")}</p> : null}
      {uploadPolicyError ? <p className="text-sm text-destructive">{tx("无法读取上传限制，请稍后重试")}</p> : null}
      {uploadError ? <p className="text-sm text-destructive">{uploadError}</p> : null}
      <Button type="submit" disabled={uploading || !uploadFile || !uploadPolicy} className="w-full">
        {uploading ? <Loader2 className="animate-spin" size={16} /> : <FileUp size={16} />}
        {uploading ? tx("上传中，请稍候") : tx("上传到我的记忆")}
      </Button>
    </form>
    </div>
  );
}
