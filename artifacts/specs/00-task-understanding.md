# 00: Task understanding

Status: **draft, waiting for review**. Sources: `TASK.md` (the brief; `README.md` points to it), `README.md`, `data/README.md`, and a first read-only profile of the sample (throwaway scripts, not project code). The numbers below come from that profile, and the pipeline will recompute them.

## 1. Requirements

### Part 1: Pipeline (the core)

Produce a dataset that serves `GET /companies/{company_number}/persons-with-significant-control`:

| # | Requirement | Source |
|---|---|---|
| R1 | For a company, return the people with significant control **now**, grouped by **control level**. Level 0 is the people registered on the company. Level 1 is the people on its corporate PSCs. Level 2 is the people on their corporate PSCs, and so on up the chain. | TASK §Part 1 |
| R2 | **One lookup by company number.** The API does no other work: no walking the chain at request time, so the result is precomputed per company. | TASK §Part 1.2, team quote |
| R3 | The input is `data/…sample.txt.gz`, **unchanged**. Treat it as a third-party source. | TASK §Part 1.1 |
| R4 | The pipeline **checks the data**. Bad data never reaches the output without anyone knowing, and we can report what the checks found. | TASK §Part 1.3 |
| R5 | **Tests** for the parts that matter. | TASK §Part 1.4 |
| R6 | Python and/or SQL. | TASK §Part 1.5 |
| R7 | No API to build. Only the data it would serve. | TASK §Part 1.6 |
| R8 | We decide what counts as a person and what happens when a chain can't be followed, and we say why. | TASK §Part 1 |

### Part 2: Helm chart

| # | Requirement |
|---|---|
| H1 | Review `kubernetes/helm/psc-pipeline/` **as received, before changing it**, as a PR review. Put it in `REVIEW.md`: each problem and how much it matters. |
| H2 | Change the chart so it **deploys our pipeline correctly**: once installed, the pipeline runs and writes its output. Checking it on a local cluster (kind) is recommended. |
| H3 | In `REVIEW.md`, say what changed for each problem, and which problems were deliberately left unfixed and why. |

### Production write-up (notes only, no code)

Write how this runs for real on GKE, BigQuery, Dataflow, GCS and Elasticsearch, at about 16M records (15 GB) a week. Cover where it runs, how it scales, how we'd know it went wrong, and what changes from what we built.

### Optional extras (one sentence each in the notes is enough)

These are serving it as an API, the reverse lookup (every company a person controls), and handling next week's snapshot. **Not planned for building.**

### Hand-back

- A fork with the work on a branch and a PR against `main`.
- `NOTES.md`: at most about 500 words, **written by the user**, keeping its six headings.
- `REVIEW.md`.
- `artifacts/`.
- `README.md` "Running the solution": the exact commands to run the pipeline from a clean clone, deploy it with the chart, and look up one company.

### Constraints

- A 3 to 4 hour time box. Small and working end to end beats big.
- Our own rules, in `CLAUDE.md`:
  - Plan before building.
  - ADRs go in `artifacts/decisions/`.
  - `data/` is read-only.
  - Python and SQL with pytest.
  - Every check writes to `data_issue`, and nothing is dropped silently.

## 2. What the data looks like (first profile)

The file has 48,154 lines and about 29,125 distinct companies once company numbers are normalised. Each line holds `{company_number, data: {kind, …}}`.

| `data.kind` | Records | Active (no `ceased_on`) |
|---|---:|---:|
| individual-person-with-significant-control | 33,099 | 25,809 |
| corporate-entity-person-with-significant-control | 11,803 | 8,726 |
| persons-with-significant-control-statement | 2,976 | 1,557 |
| legal-person-person-with-significant-control | 106 | 65 |
| individual-beneficial-owner | 65 | 57 |
| corporate-entity-beneficial-owner | 47 | 36 |
| super-secure-person-with-significant-control | 38 | 33 |
| exemptions | 16 | 16 |
| totals#persons-of-significant-control-snapshot (trailer) | 1 | n/a |

These counts include duplicates.

**Data problems found so far.** Most look planted.

