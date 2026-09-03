import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useWindowVirtualizer } from "@tanstack/react-virtual";
import type { Session, SourceFilter } from "./types";
import { useSessions } from "./hooks/useSessions";
import { usePinned } from "./hooks/usePinned";
import { useTheme } from "./hooks/useTheme";
import { sessionKey } from "./utils/format";
import { postResume } from "./api";
import { Toolbar } from "./components/Toolbar";
import { SessionCard } from "./components/SessionCard";
import { SkeletonCard } from "./components/SkeletonCard";
import { CommandPalette } from "./components/CommandPalette";
import { UsageModal } from "./components/UsageModal";

interface FilterState {
  query: string;
  source: SourceFilter;
  host: string;
}

const INITIAL_FILTER: FilterState = {
  query: "",
  source: "all",
  host: "all",
};

export default function App() {
  const { sessions, error, loading, reload } = useSessions();
  const { pinnedIds, toggle: togglePin, has: isPinned } = usePinned();
  const { theme, toggle: toggleTheme } = useTheme();

  const [filter, setFilter] = useState<FilterState>(INITIAL_FILTER);
  const [activeIdx, setActiveIdx] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);
  // Global usage modal — single instance, no per-card state.
  const [usageSession, setUsageSession] = useState<Session | null>(null);
  const [showTop, setShowTop] = useState(false);
  const { query, source, host } = filter;

  const boardRef = useRef<HTMLDivElement>(null);
  const [scrollMargin, setScrollMargin] = useState(0);

  const hosts = useMemo(
    () => Array.from(new Set(sessions.map((s) => s.host))).toSorted(),
    [sessions],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return sessions
      .filter((item) => {
        if (source !== "all" && item.source !== source) return false;
        if (host !== "all" && item.host !== host) return false;
        if (!q) return true;
        const haystack = [
          item.cwd,
          item.session_id,
          item.title,
          item.first_user,
          item.last_user,
          item.last_assistant,
        ]
          .join("\n")
          .toLowerCase();
        return haystack.includes(q);
      })
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
  }, [sessions, query, source, host, pinnedIds]);

  // Clamp activeIdx inline so we never render a stale out-of-bounds
  // selection (deriving during render avoids an extra effect commit).
  const safeActiveIdx =
    filtered.length === 0 ? 0 : Math.min(activeIdx, filtered.length - 1);

  // Measure board's offset from the top of the document so the window
  // virtualizer knows where the list starts (scrollMargin).
  useEffect(() => {
    const measure = () => {
      if (boardRef.current) {
        setScrollMargin(
          boardRef.current.getBoundingClientRect().top + window.scrollY,
        );
      }
    };
    if (!loading) measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [loading]);

  // Show back-to-top button after scrolling past the hero.
  useEffect(() => {
    const onScroll = () => setShowTop(window.scrollY > 400);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const virtualizer = useWindowVirtualizer({
    count: filtered.length,
    estimateSize: () => 300,
    overscan: 6,
    scrollMargin,
    measureElement: (el) => el.getBoundingClientRect().height,
    getItemKey: (index) => sessionKey(filtered[index]),
  });

  const scrollActiveIntoView = useCallback(
    (idx: number) => {
      virtualizer.scrollToIndex(idx, { align: "center" });
    },
    [virtualizer],
  );

  // Stable callbacks for SessionCard memo — pass index, look up item
  // inside so the callback identity never changes across renders.
  const handlePin = useCallback(
    (idx: number) => {
      const item = filtered[idx];
      if (item) togglePin(item);
    },
    [filtered, togglePin],
  );
  const handleActivate = useCallback((idx: number) => {
    setActiveIdx(idx);
  }, []);

  // Stable callback for usage chip clicks in SessionCard.
  const handleUsageOpen = useCallback((session: Session) => {
    setUsageSession(session);
  }, []);

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

      if (paletteOpen) return;
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
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [filtered, safeActiveIdx, paletteOpen, togglePin, scrollActiveIntoView]);

  const jumpToSession = useCallback(
    (item: Session) => {
      setPaletteOpen(false);
      setFilter(INITIAL_FILTER);
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
        <h1>
          Pick up
          <br />
          Where you left off.
        </h1>
        <Toolbar
          query={query}
          onQueryChange={(v) => setFilter((f) => ({ ...f, query: v }))}
          source={source}
          onSourceChange={(v) =>
            setFilter((f) => ({ ...f, source: v }))
          }
          host={host}
          onHostChange={(v) => setFilter((f) => ({ ...f, host: v }))}
          hosts={hosts}
          onRefresh={reload}
        />
      </section>

      <section ref={boardRef} className="board" aria-live="polite">
        {loading && (
          <div className="skeleton-list" aria-busy="true" aria-live="polite">
            <span className="sr-only">Loading sessions…</span>
            {Array.from({ length: 6 }, (_, i) => (
              <SkeletonCard key={i} />
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
                  key={sessionKey(item)}
                  data-index={vi.index}
                  ref={virtualizer.measureElement}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    transform: `translateY(${vi.start - scrollMargin}px)`,
                    zIndex: vi.index === safeActiveIdx ? 10 : undefined,
                  }}
                >
                  <div style={{ marginBottom: "18px" }}>
                    <SessionCard
                      session={item}
                      index={vi.index}
                      active={vi.index === safeActiveIdx}
                      pinned={isPinned(item)}
                      queryText={queryText}
                      onPin={handlePin}
                      onActivate={handleActivate}
                      onUsageOpen={handleUsageOpen}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

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

      {showTop && (
        <button
          className="back-to-top"
          type="button"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          aria-label="Back to top"
        >
          ↑
        </button>
      )}
    </main>
  );
}
