import type { Metadata } from "next";
import "./globals.css";
import { LanguageProvider } from "@/lib/language";
import { getServerLanguage } from "@/lib/server-language";

export const metadata: Metadata = {
  title: "VideoMind AI",
  description: "把收藏但没时间看的视频，自动转化为个人知识资产。"
};

export default async function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  const language = await getServerLanguage();
  return (
    <html lang={language === "zh" ? "zh-CN" : "en"} data-scroll-behavior="smooth">
      <body suppressHydrationWarning><LanguageProvider initialLanguage={language}>{children}</LanguageProvider></body>
    </html>
  );
}
