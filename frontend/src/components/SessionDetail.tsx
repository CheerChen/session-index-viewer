import { Fragment, memo, useLayoutEffect, useMemo, useRef } from "react";
import type { Session, SessionMessage } from "../types";
import { PAGE_SIZE, useConversation } from "../hooks/useConversation";
import { useSearchHighlight } from "../hooks/useSearchHighlight";
import type { SearchHit } from "../api";
import {
  formatRelative,
  formatTimestamp,
  headlessOrigin,
  sourceAccent,
} from "../utils/format";
import { renderMarkdown } from "../utils/markdown";
import { postResume } from "../api";
import { UsageChip } from "./UsageChip";
import { PinIcon, TrashIcon } from "./Icons";

// Right-hand pane: the active session's header (identity, resume, usage,
// pin, delete) over its conversation. The backend returns user turns and
// one folded reply per turn; the pane opens on the newest page and loads
// earlier pages on demand.
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

interface SessionDetailProps {
  session: Session | null;
  // Full-text query terms and this session's hits (null: none / no query).
  searchTerms: string[];
  searchHit: SearchHit | null;
  pinned: boolean;
  onPin: (session: Session) => void;
  onUsageOpen: (session: Session) => void;
  onDeleteRequest: (session: Session) => void;
  // Narrow screens show the pane as an overlay; this closes it.
  onClose: () => void;
}