| Problem | Count | Notes |
|---|---:|---|
| Malformed JSON lines | 3 | Truncated records. |
| `company_number` not in the 8-character canonical form | about 20 | Leading or trailing spaces, missing leading zeros (`7655311`), lower case (`oc330146`). |
| Exact duplicate records | 476 pairs | Identical lines. No duplicates with the same `self` link and different content were found. |
| `ceased_on` before `notified_on` | 109 | |
| `ceased_on` as a timestamp (`2026-09-22T00:00:00Z`) instead of a date | 5 | |
| `notified_on` in the future (`2026-12-31`, company 01277725) | 1 | The snapshot is dated 2026-10-29. |
| Individuals with no `natures_of_control` | 10 | |
| Corporate PSCs with no `registration_number` | 416 | 241 of them active. |
| Active corporate PSCs whose registration number doesn't match any company in the file | 521 | Includes foreign registrations (Japan, Sweden, Luxembourg `B 116694`, `N/A`) and UK companies missing from the sample. |
| Foreign registration numbers that collide with a UK company in the file after zero-padding | 153 | For example Delaware `2923466` becomes `02923466`. **A trap:** a naive join links them to the wrong company. |
| Registration numbers with inconsistent case | many | For example `Oc360196`, `Sc073998`. |
| `country_registered` in free text | many | England, United Kingdom, Uk, England & Wales, "United Kingdom (England & Wales)", missing, and so on. |
| Companies that own themselves | 19 | |
| Companies in ownership **cycles** | about 47 | |
| Maximum chain depth | 22 | |
| Individuals appearing in more than one record (same name and date of birth) | 2,058 | |

**Totals trailer.** The trailer reports 44,726 PSCs, 2,935 statements and 16 exemptions. After removing exact duplicates, statements (2,935) and exemptions (16) match exactly. PSCs come to 44,723, which is 3 short. The 3 missing records are the 3 malformed lines. So the trailer gives us a **reconciliation check**: records parsed plus records rejected should equal the trailer.

## 3. Ambiguities and decisions to make

Each item becomes an ADR in `artifacts/decisions/` once agreed. **Proposed** is my recommendation, not a decision yet.

### D1. What counts as a "person"?

The candidates are individual PSCs, individual beneficial owners (overseas-entity register), super-secure PSCs (protected identity, no details), legal persons (governments, corporations sole and similar, with no registration number to follow), and corporate PSCs we can't follow.

**Proposed:**
- Individual PSCs and individual beneficial owners are the people listed at each level.
- Super-secure PSCs are listed as a protected person with no details. A customer should see that someone exists rather than an empty result.
- Legal persons and unfollowable corporate PSCs are **not people**. They appear in a separate per-level list of "controllers we could not follow" (name, kind, reason). The response never implies "nobody" when the true answer is "unknown".

### D2. What does "now" mean?

**Proposed:** active means the record has no `ceased_on` and its `notified_on` is no later than the snapshot date (2026-10-29).
- Records with a future `notified_on` are excluded from "now" and logged to `data_issue`.
- When `ceased_on` is before `notified_on`, the record is still treated as ceased. That's the conservative reading. It's flagged.
- Timestamp-format dates are parsed to a date, flagged as `fixed`, and kept.

### D3. How do we link a corporate PSC to the company it points at?

The only link is `identification.registration_number`, plus `country_registered` and `place_registered`.

**Proposed:**
- Follow the link only when the registration looks like a **UK Companies House** one. That means the country or place normalises to the UK (or one of its nations), or the place is Companies House.
- Normalise the number: trim, upper-case, keep any OC, SC or NI style prefix, and zero-pad digits to 8 characters.
- Never follow foreign registrations. That avoids the 153 false matches.
- Every corporate PSC we don't follow gets a `data_issue` row with its reason: `no_registration_number`, `non_uk_registration`, or `uk_company_not_in_snapshot`.

### D4. What happens when a chain can't be followed?

**Proposed:**
- The chain stops at that link.
- The controller is listed at its level under D1's "could not follow" list, with the reason.
- The company still gets its levels up to that point.
- A `data_issue` row records it.

### D5. How do we handle cycles and self-ownership?

**Proposed:**
- Traverse with a per-path visited set. Revisiting a company stops that branch and logs `ownership_cycle`.
- Self-ownership is logged and not followed.
- A hard depth cap (for example 50) acts as a safety net and logs an issue if it's ever hit. The observed maximum depth is 22, so nothing is truncated in this sample.

### D6. What if the same person is reachable along several paths or levels?

**Proposed:**
- List each person **once, at the lowest level** where they're reached. That's their most direct control.
- Keep the companies we reached them through (`via`) so customers can see the route.

**Identity:** the snapshot has no stable cross-company ID for individuals. The link IDs belong to each appointment, not to the person. To de-duplicate within one company's response, use name plus date of birth (month and year). `data/README.md` says fake details are consistent per person, which supports this. It's a heuristic, and false merges are possible in the real data.

### D7. How do we handle duplicates and conflicting records?

