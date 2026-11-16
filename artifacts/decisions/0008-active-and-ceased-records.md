# 0008: Active ("now") and ceased records

- Status: Accepted (2026-11-13). Revised the same day: added future end dates, the trailer date, and statements and exemptions.
- Related: spec 00 D2; spec 01 section 6; [0012](0012-when-the-run-fails.md)

## Context

The endpoint returns PSCs **now**. The profile found:
- 107 records with `ceased_on` before `notified_on`;
- 4 `ceased_on` values written as timestamps;
- 1 future `notified_on` (2026-12-31);
- 43 overseas-entity `notified_on` dates before the PSC regime started (2016-04-06), which is valid for that register.

The trailer line includes `generated_at: 2026-10-29T07:08:01Z`.

## Options

1. Active means there's no `ceased_on`.
2. Active means it's in force on the snapshot date: `notified_on` is on or before the snapshot date, and `ceased_on` is empty or later than it.
3. Trust whatever the record says, and don't check dates.

## Decision

Option 2.
- **The snapshot date** is the date part of the trailer's `generated_at`. We check it against the date in the file name. If they differ, we log `snapshot_date_mismatch` (a warning) and use the trailer date, because it comes from the data itself. A missing trailer fails the run (ADR 0012).
- **The rule:** active = `notified_on <= snapshot_date AND (ceased_on IS NULL OR ceased_on > snapshot_date)`. A future `ceased_on` therefore still counts as active. There are none in the sample, but the rule covers it.
- **Statements** use the same rule. A withdrawn statement (with a `ceased_on`) isn't shown. **Exemptions** have no dates in the data, so they're shown as long as they're in the snapshot.
- **Ceased records** stay in the clean tables with `is_active = false`, but are left out of the answer. A normal ceased record is valid history, **not** a data issue, so it gets no `data_issue` row.
- **`ceased_on` earlier than `notified_on`:** the record is treated as ceased, because "no longer in control" is the safer reading. It's logged as `ceased_before_notified`, with action `flagged`.
- **Timestamp-format dates:** cut down to the date and logged as `date_timestamp_truncated`, with action `fixed`. The raw value is kept in `ceased_on_raw`.
- **Future `notified_on`:** treated as not active yet and logged as `notified_after_snapshot`, with action `flagged`.
- **Pre-2016 overseas-entity dates:** accepted with no issue. The check applies only to PSC kinds.
- **Super-secure records** have a `ceased` flag instead of dates. Active means `ceased = false`.

## Consequences

- The meaning of "now" comes from the data itself, with no dependency on the clock, and it can be reproduced.
- Each odd date leaves a row in `data_issue`, so analysts can review the calls we made.
