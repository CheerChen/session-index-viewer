# Changelog

## 2026-10-14

### Full-text search
- **Search reaches into conversations.** The search box still filters
  metadata as you type; after a pause the query also runs against every
  session's prompts and replies, and sessions matching only there join
  the list with a hit count. Results keep time order.
- **Index.** SQLite FTS5 with the trigram tokenizer (the default
  tokenizer finds no CJK at all), stored under
  `~/.cache/session-index-viewer/`, built in the background at startup
  and synced incrementally by each session's last-activity timestamp.
  Terms under three characters fall back to LIKE. Terms are ANDed per
  message; quotes keep phrases.
- **Matches in the detail pane** are marked with the CSS Custom
  Highlight API (no DOM changes to rendered markdown); the pane jumps to
  the newest match and `n` / `N` step through them. Matches in pages not
  loaded yet are counted with a load-earlier link.

### Two-pane layout
- **List + detail replace the card stack.** Sessions are compact rows
  (title, source, headless flag, project, turns, age); the active one
  opens in a right-hand pane with its actions, usage and conversation.
  `j`/`k` drive both, with a short debounce and a client cache so
  sweeping the list doesn't refetch. The pane opens on the newest page
  and loads earlier pages in place without jumping. Under 900px the
  pane slides over the list. The conversation modal (Devin only, `e`)
  is gone.
- **Pinning reads as pinning.** The star is now a pushpin (outline /
  filled), pinned rows carry a pin glyph and a faint wash, and a heavier
  rule closes the pinned group. Delete is an icon-only trash button.
- **Conversations for every source.** `/api/session` now reads Claude,
  Codex, Pi, Grok, Copilot and opencode as well as Devin, through one
  shared projection: user turns plus one folded reply per turn, tool
  calls counted. Turns that only ran tools (e.g. aborted) are kept so
  the count stays visible. `page=0` returns the newest page.
- **Lighter list, no silent cut-off.** `/api/sessions` drops
  `last_assistant` (about 60% of the payload; ~2.4 MB → ~1.1 MB here)
  and search no longer covers replies. The 1,000-session cap that
  silently hid the oldest sessions is now a 10,000 safety cap reported
  via `X-Sessions-Truncated` and a note at the end of the list.
- **Codex prompts and subagents.** `codex_vscode` prompts are unwrapped
  from their IDE-context preamble, AGENTS.md and guardian-review
  injections no longer pose as the opening prompt, and Codex subagent
  sessions (guardian reviews, spawned threads) are flagged headless.
- Session files are always read whole; the head+tail window was always
  followed by a full re-read anyway.

### Headless sessions
- **Every source except Pi now flags headless sessions**, not just
  Codex. The verdict is made per source adapter (`headless` on each
  session; `origin` carries the tooltip detail); see the README for the
  signal each tool leaves on disk. Pi's `-p` runs are indistinguishable
  from TUI sessions and stay unflagged.
- **Origin filter.** A toolbar select (`Interactive` / `All Origins` /
  `Headless Only`) hides headless sessions by default and remembers the
  choice in localStorage. An empty search that only failed because of
  the filter offers a one-click "Show N headless matches"; jumping to a
  hidden session from the command palette widens the filter.
- **Grok headless one-shots are shown and flagged** instead of being
  dropped by the scanner, so they follow the same filter and can be
  bulk-deleted.

## 2026-09-21

### Session cleanup
- **Delete any session via Trash.** The per-session delete flow (trash
  button on each card, `x` on the active card, or the conversation
  modal) now covers every source, not just Devin. File/dir-backed
  sessions (Claude, Codex, Pi, Grok) are moved into `~/.Trash`
  wholesale; database-backed ones (Copilot, opencode, Devin) first dump
  all session-linked rows to a JSON archive in Trash, then remove them
  (Devin still goes through `devin rm` for its own bookkeeping). When
  `~/.Trash` is unavailable the API reports it and the UI hides the
  delete affordances (`deletable` flag on each session).
- **Turns filter.** A toolbar select (`≤ 1/2/3` user turns) surfaces
  low-activity sessions for pruning — e.g. Pi's one-shot
  "reply with just: ok" noise. Sessions without usage data are
  excluded from turn-capped views rather than guessed at.
- **Multi-select bulk delete.** `m` or ⌘-click marks a card for bulk
  deletion (the card itself carries the selected state — accent border
  and wash, no checkbox). With a non-empty selection a bottom-centre
  action bar offers Select all shown / Move to Trash / Clear; `x`
  deletes the selection instead of the active card, and `Esc` clears
  it. A batch confirmation modal shows the per-source breakdown and a
  title preview, then posts to a new `/api/sessions/delete` endpoint
  that runs each item through the same per-source adapters and returns
  per-session results — partial failures stay listed in the modal for
  retry.

### Codex origins
- **Headless badge.** Codex sessions launched by automation
  (`codex exec`, ACP harnesses, MCP-driven runs) now show a filled
  amber `headless` pill next to the source pill, with the raw
  `session_meta.originator` value in the tooltip. Interactive
  `codex-tui` / `codex_vscode` sessions stay unmarked; unknown
  originators are not assumed headless.
- **Plugin recommendations no longer masquerade as prompts.** Codex
  injects a `<recommended_plugins>` marketplace listing as a user-role
  message at session start; it is now skipped like the other
  boilerplate prefixes so `first_user` reflects the real prompt.

### UI
- **Hero simplified.** The headline and host filter are gone; the
  toolbar is now a single row of search / source / turns / refresh.

