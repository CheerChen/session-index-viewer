import type { Session, SessionMessages } from "./types";

export async function fetchSessions(limit = 1000): Promise<Session[]> {
  const res = await fetch(`/api/sessions?limit=${limit}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
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
