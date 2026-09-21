import {
  Fragment,
  memo,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import type { Session, SessionMessage } from "../types";
import { useSessionMessages } from "../hooks/useSessionMessages";
import { formatTimestamp, sourceAccent } from "../utils/format";
import { renderMarkdown } from "../utils/markdown";

// Renders one page of a session's conversation in a modal, so the
// virtualized card list never hosts a multi-thousand-line DOM. The
// backend only returns user/assistant messages; pagination keeps the
// modal itself bounded too.
const MessageBody = memo(function MessageBody({
  message,
}: {
  message: SessionMessage;
}) {
  const markdownHtml = useMemo(
    () =>
      message.role === "assistant" && message.content
        ? renderMarkdown(message.content)
        : "",
    [message.content, message.role],
  );

  if (message.role === "assistant") {
    return (
      <>
        {message.thinking && (
          <details className="conv-details">
            <summary>Thinking</summary>
            <div className="conv-thinking">{message.thinking}</div>
          </details>
        )}
        {markdownHtml && (
          <div
            className="section-body markdown"
            dangerouslySetInnerHTML={{ __html: markdownHtml }}
          />
        )}
      </>
    );
  }
  return <p className="conv-user-text">{message.content}</p>;
});

interface SessionConversationProps {
  session: Session;
  onClose: () => void;
  onDeleteRequest: (session: Session) => void;
}

function Conversation({
  session,
  onClose,
  onDeleteRequest,
}: SessionConversationProps) {
  const { data, loading, error, page, setPage } = useSessionMessages(session);
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const [entered, setEntered] = useState(false);
  const accent = sourceAccent(session.source);

  useEffect(() => {
    panelRef.current?.focus();
    const raf = requestAnimationFrame(() => setEntered(true));
    return () => {
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener("keydown", onKey, true);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  const backdropClass = ["conv-modal-backdrop", entered ? "is-entered" : ""]
    .filter(Boolean)
    .join(" ");
  const panelClass = ["conv-modal", entered ? "is-entered" : ""]
    .filter(Boolean)
    .join(" ");

  const goPrev = () => setPage((p) => Math.max(1, p - 1));
  const goNext = () =>
    setPage((p) => (data ? Math.min(p + 1, data.pages) : p + 1));

  return (
    <div className={backdropClass} role="presentation" onClick={onClose}>
      <div
        ref={panelRef}
        className={panelClass}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        style={{ "--accent": accent } as React.CSSProperties}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="conv-modal-head">
          <div className="conv-modal-head-text">
            <div className="conv-modal-eyebrow">Conversation</div>
            <h2 id={titleId} className="conv-modal-title">
              <span className="conv-modal-title-text">
                {session.title || session.session_id}
              </span>
            </h2>
            <div className="conv-modal-meta">
              <span className="source-pill" style={{ color: accent }}>
                {session.source}
              </span>
              <span className="conv-modal-session">{session.session_id}</span>
            </div>
          </div>
          <div className="conv-modal-head-actions">
            {session.deletable && (
              <button
                type="button"
                className="delete-session-trigger"
                onClick={() => onDeleteRequest(session)}
              >
                Delete session
              </button>
            )}
            <button
              type="button"
              className="usage-modal-close"
              onClick={onClose}
              aria-label="Close conversation"
            >
              ✕
            </button>
          </div>
        </header>

        {error && !data ? (
          <div className="conv-status">Failed to load: {error}</div>
        ) : loading && !data ? (
          <div className="conv-status">Loading conversation…</div>
        ) : data && data.messages.length === 0 ? (
          <div className="conv-status">No messages.</div>
        ) : (
          data && (
            <div className="conv-list">
              {data.messages.map((message) => (
                <Fragment key={message.node_id}>
                  {message.role === "assistant" &&
                    !!message.tool_call_count && (
                      <div className="conv-tool-omitted">
                        省略了 {message.tool_call_count} 条 Tool 调用
                      </div>
                    )}
                  <div className={`conv-msg conv-msg--${message.role}`}>
                    <div className="conv-msg-meta">
                      <span className="conv-role">{message.role}</span>
                      {message.created_at && (
                        <span className="conv-time">
                          {formatTimestamp(message.created_at)}
                        </span>
                      )}
                    </div>
                    <MessageBody message={message} />
                  </div>
                </Fragment>
              ))}
            </div>
          )
        )}

        {data && data.messages.length > 0 && (
          <footer className="conv-modal-foot">
            <span className="conv-count">{data.total} messages</span>
            <div className="conv-pager">
              <button
                className="toggle-button"
                type="button"
                disabled={page <= 1}
                onClick={goPrev}
              >
                ‹ Prev
              </button>
              <span className="conv-page">
                Page {page} / {data.pages}
              </span>
              <button
                className="toggle-button"
                type="button"
                disabled={page >= data.pages}
                onClick={goNext}
              >
                Next ›
              </button>
            </div>
          </footer>
        )}
      </div>
    </div>
  );
}

export const SessionConversation = memo(Conversation);