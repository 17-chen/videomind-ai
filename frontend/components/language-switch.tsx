"use client";
import { useLanguage } from "@/lib/language";

export function LanguageSwitch() {
  const { language, setLanguage } = useLanguage();
  return <div className="inline-flex items-center rounded-full border border-border bg-white p-1 text-xs font-semibold shadow-panel" aria-label="Language / 语言">
    <button type="button" lang="zh-CN" onClick={() => setLanguage("zh")} className={`rounded-full px-3 py-2 ${language === "zh" ? "bg-foreground text-white" : "text-muted-foreground"}`} aria-pressed={language === "zh"}>中文</button>
    <button type="button" lang="en" onClick={() => setLanguage("en")} className={`rounded-full px-3 py-2 ${language === "en" ? "bg-foreground text-white" : "text-muted-foreground"}`} aria-pressed={language === "en"}>EN</button>
  </div>;
}
