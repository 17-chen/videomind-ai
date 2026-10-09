"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogIn, LogOut } from "lucide-react";
import { useTranslator } from "@/lib/language";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/supabase/config";

const desktopClassName = "hidden h-11 items-center gap-2 rounded-full border border-border bg-white px-4 text-sm font-semibold text-foreground shadow-panel transition hover:-translate-y-0.5 hover:shadow-float sm:inline-flex";
const mobileClassName = "flex h-12 flex-col items-center justify-center gap-1 rounded-md text-[11px] text-muted-foreground md:hidden";

export function AuthStatus({ mobile = false }: { mobile?: boolean }) {
  const router = useRouter();
  const tx = useTranslator();
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    const supabase = getSupabaseBrowserClient();
    if (!supabase) return;
    void supabase.auth.getSession().then(({ data }) => setSignedIn(Boolean(data.session)));
    const { data } = supabase.auth.onAuthStateChange((_event, session) => setSignedIn(Boolean(session)));
    return () => data.subscription.unsubscribe();
  }, []);

  async function signOut() {
    const supabase = getSupabaseBrowserClient();
    if (!supabase) return;
    const { error } = await supabase.auth.signOut();
    if (error) return;
    setSignedIn(false);
    router.replace("/auth");
    router.refresh();
  }

  const className = mobile ? mobileClassName : desktopClassName;
  if (!isSupabaseConfigured || !signedIn) {
    return <Link href="/auth" className={className}><LogIn size={16} />{tx("登录")}</Link>;
  }
  return <button type="button" onClick={signOut} className={className}><LogOut size={16} />{tx("退出")}</button>;
}
