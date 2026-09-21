import { useEffect, useId, useRef, useState } from "react";
import { deleteSession } from "../api";
import type { Session } from "../types";

interface DeleteSessionModalProps {
  session: Session;
  onCancel: () => void;
  onDeleted: () => void;
}

export function DeleteSessionModal({
  session,
  onCancel,
  onDeleted,
}: DeleteSessionModalProps) {
  const titleId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [entered, setEntered] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const handleDelete = async () => {
    setDeleting(true);
    setError(null);
    try {
      await deleteSession(session);
      onDeleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete session.");
      setDeleting(false);
    }
  };

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
        <div className="delete-confirm-eyebrow">
          Delete {session.source} session
        </div>
        <h2 id={titleId}>Delete this session?</h2>
        <div className="delete-confirm-session">
          <strong>{session.title || session.session_id}</strong>
          <code>{session.session_id}</code>
        </div>
        <p>
          The session's data is moved to the Trash (a recovery dump for
          database-backed tools). You can restore it from there if needed.
        </p>
        {error && <div className="delete-confirm-error">{error}</div>}
        <div className="delete-confirm-actions">
          <button
            ref={cancelRef}
            className="delete-confirm-cancel"
            type="button"
            disabled={deleting}
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            className="delete-confirm-submit"
            type="button"
            disabled={deleting}
            onClick={() => void handleDelete()}
          >
            {deleting ? "Deleting…" : "Move to Trash"}
          </button>
        </div>
      </div>
    </div>
  );
}
