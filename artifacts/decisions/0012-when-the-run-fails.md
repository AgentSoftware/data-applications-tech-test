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
