// ASCII identifiers stay whole; punctuation and CJK separate English words.
export function searchPattern(term: string, substring = false): RegExp {
  const literal = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(
    substring ? literal : `(?<![A-Za-z0-9_])${literal}(?![A-Za-z0-9_])`,
    "gi",
  );
}

export function matchesText(text: string, query: string, substring = false): boolean {
  return searchPattern(query, substring).test(text);
}
