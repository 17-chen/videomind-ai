"use client";

import { useEffect, useState } from "react";
import { KeyRound, Loader2, ShieldCheck, Trash2 } from "lucide-react";
import { Button, Input, Panel, SecondaryButton } from "@/components/ui";
import { deleteAiSettings, getAiSettings, saveAiSettings } from "@/lib/api";
import { useTranslator } from "@/lib/language";
import type { AiSettings } from "@/lib/types";

export function AiSettingsForm() {
  const tx = useTranslator();
  const [current, setCurrent] = useState<AiSettings | null>(null);
  const [provider, setProvider] = useState<"deepseek" | "openai">("deepseek");
  const [model, setModel] = useState("deepseek-v4-flash");
  const [apiKey, setApiKey] = useState("");
  const [asrKey, setAsrKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    void getAiSettings().then((value) => {
      setCurrent(value);
      if (value.provider) setProvider(value.provider);
      if (value.model) setModel(value.model);
    }).catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  }, []);

  function changeProvider(value: "deepseek" | "openai") {
    setProvider(value);
    if (!current || current.provider !== value) setModel(value === "deepseek" ? "deepseek-v4-flash" : "gpt-4.1-mini");
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(""); setMessage("");
    if (current?.provider && current.provider !== provider && !apiKey.trim()) {
      setError(tx("切换服务商时请填写对应的新密钥")); return;
    }
    setBusy(true);
    try {
      const value = await saveAiSettings({ provider, model: model.trim(), ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}), ...(asrKey.trim() ? { asr_api_key: asrKey.trim() } : {}) });
      setCurrent(value); setApiKey(""); setAsrKey(""); setMessage(tx("设置已保存"));
    } catch (err) { setError(err instanceof Error ? err.message : tx("保存失败")); }
    finally { setBusy(false); }
  }

  async function remove() {
    if (!window.confirm(tx("确定删除已保存的模型与转写密钥吗？"))) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await deleteAiSettings();
      setCurrent({ provider: null, model: null, has_api_key: false, has_asr_api_key: false, demo_mode: current?.demo_mode ?? false });
      setApiKey(""); setAsrKey(""); setMessage(tx("密钥已删除"));
    } catch (err) { setError(err instanceof Error ? err.message : tx("删除失败")); }
    finally { setBusy(false); }
  }

  return <Panel className="p-6 sm:p-8">
    <div className="mb-6 flex items-start justify-between gap-3">
      <div><div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-foreground text-white"><KeyRound size={18} /></div><h2 className="text-2xl font-black">{tx("使用自己的 API Key")}</h2></div>
      <span className="rounded-full border border-border bg-white px-3 py-1 text-xs font-semibold">{current?.has_api_key ? tx("已保存") : tx("未保存")}</span>
    </div>
    <p className="mb-6 text-sm leading-7 text-muted-foreground">{tx("模型会直接使用你填写的服务商账户计费。VideoMind 不代扣费用，也不会在页面重新显示已保存的密钥。")}</p>
    {current?.demo_mode ? <p className="mb-5 rounded-[18px] border border-amber-300 bg-amber-50 p-4 text-sm leading-6 text-amber-900">{tx("当前是本地演示模式：所有访问者共用演示账户，不能保存个人密钥。请先配置 Supabase 独立登录。")}</p> : null}
    {!current && !error ? <p className="text-sm text-muted-foreground">{tx("加载设置中")}</p> : null}
    <form onSubmit={save} className="space-y-5">
      <label className="block text-sm font-semibold">{tx("服务商")}<select value={provider} onChange={(e) => changeProvider(e.target.value as "deepseek" | "openai")} className="mt-2 h-12 w-full rounded-xl border border-border bg-white px-4"><option value="deepseek">DeepSeek</option><option value="openai">OpenAI</option></select></label>
      <label className="block text-sm font-semibold">{tx("模型名称")}<Input required value={model} onChange={(e) => setModel(e.target.value)} className="mt-2" placeholder="deepseek-v4-flash" /></label>
      <label className="block text-sm font-semibold">{tx("模型 API Key")}<Input type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} className="mt-2" placeholder={tx("填写新密钥以替换，留空则不修改")} /></label>
      <p className="text-xs leading-5 text-muted-foreground">{tx("首次保存必须填写密钥。以后留空表示保持原密钥。")}</p>
      <label className="block text-sm font-semibold">{tx("OpenAI 转写 API Key（可选）")}<Input type="password" autoComplete="off" value={asrKey} onChange={(e) => setAsrKey(e.target.value)} className="mt-2" placeholder={tx("单独设置转写密钥，留空则不修改")} /></label>
      <p className="text-xs leading-5 text-muted-foreground">{tx("当视频没有字幕时，转写需要 OpenAI API Key。若模型服务商是 OpenAI，可直接使用上方的模型密钥。")}</p>
      {error ? <p role="alert" className="text-sm text-destructive">{tx(error)}</p> : null}
      {message ? <p role="status" className="flex items-center gap-2 text-sm text-emerald-700"><ShieldCheck size={16} />{message}</p> : null}
      <div className="flex flex-wrap gap-3"><Button type="submit" disabled={busy || !current || current.demo_mode}>{busy ? <Loader2 className="animate-spin" size={16} /> : <ShieldCheck size={16} />}{tx("保存设置")}</Button>{current?.has_api_key ? <SecondaryButton type="button" disabled={busy} onClick={remove}><Trash2 size={16} />{tx("删除密钥")}</SecondaryButton> : null}</div>
    </form>
  </Panel>;
}