**Proposed:**
- Drop exact duplicates and log `duplicate_record` with the action `dropped`.
- If two records share a `self` link but differ in content, keep one by a deterministic rule and log both. None exist in this sample, but the rule should be there.

### D8. How do we handle malformed records and keys?

**Proposed:**
- **Malformed JSON:** reject the line and log it with its line number.
- **Company number:** normalise it (trim, upper-case, zero-pad digits) and log `fixed`.
- **Unknown `kind` or missing required fields:** reject or flag and log.
- **Trailer:** not data. Use it only for reconciliation.

### D9. When should the pipeline fail, rather than only warn?

**Proposed:** it fails, with a non-zero exit and no output published, when:
- the reconciliation against the trailer doesn't balance (parsed plus rejected not equal to the trailer), or
- the malformed share exceeds a threshold (for example 1%), or
- the input is missing or empty.

Everything else warns and writes a `data_issue` row. A summary report counts issues by type and action.

### D10. What output store and shape?

The chart already bundles **PostgreSQL**, so the natural target is:
- `psc_by_company(company_number PK, payload JSONB, generated_at)`: one row per company, and the API does `SELECT payload WHERE company_number = $1`.
- `data_issue(run_id, issue_type, severity, action, company_number, source_line, record_ref, detail)`.
- A run summary table or report.

Locally we need a way to run without a cluster: Postgres in Docker, or a file output (JSONL or SQLite) behind the same interface. **Open question Q1.**

### D11. How do we compute it?

Options:
- **(a)** Plain Python: parse, validate, build the graph in memory, traverse.
- **(b)** Load the raw data into SQL and use a recursive CTE for the chains.
- **(c)** DuckDB: SQL locally, then load into Postgres.

**Proposed:** (a) for parsing, checks and traversal. It's the easiest to test and to make cycle-safe. SQL is used for the output schema and the lookup. At 16M records this changes (see Production). **Open question Q2.**

### D12. Which companies get a row, and what goes in it?

**Proposed:**
- Every company in the snapshot gets a row, including those with no active PSCs.
- Each row includes active **statements** and **exemptions**, so an empty person list has an explanation, for example "no individual or entity with significant control".
- Each person entry: name, name elements, kind, natures of control, `notified_on`, nationality, country of residence, date of birth (month and year), and `via`.
- **Address is excluded**, to keep personal data to a minimum. **Open question Q3.**

### D13. Does any nature of control stop us following a chain?

An example is a corporate PSC that only has the right to appoint directors.

**Proposed:** follow every active corporate PSC whatever its natures of control. Keep the natures in the output so the API or customer can filter.

### D14. Which corporate PSCs do we follow?

**Proposed:** follow `corporate-entity-beneficial-owner` exactly like a corporate PSC. It's on the overseas-entity register and is usually foreign, so D3 often stops it.

## 4. Questions for you

- **Q1.** Output target: Postgres only (Docker locally, matching the chart), or a file output locally plus Postgres in the cluster?
- **Q2.** Computation: plain Python for the traversal (proposed), or a recursive-CTE SQL approach?
- **Q3.** Person fields: leave out addresses (proposed), or include them?
- **Q4.** A person reached along several paths: list once at the lowest level (proposed), or at every level they appear?
- **Q5.** Super-secure and unfollowable controllers: show them as placeholders (proposed), or leave them out of the response and keep them only in `data_issue`?

### Answers (2026-11-13)

- **Q1:** Postgres both locally and in the cluster, with Docker Compose for local runs. See ADR 0006.
- **Q2:** BFS in Python. See ADR 0001.
- **Q3:** Still open. Addresses stay out by default (ADR 0002).
- **Q4:** ~~Lowest level by default, with `route_count` and `other_levels`. All routes go in a separate table (capped), for an optional `all_routes` parameter.~~ Revised after review: each registration is listed at its company's lowest level, with `via` and `route_count` (the number of shortest routes). People aren't merged, and there's no all-routes table; that goes in `NOTES.md` as a next step. See ADR 0003.
- **Q5:** Super-secure PSCs always appear as protected placeholders. A reveal option isn't possible because the source has no identity (ADR 0004). Unfollowable corporate PSCs appear in an `unfollowed` list with a reason code (ADRs 0005 and 0009). Legal persons appear in `other_controllers` (ADR 0007).
- **Q3 (closed):** addresses, nationality and country of residence are left out. Month and year of birth stay in the answer (ADR 0011).

## 5. Out of scope (unless we have time left)

The API itself, the reverse lookup, incremental weekly loads, and fuzzy matching of unresolvable corporates by name.
