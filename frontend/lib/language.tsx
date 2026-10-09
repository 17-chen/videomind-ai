"use client";

import { createContext, useContext, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { type Language, translate } from "@/lib/i18n";
export type { Language } from "@/lib/i18n";
const LanguageContext = createContext<{ language: Language; setLanguage: (value: Language) => void }>({ language: "zh", setLanguage: () => {} });

export function LanguageProvider({ initialLanguage, children }: { initialLanguage: Language; children: React.ReactNode }) {
  const router = useRouter();
  const [language, setState] = useState<Language>(initialLanguage);
  const value = useMemo(() => ({ language, setLanguage: (next: Language) => {
    document.cookie = `videomind_language=${next}; Path=/; Max-Age=31536000; SameSite=Lax`;
    document.documentElement.lang = next === "zh" ? "zh-CN" : "en";
    setState(next);
    router.refresh();
  } }), [language, router]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() { return useContext(LanguageContext); }
export function useTranslator() {
  const { language } = useLanguage();
  return (source: string) => translate(language, source);
}
