import "server-only";
import { cookies } from "next/headers";
import { type Language, translate } from "@/lib/i18n";

export async function getServerTranslator() {
  const cookieStore = await cookies();
  const language: Language = cookieStore.get("videomind_language")?.value === "en" ? "en" : "zh";
  return (source: string) => translate(language, source);
}

export async function getServerLanguage(): Promise<Language> {
  const cookieStore = await cookies();
  return cookieStore.get("videomind_language")?.value === "en" ? "en" : "zh";
}
