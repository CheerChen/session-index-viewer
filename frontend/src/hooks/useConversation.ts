import { useCallback, useEffect, useState } from "react";
import { fetchSessionMessages } from "../api";
import { sessionKey } from "../utils/format";
import type { Session, SessionMessage } from "../types";

export const PAGE_SIZE = 50;
// j/k can sweep through many rows; only fetch once the cursor rests.
const DEBOUNCE_MS = 150;
const CACHE_LIMIT = 50;

export interface Conversation {
  messages: SessionMessage[];
  total: number;
  // Earliest page loaded so far; pages are 1-based, oldest first.
  firstPage: number;
}

// Keyed by session + its timestamp, so a session that gained turns since
// (the list refetches on tab focus) misses the cache and reloads.
const cache = new Map<string, Conversation>();

function remember(key: string, value: Conversation) {
  cache.delete(key);
  cache.set(key, value);
  if (cache.size > CACHE_LIMIT) {
    cache.delete(cache.keys().next().value as string);
  }
}

export function useConversation(session: Session | null) {
  const key = session ? `${sessionKey(session)}@${session.timestamp}` : "";
  // Depend on identity strings, not the object: every list refetch hands
  // out new Session objects for unchanged sessions.
  const source = session?.source ?? "";
  const sessionId = session?.session_id ?? "";
  const [state, setState] = useState<{
    key: string;
    data: Conversation | null;
    error: string | null;
  }>({ key: "", data: null, error: null });
  const [loadingEarlier, setLoadingEarlier] = useState(false);

  useEffect(() => {
    if (!key) return;
    const hit = cache.get(key);
    if (hit) {
      setState({ key, data: hit, error: null });
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      // Page 0 asks the server for the last (newest) page.
      fetchSessionMessages({ source, session_id: sessionId }, 0, PAGE_SIZE)
        .then((res) => {
          if (cancelled) return;
          const data = {
            messages: res.messages,
            total: res.total,
            firstPage: res.page,
          };
          remember(key, data);
          setState({ key, data, error: null });
        })
        .catch((err) => {
          if (cancelled) return;
          setState({
            key,
            data: null,
            error: err instanceof Error ? err.message : "Failed to load",
          });
        });
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [key, source, sessionId]);

  const current = state.key === key ? state : null;

  const loadEarlier = useCallback(async () => {
    const data = current?.data;
    if (!data || data.firstPage <= 1 || loadingEarlier) return;
    setLoadingEarlier(true);
    try {
      const res = await fetchSessionMessages(
        { source, session_id: sessionId },
        data.firstPage - 1,
        PAGE_SIZE,
      );
      const next = {
        messages: [...res.messages, ...data.messages],
        total: data.total,
        firstPage: res.page,
      };
      remember(key, next);
      setState((s) => (s.key === key ? { key, data: next, error: null } : s));
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingEarlier(false);
    }
  }, [current?.data, key, loadingEarlier, source, sessionId]);

  return {
    key,
    data: current?.data ?? null,
    error: current?.error ?? null,
    loading: !!key && !current,
    loadingEarlier,
    loadEarlier,
  };
}
