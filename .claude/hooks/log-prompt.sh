#!/usr/bin/env bash
# UserPromptSubmit hook: append each user prompt to artifacts/prompts/prompts-log.md
# Reads the hook payload (JSON) on stdin. Never blocks the prompt.
set -euo pipefail

root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
log="$root/artifacts/prompts/prompts-log.md"
mkdir -p "$(dirname "$log")"

payload="$(cat)"
prompt="$(printf '%s' "$payload" | jq -r '.prompt // empty')"
session="$(printf '%s' "$payload" | jq -r '.session_id // "unknown"')"
[ -z "$prompt" ] && exit 0

if [ ! -f "$log" ]; then
  printf '# Prompt log\n\nEvery prompt sent to Claude Code in this repo, appended automatically by `.claude/hooks/log-prompt.sh`. Review for secrets before committing.\n' > "$log"
fi

{
  printf '\n## %s  (session `%s`)\n\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "${session:0:8}"
  printf '%s\n' "$prompt"
} >> "$log"
