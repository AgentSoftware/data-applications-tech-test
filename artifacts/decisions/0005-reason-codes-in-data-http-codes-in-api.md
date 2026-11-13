# 0005: Reason codes in the data; HTTP status codes only in an API

- Status: Accepted (2026-11-13). Revised the same day: added the rule that every key is reachable.
- Related: spec 00 D4, D8, D9, D12

## Context

The user asked whether responses should carry status codes and descriptions. The brief says we don't need to build the API (TASK.md item 6). A small read-only API is an optional extra.

## Decision

- **In the data:** stable, machine-readable reason codes, each with a short description. Each code appears both in the payload and in `data_issue.check`. For example:
  - Company `status`: `ok`, `no_active_psc`, `psc_statement_only`, `exempt`.
  - Unfollowed links: `non_uk_registration`, `foreign_number_collision`, `no_registration_number`, `jurisdiction_missing`, `unrecognised_registration_number`, `uk_company_not_in_snapshot`, `self_ownership`, `cycle`.
  - Cleaning fixes: `company_number_normalised`, `date_timestamp_truncated`, and so on.
- **In an API**, if we build one, standard HTTP status codes:
  - `200`: found. This includes a company that has only a statement or an exemption, with the reason in the body.
  - `400`: malformed company number, after applying the pipeline's normalisation.
  - `404`: valid format but not in the snapshot.
- HTTP codes are never stored in the data.
- The company-number normalisation rule is one shared function, so a lookup for `7655311` finds `07655311`.
- **Every key is reachable.** Every `company_number` in the serving table must pass that function unchanged, and a test checks this. Otherwise a company could be in the data but return `400`. That was the case for `R0000134` before ADR 0009 added the `R` plus 7 digits pattern.

## Consequences

- The data stays independent of how it's served. The same codes work for an API, BigQuery or Elasticsearch.
- The list of codes is documented once, in the data-quality spec, and tested.