### Fixes
- **opencode resume works.** `/api/resume` previously validated every
  non-Devin session id against the hex pattern, which opencode's
  `ses_…` ids could never satisfy. Resume and delete now share a
  per-source id pattern.

### Terminal launch
- **Ghostty resume opens a tab in the running instance.** Resume now uses
  Ghostty's AppleScript dictionary (≥ 1.3, `new tab in front window` /
  `new window` with `initial input`) instead of `open -na`, which spawned a
  throwaway second instance with its own Dock icon. The command runs in a
  normal login shell so the tab stays usable after it exits. Ghostty < 1.3
  still falls back to `open -na`. First use triggers a one-time macOS
  automation permission prompt for the process hosting the server.

## 2026-09-08

### Fixes
- **Devin CLI detection covers `~/.local/bin`.** The Devin executable
  lookup now checks `~/.local/bin/devin` in addition to `PATH`,
  Homebrew, and `/usr/local/bin`, so session deletion works when Devin
  CLI was installed via its own installer instead of a package manager.

## 2026-09-04

### Devin conversations
- **In-app conversation viewer.** Devin session cards can now be opened
  in a conversation modal backed by a new paginated `/api/session`
  endpoint (50 messages per page, up to 200). The backend follows the
  active `message_nodes` chain and collapses consecutive assistant tool
  activity into a single entry with a call count, so large sessions stay
  responsive.
- **Session deletion.** The conversation modal offers a confirmed
  delete flow that calls a new delete API, removes the session via the
  Devin CLI, and evicts the stale cache entry so the card disappears on
  the next refresh.

## 2026-09-03

### Theme
- **Dark mode.** A theme toggle (sun / moon icon) in the hero's
  top-right corner switches between the original warm light palette
  and a new dark palette. The choice persists in `localStorage` and
  falls back to the OS `prefers-color-scheme` on first visit. An
  inline script in `index.html` applies the stored theme before first
  paint to avoid a flash. All surface, text, border, and shadow
  colours were refactored into semantic CSS variables under `:root`
  and flipped as a set via `[data-theme="dark"]`; agent identity
  colours (Claude / Codex / Devin / …) stay the same in both themes.

### Fixes
- **Virtualizer height cache keyed by index, not session.**
  `useWindowVirtualizer` was using the default `getItemKey` (index),
  so the per-item height cache was keyed by position, not by session
  identity. When `filtered` reordered (pin/unpin, session updates, new
  arrivals), the cached heights shifted to the wrong items and
  produced visible gaps and overlaps between cards. The cache is now
  keyed by `sessionKey(filtered[index])` so heights follow their
  content across reorders.

## 2026-08-17

### Sources
- **Three new session sources.** Added adapters for **Pi**
  (`~/.pi/agent/sessions/*/*.jsonl`, per-file JSONL like Codex),
  **Copilot CLI** (`~/.copilot/session-store.db`, SQLite `turns` +
  `assistant_usage_events`), and **opencode**
  (`~/.local/share/opencode/opencode.db`, SQLite `message`/`part`).
  Each is searchable, resumable (`pi --session`, `copilot --resume`,
  `opencode --session`), and reports token/tool usage. Source filter,
  accent colours, and context-window limits updated accordingly.

### Performance
- **Skeleton loading state.** The board now renders shimmer placeholder
  cards while `/api/sessions` is in flight instead of a blank
  "Loading…" line, so the first paint no longer looks frozen (respects
  `prefers-reduced-motion`).
- **Faster Devin refetch.** The Devin adapter only re-aggregates
  `message_nodes` usage for sessions whose `last_activity_at` changed.
  A warm `/api/sessions` (e.g. on tab refocus) dropped from ~0.65s to
  ~0.09s with no change to reported usage.

## 2026-08-11

### Performance
- **Virtual list.** The session board now uses
  [`@tanstack/react-virtual`](https://tanstack.com/virtual) window
  virtualization — only visible cards are mounted in the DOM, and
  variable card heights are measured per-item via `measureElement`.
  `SessionCard` is wrapped in `React.memo` with stable `useCallback`
  props so unchanged cards skip re-render. This keeps the UI smooth
  with the new 1000-session limit.
- **Window-scrolled layout.** Switched from a container-scrolled
  virtualizer to `useWindowVirtualizer` so the hero section scrolls
  away naturally with the page instead of being frozen at the top.
  A back-to-top button (↑) appears in the bottom-right after
  scrolling past the hero.

### Usage modal
- **Context pressure bar.** The usage modal now shows a colour-coded
  progress bar comparing peak context tokens against the model's
  context window limit. Green (< 60 %), yellow (60–85 %), red
  (≥ 85 %). Model → limit mapping is prefix-based and covers Claude,
  GPT/Codex, GLM, Gemini, Grok, DeepSeek, Kimi, and SWE variants,
  including 1 M-context variants.
- **Global single-instance modal.** `UsageModal` state was lifted
  from per-card to the App level so multiple modals can no longer
  stack on top of each other.

### Session limit
- **100 → 1000 sessions.** The default and maximum scan limits were
  raised from 100 / 500 to 1000 / 1000 across the backend
  (`siv/config.py`), frontend API client, and legacy shell indexer.
  This makes older sessions searchable without sacrificing
  responsiveness (virtual list + mtime/size cache).

### Terminal launch
- **Clean Ghostty windows.** Ghostty is now launched with
  `--window-save-state=never` so new terminal instances don't
  inherit the layout of previously closed windows.
