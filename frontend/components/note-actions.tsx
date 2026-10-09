"use client";

import { useState } from "react";
import { Check, Copy, Download } from "lucide-react";
import { useTranslator } from "@/lib/language";
import { SecondaryButton } from "@/components/ui";

export function NoteActions({ title, content }: { title: string; content: string }) {
  const tx = useTranslator();
  const [message, setMessage] = useState("");

  async function copy() {
    try {
      await navigator.clipboard.writeText(content);
      setMessage(tx("笔记已复制"));
    } catch {
      setMessage(tx("复制失败，请手动选择笔记内容"));
    }
  }

  function download() {
    const filename = `${title.replace(/[\\/:*?"<>|\x00-\x1f]/g, "-").trim().slice(0, 80) || "video-note"}.md`;
    const url = URL.createObjectURL(new Blob([content], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setMessage(tx("笔记已下载"));
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <SecondaryButton type="button" onClick={copy}><Copy size={16} />{tx("复制笔记")}</SecondaryButton>
      <SecondaryButton type="button" onClick={download}><Download size={16} />{tx("下载 Markdown")}</SecondaryButton>
      {message ? <span role="status" className="inline-flex items-center gap-1 text-xs text-muted-foreground"><Check size={14} />{message}</span> : null}
    </div>
  );
}
