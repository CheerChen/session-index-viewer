import type { SourceFilter, TurnsFilter } from "../types";

interface ToolbarProps {
  query: string;
  onQueryChange: (value: string) => void;
  source: SourceFilter;
  onSourceChange: (value: SourceFilter) => void;
  turns: TurnsFilter;
  onTurnsChange: (value: TurnsFilter) => void;
  onRefresh: () => void;
}

export function Toolbar({
  query,
  onQueryChange,
  source,
  onSourceChange,
  turns,
  onTurnsChange,
  onRefresh,
}: ToolbarProps) {
  return (
    <div className="toolbar">
      <div className="field">
        <svg
          className="field-icon"
          viewBox="0 0 16 16"
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <circle cx="7" cy="7" r="4.5" />
          <path d="M10.5 10.5L13.5 13.5" />
        </svg>
        <input
          type="search"
          placeholder="Search keywords"
          aria-label="Search sessions by keyword"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
        />
      </div>

      <div className="field">
        <select
          aria-label="Filter by source"
          value={source}
          onChange={(e) => onSourceChange(e.target.value as SourceFilter)}
        >
          <option value="all">All Sources</option>
          <option value="codex">Codex</option>
          <option value="claude">Claude</option>
          <option value="devin">Devin</option>
          <option value="grok">Grok</option>
          <option value="pi">Pi</option>
          <option value="copilot">Copilot</option>
          <option value="opencode">opencode</option>
        </select>
      </div>

      <div className="field">
        <select
          aria-label="Filter by user turns"
          title="Show sessions with at most this many user turns"
          value={turns}
          onChange={(e) => onTurnsChange(e.target.value as TurnsFilter)}
        >
          <option value="any">All Turns</option>
          <option value="1">≤ 1 turn</option>
          <option value="2">≤ 2 turns</option>
          <option value="3">≤ 3 turns</option>
        </select>
      </div>

      <div className="field load-field">
        <button type="button" onClick={onRefresh} aria-label="Refresh sessions">
          Refresh
        </button>
      </div>
    </div>
  );
}
