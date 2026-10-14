import { useEffect, useState } from "react";
import { fetchSearch, type SearchResult } from "../api";

// Full-text queries go to the server once typing pauses; the metadata
// filter in App keeps reacting on every keystroke meanwhile.
const DEBOUNCE_MS = 250;

export function useSearch(query: string): SearchResult | null {
  const q = query.trim();
  const [state, setState] = useState<{ q: string; result: SearchResult } | null>(
    null,
  );

  useEffect(() => {
    if (!q) return;
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      fetchSearch(q, ctrl.signal)
        .then((result) => setState({ q, result }))
        .catch((err) => {
          if (err?.name !== "AbortError") console.error(err);
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [q]);

  // A result for an older query would mark the wrong sessions.
  return q && state?.q === q ? state.result : null;
}
