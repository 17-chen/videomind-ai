"use client";

import { useTranslator } from "@/lib/language";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, LogIn, UserPlus } from "lucide-react";
import { Button, Input } from "@/components/ui";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/supabase/config";

type AuthMode = "login" | "signup";

export function AuthForm() {
  const tx = useTranslator();
  const router = useRouter();
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    const supabase = getSupabaseBrowserClient();
    if (!supabase) {
      setError(tx("Supabase 尚未配置，当前项目仍运行在本地演示模式。"));
      return;
    }

    setLoading(true);
    try {
      const result = mode === "login"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password });

      if (result.error) {
        setError(result.error.message);
        return;
      }
      if (mode === "signup" && !result.data.session) {
        setMessage(tx("注册成功，请前往邮箱完成验证后登录。"));
        return;
      }
      router.push("/dashboard");
      router.refresh();
    } catch {
      setError(tx("认证服务暂不可用，请稍后重试。"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 rounded-full border border-border bg-muted p-1">
        {(["login", "signup"] as const).map((item) => (
          <button key={item} type="button" onClick={() => setMode(item)} className={`h-10 rounded-full text-sm font-semibold transition ${mode === item ? "bg-white shadow-sm" : "text-muted-foreground"}`}>
            {item === "login" ? tx("登录") : tx("注册")}
          </button>
        ))}
      </div>
      <form onSubmit={submit} className="space-y-3">
        <Input required type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder={tx("邮箱")} />
        <Input required minLength={6} type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(event) => setPassword(event.target.value)} placeholder={tx("密码，至少 6 位")} />
        <Button type="submit" disabled={loading || !isSupabaseConfigured} className="w-full">
          {loading ? <Loader2 size={16} className="animate-spin" /> : mode === "login" ? <LogIn size={16} /> : <UserPlus size={16} />}
          {mode === "login" ? tx("进入我的记忆空间") : tx("创建账户")}
        </Button>
      </form>
      {!isSupabaseConfigured ? <p className="text-sm leading-6 text-muted-foreground">{tx("尚未连接 Supabase。添加项目环境变量后，这里会自动启用。")}</p> : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {message ? <p className="text-sm text-foreground">{message}</p> : null}
    </div>
  );
}
