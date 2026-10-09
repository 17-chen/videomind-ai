const URL_PATTERN = /https?:\/\/[^\s<>'"，。；]+/i;
const TRAILING_PUNCTUATION = /[)\]}>）】》」』、，。！？；：]+$/;

export function extractVideoUrl(value: string): string | null {
  const match = value.match(URL_PATTERN);
  if (!match) return null;

  const candidate = match[0].replace(TRAILING_PUNCTUATION, "");
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}

export function extractShareTitle(value: string, videoUrl: string): string {
  return value
    .replace(videoUrl, "")
    .replace(/复制打开[^\n]*/g, "")
    .replace(/https?:\/\/\S+/g, "")
    .trim()
    .slice(0, 500);
}
