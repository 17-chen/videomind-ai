import { AppShell } from "@/components/app-shell";
import { getServerTranslator } from "@/lib/server-language";
import { Badge } from "@/components/ui";
import { ChatClient } from "@/components/chat-client";
import { Sparkles } from "lucide-react";

export default async function ChatPage() {
  const tx = await getServerTranslator();
  return (
    <AppShell>
      <div className="mx-auto max-w-5xl space-y-7">
        <div className="text-center">
          <Badge className="border-accent/30 bg-white text-foreground">
            <Sparkles size={13} />
            {tx("Ask Memory")}
          </Badge>
          <h1 className="mx-auto mt-5 max-w-3xl text-5xl font-black leading-[0.95] tracking-normal sm:text-7xl">
            {tx("Chat with your video memory")}
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-sm leading-7 text-muted-foreground">
            {tx("询问过去收藏过的视频，VideoMind 会从你的记忆库里找回相关片段，再生成中文回答。")}
          </p>
        </div>
        <ChatClient />
      </div>
    </AppShell>
  );
}
