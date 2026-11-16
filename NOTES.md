# Notes

<!-- One page at most, about 500 words. Write this yourself, not with AI. Keep the six headings. See "What to hand back" in TASK.md. -->

## What I built
An ETL pipeline that turns the PSC weekly snapshot into one JSON document per company in Postgres, so the full ownership chain can be seen with a single lookup. 
 - Data profiling, cleaning and consistency checks; every dropped or fixed record is logged. 
 - A fixed Helm chart so the pipeline runs reliably every week.

## Decisions
All detailed ADRs are here [`artifacts/decisions/`](artifacts/decisions/).

- **Traversing the ownership chain:** BFS; over company-to-company links (level, via, route_count), handling cycles, depth cap and shortest path if there are multiple routes (0001,0003).
- **People:** individuals only; super-secure PSCs as placeholders; legal persons as "other controllers" (0004, 0007, 0011).
- **Rules while parsing and following links:** 
 - Only follow UK registrations, the rest keep with reason code (0009).
 - Active means not ceased by the snapshot date(0008).
- **Fail on a small set of checks:** that mean "this output can't be trusted", warn on everything else (0002,0012)
- **Chart:** the sample in the image by default, download as an opt-in, one secret, and a lock against concurrent runs (0014,0015).

## How I checked it
- **Data profiling:** started by sampling the data to inspect it and check the fields, then ran a full data profile to understand it better and validate its quality.
- **Code:** unit tests focused on edge cases such as loops, multiple routes and the depth limit, plus end-to-end tests that compare the Postgres output with a hand-written expected answer.
- **Chart:** used AI to understand the basic structure of a Helm chart and the minimum settings needed to run stable schedule, installed the chart unchanged first, to confirm the review, then tested the fix using Kind.
- **AI:** the second agent's ADR review, the per-step bug reports and ask of any dodgy design (found a password risk, missing chart tests).

## How I worked
Used Claude Code and set some rules and asks:
1. Log every prompt [hook](.claude/hooks/log-prompt.sh)
2. Plan before code
3. Check functions time complexity 
4. Don't commit without review
5. Concise code, and only warnings and errors in `data_quality`.
6. Helm was new to me, so after getting some info I set requiremnts for
    - data that survives failures, no concurrent runs, simple secrets, freshness checks.

Test pipeline locally with Docker Desktop.
Brief → spec → data profile → data model → ADRs → plan, all before code. Then small steps: approve, build with tests, report complexity and bugs, commit.

## Production

Replace the single in-memory process with:
- **GCS Ingest:** a scheduled job lands the snapshot in a cloud storage, keyed by date
- **Process:** BigQuery to parse, clean and deduplicate in SQL, with BFS as one Python step; or the current pipeline as a GKE/Cloud Run job. Choose by data size and scalability needs.
- **Serve:** Postgres (Cloud SQL) for lookup by company number.
- **Alerts:** failed job, 8 days without new snapshot, issue rates

## What I'd do next
- Weekly load strategy (incremental, overwrite or append)
- Checking the pattern of bad quaility record agains the actual source (in possible) to handle cases like bad dates
- Weak in production: memory at full scale, no audit backups.
