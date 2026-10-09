"use client";

import { useTranslator } from "@/lib/language";
import { AlertCircle, RotateCcw } from "lucide-react";
import { Button, Panel } from "@/components/ui";

export function ApiErrorPanel() {
  const tx = useTranslator();
  return (
    <Panel className="mx-auto max-w-2xl p-8 sm:p-10">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
        <AlertCircle size={22} />
      </div>
      <h1 className="mt-6 text-2xl font-black">{tx("暂时无法加载视频资料")}</h1>
      <p className="mt-3 text-sm leading-7 text-muted-foreground">
        {tx("视频服务暂时没有响应。请检查后端服务或登录状态，然后重试。已有资料不会因为这次加载失败而消失。")}
      </p>
      <Button type="button" onClick={() => window.location.reload()} className="mt-6">
        <RotateCcw size={16} />{tx("重新加载")}
      </Button>
    </Panel>
  );
}
