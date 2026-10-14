import { useCallback, useEffect, useState } from "react";
import { fetchSessions } from "../api";
import type { Session } from "../types";

// Loads sessions from /api/sessions and refetches when the tab
// regains focus — matches the common flow of running a session in
// CLI then switching back to the viewer.
export function useSessions() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await fetchSessions();
      setSessions(data.sessions);
      setTruncated(data.truncated);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const handler = () => {
      if (document.visibilityState === "visible") load();
    };
    document.addEventListener("visibilitychange", handler);
    return () => document.removeEventListener("visibilitychange", handler);
  }, [load]);

  return { sessions, truncated, error, loading, reload: load };
}
