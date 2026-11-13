# 0010: Duplicates and malformed records

- Status: Accepted (2026-11-13). Revised the same day: a new rule for conflicting duplicates, `R0000134` now valid, and failure rules moved to 0012.
- Related: spec 00 D7, D8; spec 01 sections 1, 4 and 5; [0009](0009-following-links-and-chain-breaks.md), [0012](0012-when-the-run-fails.md)

## Context

The profile found:
- 476 exact-duplicate lines;
- 3 malformed JSON lines (1144, 27119 and 41356);
- no records that share a `links.self` but differ in content;
- 715 company numbers that needed normalising;
- 1 company number, `R0000134`, that the earlier rule didn't recognise. It's an old Northern Ireland number and is now accepted (ADR 0009).

The trailer's PSC count is 3 higher than the parsed count. The gap matches the malformed lines exactly.

## Options

- **Exact duplicates:** keep both, or keep one.
- **Malformed lines:** try to repair them, or reject them.
- **Conflicting duplicates** (same `links.self`, different content): keep the latest `notified_on`, keep the ceased copy, or keep the first copy.

## Decision

- **Exact duplicates** have the same blake2b hash of the line content. We keep the first occurrence and log each extra copy as `duplicate_record`, with action `dropped`.
- **Conflicting duplicates:**
  - Control only moves from active to ceased, never back. So if exactly one copy has a `ceased_on`, we keep that copy.
  - Otherwise we keep the first line.
  - We log `conflicting_duplicate` against every copy, with action `flagged`.
  - We don't compare `notified_on`, because it's almost always the same in both copies.
  - The rule exists even though the sample has none.
- **Malformed JSON:**
  - The line is rejected and logged as `malformed_json`, with action `rejected` and the line number.
  - The `kind` is recovered from the raw text where possible, for the reconciliation.
  - We never try to repair the line.
- **Normalised company number:** logged as `company_number_normalised`, with action `fixed`, the raw value and the fixed value.
- **Unrecognised company number:** the record is rejected from the clean tables and logged as `unrecognised_company_number`, with action `rejected`. Every key in the serving table must pass the shared normalisation function (ADR 0005). The sample has none of these after the fix in 0009.

## Consequences

- With these rules, parsed records plus rejected lines equal the trailer counts. How a gap is handled is in ADR 0012.
- No record disappears without a `data_issue` row.