function Detail({
  session,
  searchTerms,
  searchHit,
  pinned,
  onPin,
  onUsageOpen,
  onDeleteRequest,
  onClose,
}: SessionDetailProps) {
  const conv = useConversation(session);
  const bodyRef = useRef<HTMLDivElement>(null);
  const scrolledKey = useRef("");
  // Distance from the bottom, captured before prepending earlier pages so
  // the reader's position doesn't jump.
  const prependAnchor = useRef<number | null>(null);
  const count = conv.data?.messages.length ?? 0;
  const highlight = useSearchHighlight(
    bodyRef,
    searchHit ? searchTerms : [],
    `${conv.key}#${count}`,
    conv.key,
  );

  useLayoutEffect(() => {
    const el = bodyRef.current;
    if (!el || !conv.data) return;
    if (prependAnchor.current !== null) {
      el.scrollTop = el.scrollHeight - prependAnchor.current;
      prependAnchor.current = null;
    } else if (scrolledKey.current !== conv.key) {
      el.scrollTop = el.scrollHeight;
      scrolledKey.current = conv.key;
    }
  }, [conv.key, conv.data, count]);

  if (!session) {
    return <div className="detail-empty">No session selected.</div>;
  }

  const accent = sourceAccent(session.source);
  const headless = headlessOrigin(session);
  const data = conv.data;

  // Hits in pages not loaded yet (positions are 0-based over the whole
  // conversation; loaded pages start at firstPage).
  const firstLoaded = data ? (data.firstPage - 1) * PAGE_SIZE : 0;
  const earlierHits =
    searchHit?.positions.filter((p) => p < firstLoaded).length ?? 0;

  const loadEarlier = () => {
    const el = bodyRef.current;
    if (el) prependAnchor.current = el.scrollHeight - el.scrollTop;
    void conv.loadEarlier();
  };

  return (
    <div
      className="detail"
      style={{ "--accent": accent } as React.CSSProperties}
    >
      <header className="detail-head">
        <div className="detail-head-top">
          <button
            type="button"
            className="detail-back"
            onClick={onClose}
            aria-label="Back to list"
          >
            ‹ Sessions
          </button>
          <span className="pill-group">
            <span className="source-pill" style={{ color: accent }}>
              {session.source}
            </span>
            {headless && (
              <span
                className="headless-pill"
                title={`Started by automation (${headless})`}
              >
                headless
              </span>
            )}
            <span className="host-pill">{session.host}</span>
          </span>
          <span className="detail-head-actions">
            <button
              className={`pin-button ${pinned ? "is-pinned" : ""}`}
              type="button"
              onClick={() => onPin(session)}
              title={pinned ? "Unpin (p)" : "Pin to top (p)"}
              aria-label={pinned ? "Unpin session" : "Pin session to top"}
              aria-pressed={pinned}
            >
              <PinIcon filled={pinned} size={15} />
            </button>
            {session.deletable && (
              <button
                type="button"
                className="delete-session-trigger"
                onClick={() => onDeleteRequest(session)}
                title="Move to Trash (x)"
                aria-label="Delete session"
              >
                <TrashIcon size={15} />
              </button>
            )}
          </span>
        </div>
        <h2 className="detail-title">
          {session.title || session.first_user || session.session_id}
        </h2>
        <dl className="detail-meta">
          <div>
            <dt>cwd</dt>
            <dd title={session.cwd}>{session.cwd}</dd>
          </div>
          <div>
            <dt>session</dt>
            <dd title={session.session_id}>{session.session_id}</dd>
          </div>
          <div>
            <dt>updated</dt>
            <dd title={formatTimestamp(session.timestamp)}>
              {formatRelative(session.timestamp)}
            </dd>
          </div>
        </dl>
        <div className="detail-actions">
          <button
            className="toggle-button"
            type="button"
            onClick={() => void postResume(session).catch(console.error)}
            title="Open in Terminal (Enter)"
          >
            <svg
              viewBox="0 0 16 16"
              width="13"
              height="13"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M4.5 5l3 3-3 3" />
              <line x1="8.5" y1="11.5" x2="12" y2="11.5" />
            </svg>
            Open in Terminal
          </button>
          <button
            className="toggle-button"
            type="button"
            onClick={() =>
              void navigator.clipboard
                .writeText(session.resume_command)
                .catch(console.error)
            }
            title={`Copy: ${session.resume_command} (c)`}
          >
            ⧉ Copy command
          </button>
          {session.usage && (
            <UsageChip
              usage={session.usage}
              source={session.source}
              onOpen={() => onUsageOpen(session)}
            />
          )}
        </div>
      </header>

      {searchHit && data && (highlight.count > 0 || earlierHits > 0) && (
        <div className="detail-search" role="status">
          {highlight.count > 0 && (
            <>
              <span>
                Match {highlight.current + 1 || "–"} / {highlight.count}
              </span>
              <button
                type="button"
                className="toggle-button"
                onClick={() => highlight.step(-1)}
                title="Previous match (N)"
              >
                ↑
              </button>
              <button
                type="button"
                className="toggle-button"
                onClick={() => highlight.step(1)}
                title="Next match (n)"
              >
                ↓
              </button>
            </>
          )}
          {earlierHits > 0 && (
            <button
              type="button"
              className="empty-action"
              onClick={loadEarlier}
              disabled={conv.loadingEarlier}
            >
              {earlierHits} more {earlierHits === 1 ? "message" : "messages"}{" "}
              match in earlier pages · Load earlier
            </button>
          )}
        </div>
      )}

      <div ref={bodyRef} className="detail-body">
        {conv.error && !data ? (
          <div className="conv-status">Failed to load: {conv.error}</div>
        ) : !data ? (
          <div className="conv-status">Loading conversation…</div>
        ) : data.messages.length === 0 ? (
          <div className="conv-status">No messages.</div>
        ) : (
          <div className="conv-list">
            {data.firstPage > 1 && (
              <button
                type="button"
                className="toggle-button conv-earlier"
                onClick={loadEarlier}
                disabled={conv.loadingEarlier}
              >
                {conv.loadingEarlier
                  ? "Loading…"
                  : `Load earlier (${data.total - data.messages.length} more)`}
              </button>
            )}
            {data.messages.map((message) => (
              <Fragment key={message.node_id}>
                {message.role === "assistant" && !!message.tool_call_count && (
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
        )}
      </div>
    </div>
  );
}

export const SessionDetail = memo(Detail);
