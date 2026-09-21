// Session shapes returned by GET /api/sessions. The `usage` field is
// present when an adapter can derive token/tool metrics (Claude, Codex,
// Devin, Grok). Field semantics differ by source — see usage utils.

export interface SessionUsage {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  tool_calls: number;
  user_turns: number;
  messages: number;
  peak_context_tokens: number;
  duration_s: number;
  model: string;
}

export interface Session {
  source: "claude" | "codex" | "devin" | "grok" | "pi" | "copilot" | "opencode" | string;
  host: string;
  timestamp: string;
  cwd: string;
  session_id: string;
  title: string;
  first_user: string;
  last_user: string;
  last_assistant: string;
  resume_command: string;
  usage: SessionUsage | null;
  // Server sets this false when ~/.Trash is unavailable — the delete UI
  // hides entirely rather than erroring at click time.
  deletable?: boolean;
  // Client that started the session (codex originator: codex-tui,
  // codex_vscode, codex_exec, acpx, codex_cli_rs). Empty when unknown.
  origin?: string;
}

// Toolbar "Turns" filter: maximum user turns a session may have.
// "any" disables the filter; numeric strings mean user_turns <= N.
export type TurnsFilter = "any" | "1" | "2" | "3";

export type SourceFilter =
  | "all"
  | "claude"
  | "codex"
  | "devin"
  | "grok"
  | "pi"
  | "copilot"
  | "opencode";

// Full-conversation message shape returned by GET /api/session. Only
// devin exposes messages today; other sources can add a page later.
export interface SessionMessage {
  node_id: number;
  role: string;
  content: string;
  created_at?: string;
  thinking?: string;
  tool_call_count?: number;
}

export interface SessionMessages {
  source: string;
  session_id: string;
  total: number;
  page: number;
  page_size: number;
  pages: number;
  messages: SessionMessage[];
}
