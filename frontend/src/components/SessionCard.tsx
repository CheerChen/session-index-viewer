import { memo } from "react";
import type { Session } from "../types";
import {
  formatRelative,
  formatTimestamp,
  headlessOrigin,
  highlight,
  sourceAccent,
  sessionKey,
} from "../utils/format";
import { postResume } from "../api";
import { MetaRow } from "./MetaRow";
import { UsageRow } from "./UsageRow";
import { AssistantSection } from "./AssistantSection";

interface SessionCardProps {
  session: Session;
  index: number;
  active: boolean;
  pinned: boolean;
  selected: boolean;
  queryText: string;
  onPin: (index: number) => void;
  onActivate: (index: number) => void;
  onConversationOpen: (session: Session) => void;
  onUsageOpen: (session: Session) => void;
  onDeleteRequest: (session: Session) => void;
  onToggleSelect: (index: number) => void;
}

function SessionCardImpl({
  session,
  index,
  active,
  pinned,
  selected,
  queryText,
  onPin,
  onActivate,
  onConversationOpen,
  onUsageOpen,
  onDeleteRequest,
  onToggleSelect,
}: SessionCardProps) {
  const accent = sourceAccent(session.source);
  const key = sessionKey(session);
  const headless = headlessOrigin(session);

  const handleOpen = async () => {
    try {
      await postResume(session);
    } catch (err) {
      console.error(err);
    }
  };

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(session.resume_command);
    } catch (err) {
      console.error(err);
    }
  };

  const classes = [
    "card",
    pinned ? "is-pinned" : "",
    active ? "is-active" : "",
    selected ? "is-selected" : "",
  ]
    .filter(Boolean)
    .join(" ");

  // Activate on plain card clicks only. Skip when the user was selecting
  // text (so copy/select works) or interacting with nested controls.
  // Avoid a full-card overlay button — it steals hover (tooltips) and
  // pointer events (text selection).
  const handleCardClick = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.closest("button, a, input, textarea, select, .usage-chip")) {
      return;
    }
    // Cmd+click is the mouse gesture for bulk-delete selection —
    // Shift would collide with text selection inside the card. The
    // card itself carries the selected visual state, no checkbox.
    if (e.metaKey && session.deletable) {
      onToggleSelect(index);
      return;
    }
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed && e.currentTarget.contains(sel.anchorNode)) {
      return;
    }
    onActivate(index);
  };

  return (
    <div
      className={classes}
      style={{ "--accent": accent } as React.CSSProperties}
      data-idx={index}
      onClick={handleCardClick}
    >
      <div className="card-side">
        <header className="card-head">
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
          <span className="card-head-actions">
            {session.deletable && (
              <button
                className="card-delete-button"
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteRequest(session);
                }}
                title="Move to Trash (x)"
                aria-label="Delete session"
              >
                <svg
                  viewBox="0 0 16 16"
                  width="13"
                  height="13"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M2.5 4h11" />
                  <path d="M6 4V2.8c0-.4.4-.8.8-.8h2.4c.4 0 .8.4.8.8V4" />
                  <path d="M4 4l.6 8.6c0 .6.5 1.4 1.1 1.4h4.6c.6 0 1.1-.8 1.1-1.4L12 4" />
                </svg>
              </button>
            )}
            <button
              className={`pin-button ${pinned ? "is-pinned" : ""}`}
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onPin(index);
              }}
              title={pinned ? "Unpin" : "Pin to top"}
              aria-label={pinned ? "Unpin session" : "Pin session to top"}
            >
              {pinned ? "★" : "☆"}
            </button>
          </span>
        </header>

        <div className="meta">
          <MetaRow label="timestamp" tooltip={formatTimestamp(session.timestamp)}>
            <div className="meta-value">
              {formatRelative(session.timestamp)}
            </div>
          </MetaRow>
          <MetaRow label="cwd" tooltip={session.cwd}>
            <div className="meta-value">{session.cwd}</div>
          </MetaRow>
          <MetaRow label="session id" tooltip={session.session_id}>
            <div className="meta-value">{session.session_id}</div>
          </MetaRow>
          {session.usage && (
            <UsageRow
              usage={session.usage}
              source={session.source}
              onOpen={() => onUsageOpen(session)}
            />
          )}
          <MetaRow label="command" tooltip={session.resume_command}>
            <div className="command-frame">
              <div className="meta-value">{session.resume_command}</div>
              <button
                className="meta-icon"
                type="button"
                onClick={handleCopy}
                title="Copy command"
                aria-label="Copy command"
              >
                ⧉
              </button>
            </div>
          </MetaRow>
        </div>

        <div className="resume-actions">
          <button
            className="toggle-button"
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              handleOpen();
            }}
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
        </div>
      </div>

      <div className="card-main">
        {session.title && (
          <h3
            className="card-title"
            dangerouslySetInnerHTML={{
              __html: highlight(session.title, queryText),
            }}
          />
        )}
        <div className="sections">
          <section className="section">
            <div className="section-title">
              <svg
                viewBox="0 0 12 12"
                width="10"
                height="10"
                fill="currentColor"
                aria-hidden="true"
              >
                <path d="M3 2L10 6L3 10Z" />
              </svg>
              Opening prompt
            </div>
            <p
              className="section-body"
              dangerouslySetInnerHTML={{
                __html: highlight(session.first_user || " ", queryText),
              }}
            />
          </section>
          <section className="section">
            <div className="section-title">
              <svg
                viewBox="0 0 12 12"
                width="10"
                height="10"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M2.5 4.5l3.5 3.5 3.5-3.5" />
              </svg>
              Last prompt
            </div>
            <p
              className="section-body"
              dangerouslySetInnerHTML={{
                __html: highlight(session.last_user || " ", queryText),
              }}
            />
          </section>
          <AssistantSection
            sessionKey={key}
            lastAssistant={session.last_assistant}
          />
        </div>
        {session.source === "devin" && (
          <div className="section-actions">
            <button
              className="toggle-button"
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onConversationOpen(session);
              }}
            >
              Show conversation
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export const SessionCard = memo(SessionCardImpl);
