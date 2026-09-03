import { useEffect, useState } from "react";
import { fetchSessionMessages } from "../api";
import { sessionKey } from "../utils/format";
import type { Session, SessionMessages } from "../types";

const PAGE_SIZE = 50;

// Module-scope page cache keyed by "session#page" so a card that unmounts
// when it scrolls out of the virtualizer restores its pages without
// re-requesting them on the way back into view.
const pageCache = new Map<string, SessionMessages>();

export function useSessionMessages(session: Session) {
  const key = sessionKey(session);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<SessionMessages | null>(() => {
    const hit = pageCache.get(`${key}#1`);
    return hit ?? null;
  });
  const [loading, setLoading] = useState(data === null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const cacheKey = `${key}#${page}`;
    const hit = pageCache.get(cacheKey);
    if (hit) {
      setData(hit);
      setError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchSessionMessages(
      { source: session.source, session_id: session.session_id },
      page,
      PAGE_SIZE,
    )
      .then((next) => {
        if (cancelled) return;
        pageCache.set(cacheKey, next);
        setData(next);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [key, page, session.source, session.session_id]);

  return { data, loading, error, page, setPage };
}