import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type {
  OriginFilter,
  Session,
  SourceFilter,
  TurnsFilter,
} from "./types";
import { useSessions } from "./hooks/useSessions";
import { useSearch } from "./hooks/useSearch";
import type { SearchHit } from "./api";
import { usePinned } from "./hooks/usePinned";
import { useTheme } from "./hooks/useTheme";
import { sessionKey } from "./utils/format";
import { postResume } from "./api";
import { Toolbar } from "./components/Toolbar";
import { ROW_HEIGHT, SessionRow } from "./components/SessionRow";
import { SkeletonRow } from "./components/SkeletonRow";
import { SessionDetail } from "./components/SessionDetail";
import { CommandPalette } from "./components/CommandPalette";
import { UsageModal } from "./components/UsageModal";
import { DeleteSessionModal } from "./components/DeleteSessionModal";
import { BatchDeleteModal } from "./components/BatchDeleteModal";

interface FilterState {
  query: string;
  source: SourceFilter;
  turns: TurnsFilter;
  origin: OriginFilter;
}

const INITIAL_FILTER: FilterState = {
  query: "",
  source: "all",
  turns: "any",
  origin: "interactive",
};

// The origin choice is a per-viewer preference, so it survives reloads.
// Storage can be unavailable (private window, blocked site data).
const ORIGIN_STORAGE_KEY = "originFilter";
const ORIGIN_VALUES: readonly OriginFilter[] = ["interactive", "all", "headless"];

function loadOrigin(): OriginFilter {
  try {
    const v = localStorage.getItem(ORIGIN_STORAGE_KEY);
    if (v && (ORIGIN_VALUES as readonly string[]).includes(v)) {
      return v as OriginFilter;
    }
  } catch {
    // fall through to the default
  }
  return INITIAL_FILTER.origin;
}

function saveOrigin(value: OriginFilter) {
  try {
    localStorage.setItem(ORIGIN_STORAGE_KEY, value);
  } catch {
    // preference just won't persist
  }
}

function matchesOrigin(item: Session, origin: OriginFilter): boolean {
  if (origin === "all") return true;
  return origin === "headless" ? !!item.headless : !item.headless;
}

// Everything except the origin filter; the empty state reuses this to
// count matches the origin filter is hiding. A query matches either the
// session's metadata (instant, client-side) or its conversation text
// (server full-text hits, arriving once typing pauses).
function matchesRest(
  item: Session,
  source: SourceFilter,
  turns: TurnsFilter,
  q: string,
  hits: Record<string, SearchHit> | null,
): boolean {
  if (source !== "all" && item.source !== source) return false;
  // Sessions without usage can't be classified — exclude them
  // from turn-capped views rather than guessing.
  if (turns !== "any" && (!item.usage || item.usage.user_turns > Number(turns)))
    return false;
  if (!q) return true;
  const haystack = [
    item.cwd,
    item.session_id,
    item.title,
    item.first_user,
    item.last_user,
  ]
    .join("\n")
    .toLowerCase();
  return haystack.includes(q) || !!hits?.[sessionKey(item)];
}

