// Formatting helpers shared across components. Kept pure (no DOM) so
// they can be unit-tested and reused in the command palette.

const RELATIVE_FORMATTER = new Intl.RelativeTimeFormat("en", {
  numeric: "auto",
});

// en-GB gives 24h DMY ("12 Jun 2026, 19:19") regardless of the
// viewer's system locale. Hoisted to module scope so the formatter
// is built once, not on every call.
const TIMESTAMP_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  year: "numeric",
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatTimestamp(value: string): string {
  if (!value) return "Unknown time";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return TIMESTAMP_FORMATTER.format(date);
}

export function formatRelative(value: string): string {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const seconds = (date.getTime() - Date.now()) / 1000;
  const abs = Math.abs(seconds);
  if (abs < 60)
    return RELATIVE_FORMATTER.format(Math.round(seconds), "second");
  if (abs < 3600)
    return RELATIVE_FORMATTER.format(Math.round(seconds / 60), "minute");
  if (abs < 86400)
    return RELATIVE_FORMATTER.format(Math.round(seconds / 3600), "hour");
  if (abs < 86400 * 7)
    return RELATIVE_FORMATTER.format(Math.round(seconds / 86400), "day");
  if (abs < 86400 * 30)
    return RELATIVE_FORMATTER.format(Math.round(seconds / 86400 / 7), "week");
  if (abs < 86400 * 365)
    return RELATIVE_FORMATTER.format(Math.round(seconds / 86400 / 30), "month");
  return RELATIVE_FORMATTER.format(
    Math.round(seconds / 86400 / 365),
    "year",
  );
}

// Compact token count: 1234 -> "1.2k", 1500000 -> "1.5M".
export function formatTokens(n: number): string {
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "k";
  return String(n);
}

// Human-readable duration for a number of seconds.
export function formatDuration(s: number): string {
  if (!s || s < 1) return "0s";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${sec}s`;
  return `${sec}s`;
}

export function escapeHtml(text: unknown): string {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

// Truncate long machine-generated text (tool results, system context)
// that would otherwise blow up the conversation DOM when expanded.
export function clipText(text: string, max = 600): string {
  if (!text || text.length <= max) return text;
  return `${text.slice(0, max)}… (+${text.length - max} chars)`;
}

// Wrap occurrences of `query` in <mark> for search highlighting.
// The input text is escaped first so the mark tags are the only HTML.
export function highlight(text: string, query: string): string {
  const safe = escapeHtml(text || " ");
  if (!query) return safe;
  const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const regex = new RegExp(`(${escapedQuery})`, "ig");
  return safe.replace(regex, "<mark>$1</mark>");
}

export function sourceAccent(source: string): string {
  if (source === "claude") return "var(--claude)";
  if (source === "devin") return "var(--devin)";
  if (source === "grok") return "var(--grok)";
  if (source === "pi") return "var(--pi)";
  if (source === "copilot") return "var(--copilot)";
  if (source === "opencode") return "var(--opencode)";
  return "var(--codex)";
}

export function sessionKey(session: {
  source: string;
  session_id: string;
}): string {
  return `${session.source}|${session.session_id}`;
}

// Codex originators that mean "started by automation, not a person":
// codex_exec = `codex exec`, acpx = ACP clients (batch harnesses like
// backpass), codex_cli_rs + source:mcp = MCP-driven. codex-tui and
// codex_vscode are interactive and get no badge; unknown values stay
// unbadged so a future interactive frontend isn't mislabeled.
const HEADLESS_ORIGINS = new Set(["codex_exec", "acpx", "codex_cli_rs"]);

export function headlessOrigin(session: { origin?: string }): string {
  const origin = session.origin || "";
  return HEADLESS_ORIGINS.has(origin) ? origin : "";
}
