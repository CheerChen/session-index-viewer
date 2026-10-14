import type { Session, SessionMessages } from "./types";

// The server returns every session up to its safety cap and flags when
// the cap cut the list short.
export async function fetchSessions(): Promise<{
  sessions: Session[];
  truncated: boolean;
}> {
  const res = await fetch("/api/sessions", { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return {
    sessions: await res.json(),
    truncated: res.headers.get("X-Sessions-Truncated") === "1",
  };
}

export async function fetchSessionMessages(
  session: Pick<Session, "source" | "session_id">,
  page: number,
  pageSize = 50,
): Promise<SessionMessages> {
  const qs = new URLSearchParams({
    source: session.source,
    session_id: session.session_id,
    page: String(page),
    page_size: String(pageSize),
  });
  const res = await fetch(`/api/session?${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function deleteSession(
  session: Pick<Session, "source" | "session_id">,
): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch("/api/session/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source: session.source,
      session_id: session.session_id,
      confirm_session_id: session.session_id,
    }),
  });
  const result = (await res.json()) as { ok: boolean; error?: string };
  if (!res.ok) throw new Error(result.error || `HTTP ${res.status}`);
  return result;
}

export interface DeleteResult {
  source: string;
  session_id: string;
  ok: boolean;
  error?: string;
}

export async function deleteSessions(
  sessions: Pick<Session, "source" | "session_id">[],
): Promise<{ ok: boolean; results: DeleteResult[]; error?: string }> {
  const res = await fetch("/api/sessions/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      confirmed: true,
      sessions: sessions.map((s) => ({
        source: s.source,
        session_id: s.session_id,
      })),
    }),
  });
  const result = (await res.json()) as {
    ok: boolean;
    results: DeleteResult[];
    error?: string;
  };
  if (!res.ok) throw new Error(result.error || `HTTP ${res.status}`);
  return result;
}

export async function postResume(
  session: Pick<Session, "source" | "session_id" | "cwd">,
): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch("/api/resume", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source: session.source,
      session_id: session.session_id,
      cwd: session.cwd,
    }),
  });
  return res.json();
}

export interface SearchHit {
  count: number;
  // 0-based positions in the session's folded message list.
  positions: number[];
}

export interface SearchResult {
  hits: Record<string, SearchHit>;
  terms: string[];
  indexing: boolean;
}

export async function fetchSearch(
  q: string,
  signal?: AbortSignal,
): Promise<SearchResult> {
  const res = await fetch(`/api/search?${new URLSearchParams({ q })}`, {
    cache: "no-store",
    signal,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
