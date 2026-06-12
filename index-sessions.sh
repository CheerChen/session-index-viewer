#!/usr/bin/env bash

set -euo pipefail

output_path="${1:-./sessions-index.json}"
limit="${2:-${SESSION_INDEX_LIMIT:-100}}"
tmp_file="$(mktemp)"
candidate_file="$(mktemp)"

cleanup() {
  rm -f "$tmp_file"
  rm -f "$candidate_file"
}

trap cleanup EXIT

jq_cmd="${JQ_BIN:-jq}"

if ! command -v "$jq_cmd" >/dev/null 2>&1; then
  echo "jq not found: $jq_cmd" >&2
  exit 1
fi

append_codex_session() {
  local file="$1"

  "$jq_cmd" -rs '
    def join_text($field; $type):
      map(select(.type == "response_item" and .payload.type == "message" and .payload.role == $field))
      | if length == 0 then "" else last.payload.content | map(select(.type == $type) | .text) | join("\n") end;
    def last_user_text:
      map(select(.type == "response_item" and .payload.type == "message" and .payload.role == "user"))
      | map(.payload.content | map(select(.type == "input_text") | .text) | join("\n"))
      | map(select(. != "" and (startswith("<environment_context>") | not) and (startswith("<turn_aborted>") | not)))
      | if length == 0 then "" else last end;
    def session_meta:
      map(select(.type == "session_meta")) | first | .payload;
    def last_timestamp:
      map(select(.timestamp? != null) | .timestamp) | last;
    def clean:
      gsub("[\r\n\t]+"; " ")
      | gsub("  +"; " ")
      | sub("^ "; "")
      | sub(" $"; "");
    def clean_multiline:
      gsub("\r"; "")
      | gsub("\t+"; " ")
      | gsub(" +\n"; "\n")
      | gsub("\n +"; "\n")
      | gsub("\n{3,}"; "\n\n")
      | sub("^\n+"; "")
      | sub("\n+$"; "");
    def clip($n):
      if (length > $n) then .[0:$n] + "..." else . end;

    session_meta as $meta
    | {
        sort_ts: (last_timestamp // $meta.timestamp // ""),
        source: "codex",
        cwd: ($meta.cwd // ""),
        session_id: ($meta.id // ""),
        last_user: (last_user_text | clean | clip(360)),
        last_assistant: (join_text("assistant"; "output_text") | clean_multiline)
      }
    | select(.sort_ts != "" and .session_id != "")
    | .
  ' "$file" >> "$tmp_file"
  printf '\n' >> "$tmp_file"
}

append_claude_session() {
  local file="$1"

  "$jq_cmd" -rs '
    def content_text:
      if . == null then ""
      elif type == "string" then .
      elif type == "array" then map(select(.type == "text") | .text) | join("\n")
      else ""
      end;
    def last_user_text:
      map(select(.type == "user"))
      | map(select((.message.content | type) == "string"))
      | map(.message.content | content_text)
      | map(select(. != ""))
      | if length == 0 then ""
        else last
        end;
    def assistant_text:
      .message.content | content_text;
    def last_text_assistant:
      map(select(.type == "assistant"))
      | map(select((assistant_text) != ""))
      | if length == 0 then null else last end;
    def last_timestamp:
      map(select(.timestamp? != null) | .timestamp) | last;
    def clean:
      gsub("[\r\n\t]+"; " ")
      | gsub("  +"; " ")
      | sub("^ "; "")
      | sub(" $"; "");
    def clean_multiline:
      gsub("\r"; "")
      | gsub("\t+"; " ")
      | gsub(" +\n"; "\n")
      | gsub("\n +"; "\n")
      | gsub("\n{3,}"; "\n\n")
      | sub("^\n+"; "")
      | sub("\n+$"; "");
    def clip($n):
      if (length > $n) then .[0:$n] + "..." else . end;

    last_text_assistant as $assistant
    | select($assistant != null)
    | {
        sort_ts: (last_timestamp // $assistant.timestamp // ""),
        source: "claude",
        cwd: ($assistant.cwd // ""),
        session_id: ($assistant.sessionId // ""),
        last_user: (last_user_text | clean | clip(360)),
        last_assistant: ($assistant | assistant_text | clean_multiline)
      }
    | select(.sort_ts != "" and .session_id != "")
    | .
  ' "$file" >> "$tmp_file"
  printf '\n' >> "$tmp_file"
}

shopt -s nullglob

for file in "$HOME"/.codex/sessions/*/*/*/rollout-*.jsonl; do
  stat -f '%m|codex|%N' "$file" >> "$candidate_file"
done

for file in "$HOME"/.claude/projects/*/*.jsonl; do
  stat -f '%m|claude|%N' "$file" >> "$candidate_file"
done

LC_ALL=C sort -r -n -t '|' -k1,1 "$candidate_file" | head -n "$limit" |
while IFS='|' read -r _ source file; do
  if [[ "$source" == "codex" ]]; then
    append_codex_session "$file"
  else
    append_claude_session "$file"
  fi
done

"$jq_cmd" -s --argjson limit "$limit" '
  def stable_unique_by_session:
    reduce .[] as $item (
      {seen: {}, items: []};
      ($item.source + "|" + $item.session_id) as $key
      | if .seen[$key] then .
        else .seen[$key] = true | .items += [$item]
        end
    ) | .items;

  sort_by(.sort_ts) | reverse
  | stable_unique_by_session
  | .[:$limit]
  | map({
      source,
      timestamp: .sort_ts,
      cwd,
      session_id,
      last_user,
      last_assistant
    })
' "$tmp_file" > "$output_path"

echo "Wrote recent $limit sessions to $output_path"
