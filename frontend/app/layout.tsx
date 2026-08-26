import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VideoMind AI",
  description: "把收藏但没时间看的视频，自动转化为个人知识资产。"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
