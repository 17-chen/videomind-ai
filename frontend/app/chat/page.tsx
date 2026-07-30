import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui";
import { ChatClient } from "@/components/chat-client";

export default function ChatPage() {
  return (
    <AppShell>
      <div className="mx-auto max-w-4xl space-y-6">
        <div>
          <Badge className="bg-white">视频问答</Badge>
          <h1 className="mt-3 text-3xl font-semibold tracking-normal">视频知识库问答</h1>
          <p className="mt-2 text-sm text-muted-foreground">询问过去收藏过的视频，系统会检索相关内容并用中文回答。</p>
        </div>
        <ChatClient />
      </div>
    </AppShell>
  );
}
