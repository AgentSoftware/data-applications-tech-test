# CLAUDE.md

Tech test: build a PSC pipeline (Part 1) and fix/review a Helm chart (Part 2). The brief is in `TASK.md`.

## Working rules

- **Never `git commit` or `git push` without explicit approval from the user.** Show the changes and ask first.
- `NOTES.md` is written by the user, not by Claude. Don't draft or edit it unless asked.
- Build only what `TASK.md` asks for. Keep it small, tested and end to end.

## Artifacts (`artifacts/`): read them at the start, and keep them up to date

This folder shows the reviewers how AI was used, so treat it as part of the deliverable.

- `artifacts/prompts/prompts-log.md`: every user prompt, appended automatically by the `UserPromptSubmit` hook (`.claude/hooks/log-prompt.sh`). Read it at the start of a session to pick up context and earlier decisions. Don't rewrite past entries.
- `artifacts/plans/`: save each implementation plan here before building, as `NN-<topic>.md` (for example `01-part1-pipeline.md`). Update it when the plan changes.
- `artifacts/specs/`: specs and design decisions (output shape, data-quality rules, what counts as a person, how broken chains are handled).
- `artifacts/agent-instructions/`: copies of this `CLAUDE.md`, the hook script and any skills or subagent prompts, ready for submission.

Don't tidy these files. Remove any secrets before they are committed.
