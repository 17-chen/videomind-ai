import Link from "next/link";
import { getServerTranslator } from "@/lib/server-language";
import { BrainCircuit } from "lucide-react";
import { AuthForm } from "@/components/auth-form";
import { LanguageSwitch } from "@/components/language-switch";
import { Panel } from "@/components/ui";

export default async function AuthPage() {
  const tx = await getServerTranslator();
  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-md space-y-6">
        <div className="flex justify-end"><LanguageSwitch /></div>
        <Link href="/" className="mx-auto flex w-fit items-center gap-3 text-lg font-black">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-foreground text-primary-foreground"><BrainCircuit size={20} /></span>
          VideoMind
        </Link>
        <Panel className="p-7 sm:p-8">
          <h1 className="text-3xl font-black">{tx("你的 AI 记忆空间")}</h1>
          <p className="mb-7 mt-2 text-sm leading-6 text-muted-foreground">{tx("登录后，每条视频、笔记和对话只属于你的知识库。")}</p>
          <AuthForm />
        </Panel>
      </div>
    </main>
  );
}