export default function App() {
  const { sessions, truncated, error, loading, reload } = useSessions();
  const { pinnedIds, toggle: togglePin, has: isPinned } = usePinned();
  const { theme, toggle: toggleTheme } = useTheme();

  const [filter, setFilter] = useState<FilterState>(() => ({
    ...INITIAL_FILTER,
    origin: loadOrigin(),
  }));
  const [activeIdx, setActiveIdx] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);
  // Narrow screens stack the panes; the detail pane then opens as an
  // overlay on row activation. Ignored by the wide layout.
  const [detailOpen, setDetailOpen] = useState(false);
  const [deleteSession, setDeleteSession] = useState<Session | null>(null);
  // Multi-select for bulk delete — keyed by source|session_id so it
  // survives filtering, pinning reorders, and virtualization.
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [batchDelete, setBatchDelete] = useState<Session[] | null>(null);
  // Global usage modal — single instance, no per-card state.
  const [usageSession, setUsageSession] = useState<Session | null>(null);
  const { query, source, turns, origin } = filter;
  const search = useSearch(query);
  const hits = search?.hits ?? null;

  const listRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return sessions
      .filter(
        (item) =>
          matchesOrigin(item, origin) &&
          matchesRest(item, source, turns, q, hits),
      )
      .sort((a, b) => {
        // Pinned sessions float above the rest; within each group,
        // newest first.
        const ap = pinnedIds.has(sessionKey(a)) ? 1 : 0;
        const bp = pinnedIds.has(sessionKey(b)) ? 1 : 0;
        if (ap !== bp) return bp - ap;
        const left = new Date(a.timestamp).getTime() || 0;
        const right = new Date(b.timestamp).getTime() || 0;
        return right - left;
      });
  }, [sessions, query, source, turns, origin, hits, pinnedIds]);

  // Matches the origin filter alone is hiding — only computed when
  // nothing is shown, to offer a one-click switch.
  const hiddenByOrigin = useMemo(() => {
    if (filtered.length > 0 || origin === "all") return 0;
    const q = query.trim().toLowerCase();
    return sessions.filter((item) =>
      matchesRest(item, source, turns, q, hits),
    ).length;
  }, [filtered.length, sessions, query, source, turns, origin, hits]);

  const setOrigin = useCallback((value: OriginFilter) => {
    saveOrigin(value);
    setFilter((f) => ({ ...f, origin: value }));
  }, []);

  // Clamp activeIdx inline so we never render a stale out-of-bounds
  // selection (deriving during render avoids an extra effect commit).
  const safeActiveIdx =
    filtered.length === 0 ? 0 : Math.min(activeIdx, filtered.length - 1);

  const activeSession = filtered[safeActiveIdx] ?? null;
  // Host labels only earn row space when sessions come from more than
  // one machine (synced histories).
  const multiHost = useMemo(
    () => new Set(sessions.map((s) => s.host)).size > 1,
    [sessions],
  );

  const virtualizer = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => listRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
    getItemKey: (index) => sessionKey(filtered[index]),
  });

  const scrollActiveIntoView = useCallback(
    (idx: number) => {
      virtualizer.scrollToIndex(idx, { align: "auto" });
    },
    [virtualizer],
  );

  // Stable callbacks for SessionRow memo — pass index, look up item
  // inside so the callback identity never changes across renders.
  const handleActivate = useCallback((idx: number) => {
    setActiveIdx(idx);
    setDetailOpen(true);
  }, []);

  const handleDeleteRequest = useCallback((session: Session) => {
    if (session.deletable) setDeleteSession(session);
  }, []);
  const handleDeleteCancel = useCallback(() => setDeleteSession(null), []);
  const handleDeleted = useCallback(() => {
    setDeleteSession(null);
    void reload();
  }, [reload]);

  // Stable callback for the usage chip in the detail pane.
  const handleUsageOpen = useCallback((session: Session) => {
    setUsageSession(session);
  }, []);

  const handleToggleSelect = useCallback(
    (idx: number) => {
      const item = filtered[idx];
      if (!item?.deletable) return;
      const key = sessionKey(item);
      setSelected((prev) => {
        const next = new Set(prev);
        if (next.has(key)) next.delete(key);
        else next.add(key);
        return next;
      });
    },
    [filtered],
  );
  const selectAllShown = useCallback(() => {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const s of filtered) {
        if (s.deletable) next.add(sessionKey(s));
      }
      return next;
    });
  }, [filtered]);
  const clearSelection = useCallback(() => setSelected(new Set()), []);
  const openBatchDelete = useCallback(() => {
    // Resolve against the full session list, not `filtered` — selection
    // deliberately persists across filter changes.
    const items = sessions.filter(
      (s) => s.deletable && selected.has(sessionKey(s)),
    );
    if (items.length > 0) setBatchDelete(items);
  }, [sessions, selected]);
  const handleBatchDeleted = useCallback(
    (deletedKeys: string[]) => {
      setSelected((prev) => {
        const next = new Set(prev);
        for (const k of deletedKeys) next.delete(k);
        return next;
      });
      void reload();
    },
    [reload],
  );

  // Keyboard navigation: j/k move, Enter opens, c copies resume cmd,
  // p pins, u opens usage, Cmd+K toggles palette. Ignored while typing
  // in inputs or when the palette is open. Single-letter shortcuts must
  // not fire with modifiers — otherwise Cmd/Ctrl+C steals the browser
  // copy of selected text.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
        return;
      }

      if (paletteOpen || deleteSession || batchDelete || usageSession) return;
      // Leave Cmd/Ctrl/Alt combos to the browser (copy, paste, print…).
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIdx((i) => {
          const next = Math.min(i + 1, filtered.length - 1);
          if (next !== i) setTimeout(() => scrollActiveIntoView(next), 0);
          return next;
        });
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIdx((i) => {
          const next = Math.max(i - 1, 0);
          if (next !== i) setTimeout(() => scrollActiveIntoView(next), 0);
          return next;
        });
      } else if (e.key === "Enter") {
        e.preventDefault();
        const item = filtered[safeActiveIdx];
        if (item) void postResume(item);
      } else if (e.key === "c") {
        e.preventDefault();
        const item = filtered[safeActiveIdx];
        if (item) void navigator.clipboard.writeText(item.resume_command);
      } else if (e.key === "p") {
        e.preventDefault();
        const item = filtered[safeActiveIdx];
        if (item) togglePin(item);
      } else if (e.key === "u") {
        e.preventDefault();
        const item = filtered[safeActiveIdx];
        if (item?.usage) setUsageSession(item);
      } else if (e.key === "m") {
        e.preventDefault();
        handleToggleSelect(safeActiveIdx);
      } else if (e.key === "x") {
        e.preventDefault();
        if (selected.size > 0) {
          openBatchDelete();
        } else {
          const item = filtered[safeActiveIdx];
          if (item?.deletable) setDeleteSession(item);
        }
      } else if (e.key === "Escape") {
        if (selected.size > 0) {
          e.preventDefault();
          clearSelection();
        } else if (detailOpen) {
          e.preventDefault();
          setDetailOpen(false);
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [
    filtered,
    safeActiveIdx,
    paletteOpen,
    deleteSession,
    batchDelete,
    usageSession,
    detailOpen,
    selected,
    togglePin,
    scrollActiveIntoView,
    handleToggleSelect,
    openBatchDelete,
    clearSelection,
  ]);

  const jumpToSession = useCallback(
    (item: Session) => {
      setPaletteOpen(false);
      // Keep the origin choice unless it would hide the target.
      setFilter((f) => ({
        ...INITIAL_FILTER,
        origin: matchesOrigin(item, f.origin) ? f.origin : "all",
      }));
      // Defer the index lookup until after the filter clears.
      requestAnimationFrame(() => {
        const idx = filtered.findIndex(
          (s) =>
            s.source === item.source && s.session_id === item.session_id,
        );
        if (idx >= 0) {
          setActiveIdx(idx);
          setTimeout(() => scrollActiveIntoView(idx), 0);
        }
      });
    },
    [filtered, scrollActiveIntoView],
  );

  const queryText = query.trim();

  return (
    <main className="shell">
      <section className="hero">
        <div className="eyebrow">Session Index Viewer</div>
        <button
          className="theme-toggle"
          type="button"
          onClick={toggleTheme}
          aria-label={
            theme === "dark" ? "Switch to light theme" : "Switch to dark theme"
          }
          title={theme === "dark" ? "Light theme" : "Dark theme"}
        >
          {theme === "dark" ? (
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
            </svg>
          ) : (
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
          )}
        </button>
        <Toolbar
          query={query}
          onQueryChange={(v) => setFilter((f) => ({ ...f, query: v }))}
          source={source}
          onSourceChange={(v) =>
            setFilter((f) => ({ ...f, source: v }))
          }
          turns={turns}
          onTurnsChange={(v) => setFilter((f) => ({ ...f, turns: v }))}
          origin={origin}
          onOriginChange={setOrigin}
          onRefresh={reload}
        />
      </section>

      <div className="workspace">
        <section
          ref={listRef}
          className="list-pane"
          role="listbox"
          aria-label="Sessions"
          aria-live="polite"
        >
          {loading && (
            <div aria-busy="true">
              <span className="sr-only">Loading sessions…</span>
              {Array.from({ length: 10 }, (_, i) => (
                <SkeletonRow key={i} />
              ))}
            </div>
          )}
          {error && (
            <div className="empty">
              Failed to load /api/sessions. Is server.py running?
            </div>
          )}
          {!loading && !error && filtered.length === 0 && (
            <div className="empty">
              No matching sessions. Try a different query.
              {hiddenByOrigin > 0 && (
                <>
                  {" "}
                  <button
                    type="button"
                    className="empty-action"
                    onClick={() => setOrigin("all")}
                  >
                    Show {hiddenByOrigin}{" "}
                    {origin === "interactive" ? "headless" : "interactive"}{" "}
                    {hiddenByOrigin === 1 ? "match" : "matches"}
                  </button>
                </>
              )}
            </div>
          )}
          {!loading && !error && filtered.length > 0 && (
            <div
              style={{
                height: `${virtualizer.getTotalSize()}px`,
                position: "relative",
              }}
            >
              {virtualizer.getVirtualItems().map((vi) => {
                const item = filtered[vi.index];
                return (
                  <div
                    key={vi.key}
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      width: "100%",
                      height: `${ROW_HEIGHT}px`,
                      transform: `translateY(${vi.start}px)`,
                    }}
                  >
                    <SessionRow
                      session={item}
                      index={vi.index}
                      active={vi.index === safeActiveIdx}
                      pinned={isPinned(item)}
                      lastPinned={
                        isPinned(item) &&
                        !!filtered[vi.index + 1] &&
                        !isPinned(filtered[vi.index + 1])
                      }
                      selected={selected.has(sessionKey(item))}
                      showHost={multiHost}
                      hitCount={hits?.[sessionKey(item)]?.count ?? 0}
                      queryText={queryText}
                      onActivate={handleActivate}
                      onToggleSelect={handleToggleSelect}
                    />
                  </div>
                );
              })}
            </div>
          )}
          {search?.indexing && (
            <div className="list-notice" role="status">
              Building the search index; conversation matches may be
              incomplete.
            </div>
          )}
          {truncated && (
            <div className="list-notice" role="status">
              Showing the newest {sessions.length} sessions; older ones are
              not loaded.
            </div>
          )}
        </section>

        <section className={`detail-pane ${detailOpen ? "is-open" : ""}`}>
          <SessionDetail
            session={activeSession}
            searchTerms={search?.terms ?? []}
            searchHit={
              activeSession ? (hits?.[sessionKey(activeSession)] ?? null) : null
            }
            pinned={activeSession ? isPinned(activeSession) : false}
            onPin={togglePin}
            onUsageOpen={handleUsageOpen}
            onDeleteRequest={handleDeleteRequest}
            onClose={() => setDetailOpen(false)}
          />
        </section>
      </div>

      {paletteOpen && (
        <CommandPalette
          sessions={sessions}
          onJump={jumpToSession}
          onClose={() => setPaletteOpen(false)}
        />
      )}

      {usageSession && (
        <UsageModal
          session={usageSession}
          onClose={() => setUsageSession(null)}
        />
      )}

      {deleteSession && (
        <DeleteSessionModal
          session={deleteSession}
          onCancel={handleDeleteCancel}
          onDeleted={handleDeleted}
        />
      )}

      {batchDelete && (
        <BatchDeleteModal
          sessions={batchDelete}
          onCancel={() => setBatchDelete(null)}
          onDeleted={handleBatchDeleted}
        />
      )}

      {selected.size > 0 && (
        <div className="selection-bar" role="toolbar" aria-label="Selection">
          <span
            className="selection-count"
            title="m or ⌘click toggles a row · Esc clears"
          >
            {selected.size} selected
          </span>
          <button type="button" onClick={selectAllShown}>
            Select all shown
          </button>
          <button
            type="button"
            className="selection-bar-delete"
            onClick={openBatchDelete}
          >
            Move to Trash
          </button>
          <button type="button" onClick={clearSelection}>
            Clear
          </button>
        </div>
      )}
    </main>
  );
}
