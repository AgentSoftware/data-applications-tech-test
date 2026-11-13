# 0002: Clean tables, plus one serving row per company in Postgres

- Status: Accepted (2026-11-13)
- Related: spec 00 D10, D12; [0006](0006-local-postgres-with-docker-compose.md)

## Context

There are three requirements:
- one lookup per request, with no other API work;
- efficient storage;
- cleaning that never "ruins" the original data.

These pull against each other. A self-contained answer per company repeats people: everyone at the top of a large group is copied into every subsidiary's row.

## Options

1. **Serving table only:** one JSON document per company.
2. **Normalised tables only:** the API joins and filters at request time.
3. **Normalised clean tables plus a denormalised serving table** built from them.

## Decision

Option 3, in Postgres (the chart already bundles it).
- **Clean tables** hold each fact once: `psc`, `statement`, `exemption`, `ownership_link`, `data_issue` and `pipeline_run`. Each cleaned field sits next to its original value (for example `company_number_raw` and `company_number`), and every row carries `source_line`.
- **A derived table** `company_ancestor(company_number, ancestor_company_number, level, via, route_count)` holds the BFS output: one row for each company and each company above it. The serving table is built from it, and it makes each answer easy to test and explain.
- **The serving table** `psc_by_company(company_number PK, payload JSONB)` holds one row per company. Postgres compresses large JSONB values automatically (TOAST), and the primary-key B-tree index makes the lookup a single index read.
- **The raw file is the untouched source of truth, so it must be kept.** `source_line` and the hash only mean something while that file exists. Each run records the file's SHA-256 in `pipeline_run`. In production, raw snapshots are kept in GCS for a fixed retention period (for example 12 weeks), and runs older than that can no longer be traced back to their source line.
- **No copy of the raw JSON in the database.** We don't copy the raw JSON into the database. The line number and the record hash point back to it, and each change made during cleaning has a `data_issue` row. That makes every fix traceable and reversible without storing the data twice.
- Payloads leave out null fields, and personal data is kept to a minimum (see [0011](0011-personal-data-in-the-output.md)).

## Consequences

- Read speed wins over storage, as the brief asks. The repetition is deliberate and limited to the serving table.
- The clean tables support checks, debugging and the optional reverse question ("every company a person controls") without reparsing the file.
- A weekly refresh can build into a staging schema and swap it in within one transaction, so readers never see a half-written output.
