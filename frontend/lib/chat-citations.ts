export type AnswerPart = { text: string; sourceIndex?: number };

/** Link only plain numbered references present in this answer's sources.
 * Answers remain plain text; this is deliberately not a Markdown renderer.
 */
export function splitAnswerCitations(answer: string, sourceCount: number): AnswerPart[] {
  const parts: AnswerPart[] = [];
  let textStart = 0;
  let codeMarker = "";
  let codeWidth = 0;
  let fenced = false;
  let lineStart = 0;
  const citation = /\[([1-9]\d*)\]/y;
  for (let i = 0; i < answer.length; i++) {
    const char = answer[i];
    if (char === "\n") lineStart = i + 1;
    if (char === "`" || char === "~") {
      let end = i + 1;
      while (answer[end] === char) end++;
      const width = end - i;
      const atLineStart = i - lineStart <= 3 && /^ {0,3}$/.test(answer.slice(lineStart, i));
      if (!codeMarker && (char === "`" || (width >= 3 && atLineStart))) {
        codeMarker = char;
        codeWidth = width;
        fenced = width >= 3 && atLineStart;
      } else if (char === codeMarker) {
        const lineEnd = fenced && atLineStart ? answer.indexOf("\n", end) : -1;
        const closes = fenced
          ? atLineStart && width >= codeWidth && /^[ \t]*$/.test(answer.slice(end, lineEnd < 0 ? answer.length : lineEnd))
          : width === codeWidth;
        if (closes) codeMarker = "";
      }
      i = end - 1;
      continue;
    }
    if (codeMarker) continue;
    // Escaped brackets are literal. Numbered Markdown links stay plain text;
    // no model-supplied URL is made clickable. Adjacent [1][2] are citations.
    if (char === "\\") { i++; continue; }
    if (char !== "[") continue;
    citation.lastIndex = i;
    const match = citation.exec(answer);
    if (!match) continue;
    const end = i + match[0].length;
    if (answer[end] === "(") {
      let depth = 1;
      i = end;
      while (++i < answer.length && depth) {
        if (answer[i] === "\\") i++;
        else if (answer[i] === "(") depth++;
        else if (answer[i] === ")") depth--;
        if (answer[i] === "\n") lineStart = i + 1;
      }
      i--;
      continue;
    }
    const sourceIndex = Number(match[1]) - 1;
    if (!Number.isSafeInteger(sourceIndex) || sourceIndex >= sourceCount) continue;
    if (i > textStart) parts.push({ text: answer.slice(textStart, i) });
    parts.push({ text: match[0], sourceIndex });
    textStart = end;
    i = end - 1;
  }
  if (textStart < answer.length) parts.push({ text: answer.slice(textStart) });
  return parts;
}
