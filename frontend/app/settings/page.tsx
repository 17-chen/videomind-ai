import { AppShell } from "@/components/app-shell";
import { AiSettingsForm } from "@/components/ai-settings-form";
import { Badge } from "@/components/ui";
import { getServerTranslator } from "@/lib/server-language";

export default async function SettingsPage() {
  const tx = await getServerTranslator();
  return <AppShell><div className="mx-auto max-w-3xl space-y-6">
    <div><Badge className="bg-white">VideoMind</Badge><h1 className="mt-4 text-5xl font-black">{tx("模型设置")}</h1><p className="mt-3 text-sm leading-7 text-muted-foreground">{tx("在这里选择语言和你自己的模型账户。")}</p></div>
    <AiSettingsForm />
  </div></AppShell>;
}
