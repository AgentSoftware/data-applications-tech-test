# 0012: When the run fails, when it only warns, and where the report goes

- Status: Accepted (2026-11-13)
- Related: spec 00 D9; [0008](0008-active-and-ceased-records.md), [0010](0010-duplicates-and-malformed-records.md); TASK.md Part 1, item 3 ("you must be able to tell us what the checks found"), and the production write-up ("how you would know it had gone wrong")

## Context

Every check writes to `data_issue`, but a few results should stop the weekly refresh altogether, because publishing would serve wrong or incomplete answers.

Being too strict has a cost too: for example, a bug in the third party's totals line would block every refresh. Rates in the sample:
- malformed lines: 3 of 48,154 (0.006%);
- trailer gap after counting rejected lines: 0;
- active corporate links not followed: about 9%, which is expected in a subset.

## Options

1. Fail on any issue.
2. Never fail. Always publish and report.
3. Fail on a small set of checks that mean "this output can't be trusted", warn on everything else, with thresholds that can be configured.

## Decision

Option 3. A failed run exits non-zero, sets `pipeline_run.run_status = failed` and **doesn't publish**: the serving table keeps last week's data (ADR 0002 swaps it in only on success).

| check | fails the run when | otherwise |
|---|---|---|
| Input missing, empty or not gzip | always | |
| Trailer missing | always (no snapshot date, nothing to reconcile) | |
| Reconciliation: trailer count minus (parsed distinct plus rejected), per kind | the gap is more than 0.1% of the trailer count | any non-zero gap is a warning |
| Malformed lines | more than 0.1% of lines | warning, with each line in `data_issue` |
| A serving key fails normalisation (ADR 0005) | always (it's a pipeline bug) | |
| Empty output (no serving rows) | always | |
| Snapshot date in the file name differs from the trailer | | warning (ADR 0008) |
| Unfollowed links as a share of active corporate links | | a recorded metric; warning above 15% |
| Depth cap reached (ADR 0001) | | warning |
| Everything else in the catalogue of issue codes | | logged in `data_issue` only |

Thresholds are run settings with these defaults, not values in the code.

**Where the report goes:**
- **`pipeline_run`** holds one row per run: counts, reconciliation, status and the failure reason.
- **`data_issue`** holds one row per finding.
- **A short text summary** of issue counts by check and action, plus the pass or fail lines, is printed at the end of each run (revised 2026-11-14: no separate file, to keep the code small).
- Spec 02 sets the exact layout.

## Consequences

- Bad data never reaches the output without a record. A failure leaves the previous week's answers in place.
- The thresholds are judgement calls, and they're easy to tune. In production they become alerts (see the production section of `NOTES.md`).

## Amendment (2026-11-14): freshness and week-on-week completeness

**Context.** The run checks only looked at the file itself. Nothing asked whether the snapshot was recent, newer than what's already published, or much smaller than last week's. The chart as received had exactly this bug: the same fixed-date file every week. The user asked whether completeness and freshness checks were needed.

**Options.** (1) Leave it to monitoring. (2) Check it in the pipeline, against the last published run in `psc_audit.pipeline_run` (status `succeeded`, not a dry run).

**Decision.** Option 2, with one query at the start of a writing run. A dry run has no database, so it skips these checks.

| check_code | Rule | Severity |
|---|---|---|
| `snapshot_not_newer` | `snapshot_date` older than the last published run's | error, fails: never replace newer data with older |
| `snapshot_already_loaded` | same `source_sha256` as the last published run | warning: a rerun is allowed |
| `snapshot_stale` | `snapshot_date` more than 8 days before the run date | warning |
| `company_count_drop` | companies down by more than 5% on the last published run | warning; error that fails above 20% |

**Consequences.** The baked-in sample (2026-10-29) is stale on every run after 2026-11-06, so the chart's default run always warns `snapshot_stale` and, from the second run, `snapshot_already_loaded`. That's true and intended. The same date reloaded is allowed, so reruns still publish. "The last succeeded run is too old" is a serving-side alert, so it stays in monitoring (NOTES).
