import { useEffect, useId, useMemo, useRef, useState } from "react";
import { deleteSessions, type DeleteResult } from "../api";
import type { Session } from "../types";
import { sessionKey } from "../utils/format";

interface BatchDeleteModalProps {
  sessions: Session[];
  onCancel: () => void;
  // Called with the keys that were successfully deleted; the parent
  // prunes them from the selection and reloads the list.
  onDeleted: (deletedKeys: string[]) => void;
}

const PREVIEW_COUNT = 6;

export function BatchDeleteModal({
  sessions,
  onCancel,
  onDeleted,
}: BatchDeleteModalProps) {
  const titleId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [entered, setEntered] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Items that failed stay in the modal so the user can retry or close.
  const [failed, setFailed] = useState<DeleteResult[] | null>(null);

  useEffect(() => {
    cancelRef.current?.focus();
    const raf = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !deleting) {
        event.preventDefault();
        event.stopPropagation();
        onCancel();
      }
    };
    document.addEventListener("keydown", onKey, true);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.body.style.overflow = previousOverflow;
    };
  }, [deleting, onCancel]);

  const bySource = useMemo(() => {
    const counts = new Map<string, number>();
    for (const s of sessions) {
      counts.set(s.source, (counts.get(s.source) || 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [sessions]);

  const handleDelete = async () => {
    setDeleting(true);
    setError(null);
    try {
      const { results } = await deleteSessions(sessions);
      const succeeded = results
        .filter((r) => r.ok)
        .map((r) => `${r.source}|${r.session_id}`);
      onDeleted(succeeded);
      const failures = results.filter((r) => !r.ok);
      if (failures.length === 0) {
        onCancel();
      } else {
        setFailed(failures);
        setDeleting(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete.");
      setDeleting(false);
    }
  };

  const preview = sessions.slice(0, PREVIEW_COUNT);
  const remaining = sessions.length - preview.length;

  return (
    <div
      className={`delete-confirm-backdrop ${entered ? "is-entered" : ""}`}
      role="presentation"
      onClick={() => {
        if (!deleting) onCancel();
      }}
    >
      <div
        className={`delete-confirm-modal ${entered ? "is-entered" : ""}`}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="delete-confirm-eyebrow">Delete sessions</div>
        <h2 id={titleId}>
          {failed
            ? `${failed.length} of ${sessions.length} failed`
            : `Delete ${sessions.length} sessions?`}
        </h2>
        {!failed && (
          <>
            <p className="delete-confirm-sources">
              {bySource.map(([src, n]) => `${src} × ${n}`).join(" · ")}
            </p>
            <ul className="delete-confirm-list">
              {preview.map((s) => (
                <li key={sessionKey(s)}>
                  <strong>{s.title || s.first_user || s.session_id}</strong>
                  <code>{s.session_id}</code>
                </li>
              ))}
              {remaining > 0 && (
                <li className="delete-confirm-more">
                  …and {remaining} more
                </li>
              )}
            </ul>
            <p>
              Sessions are moved to the Trash (a recovery dump for
              database-backed tools). You can restore them from there if
              needed.
            </p>
          </>
        )}
        {failed && (
          <ul className="delete-confirm-list">
            {failed.map((f) => (
              <li key={`${f.source}|${f.session_id}`}>
                <strong>
                  {f.source} · {f.session_id}
                </strong>
                <code>{f.error || "unknown error"}</code>
              </li>
            ))}
          </ul>
        )}
        {error && <div className="delete-confirm-error">{error}</div>}
        <div className="delete-confirm-actions">
          <button
            ref={cancelRef}
            className="delete-confirm-cancel"
            type="button"
            disabled={deleting}
            onClick={onCancel}
          >
            {failed ? "Close" : "Cancel"}
          </button>
          {!failed && (
            <button
              className="delete-confirm-submit"
              type="button"
              disabled={deleting}
              onClick={() => void handleDelete()}
            >
              {deleting
                ? "Deleting…"
                : `Move ${sessions.length} to Trash`}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
