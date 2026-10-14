import { memo } from "react";
import type { Session } from "../types";
import {
  formatRelative,
  formatTimestamp,
  headlessOrigin,
  highlight,
  sourceAccent,
} from "../utils/format";
import { PinIcon } from "./Icons";

// Fixed row height lets the list virtualizer skip measuring.
export const ROW_HEIGHT = 68;

interface SessionRowProps {
  session: Session;
  index: number;
  active: boolean;
  pinned: boolean;
  // Last row of the pinned group: draws the divider above unpinned rows.
  lastPinned: boolean;
  selected: boolean;
  showHost: boolean;
  // Messages in this session matching the full-text query (0 = none).
  hitCount: number;
  queryText: string;
  onActivate: (index: number) => void;
  onToggleSelect: (index: number) => void;
}

// Last path segment of the cwd: the project name at a glance.
function project(cwd: string): string {
  const parts = cwd.split("/").filter(Boolean);
  return parts[parts.length - 1] || cwd || "~";
}

function SessionRowImpl({
  session,
  index,
  active,
  pinned,
  lastPinned,
  selected,
  showHost,
  hitCount,
  queryText,
  onActivate,
  onToggleSelect,
}: SessionRowProps) {
  const headless = headlessOrigin(session);
  const title = session.title || session.first_user || session.session_id;
  const classes = [
    "row",
    active ? "is-active" : "",
    pinned ? "is-pinned" : "",
    lastPinned ? "is-last-pinned" : "",
    selected ? "is-selected" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={classes}
      style={{ "--accent": sourceAccent(session.source) } as React.CSSProperties}
      role="option"
      aria-selected={active}
      onClick={(e) => {
        // Cmd+click marks the row for bulk delete instead of opening it.
        if (e.metaKey && session.deletable) onToggleSelect(index);
        else onActivate(index);
      }}
    >
      <div className="row-title">
        {pinned && (
          <span className="row-pin" title="Pinned" aria-label="Pinned">
            <PinIcon filled size={12} />
          </span>
        )}
        <span dangerouslySetInnerHTML={{ __html: highlight(title, queryText) }} />
      </div>
      <div className="row-meta">
        <span className="row-source">{session.source}</span>
        {headless && (
          <span
            className="row-headless"
            title={`Started by automation (${headless})`}
          >
            headless
          </span>
        )}
        <span className="row-project" title={session.cwd}>
          {project(session.cwd)}
        </span>
        {showHost && <span className="row-host">{session.host}</span>}
        {session.usage && (
          <span className="row-turns" title="User turns">
            {session.usage.user_turns}t
          </span>
        )}
        {hitCount > 0 && (
          <span className="row-hits" title="Messages matching the search">
            {hitCount} {hitCount === 1 ? "hit" : "hits"}
          </span>
        )}
        <span className="row-time" title={formatTimestamp(session.timestamp)}>
          {formatRelative(session.timestamp)}
        </span>
      </div>
    </div>
  );
}

export const SessionRow = memo(SessionRowImpl);
